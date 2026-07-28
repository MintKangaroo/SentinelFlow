"""Hardened asynchronous REST transport shared by security-service adapters."""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx
from opentelemetry import trace

from sentinelflow.integrations.auth import AuthenticationStrategy, NoAuthentication
from sentinelflow.integrations.circuit import CircuitBreaker, CircuitSnapshot
from sentinelflow.integrations.credentials import SecretManager
from sentinelflow.integrations.errors import (
    AdapterHTTPError,
    AdapterTimeoutError,
    AdapterTransportError,
    IntegrationConfigurationError,
)
from sentinelflow.integrations.models import (
    AdapterRequestContext,
    AdapterResponse,
    QueryParameters,
    RequestContent,
)
from sentinelflow.integrations.policies import (
    CircuitBreakerPolicy,
    RetryPolicy,
    TimeoutPolicy,
)

_SERVICE_NAME = re.compile(r"^[a-z][a-z0-9_-]{1,62}$")
_HTTP_METHOD = re.compile(r"^[A-Z]+$")
_RESERVED_HEADERS = frozenset(
    {
        "authorization",
        "idempotency-key",
        "x-correlation-id",
        "x-sentinelflow-workspace-id",
    }
)
_SENSITIVE_RESPONSE_HEADERS = frozenset({"proxy-authenticate", "set-cookie", "www-authenticate"})
_tracer = trace.get_tracer(__name__)


@dataclass(frozen=True, slots=True)
class AdapterConfig:
    """Safe runtime policy for one fixed external service origin."""

    service_name: str
    base_url: str
    timeout: TimeoutPolicy = field(default_factory=TimeoutPolicy)
    retry: RetryPolicy = field(default_factory=RetryPolicy)
    circuit_breaker: CircuitBreakerPolicy = field(default_factory=CircuitBreakerPolicy)
    allow_insecure_http: bool = False

    def __post_init__(self) -> None:
        if not _SERVICE_NAME.fullmatch(self.service_name):
            raise IntegrationConfigurationError("invalid integration service name")

        url = httpx.URL(self.base_url)
        if url.scheme not in {"http", "https"} or not url.host:
            raise IntegrationConfigurationError("integration base_url must be an HTTP origin")
        if url.query or url.fragment or url.username or url.password:
            raise IntegrationConfigurationError(
                "integration base_url cannot contain credentials, query, or fragment"
            )
        if url.path not in {"", "/"}:
            raise IntegrationConfigurationError("integration base_url must not contain a path")
        if url.scheme != "https" and not self.allow_insecure_http:
            raise IntegrationConfigurationError("integration base_url must use HTTPS")


class IntegrationHTTPClient:
    """Apply auth and resilience policy without retaining resolved secrets."""

    def __init__(
        self,
        config: AdapterConfig,
        *,
        secret_manager: SecretManager,
        authentication: AuthenticationStrategy | None = None,
        http_client: httpx.AsyncClient | None = None,
        sleeper: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config = config
        self._secret_manager = secret_manager
        self._authentication = authentication or NoAuthentication()
        self._sleeper = sleeper
        self._base_url = httpx.URL(config.base_url)
        self._client = http_client or httpx.AsyncClient(
            base_url=config.base_url,
            follow_redirects=False,
        )
        self._owns_client = http_client is None
        self._circuit = CircuitBreaker(
            config.service_name,
            config.circuit_breaker,
            clock=clock,
        )

    @property
    def service_name(self) -> str:
        """Return the stable service identifier used in telemetry and errors."""
        return self._config.service_name

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
        """Execute one logical request with bounded retries and circuit protection."""
        normalized_method = method.upper()
        if not _HTTP_METHOD.fullmatch(normalized_method):
            raise IntegrationConfigurationError("invalid HTTP method")
        self._validate_path(path)
        if json is not None and content is not None:
            raise IntegrationConfigurationError("json and content cannot both be supplied")
        supplied_headers = self._validate_headers(headers or {})
        can_retry = self._config.retry.allows_retry(
            normalized_method,
            has_idempotency_key=context.idempotency_key is not None,
        )

        await self._circuit.before_request()
        try:
            auth_headers = await self._authentication.headers(
                secret_manager=self._secret_manager,
                workspace_id=context.workspace_id,
            )
            request_headers = self._build_headers(
                context=context,
                supplied=supplied_headers,
                auth=auth_headers,
            )
        except asyncio.CancelledError:
            await self._circuit.record_neutral()
            raise
        except Exception:
            await self._circuit.record_neutral()
            raise

        try:
            with _tracer.start_as_current_span(
                "integration.request",
                attributes={
                    "sentinelflow.integration.service": self._config.service_name,
                    "http.request.method": normalized_method,
                },
            ) as span:
                async with asyncio.timeout(self._config.timeout.operation_seconds):
                    response = await self._request_with_retries(
                        normalized_method,
                        path,
                        params=params,
                        json=json,
                        content=content,
                        headers=request_headers,
                        can_retry=can_retry,
                    )
                span.set_attribute("http.response.status_code", response.status_code)
        except asyncio.CancelledError:
            await self._circuit.record_neutral()
            raise
        except TimeoutError as exc:
            await self._circuit.record_failure()
            raise AdapterTimeoutError(self._config.service_name) from exc
        except (AdapterTimeoutError, AdapterTransportError):
            await self._circuit.record_failure()
            raise
        except Exception:
            await self._circuit.record_neutral()
            raise

        if response.status_code in self._config.retry.retryable_status_codes:
            await self._circuit.record_failure()
        else:
            await self._circuit.record_success()

        if raise_for_status and response.status_code >= 400:
            raise AdapterHTTPError(self._config.service_name, response)
        return response

    async def circuit_snapshot(self) -> CircuitSnapshot:
        """Expose sanitized breaker state for health and operations views."""
        return await self._circuit.snapshot()

    async def aclose(self) -> None:
        """Close only an HTTP client owned by this adapter."""
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> IntegrationHTTPClient:
        return self

    async def __aexit__(
        self,
        exc_type: object,
        exc_value: object,
        traceback: object,
    ) -> None:
        await self.aclose()

    async def _request_with_retries(
        self,
        method: str,
        path: str,
        *,
        params: QueryParameters | None,
        json: Any,
        content: RequestContent | None,
        headers: Mapping[str, str],
        can_retry: bool,
    ) -> AdapterResponse:
        for attempt in range(1, self._config.retry.max_attempts + 1):
            try:
                raw_response = await self._client.request(
                    method,
                    self._base_url.join(path),
                    params=params,
                    json=json,
                    content=content,
                    headers=headers,
                    timeout=self._config.timeout.to_httpx(),
                    follow_redirects=False,
                )
            except httpx.TimeoutException as exc:
                if can_retry and attempt < self._config.retry.max_attempts:
                    await self._sleep_before_retry(attempt)
                    continue
                raise AdapterTimeoutError(self._config.service_name) from exc
            except httpx.TransportError as exc:
                if can_retry and attempt < self._config.retry.max_attempts:
                    await self._sleep_before_retry(attempt)
                    continue
                raise AdapterTransportError(self._config.service_name) from exc

            response = await self._detach_response(raw_response)
            if (
                can_retry
                and attempt < self._config.retry.max_attempts
                and response.status_code in self._config.retry.retryable_status_codes
            ):
                await self._sleep_before_retry(
                    attempt,
                    retry_after=response.headers.get("retry-after"),
                )
                continue
            return response

        raise AssertionError("retry loop did not produce a result")

    async def _sleep_before_retry(
        self,
        failed_attempt: int,
        *,
        retry_after: str | None = None,
    ) -> None:
        await self._sleeper(
            self._config.retry.delay_seconds(
                failed_attempt,
                retry_after=retry_after,
            )
        )

    @staticmethod
    async def _detach_response(response: httpx.Response) -> AdapterResponse:
        content = await response.aread()
        detached = AdapterResponse(
            status_code=response.status_code,
            headers={
                name: value
                for name, value in response.headers.items()
                if name.lower() not in _SENSITIVE_RESPONSE_HEADERS
            },
            content=content,
        )
        await response.aclose()
        return detached

    @staticmethod
    def _validate_path(path: str) -> None:
        url = httpx.URL(path)
        if not path.startswith("/") or url.is_absolute_url or url.host:
            raise IntegrationConfigurationError(
                "adapter request path must be relative to the configured service origin"
            )
        if url.fragment:
            raise IntegrationConfigurationError("adapter request path cannot contain a fragment")

    @staticmethod
    def _validate_headers(headers: Mapping[str, str]) -> dict[str, str]:
        validated: dict[str, str] = {}
        for name, value in headers.items():
            normalized = name.lower()
            if normalized in _RESERVED_HEADERS:
                raise IntegrationConfigurationError(f"{name} is managed by the adapter SDK")
            if "\r" in name or "\n" in name or "\r" in value or "\n" in value:
                raise IntegrationConfigurationError("outbound header contains a newline")
            validated[name] = value
        return validated

    @staticmethod
    def _build_headers(
        *,
        context: AdapterRequestContext,
        supplied: Mapping[str, str],
        auth: Mapping[str, str],
    ) -> dict[str, str]:
        headers = dict(supplied)
        existing = {name.lower() for name in headers}
        for name, value in auth.items():
            if name.lower() in existing:
                raise IntegrationConfigurationError(
                    f"{name} is managed by the authentication strategy"
                )
            if "\r" in name or "\n" in name or "\r" in value or "\n" in value:
                raise IntegrationConfigurationError("authentication header is invalid")
            headers[name] = value
        headers["X-SentinelFlow-Workspace-ID"] = str(context.workspace_id)
        headers["X-Correlation-ID"] = str(context.correlation_id)
        if context.idempotency_key is not None:
            headers["Idempotency-Key"] = context.idempotency_key
        return headers
