"""Build the production vendor adapter registry from environment configuration."""

from collections.abc import Mapping
from uuid import UUID, uuid5

from pydantic import SecretStr

from sentinelflow.config import Settings
from sentinelflow.infrastructure.execution import VendorWorkflowStepExecutor
from sentinelflow.integrations import (
    AdapterConfig,
    AIShieldAdapter,
    AISOCAdapter,
    AutoPentestAdapter,
    BearerTokenAuthentication,
    CredentialReference,
    CredentialResolutionError,
    IntegrationConfigurationError,
    IntegrationHTTPClient,
    PatchtowerAdapter,
    RedMindAdapter,
    ThreatGraphAdapter,
)


class EnvironmentSecretManager:
    """Small process-local secret provider; values never enter workflow payloads."""

    def __init__(self, workspace_id: UUID, values: Mapping[UUID, SecretStr]) -> None:
        self._workspace_id = workspace_id
        self._values = dict(values)

    async def resolve(self, *, workspace_id: UUID, reference: CredentialReference) -> SecretStr:
        if workspace_id != self._workspace_id:
            raise CredentialResolutionError()
        try:
            return self._values[reference.reference_id]
        except KeyError as exc:
            raise CredentialResolutionError() from exc


_NAMESPACE = UUID("0f9d4e44-ef8e-4b8b-b1d7-2f7ebf2a6110")


def build_vendor_executor(settings: Settings) -> VendorWorkflowStepExecutor:
    """Create only explicitly configured adapters; fail closed on partial config."""
    workspace_id = settings.integration_workspace_id
    if workspace_id is None:
        raise IntegrationConfigurationError("SENTINELFLOW_INTEGRATION_WORKSPACE_ID is required")
    definitions = (
        ("ai-soc", settings.aisoc_base_url, settings.aisoc_token, AISOCAdapter),
        (
            "threatgraph",
            settings.threatgraph_base_url,
            settings.threatgraph_token,
            ThreatGraphAdapter,
        ),
        ("redmind", settings.redmind_base_url, settings.redmind_token, RedMindAdapter),
        (
            "patchtower",
            settings.patchtower_base_url,
            settings.patchtower_token,
            PatchtowerAdapter,
        ),
        (
            "autopentest",
            settings.autopentest_base_url,
            settings.autopentest_token,
            AutoPentestAdapter,
        ),
        ("aishield", settings.aishield_base_url, settings.aishield_token, AIShieldAdapter),
    )
    values: dict[UUID, SecretStr] = {}
    adapters: dict[str, object] = {}
    for service, base_url, token, adapter_type in definitions:
        if (base_url is None) != (token is None):
            raise IntegrationConfigurationError(f"{service} requires both base URL and token")
        if base_url is None or token is None:
            continue
        reference_id = uuid5(_NAMESPACE, f"{workspace_id}:{service}")
        values[reference_id] = token
        client = IntegrationHTTPClient(
            AdapterConfig(service_name=service, base_url=base_url),
            secret_manager=EnvironmentSecretManager(workspace_id, values),
            authentication=BearerTokenAuthentication(CredentialReference(reference_id)),
        )
        adapters[service] = adapter_type(client)
    manager = EnvironmentSecretManager(workspace_id, values)
    # Rebind clients to the final immutable manager (the mapping itself is copied).
    for adapter in adapters.values():
        client = adapter._client  # type: ignore[attr-defined]
        client._secret_manager = manager
    return VendorWorkflowStepExecutor(adapters)  # type: ignore[arg-type]
