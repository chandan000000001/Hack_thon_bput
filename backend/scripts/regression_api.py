"""CYBERGUARD API regression matrix (real mode).

Logs in through the Supabase password grant, then executes the assertion
matrix against the FastAPI backend at http://localhost:8000/api/v1.

Credentials are read from environment variables ONLY:
    CYBERGUARD_TEST_EMAIL
    CYBERGUARD_TEST_PASS
Supabase project config comes from SUPABASE_URL / SUPABASE_ANON_KEY env vars,
falling back to frontend/.env (VITE_SUPABASE_URL / VITE_SUPABASE_ANON_KEY).

Prints PASS/FAIL per assertion line and exits 1 on any FAIL. Writes a summary
table to evidence/reports/regression_api.md.
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import error, request

BASE_URL = os.environ.get("CYBERGUARD_API_BASE", "http://localhost:8000/api/v1")
REPO_ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = REPO_ROOT / "evidence" / "reports" / "regression_api.md"
MEDIA_PATH = REPO_ROOT / "evidence" / "media" / "manipulated.png"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not ok else ""))
    return ok


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def http_req(
    method: str,
    url: str,
    *,
    token: str | None = None,
    payload: dict | None = None,
    raw_body: bytes | None = None,
    content_type: str | None = None,
) -> tuple[int, dict | list | bytes]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = None
    if payload is not None:
        body = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    elif raw_body is not None:
        body = raw_body
        if content_type:
            headers["Content-Type"] = content_type
    req = request.Request(url, data=body, headers=headers, method=method)
    try:
        # Analysis endpoints run heuristic + ML scoring + an LLM call; the
        # first call also pays one-time model-loading cost, so allow 300s.
        with request.urlopen(req, timeout=300) as resp:
            data = resp.read()
            code = resp.status
    except error.HTTPError as exc:
        data = exc.read()
        code = exc.code
    try:
        parsed = json.loads(data) if data else {}
    except json.JSONDecodeError:
        parsed = data
    return code, parsed


def password_grant() -> str | None:
    """Exchange the env credentials for a Supabase access token."""
    email = os.environ.get("CYBERGUARD_TEST_EMAIL", "")
    password = os.environ.get("CYBERGUARD_TEST_PASS", "")
    if not email or not password:
        print("FAIL  credentials: CYBERGUARD_TEST_EMAIL / CYBERGUARD_TEST_PASS not set")
        sys.exit(2)

    env = {**load_env_file(REPO_ROOT / "frontend" / ".env"),
           **load_env_file(REPO_ROOT / "backend" / ".env")}
    supabase_url = os.environ.get("SUPABASE_URL", env.get("VITE_SUPABASE_URL", env.get("SUPABASE_URL", "")))
    anon_key = os.environ.get("SUPABASE_ANON_KEY", env.get("VITE_SUPABASE_ANON_KEY", env.get("SUPABASE_ANON_KEY", env.get("SUPABASE_KEY", ""))))
    if not supabase_url or not anon_key:
        print("FAIL  supabase config: SUPABASE_URL / SUPABASE_ANON_KEY not resolvable")
        sys.exit(2)

    url = f"{supabase_url.rstrip('/')}/auth/v1/token?grant_type=password"
    req = request.Request(
        url,
        data=json.dumps({"email": email, "password": password}).encode(),
        headers={"apikey": anon_key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=60) as resp:
            body = json.loads(resp.read())
            return body.get("access_token")
    except error.HTTPError:
        return None


def supabase_login() -> str | None:
    token = password_grant()
    check(
        "Supabase password grant login",
        bool(token),
        "no access_token",
    )
    return token


# Mutable token holder: the project's Supabase JWT TTL is shorter than the
# cumulative runtime of several 100s+ analysis calls, so api() re-authenticates
# transparently whenever the backend answers 401.
_state: dict[str, str | None] = {"token": None}


def api(method: str, path: str, token: str, **kwargs) -> tuple[int, dict | list]:
    code: int = 0
    body: dict | list = {}
    for attempt in range(3):
        try:
            code, body = http_req(method, f"{BASE_URL}{path}", token=_state["token"], **kwargs)
        except (error.URLError, TimeoutError, OSError) as exc:
            # Transient connection error or socket timeout (analysis latency
            # can spike past 300s when ML scoring + LLM calls queue up).
            if attempt < 2:
                time.sleep(5)
                continue
            raise
        if code == 401 and attempt < 2:
            _state["token"] = password_grant()
            if not _state["token"]:
                break
            continue
        if code >= 500 and attempt < 2:
            time.sleep(3)
            continue
        return code, body
    return code, body


def main() -> int:
    token = supabase_login()
    if not token:
        return 1
    _state["token"] = token

    # --- dashboard ---------------------------------------------------------
    code, summary = api("GET", "/dashboard/summary", token)
    counters_numeric = isinstance(summary, dict) and all(
        isinstance(v, (int, float))
        for k, v in summary.items()
        if k
        in {
            "totalEventsAnalyzed",
            "threatsDetected",
            "phishingAttempts",
            "impersonationAttempts",
            "suspectedDeepfakes",
            "accountTakeoverAttempts",
        }
    )
    check("GET /dashboard/summary 200 with numeric counters", code == 200 and counters_numeric, f"status {code}")

    # --- auth --------------------------------------------------------------
    code, me = api("GET", "/auth/me", token)
    check("GET /auth/me returns role admin", code == 200 and me.get("role") == "admin", f"status {code} role={me.get('role') if isinstance(me, dict) else '?'}")

    # --- email analysis -----------------------------------------------------
    code, mal_email = api(
        "POST",
        "/analysis/email",
        token,
        payload={
            "source": "regression",
            "sender": "security-alert@micr0soft-verify.xyz",
            "subject": "URGENT: verify your account immediately",
            "body": "Your account will be suspended within 24 hours. "
            "Click http://185.220.101.7/login to verify your password and restore access.",
        },
    )
    sev = mal_email.get("severity") if isinstance(mal_email, dict) else None
    check("POST /analysis/email malicious -> severity high|critical", code == 200 and sev in ("high", "critical"), f"status {code} severity={sev}")
    mal_email_id = mal_email.get("id") if isinstance(mal_email, dict) else None

    code, benign_email = api(
        "POST",
        "/analysis/email",
        token,
        payload={
            "source": "regression",
            "sender": "newsletter@updates.wikipedia.org",
            "subject": "Your weekly Wikipedia digest",
            "body": "Here are this week's featured articles. You can unsubscribe at any time from your account preferences page.",
        },
    )
    sev = benign_email.get("severity") if isinstance(benign_email, dict) else None
    check("POST /analysis/email benign -> severity safe|low", code == 200 and sev in ("safe", "low"), f"status {code} severity={sev}")

    # --- url analysis -------------------------------------------------------
    code, mal_url = api("POST", "/analysis/url", token, payload={"source": "regression", "url": "http://185.220.101.7/paypal-login/verify"})
    sev = mal_url.get("severity") if isinstance(mal_url, dict) else None
    check("POST /analysis/url malicious -> severity high|critical", code == 200 and sev in ("high", "critical"), f"status {code} severity={sev}")

    code, benign_url = api("POST", "/analysis/url", token, payload={"source": "regression", "url": "https://www.wikipedia.org/"})
    sev = benign_url.get("severity") if isinstance(benign_url, dict) else None
    check("POST /analysis/url benign -> severity safe|low", code == 200 and sev in ("safe", "low"), f"status {code} severity={sev}")

    # --- impersonation ------------------------------------------------------
    code, imp = api(
        "POST",
        "/analysis/impersonation",
        token,
        payload={
            "source": "regression",
            "message": "This is the CEO. I need an urgent wire transfer of $50,000 to a vendor "
            "before the board meeting. Buy gift cards if the transfer fails. Keep this confidential.",
            "claimed_identity": "CEO",
        },
    )
    sev = imp.get("severity") if isinstance(imp, dict) else None
    check("POST /analysis/impersonation fake-CEO -> severity high|critical", code == 200 and sev in ("high", "critical"), f"status {code} severity={sev}")

    # --- account takeover: six-event impossible travel ----------------------
    # Detector parses ISO-8601 timestamp strings only, so emit strings.
    now_iso = datetime.now(timezone.utc)
    def iso(seconds_ago: int) -> str:
        return (now_iso - timedelta(seconds=seconds_ago)).isoformat()

    ato_events = [
        {"user": "jane.doe@company.com", "status": "failed", "ip": "203.0.113.10", "location": "Mumbai, IN", "device": "Chrome/Windows", "timestamp": iso(300)},
        {"user": "jane.doe@company.com", "status": "failed", "ip": "203.0.113.10", "location": "Mumbai, IN", "device": "Chrome/Windows", "timestamp": iso(240)},
        {"user": "jane.doe@company.com", "status": "success", "ip": "198.51.100.77", "location": "Berlin, DE", "device": "Safari/macOS", "timestamp": iso(180)},
        {"user": "jane.doe@company.com", "status": "failed", "ip": "198.51.100.77", "location": "Berlin, DE", "device": "Safari/macOS", "timestamp": iso(120)},
        {"user": "jane.doe@company.com", "status": "success", "ip": "192.0.2.5", "location": "Sao Paulo, BR", "device": "unknown-device", "timestamp": iso(60)},
        {"user": "jane.doe@company.com", "status": "success", "ip": "192.0.2.9", "location": "Sao Paulo, BR", "device": "unknown-browser", "timestamp": iso(0)},
    ]
    code, ato = api("POST", "/analysis/account-takeover", token, payload={"source": "regression", "events": ato_events})
    sev = ato.get("severity") if isinstance(ato, dict) else None
    check("POST /analysis/account-takeover impossible-travel -> severity high|critical", code == 200 and sev in ("high", "critical"), f"status {code} severity={sev}")

    # --- network: C2 port 4444 ----------------------------------------------
    code, net = api(
        "POST",
        "/analysis/network",
        token,
        payload={
            "source": "regression",
            "flows": [
                {"source_ip": "10.0.0.15", "dest_ip": "185.220.101.7", "port": 4444, "bytes_out": 50_000_000, "protocol": "TCP"},
            ],
        },
    )
    score = net.get("risk_score", net.get("score")) if isinstance(net, dict) else None
    check("POST /analysis/network C2 port 4444 -> risk_score >= 40", code == 200 and isinstance(score, (int, float)) and score >= 40, f"status {code} score={score}")

    # --- media upload --------------------------------------------------------
    if MEDIA_PATH.exists():
        boundary = "----cyberguardregression"
        file_bytes = MEDIA_PATH.read_bytes()
        part = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{MEDIA_PATH.name}"\r\n'
            f"Content-Type: image/png\r\n\r\n"
        ).encode() + file_bytes + f"\r\n--{boundary}--\r\n".encode()
        code, media = http_req(
            "POST",
            f"{BASE_URL}/analysis/media",
            token=token,
            raw_body=part,
            content_type=f"multipart/form-data; boundary={boundary}",
        )
        has_prob = isinstance(media, dict) and "manipulation_probability" in media
        check("POST /analysis/media upload -> 200 with manipulation_probability", code == 200 and has_prob, f"status {code}")
    else:
        check("POST /analysis/media upload -> 200 with manipulation_probability", False, f"missing file {MEDIA_PATH}")

    # --- alerts ---------------------------------------------------------------
    code, alerts = api("GET", "/alerts", token)
    alert_list = alerts if isinstance(alerts, list) else []
    check("GET /alerts non-empty", code == 200 and len(alert_list) > 0, f"status {code} count={len(alert_list)}")

    target_alert = None
    for candidate in (mal_email_id, mal_url.get("id") if isinstance(mal_url, dict) else None):
        if candidate and any(a.get("id") == candidate for a in alert_list):
            target_alert = candidate
            break
    if not target_alert and alert_list:
        target_alert = alert_list[0].get("id")

    code, alert_detail = api("GET", f"/alerts/{target_alert}", token)
    check(f"GET /alerts/{{id}} 200 (id={target_alert})", code == 200 and isinstance(alert_detail, dict), f"status {code}")

    code, patched = api("PATCH", f"/alerts/{target_alert}/status", token, payload={"status": "acknowledged"})
    check("PATCH /alerts/{id}/status acknowledged 200", code == 200 and (isinstance(patched, dict) and patched.get("status") == "acknowledged"), f"status {code}")

    # --- incidents -------------------------------------------------------------
    code, incident = api(
        "POST",
        "/incidents",
        token,
        payload={
            "title": "Regression: linked phishing alert",
            "severity": alert_detail.get("severity", "medium") if isinstance(alert_detail, dict) else "medium",
            "linked_alert_ids": [target_alert] if target_alert else [],
        },
    )
    incident_id = incident.get("id") if isinstance(incident, dict) else None
    check("POST /incidents 201 (linked to alert)", code == 201 and bool(incident_id), f"status {code}")

    code, timeline_before = api("GET", f"/incidents/{incident_id}", token)
    tl_len_before = len(timeline_before.get("timeline", [])) if isinstance(timeline_before, dict) else 0

    code, upd = api("PATCH", f"/incidents/{incident_id}/status", token, payload={"status": "investigating"})
    check("PATCH /incidents/{id}/status investigating 200", code == 200 and (isinstance(upd, dict) and upd.get("status") == "investigating"), f"status {code}")

    code, esc = api("POST", f"/incidents/{incident_id}/escalate", token, payload={"reason": "Regression escalation check"})
    check("POST /incidents/{id}/escalate 200", code == 200 and isinstance(esc, dict), f"status {code}")

    code, timeline_after = api("GET", f"/incidents/{incident_id}", token)
    tl_len_after = len(timeline_after.get("timeline", [])) if isinstance(timeline_after, dict) else 0
    check("Incident timeline grows after mutations", tl_len_after > tl_len_before, f"before={tl_len_before} after={tl_len_after}")

    # --- response actions --------------------------------------------------------
    code, catalog = api("GET", "/responses/catalog", token)
    catalog_list = catalog if isinstance(catalog, list) else []
    check("GET /responses/catalog non-empty", code == 200 and len(catalog_list) > 0, f"status {code} count={len(catalog_list)}")

    approval_action = next((c for c in catalog_list if c.get("requires_approval")), None)
    if approval_action:
        catalog_id = approval_action.get("id")
        code, denied = api(
            "POST",
            "/responses/execute",
            token,
            payload={"catalog_id": catalog_id, "target": "regression-target@company.com", "approved": False},
        )
        check("POST /responses/execute without approval -> 403", code == 403, f"status {code}")

        code, approved_res = api(
            "POST",
            "/responses/execute",
            token,
            payload={"catalog_id": catalog_id, "target": "regression-target@company.com", "approved": True},
        )
        check("POST /responses/execute with approval -> 200", code == 200, f"status {code}")
    else:
        check("POST /responses/execute without approval -> 403", False, "no requires_approval action in catalog")
        check("POST /responses/execute with approval -> 200", False, "no requires_approval action in catalog")

    # --- audit logs ------------------------------------------------------------
    code, audit = api("GET", "/audit/logs", token)
    audit_list = audit if isinstance(audit, list) else []
    audit_blob = json.dumps(audit_list).lower() if audit_list else ""
    mutated = target_alert and target_alert.lower() in audit_blob
    check("GET /audit/logs non-empty and includes mutations", code == 200 and len(audit_list) > 0 and mutated, f"status {code} count={len(audit_list)} contains_alert={mutated}")

    # --- assistant --------------------------------------------------------------
    code, chat = api("POST", "/assistant/chat", token, payload={"message": "Summarize the current top risk for the SOC."})
    reply = chat.get("reply") if isinstance(chat, dict) else None
    check("POST /assistant/chat returns non-empty reply", code == 200 and bool(reply and reply.strip()), f"status {code}")

    # --- admin users --------------------------------------------------------------
    code, users = api("GET", "/admin/users", token)
    admin_email = os.environ.get("CYBERGUARD_TEST_EMAIL", "").lower()
    listed = isinstance(users, list) and any(
        (u.get("email") or "").lower() == admin_email for u in users if isinstance(u, dict)
    )
    check("GET /admin/users lists the admin email", code == 200 and listed, f"status {code}")

    # --- report ---------------------------------------------------------------------
    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed
    lines = [
        "# CYBERGUARD API Regression Matrix",
        "",
        f"Run: {time.strftime('%Y-%m-%d %H:%M:%S')} against `{BASE_URL}`",
        "",
        f"**Result: {passed} passed, {failed} failed**",
        "",
        "| # | Assertion | Result | Detail |",
        "|---|-----------|--------|--------|",
    ]
    for i, (name, ok, detail) in enumerate(results, 1):
        lines.append(f"| {i} | {name} | {'PASS' if ok else 'FAIL'} | {detail or '—'} |")
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n")
    print(f"\nSummary written to {REPORT_PATH}")
    print(f"TOTAL: {passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
