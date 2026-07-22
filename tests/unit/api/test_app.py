import asyncio

from fastapi.testclient import TestClient

import sentinelflow.api.app as app_module
from sentinelflow.api import create_app
from sentinelflow.config import Settings
from sentinelflow.runtime import RuntimeResources


class FakeDependency:
    def __init__(self, *, fail: bool = False, delay: float = 0) -> None:
        self.fail = fail
        self.delay = delay
        self.closed = False

    async def check(self) -> None:
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError("sensitive infrastructure error")

    async def close(self) -> None:
        self.closed = True


def build_client(
    database: FakeDependency | None = None,
    cache: FakeDependency | None = None,
    settings: Settings | None = None,
) -> TestClient:
    resources = RuntimeResources(
        database=database or FakeDependency(),
        cache=cache or FakeDependency(),
    )
    return TestClient(
        create_app(settings=settings or Settings(environment="test"), resources=resources)
    )


def test_service_metadata_and_liveness() -> None:
    with build_client() as client:
        info = client.get("/")
        live = client.get("/api/v1/health/live")

    assert info.status_code == 200
    assert info.json() == {"name": "SentinelFlow", "version": "0.1.0", "environment": "test"}
    assert live.status_code == 200
    assert live.json() == {"status": "ok"}


def test_readiness_reports_connected_dependencies() -> None:
    with build_client() as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "checks": {"database": "ok", "redis": "ok"},
    }


def test_readiness_hides_dependency_errors() -> None:
    with build_client(database=FakeDependency(fail=True)) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json() == {
        "status": "not_ready",
        "checks": {"database": "error", "redis": "ok"},
    }
    assert "sensitive" not in response.text


def test_readiness_times_out_slow_dependencies() -> None:
    settings = Settings(environment="test", dependency_timeout_seconds=0.001)
    with build_client(cache=FakeDependency(delay=0.02), settings=settings) as client:
        response = client.get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json()["checks"]["redis"] == "error"


def test_injected_resources_are_not_owned_by_app() -> None:
    database = FakeDependency()
    cache = FakeDependency()
    with build_client(database=database, cache=cache):
        pass

    assert database.closed is False
    assert cache.closed is False


def test_app_closes_resources_it_creates(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    database = FakeDependency()
    cache = FakeDependency()
    monkeypatch.setattr(app_module, "Database", lambda _url: database)
    monkeypatch.setattr(app_module, "RedisCache", lambda _url: cache)

    with TestClient(create_app(settings=Settings(environment="test"))):
        pass

    assert database.closed is True
    assert cache.closed is True


def test_production_hides_interactive_docs_and_allows_empty_cors() -> None:
    settings = Settings(environment="production", cors_origins=[])
    with build_client(settings=settings) as client:
        response = client.get("/docs")

    assert response.status_code == 404
