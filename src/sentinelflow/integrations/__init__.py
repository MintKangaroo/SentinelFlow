"""Public Integration Adapter SDK."""

from sentinelflow.integrations.auth import (
    APIKeyAuthentication,
    AuthenticationStrategy,
    BasicAuthentication,
    BearerTokenAuthentication,
    NoAuthentication,
)
from sentinelflow.integrations.base import RESTAdapter
from sentinelflow.integrations.circuit import CircuitSnapshot, CircuitState
from sentinelflow.integrations.client import AdapterConfig, IntegrationHTTPClient
from sentinelflow.integrations.credentials import CredentialReference, SecretManager
from sentinelflow.integrations.errors import (
    AdapterHTTPError,
    AdapterRequestError,
    AdapterTimeoutError,
    AdapterTransportError,
    CircuitOpenError,
    CredentialResolutionError,
    IntegrationConfigurationError,
    IntegrationError,
)
from sentinelflow.integrations.models import AdapterRequestContext, AdapterResponse
from sentinelflow.integrations.policies import (
    CircuitBreakerPolicy,
    RetryPolicy,
    TimeoutPolicy,
)

__all__ = [
    "APIKeyAuthentication",
    "AdapterConfig",
    "AdapterHTTPError",
    "AdapterRequestContext",
    "AdapterRequestError",
    "AdapterResponse",
    "AdapterTimeoutError",
    "AdapterTransportError",
    "AuthenticationStrategy",
    "BasicAuthentication",
    "BearerTokenAuthentication",
    "CircuitBreakerPolicy",
    "CircuitOpenError",
    "CircuitSnapshot",
    "CircuitState",
    "CredentialReference",
    "CredentialResolutionError",
    "IntegrationConfigurationError",
    "IntegrationError",
    "IntegrationHTTPClient",
    "NoAuthentication",
    "RESTAdapter",
    "RetryPolicy",
    "SecretManager",
    "TimeoutPolicy",
]
