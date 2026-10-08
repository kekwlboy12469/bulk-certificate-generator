from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.recipient import Recipient, RecipientStatus
from app.models.job import Job
from app.schemas.certificate import CertificateDetailResponse, CertificateVerifyResponse
from app.services.storage import storage_service
from app.security import verify_rate_limiter

router = APIRouter(prefix="/certificates", tags=["Certificates"])


@router.get(
    "/{certificate_id}",
    response_model=CertificateDetailResponse,
    summary="Get certificate details and metadata",
    description="Retrieves metadata for a specific issued certificate.",
)
def get_certificate_details(certificate_id: str, db: Session = Depends(get_db)):
    recipient = (
        db.query(Recipient)
        .filter(Recipient.certificate_id == certificate_id, Recipient.status == RecipientStatus.SUCCESS.value)
        .first()
    )
    if not recipient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate '{certificate_id}' not found or was not successfully issued.",
        )

    job = db.query(Job).filter(Job.id == recipient.job_id).first()

    return CertificateDetailResponse(
        certificate_id=recipient.certificate_id,
        recipient_name=recipient.name,
        recipient_email=recipient.email,
        event_name=job.event_name if job else "N/A",
        issuer_name=job.issuer_name if job else "N/A",
        issue_date=job.issue_date if job else "N/A",
        description=job.description if job else None,
        extra_data=recipient.extra_data,
        created_at=recipient.processed_at.isoformat() if recipient.processed_at else None,
        download_url=f"/api/v1/certificates/{recipient.certificate_id}/download",
    )


@router.get(
    "/{certificate_id}/download",
    summary="Download certificate as PDF",
    description="Streams the generated PDF certificate document.",
)
def download_certificate(certificate_id: str, db: Session = Depends(get_db)):
    recipient = (
        db.query(Recipient)
        .filter(Recipient.certificate_id == certificate_id, Recipient.status == RecipientStatus.SUCCESS.value)
        .first()
    )
    if not recipient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Certificate '{certificate_id}' not found.",
        )

    if not recipient.file_path or not Path(recipient.file_path).exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Certificate PDF file is missing from storage.",
        )

    clean_name = storage_service.sanitize_filename(recipient.name)
    download_filename = f"Certificate_{clean_name}_{recipient.certificate_id}.pdf"

    return FileResponse(
        path=recipient.file_path,
        media_type="application/pdf",
        filename=download_filename,
    )


@router.get(
    "/verify/{certificate_id}",
    response_model=CertificateVerifyResponse,
    summary="Public verification for a certificate",
    description="Verifies the authenticity and validity of an issued certificate ID. Protected by rate limiting.",
)
def verify_certificate(certificate_id: str, request: Request, db: Session = Depends(get_db)):
    # Enforce sliding-window rate limit per client IP
    verify_rate_limiter.check(request)

    recipient = (
        db.query(Recipient)
        .filter(Recipient.certificate_id == certificate_id, Recipient.status == RecipientStatus.SUCCESS.value)
        .first()
    )
    if not recipient:
        return CertificateVerifyResponse(
            is_valid=False,
            certificate_id=certificate_id,
            verification_message="Certificate could not be verified. It may be invalid or not yet issued.",
        )

    job = db.query(Job).filter(Job.id == recipient.job_id).first()

    return CertificateVerifyResponse(
        is_valid=True,
        certificate_id=recipient.certificate_id,
        recipient_name=recipient.name,
        event_name=job.event_name if job else "N/A",
        issuer_name=job.issuer_name if job else "N/A",
        issue_date=job.issue_date if job else "N/A",
        verification_message="Certificate is authentic and officially verified.",
    )
