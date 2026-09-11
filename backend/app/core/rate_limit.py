"""In-memory token-bucket rate limiting (Phase D-1).

One bucket per authenticated user id (parsed unverified from the JWT — the
sub claim is used only for bucketing, never for authorization; every request
is still fully verified by the auth dependency). Requests without a bearer
token are keyed by client IP. When a bucket is empty the middleware answers
429 with a Retry-After header instead of letting the request through.

Limits come from settings.RATE_LIMIT_RPM (env RATE_LIMIT_RPM, default 300
requests/minute). /health is exempt so container healthchecks and load
balancer probes can never be throttled.
"""

import base64
import json
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

EXEMPT_PATHS = ("/api/v1/health", "/health")
_BUCKET_SWEEP_INTERVAL_SECONDS = 300.0
# A bucket is garbage-collected after this much inactivity (keep memory bounded).
_IDLE_BUCKET_TTL_SECONDS = 3600.0


def _user_key_from_auth_header(auth_header: str | None) -> str | None:
    """Extract the unverified 'sub' claim from a bearer JWT (bucketing only)."""
    if not auth_header or not auth_header.startswith("Bearer "):
        return None
    token = auth_header.removeprefix("Bearer ").strip()
    parts = token.split(".")
    if len(parts) != 3:
        return None
    try:
        padded = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded))
        sub = payload.get("sub")
        return str(sub) if sub else None
    except Exception:
        return None


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token bucket: RATE_LIMIT_RPM tokens, refilled linearly over a minute."""

    def __init__(self, app, rpm: int = 300) -> None:
        super().__init__(app)
        self._capacity = max(int(rpm), 1)
        self._refill_per_second = self._capacity / 60.0
        # key -> [tokens, last_refill_monotonic, last_seen_monotonic]
        self._buckets: dict[str, list[float]] = {}
        self._last_sweep = time.monotonic()

    def _take_token(self, key: str) -> tuple[bool, float]:
        now = time.monotonic()
        bucket = self._buckets.get(key)
        if bucket is None:
            self._buckets[key] = [self._capacity - 1.0, now, now]
            return True, 0.0

        tokens, last_refill, _ = bucket
        tokens = min(self._capacity, tokens + (now - last_refill) * self._refill_per_second)
        if tokens >= 1.0:
            bucket[0] = tokens - 1.0
            bucket[1] = now
            bucket[2] = now
            return True, 0.0
        # Empty bucket: keep the refill clock moving so Retry-After is accurate.
        bucket[0] = tokens
        bucket[1] = now
        bucket[2] = now
        retry_after = (1.0 - tokens) / self._refill_per_second
        return False, retry_after

    def _sweep_stale_buckets(self, now: float) -> None:
        if now - self._last_sweep < _BUCKET_SWEEP_INTERVAL_SECONDS:
            return
        self._last_sweep = now
        stale = [
            key
            for key, (_, _, last_seen) in self._buckets.items()
            if now - last_seen > _IDLE_BUCKET_TTL_SECONDS
        ]
        for key in stale:
            self._buckets.pop(key, None)

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if any(path == exempt or path.startswith(exempt) for exempt in EXEMPT_PATHS):
            return await call_next(request)

        key = _user_key_from_auth_header(request.headers.get("Authorization"))
        if key is None:
            key = request.client.host if request.client else "unknown"
        self._sweep_stale_buckets(time.monotonic())

        allowed, retry_after = self._take_token(key)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"error": "rate_limited", "message": "Too many requests"},
                headers={"Retry-After": str(max(int(retry_after) + 1, 1))},
            )
        return await call_next(request)
