# CYBERGUARD Deployment & Scalability

## 1. Local Development Setup

Prerequisites: Python 3.11+, Node 18+, a Supabase project (section 3).

```bash
# --- Backend ---
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then fill in the values from section 4
# one-time: execute db/schema.sql in the Supabase SQL editor (see section 3)
uvicorn app.main:app --reload --port 8000
# interactive API docs: http://localhost:8000/docs

# --- Frontend (second terminal) ---
cd frontend
npm install
# .env already contains VITE_* values; adjust VITE_API_BASE_URL if needed
npm run dev                        # http://localhost:5173
```

Optional (evaluation harness):

```bash
cd backend && source .venv/bin/activate
python scripts/fetch_datasets.py            # downloads URLhaus / Umbrella / UCI SMS
python scripts/generate_synthetic_datasets.py
python scripts/evaluate.py                  # writes evidence/reports/evaluation.{md,json}
```

## 2. Docker Compose Setup

`docker-compose.yml` (project root) starts the two stateless services:

```bash
docker compose up --build
# backend  -> http://localhost:8000  (FastAPI, uvicorn)
# frontend -> http://localhost:3000  (Nginx serving the built SPA)
```

- **backend**: builds `backend/Dockerfile` (python:3.11-slim), loads secrets from `backend/.env` via `env_file`, publishes 8000.
- **frontend**: multi-stage `frontend/Dockerfile` (Node build → Nginx on port 80, mapped to 3000) with SPA fallback routing; `VITE_*` values are injected as build args because Vite bakes them in at build time.
- **Supabase is external and cloud-hosted** — nothing database/auth/storage related runs in Compose; both services are stateless and can be scaled/restarted freely.
- Both services share the `cyberguard-net` bridge network.

## 3. Background Workers (Phase C-1)

Heavy analysis — deepfake media forensics and bulk log ingestion — runs off
the request thread on an Arq worker backed by Redis. The API enqueues the job
and answers `202 Accepted` immediately; the alert still lands in Supabase and
reaches the dashboard via Realtime.

**Start Redis** (one command):

```bash
docker compose up -d redis          # redis:7-alpine on localhost:6379
```

**Start the worker** (in a second terminal, from `backend/` with the venv active):

```bash
arq app.workers.settings.WorkerSettings
```

The worker registers two jobs (`job_analyze_media`, `job_analyze_bulk_logs`),
runs up to 4 jobs concurrently (`max_jobs=4`) with a 300 s per-job timeout.

**Graceful synchronous fallback** — the system degrades, never breaks:

| Situation | Behaviour |
|---|---|
| Redis up, worker running | `202 Accepted`; job executes in the background |
| Redis up, worker stopped | `202 Accepted`; job waits in the queue until a worker starts |
| Redis unreachable | API logs `Worker queue unavailable, caller must run synchronously` and processes the request inline, answering `200` exactly as before Phase C-1 |
| `BACKGROUND_WORKERS_ENABLED=false` | Queue is never consulted; everything runs synchronously (200) |

Environment variables: `REDIS_URL` (default `redis://localhost:6379`) and
`BACKGROUND_WORKERS_ENABLED` (default `true`), both documented in section 5.

## 4. Supabase Cloud Configuration (one-time)

1. **Create the project** at [supabase.com](https://supabase.com); note the project URL.
2. **Schema**: open *SQL editor* and execute `backend/db/schema.sql` (creates 7 enums, 11 tables, indexes, RLS policies, the `handle_new_user` trigger and the 10-row `response_catalog` seed).
   Then run the idempotent migrations, in order (each is safe to re-run):
   - `backend/db/migrations/0004_multi_tenancy.sql` — `organizations` table, `org_id` on profiles/events/alerts/incidents/audit_logs, Default Organization backfill (all existing demo data stays visible) and the updated `handle_new_user` trigger.
   - `backend/db/migrations/0005_permissions.sql` — `permissions` + `role_permissions` matrix seeded with the 16 granular permission keys for viewer/analyst/admin.
   Finally widen the incident status enum for the Phase A NIST/SANS lifecycle (one-time):
   ```sql
   ALTER TYPE incident_status ADD VALUE IF NOT EXISTS 'TRIAGE';
   ALTER TYPE incident_status ADD VALUE IF NOT EXISTS 'CONTAINMENT';
   ALTER TYPE incident_status ADD VALUE IF NOT EXISTS 'ERADICATION';
   ALTER TYPE incident_status ADD VALUE IF NOT EXISTS 'RECOVERY';
   ALTER TYPE incident_status ADD VALUE IF NOT EXISTS 'CLOSED';
   ```
   Until 0004/0005 are applied the backend still runs: org scoping falls back to
   the Default Organization and the permission matrix falls back to the
   same matrix hardcoded in `app/core/security.py`.
3. **Realtime**: enable streaming for alert inserts —
   `alter publication supabase_realtime add table alerts;`
4. **Storage**: create a **private** bucket named `cyberguard-media` (Storage → New bucket → Private).
5. **Auth**: create at least one user (e.g. `admin@cyberguard.local`) under *Authentication → Users*. The `handle_new_user` trigger auto-creates the matching `profiles` row.
6. **Keys**: copy the Project URL, **anon** key and **service role** key from *Project Settings → API*.

## 5. Environment Variables

Backend (`backend/.env`, loaded by `app/core/config.py`):

| Variable | Purpose |
|---|---|
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_ANON_KEY` | Public anon key — used **only** to verify user JWTs (`app/core/security.py`) |
| `SUPABASE_SERVICE_ROLE_KEY` | Privileged key — all DB/storage writes; **backend-only, never commit** |
| `API_V1_PREFIX` | Route prefix (default `/api/v1`) |
| `CORS_ORIGINS` | Comma-separated allowed browser origins |
| `OPENROUTER_API_KEY` | OpenRouter key; empty makes the gateway skip OpenRouter |
| `OPENROUTER_MODEL` | Model id (default `meta-llama/llama-3.1-8b-instruct:free`) |
| `OPENROUTER_TIMEOUT_SECONDS` | OpenRouter call timeout in seconds (default `100`) |
| `GROQ_API_KEY` | Groq key; empty skips Groq and falls through to the rule-based explanation |
| `GROQ_MODEL` | Groq model id (default `llama-3.1-8b-instant`) |
| `GROQ_TIMEOUT_SECONDS` | Groq call timeout in seconds (default `60`) |
| `DATABASE_URL` | Async SQLAlchemy connection for the domain layer (`postgresql+asyncpg://...`, default local Supabase Postgres `localhost:54322`). A driver-less `postgresql://` value is rewritten to `postgresql+asyncpg://` automatically. Does **not** replace supabase-py (Auth/Storage/Realtime) |

Frontend (`frontend/.env`, Vite build-time):

| Variable | Purpose |
|---|---|
| `VITE_USE_MOCK` | `false` = live backend + Supabase Auth; anything else = self-contained mock mode |
| `VITE_API_BASE_URL` | Backend base URL (e.g. `http://localhost:8000/api/v1`) |
| `VITE_SUPABASE_URL` | Supabase project URL (browser client) |
| `VITE_SUPABASE_ANON_KEY` | Anon key only — the service role key must never appear in the frontend |

## 6. Scalability Notes

**Backend (stateless by design)**
- The FastAPI app holds no in-process state beyond cached singletons (settings, Supabase clients, the SQLAlchemy engine), the in-memory explanation cache (bounded to 256 entries) and per-provider circuit breaker state, so it scales horizontally: run multiple uvicorn workers (`--workers 4`) or replicas behind any load balancer. All shared state lives in Supabase.
- The SQLAlchemy engine pools connections (`pool_pre_ping`, `pool_size=10`, `max_overflow=20`) so bursty dashboard/incident traffic reuses a bounded connection set — pair `--workers N` with the Postgres/Supavisor connection limit when scaling out.
- Heuristic detectors are pure CPU functions measured at **< 10 ms p95** on the evaluation set (`evidence/reports/evaluation.json`); the dominant latency is the LLM explanation, now bounded twice over: per-provider timeouts plus the async circuit breakers (`app/ai/async_circuit_breaker.py`). After 3 consecutive provider failures the breaker opens for 60 s and the gateway skips that provider instantly, so a sustained LLM outage costs zero added latency (immediate rule-based fallback).
- Long-running media forensics (video frame sampling) and bulk log analysis already run off the request thread on the Arq worker when Redis is available (section 3), with synchronous fallback otherwise; further CPU-heavy work can follow the same pattern.

**Supabase (managed, auto-scaled control plane)**
- Postgres instances scale vertically via project tiers; connection pooling (Supavisor/pgBouncer) absorbs bursty read traffic from the dashboard aggregation endpoint, which deliberately does Python-side grouping over bounded result sets.
- Storage and Auth are managed services and scale transparently.
- Realtime broadcast fan-out for the `alerts` table is handled by Supabase Realtime; clients self-subscribe to the `cyberguard-alerts` channel, so additional frontend replicas need no coordination.
- Database scaling path: read replicas for dashboard queries, partitioning `events`/`audit_logs` by `created_at`, and moving hot aggregates into materialized views if row counts grow beyond the prototype's assumptions.

**Frontend**
- The SPA is served by Nginx from immutable build assets — scale by adding replicas/CDN in front of it; there is no server-side session state (Supabase JWTs live in the browser).
