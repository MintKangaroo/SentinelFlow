"""Concurrency-safe circuit breaker used by outbound integration clients."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum

from sentinelflow.integrations.errors import CircuitOpenError
from sentinelflow.integrations.policies import CircuitBreakerPolicy


class CircuitState(StrEnum):
    """Observable states of an integration circuit."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True, slots=True)
class CircuitSnapshot:
    """Non-secret circuit state for health views and telemetry."""

    state: CircuitState
    failure_count: int
    retry_after_seconds: float


class CircuitBreaker:
    """Count failures per logical operation and permit one recovery probe."""

    def __init__(
        self,
        service_name: str,
        policy: CircuitBreakerPolicy,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._service_name = service_name
        self._policy = policy
        self._clock = clock
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at: float | None = None
        self._probe_in_flight = False
        self._lock = asyncio.Lock()

    async def before_request(self) -> None:
        """Reject an open circuit or reserve the sole half-open probe."""
        async with self._lock:
            now = self._clock()
            if self._state is CircuitState.OPEN:
                retry_after = self._retry_after(now)
                if retry_after > 0:
                    raise CircuitOpenError(self._service_name, retry_after)
                self._state = CircuitState.HALF_OPEN
                self._probe_in_flight = True
                return

            if self._state is CircuitState.HALF_OPEN:
                raise CircuitOpenError(
                    self._service_name,
                    self._policy.recovery_timeout_seconds,
                )

    async def record_success(self) -> None:
        """Close the circuit after a healthy logical operation."""
        async with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._opened_at = None
            self._probe_in_flight = False

    async def record_failure(self) -> None:
        """Advance the failure count or reopen a failed recovery probe."""
        async with self._lock:
            if self._state is CircuitState.HALF_OPEN:
                self._open()
                return

            self._failure_count += 1
            if self._failure_count >= self._policy.failure_threshold:
                self._open()

    async def record_neutral(self) -> None:
        """Release a probe after a local failure that says nothing about dependency health."""
        async with self._lock:
            if self._state is CircuitState.HALF_OPEN and self._probe_in_flight:
                self._open()

    async def snapshot(self) -> CircuitSnapshot:
        """Return a point-in-time circuit state."""
        async with self._lock:
            now = self._clock()
            return CircuitSnapshot(
                state=self._state,
                failure_count=self._failure_count,
                retry_after_seconds=(
                    self._retry_after(now) if self._state is CircuitState.OPEN else 0.0
                ),
            )

    def _open(self) -> None:
        self._state = CircuitState.OPEN
        self._opened_at = self._clock()
        self._probe_in_flight = False

    def _retry_after(self, now: float) -> float:
        if self._opened_at is None:
            return self._policy.recovery_timeout_seconds
        elapsed = max(0.0, now - self._opened_at)
        return max(0.0, self._policy.recovery_timeout_seconds - elapsed)
