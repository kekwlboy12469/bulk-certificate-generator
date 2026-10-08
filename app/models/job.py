import enum
from datetime import datetime, timezone
import uuid
from sqlalchemy import Column, String, Integer, DateTime, Text
from sqlalchemy.orm import relationship
from app.database import Base


class JobStatus(str, enum.Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    PARTIALLY_FAILED = "PARTIALLY_FAILED"
    FAILED = "FAILED"


def get_utc_now():
    return datetime.now(timezone.utc)


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    idempotency_key = Column(String(128), nullable=True, unique=True, index=True)
    payload_hash = Column(String(64), nullable=True)
    webhook_url = Column(String(500), nullable=True)
    
    event_name = Column(String(255), nullable=False)
    issuer_name = Column(String(255), nullable=False)
    issue_date = Column(String(50), nullable=False)
    description = Column(Text, nullable=True)
    template_type = Column(String(50), default="classic", nullable=False)
    
    status = Column(String(30), default=JobStatus.PENDING.value, nullable=False, index=True)
    total_recipients = Column(Integer, default=0, nullable=False)
    processed_recipients = Column(Integer, default=0, nullable=False)
    successful_recipients = Column(Integer, default=0, nullable=False)
    failed_recipients = Column(Integer, default=0, nullable=False)
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    recipients = relationship("Recipient", back_populates="job", cascade="all, delete-orphan", order_by="Recipient.created_at")

    def to_dict(self):
        progress = 0.0
        if self.total_recipients > 0:
            progress = round((self.processed_recipients / self.total_recipients) * 100, 2)
        return {
            "id": self.id,
            "idempotency_key": self.idempotency_key,
            "webhook_url": self.webhook_url,
            "event_name": self.event_name,
            "issuer_name": self.issuer_name,
            "issue_date": self.issue_date,
            "description": self.description,
            "template_type": self.template_type,
            "status": self.status,
            "total_recipients": self.total_recipients,
            "processed_recipients": self.processed_recipients,
            "successful_recipients": self.successful_recipients,
            "failed_recipients": self.failed_recipients,
            "progress_percentage": progress,
            "error_message": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
