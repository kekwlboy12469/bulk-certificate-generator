import time
from fastapi.testclient import TestClient


def test_bulk_generation_larger_batch(client: TestClient):
    """
    Test bulk processing with 50 recipients to verify efficiency,
    correct counters, and zip packaging.
    """
    recipients = [
        {"name": f"Engineer #{i:02d}", "email": f"engineer{i}@techcorp.org", "extra_data": {"rank": i}}
        for i in range(1, 51)
    ]
    payload = {
        "event_name": "Large Scale Cloud Architecture 2026",
        "issuer_name": "Global Engineering Board",
        "recipients": recipients
    }

    start = time.perf_counter()
    response = client.post("/api/v1/jobs", json=payload)
    elapsed = time.perf_counter() - start

    assert response.status_code == 202
    job_id = response.json()["id"]

    # Verify status
    status_resp = client.get(f"/api/v1/jobs/{job_id}")
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["status"] == "COMPLETED"
    assert data["total_recipients"] == 50
    assert data["successful_recipients"] == 50
    assert data["failed_recipients"] == 0
    assert data["progress_percentage"] == 100.0

    # Test downloading zip for 50 certificates
    zip_resp = client.get(f"/api/v1/jobs/{job_id}/download-all")
    assert zip_resp.status_code == 200
    assert zip_resp.headers["content-type"] == "application/zip"
    assert len(zip_resp.content) > 10000


def test_unicode_and_special_characters(client: TestClient):
    """
    Ensure the generator handles unicode recipient names and special characters
    gracefully without crashes.
    """
    payload = {
        "event_name": "C++ & Python: Advanced / Concurrency <Special Edition>",
        "issuer_name": "L'Académie Européenne des Sciences",
        "recipients": [
            {"name": "José María Peña", "email": "jose@example.es"},
            {"name": "Frédéric François Chopin", "email": "frederic@example.fr"},
            {"name": "René Descartes", "email": "rene@example.fr"}
        ]
    }

    response = client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 202
    job_id = response.json()["id"]

    status_resp = client.get(f"/api/v1/jobs/{job_id}")
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["status"] == "COMPLETED"
    assert data["successful_recipients"] == 3
