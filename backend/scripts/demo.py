"""Run the three mandatory CYBERGUARD demo scenarios against a live backend.

Usage (from the backend directory):
    python scripts/demo.py <backend_url> <auth_token>

Example:
    python scripts/demo.py http://localhost:8000 eyJhbGciOi...

The auth token is a Supabase access token (any logged-in user's JWT).
The script performs real HTTP calls against the /api/v1 analysis
pipelines — the same flow the UI uses — and prints the risk score,
severity, explanation and recommended actions for each scenario.
"""

import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
TIMEOUT_SECONDS = 60.0

PHISHING_EMAIL = {
    "sender": "security-alert@micr0soft-verify.xyz",
    "subject": "URGENT: Verify your account immediately",
    "body": (
        "Your account will be suspended within 24 hours. Click here "
        "http://185.220.101.7/login to verify your password and restore access. "
        "Failure to comply will result in permanent suspension."
    ),
}

IMPERSONATION_MESSAGE = {
    "claimed_identity": "Chief Executive Officer",
    "message": (
        "This is urgent and confidential. I am in a board meeting and cannot call. "
        "Purchase three Amazon gift cards worth $500 each for a client settlement "
        "immediately and send me the codes via this email. Do not inform finance "
        "until I return. This must be done within the hour."
    ),
}

AUTH_LOG_EVENTS = [
    {"user": "alice", "ip": "10.0.1.45", "location": "New York, US", "device": "Windows-Chrome", "status": "success", "timestamp": "2026-09-08T09:00:00Z"},
    {"user": "alice", "ip": "185.220.101.7", "location": "Moscow, RU", "device": "Linux-Firefox", "status": "failed", "timestamp": "2026-09-08T09:05:00Z"},
    {"user": "alice", "ip": "185.220.101.7", "location": "Moscow, RU", "device": "Linux-Firefox", "status": "failed", "timestamp": "2026-09-08T09:05:30Z"},
    {"user": "alice", "ip": "185.220.101.7", "location": "Moscow, RU", "device": "Linux-Firefox", "status": "failed", "timestamp": "2026-09-08T09:06:00Z"},
    {"user": "alice", "ip": "185.220.101.7", "location": "Moscow, RU", "device": "Linux-Firefox", "status": "success", "timestamp": "2026-09-08T09:07:00Z"},
]


def banner(title: str) -> None:
    line = "=" * 64
    print(f"\n{line}\n{title}\n{line}")


def print_result(result: dict) -> None:
    print(f"  Alert ID       : {result.get('alert_id', 'n/a')}")
    print(f"  Module         : {result.get('module', 'n/a')}")
    print(f"  Risk score     : {result.get('risk_score', 'n/a')}/100")
    print(f"  Severity       : {result.get('severity', 'n/a')}")
    if result.get("method"):
        print(f"  Method         : {result['method']} (simulated={result.get('simulated')})")
    print(f"  Explanation    : {result.get('explanation', 'n/a')}")
    actions = result.get("recommended_actions") or []
    if actions:
        print("  Recommended actions:")
        for action in actions:
            name = action["action"] if isinstance(action, dict) else str(action)
            approval = " [approval required]" if isinstance(action, dict) and action.get("requires_approval") else ""
            print(f"    - {name}{approval}")
    mitre = result.get("mitre") or []
    if mitre:
        ids = ", ".join(t.get("id", "?") if isinstance(t, dict) else str(t) for t in mitre)
        print(f"  MITRE          : {ids}")
    indicators = result.get("indicators") or []
    if indicators:
        print(f"  Indicators     : {len(indicators)}")
        for indicator in indicators[:6]:
            print(f"    - [{indicator.get('severity')}] {indicator.get('type')}: {indicator.get('value')}")


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 1

    base_url = sys.argv[1].rstrip("/")
    token = sys.argv[2]
    api_root = base_url if base_url.endswith("/api/v1") else f"{base_url}/api/v1"
    headers = {"Authorization": f"Bearer {token}"}
    client = httpx.Client(timeout=TIMEOUT_SECONDS, headers=headers)

    def post(path: str, payload: dict) -> dict:
        response = client.post(f"{api_root}{path}", json=payload)
        if response.status_code >= 400:
            detail = response.json().get("detail", response.text) if "json" in (response.headers.get("content-type") or "") else response.text
            raise SystemExit(f"  ERROR {response.status_code} on POST {path}: {detail}")
        return response.json()

    # Health pre-check
    try:
        health = client.get(f"{api_root}/health").json()
        print(f"Backend health: {health.get('status')} | Supabase connected: {health.get('supabase_connected')}")
    except Exception as exc:
        raise SystemExit(f"  ERROR: backend not reachable at {api_root}: {exc}")

    # --- Scenario 1: Phishing ---
    banner("=== SCENARIO 1: PHISHING ===")
    print("POST /analysis/email (lookalike domain, urgency, credential URL)")
    print_result(post("/analysis/email", PHISHING_EMAIL))

    # --- Scenario 2: Impersonation / Deepfake ---
    banner("=== SCENARIO 2: IMPERSONATION / DEEPFAKE ===")
    print("POST /analysis/impersonation (CEO fraud, gift cards, secrecy)")
    print_result(post("/analysis/impersonation", IMPERSONATION_MESSAGE))

    media_path = ROOT / "datasets" / "media" / "manipulated_00.png"
    if media_path.exists():
        print(f"\nPOST /analysis/media (spliced-ELA image: {media_path.name})")
        with media_path.open("rb") as handle:
            response = client.post(
                f"{api_root}/analysis/media",
                files={"file": (media_path.name, handle, "image/png")},
            )
        if response.status_code >= 400:
            raise SystemExit(f"  ERROR {response.status_code} on POST /analysis/media: {response.text[:300]}")
        print_result(response.json())
    else:
        print("(media sample datasets/media/manipulated_00.png not found — skipping media upload)")

    # --- Scenario 3: Technical threat ---
    banner("=== SCENARIO 3: TECHNICAL THREAT (ACCOUNT TAKEOVER) ===")
    print(f"POST /analysis/account-takeover ({len(AUTH_LOG_EVENTS)} auth events: burst, impossible travel, success-after-failures)")
    print_result(post("/analysis/account-takeover", {"events": AUTH_LOG_EVENTS}))

    banner("DEMO COMPLETE — all three scenarios executed successfully")
    print("Alerts are persisted in Supabase and visible in the dashboard and on the Alerts page.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
