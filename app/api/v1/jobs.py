import hashlib
import json
from datetime import date
from typing import Optional, List
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks, Query, Header
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.config import settings
from app.models.job import Job, JobStatus, get_utc_now
from app.models.recipient import Recipient, RecipientStatus
from app.schemas.job import (
    JobCreateRequest,
    JobSummaryResponse,
    JobDetailResponse,
    JobListResponse,
    JobRetryResponse,
)
from app.schemas.recipient import RecipientResponse
from app.services.processor import process_generation_job, is_safe_webhook_url
from app.services.storage import storage_service
from app.security import verify_api_key

router = APIRouter(prefix="/jobs", tags=["Jobs"])


def compute_payload_hash(payload: JobCreateRequest) -> str:
    """Computes a deterministic SHA-256 hash of the job payload for idempotency verification."""
    data_dict = {
        "event_name": payload.event_name,
        "issuer_name": payload.issuer_name,
        "issue_date": payload.issue_date,
        "description": payload.description,
        "template_type": payload.template_type,
        "recipients": [
            {"name": r.name, "email": r.email, "extra_data": r.extra_data}
            for r in payload.recipients
        ]
    }
    encoded = json.dumps(data_dict, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@router.post(
    "",
    response_model=JobSummaryResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Submit a bulk certificate generation job",
    description="Accepts a list of recipients and enqueues an asynchronous background job to generate certificates. Supports Idempotency-Key header and payload verification.",
)
def create_generation_job(
    payload: JobCreateRequest,
    background_tasks: BackgroundTasks,
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    _auth: Optional[str] = Depends(verify_api_key),
):
    # 1. SSRF Protection: Validate Webhook Destination upfront if provided
    if payload.webhook_url:
        is_safe, ssrf_err = is_safe_webhook_url(payload.webhook_url)
        if not is_safe:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Security rejection for webhook_url: {ssrf_err}",
            )

    payload_hash = compute_payload_hash(payload)

    # 2. Idempotency Check
    if idempotency_key:
        existing_job = db.query(Job).filter(Job.idempotency_key == idempotency_key).first()
        if existing_job:
            # If the same key is reused with a DIFFERENT payload, reject with 409 Conflict
            if existing_job.payload_hash and existing_job.payload_hash != payload_hash:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Idempotency-Key reuse error: A job with this Idempotency-Key already exists with a different request payload.",
                )
            return JobSummaryResponse(**existing_job.to_dict())

    # 3. Batch-level Recipient Email Deduplication (if requested)
    recipients_input = payload.recipients
    if payload.deduplicate_emails:
        seen_emails = set()
        deduped = []
        for r in recipients_input:
            email_lower = (r.email or "").strip().lower()
            if email_lower and email_lower in seen_emails:
                continue
            if email_lower:
                seen_emails.add(email_lower)
            deduped.append(r)
        recipients_input = deduped

    issue_date = payload.issue_date or str(date.today())
    issuer_name = payload.issuer_name or settings.DEFAULT_ISSUER_NAME

    job = Job(
        idempotency_key=idempotency_key,
        payload_hash=payload_hash,
        webhook_url=payload.webhook_url,
        event_name=payload.event_name,
        issuer_name=issuer_name,
        issue_date=issue_date,
        description=payload.description,
        template_type=payload.template_type or "classic",
        status=JobStatus.PENDING.value,
        total_recipients=len(recipients_input),
        processed_recipients=0,
        successful_recipients=0,
        failed_recipients=0,
    )
    db.add(job)

    try:
        db.flush()
        # Create recipient entries
        recipients_to_create = []
        for r in recipients_input:
            recipient = Recipient(
                job_id=job.id,
                name=r.name or "",
                email=r.email or "",
                extra_data=r.extra_data,
                status=RecipientStatus.PENDING.value,
            )
            recipients_to_create.append(recipient)

        db.add_all(recipients_to_create)
        db.commit()
    except IntegrityError:
        # Concurrent insertion race condition for identical Idempotency-Key
        db.rollback()
        if idempotency_key:
            existing_job = db.query(Job).filter(Job.idempotency_key == idempotency_key).first()
            if existing_job:
                if existing_job.payload_hash and existing_job.payload_hash != payload_hash:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Idempotency-Key reuse error: Concurrent submission with different payload.",
                    )
                return JobSummaryResponse(**existing_job.to_dict())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database integrity conflict during job creation.",
        )

    db.refresh(job)

    # Dispatch to background task processing
    background_tasks.add_task(process_generation_job, job.id)

    return JobSummaryResponse(**job.to_dict())


@router.get(
    "",
    response_model=JobListResponse,
    summary="List all certificate generation jobs",
    description="Returns a paginated list of certificate generation jobs.",
)
def list_jobs(
    status_filter: Optional[str] = Query(None, alias="status", description="Filter by status (PENDING, PROCESSING, COMPLETED, PARTIALLY_FAILED, FAILED)"),
    limit: int = Query(50, ge=1, le=100, description="Number of jobs to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    db: Session = Depends(get_db),
):
    query = db.query(Job)
    if status_filter:
        query = query.filter(Job.status == status_filter.upper())
    
    total = query.count()
    jobs = query.order_by(Job.created_at.desc()).offset(offset).limit(limit).all()

    return JobListResponse(
        total=total,
        items=[JobSummaryResponse(**j.to_dict()) for j in jobs],
    )


@router.get(
    "/{job_id}",
    response_model=JobDetailResponse,
    summary="Get job status, progress, and recipient details",
    description="Returns real-time progress, counts, and per-recipient certificate status.",
)
def get_job_status(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found.",
        )

    job_data = job.to_dict()
    recipient_responses = [RecipientResponse(**r.to_dict()) for r in job.recipients]
    
    download_all = None
    if job.successful_recipients > 0:
        download_all = f"/api/v1/jobs/{job.id}/download-all"

    return JobDetailResponse(
        **job_data,
        recipients=recipient_responses,
        download_all_url=download_all,
    )


@router.post(
    "/{job_id}/retry",
    response_model=JobRetryResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Retry failed recipients in a job",
    description="Re-enqueues processing only for failed or pending recipients in this job without regenerating successful certificates.",
)
def retry_failed_recipients(
    job_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    _auth: Optional[str] = Depends(verify_api_key),
):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found.",
        )

    failed_recipients = (
        db.query(Recipient)
        .filter(Recipient.job_id == job_id, Recipient.status == RecipientStatus.FAILED.value)
        .all()
    )

    if not failed_recipients:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No failed recipients found in this job to retry.",
        )

    count = len(failed_recipients)
    for r in failed_recipients:
        r.status = RecipientStatus.PENDING.value
        r.error_message = None

    job.failed_recipients = max(0, job.failed_recipients - count)
    job.processed_recipients = max(0, job.processed_recipients - count)
    job.status = JobStatus.PROCESSING.value
    job.completed_at = None
    db.commit()

    background_tasks.add_task(process_generation_job, job.id)

    return JobRetryResponse(
        id=job.id,
        status=job.status,
        retried_recipients_count=count,
        message=f"Successfully re-enqueued {count} failed recipient(s) for processing.",
    )


@router.get(
    "/{job_id}/download-all",
    summary="Download all generated certificates as a ZIP archive",
    description="Retrieves a compressed ZIP file containing all successfully generated certificates for the job.",
)
def download_all_certificates(job_id: str, db: Session = Depends(get_db)):
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job with ID '{job_id}' not found.",
        )

    successful_recipients = (
        db.query(Recipient)
        .filter(Recipient.job_id == job_id, Recipient.status == RecipientStatus.SUCCESS.value)
        .all()
    )

    if not successful_recipients:
        if job.status in [JobStatus.PENDING.value, JobStatus.PROCESSING.value]:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Job is currently processing and no certificates are ready yet. Please check back shortly.",
            )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No successful certificates available for download in this job.",
        )

    cert_files = []
    for r in successful_recipients:
        if r.file_path and Path(r.file_path).exists():
            cert_files.append((r.name, Path(r.file_path)))

    if not cert_files:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certificate files were not found on storage.",
        )

    zip_path = storage_service.create_job_zip(job_id=job.id, cert_files=cert_files)
    safe_event_name = storage_service.sanitize_filename(job.event_name)
    download_filename = f"certificates_{safe_event_name}_{job.id[:8]}.zip"

    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=download_filename,
    )
