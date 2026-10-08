# Bulk Certificate Generator API (v1.2 Enterprise)

A high-throughput, resilient backend API built with **Python**, **FastAPI**, **SQLAlchemy**, and **ReportLab**. Designed to accept bulk certificate generation requests for event and course participants, generate certificates asynchronously from predefined vector templates, track real-time progress, and retrieve generated certificates individually or as bulk ZIP archives.

---

## 📋 Table of Contents
1. [Setup Instructions](#-setup-instructions)
2. [How to Run the Application](#-how-to-run-the-application)
3. [How to Run Tests](#-how-to-run-tests)
4. [How to Submit a Certificate Generation Request](#-how-to-submit-a-certificate-generation-request)
5. [How to Retrieve Generated Certificates](#-how-to-retrieve-generated-certificates)
6. [Important Implementation & Design Decisions](#-important-implementation--design-decisions)
   * [Sync vs. Background Processing Choice & Reasoning](#1-sync-vs-background-processing-choice--tradeoffs)
   * [Failure Resilience & Fault Isolation](#2-failure-resilience--fault-isolation)
   * [Devanagari (Hindi) Support & Complex Script Shaping Nuance](#3-devanagari-hindi-support--complex-script-shaping-nuance)
   * [Filename Sanitization & Non-ASCII Fallback](#4-filename-sanitization--non-ascii-fallback)
   * [SSRF Defense on Completion Webhooks](#5-ssrf-defense-on-completion-webhooks)
   * [Idempotency Edge Cases & Concurrency Race Protection](#6-idempotency-edge-cases--concurrency-race-protection)
   * [Verification Security, Rate Limiting & Privacy](#7-verification-security-rate-limiting--privacy)
   * [SQLite Concurrency & Batched Commits](#8-sqlite-concurrency--batched-commits)
   * [Environment Configuration & Startup Warnings](#9-environment-configuration--startup-warnings)
7. [Empirical Performance Benchmarks](#-empirical-performance-benchmarks)

---

## 🛠️ Setup Instructions

### Prerequisites
* Python 3.10+ (tested on Python 3.13)
* `pip`

### Installation
Clone or navigate to the repository directory and install dependencies:
```bash
python -m pip install -r requirements.txt
```

---

## 🚀 How to Run the Application

Start the local server using the launcher script:
```bash
python run.py
```
Or directly with Uvicorn:
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Once running, access:
* **Interactive Web Dashboard**: [http://127.0.0.1:8000](http://127.0.0.1:8000) (Live job submission, real-time polling, and ZIP downloads)
* **Interactive Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
* **ReDoc Documentation**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
* **Health Check Endpoint**: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)

---

## 🧪 How to Run Tests

Run the full automated test suite using `pytest`:
```bash
python -m pytest
```

### Mapping to Required Assignment Tests
The test suite explicitly implements and validates all 6 required criteria:

| Required Assignment Area | Explicit Test Name | Test File |
| :--- | :--- | :--- |
| **1. Creating a generation job** | `test_mandatory_create_generation_job` | [`tests/test_mandatory_suite.py`](file:///c:/web/Bulk%20Certification/tests/test_mandatory_suite.py) |
| **2. Input validation** | `test_mandatory_input_validation` | [`tests/test_mandatory_suite.py`](file:///c:/web/Bulk%20Certification/tests/test_mandatory_suite.py) |
| **3. Certificate generation** | `test_mandatory_certificate_generation` | [`tests/test_mandatory_suite.py`](file:///c:/web/Bulk%20Certification/tests/test_mandatory_suite.py) |
| **4. Job status / progress** | `test_mandatory_job_status_and_progress` | [`tests/test_mandatory_suite.py`](file:///c:/web/Bulk%20Certification/tests/test_mandatory_suite.py) |
| **5. Handling individual failure** | `test_mandatory_handling_individual_certificate_failure` | [`tests/test_mandatory_suite.py`](file:///c:/web/Bulk%20Certification/tests/test_mandatory_suite.py) |
| **6. Retrieving certificates** | `test_mandatory_retrieving_generated_certificates` | [`tests/test_mandatory_suite.py`](file:///c:/web/Bulk%20Certification/tests/test_mandatory_suite.py) |

*Total Suite: 34 tests passing across unit, integration, failure, collision, and security suites.*

---

## 📨 How to Submit a Certificate Generation Request

Submit a batch of recipients via `POST /api/v1/jobs`.

### Curl Example:
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/jobs" \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: batch-ai-summit-2026-001" \
  -d '{
    "event_name": "Full Stack Cloud & AI Systems 2026",
    "issuer_name": "DeepMind AI Academy",
    "issue_date": "2026-10-08",
    "description": "For exceptional dedication and completion of the distributed systems capstone.",
    "template_type": "classic",
    "deduplicate_emails": true,
    "recipients": [
      {
        "name": "Alice Smith",
        "email": "alice.smith@example.com",
        "extra_data": { "grade": "Distinction", "rank": "1st" }
      },
      {
        "name": "राहुल शर्मा (Rahul Sharma)",
        "email": "rahul.sharma@example.in",
        "extra_data": { "grade": "Distinction" }
      },
      {
        "name": "Invalid Recipient Entry",
        "email": "not-a-valid-email-address"
      }
    ]
  }'
```

### Response (`202 Accepted`):
```json
{
  "id": "c7a82b9e-4e31-419b-a790-264627d2bf18",
  "idempotency_key": "batch-ai-summit-2026-001",
  "event_name": "Full Stack Cloud & AI Systems 2026",
  "issuer_name": "DeepMind AI Academy",
  "issue_date": "2026-10-08",
  "description": "For exceptional dedication and completion of the distributed systems capstone.",
  "template_type": "classic",
  "status": "PENDING",
  "total_recipients": 3,
  "processed_recipients": 0,
  "successful_recipients": 0,
  "failed_recipients": 0,
  "progress_percentage": 0.0,
  "error_message": null,
  "created_at": "2026-10-08T17:40:00.000000+00:00",
  "started_at": null,
  "completed_at": null
}
```

---

## 📥 How to Retrieve Generated Certificates

### 1. Check Progress & Retrieve Metadata
Query `GET /api/v1/jobs/{job_id}`:
```bash
curl "http://127.0.0.1:8000/api/v1/jobs/c7a82b9e-4e31-419b-a790-264627d2bf18"
```
Returns overall job progress (`COMPLETED`, `PARTIALLY_FAILED`, etc.) and the list of recipients with their `certificate_id` and download URLs.

### 2. Download an Individual PDF Certificate
Query `GET /api/v1/certificates/{certificate_id}/download`:
```bash
curl -O "http://127.0.0.1:8000/api/v1/certificates/CERT-A1B2-C3D4-E5F6/download"
```
Streams the high-resolution vector PDF with `Content-Type: application/pdf`.

### 3. Bulk Download All Certificates as a ZIP Archive
Query `GET /api/v1/jobs/{job_id}/download-all`:
```bash
curl -O "http://127.0.0.1:8000/api/v1/jobs/c7a82b9e-4e31-419b-a790-264627d2bf18/download-all"
```
Streams a compressed ZIP file containing every successfully generated certificate in the batch.

### 4. Verify Authenticity Online
Query `GET /api/v1/certificates/verify/{certificate_id}` (also accessible by scanning the vector QR code on the certificate):
```bash
curl "http://127.0.0.1:8000/api/v1/certificates/verify/CERT-A1B2-C3D4-E5F6"
```

### 5. Retry Failed Recipients
If any recipients failed validation or rendering, re-enqueue only the failures:
```bash
curl -X POST "http://127.0.0.1:8000/api/v1/jobs/{job_id}/retry"
```

---

## 💡 Important Implementation & Design Decisions

### 1. Sync vs. Background Processing Choice & Trade-offs
* **The Choice**: We chose **asynchronous background processing** (`202 Accepted` + background worker pipeline) over synchronous generation.
* **Reasoning**:
  1. *Timeout Avoidance*: Generating certificates synchronously for 500 recipients would block the HTTP connection for 20+ seconds, exceeding standard proxy/ingress gateway timeouts (e.g. Nginx 60s 504 Gateway Timeout).
  2. *Server Throughput*: Synchronous processing monopolizes web worker threads, starving concurrent health checks and status queries.
* **The BackgroundTasks Trade-off**:
  * FastAPI's in-process `BackgroundTasks` runner was selected to keep the repository self-contained and immediately runnable without requiring an external Redis/RabbitMQ cluster.
  * *The Vulnerability*: In-process workers do not survive server restarts. If the process is terminated mid-batch, in-flight work is lost.
  * *The Mitigation*:
    1. **Startup Sweep**: On boot, [`sweep_stale_processing_jobs()`](file:///c:/web/Bulk%20Certification/app/main.py#L18-L64) queries dangling `PROCESSING` jobs, reconciles completed recipients, and flags unfinished jobs.
    2. **Partial Retry Endpoint**: Clients invoke `POST /jobs/{id}/retry` to resume only pending/failed recipients without re-generating existing certificates.
* **Single-Process Assumption**:
  * The startup sweep runs inside FastAPI's lifespan. If deployed across multiple Uvicorn workers (`uvicorn --workers N`) or multiple container replicas on the same database, one booting worker could inadvertently mark another active worker's jobs as stale. In multi-pod production, run the recovery sweep as a pre-start init task (e.g., Kubernetes init container) or use worker heartbeats.

### 2. Failure Resilience & Fault Isolation
* A single malformed email or rendering failure must not abort the remaining certificates in a 5,000-recipient batch.
* We implement two-tier validation:
  1. *Request-level*: Validates structural schema.
  2. *Recipient-level*: Evaluates individual emails and names during worker execution. Invalid items transition to `FAILED` with explicit error descriptions while valid recipients proceed to `SUCCESS`.
* If a worker crashes mid-batch, up to 24 uncommitted PDFs may reside on disk without a database `SUCCESS` row. When resumed or retried, existing files are safely overwritten in-place rather than creating duplicates.

### 3. Devanagari (Hindi) Support & Complex Script Shaping Nuance
* Standard ReportLab PostScript Type 1 fonts (Helvetica, Times) only support WinAnsiEncoding and crash with `UnicodeEncodeError` on Indic scripts.
* We bundle Google's `NotoSansDevanagari-Regular.ttf` in `app/fonts/`, loaded via relative path, ensuring zero OS font dependencies across Linux, Docker, and Windows.
* **Important Nuance on Complex Script Shaping**:
  ReportLab draws TrueType glyphs linearly based on unicode code points without an integrated OpenType GSUB/GPOS shaping engine (such as HarfBuzz). While individual Devanagari characters render cleanly across all platforms, complex conjunct ligatures (e.g., halant ligatures in *शर्मा*) are placed as sequential glyphs. For full production ligatures, an upstream OpenType shaping step (via `uharfbuzz`) or a headless layout engine is recommended.

### 4. Filename Sanitization & Non-ASCII Fallback
* Standard sanitizers strip non-ASCII characters, which would reduce a Hindi name like "राहुल शर्मा" to an empty string.
* Our sanitizer preserves clean alphanumeric characters. If stripping yields an empty or non-ASCII string, it falls back cleanly to `cert_{cert_id_token}.pdf`.
* Duplicate names (e.g., two entries named *Rahul Sharma*) are disambiguated on disk by unique credential tokens and inside ZIP archives via numeric counters (`Rahul_Sharma.pdf`, `Rahul_Sharma_2.pdf`).

### 5. SSRF Defense on Completion Webhooks
* When a user provides a `webhook_url`, the server POSTs completion metrics.
* To prevent Server-Side Request Forgery (SSRF) targeting internal networks, `is_safe_webhook_url()` resolves the destination hostname via DNS and strictly blocks:
  * Private RFC-1918 subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`)
  * Loopback addresses (`127.0.0.1`, `::1`)
  * Cloud metadata services (`169.254.169.254`)
  * Link-local and multicast IPs
* HTTP requests use `follow_redirects=False` and a strict 5-second timeout.

### 6. Idempotency Edge Cases & Concurrency Race Protection
* Replaying the same `Idempotency-Key` with identical payload returns the existing job (`200 OK`).
* Replaying the same key with a **different payload** is detected via deterministic SHA-256 payload hashing and rejected with **409 Conflict**.
* Under concurrent submissions with the same key, a database `unique=True` constraint on `idempotency_key` catches `IntegrityError` upon commit, safely rolls back, and returns the winning job.

### 7. Verification Security, Rate Limiting & Privacy
* Certificate IDs are 48-bit entropy pseudorandom tokens generated using Python's standard `secrets` module (`CERT-XXXX-XXXX-XXXX`), rendering online brute-force enumeration intractable when combined with rate limiting.
* The public `/verify` endpoint is protected by a sliding-window `RateLimiter` (60 requests/minute per IP) with bounded cache eviction and `X-Forwarded-For` proxy awareness.
* *Production Note*: In-memory rate limiting is process-local; multi-pod production systems should back this with Redis token buckets.
* *Privacy*: Verification returns the recipient name and course title for credential authentication (standard for digital diplomas). To prevent bulk PII harvesting, the rate limiter restricts automated scraping.

### 8. SQLite Concurrency & Batched Commits
* SQLite in WAL mode enables concurrent readers alongside a single serialized writer.
* To avoid locking errors:
  1. Configured `PRAGMA busy_timeout = 10000` (10 seconds) on engine connect.
  2. Commits are batched every `BATCH_COMMIT_SIZE = 25` recipients rather than committing in a tight per-item loop.

### 9. Environment Configuration & Startup Warnings
* `APP_BASE_URL`: Baked into certificate QR codes. At startup, the server emits a warning if set to `127.0.0.1` or `localhost`.
* `API_KEY`: Authentication via `X-API-Key` is enforced when set. If unset, authentication is bypassed for evaluation simplicity.

---

## ⚡ Empirical Performance Benchmarks

Measured using [`benchmark.py`](file:///c:/web/Bulk%20Certification/benchmark.py) over 100 consecutive certificates:

```text
1. Standard Latin Template (Type 1 Fonts + Vector QR):
   Execution Time:       4.490 s (100 certs)
   Avg Latency per Cert: 44.90 ms
   Throughput:           22.3 certs/sec
   Avg File Size:        4.90 KB

2. Devanagari / Hindi Template (Bundled TrueType Font + Vector QR):
   Execution Time:       4.702 s (100 certs)
   Avg Latency per Cert: 47.02 ms
   Throughput:           21.3 certs/sec
   Avg File Size:        16.96 KB
```
*Note: Embedding the bundled TrueType font subset for Devanagari increases average PDF file size from ~4.9 KB to ~16.96 KB, with comparable throughput (~21 certs/second).*
