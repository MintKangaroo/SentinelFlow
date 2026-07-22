from unittest.mock import AsyncMock, MagicMock

import pytest

import sentinelflow.infrastructure.database as database_module
import sentinelflow.infrastructure.redis as redis_module
from sentinelflow.infrastructure import Database, RedisCache


@pytest.mark.asyncio
async def test_database_check_and_close(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    connection = AsyncMock()
    connection_context = MagicMock()
    connection_context.__aenter__ = AsyncMock(return_value=connection)
    connection_context.__aexit__ = AsyncMock(return_value=None)
    engine = MagicMock()
    engine.connect.return_value = connection_context
    engine.dispose = AsyncMock()
    factory = MagicMock(return_value=engine)
    monkeypatch.setattr(database_module, "create_async_engine", factory)

    database = Database("postgresql+asyncpg://example")
    await database.check()
    await database.close()

    assert database.engine is engine
    factory.assert_called_once_with("postgresql+asyncpg://example", pool_pre_ping=True)
    connection.execute.assert_awaited_once()
    engine.dispose.assert_awaited_once()


@pytest.mark.asyncio
async def test_redis_check_and_close(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client = MagicMock()
    client.ping = AsyncMock(return_value=True)
    client.aclose = AsyncMock()
    factory = MagicMock(return_value=client)
    redis_type = MagicMock()
    redis_type.from_url = factory
    monkeypatch.setattr(redis_module, "Redis", redis_type)

    cache = RedisCache("redis://example/0")
    await cache.check()
    await cache.close()

    assert cache.client is client
    factory.assert_called_once_with("redis://example/0", decode_responses=True)
    client.ping.assert_awaited_once()
    client.aclose.assert_awaited_once()
