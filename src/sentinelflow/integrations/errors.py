"""Sanitized errors raised at the external integration boundary."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sentinelflow.integrations.models import AdapterResponse


class IntegrationError(RuntimeError):
    """Base error for the Integration Adapter SDK."""


class IntegrationConfigurationError(IntegrationError, ValueError):
    """Raised when an adapter is configured with an unsafe or invalid value."""


class CredentialResolutionError(IntegrationError):
    """Raised when a secret manager cannot resolve an opaque credential reference."""

    def __init__(self) -> None:
        super().__init__("integration credential could not be resolved")


class CircuitOpenError(IntegrationError):
    """Raised when a dependency circuit is open and no request was attempted."""

    def __init__(self, service_name: str, retry_after_seconds: float) -> None:
        self.service_name = service_name
        self.retry_after_seconds = max(0.0, retry_after_seconds)
        super().__init__(f"integration circuit is open for {service_name}")


class AdapterRequestError(IntegrationError):
    """Base error for failed outbound adapter requests."""

    def __init__(self, service_name: str, message: str) -> None:
        self.service_name = service_name
        super().__init__(message)


class AdapterTimeoutError(AdapterRequestError):
    """Raised when one attempt or the complete logical operation times out."""

    def __init__(self, service_name: str) -> None:
        super().__init__(service_name, f"integration request timed out for {service_name}")


class AdapterTransportError(AdapterRequestError):
    """Raised when the remote dependency cannot be reached."""

    def __init__(self, service_name: str) -> None:
        super().__init__(service_name, f"integration transport failed for {service_name}")


class AdapterHTTPError(AdapterRequestError):
    """Raised for a non-success HTTP response without logging its body."""

    def __init__(self, service_name: str, response: AdapterResponse) -> None:
        self.response = response
        super().__init__(
            service_name,
            f"integration request failed for {service_name} with status {response.status_code}",
        )
