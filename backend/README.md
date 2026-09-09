# 🛡️ CYBERGUARD — Backend

**AI-Powered Cyber Threat, Phishing & Digital Impersonation Detection and Response System**

FastAPI backend for CYBERGUARD: a multi-source threat detection platform with explainable AI, alerting, incident management, response automation and a SOC assistant — backed entirely by **Supabase** (hosted PostgreSQL, Auth, Storage, Realtime). No local PostgreSQL, Redis, Celery or MinIO.

**Author:** Chandan

## Overview

The backend exposes a versioned REST API (`/api/v1`) that ingests security events, runs them through transparent heuristic detectors, scores risk, generates LLM explanations through a timed provider chain (OpenRouter → Groq → local rule-based fallback), and persists alerts, incidents, response actions and a full audit trail in Supabase. The React frontend (`../frontend`) consumes the same API and streams new alerts over Supabase Realtime.

```
Ingestion → Heuristic Engine → Risk Scoring → XAI Gateway (OpenRouter → Groq → rule-based) → Alert Generation → Dashboard
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

Plus the operational surface: multi-source raw ingestion (`/events/*`), alert management with search and status transitions, incident lifecycle governed by a **strict NIST/SANS state machine** (TRIAGE → CONTAINMENT → ERADICATION → RECOVERY → CLOSED — illegal transitions are rejected with 400 before anything is written), approval-gated response execution, dashboard summary, audit logging, and the SOC assistant chat — with Supabase Realtime streaming new alerts to the UI.

## Architecture

```
React SPA ──JWT──> FastAPI (11 routers, /api/v1)
                      │ service role key          anon key + JWT
                      ├──> Supabase Postgres+RLS  ├──> Supabase Auth (token verification)
                      ├──> Supabase Storage       └──> frontend session (signInWithPassword)
                      └──> LLM gateway (XAI: OpenRouter -> Groq -> rule-based, each remote provider behind an async circuit breaker)
Supabase Realtime ──new alert INSERTs──> Dashboard / Alerts pages
```

Full diagram, data flow and the security model (RLS, service role vs anon key, JWT): **[docs/architecture.md](docs/architecture.md)**.

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, pydantic / pydantic-settings, supabase-py (Auth / Storage / Realtime), SQLAlchemy 2.0 async + asyncpg (domain layer over the same Postgres), httpx (OpenRouter + Groq), uvicorn
- **Database / Auth / Storage / Realtime:** Supabase (cloud) — schema in `db/schema.sql` with RLS on every table; domain reads/writes go through SQLAlchemy ORM sessions (`app/core/database.py`, `app/domain/`)
- **Media forensics:** Pillow (ELA), OpenCV (frame sampling), numpy (WAV signal statistics)
- **Frontend:** React 18, Vite 5, TypeScript (strict), Tailwind CSS, Zustand, Recharts, `@supabase/supabase-js`
- **Tooling:** docker compose, seeded dataset generators, offline evaluation harness

## Quick Start (Docker)

```bash
# one-time: create the Supabase project, run backend/db/schema.sql in the SQL
# editor, create the private bucket "cyberguard-media", and fill backend/.env
docker compose up --build
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

Offline accuracy/performance evaluation of all six detection modules (URLhaus, Cisco Umbrella and UCI SMS public data + seeded synthetic sets; no LLM or network calls during measurement):

| Module | Accuracy | Precision | Recall | F1 |
|---|---|---|---|---|
| email_phishing | 1.000 | 1.000 | 1.000 | 1.000 |
| url | 0.891 | 1.000 | 0.782 | 0.878 |
| message (SMS proxy) | 0.728 | 1.000 | 0.457 | 0.627 |
| account_takeover | 0.867 | 1.000 | 0.733 | 0.846 |
| network | 0.867 | 1.000 | 0.733 | 0.846 |
| deepfake_image | 1.000 | 1.000 | 1.000 | 1.000 |
| **Macro average** | **0.892** | **1.000** | **0.784** | **0.866** |

Full methodology, per-module breakdowns and limitations: **[evidence/reports/evaluation.md](../evidence/reports/evaluation.md)** (machine-readable: `evaluation.json`; regenerate with `python scripts/evaluate.py`).

## Security Notes

- The **service role key** bypasses RLS and lives only in `backend/.env` — it is never exposed to the frontend and never committed.
- All protected routes verify the caller's Supabase JWT (`app/core/security.py`); every state-changing action is audit-logged.
- RLS is enabled on all 11 tables (`db/schema.sql`); approval-gated response actions return 403 without explicit human approval.

## Phase A — Enterprise Upgrade (domain layer, state machine, circuit breaker)

- **SQLAlchemy domain layer** (`app/domain/`): ORM models for `incidents`, `incident_events`, `alerts` and the `incident_alerts` junction, mapped to the existing Supabase tables. Engine: async asyncpg, `pool_pre_ping`, `pool_size=10`, `max_overflow=20`. The supabase-py client is unchanged and still owns Auth, Storage and Realtime.
- **Strict incident state machine** (`app/domain/incident_lifecycle.py`): `TRIAGE → CONTAINMENT → ERADICATION → RECOVERY → CLOSED`, plus TRIAGE→CLOSED (false positive) and CONTAINMENT→TRIAGE (escalate back). `PATCH /incidents/{id}/status` validates the transition via SQLAlchemy *before* committing, so an analyst cannot close an incident that is still in containment (400 with an explanatory message). Legacy statuses (`open`/`investigating`/`contained`/`closed`) are accepted and normalized.
- **Async circuit breaker** (`app/ai/async_circuit_breaker.py`): a custom coroutine-safe breaker (CLOSED/OPEN/HALF_OPEN, threshold 3, 60 s recovery) wraps each remote LLM provider. When a provider is failing, its breaker opens and the gateway skips it instantly — an LLM outage can never hang the API; worst case is an immediate fall-through to the rule-based explanation.

> **One-time DB step:** widen the `incident_status` enum in Supabase before writing the new statuses (`ALTER TYPE incident_status ADD VALUE IF NOT EXISTS 'TRIAGE';` etc. — see `docs/deployment.md`). Until then the API reads legacy rows fine and accepts legacy status values.
