# Loom Script — LinkPlease Walkthrough (3 Minutes)

> **Format:** Verbatim spoken script with on-screen cues.  
> **Target length:** ~420 words spoken at 140 wpm = ~3 minutes.  
> **Screen:** Split — terminal left, browser (Swagger/Dashboard) right.

---

## [00:00 – 00:20] — Hook

> *(Open on the architecture diagram in README.md)*

"This is LinkPlease. It's a production-grade FastAPI backend that automates Instagram DMs based on comment keywords. A creator sets a rule: anyone who comments 'PRICE' gets a DM with a price list link. Sounds simple. The reliability engineering to make it actually work — at scale, with an intentionally flaky API, with duplicate webhooks, with restarts — is anything but."

---

## [00:20 – 00:50] — Architecture in 30 Seconds

> *(Switch to terminal. Run: `uvicorn app.main:app --reload --port 8000`)*

"Here's what happens end-to-end. A webhook hits `POST /webhook`. In under 50 milliseconds, we validate the HMAC signature, persist the event to SQLite with a unique constraint on the event ID — so duplicates are rejected at the database level — and return 200 OK. We don't block on any external API call."

> *(Open browser → `http://localhost:8000/health`)*

"The background worker wakes up every second, claims pending jobs atomically, and sends DMs through the Pseudogram API — our mock Instagram — while enforcing a strict 10-requests-per-60-seconds sliding window. It handles 202 Accepted, 429 Rate Limited, 500 transient errors, and 400 permanent failures, each with different retry strategies."

---

## [00:50 – 01:40] — Live Demonstration

> *(Switch to Swagger UI at `http://localhost:8000/docs`)*

"Let me show you the full flow live."

> *(POST /rules — keyword: 'PRICE', dm_message: 'Here is our price list: https://example.com/pricing')*

"First, create a rule. Keyword 'PRICE', DM message with the link."

> *(POST /webhook — paste a comment.created payload with text: 'Can you send me the PRICE please?')*

"Now simulate a comment arriving. Event ID, comment text containing PRICE, from user 123."

> *(GET /stats)*

"Within one second, the worker picks it up. Stats show one queued job. Give it another second — the Pseudogram API accepts it — now it's in accepted state. The reconciliation loop polls delivery status. Once confirmed delivered, it flips to delivered."

> *(POST /webhook — same event ID again)*

"Now send the exact same webhook again — simulating Pseudogram retrying delivery. Returns 200. But nothing is created. The event_id already exists in the database. Zero duplicate jobs. Zero duplicate DMs."

---

## [01:40 – 02:20] — Reliability Internals

> *(Open `app/workers/dm_worker.py`)*

"The worker uses two reliability mechanisms most engineers skip. First: on every startup, it scans for jobs stuck in `sending` state — meaning we crashed mid-send last time — and resets them to retry. Second: every external API call includes an `Idempotency-Key` header tied to the internal job ID. So if we retry after a crash, Pseudogram returns the original response instead of sending a second DM."

> *(Open `app/services/rate_limiter.py`)*

"The rate limiter is a sliding window, not a fixed bucket. It tracks actual timestamps of every sent DM. If we hit 10 in the last 60 seconds, we sleep exactly long enough for the oldest timestamp to fall out of the window. It also respects Retry-After headers from 429 responses."

---

## [02:20 – 02:45] — Test Suite

> *(Terminal: `pytest -v`)*

"Twelve automated tests covering every failure path: 500 retries, 429 backoff, 400 permanent failures, 202-to-delivered reconciliation, concurrent duplicate blocking, comment deletion cancellation, signature validation, and process restart recovery. All green."

---

## [02:45 – 03:00] — Close

"The FAILURES.md documents twelve edge cases this system does not perfectly handle — including rate limiter state loss on restart, jobs stuck in accepted forever, and the default deploy shipping with signature verification off. I'll walk through those in the next recording."

> *(End screen — show `GET /stats` with real numbers)*

---

*End of script. Total estimated runtime: 2:55 – 3:05 depending on live demo pacing.*
