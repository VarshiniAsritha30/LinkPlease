# Week 1 Improvement Plan — LinkPlease

> **Purpose:** A realistic, prioritised 7-day backlog to address the most critical production gaps identified in FAILURES.md and TRADEOFFS.md.  
> **Format:** Priority → Task → Owner → Effort → Acceptance Criteria

---

## Priority Ranking Criteria

Items are ranked by: **Risk × Likelihood × Effort-to-Fix**

- 🔴 **P0 — Critical / Fix This Week:** Active security or data integrity risk in production.
- 🟠 **P1 — High / Fix This Week If Possible:** Causes silent data loss or incorrect behaviour at low traffic.
- 🟡 **P2 — Medium / Plan for Next Sprint:** Degrades performance or operator visibility.
- 🟢 **P3 — Low / Tech Debt Backlog:** Correctness or maintainability improvement.

---

## Day 1 — Security & Authentication

### 🔴 P0.1 — Enable Webhook Signature Verification by Default

**Problem:** `WEBHOOK_SIGNATURE_REQUIRED=false` means any anonymous HTTP client can trigger DM sends.

**Fix:**
1. Change `render.yaml` default to `WEBHOOK_SIGNATURE_REQUIRED=true`.
2. Change `.env.example` to `WEBHOOK_SIGNATURE_REQUIRED=true` with a comment explaining how to get the key.
3. Add a startup warning log if `WEBHOOK_SIGNATURE_REQUIRED=false` and app is not in `DEBUG` mode.

**Effort:** 30 minutes  
**Acceptance Criteria:**
- `POST /webhook` without `X-PseudoGram-Signature` returns `HTTP 401` in default config.
- Existing test `test_signature.py` covers this path.
- Startup log prints `WARNING: Webhook signature verification is DISABLED.` if off.

---

### 🔴 P0.2 — Add Max Length Validation to DM Message

**Problem:** `Rule.dm_message` is unbounded. A 50,000-character message causes a silent 400 failure at send time.

**Fix:**
```python
# app/schemas/rule.py
class RuleCreate(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=100)
    dm_message: str = Field(..., min_length=1, max_length=1000)
```

**Effort:** 15 minutes  
**Acceptance Criteria:**
- `POST /rules` with `dm_message` > 1000 characters returns `HTTP 422 Unprocessable Entity`.
- Add one test in `test_rules.py` asserting this.

---

## Day 2 — Operator Visibility

### 🟠 P1.1 — Add `GET /health` Endpoint

**Problem:** Render, Docker, and any load balancer have no way to probe application health. A crashed worker is invisible to the platform.

**Fix:** Add `app/api/health.py`:
```python
@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)) -> dict:
    try:
        await db.execute(text("SELECT 1"))
        db_reachable = True
    except Exception:
        db_reachable = False
    return {
        "status": "ok" if db_reachable else "degraded",
        "worker_running": dm_worker._running,
        "db_reachable": db_reachable,
    }
```

Update `render.yaml`:
```yaml
healthCheckPath: /health
```

**Effort:** 1 hour  
**Acceptance Criteria:**
- `GET /health` returns `200 {"status": "ok", "worker_running": true, "db_reachable": true}`.
- If DB is unreachable, returns `200 {"status": "degraded", ...}` (not 500 — health endpoints must not error).

---

### 🟠 P1.2 — Add `GET /api/jobs/{job_id}` Endpoint for Job Introspection

**Problem:** When a DM job fails, there's no way to look up a specific job's full history without querying the database directly.

**Fix:** Add `GET /api/jobs/{job_id}` returning the full `DMJob` record including `last_error`, `attempts`, `dm_id`, and all timestamps.

**Effort:** 45 minutes  
**Acceptance Criteria:**
- `GET /api/jobs/{job_id}` returns `200` with full job details.
- Returns `404` with `ErrorResponse` body for unknown job IDs.

---

## Day 3 — Stuck Job Escalation

### 🟠 P1.3 — Auto-Escalate Jobs Stuck in `ACCEPTED` Beyond 1 Hour

**Problem:** Jobs that receive `202 Accepted` but never receive a `delivered` or `failed` status from Pseudogram stay in `accepted` forever, inflating the `queued` count indefinitely.

**Fix:** In `_reconcile_accepted_jobs`, add:
```python
from datetime import timedelta
ACCEPTED_TIMEOUT = timedelta(hours=1)

if utc_now() - job.updated_at > ACCEPTED_TIMEOUT:
    job.status = DMJobStatus.FAILED.value
    job.last_error = f"Timed out in accepted state after {ACCEPTED_TIMEOUT}. dm_id={job.dm_id}"
    logger.error("DMJob %s escalated to failed: stuck in accepted for >1 hour", job.id)
```

**Effort:** 1 hour  
**Acceptance Criteria:**
- A job that stays in `accepted` for >1 hour automatically transitions to `failed`.
- Add test `test_accepted_timeout.py` mocking a job with `updated_at` 2 hours ago.

---

## Day 4 — Data Integrity & Logging

### 🟡 P2.1 — Structured JSON Logging

**Problem:** Logs use plain string format: `"%(asctime)s [%(levelname)s] %(name)s: %(message)s"`. In production on Render, these are not parseable by log aggregators (Datadog, Papertrail, Logtail).

**Fix:** Install `python-json-logger` and update `main.py`:
```python
from pythonjsonlogger import jsonlogger
handler = logging.StreamHandler()
handler.setFormatter(jsonlogger.JsonFormatter(
    fmt="%(asctime)s %(levelname)s %(name)s %(message)s"
))
logging.getLogger().addHandler(handler)
```

Add structured extras to key log lines:
```python
logger.info("DMJob accepted", extra={"job_id": job.id, "dm_id": dm_id, "http_status": status_code})
```

**Effort:** 2 hours  
**Acceptance Criteria:**
- Each log line is valid JSON parseable by `json.loads()`.
- `job_id` and `dm_id` appear as top-level JSON fields in DM-related log lines.

---

### 🟡 P2.2 — Add `POST /api/jobs/{job_id}/retry` Admin Endpoint

**Problem:** Once a job reaches `failed` status, there is no way to retry it without a raw SQL update. Operators dealing with an outage aftermath have no self-service recovery.

**Fix:**
```python
@router.post("/api/jobs/{job_id}/retry")
async def retry_job(job_id: str, db: AsyncSession = Depends(get_db)):
    job = await db.get(DMJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status != DMJobStatus.FAILED.value:
        raise HTTPException(400, f"Job is in state '{job.status}', not 'failed'")
    job.status = DMJobStatus.QUEUED.value
    job.attempts = 0
    job.last_error = None
    job.next_attempt_at = utc_now()
    await db.commit()
    return {"job_id": job_id, "status": "requeued"}
```

**Effort:** 1.5 hours  
**Acceptance Criteria:**
- `POST /api/jobs/{job_id}/retry` on a `failed` job sets it back to `queued`.
- Returns `400` if job is not in `failed` state.

---

## Day 5 — Rate Limiter Resilience

### 🟡 P2.3 — Persist Rate Limiter State to DB on Shutdown

**Problem:** Rate limiter loses its sliding window on every restart, risking burst-over-limit after cold start.

**Fix (pragmatic, no Redis):** On `DMWorker.stop()`, write the current timestamp list to a DB row. On `DMWorker.start()`, restore it.

Add a `RateLimiterState` SQLAlchemy model with a single row storing JSON-serialised timestamps. On startup, if the persisted timestamps are within the last 60 seconds, load them into the deque.

**Effort:** 3 hours  
**Acceptance Criteria:**
- After `uvicorn` restart, `dm_rate_limiter._timestamps` is pre-populated from the DB if a recent state exists.
- Unit test verifies restore + window eviction of stale timestamps.

---

## Day 6 — Performance & Scalability

### 🟡 P2.4 — Cache Active Rules With 5-Second TTL

**Problem:** Every `comment.created` webhook fires `SELECT * FROM rules WHERE active = true`. At high comment volume, this hammers the DB for data that changes rarely.

**Fix:**
```python
import asyncio
from datetime import datetime, timedelta

_rules_cache: list = []
_rules_cache_expiry: datetime = datetime.min

async def get_active_rules_cached(db: AsyncSession) -> list:
    global _rules_cache, _rules_cache_expiry
    if datetime.utcnow() < _rules_cache_expiry:
        return _rules_cache
    _rules_cache = await get_active_rules(db)
    _rules_cache_expiry = datetime.utcnow() + timedelta(seconds=5)
    return _rules_cache
```

**Effort:** 1.5 hours  
**Acceptance Criteria:**
- At 100 webhooks/second, DB shows ≤1 `SELECT rules` query per 5 seconds.
- Cache is invalidated immediately on `POST /rules` (call `_rules_cache_expiry = datetime.min`).

---

## Day 7 — Documentation & Deploy Polish

### 🟢 P3.1 — Add Alembic for Schema Migrations

**Problem:** `Base.metadata.create_all()` is not safe for production. It cannot add columns, rename fields, or drop tables without manual intervention.

**Fix:**
```bash
pip install alembic
alembic init alembic
# Configure alembic.ini to use DATABASE_URL from settings
alembic revision --autogenerate -m "initial schema"
alembic upgrade head
```

Update `main.py` startup to run `alembic upgrade head` instead of `create_all`.

**Effort:** 3 hours  
**Acceptance Criteria:**
- `alembic upgrade head` creates all tables from scratch.
- `alembic downgrade -1` safely reverses the latest migration.

---

### 🟢 P3.2 — Add `pytest-cov` Coverage Report

**Problem:** There is no code coverage measurement. It is unknown which branches (e.g., `status_code 404` in reconciliation) are tested.

**Fix:**
```bash
pip install pytest-cov
pytest --cov=app --cov-report=html
```

Add `coverage.xml` to `.gitignore`. Target: ≥85% line coverage.

**Effort:** 30 minutes  
**Acceptance Criteria:**
- `pytest --cov=app --cov-report=term-missing` passes showing ≥85% coverage.
- HTML report available at `htmlcov/index.html`.

---

## Summary Table

| Day | Item | Priority | Effort | Risk if Skipped |
|-----|------|----------|--------|-----------------|
| 1 | Enable signature verification default | 🔴 P0 | 30 min | Open unauthenticated webhook endpoint in production |
| 1 | Max message length validation | 🔴 P0 | 15 min | Silent DM delivery failures with no operator feedback |
| 2 | GET /health endpoint | 🟠 P1 | 1 hr | Platform cannot detect crashed worker |
| 2 | GET /api/jobs/{id} introspection | 🟠 P1 | 45 min | No self-service debugging for failed jobs |
| 3 | Auto-escalate stuck accepted jobs | 🟠 P1 | 1 hr | Permanently inflated queued count, rate limit budget waste |
| 4 | Structured JSON logging | 🟡 P2 | 2 hr | Logs unparseable by production log aggregators |
| 4 | Admin retry endpoint | 🟡 P2 | 1.5 hr | Manual SQL required to recover from outage-caused failures |
| 5 | Persist rate limiter state | 🟡 P2 | 3 hr | Burst-over-limit risk after every restart |
| 6 | Cache active rules | 🟡 P2 | 1.5 hr | DB hammered at high comment volume |
| 7 | Alembic migrations | 🟢 P3 | 3 hr | Schema changes require manual DB intervention |
| 7 | Test coverage report | 🟢 P3 | 30 min | Unknown coverage gaps |
