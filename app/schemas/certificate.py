from typing import Optional, Dict, Any
from pydantic import BaseModel, ConfigDict


class CertificateDetailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    certificate_id: str
    recipient_name: str
    recipient_email: str
    event_name: str
    issuer_name: str
    issue_date: str
    description: Optional[str] = None
    extra_data: Optional[Dict[str, Any]] = None
    created_at: Optional[str] = None
    download_url: str


class CertificateVerifyResponse(BaseModel):
    is_valid: bool
    certificate_id: str
    recipient_name: Optional[str] = None
    event_name: Optional[str] = None
    issuer_name: Optional[str] = None
    issue_date: Optional[str] = None
    verification_message: str
