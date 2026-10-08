from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class RecipientInput(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Jane Doe",
                "email": "jane.doe@example.com",
                "extra_data": {"grade": "A+", "hours": 40}
            }
        }
    )

    name: Optional[str] = Field(None, description="Full name of the recipient")
    email: Optional[str] = Field(None, description="Email address of the recipient")
    extra_data: Optional[Dict[str, Any]] = Field(default=None, description="Additional custom fields (e.g. grade, honors)")


class RecipientResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    job_id: str
    name: str
    email: str
    extra_data: Optional[Dict[str, Any]] = None
    status: str
    error_message: Optional[str] = None
    certificate_id: Optional[str] = None
    download_url: Optional[str] = None
    created_at: Optional[str] = None
    processed_at: Optional[str] = None
