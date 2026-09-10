# 🛡️ CYBERGUARD — Backend

**AI-Powered Cyber Threat, Phishing & Digital Impersonation Detection and Response System**

FastAPI backend for CYBERGUARD: a multi-tenant, permission-matrix-gated threat detection platform with explainable AI, alerting, incident management, response automation and a SOC assistant — backed by **Supabase** (hosted PostgreSQL, Auth, Storage, Realtime) plus SQLAlchemy (async domain layer) and Redis/Arq (background analysis workers; graceful synchronous fallback without Redis).

**Author:** Chandan

## Overview

The backend exposes a versioned REST API (`/api/v1`) that ingests security events, runs them through transparent heuristic detectors, scores risk, generates LLM explanations through a timed provider chain (Groq 20 s → OpenRouter 60 s → local rule-based fallback), and persists alerts, incidents, response actions and a full audit trail in Supabase. The React frontend (`../frontend`) consumes the same API and streams new alerts over Supabase Realtime.

```
Ingestion → Heuristic Engine → Risk Scoring → XAI Gateway (Groq → OpenRouter → rule-based, circuit-broken) → Alert Generation → Dashboard
               └─ heavy media/bulk analysis may run on the Arq worker (Redis) instead of the request thread
```

- API reference: `docs/architecture.md` · Detection details: `docs/models.md`
- Deployment & scaling: `docs/deployment.md` · Evaluator walkthrough: `docs/demo_script.md`
- Datasets & ground truth: `docs/datasets.md`

## Features (6 detection modules)

| Module | Endpoint | Detects |
|---|---|---|
| **Phishing** | `POST /api/v1/analysis/email` | Lookalike sender domains, urgency, credential harvesting, malicious body URLs, SMS spam patterns (shortcodes, spam vocabulary, digit ratio, ALL-CAPS) |
| **Malicious URL** | `POST /api/v1/analysis/url` | IP hosts, suspicious TLDs, brand-in-subdomain, payload extensions, random high-entropy paths, URLhaus-style patterns |
| **Impersonation** | `POST /api/v1/analysis/impersonation` | CEO fraud / BEC: authority claims, pressure, unusual financial requests, secrecy demands |
| **Account takeover** | `POST /api/v1/analysis/account-takeover` | Failed-login bursts, impossible travel, unknown devices, success-after-failures |
| **Network / API abuse** | `POST /api/v1/analysis/network` | Data exfiltration (>10 MB flows), C2 ports (4444/8888/…), API rate abuse, 401 bursts |
| **Deepfake / media forensics** | `POST /api/v1/analysis/media` | ELA image forensics, frame-sampled video ELA, WAV signal statistics; non-WAV audio is clearly labelled simulated |

Plus the operational surface: multi-source raw ingestion (`/events/*`, including bulk batches), alert management with search and status transitions, incident lifecycle governed by a **strict NIST/SANS state machine** (TRIAGE → CONTAINMENT → ERADICATION → RECOVERY → CLOSED — illegal transitions are rejected with 400 before anything is written), approval-gated response execution, dashboard summary, audit logging, and the SOC assistant chat — with Supabase Realtime streaming new alerts to the UI. Everything is **organization-scoped** (Phase B) and **permission-matrix-gated** (Phase C-2), and heavy media/bulk analysis runs on background workers when Redis is available (Phase C-1).

## Architecture

```
React SPA ──JWT──> FastAPI (12 routers, /api/v1, permission-matrix-gated)
                      │ service role key          anon key + JWT
                      ├──> Supabase Postgres+RLS  ├──> Supabase Auth (token verification)
                      ├──> Supabase Storage       └──> frontend session (signInWithPassword)
                      ├──> SQLAlchemy async (org-scoped domain reads/writes)
                      ├──> LLM gateway (XAI: Groq 20s -> OpenRouter 60s -> rule-based, each remote provider behind an async circuit breaker)
                      └──> Redis (Arq queue) ──> background worker (media forensics, bulk logs)
Supabase Realtime ──new alert INSERTs──> Dashboard / Alerts pages
```

Full diagram, data flow and the security model (RLS, service role vs anon key, JWT): **[docs/architecture.md](docs/architecture.md)**.

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, pydantic / pydantic-settings, supabase-py (Auth / Storage / Realtime), SQLAlchemy 2.0 async + asyncpg (domain layer over the same Postgres), httpx (OpenRouter + Groq), arq + Redis (background workers), uvicorn
- **Database / Auth / Storage / Realtime:** Supabase (cloud) — schema in `db/schema.sql` with RLS on every table; domain reads/writes go through SQLAlchemy ORM sessions (`app/core/database.py`, `app/domain/`)
- **Media forensics:** Pillow (ELA), OpenCV (frame sampling), numpy (WAV signal statistics)
- **Frontend:** React 18, Vite 5, TypeScript (strict), Tailwind CSS, Zustand, Recharts, `@supabase/supabase-js`
- **Tooling:** docker compose, seeded dataset generators, offline evaluation harness

## Quick Start (Docker)

```bash
# one-time: create the Supabase project, run backend/db/schema.sql plus the
# idempotent migrations backend/db/migrations/0003_roles_and_seed.sql,
# 0004_multi_tenancy.sql, 0005_permissions.sql and
# 0006_org_bootstrap_guard.sql in the SQL editor, create the private bucket
# "cyberguard-media", and fill backend/.env
docker compose up --build        # redis + backend + frontend
# optional background worker (on the host or a dedicated container):
# cd backend && arq app.workers.settings.WorkerSettings
# backend  -> http://localhost:8000
# frontend -> http://localhost:3000
```

## Quick Start (Local)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # Supabase URL/keys; OpenRouter/Groq keys optional (explanations)
uvicorn app.main:app --reload --port 8000
# optional: docker compose up -d redis && arq app.workers.settings.WorkerSettings

cd ../frontend
npm install
npm run dev                     # http://localhost:5173 (VITE_USE_MOCK=false)
```

Then run the three mandatory demo scenarios end to end:

```bash
cd backend
python scripts/demo.py http://localhost:8000 <supabase_access_token>
```

The step-by-step evaluator guide (UI walkthrough + expected API responses) is in **[docs/demo_script.md](docs/demo_script.md)**.

## Evaluation Results

Offline evaluation of all six detection modules on held-out data (URLhaus, Cisco Umbrella and UCI SMS public data + seeded synthetic sets; no LLM or network calls during measurement) — heuristics-only vs hybrid (0.45/0.55 monotonic blend):

| Module | n | Heuristic F1 | Hybrid F1 |
|---|---|---|---|
| email_phishing | 24000 | 0.0268 | **0.9842** |
| url | 200 | 0.9189 | **1.0000** (held-out; small-sample caveat) |
| message (SMS proxy) | 600 | 0.6270 | 0.6826 |
| account_takeover | 60 | 0.8462 | 0.8462 (no trained model) |
| network | 60 | 0.8462 | 0.8148 |
| deepfake_image | 1000 | 0.6667 | 0.6667 |
| **Macro average** | | 0.6553 | **0.8324** |

Full methodology, per-module breakdowns and limitations: **[evidence/reports/evaluation.md](../evidence/reports/evaluation.md)** (machine-readable: `evaluation.json`; regenerate with `python scripts/evaluate.py`).

## Security Notes

- The **service role key** bypasses RLS and lives only in `backend/.env` — it is never exposed to the frontend and never committed.
- All protected routes verify the caller's Supabase JWT (`app/core/security.py`); every state-changing action is audit-logged.
- **Tenant isolation (Phase B):** every SELECT filters `org_id` and every INSERT carries it at the service layer — the primary enforcement, because the service-role client bypasses RLS. Unassigned users fall back to the Default Organization.
- **Permission matrix (Phase C-2):** roles resolve to granular permission keys (`role_permissions`, migration 0005); `require_permission(key)` returns 403 `Missing permission: <key>`. Destructive response execution additionally needs `response.execute_destructive`; closing an incident needs `incident.close`.
- RLS is enabled on all 11 tables (`db/schema.sql`) plus the `organizations`/`permissions` tables from migrations 0004/0005; approval-gated response actions return 403 without explicit human approval.

## Enterprise Upgrade (Phases A–C)

- **SQLAlchemy domain layer** (`app/domain/`): ORM models for `incidents`, `incident_events`, `alerts` and the `incident_alerts` junction, mapped to the existing Supabase tables. Engine: async asyncpg, `pool_pre_ping`, `pool_size=10`, `max_overflow=20`. The supabase-py client is unchanged and still owns Auth, Storage and Realtime.
- **Strict incident state machine** (`app/domain/incident_lifecycle.py`): `TRIAGE → CONTAINMENT → ERADICATION → RECOVERY → CLOSED`, plus TRIAGE→CLOSED (false positive) and CONTAINMENT→TRIAGE (escalate back). `PATCH /incidents/{id}/status` validates the transition via SQLAlchemy *before* committing, so an analyst cannot close an incident that is still in containment (400 with an explanatory message). Legacy statuses (`open`/`investigating`/`contained`/`closed`) are accepted and normalized.
- **Async circuit breaker** (`app/ai/async_circuit_breaker.py`): a custom coroutine-safe breaker (CLOSED/OPEN/HALF_OPEN, threshold 3, 60 s recovery) wraps each remote LLM provider. When a provider is failing, its breaker opens and the gateway skips it instantly — an LLM outage can never hang the API; worst case is an immediate fall-through to the rule-based explanation.

> **One-time DB steps:** run `db/migrations/0003_roles_and_seed.sql`, `0004_multi_tenancy.sql`, `0005_permissions.sql` and `0006_org_bootstrap_guard.sql` (in that order, after `db/schema.sql`), then widen the `incident_status` enum (`ALTER TYPE incident_status ADD VALUE IF NOT EXISTS 'TRIAGE';` etc. — see `docs/deployment.md`). Until then the API reads legacy rows fine, accepts legacy status values, scopes to the Default Organization and serves the permission matrix from code.

- **Phase B — multi-tenancy:** `organizations` table + `org_id` on profiles/events/alerts/incidents/audit_logs (migration 0004); every service SELECT filters by the caller's org and every INSERT tags it; `get_user_org_id` resolves the tenant with a 5-minute cache and Default Organization fallback so new signups never crash.
- **Phase C-1 — background workers:** deepfake media and bulk log analysis (`POST /events/bulk`) run on an Arq worker via Redis (202 Accepted immediately); without Redis, or with `BACKGROUND_WORKERS_ENABLED=false`, the identical pipeline runs synchronously (200). Jobs are idempotent and org-scoped.
- **Phase C-2 — permission matrix:** 16 granular permission keys seeded per role (viewer: views only; analyst: + analysis/media/incidents/alerts/safe responses/audit; admin: + destructive responses/user management). `/auth/me` returns the caller's permission list, which the frontend uses via `can(key)`; the Sidebar hides User Management without `users.manage` and the destructive execute button is disabled without `response.execute_destructive`.
