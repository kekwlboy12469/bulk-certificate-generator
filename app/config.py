import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    PROJECT_NAME: str = "Bulk Certificate Generator"
    VERSION: str = "1.1.0"
    API_V1_STR: str = "/api/v1"
    
    # Base directory of the project
    BASE_DIR: Path = Path(__file__).resolve().parent.parent
    
    # Database URL
    DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{Path(__file__).resolve().parent.parent}/certificates.db")
    
    # File Storage
    STORAGE_DIR: Path = Path(os.getenv("STORAGE_DIR", str(Path(__file__).resolve().parent.parent / "generated_certificates")))
    
    # Bulk Processing Configuration
    MAX_RECIPIENTS_PER_JOB: int = 5000
    BATCH_COMMIT_SIZE: int = 25
    WORKER_CONCURRENCY: int = 4
    
    # Predefined Certificate Defaults
    DEFAULT_ISSUER_NAME: str = "Global Certification Authority"
    DEFAULT_ISSUER_TITLE: str = "Director of Certification"
    
    # Base URL for QR Code Verification Links
    APP_BASE_URL: str = os.getenv("APP_BASE_URL", "http://127.0.0.1:8000")
    
    # Auth & Security
    API_KEY: Optional[str] = os.getenv("API_KEY", None)  # If set, requires X-API-Key header
    RATE_LIMIT_VERIFY_PER_MINUTE: int = 60               # Max /verify queries per IP/minute


settings = Settings()

# Ensure storage directory exists
settings.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
