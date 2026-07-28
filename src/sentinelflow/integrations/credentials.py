"""Credential-reference and secret-manager boundaries for integrations."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID

from pydantic import SecretStr

from sentinelflow.integrations.errors import CredentialResolutionError


@dataclass(frozen=True, slots=True)
class CredentialReference:
    """Opaque identifier that is safe to persist instead of a credential value."""

    reference_id: UUID


@runtime_checkable
class SecretManager(Protocol):
    """Resolve workspace-scoped credentials outside the application database."""

    async def resolve(
        self,
        *,
        workspace_id: UUID,
        reference: CredentialReference,
    ) -> SecretStr:
        """Return a secret value or raise ``CredentialResolutionError``."""
        ...


async def resolve_secret(
    secret_manager: SecretManager,
    *,
    workspace_id: UUID,
    reference: CredentialReference,
) -> str:
    """Resolve a secret while normalizing provider failures to a sanitized error."""
    try:
        value = await secret_manager.resolve(
            workspace_id=workspace_id,
            reference=reference,
        )
    except CredentialResolutionError:
        raise
    except Exception as exc:
        raise CredentialResolutionError() from exc

    secret = value.get_secret_value()
    if not secret:
        raise CredentialResolutionError()
    return secret
