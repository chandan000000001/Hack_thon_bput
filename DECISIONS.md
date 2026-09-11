# CYBERGUARD — Decision Records

Consolidated architecture decision records. Each entry states the decision, the rationale, and where it lives in the code.

## DR-1 — Supabase as hosted infrastructure
**Decision:** database (PostgreSQL + RLS), Auth, Storage and Realtime are provided by a cloud-hosted Supabase project; nothing data-related runs locally or in Compose (the backend and frontend are stateless; Redis only carries the job queue).
**Rationale:** a hackathon team gets managed auth, row-level security, media storage with signed URLs and realtime streaming without operating any data plane.
**Code:** `backend/app/core/supabase_client.py` (service-role singleton), `backend/db/schema.sql`, `docker-compose.yml` (redis/backend/frontend only).

## DR-2 — Monotonic hybrid blending
**Decision:** the hybrid score is `max(heuristic_score, round(0.45 * heuristic_score + 0.55 * ml_probability * 100))` — a trained model may raise a score but may **never** lower it below the heuristic verdict; the ML contribution is carried as a `type: ml_model` indicator and never adds heuristic weight on top of the blend.
**Rationale:** a weak or mismatched ML signal must not dilute a strong heuristic verdict (e.g. a C2-port exfiltration event must never be downgraded to Safe); missing models degrade cleanly to heuristics-only.
**Code:** `backend/app/services/ml_inference.py` (`blend_scores`, `split_ml_indicator`, `score_with_ml`).

## DR-3 — RBAC hierarchy with default viewer on signup
**Decision:** roles are strictly ordered viewer < analyst < admin; every brand-new signup is the least-privileged `viewer`.
**Rationale:** fail-safe authorization — a new account can read dashboards but cannot run analyses or mutate anything until an admin promotes it.
**Code:** `backend/app/core/security.py` (`ROLE_LEVELS`, `DEFAULT_ROLE`), `backend/db/migrations/0003_roles_and_seed.sql` (column default + trigger writes `viewer`).

## DR-4 — Database-backed permission matrix
**Decision:** access is decided by granular permission keys (16 keys in `permissions` + `role_permissions`, migration 0005) resolved per role, not by coarse role checks; `require_permission(key)` returns 403 `Missing permission: <key>`; `require_role` survives as a compatibility alias; the identical matrix is hardcoded in `security.py` as a fail-safe fallback for deployments where migration 0005 has not run.
**Rationale:** the matrix can evolve (add roles/keys) with a SQL edit, and conditional in-handler gates (`incident.close` on CLOSED, `response.execute_destructive` on destructive catalog entries) stay explicit.
**Code:** `backend/app/core/security.py` (`get_role_permissions`, `require_permission(s)`, `has_permission`, `DEFAULT_ROLE_PERMISSIONS`), `backend/db/migrations/0005_permissions.sql`.

## DR-5 — Multi-tenancy enforced at the service layer; RLS as defence in depth
**Decision:** every user/event/alert/incident/audit row carries `org_id` (migration 0004); because the backend talks to Postgres with the service-role key (which bypasses RLS), the **primary** enforcement is the service layer: every SELECT filters `.eq("org_id", …)` and every INSERT carries the caller's org; cross-tenant ids resolve to 404. RLS stays enabled on every table as a second layer.
**Rationale:** tenant resolution (`profiles.org_id`, 5-minute LRU cache, Default Organization fallback that even auto-creates the org — mirroring migration 0006) means an unassigned signup can never crash scoping, while RLS constrains any direct anon-key access.
**Code:** `backend/app/core/supabase_client.py`, `backend/app/core/security.py`, `backend/db/migrations/0004_multi_tenancy.sql`, `backend/db/migrations/0006_org_bootstrap_guard.sql`, all services under `backend/app/services/`.

## DR-6 — Arq + Redis background workers with synchronous fallback
**Decision:** heavy analysis (deepfake media forensics, bulk auth-log/network batches) is enqueued to an Arq worker via Redis (`max_jobs=4`, `job_timeout=300`) and the API answers **202 Accepted**; when Redis is unreachable or `BACKGROUND_WORKERS_ENABLED=false`, the identical `run_*` coroutine executes synchronously and the API answers 200. Jobs are idempotent (completed events exit immediately) and never re-raise.
**Rationale:** one shared implementation for queued and fallback paths cannot drift; the product degrades, never breaks, without a broker.
**Code:** `backend/app/services/job_queue.py` (fail-soft `enqueue_job`, 30 s Redis re-dial cooldown), `backend/app/workers/jobs.py`, `backend/app/workers/settings.py`, `POST /analysis/media` + `POST /events/bulk` in `backend/app/api/`.
**SUPERSEDED 2026-09-11:** the worker queue, `job_queue.py` and `app/workers/` were removed — heavy analysis (media forensics, bulk logs) now always runs synchronously on the request thread (200; the `202` queued flow no longer exists). The shared-coroutine principle survives in `app/services/bulk_analysis.py`. The `redis` compose service and `arq`/`redis` packages remain as standalone infrastructure. The Phase D-1 rate limiter (`app/core/rate_limit.py`, `RATE_LIMIT_RPM`) was removed in the same change — requests are no longer throttled.

## DR-7 — Custom async circuit breaker (pybreaker replaced)
**Decision:** each remote LLM provider sits behind a custom `AsyncCircuitBreaker` (CLOSED/OPEN/HALF_OPEN, failure_threshold=3, recovery_timeout=60 s); pybreaker was dropped because it is synchronous and would block the asyncio event loop.
**Rationale:** an OPEN breaker means the gateway skips that provider instantly (`Circuit breaker OPEN for <provider>, skipping to fallback`), so a sustained LLM outage costs zero added latency instead of the full timeout chain.
**Code:** `backend/app/ai/async_circuit_breaker.py`, wired in `backend/app/ai/llm_gateway.py`.

## DR-8 — LLM provider chain with configurable timeouts
**Decision:** explanations run through a strict provider chain — Groq (`GROQ_TIMEOUT_SECONDS`, default 20 s) → OpenRouter (`OPENROUTER_TIMEOUT_SECONDS`, default 60 s) → local rule-based template (instant, never fails) — Groq first as the fastest provider; results are cached (TTL 3600 s, max 256 entries) and every response carries `explanation_provider` + `explanation_latency_ms` provenance.
**Rationale:** bounded analysis latency even when a provider degrades; providers never produce scores.
**Code:** `backend/app/ai/llm_gateway.py`, `groq_client.py`, `openrouter_client.py`, `explanation_cache.py`; commit 619f303 "Reorder LLM provider chain: Groq 20s -> OpenRouter 60s -> rule-based".

## DR-9 — Threadpool rule for blocking IO
**Decision:** blocking IO never runs on the event loop — every supabase-py call, Supabase Auth round-trip, storage upload/download and ELA/CNN inference invoked from an async context goes through `app/core/asyncbridge.to_thread` (Starlette's threadpool) or is a plain `def` route; uploaded files are read exactly once (never re-reading the `SpooledUploadFile`).
**Rationale:** a single blocking call on the loop stalls every concurrent request.
**Code:** `backend/app/core/asyncbridge.py`; used across `security.py`, `routes_analysis.py`, `workers/jobs.py`, `core/storage.py`.

## DR-10 — Cache TTLs of 60 s with invalidation on privilege change
**Decision:** verified auth context (sha256 of the bearer token), profile role and role permission matrix are cached for **60 seconds** each (user organization 5 min, LRU maxsize 1024); `invalidate_user(user_id)` clears all of a user's cached authorization artifacts immediately after an admin changes that user's role.
**Rationale:** short TTLs bound staleness; explicit invalidation makes privilege changes take effect instantly instead of at cache expiry.
**Code:** `backend/app/core/security.py` (`invalidate_user`), called from `PATCH /admin/users/{user_id}/role` in `backend/app/api/routes_admin.py`.

## DR-11 — Black / white / red monochrome theme
**Decision:** the entire frontend uses a strict monochrome red palette — page `#050505`, panels `#0a0a0a`, cards `#101010`, primary/secondary text `#fafafa`/`#a3a3a3`, red-600 `#dc2626` accent (hover `#ef4444`); the severity ramp is `#e4e4e7` / `#71717a` / `#f87171` / `#dc2626` / `#ef4444`; selection color and scrollbars are red on black; no cyan/teal/blue accents remain.
**Rationale:** a single centralized theme keeps the SOC console visually coherent and severity-coded.
**Code:** `frontend/src/theme.ts` (`SEVERITY_RAMP`, `SEVERITY_COLORS`), consumed by SeverityBadge, RiskGauge, StatusPill, Toast, recharts series and the landing page.

## DR-12 — Public editorial landing page
**Decision:** `/` is a public editorial landing page (no authentication) presenting the platform's modules, severity bands and auth entry points; the SOC console lives behind login.
**Rationale:** judges and visitors see the product story before authenticating; the dashboard stays gated.
**Code:** `frontend/src/pages/Landing.tsx`; commit 400bea1 "P6/P30: public editorial landing page at / with prmodule spreads and auth entry points".

## DR-13 — Single neural deepfake artifact; heuristics-only degraded mode
**Decision:** the v1 deepfake artifact (`deepfake_cnn.pt`, 32x32 CIFAKE CNN) and all of its code paths — the dual-version loader branch, the 32px preprocessing, the manipulation cap and the medium severity clamp, and the v1-only calibration keys — were deleted; there is no inference-time ensemble of v1 and v2, and the loader serves exactly one 128px artifact selected by `ml/models/calibration.json` (`deepfake_model_version`, currently v2, future v3). If the selected artifact file is missing, detection degrades to heuristics-only (localised ELA splice plus metadata) and every response carries an `ml_model` indicator valued `heuristics-only-fallback` with a logged warning — never a silent neural fallback.
**Rationale:** one artifact means one evaluation story; a hidden fallback to an obsolete model silently changes detection behaviour and invalidates the measured gates.
**Code:** `backend/app/services/ml_inference.py` (single-artifact loader, `deepfake_degraded()`), `backend/app/services/deepfake_detector.py`, `backend/ml/models/calibration.json`; verified by `backend/scripts/verify_deployment.py`.
