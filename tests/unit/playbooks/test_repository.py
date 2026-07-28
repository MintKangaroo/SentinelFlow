from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select

from sentinelflow.application import PlaybookService
from sentinelflow.domain import ConcurrentPlaybookWrite
from sentinelflow.infrastructure import SQLAlchemyPlaybookUnitOfWork
from sentinelflow.infrastructure.playbooks import (
    ImmutablePlaybookRecordError,
    PlaybookEventRecord,
    PlaybookVersionRecord,
)
from tests.unit.conftest import AdvancingClock
from tests.unit.playbooks.helpers import low_risk_steps


@pytest.mark.asyncio
async def test_repository_rejects_concurrent_write_and_immutable_mutation(
    incident_runtime: Any,
) -> None:
    service = PlaybookService(
        lambda: SQLAlchemyPlaybookUnitOfWork(incident_runtime.database.session_factory),
        clock=AdvancingClock(),
    )
    workspace_id = uuid4()
    playbook, _ = await service.create(
        workspace_id=workspace_id,
        name="Immutable",
        description="",
        steps=low_risk_steps(),
        actor_id="author",
        idempotency_key="immutable-create",
    )

    with pytest.raises(ConcurrentPlaybookWrite):
        async with SQLAlchemyPlaybookUnitOfWork(
            incident_runtime.database.session_factory
        ) as unit_of_work:
            loaded = await unit_of_work.playbooks.get(workspace_id, playbook.id, for_update=True)
            assert loaded is not None
            loaded.version += 1
            await unit_of_work.playbooks.save(loaded, previous_version=99)

    for record_type in (PlaybookVersionRecord, PlaybookEventRecord):
        async with incident_runtime.database.session_factory() as session:
            record = (await session.execute(select(record_type))).scalars().first()
            assert record is not None
            await session.delete(record)
            with pytest.raises(ImmutablePlaybookRecordError, match="append-only"):
                await session.commit()
