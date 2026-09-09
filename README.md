# 🛡️ CYBERGUARD

**AI-Powered Cyber Threat, Phishing & Digital Impersonation Detection and Response System**

A hackathon project by **Chandan** — a full-stack SOC (Security Operations Center) platform that ingests emails, URLs, messages, authentication logs, network flows, API logs and media files, runs them through a **hybrid detection engine** (transparent heuristics + trained ML models), scores risk, generates LLM explanations through a timed provider chain (OpenRouter → Groq → local rule-based fallback), and surfaces everything in a live cybersecurity command dashboard.

> ⚠️ Educational prototype. All response actions are simulated; no real infrastructure is modified.

---

## ✨ Features

| Detection module | What it catches |
|---|---|
| 🎣 **Phishing** | Lookalike sender domains, urgency, credential harvesting, malicious body URLs, SMS spam patterns (shortcodes, spam vocabulary, ALL-CAPS) |
| 🔗 **Malicious URL** | IP hosts, suspicious TLDs, brand-in-subdomain, payload extensions, random high-entropy paths, URLhaus-style patterns |
| 🎭 **Impersonation** | CEO fraud / BEC: authority claims, pressure, unusual financial requests, secrecy demands |
| 🔑 **Account takeover** | Failed-login bursts, impossible travel, unknown devices, success-after-failures |
| 🌐 **Network / API abuse** | Data exfiltration (>10 MB flows), C2 ports (4444/8888/…), API rate abuse, 401 bursts |
| 🖼️ **Deepfake / media forensics** | Error Level Analysis (images), frame-sampled ELA (videos), WAV signal statistics — blended with a trained CNN |

Plus: a public editorial landing page at `/` (no auth), multi-source ingestion API, alert management & search, incident lifecycle (create → assign → escalate), approval-gated response execution, dashboard summary, audit logging, SOC assistant chat, and **Supabase Realtime** live alert streaming.

## 🧠 Hybrid Detection Engine

```
Ingestion → Heuristic Engine → Risk Scoring → XAI Gateway (OpenRouter → Groq → rule-based) → Alert Generation → Dashboard
                                   ↑
                  trained ML models (XGBoost + CNN, blended 45/55)
```

- **Heuristics** (`backend/app/services/*_detector.py`) — transparent, enumerable rules
- **ML models** (`backend/ml/models/`, trained by `backend/ml/train_models.py`) — TF-IDF+XGBoost (emails), XGBoost (URLs, network), CNN (CIFAKE deepfake images)
- Blended score: `hybrid = round(0.45 × heuristic + 0.55 × ml × 100)`; falls back to heuristics-only automatically if a model is missing or `ML_ENABLED=false`

## 🏗️ Architecture

- **Frontend** (`frontend/`): React 18 + Vite 5 + TypeScript + Tailwind + Zustand + Recharts, Supabase Auth login, Realtime alert stream
- **Backend** (`backend/`): FastAPI (11 routers under `/api/v1`), pydantic-settings, supabase-py, httpx (OpenRouter + Groq), joblib/XGBoost/PyTorch inference
- **Supabase (cloud)**: PostgreSQL with RLS on every table, Auth (JWT), Storage (private media bucket), Realtime
- Full diagram & security model: [`backend/docs/architecture.md`](backend/docs/architecture.md)

## 🚀 Quick Start

```bash
# 1. Supabase: create a project, run backend/db/schema.sql in the SQL editor,
#    create the private bucket "cyberguard-media", add table alerts to the
#    supabase_realtime publication (see backend/docs/deployment.md)

# 2. Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                      # fill in Supabase keys; OpenRouter/Groq keys optional (explanations)
uvicorn app.main:app --reload --port 8000

# 3. Frontend (second terminal)
cd frontend
npm install
cp .env.example .env                      # fill in VITE_SUPABASE_* + VITE_API_BASE_URL
npm run dev                               # http://localhost:5173
```

Docker alternative: `docker compose up --build` → backend on :8000, frontend on :3000.

Run the three mandatory demo scenarios end-to-end:

```bash
python backend/scripts/demo.py http://localhost:8000 <supabase_access_token>
```

## 📊 Evaluation Results

Offline evaluation of all six modules (heuristics-only vs hybrid) on held-out data — full report: [`evidence/reports/evaluation.md`](evidence/reports/evaluation.md):

| Module | Heuristic F1 | Hybrid F1 |
|---|---|---|
| email_phishing | 0.0268 | **0.9867** |
| url | 0.9189 | **1.0000** (held-out, small-sample caveat) |
| message (SMS proxy) | 0.6270 | 0.5000 |
| account_takeover | 0.8462 | 0.8462 (no ML model yet) |
| network | 0.8462 | 0.0000 (KDD99 domain mismatch — reported honestly) |
| deepfake_image | 0.6667 | **0.9182** |
| **Macro** | 0.6553 | **0.7085** |

## 📁 Repository Layout

```
├── backend/          FastAPI app, detection services, ML pipeline, docs
│   ├── app/          api/ core/ ai/ services/ schemas/
│   ├── ml/           fetch_data.py preprocess.py train_models.py + data/ models/
│   ├── db/           schema.sql (Supabase schema, RLS, seeds)
│   ├── docs/         architecture, models, deployment, datasets, demo_script
│   └── scripts/      fetch_datasets, generate_synthetic_datasets, evaluate, demo
├── frontend/         React SOC dashboard (services, store, pages, components)
├── datasets/         labelled datasets (URLhaus, Umbrella, UCI SMS, synthetic)
├── evidence/         evaluation reports, screenshots, demo media
├── docker-compose.yml
└── plan.md           master implementation plan
```

## 🎨 Frontend Theme — Black / White / Red

The entire frontend uses a strict monochrome red palette (centralised in `frontend/src/theme.ts`):

| Surface | Value |
|---|---|
| Page background | `#050505` |
| Sidebar / topbar / panels | `#0a0a0a` |
| Cards | `#101010` (border `#262626`) |
| Primary text / secondary text | `#fafafa` / `#a3a3a3` |
| Accent (nav, links, buttons, gauge arcs, chart series) | `#dc2626` (hover `#ef4444`) |
| Secondary buttons | transparent, white border/text; hover inverts to white bg / black text |

**Severity ramp (0-100 risk bands):**

| Band | Score | Color | Text on swatch |
|---|---|---|---|
| Safe | 0-20 | `#e4e4e7` | black |
| Low | 21-40 | `#71717a` | white |
| Medium | 41-60 | `#f87171` | black |
| High | 61-80 | `#dc2626` | white |
| Critical | 81-100 | `#ef4444` | white + subtle pulse ring |

The ramp is consumed everywhere via `SEVERITY_RAMP` / `SEVERITY_COLORS` from `src/theme.ts` —
SeverityBadge, RiskGauge, StatusPill, Toast, all recharts series, the Settings risk-threshold
table swatches, and the public landing page severity film strip. Selection color and scrollbars
are red on black. No cyan, teal or blue accents remain anywhere in `src/`.

## 🔒 Security

The Supabase **service role key** lives only in `backend/.env` (git-ignored) — it is never exposed to the browser. All protected routes verify Supabase JWTs; RLS is enabled on every table; destructive response actions require explicit human approval and are audit-logged.
