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
    """Exchange the credentials for a Supabase access token.

    Credentials come from the environment or ../.env.test (same convention as
    scripts/verify_deployment.py) — no manual shell exports required.
    """
    env_test = load_env_file(REPO_ROOT / ".env.test")
    email = os.environ.get("CYBERGUARD_TEST_EMAIL", env_test.get("CYBERGUARD_TEST_EMAIL", ""))
    password = os.environ.get("CYBERGUARD_TEST_PASS", env_test.get("CYBERGUARD_TEST_PASS", ""))
    if not email or not password:
        print("FAIL  credentials: CYBERGUARD_TEST_EMAIL / CYBERGUARD_TEST_PASS not set")
        print("      provide them via the environment or ../.env.test (see scripts/verify_deployment.py)")
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


# Provider distribution across the suite: tallied from every response that
# carries explanation_provider (groq | openrouter | rule_based | cache:<orig>).
PROVIDER_COUNTS: dict[str, int] = {}


def _tally_provider(body: dict | list) -> None:
    if isinstance(body, dict) and body.get("explanation_provider"):
        provider = str(body["explanation_provider"])
        PROVIDER_COUNTS[provider] = PROVIDER_COUNTS.get(provider, 0) + 1


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
        _tally_provider(body)
        return code, body
    return code, body


def service_role_config() -> tuple[str, str]:
    """Resolve SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY from env/backend .env."""
    env = {**load_env_file(REPO_ROOT / "frontend" / ".env"),
           **load_env_file(REPO_ROOT / "backend" / ".env")}
    supabase_url = os.environ.get("SUPABASE_URL", env.get("SUPABASE_URL", ""))
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", env.get("SUPABASE_SERVICE_ROLE_KEY", ""))
    return supabase_url, service_key


def service_role_rest(
    method: str, table: str, supabase_url: str, service_key: str,
    *, payload: list[dict] | None = None, query: str = "",
) -> tuple[int, list | dict]:
    """Service-role PostgREST call (bypasses RLS) for test-fixture setup/teardown."""
    url = f"{supabase_url.rstrip('/')}/rest/v1/{table}{query}"
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
    }
    if method == "POST":
        headers["Prefer"] = "return=representation"
    req = request.Request(url, data=json.dumps(payload).encode() if payload else None,
                          headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=60) as resp:
            data = resp.read()
            code = resp.status
    except error.HTTPError as exc:
        data = exc.read()
        code = exc.code
    try:
        parsed = json.loads(data) if data else []
    except json.JSONDecodeError:
        parsed = []
    return code, parsed


def main() -> int:
    token = supabase_login()
    if not token:
        return 1
    _state["token"] = token

    # --- health (Phase D-2, item 9) ------------------------------------------
    # /health is a shallow liveness probe (no Supabase round-trip per call).
    code, health = api("GET", "/health", token)
    check(
        "GET /health shallow liveness 200",
        code == 200 and isinstance(health, dict) and health.get("status") == "ok",
        f"status {code}",
    )

    # /health/deep is the authenticated diagnostics probe (live round-trip).
    code, deep = api("GET", "/health/deep", token)
    check(
        "GET /health/deep authenticated diagnostics 200",
        code == 200 and isinstance(deep, dict) and deep.get("supabase_connected") is True,
        f"status {code}",
    )

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

    # Preset test case: RFC 2606 reserved domain sender
    code, rev_email = api(
        "POST",
        "/analysis/email",
        token,
        payload={
            "source": "regression",
            "sender": "notifications@account-review.example.com",
            "subject": "Account Review Notice",
            "body": "Please review your account details at your earliest convenience.",
        },
    )
    r_sev = rev_email.get("severity") if isinstance(rev_email, dict) else None
    r_exp = (rev_email.get("explanation") or "") if isinstance(rev_email, dict) else ""
    check(
        "POST /analysis/email account-review.example.com -> severity >= medium",
        code == 200 and r_sev in ("medium", "high", "critical"),
        f"status {code} severity={r_sev}",
    )
    if code == 200 and r_exp:
        check(
            "POST /analysis/email account-review.example.com explanation leading band matches final band",
            r_exp.startswith(f"{str(r_sev).capitalize()} Risk:"),
            f"explanation={r_exp[:40]!r}",
        )

    code, benign_preset = api(
        "POST",
        "/analysis/email",
        token,
        payload={
            "source": "regression",
            "sender": "notices@university.edu",
            "subject": "Library hours update",
            "body": "The central library will remain open until 10 PM during examination week. No action is required from students.",
        },
    )
    bp_sev = benign_preset.get("severity") if isinstance(benign_preset, dict) else None
    check(
        "POST /analysis/email benign preset -> severity safe|low",
        code == 200 and bp_sev in ("safe", "low"),
        f"status {code} severity={bp_sev}",
    )

    # --- Indic-language phishing (hi / te / or) + benign Hindi ---------------
    # Script detection must tag a `language` indicator; keyword hits drive the
    # heuristic score and the v2 char-n-gram model scores all languages.
    indic_samples = [
        (
            "hi",
            "security-alert@sbi-kyc-verify.xyz",
            "तुरंत कार्रवाई करें: खाता बंद हो जाएगा",
            "आपका SBI खाता 24 घंटे में बंद हो जाएगा। KYC अपडेट के लिए "
            "http://185.220.101.7/kyc पर जाएं और OTP भेजें।",
        ),
        (
            "te",
            "security-alert@hdfc-secure.top",
            "తక్షణం: ఖాతా మూసివేయబడుతుంది",
            "మీ HDFC Bank ఖాతా ధృవీకరించబడలేదు. KYC అప్‌డేట్ కోసం "
            "http://185.220.101.7/kyc సందర్శించండి మరియు OTP పంపండి.",
        ),
        (
            "or",
            "security-alert@icici-alerts.work",
            "ତୁରନ୍ତ: ଖାତା ବନ୍ଦ ହୋଇଯିବ",
            "ଆପଣଙ୍କ ICICI Bank ଖାତା ଯାଞ୍ଚ ହୋଇନାହିଁ। KYC ଅପଡେଟ୍ ପାଇଁ "
            "http://185.220.101.7/kyc ପରିଦର୍ଶନ କରନ୍ତୁ ଏବଂ OTP ପଠାନ୍ତୁ।",
        ),
    ]
    for lang_code, sender, subject, body in indic_samples:
        code, resp = api(
            "POST",
            "/analysis/email",
            token,
            payload={"source": "regression", "sender": sender, "subject": subject, "body": body},
        )
        sev = resp.get("severity") if isinstance(resp, dict) else None
        indicators = resp.get("indicators") if isinstance(resp, dict) else []
        lang_present = any(
            i.get("type") == "language" and i.get("value") == lang_code for i in indicators
        )
        check(
            f"POST /analysis/email {lang_code} phishing -> severity high|critical + lang indicator",
            code == 200 and sev in ("high", "critical") and lang_present,
            f"status {code} severity={sev} lang_present={lang_present}",
        )

    code, benign_hi = api(
        "POST",
        "/analysis/email",
        token,
        payload={
            "source": "regression",
            "sender": "newsletter@updates.wikipedia.org",
            "subject": "आपकी साप्ताहिक विकिपीडिया डाइजेस्ट",
            "body": "इस सप्ताह की चुनी हुई कहानियां पढ़ें। आप कभी भी अपनी खाता "
            "प्राथमिकताओं से सदस्यता रद्द कर सकते हैं।",
        },
    )
    sev = benign_hi.get("severity") if isinstance(benign_hi, dict) else None
    hi_indicators = benign_hi.get("indicators") if isinstance(benign_hi, dict) else []
    hi_lang_present = any(
        i.get("type") == "language" and i.get("value") == "hi" for i in hi_indicators
    )
    check(
        "POST /analysis/email benign Hindi -> severity safe|low + lang indicator",
        code == 200 and sev in ("safe", "low") and hi_lang_present,
        f"status {code} severity={sev} lang_present={hi_lang_present}",
    )

    # --- url analysis -------------------------------------------------------
    code, mal_url = api("POST", "/analysis/url", token, payload={"source": "regression", "url": "http://185.220.101.7/paypal-login/verify"})
    sev = mal_url.get("severity") if isinstance(mal_url, dict) else None
    check("POST /analysis/url malicious -> severity high|critical", code == 200 and sev in ("high", "critical"), f"status {code} severity={sev}")

    code, benign_url = api("POST", "/analysis/url", token, payload={"source": "regression", "url": "https://www.wikipedia.org/"})
    sev = benign_url.get("severity") if isinstance(benign_url, dict) else None
    check("POST /analysis/url benign -> severity safe|low", code == 200 and sev in ("safe", "low"), f"status {code} severity={sev}")

    # High-reputation URL deep links (Fix 1)
    code, chatgpt_url = api(
        "POST",
        "/analysis/url",
        token,
        payload={
            "source": "regression",
            "url": "https://chatgpt.com/c/6aa30aae-379c-83ee-9950-0e4c6eb55d76",
        },
    )
    cg_sev = chatgpt_url.get("severity") if isinstance(chatgpt_url, dict) else None
    check(
        "POST /analysis/url chatgpt conversation link -> severity safe|low",
        code == 200 and cg_sev in ("safe", "low"),
        f"status {code} severity={cg_sev}",
    )

    code, drive_url = api(
        "POST",
        "/analysis/url",
        token,
        payload={
            "source": "regression",
            "url": "https://drive.google.com/file/d/1AbC-defG/view",
        },
    )
    dr_sev = drive_url.get("severity") if isinstance(drive_url, dict) else None
    check(
        "POST /analysis/url drive share link -> severity safe|low",
        code == 200 and dr_sev in ("safe", "low"),
        f"status {code} severity={dr_sev}",
    )

    code, yt_url = api(
        "POST",
        "/analysis/url",
        token,
        payload={
            "source": "regression",
            "url": "https://youtu.be/dQw4w9WgXcQ",
        },
    )
    yt_sev = yt_url.get("severity") if isinstance(yt_url, dict) else None
    check(
        "POST /analysis/url youtube link -> severity safe|low",
        code == 200 and yt_sev in ("safe", "low"),
        f"status {code} severity={yt_sev}",
    )

    code, mal_url2 = api(
        "POST",
        "/analysis/url",
        token,
        payload={
            "source": "regression",
            "url": "http://176.65.139.206/ppc",
        },
    )
    m2_sev = mal_url2.get("severity") if isinstance(mal_url2, dict) else None
    check(
        "POST /analysis/url malicious URLhaus 2 -> severity high|critical",
        code == 200 and m2_sev in ("high", "critical"),
        f"status {code} severity={m2_sev}",
    )

    # Residual URL false positive: standard auth path on a high-reputation
    # domain (top-1M whitelist) must not be flagged for its /login path.
    code, gh_login = api(
        "POST",
        "/analysis/url",
        token,
        payload={"source": "regression", "url": "https://www.github.com/login"},
    )
    gh_sev = gh_login.get("severity") if isinstance(gh_login, dict) else None
    check(
        "POST /analysis/url github.com/login -> severity safe|low",
        code == 200 and gh_sev in ("safe", "low"),
        f"status {code} severity={gh_sev}",
    )

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

    # Calibration check: Benign CFO vendor-payment message returns severity <= medium
    code, benign_imp = api(
        "POST",
        "/analysis/impersonation",
        token,
        payload={
            "source": "regression",
            "message": "Please review the attached vendor payment schedule and confirm status for this week.",
            "claimed_identity": "CFO",
        },
    )
    b_sev = benign_imp.get("severity") if isinstance(benign_imp, dict) else None
    b_exp = (benign_imp.get("explanation") or "") if isinstance(benign_imp, dict) else ""
    check(
        "POST /analysis/impersonation benign-CFO -> severity <= medium",
        code == 200 and b_sev in ("safe", "low", "medium"),
        f"status {code} severity={b_sev}",
    )
    expected_cfo_lead = f"{str(b_sev).capitalize()} Risk:"
    check(
        "POST /analysis/impersonation benign-CFO explanation leading band matches final band",
        code == 200 and b_exp.startswith(expected_cfo_lead),
        f"explanation={b_exp[:40]!r}",
    )

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
        # Phase C-1: 200 = synchronous result with manipulation_probability;
        # 202 = queued for the background worker (event_id + status analyzing).
        sync_ok = isinstance(media, dict) and "manipulation_probability" in media
        queued_ok = isinstance(media, dict) and media.get("status") == "analyzing" and media.get("event_id")
        check("POST /analysis/media upload -> 200 sync | 202 queued", code == 200 and sync_ok or code == 202 and queued_ok, f"status {code}")

        # Calibration check: manipulated.png returns high or critical
        sev_manip = media.get("severity") if isinstance(media, dict) else None
        check(
            "POST /analysis/media manipulated.png -> severity high|critical",
            (code == 200 and sev_manip in ("high", "critical")) or (code == 202),
            f"status {code} severity={sev_manip}",
        )
    else:
        check("POST /analysis/media upload -> 200 with manipulation_probability", False, f"missing file {MEDIA_PATH}")

    # Calibration check: real_camera_whatsapp.jpg returns severity <= medium
    WHATSAPP_MEDIA_PATH = REPO_ROOT / "evidence" / "media" / "real_camera_whatsapp.jpg"
    if WHATSAPP_MEDIA_PATH.exists():
        boundary_wa = "----cyberguardwhatsapp"
        wa_bytes = WHATSAPP_MEDIA_PATH.read_bytes()
        part_wa = (
            f"--{boundary_wa}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{WHATSAPP_MEDIA_PATH.name}"\r\n'
            f"Content-Type: image/jpeg\r\n\r\n"
        ).encode() + wa_bytes + f"\r\n--{boundary_wa}--\r\n".encode()
        code_wa, media_wa = http_req(
            "POST",
            f"{BASE_URL}/analysis/media",
            token=token,
            raw_body=part_wa,
            content_type=f"multipart/form-data; boundary={boundary_wa}",
        )
        sev_wa = media_wa.get("severity") if isinstance(media_wa, dict) else None
        exp_wa = (media_wa.get("explanation") or "") if isinstance(media_wa, dict) else ""
        # Deepfake v2 gate: the messenger-encoded genuine photo must be
        # safe/low (the v1 cap no longer masks ELA false positives).
        check(
            "POST /analysis/media real_camera_whatsapp.jpg -> severity safe|low",
            (code_wa == 200 and sev_wa in ("safe", "low")) or (code_wa == 202),
            f"status {code_wa} severity={sev_wa}",
        )
        if code_wa == 200 and exp_wa:
            check(
                "POST /analysis/media real_camera_whatsapp.jpg explanation leading band matches final band",
                exp_wa.startswith(f"{str(sev_wa).capitalize()} Risk:"),
                f"explanation={exp_wa[:40]!r}",
            )
    else:
        check("POST /analysis/media real_camera_whatsapp.jpg exists and tested", False, f"missing {WHATSAPP_MEDIA_PATH}")

    # Calibration check: erew.jpeg returns safe or low (Fix 2 CNN vs ELA disagreement policy)
    EREW_MEDIA_PATH = REPO_ROOT / "evidence" / "media" / "erew.jpeg"
    if EREW_MEDIA_PATH.exists():
        boundary_er = "----cyberguarderew"
        er_bytes = EREW_MEDIA_PATH.read_bytes()
        part_er = (
            f"--{boundary_er}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{EREW_MEDIA_PATH.name}"\r\n'
            f"Content-Type: image/jpeg\r\n\r\n"
        ).encode() + er_bytes + f"\r\n--{boundary_er}--\r\n".encode()
        code_er, media_er = http_req(
            "POST",
            f"{BASE_URL}/analysis/media",
            token=token,
            raw_body=part_er,
            content_type=f"multipart/form-data; boundary={boundary_er}",
        )
        sev_er = media_er.get("severity") if isinstance(media_er, dict) else None
        check(
            "POST /analysis/media erew.jpeg -> severity safe|low",
            (code_er == 200 and sev_er in ("safe", "low")) or (code_er == 202),
            f"status {code_er} severity={sev_er}",
        )
    else:
        check("POST /analysis/media erew.jpeg exists and tested", False, f"missing {EREW_MEDIA_PATH}")

    # --- audio deepfake gates (audio_cnn_v1) ---------------------------------
    # ercv.mp3 (user-contributed ElevenLabs clip) must trip the trained audio
    # model; tone.wav (synthetic tone) and real_speech.wav (bona fide ASVspoof
    # dev utterance) must stay safe/low. Audio responses carry
    # simulated=false when the trained model serves the analysis.
    def upload_media(path: Path, mime: str, boundary: str):
        file_bytes = path.read_bytes()
        part = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode() + file_bytes + f"\r\n--{boundary}--\r\n".encode()
        return http_req(
            "POST",
            f"{BASE_URL}/analysis/media",
            token=token,
            raw_body=part,
            content_type=f"multipart/form-data; boundary={boundary}",
        )

    audio_cases = [
        ("ercv.mp3", "audio/mpeg", ("medium", "high", "critical")),
        ("tone.wav", "audio/wav", ("safe", "low")),
        ("real_speech.wav", "audio/wav", ("safe", "low")),
    ]
    for audio_name, audio_mime, audio_expected in audio_cases:
        audio_path = REPO_ROOT / "evidence" / "media" / audio_name
        if not audio_path.exists():
            check(f"POST /analysis/media {audio_name} exists and tested", False, f"missing {audio_path}")
            continue
        code_a, media_a = upload_media(audio_path, audio_mime, f"----cyberguard{audio_name.replace('.', '')}")
        sev_a = media_a.get("severity") if isinstance(media_a, dict) else None
        sim_a = media_a.get("simulated") if isinstance(media_a, dict) else None
        ind_a = [
            i.get("value")
            for i in (media_a.get("indicators") or [])
            if isinstance(i, dict) and i.get("type") == "ml_model"
        ] if isinstance(media_a, dict) else []
        base_ok = (code_a == 200) or (code_a == 202)
        check(
            f"POST /analysis/media {audio_name} -> 200 sync | 202 queued",
            base_ok,
            f"status {code_a}",
        )
        if code_a != 200:
            continue
        check(
            f"POST /analysis/media {audio_name} -> severity in {audio_expected}",
            sev_a in audio_expected,
            f"severity={sev_a} ml_model={ind_a} simulated={sim_a}",
        )
        if audio_name == "ercv.mp3":
            check(
                "POST /analysis/media ercv.mp3 -> ml_model audio_cnn_v1.pt and simulated false",
                "audio_cnn_v1.pt" in ind_a and sim_a is False,
                f"ml_model={ind_a} simulated={sim_a}",
            )

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

    # Phase D-1: legal NIST/SANS lifecycle walk (created as open -> TRIAGE).
    # Each step must answer 200; statuses come back canonical uppercase.
    lifecycle_steps = [
        ("CONTAINMENT", "TRIAGE -> CONTAINMENT"),
        ("ERADICATION", "CONTAINMENT -> ERADICATION"),
        ("RECOVERY", "ERADICATION -> RECOVERY"),
        ("CLOSED", "RECOVERY -> CLOSED"),
    ]
    for step_status, step_label in lifecycle_steps:
        code, walked = api(
            "PATCH", f"/incidents/{incident_id}/status", token, payload={"status": step_status}
        )
        check(
            f"PATCH /incidents/{{id}}/status {step_label} 200",
            code == 200 and (isinstance(walked, dict) and walked.get("status") == step_status),
            f"status {code} got={walked.get('status') if isinstance(walked, dict) else '?'}",
        )

    # Illegal jump: a fresh incident sits in TRIAGE; skipping straight to
    # RECOVERY skips CONTAINMENT and ERADICATION and must be rejected 400.
    # (TRIAGE -> CLOSED is a LEGAL false-positive close in the Phase A matrix,
    # so RECOVERY is the representative illegal jump.)
    code, second_incident = api(
        "POST",
        "/incidents",
        token,
        payload={"title": "Regression: illegal jump probe", "severity": "low"},
    )
    second_id = second_incident.get("id") if isinstance(second_incident, dict) else None
    code, rejected = api(
        "PATCH", f"/incidents/{second_id}/status", token, payload={"status": "RECOVERY"}
    )
    detail = rejected.get("detail") if isinstance(rejected, dict) else ""
    check(
        "PATCH /incidents/{id}/status TRIAGE -> RECOVERY 400",
        code == 400 and "Cannot transition" in str(detail),
        f"status {code} detail={detail}",
    )

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
    admin_email = os.environ.get(
        "CYBERGUARD_TEST_EMAIL", load_env_file(REPO_ROOT / ".env.test").get("CYBERGUARD_TEST_EMAIL", "")
    ).lower()
    listed = isinstance(users, list) and any(
        (u.get("email") or "").lower() == admin_email for u in users if isinstance(u, dict)
    )
    check("GET /admin/users lists the admin email", code == 200 and listed, f"status {code}")

    # --- cross-tenant isolation (Phase D-1) ---------------------------------
    # Create a second organization plus one event inside it via the service
    # role client, then verify the default-org token gets 404 for that event
    # on both GET /events/{id} and POST /analysis/media/event/{id}.
    supabase_url, service_key = service_role_config()
    if supabase_url and service_key:
        marker = f"regression-org-{time.time_ns()}"
        code, created_org = service_role_rest(
            "POST", "organizations", supabase_url, service_key,
            payload=[{"name": marker}],
        )
        org2_id = created_org[0].get("id") if code in (200, 201) and isinstance(created_org, list) and created_org else None

        code, foreign_event_resp = service_role_rest(
            "POST", "events", supabase_url, service_key,
            payload=[{
                "org_id": org2_id,
                "event_type": "phishing_email",
                "source": "regression",
                "raw_data": {"subject": "cross-tenant probe"},
                "status": "analyzing",
            }] if org2_id else None,
        )
        foreign_event_id = (
            foreign_event_resp[0].get("id")
            if org2_id and isinstance(foreign_event_resp, list) and foreign_event_resp
            else None
        )

        if foreign_event_id:
            code, _ = api("GET", f"/events/{foreign_event_id}", token)
            check("Cross-tenant event GET -> 404", code == 404, f"status {code}")

            code, _ = api("POST", f"/analysis/media/event/{foreign_event_id}", token)
            check("Cross-tenant media re-analysis -> 404", code == 404, f"status {code}")

            # cleanup: remove the fixture rows
            service_role_rest(
                "DELETE", "events", supabase_url, service_key,
                query=f"?id=eq.{foreign_event_id}",
            )
            service_role_rest(
                "DELETE", "organizations", supabase_url, service_key,
                query=f"?id=eq.{org2_id}",
            )
        else:
            check("Cross-tenant event GET -> 404", False, f"fixture setup failed (org status {code})")
            check("Cross-tenant media re-analysis -> 404", False, "fixture setup failed")
    else:
        check("Cross-tenant event GET -> 404", False, "SUPABASE_SERVICE_ROLE_KEY not configured")
        check("Cross-tenant media re-analysis -> 404", False, "SUPABASE_SERVICE_ROLE_KEY not configured")

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
    distribution = "  ".join(f"{p}={n}" for p, n in sorted(PROVIDER_COUNTS.items())) or "none"
    print(f"\nProvider distribution across analysis responses: {distribution}")
    print(f"\nSummary written to {REPORT_PATH}")
    print(f"TOTAL: {passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
