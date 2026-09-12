# CYBERGUARD Deployment & Scalability

## 1. Local Development Setup

Prerequisites: Python 3.11+, Node 18+, a Supabase project (section 4), and optionally Docker.

```bash
# --- Backend ---
cd backend
uv sync
cp .env.example .env               # then fill in the values from section 5
# one-time: run the SQL files in the Supabase SQL editor (see section 4)
uv run uvicorn app.main:app --reload --port 8000
# interactive API docs: http://localhost:8000/docs

# --- Frontend (second terminal) ---
cd frontend
npm install
cp .env.example .env               # fill in VITE_SUPABASE_* + VITE_API_BASE_URL
npm run dev                        # http://localhost:5173
```

Optional (evaluation harness):

```bash
cd backend
uv run python scripts/fetch_datasets.py            # downloads URLhaus / Umbrella / UCI SMS
uv run python scripts/generate_synthetic_datasets.py
uv run python scripts/evaluate.py                  # writes evidence/reports/evaluation.{md,json}

ML pipeline scripts launch canonically as modules (both
`uv run python -m ml.<module>` and `uv run python ml/<module>.py` work —
every script bootstraps `backend/` onto `sys.path`):

uv run python -m ml.fetch_data              # raw dataset download
uv run python -m ml.train_models            # email/url/network models
```

## 2. Analysis execution model (synchronous)

The background worker queue (Arq + Redis) and the per-request rate limiter were **removed** from the codebase: heavy analysis — deepfake media forensics and bulk log ingestion — now always runs synchronously on the request thread and the API answers `200` with the finished result (the `202 Accepted` queue path no longer exists).

> **Phase D-1 rule (unchanged):** blocking IO never runs on the event loop; all supabase-py and media forensics calls execute in the threadpool (`app/core/asyncbridge.to_thread` or plain `def` routes).

The `redis` service remains in `docker-compose.yml` (and the `redis`/`arq` packages in `pyproject.toml`) as standalone infrastructure for local tooling — the application itself no longer depends on them.

## 3. Docker Compose Setup

`docker-compose.yml` (project root) starts three services:

```bash
docker compose up --build
# redis    -> localhost:6379   (standalone local infrastructure; app no longer uses it)
# backend  -> http://localhost:8000  (FastAPI, uvicorn)
# frontend -> http://localhost:3000  (Nginx serving the built SPA)
```

- **redis**: `redis:7-alpine` with a `redis-cli ping` healthcheck; the backend waits for it to be healthy.
- **backend**: builds `backend/Dockerfile` (python:3.11-slim), loads secrets from `backend/.env` via `env_file`, publishes 8000, healthchecked against `GET /api/v1/health`.
- **frontend**: multi-stage `frontend/Dockerfile` (Node build → Nginx on port 80, mapped to 3000) with SPA fallback routing; `VITE_*` values are injected as build args because Vite bakes them in at build time.
- **Supabase is external and cloud-hosted** — nothing database/auth/storage related runs in Compose; the stateless services scale/restart freely. All services share the `cyberguard-net` bridge network.

## 4. Supabase Cloud Configuration (one-time)

1. **Create the project** at [supabase.com](https://supabase.com); note the project URL.
2. **Schema + migrations**: open the *SQL editor* and run the following, **in order** (all idempotent — safe to re-run):

   | Order | File | Purpose (one line) |
   |---|---|---|
   | 1 | `backend/db/schema.sql` | Base schema (acts as migration 0001): 7 enum types, 11 tables, indexes, RLS policies, the `handle_new_user` trigger and the 10-row `response_catalog` seed |
   | 2 | `backend/db/migrations/0003_roles_and_seed.sql` | Default role `viewer` on signup, `profiles.email` column, and idempotent seeding of the three demo roles |
   | 3 | `backend/db/migrations/0004_multi_tenancy.sql` | `organizations` table + `org_id` on profiles/events/alerts/incidents/audit_logs, backfill to the Default Organization, org_id indexes, updated signup trigger |
   | 4 | `backend/db/migrations/0005_permissions.sql` | `permissions` + `role_permissions` matrix seeded with the 16 granular permission keys for viewer/analyst/admin |
   | 5 | `backend/db/migrations/0006_org_bootstrap_guard.sql` | Signup trigger guard: the Default Organization row is created on demand, so a new signup can never get a NULL `org_id` |

   > The repository contains **no `0002` file** — the base schema lives in `db/schema.sql` and the numbered migration sequence starts at `0003`. Run them in the order above.

   Then widen the incident status enum for the Phase A NIST/SANS lifecycle (one-time):
   ```sql
   ALTER TYPE incident_status ADD VALUE IF NOT EXISTS 'TRIAGE';
   ALTER TYPE incident_status ADD VALUE IF NOT EXISTS 'CONTAINMENT';
   ALTER TYPE incident_status ADD VALUE IF NOT EXISTS 'ERADICATION';
   ALTER TYPE incident_status ADD VALUE IF NOT EXISTS 'RECOVERY';
   ALTER TYPE incident_status ADD VALUE IF NOT EXISTS 'CLOSED';
   ```
   Until 0003–0006 are applied the backend still runs: org scoping falls back to the Default Organization and the permission matrix falls back to the same matrix hardcoded in `app/core/security.py`.
3. **Realtime**: enable streaming for alert inserts —
   `alter publication supabase_realtime add table alerts;`
4. **Storage**: create a **private** bucket named `cyberguard-media` (Storage → New bucket → Private).
5. **Auth**: create the three demo users under *Authentication → Users → Add user* — `admin@cyberguard.local`, `analyst@cyberguard.local`, `viewer@cyberguard.local` (passwords of your choice). The `handle_new_user` trigger auto-creates their profiles; migration 0003 assigns their roles.
6. **Keys**: copy the Project URL, **anon** key and **service role** key from *Project Settings → API*.

## 5. Environment Variables

Backend (`backend/.env`, loaded by `app/core/config.py`):

| Variable | Purpose | Default |
|---|---|---|
| `SUPABASE_URL` | Supabase project URL | — (required) |
| `SUPABASE_ANON_KEY` | Public anon key — used **only** to verify user JWTs (`app/core/security.py`) | — (required) |
| `SUPABASE_SERVICE_ROLE_KEY` | Privileged key — all DB/storage writes; **backend-only, never commit** | — (required) |
| `DATABASE_URL` | Async SQLAlchemy connection for the incident domain layer (`postgresql+asyncpg://…`); a driver-less `postgresql://` value is rewritten automatically. Does **not** replace supabase-py (Auth/Storage/Realtime) | `postgresql+asyncpg://postgres:postgres@localhost:54322/postgres` |
| `GROQ_API_KEY` | Groq key; empty skips Groq in the provider chain | `""` |
| `GROQ_MODEL` | Groq model id | `qwen/qwen3.8-27b` |
| `GROQ_TIMEOUT_SECONDS` | Groq call timeout in seconds (first provider in the chain) | `15` |
| `OPENROUTER_API_KEY` | OpenRouter key; empty skips OpenRouter | `""` |
| `OPENROUTER_MODEL` | Model id | `liquid/lfm-2.5-2.6b:free` |
| `OPENROUTER_TIMEOUT_SECONDS` | OpenRouter call timeout in seconds (second provider) | `20` |
| `ML_ENABLED` | Toggles trained-model inference (heuristics-only when false) | `true` |
| `ML_MODELS_DIR` | Trained-artifact directory | `ml/models` |
| `API_V1_PREFIX` | Route prefix | `/api/v1` |
| `CORS_ORIGINS` | Comma-separated allowed browser origins (`*` is rejected at boot while credentials are enabled) | `http://localhost:5173,http://localhost:3000` |

Frontend (`frontend/.env`, Vite build-time):

| Variable | Purpose | Default |
|---|---|---|
| `VITE_USE_MOCK` | `false` = live backend + Supabase Auth; anything else = self-contained mock mode | `false` |
| `VITE_API_BASE_URL` | Backend base URL (e.g. `http://localhost:8000/api/v1`) | `http://localhost:8000/api/v1` |
| `VITE_SUPABASE_URL` | Supabase project URL (browser client) | — |
| `VITE_SUPABASE_ANON_KEY` | Anon key only — the service role key must never appear in the frontend | — |

## 6. Scalability Approach

**Backend (stateless by design)**
- The FastAPI app holds no in-process state beyond cached singletons (settings, Supabase clients, the SQLAlchemy engine), the in-memory explanation cache (bounded to 256 entries) and per-provider circuit-breaker state, so it scales horizontally: run multiple uvicorn workers (`--workers 4`) or replicas behind any load balancer. All shared state lives in Supabase.
- **Pool sizes:** the SQLAlchemy engine pools connections (`pool_pre_ping`, `pool_size=10`, `max_overflow=20`) so bursty incident traffic reuses a bounded connection set — pair `--workers N` with the Postgres/Supavisor connection limit when scaling out. (The Arq worker was removed; analysis runs in-process — scale by running more uvicorn workers.)
- Heuristic detectors are pure CPU functions measured at **< 10 ms p95** on the evaluation set (`evidence/reports/evaluation.json`); the dominant latency is the LLM explanation, bounded twice over: per-provider timeouts plus the async circuit breakers. After 3 consecutive provider failures a breaker opens for 60 s and the gateway skips that provider instantly.
- Long-running media forensics and bulk log analysis run synchronously on the request thread (section 2) with all blocking IO in the threadpool; further CPU-heavy work should follow the same pattern.
- **Supabase pooler:** when scaling to many backend workers, connect `DATABASE_URL` through Supabase's connection pooler (Supavisor, port 6543 transaction mode / 5432 session mode) instead of the direct Postgres port, and size `pool_size` × workers within the pooler's client limit.

**Supabase (managed, auto-scaled control plane)**
- Postgres instances scale vertically via project tiers; the connection pooler (Supavisor/pgBouncer) absorbs bursty read traffic from the dashboard aggregation endpoint, which deliberately does Python-side grouping over bounded result sets.
- Storage and Auth are managed services and scale transparently.
- Realtime broadcast fan-out for the `alerts` table is handled by Supabase Realtime; clients self-subscribe to the `cyberguard-alerts` channel, so additional frontend replicas need no coordination.
- Database scaling path: read replicas for dashboard queries, partitioning `events`/`audit_logs` by `created_at`, and moving hot aggregates into materialized views if row counts grow beyond the prototype's assumptions.

**Frontend**
- The SPA is served by Nginx from immutable build assets — scale by adding replicas/CDN in front of it; there is no server-side session state (Supabase JWTs live in the browser).

**Backup**
- Database, Auth and Storage data live in the Supabase project and are covered by Supabase's managed backups (scheduled backups/PITR per project tier; manual backups via `supabase db dump` or *Database → Backups* in the dashboard). The only durable local artifact the backend writes is the audit fallback log (`evidence/logs/audit_fallback.jsonl`) — include `evidence/` and the git-tracked repository (code, migrations, ML artifacts, reports) in any off-Supabase backup routine.

## 7. Hardening Notes (Phase D-2)

- **Rate limiting (removed):** the Phase D-1 token-bucket middleware
  (`app/core/rate_limit.py`, `RATE_LIMIT_RPM`, `429` + `Retry-After`) was
  removed — requests are no longer throttled.
- **CORS boot guard:** the API refuses to boot when `CORS_ORIGINS` contains
  `*` while `allow_credentials` is enabled
  (`RuntimeError: CORS_ORIGINS must not contain '*' while allow_credentials is True`).
- **Threadpool rule:** blocking IO never runs on the event loop; all
  supabase-py and media forensics calls execute in the threadpool
  (`app/core/asyncbridge.to_thread`, or plain `def` routes).
- **Audit durability:** a failed audit write is retried once; if the retry
  also fails, the record is appended to `evidence/logs/audit_fallback.jsonl`
  (user, action, resource, details, timestamp, error) and an error is logged —
  audit rows are never lost silently.
- **Cache TTLs and invalidation:** verified auth context (sha256 of bearer
  token) 60 s; profile role 60 s; role permission matrix 60 s; user
  organization 5 min (LRU, maxsize 1024). All user-scoped caches are cleared
  by `invalidate_user(user_id)` immediately after an admin changes that
  user's role (`PATCH /admin/users/{id}/role`).
- **Bulk ingestion cap:** `POST /events/bulk` accepts at most 1000 rows per
  batch; larger batches answer `400 "Bulk batch exceeds 1000 rows"`.
- **Circuit breakers:** one `AsyncCircuitBreaker` per remote LLM provider —
  failure threshold 3 consecutive failures, 60 s recovery window,
  CLOSED/OPEN/HALF_OPEN; an OPEN breaker is skipped instantly.
- **LLM provider chain timeouts:** Groq `GROQ_TIMEOUT_SECONDS` (default 15 s)
  → OpenRouter `OPENROUTER_TIMEOUT_SECONDS` (default 20 s) → local rule-based
  template (instant). Background jobs additionally cap at `job_timeout=300`.
- **Health probes:** `GET /api/v1/health` never performs a Supabase
  round-trip per call (30-second cached connectivity) so container
  healthchecks and load-balancer probes cannot be throttled or slowed;
  `GET /api/v1/health/deep` is the authenticated live-round-trip variant.
- **Dependency pins:** `backend/requirements.txt` pins the exact runtime
  dependency versions from the working venv (Phase D-2, item 6).
