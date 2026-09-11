# CYBERGUARD API Reference

Complete reference for the FastAPI backend (`backend/app/api/`), read directly from the routers. Base URL: `http://localhost:8000/api/v1` (configurable via `API_V1_PREFIX`). Interactive docs: `http://localhost:8000/docs`.

**Authentication** — every protected endpoint expects a Supabase Auth bearer token (`Authorization: Bearer <JWT>`). `get_current_user` verifies the token against Supabase Auth (anon client) and resolves the caller's `org_id`; missing/invalid tokens answer **401** with `WWW-Authenticate: Bearer`. Mutating endpoints are additionally gated by **permission keys** from the `role_permissions` matrix (migration 0005) via `require_permission`/`require_permissions`; a caller without the key gets **403** `Missing permission: <key>`. Endpoints marked *authenticated* only require a valid token.

**Global error semantics**

| Status | Meaning |
|---|---|
| 400 | Invalid request payload (custom handler converts FastAPI validation errors to `{"error": "invalid_payload", "message": …, "details": […]}`) or a rejected domain rule (illegal incident transition, unknown status, admin self-demote, bulk > 1000 rows, wrong media content type) |
| 401 | Missing, invalid or expired bearer token |
| 403 | `Missing permission: <key>` (permission matrix) or approval/permission gate |
| 404 | Resource not found **in the caller's organization** — cross-tenant ids resolve to 404 before any data is touched |
| 413 | Media upload exceeds 25 MB |
| 500 | Internal error; raw Supabase/driver error strings never reach the client |

---

## Health — `routes_health.py`

### `GET /health`
*Authenticated: no.*
Shallow liveness probe — no Supabase round-trip per call (connectivity served from a 30-second cache).
```json
{"status": "ok", "version": "0.1.0", "timestamp": "…ISO-8601…", "supabase_connected": true}
```

### `GET /health/deep`
*Authenticated: yes.*
Diagnostics probe performing a live Supabase round-trip; same body plus `"checked_by": "<user_id>"`.

## Auth — `routes_auth.py`

### `GET /auth/me`
*Authenticated: yes.*
Returns the caller's identity, profile role (fallback `viewer`) and permission list from the role matrix.
```json
{"id": "…", "email": "admin@cyberguard.local", "role": "admin", "full_name": "…", "permissions": ["dashboard.view", "…"]}
```

## DB — `routes_db.py`

### `GET /db/check`
*Authenticated: yes.*
Org-scoped row counts for `events`, `alerts`, `incidents`, `audit_logs`.
```json
{"tables": {"events": 42, "alerts": 50, "incidents": 3, "audit_logs": 100}, "org_id": "…"}
```
Failures answer 500 `"database check unavailable"` (raw errors stay server-side).

## Events — `routes_events.py` (raw ingestion)

All `POST /events/*` endpoints require **`analysis.run`** and return:
```json
{"event_id": "…", "event_type": "…", "status": "received"}
```
Every insert carries the caller's `org_id`.

| Endpoint | Body (Pydantic schema) |
|---|---|
| `POST /events/email` | `EmailEvent`: `event_type="phishing_email"`, `source` (min 1), `sender` (min 1), `subject`, `body`, `target_user?` |
| `POST /events/url` | `UrlEvent`: `event_type="malicious_url"`, `source`, `url` (min 1), `target_user?` |
| `POST /events/message` | `MessageEvent`: `event_type="impersonation_message"`, `source`, `sender`, `claimed_identity` (min 1), `message` |
| `POST /events/auth-log` | `AuthLogEvent`: `event_type="account_takeover"`, `source`, `events: list[dict]` |
| `POST /events/network` | `NetworkFlowEvent`: `event_type="network_flow"`, `source`, `flows: list[dict]` |
| `POST /events/api-log` | `ApiLogEvent`: `event_type="api_abuse"`, `source`, `logs: list[dict]` |

### `POST /events/media`
*Permissions: `analysis.run` **and** `media.upload` (two dependency checks).*
Multipart `file` (image/audio/video content type, else **400**). Uploads to the private `cyberguard-media` bucket, inserts the event (`deepfake_media`, status `received`) and a `media_files` row.
```json
{"event_id": "…", "event_type": "deepfake_media", "status": "received", "file_name": "…", "storage_path": "media/<event_id>/<name>"}
```

### `POST /events/bulk`
*Permission: `analysis.run`.* Body: `{"kind": "auth-log" | "network", "rows": [dict, …]}` (min 1 row; > 1000 rows → **400** `"Bulk batch exceeds 1000 rows"`).

- **200** (always — the batch is analysed synchronously on the request thread): `{"event_id": "…", "event_type": "…", "status": "completed" | "failed", "message": "Analyzed synchronously"}`

### `GET /events/{event_id}`
*Authenticated: yes.* Returns the org-scoped event row; **404** when missing or cross-tenant.

### `GET /events/{event_id}/media-url`
*Authenticated: yes.* Org-scoped; returns a 1-hour signed URL for the event's media file.
```json
{"event_id": "…", "file_name": "…", "signed_url": "…", "expires_in_seconds": 3600}
```
**404** when the event or its media file does not exist.

## Analysis — `routes_analysis.py` (full detection pipeline)

All `POST /analysis/*` text/flow endpoints require **`analysis.run`**, run the shared pipeline (event insert status `analyzing` → heuristics → hybrid ML blending → LLM explanation → org-scoped alert + recommended actions) and return the persisted **alert**:

```json
{
  "id": "…", "event_id": "…", "title": "…", "module": "phishing", "threat_type": "…",
  "severity": "critical", "risk_score": 100, "confidence": 0.99, "status": "new",
  "summary": "…", "indicators": [{"type": "…", "value": "…", "severity": "high", "description": "…"}],
  "explanation": "…", "mitre": [{"id": "T1566.001", "name": "…"}],
  "recommended_actions": [{"action": "…", "automation_level": "manual", "requires_approval": false, "priority": "…"}],
  "explanation_provider": "groq | openrouter | rule_based | cache:<provider>",
  "explanation_latency_ms": 0, "target_user": null, "source_ip": null, "created_at": "…"
}
```

| Endpoint | Body | Notes |
|---|---|---|
| `POST /analysis/email` | `EmailAnalysisRequest`: `source="api"`, `sender` (min 1), `subject`, `body`, `target_user?` | module `phishing`, event_type `phishing_email` |
| `POST /analysis/url` | `UrlAnalysisRequest`: `source="api"`, `url` (min 1), `target_user?` | module `url`, event_type `malicious_url` |
| `POST /analysis/impersonation` | `ImpersonationAnalysisRequest`: `source="api"`, `message`, `claimed_identity` (min 1) | module `impersonation` |
| `POST /analysis/account-takeover` | `AccountTakeoverAnalysisRequest`: `source="api"`, `events: list[dict]` | module `account_takeover` |
| `POST /analysis/network` | `NetworkAnalysisRequest`: `source="api"`, `flows: list[dict]` (default `[]`), `api_logs: list[dict]` (default `[]`) | module is `network` when flows are present, else `api_abuse` |

### `POST /analysis/media`
*Permissions: `analysis.run` **and** `media.upload`.*
Multipart `file` (image/video/audio, else **400**; > 25 MB → **413**). Uploads to Storage, records `media_files`, then:

- **200** (always — analysis runs synchronously; the Arq/202 queued flow was removed): full deepfake result plus `event_id`, `alert_id`, `storage_path`, `explanation`, `explanation_provider`, `explanation_latency_ms`, `mitre_techniques`, `recommended_actions`, and the analyzer fields `media_type`, `method`, `simulated`, `authenticity_score`, `manipulation_probability`.

### `POST /analysis/media/event/{event_id}`
*Permissions: `analysis.run` **and** `media.upload`.*
Re-runs the deepfake pipeline for an already-ingested media event, downloading the file from Storage. The event must belong to the caller's org (**404** otherwise, and **404** when no media file exists for it). Response: same shape as the synchronous 200 media result.

### `GET /analysis/alerts`
*Authenticated: yes.* Org-scoped alerts, newest first.
```json
{"count": 3, "alerts": [ …alert rows… ]}
```

### `GET /analysis/alerts/{alert_id}`
*Authenticated: yes.* Single org-scoped alert with `recommended_actions` attached; **404** when missing/cross-tenant. (A recommended-actions query failure never fails the request — the alert is returned with an empty actions list.)

## Alerts — `routes_alerts.py`

### `GET /alerts`
*Authenticated: yes.* Query parameters: `severity?`, `module?`, `status?`, `search?` (full-text over title/summary/explanation, PostgREST `ilike` wildcards escaped), `limit` (1–200, default 50), `offset` (default 0). Returns a list of alert rows (each with `recommended_actions` joined), newest first.

### `GET /alerts/{alert_id}`
*Authenticated: yes.* Single org-scoped alert; **404** when missing/cross-tenant.

### `PATCH /alerts/{alert_id}/status`
*Authenticated: yes.* Body: `{"status": "new" | "acknowledged" | "resolved" | "dismissed"}`. Updates the org-scoped alert and writes an audit-log entry. Returns the updated alert; **404** when missing/cross-tenant.

## Incidents — `routes_incidents.py`

Statuses are governed by the NIST/SANS state machine (`TRIAGE → CONTAINMENT → ERADICATION → RECOVERY → CLOSED`; `TRIAGE → CLOSED` false-positive escape; `CONTAINMENT → TRIAGE` escalate-back). Legacy values `open`/`investigating`/`contained`/`closed` are normalized.

### `GET /incidents`
*Authenticated: yes.* Query: `status_filter?` (optional). Org-scoped incidents, newest activity first; each carries `linked_alert_ids` and `timeline`.

### `GET /incidents/{incident_id}`
*Authenticated: yes.* Org-scoped incident with timeline and linked alerts; **404** when missing/cross-tenant (including non-UUID ids).

### `POST /incidents`
*Permission: `incident.create`.* Body: `{"title": "…", "severity": "safe|low|medium|high|critical", "linked_alert_ids": ["…"]}`. Returns **201** with the created `IncidentResponse`.

### `PATCH /incidents/{incident_id}/status`
*Permission: `incident.update`; transitioning to CLOSED additionally requires `incident.close` (checked in-handler → **403** `Missing permission: incident.close`).*
Body: `{"status": "TRIAGE|CONTAINMENT|ERADICATION|RECOVERY|CLOSED"}` (legacy values accepted). The row is loaded with `FOR UPDATE` locking; an illegal transition returns **400** naming the required path (e.g. `Cannot transition from CONTAINMENT to CLOSED. Must go through ERADICATION and RECOVERY first.`); cross-tenant/non-UUID ids return **404** before anything is written. Returns the updated incident; a timeline event and an audit entry are recorded.

### `PATCH /incidents/{incident_id}/assign`
*Permission: `incident.update`.* Body: `{"assigned_to": "…"}`. Returns the updated incident.

### `POST /incidents/{incident_id}/escalate`
*Permission: `incident.escalate`.* Body: `{"reason": "…"}`. Sets severity to critical with the reason on the timeline. Returns the updated incident.

## Response Actions — `routes_response.py`

### `GET /responses/catalog`
*Authenticated: yes.* The full `response_catalog` (10 seeded actions with `automation_level` and `requires_approval`).

### `POST /responses/execute`
*Permission: `response.execute`; approval-required (destructive) catalog entries additionally require `response.execute_destructive` (**403** `Missing permission: response.execute_destructive` if the caller lacks it, checked before execution).*
Body: `{"catalog_id": "…", "target": "…" (min 1 each), "approved": false}`. Behaviour: unknown catalog id → **404**; approval-required action with `approved: false` → **403** `"This action requires explicit approval"` (nothing is executed); otherwise the action is executed with `approved_by` recorded. All executions are audit-logged. Response:
```json
{"id": "…", "catalog_id": "…", "action_name": "…", "target": "…", "status": "executed", "executed_by": "…", "approved_by": "…", "created_at": "…"}
```

### `GET /responses/history`
*Authenticated: yes.* Query: `limit` (1–200, default 50). Recent executions, newest first.

## Dashboard — `routes_dashboard.py`

### `GET /dashboard/summary`
*Authenticated: yes.* Aggregated metrics for the caller's organization (Python-side grouping):
```json
{"total_events_analyzed": 0, "threats_detected": 0, "phishing_attempts": 0, "impersonation_attempts": 0,
 "suspected_deepfakes": 0, "account_takeover_attempts": 0, "network_threats": 0, "api_abuse_attempts": 0,
 "risk_distribution": [], "threat_categories": [], "attack_timeline": [], "top_targeted_users": [],
 "top_targeted_services": [], "recent_alerts": [], "incident_summary": {}}
```
`attack_timeline` covers the last 24 hours in hourly buckets.

## Audit — `routes_audit.py`

### `GET /audit/logs`
*Permission: `audit.view`.* Query: `limit` (1–500, default 100), `offset` (default 0). Org-scoped audit entries, newest first.

## SOC Assistant — `routes_assistant.py`

### `POST /assistant/chat`
*Authenticated: yes.* Body: `{"message": "…" (min 1)}`. Answers grounded in recent org alerts; the reply cites the alert IDs used as context.
```json
{"reply": "…", "context_used": ["<alert_id>", "…"]}
```

## Admin — `routes_admin.py`

### `GET /admin/users`
*Permission: `users.manage`.* All user profiles, oldest first: `[{"id", "email", "full_name", "role", "created_at"}, …]` (emails live on `profiles`, added by migration 0003).

### `PATCH /admin/users/{user_id}/role`
*Permission: `users.manage`.* Body: `{"role": "viewer" | "analyst" | "admin"}`. Self-demote protection: an admin cannot lower their own role (**400** `"Admins cannot change their own role (lockout prevention)"`); unknown user → **404**. On success the target user's cached role/auth-context/org entries are invalidated immediately (Phase D-2) and the change is audit-logged. Returns the updated profile row.
