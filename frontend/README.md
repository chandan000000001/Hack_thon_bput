# CYBERGUARD — SOC Command Dashboard (Frontend)

AI Powered Cyber Threat, Phishing & Digital Impersonation Detection and Response System — **frontend prototype with dual data modes**: live Supabase Auth + backend API, or the fully self-contained in-browser mock layer behind an environment flag.

## Quick Start

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 and log in:

```
Email:    admin@cyberguard.local
Password: demo1234
```

Production build (zero TypeScript errors, strict mode):

```bash
npm run build
npm run preview
```

## Mock Mode

- `VITE_USE_MOCK=true` (default, see `.env`) routes every API call through `src/services/mockApi.ts`, which wraps the in-browser mock database (`mockData.ts`) and the heuristic analysis engine (`mockEngine.ts`) with a simulated 400–900 ms network delay.
- The detection engine is **rule-based and deterministic**: the same input always produces the same risk score. Benign samples score low; malicious samples score high.
- A cyan **MOCK MODE** badge is always visible in the topbar.
- **Live Simulation** (topbar toggle) generates a new randomized alert every 20 seconds with a toast notification.

### Score Bands

| Score | Severity | Color |
|---|---|---|
| 0–20 | Safe | emerald-500 |
| 21–40 | Low | yellow-500 |
| 41–60 | Medium | amber-500 |
| 61–80 | High | orange-500 |
| 81–100 | Critical | red-500 |

## Page Map

| Route | Page | Description |
|---|---|---|
| `/login` | Login | Demo-credential auth against the mock API |
| `/dashboard` | SOC Dashboard | 6 stat cards, risk donut, category bars, 24h attack timeline, incident summary, top targeted users/services, recent alerts (auto-refresh 30s) |
| `/phishing` | Phishing Analysis | Email heuristic analysis: lookalike domains, urgency, credential/payment requests, embedded URL checks, brand mismatch |
| `/url-analysis` | URL Analysis | Lexical URL analysis with breakdown, risk-contributing feature table and simulated redirect chain |
| `/impersonation` | Impersonation | BEC detection: authority claims, urgency, secrecy demands, unusual financial/credential requests |
| `/deepfake` | Deepfake Detection | File upload (image/audio/video ≤ 25 MB) with deterministic authenticity/manipulation gauges |
| `/account-takeover` | Account Takeover | Login-event table, failed-logins chart, JSON auth-log analyzer (brute force, spraying, impossible travel) |
| `/network-threats` | Network & API | Tabbed flows/API logs with filters, expandable detail panels and outbound volume chart |
| `/alerts` | Alerts | Filterable, sortable, searchable alert table with show-more paging |
| `/alerts/:id` | Alert Detail | Risk gauge, indicators, AI explanation, MITRE ATT&CK tab, response actions, create-incident flow |
| `/incidents` | Incidents | Status-filtered incident list |
| `/incidents/:id` | Incident Detail | Assignment, status transitions, escalation, timeline, linked alerts |
| `/response-actions` | Response Actions | Action catalog, simulated executor (approval-gated), execution history |
| `/audit-logs` | Audit Logs | Searchable full audit trail (response executions are audit-logged) |
| `/reports` | Reports | Summary cards + client-side JSON and CSV export downloads |
| `/settings` | Settings | Profile, mock-mode/backend URL, risk threshold reference, about |

The **SOC Assistant** slide-over (bottom of the sidebar) answers context-aware questions from the mock database — try "Summarize today's threats", "Show critical alerts", "List MITRE techniques detected", or "What should I investigate first?".

## Environment Variables

All four are Vite environment variables read at build/dev time from `frontend/.env` (see `.env`):

| Variable | Meaning |
|---|---|
| `VITE_USE_MOCK` | Master data-source flag. Any value other than exactly `false` (including unset) enables mock mode; set to `false` to use live Supabase Auth + the backend API. |
| `VITE_API_BASE_URL` | Base URL of the CYBERGUARD FastAPI backend, e.g. `http://localhost:8000/api/v1`. |
| `VITE_SUPABASE_URL` | Your Supabase project URL. Used by `src/lib/supabaseClient.ts` for authentication. |
| `VITE_SUPABASE_ANON_KEY` | Your Supabase **anon** (public) key. Requests are scoped by Row Level Security. **Never place the Supabase service role key in the frontend.** |

## Real Backend Mode (`VITE_USE_MOCK=false`)

- **Login is real**: the auth store (`src/store/authStore.ts`) signs users in with `supabase.auth.signInWithPassword`, using **Supabase Auth users created in the Supabase dashboard** (e.g. `admin@cyberguard.local`). The session is persisted by `@supabase/supabase-js` and restored on app start via `supabase.auth.getSession()`.
- The browser sends the Supabase access token as `Authorization: Bearer <token>` on every API call (`src/services/http.ts`). On a 401, the token is refreshed once and the request retried; if the refresh fails, the user is signed out.
- **Live reads**: Dashboard and Alerts pages (including alert status changes) call the real backend through the facade in `src/services/api.ts`, with snake_case responses mapped to camelCase in `src/services/mappers.ts`.
- **Mock fallback**: endpoints not yet integrated in real mode still serve mock data, with a `[CYBERGUARD] endpoint not yet integrated, using mock:` console warning, so no page breaks during phased integration.
- Set `VITE_USE_MOCK=true` (or remove it) at any time to return to the fully self-contained mock demo.

### Roles & Authentication Flows

Three roles are enforced by the backend (`profiles.role`) and mirrored in the UI:

| Role | Level | Can do |
|---|---|---|
| **viewer** | 1 | Read-only: dashboards, alerts, incidents, reports. All submit/execute/status-change controls are disabled with a "Read-only role" tooltip and a banner on each page. |
| **analyst** | 2 | Everything viewer can, plus run analyses, ingest events, change alert statuses, execute response actions, and manage incidents. |
| **admin** | 3 | Everything analyst can, plus **Admin → User Management** (`/admin/users`) to change other users' roles (audit-logged, self-demote blocked). |

- The role comes from the `profiles` table (fetched via `GET /auth/me` after every login and session restore). A missing profile falls back to **viewer**.
- **Sign-up default role is viewer**: "Create Account" on the Login page calls `supabase.auth.signUp` with the full name stored in the user metadata. New sign-ups get the `viewer` role until an admin elevates them.
- **Forgot / Reset Password**: "Forgot Password" sends a Supabase reset email pointing at `/reset-password`, where the user sets a new password (`supabase.auth.updateUser`) and is returned to the sign-in page.
- **Required Supabase configuration** (Authentication → URL Configuration):
  - **Site URL**: your app origin, e.g. `http://localhost:5173` (or the deployed URL).
  - **Redirect URLs** must include `<origin>/reset-password` (e.g. `http://localhost:5173/reset-password`) — otherwise the reset email link will not return to the app.
- Seeded demo accounts (roles assigned by `backend/db/migrations/0003_roles_and_seed.sql`): `admin@cyberguard.local`, `analyst@cyberguard.local`, `viewer@cyberguard.local`. In **mock mode** the role defaults to `admin` so every feature stays testable without a backend.

## Tech Stack

- Vite 5 + React 18 + TypeScript (strict: `noUnusedLocals`, `noUnusedParameters`)
- Tailwind CSS (dark SOC theme, slate-950 / cyan-500 accent)
- react-router-dom v6
- Recharts (donut, bar, area charts)
- lucide-react (all icons)
- Zustand (auth store with localStorage persistence + UI store with toasts/live simulation)

## Folder Structure

```
frontend/
├── package.json / tsconfig*.json / vite.config.ts / tailwind.config.js / postcss.config.js
├── index.html / .env / README.md
└── src/
    ├── main.tsx / App.tsx / index.css / constants.ts / vite-env.d.ts
    ├── types/index.ts            # shared interfaces
    ├── services/
    │   ├── mockData.ts           # 27 alerts, 8 incidents, 32 logins, 22 flows, 18 API logs, 32 audit entries
    │   ├── mockEngine.ts         # 7 heuristic detectors + scoring helpers
    │   ├── mockApi.ts            # async mock API + SOC assistant + live-sim generator
    │   └── api.ts                # single facade (mock ⇄ real backend)
    ├── store/                    # authStore, uiStore (zustand)
    ├── hooks/useApi.ts           # loading/error/data/refetch hook
    ├── components/
    │   ├── layout/               # Sidebar, Topbar, MainLayout, ProtectedRoute, SocAssistant
    │   └── common/               # StatCard, SeverityBadge, RiskGauge, DataTable, IndicatorList,
    │                             # ExplanationPanel, RecommendedActionsPanel, MitreTags, ChartCard,
    │                             # StatusPill, EmptyState, LoadingSkeleton, PageHeader, Toast, FileUpload
    └── pages/                    # 16 pages listed in the page map
```

## Notes & Limitations

- All data is **simulated**; all analysis is **heuristic (rule-based)**, not a trained ML model, and all response executions are clearly marked as simulated.
- Response actions marked semi-automatic require an explicit approval checkbox before the execute button enables (human-in-the-loop by design).
- Mock login accepts only the demo credentials; the token is a fake placeholder persisted to `localStorage`.
