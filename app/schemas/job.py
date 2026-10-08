from typing import List, Optional
from datetime import date
from pydantic import BaseModel, Field, field_validator, ConfigDict
from app.config import settings
from app.schemas.recipient import RecipientInput, RecipientResponse


class JobCreateRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "event_name": "Full Stack Software Engineering Bootcamp",
                "issuer_name": "Global Tech Institute",
                "issue_date": str(date.today()),
                "description": "For demonstrating exceptional mastery of modern distributed systems and API design.",
                "template_type": "classic",
                "webhook_url": "https://example.com/api/webhooks/certificate-complete",
                "deduplicate_emails": True,
                "recipients": [
                    {"name": "Alice Smith", "email": "alice@example.com", "extra_data": {"grade": "Distinction"}},
                    {"name": "Bob Jones", "email": "bob@example.com", "extra_data": {"grade": "Merit"}}
                ]
            }
        }
    )

    event_name: str = Field(..., min_length=1, max_length=255, description="Name of the course, event, or certification")
    issuer_name: Optional[str] = Field(default=None, max_length=255, description="Issuing organization or authority")
    issue_date: Optional[str] = Field(default=None, description="Issue date (e.g. YYYY-MM-DD), defaults to today")
    description: Optional[str] = Field(default=None, max_length=1000, description="Description or reason for certificate")
    template_type: Optional[str] = Field(default="classic", description="Certificate template design identifier (classic, modern)")
    webhook_url: Optional[str] = Field(default=None, description="Optional HTTP(S) URL to invoke when job generation completes")
    deduplicate_emails: bool = Field(default=True, description="Whether to deduplicate recipients with identical emails in the same batch")
    recipients: List[RecipientInput] = Field(..., min_length=1, description="List of recipient entries to generate certificates for")

    @field_validator("event_name")
    @classmethod
    def validate_event_name(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("event_name cannot be blank or whitespace only")
        return stripped

    @field_validator("recipients")
    @classmethod
    def validate_recipients_list(cls, v: List[RecipientInput]) -> List[RecipientInput]:
        if not v:
            raise ValueError("recipients list must contain at least one recipient")
        if len(v) > settings.MAX_RECIPIENTS_PER_JOB:
            raise ValueError(
                f"recipients list exceeds maximum allowable limit of {settings.MAX_RECIPIENTS_PER_JOB} entries per job"
            )
        return v


class JobSummaryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    idempotency_key: Optional[str] = None
    webhook_url: Optional[str] = None
    event_name: str
    issuer_name: str
    issue_date: str
    description: Optional[str] = None
    template_type: str
    status: str
    total_recipients: int
    processed_recipients: int
    successful_recipients: int
    failed_recipients: int
    progress_percentage: float
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class JobDetailResponse(JobSummaryResponse):
    model_config = ConfigDict(from_attributes=True)

    recipients: List[RecipientResponse] = []
    download_all_url: Optional[str] = None


class JobListResponse(BaseModel):
    total: int
    items: List[JobSummaryResponse]


class JobRetryResponse(BaseModel):
    id: str
    status: str
    retried_recipients_count: int
    message: str
