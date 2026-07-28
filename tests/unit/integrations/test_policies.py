from types import MappingProxyType
from uuid import uuid4

import pytest

from sentinelflow.integrations import (
    AdapterConfig,
    AdapterRequestContext,
    AdapterResponse,
    CircuitBreakerPolicy,
    IntegrationConfigurationError,
    RetryPolicy,
    TimeoutPolicy,
)


def test_retry_policy_requires_idempotency_for_unsafe_methods() -> None:
    policy = RetryPolicy(initial_backoff_seconds=0.25, max_backoff_seconds=1)

    assert policy.allows_retry("GET", has_idempotency_key=False)
    assert not policy.allows_retry("POST", has_idempotency_key=False)
    assert policy.allows_retry("POST", has_idempotency_key=True)
    assert policy.delay_seconds(1) == 0.25
    assert policy.delay_seconds(3) == 1
    assert policy.delay_seconds(1, retry_after="0.75") == 0.75
    assert policy.delay_seconds(1, retry_after="invalid") == 0.25


@pytest.mark.parametrize(
    "policy",
    [
        lambda: RetryPolicy(max_attempts=0),
        lambda: RetryPolicy(initial_backoff_seconds=2, max_backoff_seconds=1),
        lambda: RetryPolicy(retryable_status_codes=frozenset({999})),
        lambda: TimeoutPolicy(read_seconds=0),
        lambda: CircuitBreakerPolicy(failure_threshold=0),
        lambda: CircuitBreakerPolicy(recovery_timeout_seconds=0),
    ],
)
def test_invalid_resilience_policy_is_rejected(policy: object) -> None:
    with pytest.raises(IntegrationConfigurationError):
        policy()  # type: ignore[operator]


@pytest.mark.parametrize(
    "config",
    [
        lambda: AdapterConfig("AI SOC", "https://service.example"),
        lambda: AdapterConfig("ai-soc", "http://service.example"),
        lambda: AdapterConfig("ai-soc", "https://user:pass@service.example"),
        lambda: AdapterConfig("ai-soc", "https://service.example/api"),
        lambda: AdapterConfig("ai-soc", "file:///tmp/service"),
    ],
)
def test_adapter_config_rejects_unsafe_origins(config: object) -> None:
    with pytest.raises(IntegrationConfigurationError):
        config()  # type: ignore[operator]


def test_insecure_http_requires_explicit_development_opt_in() -> None:
    config = AdapterConfig(
        "mock-service",
        "http://localhost:9000",
        allow_insecure_http=True,
    )

    assert config.base_url == "http://localhost:9000"


def test_timeout_policy_builds_phase_specific_httpx_timeout() -> None:
    policy = TimeoutPolicy(
        connect_seconds=1,
        read_seconds=2,
        write_seconds=3,
        pool_seconds=4,
        operation_seconds=5,
    )

    timeout = policy.to_httpx()

    assert timeout.connect == 1
    assert timeout.read == 2
    assert timeout.write == 3
    assert timeout.pool == 4


def test_request_context_blocks_header_injection() -> None:
    with pytest.raises(IntegrationConfigurationError):
        AdapterRequestContext(workspace_id=uuid4(), idempotency_key="bad\nkey")


def test_detached_response_is_json_decodable_and_headers_are_immutable() -> None:
    response = AdapterResponse(
        status_code=200,
        headers={"Content-Type": "application/json"},
        content=b'{"ok": true}',
    )

    assert response.json() == {"ok": True}
    assert isinstance(response.headers, MappingProxyType)
    with pytest.raises(TypeError):
        response.headers["Other"] = "value"  # type: ignore[index]
