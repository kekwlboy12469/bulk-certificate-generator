import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from app.services.generator import certificate_generator


def test_mandatory_create_generation_job(client: TestClient):
    """
    Mandatory Test 1: Creating a generation job.
    Accepts certificate generation request for a list of recipients and returns 202 Accepted.
    """
    payload = {
        "event_name": "Full Stack Engineering 2026",
        "issuer_name": "Technology Board",
        "recipients": [
            {"name": "Alice Smith", "email": "alice@example.com"},
            {"name": "Bob Jones", "email": "bob@example.com"}
        ]
    }
    response = client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 202
    data = response.json()
    assert "id" in data
    assert data["total_recipients"] == 2
    assert data["status"] in ("PENDING", "COMPLETED")


def test_mandatory_input_validation(client: TestClient):
    """
    Mandatory Test 2: Input validation.
    Rejects malformed top-level requests with 422 and captures invalid recipient data per-recipient.
    """
    # 1. Missing event_name -> 422
    resp_missing_event = client.post("/api/v1/jobs", json={
        "recipients": [{"name": "A", "email": "a@test.com"}]
    })
    assert resp_missing_event.status_code == 422

    # 2. Empty recipients list -> 422
    resp_empty = client.post("/api/v1/jobs", json={
        "event_name": "Event",
        "recipients": []
    })
    assert resp_empty.status_code == 422

    # 3. Invalid recipient data (bad email / empty name) inside a job
    resp_job = client.post("/api/v1/jobs", json={
        "event_name": "Validation Event",
        "recipients": [
            {"name": "Valid User", "email": "valid@example.com"},
            {"name": "Invalid Email", "email": "not-an-email"},
            {"name": "", "email": "missing.name@example.com"}
        ]
    })
    assert resp_job.status_code == 202
    job_id = resp_job.json()["id"]

    status_resp = client.get(f"/api/v1/jobs/{job_id}")
    data = status_resp.json()
    assert data["status"] == "PARTIALLY_FAILED"
    assert data["successful_recipients"] == 1
    assert data["failed_recipients"] == 2


def test_mandatory_certificate_generation():
    """
    Mandatory Test 3: Certificate generation.
    Generates a valid certificate from a predefined template.
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        output_pdf = Path(tmp_dir) / "test_cert.pdf"
        certificate_generator.generate(
            output_path=output_pdf,
            recipient_name="Grace Hopper",
            event_name="Systems Engineering",
            issuer_name="Computing Heritage",
            issue_date="2026-10-08",
            certificate_id="CERT-TEST-4455-6677",
            description="Excellence in computing",
            template_type="classic"
        )
        assert output_pdf.exists()
        assert output_pdf.stat().st_size > 1000
        with open(output_pdf, "rb") as f:
            assert f.read(5) == b"%PDF-"


def test_mandatory_job_status_and_progress(client: TestClient):
    """
    Mandatory Test 4: Job status / progress.
    Tracks progress percentage, processed count, successful count, and failed count.
    """
    payload = {
        "event_name": "Progress Tracking Summit",
        "recipients": [
            {"name": f"Attendee {i}", "email": f"attendee{i}@test.com"}
            for i in range(5)
        ]
    }
    create_resp = client.post("/api/v1/jobs", json=payload)
    assert create_resp.status_code == 202
    job_id = create_resp.json()["id"]

    status_resp = client.get(f"/api/v1/jobs/{job_id}")
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["total_recipients"] == 5
    assert data["processed_recipients"] == 5
    assert data["successful_recipients"] == 5
    assert data["failed_recipients"] == 0
    assert data["progress_percentage"] == 100.0
    assert data["status"] == "COMPLETED"


def test_mandatory_handling_individual_certificate_failure(client: TestClient):
    """
    Mandatory Test 5: Handling an individual certificate failure.
    A failure on one certificate does NOT block other valid certificates from being generated.
    """
    payload = {
        "event_name": "Fault Tolerance Workshop",
        "recipients": [
            {"name": "Valid Recipient 1", "email": "valid1@test.com"},
            {"name": "", "email": "fail_empty_name@test.com"},
            {"name": "Valid Recipient 2", "email": "valid2@test.com"},
            {"name": "Bad Email Recipient", "email": "invalid-email-no-at"}
        ]
    }
    resp = client.post("/api/v1/jobs", json=payload)
    assert resp.status_code == 202
    job_id = resp.json()["id"]

    status_resp = client.get(f"/api/v1/jobs/{job_id}")
    data = status_resp.json()
    assert data["status"] == "PARTIALLY_FAILED"
    assert data["successful_recipients"] == 2
    assert data["failed_recipients"] == 2

    # Valid recipients must be SUCCESS and have certificate IDs
    success_recs = [r for r in data["recipients"] if r["status"] == "SUCCESS"]
    assert len(success_recs) == 2
    for r in success_recs:
        assert r["certificate_id"] is not None

    # Failed recipients must record reasons
    failed_recs = [r for r in data["recipients"] if r["status"] == "FAILED"]
    assert len(failed_recs) == 2
    for r in failed_recs:
        assert r["error_message"] is not None


def test_mandatory_retrieving_generated_certificates(client: TestClient):
    """
    Mandatory Test 6: Retrieving generated certificates.
    Allows retrieving single certificates as PDF and bulk retrieval as ZIP.
    """
    payload = {
        "event_name": "Retrieval Test Event",
        "recipients": [
            {"name": "Marie Curie", "email": "marie@science.org"}
        ]
    }
    resp = client.post("/api/v1/jobs", json=payload)
    assert resp.status_code == 202
    job_id = resp.json()["id"]

    status_resp = client.get(f"/api/v1/jobs/{job_id}")
    cert_id = status_resp.json()["recipients"][0]["certificate_id"]

    # 1. Single Certificate Download (PDF)
    single_dl = client.get(f"/api/v1/certificates/{cert_id}/download")
    assert single_dl.status_code == 200
    assert single_dl.headers["content-type"] == "application/pdf"
    assert single_dl.content.startswith(b"%PDF-")

    # 2. Bulk Certificate Download (ZIP)
    bulk_dl = client.get(f"/api/v1/jobs/{job_id}/download-all")
    assert bulk_dl.status_code == 200
    assert bulk_dl.headers["content-type"] == "application/zip"
    assert len(bulk_dl.content) > 1000
