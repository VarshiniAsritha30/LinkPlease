# LinkPlease - Reliable Instagram Comment DM Automation Engine

LinkPlease is a production-grade, highly reliable FastAPI backend and monitoring dashboard designed to automate Instagram Direct Messages (DMs) triggered by post comments, interfacing with an intentionally unreliable Mock API (Pseudogram).

---

## 🌟 Overview

Creators set rules such as:
> **Keyword:** `PRICE`  
> **DM Message:** `Here is our official price list: https://example.com/pricing`

When a user comments on a creator's post with `"Can you send the PRICE please?"`:
1. The webhook arrives at `POST /webhook`.
2. LinkPlease validates the payload and HMAC signature, persists the event, and responds with `HTTP 200 OK` in **under 50ms**.
3. A background queue matches active rules against the comment text.
4. Database uniqueness rules prevent duplicate DMs even if the user comments multiple times or webhooks arrive out-of-order/concurrently.
5. A durable polling worker respects a strict **10 requests per 60 seconds** rate limit, sends DMs with `Idempotency-Key` headers, handles exponential backoffs, and reconciles delivery status via background polling.

---

## 🏗️ Architecture

```
Webhook Request (POST /webhook)
  ├── HMAC-SHA256 Signature Verification
  ├── Store WebhookEvent (DB UNIQUE constraint on event_id)
  └── Return 200 OK (< 50ms)
        │
        ▼ (Async Processing)
  ├── Rule Matcher (Case-insensitive word boundary regex \bKEYWORD\b)
  ├── Deduplication Check (DB UNIQUE constraint on rule_id + user_id)
  └── Create DMJob (status: queued)
        │
        ▼ (Durable DB Worker)
  ├── Sliding Window Rate Limiter (Max 10 POST /v1/dm/send per 60s)
  ├── External API Call with Idempotency-Key
  │      ├── 202 Accepted -> store dm_id, set status to accepted
  │      ├── 429 Rate Limited -> parse Retry-After, exponential backoff
  │      ├── 500 Server Error -> exponential backoff + jitter
  │      └── 400 Bad Request -> permanent failure (status = failed)
        │
        ▼ (Reconciliation Engine)
  └── GET /v1/dm/{dm_id} Status Polling
         ├── delivered -> status = delivered (Counted in /stats sent)
         ├── failed -> retry or mark failed
         └── queued -> await next poll cycle
```

---

## 🛡️ Reliability & Deduplication Strategy

1. **Layer 1: Event-Level Deduplication**
   - `WebhookEvent.event_id` has a database `UNIQUE` constraint. Duplicate webhooks with the same `event_id` return HTTP 200 immediately without creating extra jobs.
2. **Layer 2: User/Rule-Level Idempotency (Concurrency-Safe)**
   - `DMJob` has a database `UNIQUE(rule_id, user_id)` constraint.
   - If two comments from `usr_123` arrive concurrently, the database enforces that only ONE job can be inserted. The secondary transaction raises an `IntegrityError` and is recorded as a `DuplicateBlock` record for accurate `/stats`.
3. **Application Rate Limiter**
   - Enforces a maximum of 10 `POST /v1/dm/send` requests per rolling 60-second window using a sliding window timestamps queue.
   - Respects `Retry-After` headers on HTTP 429 responses.
4. **Durable Database Persistence & Process Recovery**
   - Jobs are stored on disk in SQLite/PostgreSQL (not in memory). On server restart, jobs stuck in `sending` are safely reset to `retry_wait` and resumed.
5. **Idempotency Keys**
   - Outer API calls pass `Idempotency-Key: dm-job-{job_id}`. Retries after network timeouts do not cause duplicate DMs on Pseudogram.
6. **Delivery Status Reconciliation**
   - HTTP 202 does **not** mean delivered. The job remains in `accepted` until `GET /v1/dm/{dm_id}` confirms `delivered`.

---

## 💾 Why SQLite with WAL Mode?

For local development and single-container deployments (e.g. Render/Fly.io), SQLite configured with **Write-Ahead Logging (WAL)** (`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000;`) provides concurrent reads and non-blocking writes without external database dependency overhead. The codebase uses SQLAlchemy 2.0 async engine (`aiosqlite` / `asyncpg`) and switches to PostgreSQL by changing `DATABASE_URL`.

---

## 🚀 Environment Variables

Create a `.env` file (see `.env.example`):

| Variable | Default | Description |
| :--- | :--- | :--- |
| `PSEUDOGRAM_API_BASE_URL` | `https://pseudogram-api.onrender.com` | Base URL for external Mock API |
| `PSEUDOGRAM_API_KEY` | `""` | X-API-Key for external API calls |
| `DATABASE_URL` | `sqlite+aiosqlite:///./linkplease.db` | Async database connection string |
| `WEBHOOK_SIGNATURE_REQUIRED` | `false` | Enforce HMAC-SHA256 header validation |
| `MAX_DM_ATTEMPTS` | `5` | Maximum retry limit for DM sending |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`) |

---

## 🔌 API Endpoints

### 1. `POST /webhook`
Receives comment webhook events.  
**Response:** `200 OK` `{ "status": "success", "message": "...", "event_id": "..." }`

### 2. `POST /rules`
Creates a DM automation rule.  
**Request:**
```json
{
  "keyword": "PRICE",
  "dm_message": "Here is our price list: https://example.com/pricing"
}
```
**Response:** `201 Created` `{ "rule_id": "...", "keyword": "PRICE", "dm_message": "..." }`

### 3. `GET /stats`
Returns aggregated metrics derived directly from persistent database state.  
**Response:**
```json
{
  "sent": 142,
  "failed": 3,
  "queued": 8,
  "duplicates_blocked": 57
}
```

---

## 💻 Local Setup & Execution

### Step 1: Install Dependencies
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 2: Run Application
You can run the application using `npm` from either the workspace root or the `LinkPlease` directory:

```bash
npm run dev
```

Alternatively, you can run it directly using Uvicorn (after activating the virtual environment):
```bash
uvicorn app.main:app --reload --port 8000
```
Visit Interactive Swagger Docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)  
Visit Live Dashboard: [http://127.0.0.1:8000/dashboard](http://127.0.0.1:8000/dashboard)


---

## 🧪 Automated Testing Suite

Run the full automated test suite covering rules, matching, deduplication, concurrency, 500 retries, 429 rate limiting, 400 failure, 202 reconciliation, comment deletion, signature validation, and process restart recovery:

```bash
pytest -v
```

---

## ⚡ 500-Event Load Testing

To run the simulator load test against a deployed app:

```bash
# 1. Obtain API Key
python scripts/keygen.py

# 2. Execute Load Test
python scripts/load_test.py https://YOUR-APP.onrender.com/webhook YOUR_API_KEY
```

---

## 🐳 Docker & Production Deployment

Build and run via Docker:
```bash
docker build -t linkplease .
docker run -p 8000:8000 -e PSEUDOGRAM_API_KEY="your_key" linkplease
```

Deploy on Render using `render.yaml`:
1. Connect your repository to Render.
2. Render will automatically detect `render.yaml` and create the web service with Uvicorn.
