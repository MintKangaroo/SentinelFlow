"""Redis-backed ephemeral workflow leases."""

from collections.abc import Awaitable
from typing import Any, cast

from redis.asyncio import Redis

_RELEASE_IF_OWNER = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""


class RedisWorkflowLeaseManager:
    """Acquire bounded Redis leases while PostgreSQL remains the state ledger."""

    def __init__(self, client: Redis) -> None:
        self._client = client

    async def acquire(self, key: str, owner: str, ttl_seconds: int) -> bool:
        acquired = await self._client.set(
            f"sentinelflow:lease:{key}",
            owner,
            ex=ttl_seconds,
            nx=True,
        )
        return bool(acquired)

    async def release(self, key: str, owner: str) -> None:
        await cast(
            Awaitable[Any],
            self._client.eval(
                _RELEASE_IF_OWNER,
                1,
                f"sentinelflow:lease:{key}",
                owner,
            ),
        )
