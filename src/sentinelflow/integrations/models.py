"""Transport-neutral values exchanged through the Integration Adapter SDK."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from uuid import UUID, uuid4

from sentinelflow.integrations.errors import IntegrationConfigurationError

_MAX_HEADER_VALUE_LENGTH = 512
type QueryParameters = Mapping[str, str | int | float | bool | None]
type RequestContent = str | bytes


def _validate_header_value(name: str, value: str) -> None:
    if not value or len(value) > _MAX_HEADER_VALUE_LENGTH or "\r" in value or "\n" in value:
        raise IntegrationConfigurationError(f"{name} is not a safe HTTP header value")


@dataclass(frozen=True, slots=True)
class AdapterRequestContext:
    """Non-secret context attached to every outbound integration request."""

    workspace_id: UUID
    correlation_id: UUID = field(default_factory=uuid4)
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        if self.idempotency_key is not None:
            _validate_header_value("idempotency_key", self.idempotency_key)


@dataclass(frozen=True, slots=True)
class AdapterResponse:
    """Detached response data that does not retain auth-bearing request objects."""

    status_code: int
    headers: Mapping[str, str]
    content: bytes

    def __post_init__(self) -> None:
        object.__setattr__(self, "headers", MappingProxyType(dict(self.headers)))

    def json(self) -> object:
        """Decode the response body as JSON."""
        return json.loads(self.content)
