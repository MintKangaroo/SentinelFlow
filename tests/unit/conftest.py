from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest_asyncio

from sentinelflow.application import IncidentService
from sentinelflow.infrastructure import Database, SQLAlchemyIncidentUnitOfWork
from sentinelflow.infrastructure.models import Base


class AdvancingClock:
    def __init__(self) -> None:
        self._current = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        current = self._current
        self._current += timedelta(seconds=1)
        return current


@dataclass(frozen=True, slots=True)
class IncidentRuntime:
    database: Database
    service: IncidentService


@pytest_asyncio.fixture
async def incident_runtime() -> AsyncIterator[IncidentRuntime]:
    database = Database("sqlite+aiosqlite:///:memory:")
    async with database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    service = IncidentService(
        lambda: SQLAlchemyIncidentUnitOfWork(database.session_factory),
        clock=AdvancingClock(),
    )
    yield IncidentRuntime(database=database, service=service)
    await database.close()
