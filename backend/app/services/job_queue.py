"""Arq/Redis job-queue access for Phase C-1 background workers.

Heavy analysis (deepfake media, bulk log ingestion) is offloaded to an Arq
worker so the request thread returns immediately. Every helper in this module
fails soft: when Redis is unreachable the API falls back to running the same
work synchronously, so the product keeps working without a broker.
"""

import logging
import time
from typing import Any, Optional

from arq import create_pool
from arq.connections import ArqRedis, RedisSettings

from app.core.config import get_settings

logger = logging.getLogger("cyberguard.job_queue")

_pool: Optional[ArqRedis] = None
_pool_retry_at = 0.0  # monotonic timestamp before which we do not re-dial Redis
_CONNECT_RETRY_COOLDOWN_SECONDS = 30.0
_DEGRADED_WARN_INTERVAL_SECONDS = 60.0
_last_degraded_warn = 0.0


async def _discard_pool() -> None:
    """Drop a possibly-stale cached pool so the next call rebuilds it."""
    global _pool
    pool, _pool = _pool, None
    if pool is not None:
        try:
            await pool.close()
        except Exception:
            pass  # closing a dead connection is best-effort


def _warn_degraded_once_per_minute(exc: Exception) -> None:
    """Throttled (<= once / 60 s) warning for synchronous degradation."""
    global _last_degraded_warn
    now = time.monotonic()
    if now - _last_degraded_warn >= _DEGRADED_WARN_INTERVAL_SECONDS:
        _last_degraded_warn = now
        logger.warning(
            "Worker queue unavailable, caller must run synchronously: %s", exc
        )


async def get_arq_pool(force_rebuild: bool = False) -> Optional[ArqRedis]:
    """Return the cached Arq redis pool, or None when Redis is unreachable.

    The pool is created once from settings.redis_url and reused across
    requests. Connection failures start a 30 s cooldown during which callers
    get None immediately instead of paying arq's connection-retry delay —
    the synchronous fallback must stay fast. After the cooldown the next call
    retries the connection. ``force_rebuild=True`` bypasses the cooldown
    (used by enqueue_job's immediate retry after discarding a stale pool).
    """
    global _pool, _pool_retry_at
    if _pool is not None:
        return _pool
    if not force_rebuild and time.monotonic() < _pool_retry_at:
        return None
    try:
        _pool = await create_pool(
            RedisSettings.from_dsn(get_settings().REDIS_URL)
        )
        return _pool
    except Exception:
        _pool_retry_at = time.monotonic() + _CONNECT_RETRY_COOLDOWN_SECONDS
        return None


async def enqueue_job(job_name: str, **kwargs: Any) -> bool:
    """Enqueue an Arq job; return True on success, False on ANY failure.

    A False return is the caller's signal to run the work synchronously on
    the request thread — never raise, so the API path cannot break because
    the queue is down. On failure the cached pool is discarded (it may be
    stale after a Redis restart) and one immediate rebuild + retry is
    attempted before giving up (Phase D-1).
    """
    global _last_degraded_warn
    try:
        pool = await get_arq_pool()
        if pool is None:
            raise RuntimeError("Redis pool unavailable")
        job = await pool.enqueue_job(job_name, **kwargs)
        if job is None:
            # arq returns None when an identical job is already queued —
            # treat as accepted (the work will run once).
            logger.info("Job %s already queued (deduplicated by arq)", job_name)
        return True
    except Exception as exc:
        # The cached pool may be stale (Redis restarted); discard it and try
        # one immediate rebuild + retry before degrading to synchronous.
        try:
            await _discard_pool()
            pool = await get_arq_pool(force_rebuild=True)
            if pool is not None:
                await pool.enqueue_job(job_name, **kwargs)
                logger.info(
                    "Redis pool rebuilt after failure; job %s enqueued on retry",
                    job_name,
                )
                return True
        except Exception as retry_exc:
            exc = retry_exc  # report the retry failure, not the original
        _warn_degraded_once_per_minute(exc)
        return False
