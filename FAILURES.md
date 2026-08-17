# FAILURES.md — Honest Failure Modes & Known Limitations

This document provides a technical analysis of the real-world failure modes and architectural limitations of LinkPlease. By grouping these into three core areas, operators can understand the system's trade-offs and mitigate risks under production workloads.

---

## 1. Distributed Consensus & Transactional Desynchronization

When interfacing with an external API (Pseudogram) and a local database, maintaining absolute consistency of job states across process crashes, webhooks, and out-of-order execution is a classic distributed systems challenge. LinkPlease has three main vulnerabilities in this area:

### A. The Crash-After-API-Response Gap
During a DM send job, the worker executes a `POST /v1/dm/send`. The Pseudogram API accepts the payload, registers a delivery job, and returns `HTTP 202 Accepted` with a `dm_id`. The worker must then execute `await db.commit()` to persist this `dm_id` and transition the local job status to `ACCEPTED`.

If the server crashes (due to OOM, manual restarts, or infrastructure sleep cycles) **after** the API returns the 202 but **before** the DB transaction is committed:
- The local job remains marked as `SENDING` or `RETRY_WAIT` in the database.
- Upon reboot, recovery logic schedule restarts this job, forcing a send retry.
- The retry relies on the `Idempotency-Key` header (`dm-job-{job_id}`). If Pseudogram has cleared its idempotency cache (e.g., due to TTL expiry, API restarts, or database resets), the recipient will receive a **duplicate DM**.

### B. Connection Drops Prior to Webhook Event Commitment
If Uvicorn receives a webhook request (`POST /webhook`), parses the payload, but crashes mid-execution (e.g., during SQLite write operations) before committing the `WebhookEvent` to disk:
- The database has no record of the webhook, and no `DMJob` is created.
- The TCP connection is closed abruptly. LinkPlease relies on the sender (Pseudogram) retrying the webhook upon connection failure. If Pseudogram treats a dropped connection as "delivered" or fails to retry, the comment event is **permanently lost**.

### C. Post-Delivery Comment Deletions (No Recall Path)
When a user deletes their comment, triggering a `comment.deleted` webhook:
- The repository successfully cancels any pending jobs (`QUEUED` or `RETRY_WAIT`).
- However, if the job has already transitioned to `DELIVERED`, the DM has landed in the user's inbox. There is no API-level recall mechanism. The record remains marked as `delivered` in our database, with no persistent audit trail link indicating that the original comment was deleted post-facto.

---

## 2. Resource Starvation & Concurrency Bottlenecks

LinkPlease is architected for lightweight, single-container environments. Under high-throughput conditions (e.g., concurrent comment storms), it suffers from performance degradation due to SQLite and memory-bound state designs:

### A. SQLite WAL Write Lock Contention
SQLite WAL mode allows multiple concurrent readers but serializes all writers through a single thread pool under Python's `aiosqlite`.
- Under high concurrency (50+ simultaneous webhook writes), writers contend for the SQLite write lock.
- Even with `PRAGMA busy_timeout=5000` (allowing writers to wait up to 5 seconds), sustained load leads to `OperationalError: database is locked`, forcing webhooks to return `HTTP 500` to the sender.
- Sequential writes are fast, but parallel write throughput degrades heavily under serialization overhead compared to dedicated client-server databases like PostgreSQL.

### B. In-Memory Rate Limiter State Loss
The sliding-window rate limiter tracks requests in a `collections.deque` stored in Python's active process memory.
- If the application restarts, this state is completely wiped.
- If the system had sent 9 DMs in the last 30 seconds before a restart, the new process starts with a clean sliding window count of 0.
- It will immediately allow up to 10 more sends, violating the strict **10 requests per 60 seconds** limit and triggering an API-level `429 Too Many Requests` or account suspension.

### C. O(N) Memory & Regex Rule Evaluation
Every incoming comment webhook queries all active rules using `SELECT * FROM rules WHERE active = true`, loading them into memory, and loops through them calling `re.search()` sequentially.
- With small rule counts, this is highly efficient.
- With larger configurations (e.g., 5,000+ active creator rules), this creates an `O(N)` scaling overhead in both memory allocation and CPU cycles per webhook request, introducing latency spikes and thread-pool starvation.

---

## 3. External API Integration Stagnation (Zombie Job States)

Interfacing with an external mock API exposes the application to remote outages, status expirations, and unhandled status loops that inflate stats and waste rate-limiting quotas:

### A. The "Zombie" Accepted Job Loop
Reconciliation logic polls `GET /v1/dm/{dm_id}` for jobs in the `ACCEPTED` state to verify delivery.
- If the external API consistently returns a status of `"queued"` (due to internal mock API processing freezes or outages), the job remains in `ACCEPTED` indefinitely.
- There is **no timeout threshold** to auto-expire jobs stuck in `ACCEPTED`.
- The reconciliation worker continues to poll these stale records in every 1-second interval, wasting rate limit tokens and inflating the `/stats` `queued` count.

### B. 404 Status Responses on Reconciliation
If a DM was accepted by the external API (returning 202) but during status polling, the API returns `HTTP 404 Not Found` (due to external data purges, record expiration, or server-side sync issues):
- The reconciliation loop receives a non-200 response and logs a warning, but **leaves the job in the `ACCEPTED` state**.
- The job is never marked as `FAILED` or rescheduled, causing it to remain a permanent zombie record that is polled indefinitely.

### C. Lack of Outage Escalation & DLQ (Dead-Letter Queue)
When Pseudogram experiences a prolonged outage (hours/days), jobs in the queue accumulate with exponential backoffs.
- Once a job reaches `MAX_DM_ATTEMPTS` (default: 5), it transitions to `FAILED` permanently.
- The system has no notification system (Slack, Email, SMS) to alert operators of escalating delivery failure rates.
- There is no administrative dashboard or DLQ management interface to bulk-retry or review failed messages without writing raw SQL queries to manually reset job states.
