#!/usr/bin/env python3
"""CYBERGUARD deployment verification — self-authenticating, no manual exports.

Obtains its own Supabase token via the password grant (credentials from the
environment or ../.env.test — never a shell variable like $TOKEN), exercises
the live deepfake pipeline and asserts the deployment is serving the artifact
named in ml/models/calibration.json.

Exit codes: 0 all checks PASS · 1 assertion failure · 2 missing credentials ·
3 backend unreachable · 4 Supabase authentication failure.

Run from the backend directory:
    uv run python scripts/verify_deployment.py
"""

import json
import mimetypes
import os
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]   # backend/
REPO = ROOT.parent                            # hackathon_01/
BASE_URL = os.environ.get("CYBERGUARD_BACKEND_URL", "http://localhost:8000/api/v1")

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, ok, detail))
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


def load_credentials() -> tuple[str | None, str | None]:
    """CYBERGUARD_TEST_EMAIL / CYBERGUARD_TEST_PASS from env, then ../.env.test."""
    env = {**load_env_file(REPO / ".env.test"), **os.environ}
    return env.get("CYBERGUARD_TEST_EMAIL"), env.get("CYBERGUARD_TEST_PASS")


def supabase_config() -> tuple[str, str]:
    env = {**load_env_file(REPO / "frontend" / ".env"), **load_env_file(ROOT / ".env"), **os.environ}
    url = os.environ.get("SUPABASE_URL", env.get("VITE_SUPABASE_URL", env.get("SUPABASE_URL", "")))
    anon = os.environ.get("SUPABASE_ANON_KEY", env.get("VITE_SUPABASE_ANON_KEY", env.get("SUPABASE_ANON_KEY", "")))
    return url, anon


def password_grant(email: str, password: str, url: str, anon: str) -> str:
    resp = httpx.post(
        f"{url.rstrip('/')}/auth/v1/token?grant_type=password",
        headers={"apikey": anon},
        json={"email": email, "password": password},
        timeout=30,
    )
    if resp.status_code != 200:
        print(f"Supabase authentication failed (HTTP {resp.status_code}): {resp.text[:300]}")
        sys.exit(4)
    token = resp.json().get("access_token")
    if not token:
        print("Supabase authentication failed: no access_token in the grant response")
        sys.exit(4)
    return token


def analyze_media(client: httpx.Client, token: str, path: Path) -> dict | None:
    """POST /analysis/media; on 202 (queued) poll the event until completed."""
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    with path.open("rb") as fh:
        resp = client.post(
            f"{BASE_URL}/analysis/media",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": (path.name, fh, mime)},
            timeout=300,
        )
    if resp.status_code == 202:
        event_id = resp.json().get("event_id")
        for _ in range(30):
            time.sleep(2)
            ev = client.get(
                f"{BASE_URL}/events/{event_id}",
                headers={"Authorization": f"Bearer {token}"},
                timeout=60,
            )
            if ev.status_code == 200 and ev.json().get("status") in ("completed", "failed"):
                break
        alerts = client.get(
            f"{BASE_URL}/alerts",
            headers={"Authorization": f"Bearer {token}"},
            params={"module": "deepfake", "limit": 10},
            timeout=60,
        )
        for alert in alerts.json() if alerts.status_code == 200 else []:
            if alert.get("event_id") == event_id:
                return alert
        return None
    if resp.status_code != 200:
        return {"http_error": resp.status_code, "detail": resp.text[:200]}
    return resp.json()


def main() -> int:
    # --- 1. credentials ------------------------------------------------------
    email, password = load_credentials()
    if not email or not password:
        print("Missing credentials. Provide them in ONE of these ways:")
        print("  export CYBERGUARD_TEST_EMAIL=<supabase-test-user-email>")
        print("  export CYBERGUARD_TEST_PASS=<that-user-password>")
        print("  or create ../.env.test (repo root) containing the lines:")
        print("    CYBERGUARD_TEST_EMAIL=<supabase-test-user-email>")
        print("    CYBERGUARD_TEST_PASS=<that-user-password>")
        print("The script authenticates itself via the Supabase password grant;")
        print("it never reads a shell variable such as $TOKEN.")
        return 2

    # --- 2. liveness ---------------------------------------------------------
    try:
        health = httpx.get(f"{BASE_URL}/health", timeout=10)
        health.raise_for_status()
    except Exception:
        print("backend not running - start it with: uv run uvicorn app.main:app --reload --port 8000")
        return 3

    # --- 3. own token via the password grant ---------------------------------
    supabase_url, anon_key = supabase_config()
    if not supabase_url or not anon_key:
        print("Supabase configuration missing: SUPABASE_URL / SUPABASE_ANON_KEY not resolvable")
        sys.exit(4)
    token = password_grant(email, password, supabase_url, anon_key)
    headers = {"Authorization": f"Bearer {token}"}

    with httpx.Client() as client:
        # --- 4. execute and print --------------------------------------------
        me = client.get(f"{BASE_URL}/auth/me", headers=headers, timeout=60)
        me_role = me.json().get("role") if me.status_code == 200 else None
        me_perm_count = len(me.json().get("permissions", [])) if me.status_code == 200 else 0
        print(f"GET /auth/me -> role={me_role} permissions={me_perm_count}")

        calibration = json.loads((ROOT / "ml" / "models" / "calibration.json").read_text())
        expected_artifact = f"deepfake_cnn_{calibration.get('deepfake_model_version', 'v2')}.pt"

        media_results: dict[str, dict | None] = {}
        for rel in ("evidence/media/real_camera_whatsapp.jpg", "evidence/media/manipulated.png"):
            path = REPO / rel
            if not path.exists():
                path = ROOT / rel
            result = analyze_media(client, token, path)
            media_results[rel] = result
            if result is None:
                print(f"POST /analysis/media {path.name} -> no finished alert (queued/failed)")
            elif "http_error" in result:
                print(f"POST /analysis/media {path.name} -> HTTP {result['http_error']} {result['detail']}")
            else:
                ml_values = [i.get("value") for i in result.get("indicators", []) if i.get("type") == "ml_model"]
                print(
                    f"POST /analysis/media {path.name} -> ml_model={ml_values} "
                    f"severity={result.get('severity')} risk_score={result.get('risk_score')}"
                )

    # --- 5. assertions -------------------------------------------------------
    check("GET /auth/me role == admin", me.status_code == 200 and me_role == "admin", f"role={me_role}")

    whatsapp = media_results.get("evidence/media/real_camera_whatsapp.jpg") or {}
    wa_sev = whatsapp.get("severity")
    check(
        "whatsapp severity in (safe, low)",
        wa_sev in ("safe", "low"),
        f"severity={wa_sev}",
    )

    manipulated = media_results.get("evidence/media/manipulated.png") or {}
    man_sev = manipulated.get("severity")
    check(
        "manipulated severity in (high, critical)",
        man_sev in ("high", "critical"),
        f"severity={man_sev}",
    )

    for rel, result in media_results.items():
        ml_values = [i.get("value") for i in (result or {}).get("indicators", []) if i.get("type") == "ml_model"]
        neural = [v for v in ml_values if v != "heuristics-only-fallback"]
        check(
            f"{Path(rel).name}: ml_model == {expected_artifact} (never deepfake_cnn.pt)",
            neural == [expected_artifact],
            f"ml_model={ml_values}",
        )

    # --- 6. PASS/FAIL table --------------------------------------------------
    print("\n=== Deployment verification ===")
    print(f"{'RESULT':<6} {'CHECK':<70} DETAIL")
    all_pass = True
    for name, ok, detail in results:
        all_pass &= ok
        print(f"{'PASS' if ok else 'FAIL':<6} {name:<70} {detail}")
    print("===============================")
    if all_pass:
        print(f"ALL PASS — deepfake {expected_artifact} is the live inference model")
        return 0
    print("VERIFICATION FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(main())
