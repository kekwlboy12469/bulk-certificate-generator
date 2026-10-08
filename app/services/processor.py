import logging
import re
import secrets
import socket
import ipaddress
import urllib.parse
from typing import Tuple, List
from datetime import datetime, timezone
import httpx

from app.config import settings
from app.database import SessionLocal
from app.models.job import Job, JobStatus, get_utc_now
from app.models.recipient import Recipient, RecipientStatus
from app.services.generator import certificate_generator
from app.services.storage import storage_service

logger = logging.getLogger(__name__)

# RFC-compliant email regex
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")


def validate_recipient_data(name: str, email: str) -> Tuple[bool, List[str]]:
    """
    Validates individual recipient data.
    Returns (is_valid, list_of_error_reasons).
    """
    errors = []
    
    if not name or not isinstance(name, str) or not name.strip():
        errors.append("Recipient name is required and cannot be empty")
    elif len(name.strip()) > 200:
        errors.append("Recipient name cannot exceed 200 characters")

    if not email or not isinstance(email, str) or not email.strip():
        errors.append("Recipient email is required and cannot be empty")
    else:
        email_clean = email.strip()
        if len(email_clean) > 254 or not EMAIL_REGEX.match(email_clean):
            errors.append(f"Invalid email address format: '{email_clean}'")

    return (len(errors) == 0, errors)


def generate_secure_certificate_id() -> str:
    """
    Generates a 48-bit entropy pseudorandom token via the standard secrets module.
    Formatted as CERT-XXXX-XXXX-XXXX (2.8e14 states), designed to make online
    guessing intractable when paired with rate limiting on the verification endpoint.
    """
    token = secrets.token_hex(6).upper()
    return f"CERT-{token[:4]}-{token[4:8]}-{token[8:12]}"


def is_safe_webhook_url(url: str) -> Tuple[bool, str]:
    """
    SSRF Protection: Validates that a user-supplied webhook URL cannot target
    internal loopback, private RFC-1918 networks, link-local, or cloud metadata endpoints.
    """
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False, "Invalid URL scheme: only http and https are permitted."
        if not parsed.hostname:
            return False, "Missing hostname in webhook URL."

        # Resolve hostname to check actual destination IP addresses
        addr_info = socket.getaddrinfo(parsed.hostname, None)
        for entry in addr_info:
            ip_str = entry[4][0]
            ip = ipaddress.ip_address(ip_str)
            if (
                ip.is_private or
                ip.is_loopback or
                ip.is_link_local or
                ip.is_reserved or
                ip.is_multicast or
                ip_str == "169.254.169.254" or
                ip_str == "::1"
            ):
                return False, f"Prohibited webhook destination: cannot target private or internal IP ({ip_str})."
        return True, ""
    except Exception as e:
        return False, f"Failed to validate webhook destination: {e}"


def trigger_webhook_notification(webhook_url: str, job_dict: dict) -> None:
    """
    Sends an asynchronous POST notification to the client's webhook endpoint.
    Guarded against SSRF, with strict timeouts and disabled redirects.
    """
    if not webhook_url:
        return

    is_safe, reason = is_safe_webhook_url(webhook_url)
    if not is_safe:
        logger.warning(f"Aborting webhook delivery: {reason}")
        return

    try:
        with httpx.Client(timeout=5.0, follow_redirects=False) as client:
            resp = client.post(
                webhook_url,
                json={
                    "event": "job.completed",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "job": job_dict,
                },
                headers={"Content-Type": "application/json", "User-Agent": "Bulk-Certificate-Generator/1.1"}
            )
            logger.info(f"Webhook delivered to {webhook_url}: HTTP {resp.status_code}")
    except Exception as e:
        logger.warning(f"Failed to deliver completion webhook to {webhook_url}: {e}")


def process_generation_job(job_id: str) -> None:
    """
    Background worker task that processes recipients in bulk.
    Features:
    - Serializable single argument (job_id: str) for Celery compatibility
    - Worker-owned database session with lifecycle cleanup
    - Idempotent recipient processing: skips already successful recipients
    - Batched SQLite commits (every BATCH_COMMIT_SIZE) to minimize writer locks
    - Fault isolation: individual failures do not block remaining recipients
    - Crash recovery note: In-flight PDFs regenerated upon retry safely overwrite disk files
    """
    logger.info(f"Worker started for Job ID: {job_id}")
    db = SessionLocal()
    
    try:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job:
            logger.error(f"Job with ID {job_id} not found in database.")
            return

        job.status = JobStatus.PROCESSING.value
        if not job.started_at:
            job.started_at = get_utc_now()
        db.commit()

        recipients = db.query(Recipient).filter(Recipient.job_id == job_id).all()
        successful_certs: List[Tuple[str, str]] = []

        uncommitted_count = 0
        batch_commit_size = settings.BATCH_COMMIT_SIZE

        for recipient in recipients:
            # Idempotency check: if recipient already has SUCCESS, don't re-generate
            if recipient.status == RecipientStatus.SUCCESS.value:
                if recipient.file_path:
                    successful_certs.append((recipient.name, recipient.file_path))
                continue

            try:
                # 1. Validate recipient details
                is_valid, validation_errors = validate_recipient_data(recipient.name, recipient.email)
                
                # Check for explicit failure simulation in test extra_data
                if recipient.extra_data and recipient.extra_data.get("_simulate_failure"):
                    is_valid = False
                    validation_errors.append(recipient.extra_data.get("_simulate_failure_message", "Simulated failure for testing"))

                if not is_valid:
                    recipient.status = RecipientStatus.FAILED.value
                    recipient.error_message = "; ".join(validation_errors)
                    recipient.processed_at = get_utc_now()
                    job.processed_recipients += 1
                    job.failed_recipients += 1
                    uncommitted_count += 1
                    logger.warning(f"Validation failed for recipient {recipient.id}: {recipient.error_message}")
                else:
                    # 2. Generate cryptographically secure Certificate ID
                    cert_id = generate_secure_certificate_id()
                    
                    pdf_path = storage_service.get_certificate_path(
                        job_id=job.id,
                        recipient_name=recipient.name,
                        cert_id=cert_id
                    )

                    # 3. Render certificate PDF using template with QR verification
                    # Note: ReportLab canvas safely overwrites any existing partial file on retry
                    certificate_generator.generate(
                        output_path=pdf_path,
                        recipient_name=recipient.name.strip(),
                        event_name=job.event_name,
                        issuer_name=job.issuer_name,
                        issue_date=job.issue_date,
                        certificate_id=cert_id,
                        description=job.description,
                        extra_data=recipient.extra_data,
                        template_type=job.template_type or "classic",
                    )

                    # 4. Record successful generation
                    recipient.status = RecipientStatus.SUCCESS.value
                    recipient.certificate_id = cert_id
                    recipient.file_path = str(pdf_path)
                    recipient.processed_at = get_utc_now()
                    recipient.error_message = None
                    
                    job.processed_recipients += 1
                    job.successful_recipients += 1
                    successful_certs.append((recipient.name, pdf_path))
                    uncommitted_count += 1
                    logger.info(f"Successfully generated certificate {cert_id} for {recipient.name}")

            except Exception as item_error:
                logger.exception(f"Error generating certificate for recipient {recipient.id}: {item_error}")
                db.rollback()
                
                recipient.status = RecipientStatus.FAILED.value
                recipient.error_message = f"Generation error: {str(item_error)}"
                recipient.processed_at = get_utc_now()
                job.processed_recipients += 1
                job.failed_recipients += 1
                uncommitted_count += 1

            if uncommitted_count >= batch_commit_size:
                db.commit()
                uncommitted_count = 0

        if uncommitted_count > 0:
            db.commit()

        # 5. Finalize Job Status
        if job.failed_recipients == 0:
            job.status = JobStatus.COMPLETED.value
        elif job.successful_recipients > 0:
            job.status = JobStatus.PARTIALLY_FAILED.value
        else:
            job.status = JobStatus.FAILED.value

        job.completed_at = get_utc_now()
        db.commit()

        # 6. Pre-generate ZIP package if there are successful certificates
        if successful_certs:
            try:
                storage_service.create_job_zip(job_id=job.id, cert_files=successful_certs)
            except Exception as zip_err:
                logger.warning(f"Could not pre-generate zip archive for job {job_id}: {zip_err}")

        # 7. Trigger SSRF-guarded Webhook Callback
        if job.webhook_url:
            trigger_webhook_notification(job.webhook_url, job.to_dict())

        logger.info(
            f"Finished Job {job_id}: status={job.status}, "
            f"total={job.total_recipients}, success={job.successful_recipients}, "
            f"failed={job.failed_recipients}"
        )

    except Exception as fatal_job_error:
        logger.exception(f"Fatal error processing job {job_id}: {fatal_job_error}")
        db.rollback()
        try:
            job = db.query(Job).filter(Job.id == job_id).first()
            if job:
                job.status = JobStatus.FAILED.value
                job.error_message = f"Fatal worker error: {str(fatal_job_error)}"
                job.completed_at = get_utc_now()
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
