# 🛡️ CYBERGUARD

**AI-Powered Cyber Threat, Phishing & Digital Impersonation Detection and Response System**

CYBERGUARD is a full-stack SOC (Security Operations Center) platform built to detect, classify, score, explain and respond to AI-powered phishing, deepfakes, digital impersonation and technical threats. It ingests emails, URLs, messages, authentication logs, network flows, API logs and media files, runs them through a **hybrid detection engine** (transparent heuristics + four trained models), maps every detection to risk bands and MITRE ATT&CK techniques, generates LLM explanations through a timed provider chain, and recommends response actions — all surfaced in a live cybersecurity command dashboard backed by Supabase.

> ⚠️ Educational prototype. All response actions are simulated; no real infrastructure is modified.

---

## ✨ Features

- **Six detection modules** — phishing (email + SMS text), malicious URL, digital impersonation, account takeover, network/API abuse, and deepfake/media forensics.
- **Hybrid detection: heuristics + five trained models** — TF-IDF + XGBoost for emails, feature-based XGBoost for URLs, a MobileNetV3 CNN for deepfake images, an LCNN audio anti-spoofing model (ASVspoof 2019), and scaler + XGBoost for KDD99 network flows. Monotonic blending: `hybrid = max(heuristic, round(0.45 × heuristic + 0.55 × ml × 100))` — a trained model may raise a score but never lower the heuristic verdict below it.
- **Explainable AI with provenance** — every alert carries a human-readable explanation, MITRE ATT&CK techniques and recommended actions; each response includes `explanation_provider` (`groq` | `openrouter` | `rule_based` | `cache:<provider>`) and `explanation_latency_ms`.
- **LLM gateway chain with circuit breakers** — Groq (`GROQ_TIMEOUT_SECONDS`, default 20 s) → OpenRouter (`OPENROUTER_TIMEOUT_SECONDS`, default 60 s) → local rule-based template, each remote provider behind its own async circuit breaker (3 failures → OPEN for 60 s), with a bounded explanation cache (TTL 3600 s, 256 entries).
- **Risk bands Safe → Critical** — deterministic indicator scoring (critical 25 / high 15 / medium 5, capped at 100) mapped to bands safe 0–20, low 21–40, medium 41–60, high 61–80, critical 81–100.
- **RBAC viewer / analyst / admin with a database-backed permission matrix** — 16 granular permission keys in `role_permissions` (migration 0005), enforced by `require_permission(key)` (403 `Missing permission: <key>`); new signups default to `viewer`.
- **Multi-tenancy via `org_id`** — every user, event, alert, incident and audit row is organization-scoped and filtered at the service layer (migration 0004); RLS is defence in depth.
- **Synchronous heavy analysis** — media forensics and bulk log ingestion run on the request thread (the background worker queue and rate limiter were removed); blocking IO stays off the event loop via the threadpool.
- **Supabase Auth, Storage and Realtime** — JWT authentication, private `cyberguard-media` bucket (25 MB cap, 1-hour signed URLs), and Realtime streaming of new alerts to the dashboard.
- **React SOC dashboard and editorial landing page** — black/white/red SOC console (dashboard, six analysis pages, alerts, incidents, response actions, audit logs, user management, SOC assistant) plus a public editorial landing page at `/`.

## 🧠 Hybrid Detection Engine

```
Ingestion → Heuristic Engine → Risk Scoring → XAI Gateway (Groq → OpenRouter → rule-based) → Alert Generation → Dashboard
                                   ↑
        trained ML models (2× XGBoost + CNN + XGBoost/scaler, blended 45/55, monotonic)
```

- **Heuristics** (`backend/app/services/*_detector.py`) — transparent, enumerable rules with severity weights.
- **ML models** (`backend/ml/models/`, trained by `backend/ml/train_models.py`) — served via `app/services/ml_inference.py`; missing models or `ML_ENABLED=false` degrade gracefully to heuristics-only.
- **Blending** — `hybrid_score = max(heuristic_score, round(0.45 × heuristic_score + 0.55 × ml_probability × 100))`; the ML contribution is persisted as a `type: ml_model` indicator and never adds heuristic weight.

## 🏗️ Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite 5, TypeScript, Tailwind CSS, Zustand, Recharts, supabase-js (Auth + Realtime) |
| Backend | Python 3.11+, FastAPI, pydantic-settings, supabase-py (Auth/Storage/Realtime) + SQLAlchemy 2.0 async domain layer (asyncpg), httpx |
| Detection / ML | Heuristic detectors (pure Python), XGBoost, scikit-learn, PyTorch + torchvision, Pillow ELA, OpenCV |
| Explainability | LLM gateway: Groq + OpenRouter (OpenAI-compatible) with async circuit breakers, local rule-based fallback |
| Data platform | Supabase (PostgreSQL + RLS, Auth, Storage, Realtime) |
| Deployment | Docker Compose (backend, frontend), uvicorn, Nginx |

## 📁 Project Structure

```
├── backend/
│   ├── app/
│   │   ├── api/          12 routers under /api/v1 (health, auth, db, events, analysis,
│   │   │                 alerts, incidents, response, dashboard, audit, assistant, admin)
│   │   ├── core/         config, security (JWT + permission matrix), supabase client,
│   │   │                 storage, database (async SQLAlchemy), asyncbridge
│   │   ├── ai/           llm_gateway, groq_client, openrouter_client, async circuit
│   │   │                 breaker, explanation cache, prompt templates
│   │   ├── domain/       ORM models + NIST/SANS incident lifecycle state machine
│   │   ├── services/     6 detectors, scoring, ml_inference, alert/incident/response/
│   │   │                 dashboard/audit/assistant services, bulk_analysis, media_forensics/
│   │   ├── schemas/      Pydantic request/response models
│   │   └── workers/      (removed — analysis runs synchronously)
│   ├── ml/               fetch_data.py, preprocess.py, train_models.py, train_audio_v1.py,
│   │                     fetch_audio_data.py, audio_features.py, audio_model.py, data/, models/, cache/
│   ├── db/               schema.sql + migrations/ (0003 roles, 0004 multi-tenancy,
│   │                     0005 permissions, 0006 org bootstrap guard)
│   ├── docs/             architecture, api, models, datasets, deployment, demo_script
│   └── scripts/          fetch_datasets, generate_synthetic_datasets, evaluate, demo,
│                         regression_api, make_test_media
├── frontend/             React SOC dashboard + editorial landing page
│   └── src/              pages/, components/, services/, store/, hooks/, theme.ts
├── datasets/             labelled datasets (URLhaus, Umbrella, UCI SMS, synthetic) + provenance.json
├── evidence/             reports/ (evaluation, regression), screenshots/, logs/, media/
├── docker-compose.yml    redis + backend + frontend
├── plan.md               master implementation plan (phases 0-30 + enterprise A-D-2)
├── STATUS.md             phase status table with evidence pointers
└── DECISIONS.md          consolidated architecture decision records
```

## 🚀 Quick Start

```bash
# 1. Supabase (one-time, see backend/docs/deployment.md):
#    - create a project at supabase.com
#    - in the SQL editor run, in order:
#        backend/db/schema.sql                          # base schema: 7 enums, 11 tables, RLS, trigger, response catalog
#        backend/db/migrations/0003_roles_and_seed.sql   # profiles.email column + demo role seeding (viewer default)
#        backend/db/migrations/0004_multi_tenancy.sql    # organizations + org_id everywhere
#        backend/db/migrations/0005_permissions.sql      # 16-key permission matrix (viewer/analyst/admin)
#        backend/db/migrations/0006_org_bootstrap_guard.sql # signup can never get a NULL org
#      then widen the incident status enum for the NIST lifecycle (one-time SQL, see deployment.md)
#    - create the private storage bucket "cyberguard-media"
#    - add the alerts table to the supabase_realtime publication
#    - create the three demo users in Supabase Auth (roles assigned by migration 0003)

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                      # fill in Supabase keys; Groq/OpenRouter keys optional (explanations)
uvicorn app.main:app --reload --port 8000 # http://localhost:8000/docs

# 3. Frontend (second terminal)
cd frontend
npm install
cp .env.example .env                      # fill in VITE_SUPABASE_* + VITE_API_BASE_URL
npm run dev                               # http://localhost:5173
```

Docker alternative: `docker compose up --build` → backend on :8000, frontend on :3000 (redis remains available on :6379 as standalone infrastructure — the app no longer uses it).

Automated end-to-end demo: `python backend/scripts/demo.py http://localhost:8000 <supabase_access_token>`

## ⚙️ Environment Variables

Backend (`backend/.env`, loaded by `app/core/config.py`):

| Variable | Purpose | Default |
|---|---|---|
| `SUPABASE_URL` | Supabase project URL | — (required) |
| `SUPABASE_ANON_KEY` | Public anon key — used only to verify user JWTs | — (required) |
| `SUPABASE_SERVICE_ROLE_KEY` | Privileged key — all DB/storage writes; **backend-only, never commit** | — (required) |
| `DATABASE_URL` | Async SQLAlchemy connection for the incident domain layer (`postgresql+asyncpg://…`); does **not** replace supabase-py | `postgresql+asyncpg://postgres:postgres@localhost:54322/postgres` |
| `OPENROUTER_API_KEY` | OpenRouter key; empty skips the provider | `""` |
| `OPENROUTER_MODEL` | OpenRouter model id | `meta-llama/llama-3.1-8b-instruct:free` |
| `OPENROUTER_TIMEOUT_SECONDS` | OpenRouter call timeout (s) | `60` |
| `GROQ_API_KEY` | Groq key; empty skips the provider | `""` |
| `GROQ_MODEL` | Groq model id | `llama-3.1-8b-instant` |
| `GROQ_TIMEOUT_SECONDS` | Groq call timeout (s) | `20` |
| `CORS_ORIGINS` | Comma-separated allowed browser origins (`*` is rejected at boot while credentials are allowed) | `http://localhost:5173,http://localhost:3000` |
| `API_V1_PREFIX` | Route prefix | `/api/v1` |
| `ML_ENABLED` | Toggles trained-model inference (heuristics-only when false) | `true` |
| `ML_MODELS_DIR` | Trained-artifact directory | `ml/models` |

Frontend (`frontend/.env`, Vite build-time):

| Variable | Purpose | Default |
|---|---|---|
| `VITE_USE_MOCK` | `false` = live backend + Supabase Auth; anything else = self-contained mock mode | `false` |
| `VITE_API_BASE_URL` | Backend base URL | `http://localhost:8000/api/v1` |
| `VITE_SUPABASE_URL` | Supabase project URL (browser client) | — |
| `VITE_SUPABASE_ANON_KEY` | Anon key only — the service role key must never appear in the frontend | — |

## 👥 Demo Accounts

Create in **Supabase Auth → Users → Add user** (passwords of your choice); the `handle_new_user` trigger creates their profiles and **migration 0003** assigns the roles:

| Email | Role | Can do |
|---|---|---|
| `admin@cyberguard.local` | admin | Everything, including destructive (approval-required) responses and user management |
| `analyst@cyberguard.local` | analyst | Run all analyses, work incidents/alerts, execute safe responses, view audit |
| `viewer@cyberguard.local` | viewer | Read-only dashboards, alerts, incidents, reports |

## 📊 Evaluation Results

Offline evaluation of all six modules (heuristics-only vs hybrid) on held-out data — full report: [`evidence/reports/evaluation.md`](evidence/reports/evaluation.md) (generated 2026-09-07 by `backend/scripts/evaluate.py`):

| Module | n | Heuristic F1 | Hybrid F1 |
|---|---|---|---|
| email_phishing | 24000 | 0.0268 | **0.9842** |
| url | 200 | 0.9189 | **1.0000** (held-out; small-sample caveat) |
| message (SMS proxy) | 600 | 0.6270 | 0.6826 |
| account_takeover | 60 | 0.8462 | 0.8462 (no trained model) |
| network | 60 | 0.8462 | 0.8148 |
| deepfake_image | 1000 | 0.6667 | 0.6667 |
| **Macro average** | | 0.6553 | **0.8324** |

## 📚 Documentation & Evidence

- [`backend/docs/architecture.md`](backend/docs/architecture.md) — system architecture, data flow, state machine, circuit breakers, multi-tenancy
- [`backend/docs/api.md`](backend/docs/api.md) — complete endpoint reference
- [`backend/docs/models.md`](backend/docs/models.md) — model cards, blending rule, provider chain, limitations
- [`backend/docs/datasets.md`](backend/docs/datasets.md) — dataset provenance and caveats
- [`backend/docs/deployment.md`](backend/docs/deployment.md) — deployment, scalability, hardening notes
- [`backend/docs/demo_script.md`](backend/docs/demo_script.md) — judge walkthrough
- [`evidence/reports/evaluation.md`](evidence/reports/evaluation.md) — detection metrics + artifact hashes
- [`evidence/reports/regression_api.md`](evidence/reports/regression_api.md) — 24/24 API regression matrix
- [`STATUS.md`](STATUS.md) · [`DECISIONS.md`](DECISIONS.md) · [`plan.md`](plan.md)

## 🔒 Security

The Supabase **service role key** lives only in `backend/.env` (git-ignored) — it is never exposed to the browser. All protected routes verify Supabase JWTs against the anon client and the **database-backed permission matrix** (`role_permissions`, migration 0005): viewers are read-only, analysts run analyses and work incidents/alerts, admins additionally execute destructive responses and manage users. Every row is **organization-scoped** (migration 0004) with service-layer `org_id` filtering — the primary enforcement, because the service-role client bypasses RLS — and RLS is enabled on every table as defence in depth. Destructive response actions require explicit human approval plus the `response.execute_destructive` permission, and every mutation is audit-logged (with a durable local fallback in `evidence/logs/audit_fallback.jsonl`).
