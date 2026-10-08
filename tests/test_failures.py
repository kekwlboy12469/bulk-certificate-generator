from fastapi.testclient import TestClient


def test_individual_certificate_failure_does_not_block_others(client: TestClient):
    """
    Key requirement: A failure while generating one certificate should not
    prevent other valid certificates in the same job from being generated.
    """
    payload = {
        "event_name": "Failure Resilience Workshop",
        "recipients": [
            {
                "name": "Successful Recipient One",
                "email": "success1@example.com",
            },
            {
                "name": "Failed Recipient (Simulated)",
                "email": "fail@example.com",
                "extra_data": {
                    "_simulate_failure": True,
                    "_simulate_failure_message": "Certificate template engine rendered simulated error"
                }
            },
            {
                "name": "Successful Recipient Two",
                "email": "success2@example.com",
            },
            {
                "name": "Invalid Recipient (No Email)",
                "email": "",
            }
        ]
    }

    response = client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 202
    job_id = response.json()["id"]

    # Verify status
    status_resp = client.get(f"/api/v1/jobs/{job_id}")
    assert status_resp.status_code == 200
    data = status_resp.json()

    assert data["status"] == "PARTIALLY_FAILED"
    assert data["total_recipients"] == 4
    assert data["successful_recipients"] == 2
    assert data["failed_recipients"] == 2

    # Verify each recipient
    rec_by_name = {r["name"]: r for r in data["recipients"]}
    
    assert rec_by_name["Successful Recipient One"]["status"] == "SUCCESS"
    assert rec_by_name["Successful Recipient One"]["certificate_id"] is not None
    assert rec_by_name["Successful Recipient Two"]["status"] == "SUCCESS"
    assert rec_by_name["Successful Recipient Two"]["certificate_id"] is not None

    assert rec_by_name["Failed Recipient (Simulated)"]["status"] == "FAILED"
    assert "simulated error" in rec_by_name["Failed Recipient (Simulated)"]["error_message"].lower()

    assert rec_by_name["Invalid Recipient (No Email)"]["status"] == "FAILED"
    assert "email is required" in rec_by_name["Invalid Recipient (No Email)"]["error_message"].lower()


def test_all_recipients_failed_job_status(client: TestClient):
    """When every recipient fails, job status should be FAILED."""
    payload = {
        "event_name": "All Fail Test",
        "recipients": [
            {"name": "", "email": "bad"},
            {"name": "Bad Email", "email": "not-an-email"}
        ]
    }

    response = client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 202
    job_id = response.json()["id"]

    status_resp = client.get(f"/api/v1/jobs/{job_id}")
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["status"] == "FAILED"
    assert data["successful_recipients"] == 0
    assert data["failed_recipients"] == 2
