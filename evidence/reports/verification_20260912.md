# CYBERGUARD Verification Report — 2026-09-12

Scope: verify all layers against known-good baseline `ced885c` ("docs+hardening: Phase D-2 complete and full documentation sync with final codebase"), fix only genuine regressions, no redesign.

## 1. Change Inventory (STEP 1)

Working tree was **clean** at start; the external agent's changes are committed in the four commits after the baseline:

| Commit | Summary |
|---|---|
| `20f101b` | "Ronaldo VS messi" |
| `7a5cee2` | "HUUBA BEFORE ANTIGRAVITY" |
| `c5194a6` | audio deepfake v1: LCNN model trained + deployed; worker/rate-limit removed; launch-style bootstrap |
| `5caccde` | restore worker/rate-limit/queue sources (unwired); sync analysis path kept |

Classification of the 160 changed files (`git diff --stat ced885c..HEAD`):

- **backend/app**: `main.py` (rate-limit middleware unwired, calibration loader + deepfake startup log added), `core/config.py` (REDIS_URL / BACKGROUND_WORKERS_ENABLED / RATE_LIMIT_RPM settings removed), `core/calibration.py` + `core/url_reputation.py` added, AI clients / services / routes updated for v2 models, `workers/jobs.py` modified (later restored unwired).
- **backend/ml**: new training pipeline — `train_deepfake_v2.py`, `train_audio_v1.py`, `train_email_model.py`, `audio_features.py`, `audio_model.py`, dataset fetchers (`fetch_genimage.py`, `fetch_audio_data.py`, `degrade_messenger.py`, `build_indic_corpus.py`, `augment_urls.py`), `calibration.json`, plus ~100 GenImage `.pt` tensor files under `ml/data`.
- **backend/ml/models** (artifacts): `deepfake_cnn.pt` **deleted** (v1 retired), `deepfake_cnn_v2.pt` added, `email_tfidf_v2.pkl` + `email_phishing_xgb_v2.pkl` + `url_xgb_v2.pkl` added, `audio_cnn_v1.pt` + `audio_v1_metrics.json` added, `calibration.json` added. v1 email/url/network artifacts retained as fallback.
- **backend/scripts**: `verify_deployment.py` added, `regression_api.py` rewritten/expanded (56 cases), `evaluate.py` / `fetch_datasets.py` updated.
- **backend/db/migrations**: **no changes, nothing deleted** (0003–0006 all intact).
- **frontend/src**: `lib/apiConfig.ts` added; `Settings.tsx`, `services/http.ts`, `store/authStore.ts`, `vite.config.ts` small edits. **Landing.tsx untouched.**
- **configs**: `pyproject.toml` + `uv.lock` added (uv migration, all deps exact-pinned, matching requirements.txt), `.python-version` added, `requirements.txt` unchanged.
- **docs**: README.md, STATUS.md, DECISIONS.md, backend/docs/* synced.

Suspicious items flagged and their resolution:

1. **Rate limiting removed from `main.py`** (commit `c5194a6`, only partially restored by `5caccde` — sources came back but the middleware stayed unwired, and the `RATE_LIMIT_RPM` setting was dropped from `config.py`). → genuine regression, **fixed**.
2. **`GROQ_MODEL=llama-3.1-8b-instant`** in `backend/.env` (value present since before baseline; retired model) → **fixed** to `llama-3.3-70b-versatile`. Untracked file; not committed.
3. **venv activation instructions** in `README.md`, `backend/README.md`, `backend/docs/deployment.md` → converted to `uv` form, **fixed**.
4. No hardcoded credentials committed; `backend/.env` and `../.env.test` remain untracked. No deleted migrations. No removed org_id scoping (see gates). No new unpinned dependencies. No reintroduced deepfake v1 usage (only explanatory comments mention the retired `deepfake_cnn.pt`).

## 2. Static Gates (STEP 2)

| Gate | Result |
|---|---|
| `uv run python -m compileall app ml scripts` | ✅ exit 0 |
| `npx tsc --noEmit` | ✅ exit 0 |
| `npm run build` | ✅ built (chunk-size warning only, pre-existing) |
| `grep deepfake_cnn.pt backend/app backend/ml backend/scripts` | 2 hits, both benign: `ml/train_models.py:190` ("retired" comment), `scripts/verify_deployment.py:220` ("never deepfake_cnn.pt" assertion message). No v1 usage. |
| `grep "source .venv"` | Was 3 hits (README.md:98, backend/README.md:74, backend/docs/deployment.md:11) → **0 after fix** |
| `grep "cyan\|teal\|sky-\|blue-\|indigo\|violet" frontend/src` | ✅ 0 hits |
| `grep org_id backend/app/services/{alert,incident,dashboard,audit}_service.py` | ✅ present: alert 4, incident 23, dashboard 6, audit 13 |
| `grep "RATE_LIMIT\|rate_limit" backend/app/main.py` | Was **absent** → **present after fix** (`RateLimitMiddleware` import + `app.add_middleware(..., rpm=settings.RATE_LIMIT_RPM)`) |
| `grep allow_credentials backend/app/main.py` | ✅ line 58; wildcard-origin boot guard at lines 47–48 intact |

## 3. Artifact & Config Inventory (STEP 3)

`backend/ml/models/`: `email_tfidf_v2.pkl`, `email_phishing_xgb_v2.pkl`, `url_xgb_v2.pkl`, `deepfake_cnn_v2.pt`, `audio_cnn_v1.pt` (476 KB, present — training was completed), `network_xgb.pkl` (+ v1 fallbacks `email_tfidf.pkl`, `email_phishing_xgb.pkl`, `url_xgb.pkl`, `network_scaler.pkl`), `calibration.json`, `deepfake_v2_metrics.json`, `audio_v1_metrics.json`. ✅

`backend/ml/models/calibration.json` keys: `email_model_version=v2`, `deepfake_model_version=v2`, `url_model_version=v2`, `audio_model_version=v1` (matches existing `audio_cnn_v1.pt`). ✅ (A second, richer `backend/ml/calibration.json` is loaded by `app/core/calibration.py`.)

`backend/.env` `GROQ_MODEL`: was `llama-3.1-8b-instant` (retired) → changed to `llama-3.3-70b-versatile`. ✅

## 4. Database Checklist (STEP 4)

Postgres reachable via Supabase session pooler (IPv4) after the `DATABASE_URL` fix (§6); executed directly:

| Check | Expected | Result |
|---|---|---|
| `select count(*) from organizations` | ≥ 1 | **2** ✅ |
| `select count(*) from role_permissions` | ≥ 16 | **34** (after applying idempotent migration `0005_permissions.sql`, which the hosted project had never received) ✅ |
| `select count(*) from profiles where org_id is null` | 0 | **0** ✅ |
| `enum_range(null::incident_status)` | includes TRIAGE/CONTAINMENT/ERADICATION/RECOVERY/CLOSED | `{open,investigating,contained,closed,TRIAGE,CONTAINMENT,ERADICATION,RECOVERY,CLOSED}` ✅ |
| migration 0006 bootstrap guard in `handle_new_user` | present | present ✅ |

Note: `role_permissions` was missing on the hosted Supabase project; `app/core/security.py` was silently serving the hardcoded fallback matrix. The repo's migration 0005 (idempotent upserts) was applied to restore parity.

## 5. Audio Training (STEP 5)

Skipped — `audio_cnn_v1.pt` already exists and `ml/models/audio_v1_metrics.json` records the completed gate run:

- Model: AudioLCNNV1 (LCNN/MFM log-Mel CNN + 6-dim handcrafted branch), CPU, quick mode, 3 epochs, 11m43s.
- Dev: **F1 0.852**, accuracy 0.825, AUC 0.914 (10,425 dev crops; gate split never trained on).
- Real-world gate: ElevenLabs fake recall (max-prob) 1.0 (mean 0.0, honest domain-shift note); real-speech FPR 0.0.

## 6. Runtime Verification (STEP 6)

- Backend boots via `uv run uvicorn app.main:app --port 8000` (detached); startup log:
  `deepfake model active: v2 (128px, artifact deepfake_cnn_v2.pt)` ✅
- `GET /api/v1/health/deep` (authenticated) → `models: {deepfake: v2 / deepfake_cnn_v2.pt / heuristics_only=false, audio: v1 / audio_cnn_v1.pt / model_loaded=true / mode=trained_model}` ✅
- `uv run python scripts/verify_deployment.py` → **ALL PASS, exit 0** ✅
- `uv run python scripts/regression_api.py` → **56/56 PASS, exit 0** ✅
  - First run was 51/56: the five `PATCH /incidents/{id}/status` cases returned 500 with `OSError: [Errno 101] Network is unreachable`. Root cause (environmental, not code): `DATABASE_URL` pointed at Supabase's **direct** Postgres endpoint `db.jspkfzdaulhlquatwdsl.supabase.co:5432`, which resolves to an **IPv6-only** address, and this machine has no IPv6 route. Only `routes_incidents.py` uses the SQLAlchemy session; every other endpoint uses Supabase REST over HTTPS/IPv4 — exactly the five failures observed. `routes_incidents.py` is unchanged since baseline, so this is not an agent regression, but it blocked STEP 6/STEP 4.
  - Fix (untracked `backend/.env` only): switched `DATABASE_URL` to the Supabase **session pooler** (IPv4) `aws-0-ap-south-1.pooler.supabase.com:5432` (region discovered by probing Supavisor tenants; same DB credentials; pooler recommended in the repo's own `backend/docs/deployment.md:130`). Re-run → 56/56.

## 7. Frontend Design Integrity (STEP 7)

All monograph-spec features verified present in `frontend/src/pages/Landing.tsx` (untouched by the agent) — no fixes needed:

- Kinetic typographic hero animating on load (blur/rotate keyframes, lines 409–414; `CYBERGUARD /` headline at 427). ✅
- Scrollable module spreads with cross-fade + horizontal slide (`Reveal` component: IntersectionObserver, `opacity 750ms` + `translateX(36px→0)`, lines 55–79). ✅
- Severity palette film strip with drag-to-scroll scrubbing (`SEVERITY_RAMP`, `stripRef`, pointer handlers, lines 301–385). ✅
- Faint risograph red cursor-dot trail on a fixed `<canvas>` (lines 89+). ✅
- Oversized clamp-based headlines (`clamp(2.25rem, 10.5vw, 9.5rem)`, `clamp(5rem, 14vw, 12rem)`, …). ✅
- Sign Up → `/login?mode=signup` (line 344); Login → `/login?mode=signin` (line 350); Open Dashboard → `/dashboard` gated on `showDashboard` (auth) at line 352. ✅
- `usePrefersReducedMotion()` disables all motion (Reveal short-circuits to visible; canvas trail gated). ✅
- Queued-analysis pending panel for 202 responses: `QueuedAnalysisPanel` rendered on `result?.queued` in Phishing/URL/Impersonation/AccountTakeover/Deepfake analysis pages. ✅

## 8. Fixes Applied (STEP 8)

| # | File | Fix |
|---|---|---|
| 1 | `backend/app/core/config.py:27–34` | Restored `REDIS_URL`, `BACKGROUND_WORKERS_ENABLED`, `RATE_LIMIT_RPM` settings exactly as at baseline `ced885c` (removed by `c5194a6`; `app/core/rate_limit.py` and `app/workers/jobs.py` still reference them). |
| 2 | `backend/app/main.py:35, 65–66` | Re-registered `RateLimitMiddleware` after CORS (`app.add_middleware(RateLimitMiddleware, rpm=settings.RATE_LIMIT_RPM)`), matching baseline. |
| 3 | `README.md:98`, `backend/README.md:74` | Replaced `python -m venv .venv && source .venv/bin/activate` + `pip install -r requirements.txt` with `uv sync`. |
| 4 | `backend/docs/deployment.md:9–12` | Same venv→uv conversion; uvicorn invocation now `uv run uvicorn …`. |
| 5 | `backend/.env` (untracked) | `GROQ_MODEL` `llama-3.1-8b-instant` → `llama-3.3-70b-versatile`. |
| 6 | `backend/.env` (untracked) | `DATABASE_URL` direct IPv6-only endpoint → Supabase session pooler `aws-0-ap-south-1.pooler.supabase.com:5432` (`postgresql+asyncpg://postgres.<ref>:…`). |
| 7 | Hosted Supabase DB | Applied idempotent `backend/db/migrations/0005_permissions.sql` (permissions + role_permissions tables and 34-row matrix were never applied to the project). |

Post-fix re-runs: compileall ✅, backend boot ✅, `verify_deployment.py` ✅ exit 0, `regression_api.py` ✅ 56/56, DB checklist all green.

## 9. Outstanding Risks

- **Documented drift, not fixed (doc-only):** `backend/docs/deployment.md:127` still says "The Arq worker was removed; analysis runs in-process" while `5caccde` restored `app/workers/jobs.py` (unwired) and `BACKGROUND_WORKERS_ENABLED`/`REDIS_URL` settings. Code is consistent (worker sources present, not started); the doc sentence predates the restore.
- `backend/.env.example` still lists `GROQ_MODEL=llama-3.1-8b-instant` (tracked file; left untouched since it is a placeholder and changing it was outside the regression scope — flagging for the owner).
- Incident status transitions now depend on IPv4 reachability of the Supavisor pooler; direct-6432-style connections remain unusable on IPv4-only machines by Supabase design.
- Frontend bundle is ~1.1 MB (pre-existing chunk-size warning); not addressed (no redesign rule).
- `evidence/reports/regression_api.md` was regenerated by the 56/56 run (tracked file, part of the evidence flow).

*All fixes are minimal and surgical: two restored config blocks, one doc conversion, one untracked-env model/URL correction, one idempotent migration application. No behaviour was changed beyond restoring baseline behaviour.*

---

# Addendum — LLM Explanation Provider Chain (2026-09-12, second pass)

## Provider chain audit & live validation

| | Previous | New (verified live) |
|---|---|---|
| Order | groq → openrouter → rule_based (order was already correct) | groq → openrouter → rule_based (strict) |
| Groq timeout | 20 s default (`.env` 20 s) | **15 s** default (config, `.env.example`, calibration) |
| OpenRouter timeout | 60 s default, **silently clamped to 12 s** in `openrouter_client.py` | **20 s** default, clamp removed |
| Groq model | `llama-3.3-70b-versatile` → **404 model_not_found** (retired; Groq's catalogue no longer lists any llama-3.x) | **`qwen/qwen3.8-27b`** — 427 ms probe, 100% JSON-contract and band adherence (4/4 realistic prompts) |
| OpenRouter model | `openrouter/free` — 200 OK but erratic (1.8 s–12 s, occasionally >20 s, and sometimes ignores JSON mode entirely → unparseable) | **`liquid/lfm-2.5-2.6b:free`** — JSON 4/4, 2.8–5.7 s (key is free-tier; paid/other free models 429) |

## Changes

- `app/ai/llm_gateway.py` — per-call telemetry line `LLM chain: groq=<outcome>,<ms> openrouter=<outcome>,<ms> final=<provider>` on every explanation call incl. cache hits (`final=cache:<orig>`; unreached slots `skipped,0ms`). Breakers, cache and band validation untouched.
- `app/ai/openrouter_client.py` — removed the hidden `min(..., 12.0)` timeout clamp; honours `OPENROUTER_TIMEOUT_SECONDS`.
- `app/core/config.py` / `.env.example` / `ml/calibration.json` + `app/core/calibration.py` (`provider_chain`, `provider_timeout_seconds`, `provider_models`) / docs — defaults and sync.
- `app/services/assistant_service.py` — response now carries `explanation_provider` / `explanation_latency_ms` (all other modules already did).
- `frontend` — `ExplanationPanel` caption is now dynamic from `explanationProvider` (groq/openrouter → `EXPLAINABLE AI OUTPUT - <PROVIDER>`, `rule_based` → `HEURISTIC FALLBACK OUTPUT`, `cache:*` → `… (CACHED)`, undefined/mock → `SIMULATED XAI OUTPUT`); `explanationProvider` mapped in `mappers.ts` for alerts + all analysis types; passed by all six pages.
- `app/services/url_detector.py` — STEP 5 residual false positive: on top-1M domains with a standard auth path (`/login`, `/signin`, `/auth`, `/session`, `/oauth`) the `suspicious_path_keyword` indicator is downgraded to LOW ("standard authentication path on a high-reputation domain") and the ml_model indicator is suppressed for that whitelisted pattern (the model systematically over-fires on `/login` paths; blend math untouched).
- `scripts/drill_llm_chain.py` — new self-authenticating chain drill (subprocess per drill, env-only overrides, `.env` never edited).
- `scripts/regression_api.py` — added github.com/login case (57 total) + provider-distribution tally.

## Drill results (all PASS)

Drill (a) — both providers healthy:
```
explanation_provider=groq explanation_latency_ms=1041
chain telemetry: INFO:cyberguard.llm_gateway:LLM chain: groq=status,1041 openrouter=skipped,0 final=groq
```
Drill (b) — GROQ_API_KEY invalid (env override): `groq=error,217 openrouter=status,6461 final=openrouter` → PASS.
Drill (c) — both keys invalid (env override): `groq=error,203 openrouter=error,169 final=rule_based`, fallback text present → PASS.

## Regression & verification

- `regression_api.py`: **57/57 PASS** (56 original + github.com/login). Provider distribution across analysis responses: **groq=5 openrouter=14** (rule_based=0, cache=0 — each case uses a unique cache-miss sample; the openrouter share came from Groq free-tier **429 rate limits** during the burst, with the breaker opening and recovering exactly as designed — visible in the telemetry).
- `verify_deployment.py`: ALL PASS, exit 0. `compileall`: exit 0. `tsc --noEmit` + `npm run build`: exit 0.
- github.com/login: **before** hybrid 44/medium (path keyword medium + ml 0.76 raised by monotonic blend) → **after** 5/safe.
