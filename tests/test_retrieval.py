import io
import zipfile
from fastapi.testclient import TestClient


def test_certificate_and_bulk_retrieval(client: TestClient):
    # 1. Create a job with 2 recipients
    payload = {
        "event_name": "Distributed Systems Certification",
        "issuer_name": "Systems Institute",
        "recipients": [
            {"name": "Leslie Lamport", "email": "lamport@paxos.org"},
            {"name": "Barbara Liskov", "email": "liskov@mit.edu"}
        ]
    }
    create_resp = client.post("/api/v1/jobs", json=payload)
    assert create_resp.status_code == 202
    job_id = create_resp.json()["id"]

    # 2. Check job status to get certificate IDs
    job_resp = client.get(f"/api/v1/jobs/{job_id}")
    assert job_resp.status_code == 200
    job_data = job_resp.json()
    assert job_data["status"] == "COMPLETED"
    
    cert_1 = job_data["recipients"][0]
    cert_id = cert_1["certificate_id"]
    assert cert_id is not None

    # 3. Retrieve Certificate Metadata
    meta_resp = client.get(f"/api/v1/certificates/{cert_id}")
    assert meta_resp.status_code == 200
    meta_data = meta_resp.json()
    assert meta_data["certificate_id"] == cert_id
    assert meta_data["recipient_name"] == "Leslie Lamport"
    assert meta_data["event_name"] == "Distributed Systems Certification"

    # 4. Download Certificate PDF File
    download_resp = client.get(f"/api/v1/certificates/{cert_id}/download")
    assert download_resp.status_code == 200
    assert download_resp.headers["content-type"] == "application/pdf"
    assert download_resp.content.startswith(b"%PDF-")

    # 5. Verify Certificate Authenticity
    verify_resp = client.get(f"/api/v1/certificates/verify/{cert_id}")
    assert verify_resp.status_code == 200
    verify_data = verify_resp.json()
    assert verify_data["is_valid"] is True
    assert verify_data["recipient_name"] == "Leslie Lamport"

    # 6. Verify non-existent Certificate Authenticity
    bad_verify = client.get("/api/v1/certificates/verify/CERT-INVALID999")
    assert bad_verify.status_code == 200
    assert bad_verify.json()["is_valid"] is False

    # 7. Bulk Download all certificates as ZIP archive
    zip_resp = client.get(f"/api/v1/jobs/{job_id}/download-all")
    assert zip_resp.status_code == 200
    assert zip_resp.headers["content-type"] == "application/zip"
    
    # Inspect contents of the zip file
    zip_bytes = io.BytesIO(zip_resp.content)
    with zipfile.ZipFile(zip_bytes, "r") as zf:
        file_list = zf.namelist()
        assert len(file_list) == 2
        for f in file_list:
            assert f.endswith(".pdf")
            content = zf.read(f)
            assert content.startswith(b"%PDF-")


def test_download_nonexistent_certificate(client: TestClient):
    response = client.get("/api/v1/certificates/CERT-NONEXISTENT/download")
    assert response.status_code == 404


def test_bulk_download_nonexistent_job(client: TestClient):
    response = client.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000/download-all")
    assert response.status_code == 404
