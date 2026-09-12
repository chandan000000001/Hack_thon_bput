#!/usr/bin/env python3
"""CYBERGUARD LLM provider-chain drill — self-authenticating, uv-compatible.

Spawns a dedicated backend subprocess per drill (so provider credentials can
be overridden per process via environment variables only — backend/.env is
NEVER edited) and asserts the strict chain order:

    groq (GROQ_TIMEOUT_SECONDS, default 15) ->
    openrouter (OPENROUTER_TIMEOUT_SECONDS, default 20) ->
    rule_based

Drills (each uses a unique cache-miss sample):
  (a) both providers healthy      -> explanation_provider in (groq, openrouter)
  (b) GROQ_API_KEY invalid (env)  -> final provider openrouter
  (c) both API keys invalid (env) -> final provider rule_based + fallback text

Credentials come from the environment or ../.env.test (never a shell variable
like $TOKEN). The parent environment is untouched: each drill's overrides live
only in its subprocess and are discarded when the drill ends.

Run from the backend directory:
    uv run python scripts/drill_llm_chain.py [--port 8010]

Exit codes: 0 all drills PASS · 1 assertion failure · 2 missing credentials ·
3 backend unreachable · 4 Supabase authentication failure.
"""

import argparse
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]   # backend/
REPO = ROOT.parent                            # hackathon_01/
READY_TIMEOUT_SECONDS = 90
ANALYSIS_TIMEOUT_SECONDS = 120

# Fallback text produced by the rule_based provider (openrouter_client.
# FALLBACK_LLM_OUTPUT) — asserted in drill (c).
RULE_BASED_FALLBACK_TEXT = "Automated explanation is temporarily unavailable"


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
    env = {**load_env_file(REPO / ".env.test"), **os.environ}
    return env.get("CYBERGUARD_TEST_EMAIL"), env.get("CYBERGUARD_TEST_PASS")


def supabase_config() -> tuple[str, str]:
    env = {**load_env_file(ROOT / ".env"), **os.environ}
    url = os.environ.get("SUPABASE_URL", env.get("SUPABASE_URL", ""))
    anon = os.environ.get("SUPABASE_ANON_KEY", env.get("SUPABASE_ANON_KEY", ""))
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


class BackendDrill:
    """One backend subprocess with per-drill environment overrides."""

    def __init__(self, port: int, overrides: dict[str, str], log_path: Path):
        self.port = port
        self.overrides = overrides
        self.log_path = log_path
        self.proc: subprocess.Popen | None = None

    def __enter__(self) -> "BackendDrill":
        env = {**os.environ, **self.overrides}
        log_file = self.log_path.open("w")
        self.proc = subprocess.Popen(
            ["uv", "run", "uvicorn", "app.main:app", "--port", str(self.port)],
            cwd=ROOT,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        deadline = time.time() + READY_TIMEOUT_SECONDS
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError(
                    f"backend exited early (code {self.proc.returncode}); log: {self.log_path}"
                )
            try:
                r = httpx.get(f"http://localhost:{self.port}/api/v1/health/", timeout=3)
                if r.status_code in (200, 307):
                    return self
            except httpx.HTTPError:
                pass
            time.sleep(1.0)
        raise RuntimeError(f"backend not ready after {READY_TIMEOUT_SECONDS}s; log: {self.log_path}")

    def __exit__(self, *exc) -> None:
        if self.proc and self.proc.poll() is None:
            os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
        # Environment restore is implicit: overrides never touched the parent
        # process or backend/.env; the subprocess (and its env) is gone.
        self.overrides.clear()


def run_analysis(base_url: str, token: str) -> dict:
    """POST /analysis/email with a unique cache-miss sample; return the response."""
    nonce = uuid.uuid4().hex
    payload = {
        "source": "llm-chain-drill",
        "sender": f"drill-{nonce}@example.com",
        "subject": f"Quarterly report review {nonce}",
        "body": (
            f"Hello, please review the attached quarterly summary (ref {nonce}) "
            "and confirm the figures before the next finance meeting. Thank you."
        ),
    }
    resp = httpx.post(
        f"{base_url}/analysis/email",
        headers={"Authorization": f"Bearer {token}"},
        json=payload,
        timeout=ANALYSIS_TIMEOUT_SECONDS,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"/analysis/email returned HTTP {resp.status_code}: {resp.text[:300]}")
    return resp.json()


def _last_chain_line(log_path: Path) -> str:
    """Return the last 'LLM chain:' telemetry line from a drill log."""
    lines = [
        line.strip()
        for line in log_path.read_text(errors="replace").splitlines()
        if "LLM chain:" in line
    ]
    return lines[-1] if lines else "<no LLM chain telemetry line found>"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8010, help="port for drill backends")
    args = parser.parse_args()

    email, password = load_credentials()
    if not email or not password:
        print("Missing credentials: set CYBERGUARD_TEST_EMAIL / CYBERGUARD_TEST_PASS or ../.env.test")
        return 2
    supa_url, anon = supabase_config()
    if not supa_url or not anon:
        print("Missing Supabase config: SUPABASE_URL / SUPABASE_ANON_KEY")
        return 2
    token = password_grant(email, password, supa_url, anon)
    print("Supabase password grant OK (token acquired)")

    failures: list[str] = []

    # (a) both providers healthy
    name = "a"
    print(f"\n=== Drill ({name}) both providers healthy ===")
    log_a = ROOT / "evidence" / "reports" / "drill_llm_a.log"
    with BackendDrill(args.port, {}, log_a):
        result = run_analysis(f"http://localhost:{args.port}/api/v1", token)
        provider = result.get("explanation_provider")
        latency = result.get("explanation_latency_ms")
        chain_line = _last_chain_line(log_a)
        print(f"explanation_provider={provider} explanation_latency_ms={latency}")
        print(f"chain telemetry: {chain_line}")
        if provider not in ("groq", "openrouter"):
            failures.append(f"drill (a): expected provider in (groq, openrouter), got {provider!r}")

    # (b) GROQ_API_KEY invalid via environment override only
    name = "b"
    print(f"\n=== Drill ({name}) GROQ_API_KEY invalid (env override) ===")
    log_b = ROOT / "evidence" / "reports" / "drill_llm_b.log"
    with BackendDrill(args.port, {"GROQ_API_KEY": "invalid-key-drill-b"}, log_b):
        # The free OpenRouter auto-router occasionally exceeds the 20 s chain
        # timeout; retry with fresh cache-miss samples (each attempt asserts
        # the same chain behaviour through a cold cache key).
        provider = None
        for attempt in range(1, 4):
            result = run_analysis(f"http://localhost:{args.port}/api/v1", token)
            provider = result.get("explanation_provider")
            latency = result.get("explanation_latency_ms")
            print(f"attempt {attempt}: explanation_provider={provider} explanation_latency_ms={latency}")
            if provider == "openrouter":
                break
        chain_line = _last_chain_line(log_b)
        print(f"chain telemetry: {chain_line}")
        if provider != "openrouter":
            failures.append(f"drill (b): expected final provider openrouter, got {provider!r}")

    # (c) both keys invalid via environment override only
    name = "c"
    print(f"\n=== Drill ({name}) both API keys invalid (env override) ===")
    log_c = ROOT / "evidence" / "reports" / "drill_llm_c.log"
    with BackendDrill(
        args.port,
        {"GROQ_API_KEY": "invalid-key-drill-c", "OPENROUTER_API_KEY": "invalid-key-drill-c"},
        log_c,
    ):
        result = run_analysis(f"http://localhost:{args.port}/api/v1", token)
        provider = result.get("explanation_provider")
        latency = result.get("explanation_latency_ms")
        explanation = str(result.get("explanation") or "")
        chain_line = _last_chain_line(log_c)
        print(f"explanation_provider={provider} explanation_latency_ms={latency}")
        print(f"chain telemetry: {chain_line}")
        if provider != "rule_based":
            failures.append(f"drill (c): expected final provider rule_based, got {provider!r}")
        if RULE_BASED_FALLBACK_TEXT not in explanation:
            failures.append(f"drill (c): fallback text missing from explanation: {explanation[:120]!r}")

    print("\n=== Drill summary ===")
    if failures:
        for failure in failures:
            print(f"FAIL {failure}")
        return 1
    print("ALL DRILLS PASS — chain order groq -> openrouter -> rule_based verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
