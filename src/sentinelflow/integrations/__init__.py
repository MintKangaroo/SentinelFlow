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
from sentinelflow.integrations.vendors import (
    AIShieldAdapter,
    AISOCAdapter,
    AutoPentestAdapter,
    PatchtowerAdapter,
    RedMindAdapter,
    SecurityServiceAdapter,
    ThreatGraphAdapter,
)

__all__ = [
    "APIKeyAuthentication",
    "AISOCAdapter",
    "AIShieldAdapter",
    "AdapterConfig",
    "AdapterHTTPError",
    "AdapterRequestContext",
    "AdapterRequestError",
    "AdapterResponse",
    "AdapterTimeoutError",
    "AdapterTransportError",
    "AutoPentestAdapter",
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
    "PatchtowerAdapter",
    "RedMindAdapter",
    "RESTAdapter",
    "RetryPolicy",
    "SecretManager",
    "SecurityServiceAdapter",
    "ThreatGraphAdapter",
    "TimeoutPolicy",
]
