import io
import zipfile
from fastapi.testclient import TestClient
from app.services.storage import storage_service


def test_identical_recipient_names_no_collision(client: TestClient):
    """
    Critical requirement: Two recipients named 'Rahul Sharma' must not
    overwrite each other on disk or inside the ZIP archive.
    """
    payload = {
        "event_name": "Indian Institute of AI Fellowship",
        "issuer_name": "National Computing Council",
        "recipients": [
            {"name": "Rahul Sharma", "email": "rahul.sharma.1@example.in"},
            {"name": "Rahul Sharma", "email": "rahul.sharma.2@example.in"},
            {"name": "Rahul Sharma", "email": "rahul.sharma.3@example.in"}
        ]
    }

    resp = client.post("/api/v1/jobs", json=payload)
    assert resp.status_code == 202
    job_id = resp.json()["id"]

    status_resp = client.get(f"/api/v1/jobs/{job_id}")
    assert status_resp.status_code == 200
    job_data = status_resp.json()
    assert job_data["status"] == "COMPLETED"
    assert job_data["successful_recipients"] == 3

    recs = job_data["recipients"]
    assert len(recs) == 3

    # 1. Verify all 3 have distinct certificate IDs
    cert_ids = [r["certificate_id"] for r in recs]
    assert len(set(cert_ids)) == 3

    # 2. Verify all 3 individual download endpoints work
    for cid in cert_ids:
        dl_resp = client.get(f"/api/v1/certificates/{cid}/download")
        assert dl_resp.status_code == 200
        assert dl_resp.headers["content-type"] == "application/pdf"
        assert dl_resp.content.startswith(b"%PDF-")

    # 3. Verify ZIP archive contains 3 distinct files without overwriting
    zip_resp = client.get(f"/api/v1/jobs/{job_id}/download-all")
    assert zip_resp.status_code == 200
    assert zip_resp.headers["content-type"] == "application/zip"

    zip_bytes = io.BytesIO(zip_resp.content)
    with zipfile.ZipFile(zip_bytes, "r") as zf:
        namelist = zf.namelist()
        assert len(namelist) == 3
        assert len(set(namelist)) == 3  # All filenames must be unique
        for filename in namelist:
            assert "Rahul_Sharma" in filename
            content = zf.read(filename)
            assert content.startswith(b"%PDF-")


def test_hindi_names_safe_filename_fallback(client: TestClient):
    """
    Verifies that recipients with non-ASCII / Hindi names generate safe,
    clean filenames that fall back to cert ID tokens rather than empty strings
    or OS encoding errors.
    """
    payload = {
        "event_name": "Devanagari Test Conference",
        "issuer_name": "Hindi Tech Forum",
        "recipients": [
            {"name": "राहुल शर्मा", "email": "hindi.rahul@example.in"},
            {"name": "अमिताभ बच्चन", "email": "amitabh@example.in"}
        ]
    }

    resp = client.post("/api/v1/jobs", json=payload)
    assert resp.status_code == 202
    job_id = resp.json()["id"]

    status_resp = client.get(f"/api/v1/jobs/{job_id}")
    assert status_resp.status_code == 200
    job_data = status_resp.json()
    assert job_data["status"] == "COMPLETED"

    recs = job_data["recipients"]
    assert len(recs) == 2

    # Download individual certificates
    for r in recs:
        cid = r["certificate_id"]
        dl = client.get(f"/api/v1/certificates/{cid}/download")
        assert dl.status_code == 200
        assert dl.headers["content-type"] == "application/pdf"
        assert dl.content.startswith(b"%PDF-")

    # Verify ZIP contains valid entries with cert token fallbacks
    zip_resp = client.get(f"/api/v1/jobs/{job_id}/download-all")
    assert zip_resp.status_code == 200
    zip_bytes = io.BytesIO(zip_resp.content)
    with zipfile.ZipFile(zip_bytes, "r") as zf:
        namelist = zf.namelist()
        assert len(namelist) == 2
        for fn in namelist:
            assert fn.endswith(".pdf")
            assert len(fn) > 5
