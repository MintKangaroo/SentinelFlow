"""Reusable authentication strategies backed by opaque secret references."""

from __future__ import annotations

import base64
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID

from sentinelflow.integrations.credentials import (
    CredentialReference,
    SecretManager,
    resolve_secret,
)
from sentinelflow.integrations.errors import IntegrationConfigurationError

_HEADER_NAME = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
_AUTH_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.-]*$")


@runtime_checkable
class AuthenticationStrategy(Protocol):
    """Materialize outbound auth headers only at request time."""

    async def headers(
        self,
        *,
        secret_manager: SecretManager,
        workspace_id: UUID,
    ) -> Mapping[str, str]:
        """Return auth headers without retaining resolved credentials."""
        ...


@dataclass(frozen=True, slots=True)
class NoAuthentication:
    """Explicitly configure an integration that requires no authentication."""

    async def headers(
        self,
        *,
        secret_manager: SecretManager,
        workspace_id: UUID,
    ) -> Mapping[str, str]:
        del secret_manager, workspace_id
        return {}


@dataclass(frozen=True, slots=True)
class BearerTokenAuthentication:
    """Send a token from the secret manager in the Authorization header."""

    credential: CredentialReference
    scheme: str = "Bearer"

    def __post_init__(self) -> None:
        if not _AUTH_SCHEME.fullmatch(self.scheme):
            raise IntegrationConfigurationError("invalid authorization scheme")

    async def headers(
        self,
        *,
        secret_manager: SecretManager,
        workspace_id: UUID,
    ) -> Mapping[str, str]:
        token = await resolve_secret(
            secret_manager,
            workspace_id=workspace_id,
            reference=self.credential,
        )
        return {"Authorization": f"{self.scheme} {token}"}


@dataclass(frozen=True, slots=True)
class APIKeyAuthentication:
    """Send an API key from the secret manager in a configured header."""

    credential: CredentialReference
    header_name: str = "X-API-Key"

    def __post_init__(self) -> None:
        if not _HEADER_NAME.fullmatch(self.header_name):
            raise IntegrationConfigurationError("invalid API key header name")

    async def headers(
        self,
        *,
        secret_manager: SecretManager,
        workspace_id: UUID,
    ) -> Mapping[str, str]:
        api_key = await resolve_secret(
            secret_manager,
            workspace_id=workspace_id,
            reference=self.credential,
        )
        return {self.header_name: api_key}


@dataclass(frozen=True, slots=True)
class BasicAuthentication:
    """Resolve both Basic auth fields from the secret manager."""

    username: CredentialReference
    password: CredentialReference

    async def headers(
        self,
        *,
        secret_manager: SecretManager,
        workspace_id: UUID,
    ) -> Mapping[str, str]:
        username = await resolve_secret(
            secret_manager,
            workspace_id=workspace_id,
            reference=self.username,
        )
        password = await resolve_secret(
            secret_manager,
            workspace_id=workspace_id,
            reference=self.password,
        )
        encoded = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
        return {"Authorization": f"Basic {encoded}"}
