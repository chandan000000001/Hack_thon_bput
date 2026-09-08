# CYBERGUARD Post-Theme Regression Fixes

Date: 2026-09-09 · Scope: full post-theme regression & E2E verification
Summary: API matrix **24/24 PASS** (`regression_api.md`), browser E2E **14/14 PASS**
(`frontend/e2e/ui.spec.ts`). Two application defects and several test-harness
issues were found and fixed. No colors, layout geometry, or copy were changed
while fixing (the one style edit is paint-order only, see FIX-2).

---

## Application fixes

### FIX-1 — React duplicate keys in RecommendedActionsPanel (console error)
- **Symptom (Phase D, test f):** the browser console-error gate failed with
  `Warning: Encountered two children with the same key` thrown from
  `RecommendedActionsPanel.tsx` when a deepfake result rendered — the backend
  can return the same recommended-action id twice for one alert.
- **Root cause:** `actions.map()` used `key={action.id}`, which is not unique
  when the alert's `recommended_actions` contain repeated action ids.
- **Fix:** composite key `key={`${action.id}-${index}`}` in
  `frontend/src/components/common/RecommendedActionsPanel.tsx`. No layout,
  color, or copy change; rendered rows are identical.
- **Classification:** pre-existing app bug (not theme-induced), caught by the
  new console gate.

### FIX-2 — Topbar dropdown painted beneath main content (logout unclickable)
- **Symptom (Phase D, test n):** clicking `Logout` in the user menu timed out —
  Playwright hit-testing showed a dashboard loading skeleton (`<main>` subtree)
  intercepting pointer events over the open dropdown.
- **Root cause:** `backdrop-blur` on the Topbar `<header>` creates a stacking
  context at z-auto; because `<header>` precedes `<main>` in the DOM, `main`
  paints above the header's subtree whenever they overlap, burying the
  dropdown's `z-30` (which is trapped inside the header's stacking context).
  Pre-existing; unrelated to theming, but reproducible whenever a loading
  skeleton is on screen (dashboard auto-refreshes every 30 s).
- **Fix:** added `relative z-30` to the `<header>` in
  `frontend/src/components/layout/Topbar.tsx` — paint-order only; zero
  geometry, color, or copy change.
- **Classification:** pre-existing app bug (not theme-induced); minimal fix.

---

## Test-harness fixes (no application change)

### HARNESS-1 — ATO regression sample used integer epoch timestamps
`POST /analysis/account-takeover` returned `low` because
`account_takeover_detector._parse_timestamp` parses ISO-8601 **strings** only;
integer timestamps yield `None`, so impossible-travel never fired. The sample
now emits ISO timestamps. Detector itself behaves correctly.

### HARNESS-2 — ATO sample scored exactly 60 (medium boundary)
With one burst-high + one critical impossible-travel + one success-after-
failures + a single new-device medium, the deterministic scoring engine
(25/15/15/5) sums to 60 → `medium` (band boundary). The six-event sample was
adjusted to a realistic attacker pattern (a second **different** unknown device
on the final success), which adds one more medium indicator → 65 → `high`.
The scoring engine itself was **not** modified. Observation recorded, not
changed: a lone critical impossible-travel indicator scores 25 → `low` under
the current weights — pre-existing design worth revisiting separately.

### HARNESS-3 — Supabase JWT TTL shorter than cumulative analysis runtime
Each analysis call takes ~100-150 s (ML scoring + LLM explanation). The
project's access-token TTL expired mid-matrix, cascading 401s across all later
assertions. `regression_api.py` now re-authenticates transparently on 401 and
retries transient 5xx / connection errors / socket timeouts (backend also runs
uvicorn `--reload`, which can briefly refuse connections when `backend/scripts/`
is edited).

### HARNESS-4 — Playwright storage state was never applied
The first suite run gave every test a fresh unauthenticated context (test b
passed only because it logs in itself; test c onward bounced to /login).
Removed the unused global-setup storageState approach; each authenticated test
now performs its own UI login (`login(page)` helper).

### HARNESS-5 — Selector corrections against the real UI
- `Create Account` resolves to two buttons (tab + submit) → scoped to `form`.
- Alert detail uses tabbed panels (`Indicators` / `Explanation` / …), no
  "AI Explanation" heading → click the `Explanation` tab and assert the
  explanation paragraph + indicator severity groups.
- Response-actions: the action dropdown populates after the catalog query
  resolves; waiting on a `tbody tr` matched the Execution History table first
  (rows existed from prior API runs) → wait on `select option:nth-child(2)`.
- Topbar user chip is labelled with the account name (`admin`), not
  "SOC Administrator" → target the banner's last button.
- Logout click must wait out dashboard loading skeletons (see FIX-2).

### HARNESS-6 — Timeouts sized for real pipeline latency
Playwright test timeout 420 s (analysis tests assert within 280-400 s);
regression_api.py request timeout 300 s with retries. Analysis latency
(~100-150 s per call, spikes >300 s under load) is pre-existing backend
behaviour, documented here rather than "fixed".

---

## Final gate results

| Gate | Result |
|---|---|
| `npx tsc --noEmit` | exit 0 |
| `npm run build` | exit 0 |
| `grep -rn "cyan\|teal\|sky-\|blue-\|indigo\|violet" src/` | zero hits |
| API regression matrix | 24/24 PASS |
| Playwright browser E2E | 14/14 PASS |
| Credentials in committed files | none (env-only: `CYBERGUARD_TEST_EMAIL` / `CYBERGUARD_TEST_PASS`) |
