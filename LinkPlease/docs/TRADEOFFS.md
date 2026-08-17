# Technical Tradeoffs — LinkPlease

> Every architectural decision is a tradeoff. This document names them honestly, without pretending the chosen approach is universally correct.

---

## 1. SQLite vs. PostgreSQL

### Decision: SQLite with WAL mode (default)

| Dimension | SQLite | PostgreSQL |
|---|---|---|
| Setup complexity | Zero — file on disk | Requires a DB server or managed service |
| Concurrent writes | Serialised through WAL, ~200–500 writes/sec | True concurrent writers, thousands of writes/sec |
| Async driver | `aiosqlite` (thread pool wrapper) | `asyncpg` (native async) |
| Connection pooling | Not needed | Required (pgBouncer or SQLAlchemy pool) |
| Production readiness | Fine for single-container, low-to-medium traffic | Required for multi-worker or high-traffic |
| Data loss risk | Single file — one disk failure loses everything | Replication, WAL shipping, point-in-time recovery |

**Why SQLite was chosen:**
Single-container deployment on Render's free tier has no persistent external database. SQLite with WAL enables non-blocking reads while writes are in progress, covering the concurrent-webhook use case adequately at low scale.

**When this breaks:**
Above ~50 concurrent webhook requests/second, SQLite's serialised write lock becomes the bottleneck. The `busy_timeout=5000` prevents immediate failure but degrades response times to seconds.

**Migration path:**
Change `DATABASE_URL` to `postgresql+asyncpg://...`. SQLAlchemy's ORM-level code is 100% database-agnostic. No application code changes required.

---

## 2. In-Process Rate Limiter vs. Redis Distributed Rate Limiter

### Decision: In-process sliding window (`collections.deque`)

| Dimension | In-Process | Redis (sorted set or INCR+EXPIRE) |
|---|---|---|
| External dependency | None | Requires Redis instance |
| State persistence on restart | ❌ Lost on every restart | ✅ Survives restarts |
| Multi-worker support | ❌ Each process has independent state | ✅ Shared across all workers |
| Latency | ~0 microseconds | ~0.5–2ms per operation |
| Failure mode | Loses window state on crash | Redis outage blocks all sends |

**Why in-process was chosen:**
No Redis infrastructure exists or is needed for single-process deployment. Adding Redis for rate limiting alone introduces significant operational overhead (provisioning, monitoring, connection management, failure handling).

**When this breaks:**
On every server restart, the sliding window resets. If the server restarts 30 seconds into a 60-second window after 9 sends, the new process can immediately send 10 more — delivering 19 DMs in the rate-limit window. This can trigger Pseudogram's server-side rate limiting and 429 responses.

---

## 3. Database-Polling Worker vs. Message Queue (Redis/RabbitMQ/SQS)

### Decision: 1-second SQLite polling loop

| Dimension | DB Polling | Message Queue |
|---|---|---|
| Infrastructure dependencies | None (reuses existing DB) | Requires Broker (Redis/RabbitMQ/SQS) |
| Message delivery guarantee | DB row = durable record | Depends on queue durability config |
| Latency | 0–1 second (poll interval) | Sub-100ms |
| Worker scaling | Single-process safe | Supports horizontal scaling |
| Dead letter handling | Manual DB query | Native DLQ support |
| Visibility into queue depth | Direct DB query | Broker metrics |

**Why polling was chosen:**
The Pseudogram API enforces 10 DMs/60 seconds. At that throughput, sub-second latency has zero practical benefit. A message queue would add infrastructure complexity with no measurable user benefit. DB polling also provides a built-in audit trail — every job's history is queryable in SQLite.

**When this breaks:**
Polling at 1-second intervals means worst-case 1-second delay per DM dispatch. Under Render's free-tier sleep, the server cold-starts in 10–30 seconds, during which no polling happens.

---

## 4. HTTP Status Polling for Delivery Confirmation vs. Outbound Webhook Callback

### Decision: Polling `GET /v1/dm/{dm_id}` every second

| Dimension | Polling | Callback Webhook |
|---|---|---|
| Infrastructure | None extra | Requires Pseudogram to call back to us |
| Delivery confirmation latency | 0–1 second | Near-instant |
| API rate limit consumption | Consumes GET budget | Zero budget usage |
| Failure mode | Stuck in `accepted` if Pseudogram loses the record | Missed if our server is down during callback |

**Why polling was chosen:**
The Pseudogram mock API provides a `GET /v1/dm/{dm_id}` endpoint. Using it requires no additional Pseudogram configuration. A callback approach would require Pseudogram to know our public URL — introducing chicken-and-egg registration complexity.

**Cost:**
Each reconciliation cycle polls all `accepted` jobs. With 100 accepted jobs and a 1-second poll interval, this generates 100 GET requests/second against Pseudogram — potentially consuming its own rate limit budget.

---

## 5. HMAC-SHA256 Signature Verification — Default Off

### Decision: `WEBHOOK_SIGNATURE_REQUIRED=false` in default config

**Why:**
During development and initial testing with the Pseudogram mock, the `X-PseudoGram-Signature` header is not sent. Requiring it by default would cause every development test to fail until the developer manually computes and passes signatures.

**Risk:**
Any production deployment using `render.yaml` as-is ships with an open, unauthenticated webhook endpoint. A hostile actor can trigger arbitrary DM sends to any `user_id`.

**The correct production posture:**
```
WEBHOOK_SIGNATURE_REQUIRED=true
PSEUDOGRAM_API_KEY=<your_secret_key>
```
This was documented in README but not enforced by default.

---

## 6. Synchronous Event Persistence vs. Fire-and-Forget

### Decision: Webhook handler persists event synchronously before returning 200

**Why:**
If we returned 200 before persisting the event and the process crashed immediately after, the event would be silently lost. Pseudogram would not retry because it received a 200 success response. Synchronous persistence is the correct choice for guaranteed processing.

**Cost:**
Every webhook request incurs a full database write round-trip before responding. This adds ~2–10ms on SQLite, ~1–5ms on local PostgreSQL, ~10–50ms on a remote managed DB.

**The alternative (wrong for this use case):**
Background queuing + immediate 200 — used in high-throughput systems where event loss is acceptable or recoverable. Not suitable here where every comment is a potential revenue-generating DM.
