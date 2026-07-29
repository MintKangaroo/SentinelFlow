from uuid import uuid4

import httpx
import pytest

from sentinelflow.integrations import (
    AdapterConfig,
    IntegrationConfigurationError,
    IntegrationHTTPClient,
    NoAuthentication,
)
from sentinelflow.integrations.models import AdapterRequestContext
from sentinelflow.integrations.vendors import PatchtowerAdapter, ThreatGraphAdapter


def client(handler):
    transport = httpx.MockTransport(handler)
    return IntegrationHTTPClient(
        AdapterConfig(service_name="patchtower", base_url="https://vendor.test"),
        secret_manager=object(),
        authentication=NoAuthentication(),
        http_client=httpx.AsyncClient(transport=transport, base_url="https://vendor.test"),
    )


@pytest.mark.asyncio
async def test_patchtower_requires_dry_run_and_sanitizes_response() -> None:
    calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("dry-run"):
            return httpx.Response(200, json={"allowed": True, "receipt": "r-1", "token": "drop"})
        return httpx.Response(200, json={"accepted": True, "authorization": "drop"})

    adapter = PatchtowerAdapter(client(handler))
    result = await adapter.execute(
        "endpoint.isolate",
        {"target_ref": "endpoint:123"},
        context=AdapterRequestContext(workspace_id=uuid4(), idempotency_key="idem"),
    )
    assert calls == ["/v1/actions/dry-run", "/v1/endpoints/isolate"]
    assert result == {"accepted": True}


@pytest.mark.asyncio
async def test_vendor_operation_and_target_allowlists() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    adapter = ThreatGraphAdapter(client(handler))
    with pytest.raises(IntegrationConfigurationError):
        await adapter.execute(
            "unknown.operation", {}, context=AdapterRequestContext(workspace_id=uuid4())
        )
    with pytest.raises(IntegrationConfigurationError):
        await PatchtowerAdapter(client(handler)).execute(
            "endpoint.isolate",
            {"target_ref": "https://unsafe"},
            context=AdapterRequestContext(workspace_id=uuid4()),
        )
