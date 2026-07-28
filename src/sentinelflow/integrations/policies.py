"""Timeout, retry, and circuit-breaker policies shared by adapters."""

from dataclasses import dataclass, field

import httpx

from sentinelflow.integrations.errors import IntegrationConfigurationError

_IDEMPOTENT_METHODS = frozenset({"DELETE", "GET", "HEAD", "OPTIONS", "PUT"})


@dataclass(frozen=True, slots=True)
class TimeoutPolicy:
    """Bound individual network phases and the complete logical operation."""

    connect_seconds: float = 2.0
    read_seconds: float = 10.0
    write_seconds: float = 10.0
    pool_seconds: float = 2.0
    operation_seconds: float = 30.0

    def __post_init__(self) -> None:
        values = (
            self.connect_seconds,
            self.read_seconds,
            self.write_seconds,
            self.pool_seconds,
            self.operation_seconds,
        )
        if any(value <= 0 for value in values):
            raise IntegrationConfigurationError("timeout values must be positive")

    def to_httpx(self) -> httpx.Timeout:
        """Build the HTTPX per-attempt timeout configuration."""
        return httpx.Timeout(
            connect=self.connect_seconds,
            read=self.read_seconds,
            write=self.write_seconds,
            pool=self.pool_seconds,
        )


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """Retry transient responses only when the operation is safe to repeat."""

    max_attempts: int = 3
    initial_backoff_seconds: float = 0.1
    max_backoff_seconds: float = 2.0
    retryable_status_codes: frozenset[int] = field(
        default_factory=lambda: frozenset({408, 425, 429, 500, 502, 503, 504})
    )

    def __post_init__(self) -> None:
        if not 1 <= self.max_attempts <= 10:
            raise IntegrationConfigurationError("max_attempts must be between 1 and 10")
        if self.initial_backoff_seconds < 0 or self.max_backoff_seconds < 0:
            raise IntegrationConfigurationError("retry backoff cannot be negative")
        if self.initial_backoff_seconds > self.max_backoff_seconds:
            raise IntegrationConfigurationError(
                "initial retry backoff cannot exceed maximum backoff"
            )
        if any(not 100 <= status <= 599 for status in self.retryable_status_codes):
            raise IntegrationConfigurationError("retry status code is invalid")

    def allows_retry(self, method: str, *, has_idempotency_key: bool) -> bool:
        """Return whether repeating this operation is allowed."""
        return method.upper() in _IDEMPOTENT_METHODS or has_idempotency_key

    def delay_seconds(self, failed_attempt: int, *, retry_after: str | None = None) -> float:
        """Compute bounded exponential backoff and honor numeric Retry-After."""
        if retry_after is not None:
            try:
                requested_delay = float(retry_after)
            except ValueError:
                requested_delay = -1
            if requested_delay >= 0:
                return min(requested_delay, self.max_backoff_seconds)

        delay = self.initial_backoff_seconds * (2.0 ** max(0, failed_attempt - 1))
        return min(delay, self.max_backoff_seconds)


@dataclass(frozen=True, slots=True)
class CircuitBreakerPolicy:
    """Open a dependency circuit after repeated logical request failures."""

    failure_threshold: int = 5
    recovery_timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not 1 <= self.failure_threshold <= 100:
            raise IntegrationConfigurationError(
                "circuit failure_threshold must be between 1 and 100"
            )
        if self.recovery_timeout_seconds <= 0:
            raise IntegrationConfigurationError("circuit recovery timeout must be positive")
