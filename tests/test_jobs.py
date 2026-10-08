from fastapi.testclient import TestClient


def test_create_generation_job_success(client: TestClient):
    payload = {
        "event_name": "Cloud Native Architecture 2026",
        "issuer_name": "Cloud Native Foundation",
        "issue_date": "2026-10-08",
        "description": "Excellence in Microservices and Kubernetes",
        "recipients": [
            {"name": "Alice Cooper", "email": "alice@cloud.example"},
            {"name": "Bob Dylan", "email": "bob@cloud.example", "extra_data": {"grade": "Distinction"}}
        ]
    }

    response = client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 202
    data = response.json()
    assert "id" in data
    assert data["event_name"] == "Cloud Native Architecture 2026"
    assert data["total_recipients"] == 2
    
    # In TestClient, background task completes immediately
    job_id = data["id"]
    status_resp = client.get(f"/api/v1/jobs/{job_id}")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["status"] == "COMPLETED"
    assert status_data["successful_recipients"] == 2
    assert status_data["failed_recipients"] == 0
    assert status_data["progress_percentage"] == 100.0
    assert len(status_data["recipients"]) == 2
    assert status_data["recipients"][0]["status"] == "SUCCESS"
    assert status_data["recipients"][0]["certificate_id"] is not None


def test_list_jobs(client: TestClient):
    # Create two jobs
    for i in range(2):
        client.post("/api/v1/jobs", json={
            "event_name": f"Batch Test {i}",
            "recipients": [{"name": f"User {i}", "email": f"user{i}@test.com"}]
        })

    response = client.get("/api/v1/jobs?limit=10&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert data["total"] >= 2
    assert len(data["items"]) >= 2


def test_get_nonexistent_job(client: TestClient):
    response = client.get("/api/v1/jobs/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
