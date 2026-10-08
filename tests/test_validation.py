from fastapi.testclient import TestClient


def test_missing_event_name(client: TestClient):
    payload = {
        "recipients": [{"name": "Alice", "email": "alice@test.com"}]
    }
    response = client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 422


def test_blank_event_name(client: TestClient):
    payload = {
        "event_name": "    ",
        "recipients": [{"name": "Alice", "email": "alice@test.com"}]
    }
    response = client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 422


def test_empty_recipients_list(client: TestClient):
    payload = {
        "event_name": "Python Conference",
        "recipients": []
    }
    response = client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 422


def test_recipient_data_validation(client: TestClient):
    """
    Tests that invalid recipient data inside a job is captured per-recipient
    without blowing up the API request upfront.
    """
    payload = {
        "event_name": "Data Engineering Summit",
        "recipients": [
            {"name": "Valid User", "email": "valid.user@example.com"},
            {"name": "", "email": "no.name@example.com"},
            {"name": "Invalid Email User", "email": "not-an-email"},
            {"name": "   ", "email": "bad-all-around"}
        ]
    }
    response = client.post("/api/v1/jobs", json=payload)
    assert response.status_code == 202
    job_id = response.json()["id"]

    status_resp = client.get(f"/api/v1/jobs/{job_id}")
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert data["status"] == "PARTIALLY_FAILED"
    assert data["total_recipients"] == 4
    assert data["successful_recipients"] == 1
    assert data["failed_recipients"] == 3

    recs = {r["name"]: r for r in data["recipients"]}
    
    # Valid User
    assert recs["Valid User"]["status"] == "SUCCESS"
    assert recs["Valid User"]["certificate_id"] is not None

    # Empty name user
    empty_name_rec = [r for r in data["recipients"] if r["email"] == "no.name@example.com"][0]
    assert empty_name_rec["status"] == "FAILED"
    assert "name is required" in empty_name_rec["error_message"].lower()

    # Invalid email user
    bad_email_rec = recs["Invalid Email User"]
    assert bad_email_rec["status"] == "FAILED"
    assert "invalid email" in bad_email_rec["error_message"].lower()
