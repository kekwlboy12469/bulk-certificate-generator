import os
import re
import zipfile
from pathlib import Path
from typing import List, Tuple, Optional
from app.config import settings


class StorageService:
    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or settings.STORAGE_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def get_job_dir(self, job_id: str) -> Path:
        """Returns and ensures the directory for a specific job exists."""
        job_dir = self.base_dir / "jobs" / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        return job_dir

    def get_job_certs_dir(self, job_id: str) -> Path:
        """Returns and ensures the certificates folder for a specific job exists."""
        certs_dir = self.get_job_dir(job_id) / "certificates"
        certs_dir.mkdir(parents=True, exist_ok=True)
        return certs_dir

    def sanitize_filename(self, name: str, fallback_token: str = "") -> str:
        """
        Sanitizes names for safe cross-platform filesystem filenames.
        Preserves clean ASCII alphanumeric characters. If the resulting
        string is empty (e.g. non-Latin scripts such as Devanagari, CJK, or symbols),
        falls back cleanly to the certificate ID token to prevent empty names,
        filesystem encoding crashes, or ZIP extraction errors on legacy OSes.
        """
        clean = re.sub(r'[^a-zA-Z0-9_\-\s]', '', name)
        clean = re.sub(r'\s+', '_', clean).strip('._-')
        if not clean:
            return f"cert_{fallback_token}" if fallback_token else "certificate"
        return clean

    def get_certificate_path(self, job_id: str, recipient_name: str, cert_id: str) -> Path:
        """
        Constructs safe absolute file path for a generated certificate.
        Includes cert_id to guarantee unique disk filenames even if recipients share identical names.
        """
        token = cert_id.replace("CERT-", "").replace("-", "")[:8]
        clean_name = self.sanitize_filename(recipient_name, fallback_token=token)
        if clean_name.startswith("cert_"):
            filename = f"{clean_name}.pdf"
        else:
            filename = f"{clean_name}_{token}.pdf"
        return self.get_job_certs_dir(job_id) / filename

    def create_job_zip(self, job_id: str, cert_files: List[Tuple[str, Path]]) -> Path:
        """
        Creates a ZIP archive of all successfully generated certificates for a job.
        cert_files: List of (recipient_name, file_path) tuples.
        Guarantees that duplicate recipient names (e.g. two 'Rahul Sharma' or two Hindi names)
        receive distinct names inside the ZIP without collision or overwrite.
        """
        job_dir = self.get_job_dir(job_id)
        zip_path = job_dir / f"certificates_job_{job_id[:8]}.zip"
        
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zip_file:
            used_arcnames = set()
            for display_name, file_path in cert_files:
                if file_path.exists():
                    arcname = file_path.name
                    # If an identical name already exists in the ZIP archive, disambiguate with a counter
                    counter = 2
                    base, ext = os.path.splitext(arcname)
                    while arcname in used_arcnames:
                        arcname = f"{base}_{counter}{ext}"
                        counter += 1
                    used_arcnames.add(arcname)
                    zip_file.write(file_path, arcname=arcname)
                    
        return zip_path


storage_service = StorageService()
