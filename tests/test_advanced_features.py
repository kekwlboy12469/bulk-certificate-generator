from fastapi.testclient import TestClient
from app.models.job import Job, JobStatus
from app.models.recipient import Recipient, RecipientStatus
from app.main import sweep_stale_processing_jobs
from app.security import verify_rate_limiter


def test_idempotency_key_prevents_duplicate_jobs(client: TestClient):
    payload = {
        "event_name": "Idempotent Event 2026",
        "recipients": [{"name": "User A", "email": "usera@example.com"}]
    }
    headers = {"Idempotency-Key": "test-key-uuid-12345"}

    # First request
    resp1 = client.post("/api/v1/jobs", json=payload, headers=headers)
    assert resp1.status_code == 202
    job_id_1 = resp1.json()["id"]

    # Duplicate request with same Idempotency-Key and same payload
    resp2 = client.post("/api/v1/jobs", json=payload, headers=headers)
    assert resp2.status_code in (200, 202)
    job_id_2 = resp2.json()["id"]

    assert job_id_1 == job_id_2


def test_idempotency_key_rejects_different_payload(client: TestClient):
    """Reusing the same Idempotency-Key with a different payload must return 409 Conflict."""
    payload_a = {
        "event_name": "Original Event A",
        "recipients": [{"name": "User A", "email": "usera@example.com"}]
    }
    payload_b = {
        "event_name": "Different Event B",
        "recipients": [{"name": "User B", "email": "userb@example.com"}]
    }
    headers = {"Idempotency-Key": "test-conflict-key-999"}

    # First request succeeds
    resp1 = client.post("/api/v1/jobs", json=payload_a, headers=headers)
    assert resp1.status_code == 202

    # Second request with SAME key but DIFFERENT payload fails with 409 Conflict
    resp2 = client.post("/api/v1/jobs", json=payload_b, headers=headers)
    assert resp2.status_code == 409
    assert "different request payload" in resp2.json()["detail"].lower()


def test_ssrf_protection_on_webhook(client: TestClient):
    """Ensure submitting internal IP or cloud metadata webhook is rejected with 422."""
    prohibited_urls = [
        "http://127.0.0.1:8000/internal",
        "http://localhost:5000/hook",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/admin"
    ]

    for bad_url in prohibited_urls:
        payload = {
            "event_name": "SSRF Test Event",
            "webhook_url": bad_url,
            "recipients": [{"name": "User", "email": "user@example.com"}]
        }
        resp = client.post("/api/v1/jobs", json=payload)
        assert resp.status_code == 422
        assert "security rejection for webhook_url" in resp.text.lower()


def test_retry_failed_recipients_endpoint(client: TestClient, db_session):
    # 1. Create a job with 1 success and 1 simulated failure
    payload = {
        "event_name": "Retry Mechanics Workshop",
        "recipients": [
            {"name": "Alice Winner", "email": "alice@winner.com"},
            {
                "name": "Bob Retryable",
                "email": "bob@retry.com",
                "extra_data": {"_simulate_failure": True, "_simulate_failure_message": "Temporary fault"}
            }
        ]
    }
    resp = client.post("/api/v1/jobs", json=payload)
    assert resp.status_code == 202
    job_id = resp.json()["id"]

    # Check status
    st_resp = client.get(f"/api/v1/jobs/{job_id}")
    assert st_resp.status_code == 200
    assert st_resp.json()["status"] == "PARTIALLY_FAILED"
    assert st_resp.json()["failed_recipients"] == 1
    assert st_resp.json()["successful_recipients"] == 1

    # Fix the recipient extra_data in DB so the retry succeeds
    failed_rec = db_session.query(Recipient).filter(
        Recipient.job_id == job_id, 
        Recipient.status == RecipientStatus.FAILED.value
    ).first()
    assert failed_rec is not None
    failed_rec.extra_data = {}
    db_session.commit()

    # 2. Call Retry Endpoint
    retry_resp = client.post(f"/api/v1/jobs/{job_id}/retry")
    assert retry_resp.status_code == 202
    retry_data = retry_resp.json()
    assert retry_data["retried_recipients_count"] == 1

    # 3. Check status after retry
    after_resp = client.get(f"/api/v1/jobs/{job_id}")
    assert after_resp.status_code == 200
    after_data = after_resp.json()
    assert after_data["status"] == "COMPLETED"
    assert after_data["successful_recipients"] == 2
    assert after_data["failed_recipients"] == 0


def test_rate_limiting_on_verify_endpoint(client: TestClient):
    verify_rate_limiter.reset()
    original_limit = verify_rate_limiter.requests_per_minute
    verify_rate_limiter.requests_per_minute = 5

    try:
        for _ in range(5):
            r = client.get("/api/v1/certificates/verify/CERT-TEST-RATE-LIMIT")
            assert r.status_code == 200

        exceeded_resp = client.get("/api/v1/certificates/verify/CERT-TEST-RATE-LIMIT")
        assert exceeded_resp.status_code == 429
        assert "rate limit exceeded" in exceeded_resp.json()["detail"].lower()
    finally:
        verify_rate_limiter.requests_per_minute = original_limit
        verify_rate_limiter.reset()


def test_startup_stale_jobs_sweep(db_session, test_engine):
    """Verify that jobs left stuck in PROCESSING are recovered on startup."""
    import app.main as main_module
    from sqlalchemy.orm import sessionmaker
    
    orig_session_local = main_module.SessionLocal
    main_module.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    try:
        stale_job = Job(
            event_name="Interrupted Job",
            issuer_name="System",
            issue_date="2026-10-08",
            status=JobStatus.PROCESSING.value,
            total_recipients=2,
            processed_recipients=1,
            successful_recipients=1,
            failed_recipients=0
        )
        db_session.add(stale_job)
        db_session.flush()

        rec_success = Recipient(
            job_id=stale_job.id,
            name="Done User",
            email="done@test.com",
            status=RecipientStatus.SUCCESS.value
        )
        rec_pending = Recipient(
            job_id=stale_job.id,
            name="Pending User",
            email="pending@test.com",
            status=RecipientStatus.PENDING.value
        )
        db_session.add_all([rec_success, rec_pending])
        db_session.commit()
        job_id = stale_job.id

        sweep_stale_processing_jobs()

        db_session.expire_all()
        recovered = db_session.query(Job).filter(Job.id == job_id).first()
        assert recovered.status == JobStatus.PARTIALLY_FAILED.value
        assert "process interrupted" in recovered.error_message.lower()
    finally:
        main_module.SessionLocal = orig_session_local
