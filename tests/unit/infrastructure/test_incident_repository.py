from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select

from sentinelflow.domain import (
    ConcurrentIncidentWrite,
    IncidentEvent,
    IncidentEventType,
    IncidentSeverity,
)
from sentinelflow.infrastructure.incidents import (
    ImmutableIncidentEventError,
    IncidentEventRecord,
    SQLAlchemyIncidentUnitOfWork,
)


@pytest.mark.asyncio
async def test_repository_detects_concurrent_aggregate_write(incident_runtime) -> None:  # type: ignore[no-untyped-def]
    workspace_id = uuid4()
    incident = await incident_runtime.service.create(
        workspace_id=workspace_id,
        title="Concurrent write",
        description="",
        severity=IncidentSeverity.MEDIUM,
        actor_id="analyst",
        idempotency_key="concurrent-create",
    )

    with pytest.raises(ConcurrentIncidentWrite):
        async with SQLAlchemyIncidentUnitOfWork(
            incident_runtime.database.session_factory
        ) as unit_of_work:
            loaded = await unit_of_work.incidents.get(workspace_id, incident.id, for_update=True)
            assert loaded is not None
            loaded.record_timeline_entry(datetime.now(UTC))
            await unit_of_work.incidents.save(loaded, previous_version=99)


@pytest.mark.asyncio
async def test_timeline_records_reject_update_and_delete(incident_runtime) -> None:  # type: ignore[no-untyped-def]
    workspace_id = uuid4()
    await incident_runtime.service.create(
        workspace_id=workspace_id,
        title="Immutable timeline",
        description="",
        severity=IncidentSeverity.LOW,
        actor_id="analyst",
        idempotency_key="immutable-create",
    )

    async with incident_runtime.database.session_factory() as session:
        record = (await session.execute(select(IncidentEventRecord))).scalar_one()
        record.actor_id = "changed"
        with pytest.raises(ImmutableIncidentEventError, match="append-only"):
            await session.commit()
        await session.rollback()

    async with incident_runtime.database.session_factory() as session:
        record = (await session.execute(select(IncidentEventRecord))).scalar_one()
        await session.delete(record)
        with pytest.raises(ImmutableIncidentEventError, match="append-only"):
            await session.commit()


@pytest.mark.asyncio
async def test_unit_of_work_maps_integrity_error_and_requires_entry(incident_runtime) -> None:  # type: ignore[no-untyped-def]
    unit_of_work = SQLAlchemyIncidentUnitOfWork(incident_runtime.database.session_factory)
    with pytest.raises(RuntimeError, match="not been entered"):
        await unit_of_work.commit()

    workspace_id = uuid4()
    incident = await incident_runtime.service.create(
        workspace_id=workspace_id,
        title="Duplicate event",
        description="",
        severity=IncidentSeverity.HIGH,
        actor_id="analyst",
        idempotency_key="duplicate-create",
    )
    duplicate = IncidentEvent(
        id=uuid4(),
        workspace_id=workspace_id,
        incident_id=incident.id,
        sequence=1,
        event_type=IncidentEventType.NOTE_ADDED,
        actor_id="analyst",
        idempotency_key="different-key",
        data={"body": "duplicate sequence"},
        occurred_at=datetime.now(UTC),
    )

    with pytest.raises(ConcurrentIncidentWrite):
        async with unit_of_work:
            await unit_of_work.incidents.add_event(duplicate)
            await unit_of_work.commit()
