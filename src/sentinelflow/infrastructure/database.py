"""PostgreSQL connection lifecycle and health probing."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class Database:
    """Own the async SQLAlchemy engine used by the API process."""

    def __init__(self, url: str) -> None:
        self._engine = create_async_engine(url, pool_pre_ping=True)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

    @property
    def engine(self) -> AsyncEngine:
        """Expose the engine for future repository adapters."""
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """Create isolated sessions for application unit-of-work adapters."""
        return self._session_factory

    async def check(self) -> None:
        """Raise when PostgreSQL is not ready to accept a simple query."""
        async with self._engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    async def close(self) -> None:
        """Dispose all pooled database connections."""
        await self._engine.dispose()
