"""Base class for concrete external security-service REST adapters."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from sentinelflow.integrations.client import IntegrationHTTPClient
from sentinelflow.integrations.models import (
    AdapterRequestContext,
    AdapterResponse,
    QueryParameters,
    RequestContent,
)


class RESTAdapter:
    """Thin vendor adapter base that delegates resilience to the common client."""

    def __init__(self, client: IntegrationHTTPClient) -> None:
        self._client = client

    @property
    def service_name(self) -> str:
        """Return the configured external service identifier."""
        return self._client.service_name

    async def request(
        self,
        method: str,
        path: str,
        *,
        context: AdapterRequestContext,
        params: QueryParameters | None = None,
        json: Any = None,
        content: RequestContent | None = None,
        headers: Mapping[str, str] | None = None,
        raise_for_status: bool = True,
    ) -> AdapterResponse:
        """Delegate an operation to the hardened transport."""
        return await self._client.request(
            method,
            path,
            context=context,
            params=params,
            json=json,
            content=content,
            headers=headers,
            raise_for_status=raise_for_status,
        )

    async def aclose(self) -> None:
        """Close resources owned by the common transport."""
        await self._client.aclose()
