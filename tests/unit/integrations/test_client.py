import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from uuid import uuid4

import httpx
import pytest

from sentinelflow.integrations import (
    AdapterConfig,
    AdapterHTTPError,
    AdapterRequestContext,
    AdapterTimeoutError,
    APIKeyAuthentication,
    CircuitBreakerPolicy,
    CircuitOpenError,
    CircuitState,
    CredentialReference,
    IntegrationConfigurationError,
    IntegrationHTTPClient,
    RetryPolicy,
    TimeoutPolicy,
)
from tests.unit.integrations.helpers import (
    FakeClock,
    RecordingSecretManager,
    RejectingSecretManager,
)

type Handler = (
    Callable[[httpx.Request], httpx.Response]
    | Callable[[httpx.Request], Coroutine[None, None, httpx.Response]]
)


def build_client(
    handler: Handler,
    *,
    config: AdapterConfig | None = None,
    authentication: APIKeyAuthentication | None = None,
    secret_manager: RecordingSecretManager | RejectingSecretManager | None = None,
    sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
    clock: FakeClock | None = None,
) -> tuple[IntegrationHTTPClient, httpx.AsyncClient]:
    raw_client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://injected-origin.invalid",
    )
    adapter = IntegrationHTTPClient(
        config or AdapterConfig("mock-service", "https://service.example"),
        secret_manager=secret_manager or RejectingSecretManager(),
        authentication=authentication,
        http_client=raw_client,
        sleeper=sleeper,
        clock=clock or FakeClock(),
    )
    return adapter, raw_client


@pytest.mark.asyncio
async def test_request_injects_scoped_auth_and_control_headers_on_fixed_origin() -> None:
    workspace_id = uuid4()
    credential = CredentialReference(uuid4())
    manager = RecordingSecretManager({(workspace_id, credential.reference_id): "credential-value"})
    observed: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        observed.append(request)
        return httpx.Response(200, json={"ok": True})

    adapter, raw_client = build_client(
        handler,
        authentication=APIKeyAuthentication(credential),
        secret_manager=manager,
    )
    context = AdapterRequestContext(
        workspace_id=workspace_id,
        correlation_id=uuid4(),
        idempotency_key="operation-123",
    )

    response = await adapter.request(
        "POST",
        "/v1/analyze",
        context=context,
        json={"indicator": "example.test"},
        headers={"Accept": "application/json"},
    )

    assert response.json() == {"ok": True}
    request = observed[0]
    assert request.url == httpx.URL("https://service.example/v1/analyze")
    assert request.headers["x-api-key"] == "credential-value"
    assert request.headers["x-sentinelflow-workspace-id"] == str(workspace_id)
    assert request.headers["x-correlation-id"] == str(context.correlation_id)
    assert request.headers["idempotency-key"] == "operation-123"
    await adapter.aclose()
    assert not raw_client.is_closed
    await raw_client.aclose()


@pytest.mark.asyncio
async def test_get_retries_transient_status_and_honors_bounded_retry_after() -> None:
    attempts = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(503, headers={"Retry-After": "0.75"}, request=request)
        return httpx.Response(200, json={"attempts": attempts}, request=request)

    async def sleep(delay: float) -> None:
        delays.append(delay)

    config = AdapterConfig(
        "threatgraph",
        "https://graph.example",
        retry=RetryPolicy(
            max_attempts=3,
            initial_backoff_seconds=0.1,
            max_backoff_seconds=0.5,
        ),
    )
    adapter, raw_client = build_client(handler, config=config, sleeper=sleep)

    response = await adapter.request(
        "GET",
        "/v1/indicators",
        context=AdapterRequestContext(uuid4()),
    )

    assert response.status_code == 200
    assert attempts == 2
    assert delays == [0.5]
    await raw_client.aclose()


@pytest.mark.asyncio
async def test_post_retries_only_with_idempotency_key() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, request=request)

    config = AdapterConfig(
        "patchtower",
        "https://patch.example",
        retry=RetryPolicy(max_attempts=3, initial_backoff_seconds=0, max_backoff_seconds=0),
    )

    without_key, raw_client = build_client(handler, config=config)
    with pytest.raises(AdapterHTTPError):
        await without_key.request(
            "POST",
            "/v1/actions",
            context=AdapterRequestContext(uuid4()),
        )
    assert attempts == 1

    with_key, second_raw_client = build_client(handler, config=config)
    with pytest.raises(AdapterHTTPError):
        await with_key.request(
            "POST",
            "/v1/actions",
            context=AdapterRequestContext(uuid4(), idempotency_key="action-1"),
        )
    assert attempts == 4
    await raw_client.aclose()
    await second_raw_client.aclose()


@pytest.mark.asyncio
async def test_timeout_is_retried_then_normalized_without_target_details() -> None:
    attempts = 0
    delays: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("sensitive upstream detail", request=request)

    async def sleep(delay: float) -> None:
        delays.append(delay)

    config = AdapterConfig(
        "redmind",
        "https://redmind.example",
        retry=RetryPolicy(max_attempts=2, initial_backoff_seconds=0.1),
    )
    adapter, raw_client = build_client(handler, config=config, sleeper=sleep)

    with pytest.raises(AdapterTimeoutError) as captured:
        await adapter.request(
            "GET",
            "/v1/analysis",
            context=AdapterRequestContext(uuid4()),
        )

    assert attempts == 2
    assert delays == [0.1]
    assert "sensitive upstream detail" not in str(captured.value)
    await raw_client.aclose()


@pytest.mark.asyncio
async def test_operation_timeout_includes_retry_backoff() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, request=request)

    async def slow_sleep(delay: float) -> None:
        del delay
        await asyncio.sleep(0.05)

    config = AdapterConfig(
        "ai-shield",
        "https://shield.example",
        timeout=TimeoutPolicy(operation_seconds=0.01),
        retry=RetryPolicy(max_attempts=2),
    )
    adapter, raw_client = build_client(handler, config=config, sleeper=slow_sleep)

    with pytest.raises(AdapterTimeoutError):
        await adapter.request(
            "GET",
            "/v1/assessments",
            context=AdapterRequestContext(uuid4()),
        )
    await raw_client.aclose()


@pytest.mark.asyncio
async def test_circuit_counts_logical_failures_and_allows_recovery_probe() -> None:
    attempts = 0
    clock = FakeClock()

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        status = 503 if attempts <= 2 else 200
        return httpx.Response(status, request=request)

    config = AdapterConfig(
        "auto-pentest",
        "https://pentest.example",
        retry=RetryPolicy(max_attempts=1),
        circuit_breaker=CircuitBreakerPolicy(
            failure_threshold=2,
            recovery_timeout_seconds=10,
        ),
    )
    adapter, raw_client = build_client(handler, config=config, clock=clock)
    context = AdapterRequestContext(uuid4())

    for _ in range(2):
        with pytest.raises(AdapterHTTPError):
            await adapter.request("GET", "/v1/validations", context=context)

    assert (await adapter.circuit_snapshot()).state is CircuitState.OPEN
    with pytest.raises(CircuitOpenError):
        await adapter.request("GET", "/v1/validations", context=context)
    assert attempts == 2

    clock.advance(10)
    response = await adapter.request("GET", "/v1/validations", context=context)
    assert response.status_code == 200
    assert (await adapter.circuit_snapshot()).state is CircuitState.CLOSED
    await raw_client.aclose()


@pytest.mark.asyncio
async def test_redirect_is_not_followed_and_error_body_is_not_in_message() -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(
            401,
            content=b"upstream-secret-detail",
            headers={
                "Location": "https://evil.example/capture",
                "Set-Cookie": "session=secret",
            },
            request=request,
        )

    adapter, raw_client = build_client(handler)

    with pytest.raises(AdapterHTTPError) as captured:
        await adapter.request(
            "GET",
            "/v1/resource",
            context=AdapterRequestContext(uuid4()),
        )

    assert attempts == 1
    assert "upstream-secret-detail" not in str(captured.value)
    assert captured.value.response.content == b"upstream-secret-detail"
    assert "set-cookie" not in captured.value.response.headers
    await raw_client.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("method", "path", "headers"),
    [
        ("GET\nInjected", "/v1/resource", None),
        ("GET", "https://evil.example/capture", None),
        ("GET", "//evil.example/capture", None),
        ("GET", "/v1/resource#fragment", None),
        ("GET", "/v1/resource", {"Authorization": "caller-value"}),
        ("GET", "/v1/resource", {"X-Test": "bad\nvalue"}),
    ],
)
async def test_request_rejects_origin_escape_and_managed_headers(
    method: str,
    path: str,
    headers: dict[str, str] | None,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected request: {request.url}")

    adapter, raw_client = build_client(handler)

    with pytest.raises(IntegrationConfigurationError):
        await adapter.request(
            method,
            path,
            context=AdapterRequestContext(uuid4()),
            headers=headers,
        )
    await raw_client.aclose()


@pytest.mark.asyncio
async def test_json_and_content_are_mutually_exclusive() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"unexpected request: {request.url}")

    adapter, raw_client = build_client(handler)
    with pytest.raises(IntegrationConfigurationError):
        await adapter.request(
            "POST",
            "/v1/resource",
            context=AdapterRequestContext(uuid4()),
            json={"key": "value"},
            content=b"raw",
        )
    await raw_client.aclose()
