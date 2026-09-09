"""Async circuit breaker for outbound provider calls (Phase A).

pybreaker is synchronous and would block the asyncio event loop, so CYBERGUARD
implements its own coroutine-aware breaker.

State machine:

    CLOSED      normal operation; failures are counted
    OPEN        failures reached ``failure_threshold``; every call is rejected
                instantly with CircuitBreakerOpenError until
                ``recovery_timeout`` seconds have elapsed
    HALF_OPEN   the timeout elapsed; exactly one probe call is allowed through.
                Success closes the breaker, failure reopens it for another
                ``recovery_timeout`` window.

All state mutation happens under an asyncio.Lock so concurrent requests share
one breaker safely without ever blocking the loop on synchronous I/O.
"""

from __future__ import annotations

import asyncio
import enum
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger("cyberguard.circuit_breaker")


class CircuitBreakerOpenError(RuntimeError):
    """Raised immediately when a call is attempted while the breaker is OPEN."""


class CircuitState(str, enum.Enum):
    """Lifecycle states of an AsyncCircuitBreaker."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class AsyncCircuitBreaker:
    """Async circuit breaker guarding one downstream provider."""

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
        name: str = "circuit",
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.name = name
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at = 0.0
        self._probe_in_flight = False
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Current breaker state (intended for diagnostics/metrics)."""
        return self._state

    @property
    def failure_count(self) -> int:
        """Consecutive failures recorded in the current CLOSED window."""
        return self._failure_count

    async def call(
        self, coro_func: Callable[..., Awaitable[Any]], *args: Any, **kwargs: Any
    ) -> Any:
        """Await ``coro_func(*args, **kwargs)`` through the breaker.

        Raises CircuitBreakerOpenError without executing the coroutine when the
        breaker is OPEN and the recovery timeout has not elapsed. The original
        provider exception is re-raised after being recorded as a failure.
        """
        async with self._lock:
            if self._state is CircuitState.OPEN:
                elapsed = time.monotonic() - self._opened_at
                if elapsed >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._probe_in_flight = False
                    logger.info(
                        "Circuit breaker %s: recovery timeout elapsed, moving to HALF_OPEN",
                        self.name,
                    )
                else:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' is OPEN; "
                        f"retry allowed in {self.recovery_timeout - elapsed:.1f}s"
                    )
            if self._state is CircuitState.HALF_OPEN:
                if self._probe_in_flight:
                    raise CircuitBreakerOpenError(
                        f"Circuit breaker '{self.name}' is HALF_OPEN with a probe in flight"
                    )
                self._probe_in_flight = True

        try:
            result = await coro_func(*args, **kwargs)
        except Exception:
            async with self._lock:
                self._probe_in_flight = False
                self._failure_count += 1
                if (
                    self._state is CircuitState.HALF_OPEN
                    or self._failure_count >= self.failure_threshold
                ):
                    self._trip()
            raise

        async with self._lock:
            self._probe_in_flight = False
            self._failure_count = 0
            if self._state is not CircuitState.CLOSED:
                logger.info("Circuit breaker %s: probe succeeded, moving to CLOSED", self.name)
            self._state = CircuitState.CLOSED
        return result

    def _trip(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = time.monotonic()
        logger.warning(
            "Circuit breaker %s tripped OPEN after %d consecutive failure(s)",
            self.name,
            self._failure_count,
        )
