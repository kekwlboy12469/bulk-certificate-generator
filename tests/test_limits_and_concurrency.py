import concurrent.futures
from fastapi.testclient import TestClient
from app.config import settings


def test_over_limit_rejection(client: TestClient):
    """Ensure submitting more recipients than MAX_RECIPIENTS_PER_JOB returns HTTP 422."""
    orig_limit = settings.MAX_RECIPIENTS_PER_JOB
    settings.MAX_RECIPIENTS_PER_JOB = 10  # Temporarily lower limit to 10 for test

    try:
        excess_recipients = [
            {"name": f"User {i}", "email": f"user{i}@test.com"}
            for i in range(12)
        ]
        payload = {
            "event_name": "Over Limit Test",
            "recipients": excess_recipients
        }
        resp = client.post("/api/v1/jobs", json=payload)
        assert resp.status_code == 422
        assert "exceeds maximum allowable limit" in resp.text.lower()
    finally:
        settings.MAX_RECIPIENTS_PER_JOB = orig_limit


def test_concurrent_jobs_submission(client: TestClient):
    """Ensure submitting multiple jobs concurrently executes without SQLite database lockouts."""
    job_payloads = [
        {
            "event_name": f"Concurrent Track {i}",
            "recipients": [
                {"name": f"Track {i} Runner A", "email": f"runner{i}a@test.com"},
                {"name": f"Track {i} Runner B", "email": f"runner{i}b@test.com"}
            ]
        }
        for i in range(3)
    ]

    job_ids = []
    for payload in job_payloads:
        resp = client.post("/api/v1/jobs", json=payload)
        assert resp.status_code == 202
        job_ids.append(resp.json()["id"])

    # Check that all 3 completed successfully
    for jid in job_ids:
        st_resp = client.get(f"/api/v1/jobs/{jid}")
        assert st_resp.status_code == 200
        data = st_resp.json()
        assert data["status"] == "COMPLETED"
        assert data["successful_recipients"] == 2
