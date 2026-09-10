# CYBERGUARD Demo Script

Step-by-step judge walkthrough. Every scenario exercises the full pipeline: **detection → classification → risk score → explanation → alert → recommended response**, with results visible in the UI and via the API.

## Preparation (one-time)

1. Backend on `http://localhost:8000` (`uvicorn app.main:app --reload --port 8000`), frontend on `http://localhost:5173` (`npm run dev`), `frontend/.env` set to `VITE_USE_MOCK=false`.
2. Redis up and the Arq worker running so the deepfake upload demonstrates the queued flow:
   ```bash
   docker compose up -d redis
   cd backend && arq app.workers.settings.WorkerSettings
   ```
   (Without Redis the same upload runs synchronously and answers 200 — say this out loud if demoing without a worker.)
3. Log in as **`admin@cyberguard.local`** (created in Supabase Auth; role assigned by migration 0003). The SOC **Dashboard** loads live from `GET /api/v1/dashboard/summary` (stat cards, risk donut, threat categories, 24-hour attack timeline, incident summary).
4. Automated alternative: `python backend/scripts/demo.py http://localhost:8000 <access_token>`.

---

## Scenario 1 — Phishing / Social Engineering (email)

1. Open **Phishing Analysis** in the sidebar.
2. Click **Load Phishing Sample** (sender `security-alert@micr0soft-verify.xyz`, subject "URGENT: Verify your account immediately", body with an IP-host credential URL) — or paste any email.
3. Click **Analyze Email**.

**Expected result**
- Risk gauge in the **critical** band — the API regression matrix runs exactly this sample and observes `severity=critical` (evaluation report: hybrid email F1 **0.9842** at n=24,000).
- **Indicators** tab: lookalike domain `micr0soft-verify.xyz`, urgency keywords, credential-request phrase, insecure/IP link.
- **Explanation** tab: LLM paragraph starting with the risk level, produced by the provider chain (Groq → OpenRouter → rule-based; the response field `explanation_provider` shows which one answered — if all remote providers fail, a local rule-based explanation is generated and detection still works).
- **MITRE ATT&CK** tab: e.g. T1566.001 Spearphishing Attachment.
- **Recommended Response** tab: actions mapped from the 10-entry response catalog, with `automation_level` and `requires_approval`.
- **Where it appears:** the new alert shows in **Security Alerts** (filter by severity/module/status, full-text search) and increments the Dashboard counters and 24-hour timeline.

**Negative test:** click **Load Benign Sample** and re-run — `safe` band (0–20), no indicators.

## Scenario 2 — Impersonation + deepfake upload (202 queued flow, Realtime toast)

**Part A — Impersonation message**

1. Open **Impersonation Analysis**.
2. Use the CEO-fraud sample: claimed identity "Chief Executive Officer", message demanding urgent, confidential gift-card purchases ("don't tell anyone, keep this between us").
3. Click **Analyze**.

**Expected result:** critical band (authority identity + pressure + unusual financial request + secrecy); indicators `authority_identity`, `pressure_language`, `unusual_request` (critical), `secrecy_request`; MITRE T1656 Impersonation; alert module `impersonation` in **Security Alerts**.

**Part B — Deepfake image upload with the queued (202) flow**

1. Open **Deepfake Detection**.
2. Upload a manipulated image, e.g. `evidence/media/manipulated.png` (≤ 25 MB; images, videos and audio accepted).
3. With Redis + the worker running, the backend answers **202 Accepted**: the page immediately shows the **QueuedAnalysisPanel** pending state ("Queued for background analysis", `status: analyzing`, null risk fields) while the heavy ELA/CNN forensics run on the Arq worker.
4. Moments later the worker persists the alert, Supabase **Realtime** pushes it on the `cyberguard-alerts` channel and a **toast** appears in the open page; the alert then appears in **Security Alerts** and the Dashboard counters.
5. Result panel (this appears directly if demoed without Redis): three gauges — **Authenticity**, **Manipulation Probability**, **Risk** — plus a badge reading **Real forensic analysis** (ELA image forensics blended 50/50 with the CIFAKE CNN) or **Simulated analysis** (non-WAV audio only). `GET /api/v1/events/{event_id}/media-url` returns the 1-hour signed Storage URL.

## Scenario 3 — Technical threat: account takeover or network C2

**Option A — Account takeover.** Open **Account Takeover**, paste:

```json
[
  {"user": "alice", "ip": "10.0.1.45", "location": "New York, US", "device": "Windows-Chrome", "status": "success", "timestamp": "2026-09-08T09:00:00Z"},
  {"user": "alice", "ip": "185.220.101.7", "location": "Moscow, RU", "device": "Linux-Firefox", "status": "failed", "timestamp": "2026-09-08T09:05:00Z"},
  {"user": "alice", "ip": "185.220.101.7", "location": "Moscow, RU", "device": "Linux-Firefox", "status": "failed", "timestamp": "2026-09-08T09:05:30Z"},
  {"user": "alice", "ip": "185.220.101.7", "location": "Moscow, RU", "device": "Linux-Firefox", "status": "failed", "timestamp": "2026-09-08T09:06:00Z"},
  {"user": "alice", "ip": "185.220.101.7", "location": "Moscow, RU", "device": "Linux-Firefox", "status": "success", "timestamp": "2026-09-08T09:07:00Z"}
]
```

**Expected result:** high band from `failed_login_burst` (high), `impossible_travel` NY → Moscow within minutes (critical), `success_after_failures` (high), new/unknown device (medium); MITRE T1110.003; alert module `account_takeover` in **Security Alerts**.

**Option B — Network C2.** Use the Network Threats page or `POST /api/v1/analysis/network` with a flow such as `{"source_ip": "10.0.0.5", "dest_ip": "185.220.101.7", "port": 4444, "bytes_out": 25000000, "protocol": "tcp"}` — C2 port (critical) + exfiltration > 10 MB (high). The regression matrix runs the C2-port sample and observes `risk_score=40`.

---

## Closing the loop

### Incident lifecycle (NIST/SANS state machine, including an illegal-transition rejection)

1. From any alert detail page click **Create Incident** (permission `incident.create`) — the alert is linked, a timeline entry is recorded, and you land on the incident.
2. Walk the state machine via status changes (`incident.update`): TRIAGE → CONTAINMENT → ERADICATION → RECOVERY → CLOSED.
3. **Demonstrate the rejection:** while the incident is in CONTAINMENT, attempt to jump straight to CLOSED — the API answers **400** `Cannot transition from CONTAINMENT to CLOSED. Must go through ERADICATION and RECOVERY first.` and nothing is written. (The legitimate escape hatches: TRIAGE → CLOSED is accepted for a false positive, and CONTAINMENT → TRIAGE is accepted when containment failed.)
4. Note that transitioning to CLOSED additionally requires the `incident.close` permission (`403 Missing permission: incident.close` otherwise).
5. Assign an analyst (**Assign**, `incident.update`) and use **Escalate** (`incident.escalate`, reason requested — sets severity to critical). Every step appends to the incident timeline and the audit trail; the incident summary panel on the Dashboard updates.

### Destructive response with approval

1. Open **Response Actions**; the seeded catalog shows 10 actions with automation level and approval requirements.
2. Execute **Block suspicious IP/device** against `185.220.101.7` **without** checking the approval box → the API refuses with **403**:
   - as admin: `"This action requires explicit approval"` (approval is mandatory even for admins);
   - as analyst/viewer: `"Missing permission: response.execute_destructive"` (and the UI shows the "Requires destructive-response permission" tooltip).
3. Check the approval box and execute as admin → the execution is recorded (`executed`, with `approved_by`) and appears immediately in **Execution History** and in **Audit Logs**.

### Viewer read-only demonstration

Sign out and sign in as **`viewer@cyberguard.local`** (permission matrix from migration 0005):
- Dashboards, alerts, incidents and reports are readable (`dashboard.view`, `alerts.view`, `incidents.view`, `reports.view`).
- Every analysis/ingestion endpoint returns `403 Missing permission: analysis.run`; destructive responses need `response.execute_destructive` and the admin area needs `users.manage` (User Management is hidden in the sidebar) — mutation controls are disabled in the UI.

### SOC assistant

Sign back in as admin and open the **SOC Assistant** (sidebar). Ask *"Show critical alerts"* or *"What should I investigate first?"* — the reply is grounded in recent org alerts and cites the alert IDs used as context (`context_used`).

### Where every result appears

| Result | Where in the dashboard |
|---|---|
| New alerts (all scenarios) | **Security Alerts** list + **Alert Detail** (indicators, explanation, MITRE tags, recommended actions) + Dashboard stat cards / risk donut / threat categories / 24-hour timeline |
| Queued deepfake analysis | QueuedAnalysisPanel → Realtime toast → Alerts |
| Incidents | **Incidents** list + **Incident Detail** (state machine, timeline, linked alerts) + Dashboard incident summary |
| Response executions | **Response Actions** execution history + **Audit Logs** |
| Role changes / mutations | **Admin → User Management** + **Audit Logs** |
| Reports | **Reports** page — export current state as JSON/CSV evidence |

Toggle **Live Alerts** in the topbar at any point: new alert INSERTs stream to the open Dashboard/Alerts page as toasts with automatic refresh (Supabase Realtime).
