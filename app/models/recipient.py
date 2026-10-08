import enum
from datetime import datetime, timezone
import uuid
from sqlalchemy import Column, String, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.database import Base


class RecipientStatus(str, enum.Enum):
    PENDING = "PENDING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


def get_utc_now():
    return datetime.now(timezone.utc)


class Recipient(Base):
    __tablename__ = "recipients"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    job_id = Column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False, index=True)
    
    name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False, index=True)
    extra_data = Column(JSON, nullable=True)
    
    status = Column(String(30), default=RecipientStatus.PENDING.value, nullable=False, index=True)
    error_message = Column(Text, nullable=True)
    
    # Certificate tracking fields
    certificate_id = Column(String(64), nullable=True, unique=True, index=True)
    file_path = Column(String(500), nullable=True)
    
    created_at = Column(DateTime(timezone=True), default=get_utc_now, nullable=False)
    processed_at = Column(DateTime(timezone=True), nullable=True)

    job = relationship("Job", back_populates="recipients")

    def to_dict(self):
        return {
            "id": self.id,
            "job_id": self.job_id,
            "name": self.name,
            "email": self.email,
            "extra_data": self.extra_data,
            "status": self.status,
            "error_message": self.error_message,
            "certificate_id": self.certificate_id,
            "download_url": f"/api/v1/certificates/{self.certificate_id}/download" if self.certificate_id else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
        }
