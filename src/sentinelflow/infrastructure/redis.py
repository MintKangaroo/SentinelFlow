"""Redis connection lifecycle and health probing."""

from redis.asyncio import Redis


class RedisCache:
    """Own the Redis client used for ephemeral control-plane coordination."""

    def __init__(self, url: str) -> None:
        self._client: Redis = Redis.from_url(url, decode_responses=True)

    @property
    def client(self) -> Redis:
        """Expose the client for future infrastructure adapters."""
        return self._client

    async def check(self) -> None:
        """Raise when Redis does not answer a ping."""
        await self._client.ping()

    async def close(self) -> None:
        """Close the Redis connection pool."""
        await self._client.aclose()
