import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.config import settings
from app.database import init_db, SessionLocal
from app.models.job import Job, JobStatus, get_utc_now
from app.models.recipient import Recipient, RecipientStatus
from app.api.v1.router import api_v1_router

logger = logging.getLogger(__name__)


def sweep_stale_processing_jobs():
    """
    Startup recovery routine:
    Identifies any jobs left in PROCESSING or PENDING from an ungraceful server restart or crash.
    Finalizes completed portions and marks unfinished jobs so they never hang in PROCESSING forever,
    enabling immediate one-click resume via POST /api/v1/jobs/{id}/retry.
    
    Single-Process Lifespan Note:
    This lifespan sweep assumes a single-process deployment or pre-fork execution.
    In multi-worker production deployments (`uvicorn --workers N` or multiple pods),
    this sweep should be executed as a pre-start init task (e.g. Kubernetes init container)
    to prevent a booting worker process from inadvertently marking a sister worker's active jobs as stale.
    """
    db = SessionLocal()
    try:
        stale_jobs = db.query(Job).filter(
            Job.status.in_([JobStatus.PROCESSING.value, JobStatus.PENDING.value])
        ).all()

        for job in stale_jobs:
            pending_count = (
                db.query(Recipient)
                .filter(Recipient.job_id == job.id, Recipient.status == RecipientStatus.PENDING.value)
                .count()
            )
            
            if pending_count == 0 and job.total_recipients > 0:
                if job.failed_recipients == 0:
                    job.status = JobStatus.COMPLETED.value
                elif job.successful_recipients > 0:
                    job.status = JobStatus.PARTIALLY_FAILED.value
                else:
                    job.status = JobStatus.FAILED.value
            else:
                if job.successful_recipients > 0:
                    job.status = JobStatus.PARTIALLY_FAILED.value
                else:
                    job.status = JobStatus.FAILED.value
                job.error_message = (
                    "Process interrupted by server restart/shutdown. "
                    "Unfinished recipients can be resumed using POST /api/v1/jobs/{id}/retry."
                )

            job.completed_at = get_utc_now()
            logger.warning(f"Startup sweep: Cleaned stale job {job.id} -> {job.status}")

        db.commit()
    except Exception as e:
        logger.error(f"Error during startup stale job recovery sweep: {e}")
        db.rollback()
    finally:
        db.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables on startup
    init_db()
    # Check QR Base URL
    if "127.0.0.1" in settings.APP_BASE_URL or "localhost" in settings.APP_BASE_URL:
        logger.warning(
            f"APP_BASE_URL is configured as '{settings.APP_BASE_URL}'. "
            "Embedded QR codes will point to localhost. Configure APP_BASE_URL in production."
        )
    # Sweep and recover any jobs left dangling in PROCESSING from prior restart
    sweep_stale_processing_jobs()
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="""
# Bulk Certificate Generator API

Production-grade asynchronous backend API for bulk certificate issuance.

### Core Capabilities:
* **Asynchronous Bulk Ingestion**: Immediate `202 Accepted` response with real-time tracking.
* **Idempotency & Deduplication**: Safe retries via `Idempotency-Key` header with payload hash validation.
* **SSRF Guarded Webhooks**: User webhooks are validated against private, link-local, and cloud metadata IPs.
* **Fault Isolation & Partial Retry**: Independent recipient processing with one-click re-enqueue via `POST /jobs/{id}/retry`.
* **Full Unicode & Vector QR Verification**: TrueType rendering supporting Devanagari (Hindi) / accented names, and scannable QR verification badges.
* **Database & Concurrency Hardening**: SQLite WAL mode with 10s busy timeout and batched commits.
* **Multi-Format Retrieval**: Stream individual PDFs, download bulk ZIP packages, or verify authenticity online.
    """,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API Routers
app.include_router(api_v1_router, prefix=settings.API_V1_STR)


@app.get("/health", tags=["Health"])
def health_check():
    """Health check endpoint for container orchestrators and monitoring."""
    return {
        "status": "healthy",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "storage_dir": str(settings.STORAGE_DIR),
        "database_url": settings.DATABASE_URL.split("?")[0],
    }


@app.get("/", response_class=HTMLResponse, tags=["Dashboard"])
def interactive_dashboard():
    """Interactive visual dashboard for testing and reviewing bulk certificate generation."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Bulk Certificate Generator - Dashboard</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
  <style>
    @keyframes pulse-subtle { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }
    .animate-pulse-subtle { animation: pulse-subtle 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; }
  </style>
</head>
<body class="bg-slate-50 text-slate-800 min-h-screen">
  <!-- Navbar -->
  <header class="bg-slate-900 text-white shadow-md">
    <div class="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
      <div class="flex items-center space-x-3">
        <i class="fa-solid fa-award text-amber-400 text-2xl"></i>
        <div>
          <span class="text-xl font-bold tracking-tight">Bulk Certificate Generator</span>
          <span class="ml-2 px-2 py-0.5 text-[11px] font-semibold bg-amber-500/20 text-amber-300 rounded border border-amber-500/30">v1.1 Enterprise</span>
        </div>
      </div>
      <div class="flex items-center space-x-4 text-sm">
        <a href="/docs" target="_blank" class="text-slate-300 hover:text-white flex items-center gap-1.5 bg-slate-800 px-3 py-1.5 rounded-lg border border-slate-700 transition">
          <i class="fa-solid fa-book text-amber-400"></i> Interactive Swagger Docs
        </a>
        <a href="/redoc" target="_blank" class="text-slate-300 hover:text-white flex items-center gap-1.5 bg-slate-800 px-3 py-1.5 rounded-lg border border-slate-700 transition">
          <i class="fa-solid fa-code"></i> ReDoc
        </a>
      </div>
    </div>
  </header>

  <!-- Main Container -->
  <main class="max-w-7xl mx-auto px-6 py-8">
    <div class="grid grid-cols-1 lg:grid-cols-12 gap-8">
      
      <!-- Left Column: Job Submission Form -->
      <div class="lg:col-span-5 bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
        <h2 class="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2">
          <i class="fa-solid fa-paper-plane text-amber-500"></i> Submit Generation Job
        </h2>

        <div class="space-y-4">
          <div>
            <label class="block text-xs font-semibold text-slate-600 uppercase mb-1">Event / Course Name *</label>
            <input id="eventName" type="text" value="Advanced Cloud & AI Systems 2026" 
              class="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-amber-500 focus:outline-none">
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-semibold text-slate-600 uppercase mb-1">Issuer Authority</label>
              <input id="issuerName" type="text" value="DeepMind AI Academy" 
                class="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-amber-500 focus:outline-none">
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-600 uppercase mb-1">Issue Date</label>
              <input id="issueDate" type="date" 
                class="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-amber-500 focus:outline-none">
            </div>
          </div>

          <div class="grid grid-cols-2 gap-3">
            <div>
              <label class="block text-xs font-semibold text-slate-600 uppercase mb-1">Template Style</label>
              <select id="templateType" class="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-amber-500 focus:outline-none">
                <option value="classic">Classic (Navy & Gold)</option>
                <option value="modern">Modern (Indigo & Emerald)</option>
              </select>
            </div>
            <div>
              <label class="block text-xs font-semibold text-slate-600 uppercase mb-1">Idempotency Key (Opt.)</label>
              <input id="idempotencyKey" type="text" placeholder="e.g. batch-2026-xyz" 
                class="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-amber-500 focus:outline-none">
            </div>
          </div>

          <div>
            <label class="block text-xs font-semibold text-slate-600 uppercase mb-1">Certificate Remarks / Description</label>
            <input id="description" type="text" value="For exceptional dedication and completion of all technical capstone projects." 
              class="w-full px-3 py-2 border border-slate-300 rounded-lg text-sm focus:ring-2 focus:ring-amber-500 focus:outline-none">
          </div>

          <div>
            <div class="flex justify-between items-center mb-1">
              <label class="block text-xs font-semibold text-slate-600 uppercase">Recipients (JSON list) *</label>
              <div class="space-x-1">
                <button onclick="loadSampleRecipients('standard')" class="text-xs text-amber-600 hover:text-amber-700 underline font-medium">Standard</button>
                <span class="text-slate-300">|</span>
                <button onclick="loadSampleRecipients('hindi')" class="text-xs text-indigo-600 hover:text-indigo-700 underline font-medium">Hindi (Unicode)</button>
                <span class="text-slate-300">|</span>
                <button onclick="loadSampleRecipients('failures')" class="text-xs text-rose-600 hover:text-rose-700 underline font-medium">Partial Failures</button>
              </div>
            </div>
            <textarea id="recipientsJson" rows="8" 
              class="w-full font-mono text-xs p-3 bg-slate-900 text-slate-100 rounded-lg border border-slate-700 focus:ring-2 focus:ring-amber-500 focus:outline-none"></textarea>
          </div>

          <button id="submitBtn" onclick="submitJob()" 
            class="w-full py-2.5 px-4 bg-amber-500 hover:bg-amber-600 text-slate-950 font-semibold rounded-lg shadow-sm transition flex items-center justify-center gap-2">
            <i class="fa-solid fa-bolt"></i> Generate Bulk Certificates
          </button>
        </div>
      </div>

      <!-- Right Column: Live Job Progress & Results -->
      <div class="lg:col-span-7 space-y-6">
        
        <!-- Active Job Card -->
        <div id="activeJobCard" class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
          <div class="flex items-center justify-between mb-4">
            <h2 class="text-lg font-bold text-slate-900 flex items-center gap-2">
              <i class="fa-solid fa-spinner text-amber-500" id="jobSpinner"></i> Active Job Status
            </h2>
            <div class="flex items-center gap-2">
              <button id="retryBtn" onclick="retryJob()" class="hidden px-2.5 py-1 text-xs font-bold rounded-lg bg-rose-600 hover:bg-rose-700 text-white shadow-sm transition">
                <i class="fa-solid fa-rotate-right"></i> Retry Failed
              </button>
              <span id="jobStatusBadge" class="px-2.5 py-1 text-xs font-bold rounded-full bg-slate-100 text-slate-600">NO JOB SELECTED</span>
            </div>
          </div>

          <div id="jobDetailsArea" class="text-slate-500 text-sm py-8 text-center">
            Submit a job or select a job from recent history below to view live generation progress.
          </div>
        </div>

        <!-- Recent Jobs History -->
        <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
          <div class="flex items-center justify-between mb-3">
            <h3 class="font-bold text-slate-900 flex items-center gap-2">
              <i class="fa-solid fa-clock-rotate-left text-slate-400"></i> Recent Jobs
            </h3>
            <button onclick="fetchRecentJobs()" class="text-xs text-slate-500 hover:text-slate-800">
              <i class="fa-solid fa-arrows-rotate"></i> Refresh
            </button>
          </div>
          <div id="recentJobsList" class="divide-y divide-slate-100 text-sm max-h-56 overflow-y-auto">
            <p class="py-4 text-center text-slate-400 text-xs">Loading recent jobs...</p>
          </div>
        </div>

      </div>
    </div>
  </main>

  <script>
    document.getElementById('issueDate').value = new Date().toISOString().split('T')[0];

    const standardRecipients = [
      { "name": "Ada Lovelace", "email": "ada.lovelace@computing.org", "extra_data": { "grade": "Distinction", "rank": "1st" } },
      { "name": "Alan Turing", "email": "alan.turing@manchester.ac.uk", "extra_data": { "grade": "Distinction" } },
      { "name": "Grace Hopper", "email": "grace.hopper@usnavy.mil", "extra_data": { "honors": "Summa Cum Laude" } },
      { "name": "Katherine Johnson", "email": "katherine.johnson@nasa.gov", "extra_data": { "grade": "Distinction" } }
    ];

    const hindiRecipients = [
      { "name": "राहुल शर्मा (Rahul Sharma)", "email": "rahul.sharma@example.in", "extra_data": { "grade": "Distinction" } },
      { "name": "अमिताभ बच्चन (Amitabh Bachchan)", "email": "amitabh@example.in", "extra_data": { "award": "Honorary" } },
      { "name": "Pooja Patel", "email": "pooja.patel@example.in", "extra_data": { "rank": "Top 1%" } }
    ];

    const partialFailureRecipients = [
      { "name": "Dr. Claude Shannon", "email": "claude@bell-labs.com", "extra_data": { "grade": "Distinction" } },
      { "name": "", "email": "missing.name@example.com" },
      { "name": "Tim Berners-Lee", "email": "bad-email-without-at-sign" },
      { "name": "Margaret Hamilton", "email": "margaret@mit.edu", "extra_data": { "grade": "Excellence" } },
      { "name": "Test Simulation Fail", "email": "simfail@example.com", "extra_data": { "_simulate_failure": true, "_simulate_failure_message": "Certificate template engine simulated failure" } }
    ];

    function loadSampleRecipients(type) {
      let data = standardRecipients;
      if (type === 'hindi') data = hindiRecipients;
      if (type === 'failures') data = partialFailureRecipients;
      document.getElementById('recipientsJson').value = JSON.stringify(data, null, 2);
    }
    loadSampleRecipients('standard');

    let currentJobId = null;
    let pollInterval = null;

    async function submitJob() {
      const submitBtn = document.getElementById('submitBtn');
      const eventName = document.getElementById('eventName').value;
      const issuerName = document.getElementById('issuerName').value;
      const issueDate = document.getElementById('issueDate').value;
      const description = document.getElementById('description').value;
      const templateType = document.getElementById('templateType').value;
      const idempotencyKey = document.getElementById('idempotencyKey').value;
      let recipients;
      
      try {
        recipients = JSON.parse(document.getElementById('recipientsJson').value);
      } catch (e) {
        alert("Invalid JSON format in Recipients field: " + e.message);
        return;
      }

      submitBtn.disabled = true;
      submitBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Submitting Job...';

      const headers = { 'Content-Type': 'application/json' };
      if (idempotencyKey.trim()) {
        headers['Idempotency-Key'] = idempotencyKey.trim();
      }

      try {
        const resp = await fetch('/api/v1/jobs', {
          method: 'POST',
          headers: headers,
          body: JSON.stringify({
            event_name: eventName,
            issuer_name: issuerName,
            issue_date: issueDate,
            description: description,
            template_type: templateType,
            recipients: recipients
          })
        });

        if (!resp.ok) {
          const errData = await resp.json();
          alert("Submission Error: " + (errData.detail || JSON.stringify(errData)));
          submitBtn.disabled = false;
          submitBtn.innerHTML = '<i class="fa-solid fa-bolt"></i> Generate Bulk Certificates';
          return;
        }

        const data = await resp.json();
        currentJobId = data.id;
        startPollingJob(currentJobId);
        fetchRecentJobs();
      } catch (err) {
        alert("Network error: " + err.message);
      } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<i class="fa-solid fa-bolt"></i> Generate Bulk Certificates';
      }
    }

    async function retryJob() {
      if (!currentJobId) return;
      const retryBtn = document.getElementById('retryBtn');
      retryBtn.disabled = true;
      retryBtn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> Retrying...';

      try {
        const resp = await fetch(`/api/v1/jobs/${currentJobId}/retry`, { method: 'POST' });
        if (!resp.ok) {
          const err = await resp.json();
          alert("Retry Error: " + (err.detail || JSON.stringify(err)));
          return;
        }
        startPollingJob(currentJobId);
      } catch (e) {
        alert("Network error: " + e.message);
      } finally {
        retryBtn.disabled = false;
        retryBtn.innerHTML = '<i class="fa-solid fa-rotate-right"></i> Retry Failed';
      }
    }

    function startPollingJob(jobId) {
      currentJobId = jobId;
      if (pollInterval) clearInterval(pollInterval);
      loadJobDetails(jobId);
      pollInterval = setInterval(() => loadJobDetails(jobId), 1500);
    }

    async function loadJobDetails(jobId) {
      try {
        const resp = await fetch(`/api/v1/jobs/${jobId}`);
        if (!resp.ok) return;
        const job = await resp.json();
        renderJobCard(job);

        if (job.status === 'COMPLETED' || job.status === 'PARTIALLY_FAILED' || job.status === 'FAILED') {
          clearInterval(pollInterval);
          pollInterval = null;
          fetchRecentJobs();
        }
      } catch (e) {
        console.error(e);
      }
    }

    function renderJobCard(job) {
      const statusColors = {
        'PENDING': 'bg-amber-100 text-amber-800',
        'PROCESSING': 'bg-blue-100 text-blue-800 animate-pulse',
        'COMPLETED': 'bg-emerald-100 text-emerald-800',
        'PARTIALLY_FAILED': 'bg-orange-100 text-orange-800',
        'FAILED': 'bg-rose-100 text-rose-800'
      };

      const badge = document.getElementById('jobStatusBadge');
      badge.className = `px-2.5 py-1 text-xs font-bold rounded-full ${statusColors[job.status] || 'bg-slate-100 text-slate-700'}`;
      badge.textContent = job.status;

      const retryBtn = document.getElementById('retryBtn');
      if (job.failed_recipients > 0) {
        retryBtn.classList.remove('hidden');
      } else {
        retryBtn.classList.add('hidden');
      }

      const spinner = document.getElementById('jobSpinner');
      spinner.className = (job.status === 'PROCESSING' || job.status === 'PENDING') ? 'fa-solid fa-spinner fa-spin text-amber-500' : 'fa-solid fa-circle-check text-emerald-500';

      const html = `
        <div class="space-y-4">
          <div class="flex flex-wrap justify-between items-start border-b border-slate-100 pb-3 gap-2">
            <div>
              <h3 class="font-bold text-slate-900">${job.event_name}</h3>
              <p class="text-xs text-slate-500">Issued by ${job.issuer_name} &bull; ${job.issue_date} &bull; ID: <code class="bg-slate-100 px-1 py-0.5 rounded text-slate-700">${job.id.substring(0,8)}...</code> &bull; Style: <span class="capitalize font-semibold text-slate-700">${job.template_type}</span></p>
              ${job.idempotency_key ? `<p class="text-[11px] text-indigo-600 mt-0.5">Idempotency Key: <code>${job.idempotency_key}</code></p>` : ''}
              ${job.error_message ? `<p class="text-xs text-rose-600 font-medium mt-1"><i class="fa-solid fa-triangle-exclamation"></i> ${job.error_message}</p>` : ''}
            </div>
            ${job.download_all_url ? `
              <a href="${job.download_all_url}" class="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold rounded-lg flex items-center gap-1.5 shadow-sm transition">
                <i class="fa-solid fa-file-zipper"></i> Download All (ZIP)
              </a>
            ` : ''}
          </div>

          <!-- Progress Bar -->
          <div>
            <div class="flex justify-between text-xs font-medium text-slate-600 mb-1">
              <span>Progress: ${job.processed_recipients} / ${job.total_recipients} (${job.progress_percentage}%)</span>
              <span class="space-x-2">
                <span class="text-emerald-600"><i class="fa-solid fa-check"></i> ${job.successful_recipients} succeeded</span>
                ${job.failed_recipients > 0 ? `<span class="text-rose-600"><i class="fa-solid fa-triangle-exclamation"></i> ${job.failed_recipients} failed</span>` : ''}
              </span>
            </div>
            <div class="w-full bg-slate-100 rounded-full h-3 overflow-hidden">
              <div class="h-3 rounded-full transition-all duration-300 ${job.failed_recipients > 0 ? 'bg-amber-500' : 'bg-emerald-500'}" style="width: ${job.progress_percentage}%"></div>
            </div>
          </div>

          <!-- Recipient Items Table -->
          <div class="mt-4">
            <h4 class="text-xs font-bold uppercase text-slate-400 mb-2">Recipient Records</h4>
            <div class="border border-slate-200 rounded-lg overflow-x-auto max-h-64 overflow-y-auto">
              <table class="min-w-full divide-y divide-slate-200 text-xs">
                <thead class="bg-slate-50 sticky top-0">
                  <tr>
                    <th class="px-3 py-2 text-left font-semibold text-slate-600">Recipient</th>
                    <th class="px-3 py-2 text-left font-semibold text-slate-600">Email</th>
                    <th class="px-3 py-2 text-left font-semibold text-slate-600">Status</th>
                    <th class="px-3 py-2 text-right font-semibold text-slate-600">Certificate / Action</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-slate-100 bg-white">
                  ${job.recipients.map(r => `
                    <tr class="hover:bg-slate-50">
                      <td class="px-3 py-2 font-medium text-slate-800">${r.name || '<em class="text-rose-500">[Missing Name]</em>'}</td>
                      <td class="px-3 py-2 text-slate-500">${r.email || '<em class="text-rose-500">[Missing Email]</em>'}</td>
                      <td class="px-3 py-2">
                        ${r.status === 'SUCCESS' ? '<span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800">SUCCESS</span>' :
                          r.status === 'FAILED' ? `<span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-rose-100 text-rose-800" title="${r.error_message || ''}">FAILED</span>` :
                          '<span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-100 text-amber-800">PENDING</span>'}
                      </td>
                      <td class="px-3 py-2 text-right">
                        ${r.download_url ? `
                          <a href="${r.download_url}" target="_blank" class="text-indigo-600 hover:text-indigo-800 font-medium inline-flex items-center gap-1">
                            <i class="fa-solid fa-file-pdf"></i> Download PDF
                          </a>
                        ` : (r.error_message ? `<span class="text-rose-500 text-[11px]">${r.error_message}</span>` : '<span class="text-slate-400">Processing...</span>')}
                      </td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      `;
      document.getElementById('jobDetailsArea').innerHTML = html;
    }

    async function fetchRecentJobs() {
      try {
        const resp = await fetch('/api/v1/jobs?limit=10');
        if (!resp.ok) return;
        const data = await resp.json();
        const listEl = document.getElementById('recentJobsList');
        
        if (!data.items || data.items.length === 0) {
          listEl.innerHTML = '<p class="py-4 text-center text-slate-400 text-xs">No jobs created yet.</p>';
          return;
        }

        listEl.innerHTML = data.items.map(j => `
          <div onclick="startPollingJob('${j.id}')" class="py-2.5 px-3 hover:bg-slate-50 rounded-lg cursor-pointer flex items-center justify-between transition">
            <div>
              <p class="font-semibold text-xs text-slate-800">${j.event_name}</p>
              <p class="text-[11px] text-slate-400">Total: ${j.total_recipients} &bull; Succeeded: ${j.successful_recipients} &bull; Failed: ${j.failed_recipients}</p>
            </div>
            <span class="text-[10px] font-bold px-2 py-0.5 rounded-full ${j.status === 'COMPLETED' ? 'bg-emerald-100 text-emerald-800' : j.status === 'PARTIALLY_FAILED' ? 'bg-orange-100 text-orange-800' : j.status === 'FAILED' ? 'bg-rose-100 text-rose-800' : 'bg-blue-100 text-blue-800'}">
              ${j.status}
            </span>
          </div>
        `).join('');
      } catch (e) {
        console.error(e);
      }
    }

    fetchRecentJobs();
  </script>
</body>
</html>
"""
