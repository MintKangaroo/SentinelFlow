from typing import Any
from uuid import uuid4

import pytest

from sentinelflow.application import PlaybookService
from sentinelflow.domain import (
    PlaybookArchived,
    PlaybookIdempotencyConflict,
    PlaybookNotFound,
    PlaybookStatus,
    PlaybookVersionConflict,
)
from sentinelflow.infrastructure import SQLAlchemyPlaybookUnitOfWork
from tests.unit.conftest import AdvancingClock
from tests.unit.playbooks.helpers import low_risk_steps, safe_response_steps


def service_for(runtime: Any) -> PlaybookService:
    return PlaybookService(
        lambda: SQLAlchemyPlaybookUnitOfWork(runtime.database.session_factory),
        clock=AdvancingClock(),
    )


@pytest.mark.asyncio
async def test_create_is_idempotent_and_workspace_isolated(incident_runtime: Any) -> None:
    service = service_for(incident_runtime)
    workspace_id = uuid4()
    other_workspace_id = uuid4()

    playbook, revision = await service.create(
        workspace_id=workspace_id,
        name="Critical endpoint containment",
        description="Contain and validate an affected endpoint",
        steps=safe_response_steps(),
        actor_id="author@example.com",
        idempotency_key="create-playbook",
    )
    replayed, replayed_revision = await service.create(
        workspace_id=workspace_id,
        name="Critical endpoint containment",
        description="Contain and validate an affected endpoint",
        steps=safe_response_steps(),
        actor_id="author@example.com",
        idempotency_key="create-playbook",
    )

    assert replayed.id == playbook.id
    assert replayed_revision.id == revision.id
    assert revision.number == 1
    assert playbook.status is PlaybookStatus.DRAFT
    with pytest.raises(PlaybookNotFound):
        await service.get(workspace_id=other_workspace_id, playbook_id=playbook.id)

    with pytest.raises(PlaybookIdempotencyConflict):
        await service.create(
            workspace_id=workspace_id,
            name="Different",
            description="",
            steps=low_risk_steps(),
            actor_id="author@example.com",
            idempotency_key="create-playbook",
        )


@pytest.mark.asyncio
async def test_revision_publish_and_audit_history(incident_runtime: Any) -> None:
    service = service_for(incident_runtime)
    workspace_id = uuid4()
    playbook, _ = await service.create(
        workspace_id=workspace_id,
        name="Response",
        description="",
        steps=low_risk_steps(),
        actor_id="author",
        idempotency_key="response-create",
    )
    revised, revision = await service.create_version(
        workspace_id=workspace_id,
        playbook_id=playbook.id,
        steps=safe_response_steps(),
        expected_version=1,
        actor_id="author",
        idempotency_key="response-v2",
    )
    replayed, replayed_revision = await service.create_version(
        workspace_id=workspace_id,
        playbook_id=playbook.id,
        steps=safe_response_steps(),
        expected_version=1,
        actor_id="author",
        idempotency_key="response-v2",
    )
    published = await service.publish(
        workspace_id=workspace_id,
        playbook_id=playbook.id,
        revision=2,
        expected_version=2,
        actor_id="lead",
        idempotency_key="response-publish",
    )
    versions = await service.list_versions(
        workspace_id=workspace_id,
        playbook_id=playbook.id,
    )
    events = await service.events(
        workspace_id=workspace_id,
        playbook_id=playbook.id,
        limit=10,
    )

    assert revised.latest_version == 2
    assert replayed_revision.id == revision.id
    assert replayed.latest_version == 2
    assert published.active_version == 2
    assert published.status is PlaybookStatus.ACTIVE
    assert [version.number for version in versions] == [2, 1]
    assert [event.sequence for event in events] == [1, 2, 3]


@pytest.mark.asyncio
async def test_stale_writes_and_archived_playbooks_are_rejected(incident_runtime: Any) -> None:
    service = service_for(incident_runtime)
    workspace_id = uuid4()
    playbook, _ = await service.create(
        workspace_id=workspace_id,
        name="Archive",
        description="",
        steps=low_risk_steps(),
        actor_id="author",
        idempotency_key="archive-create",
    )

    with pytest.raises(PlaybookVersionConflict):
        await service.publish(
            workspace_id=workspace_id,
            playbook_id=playbook.id,
            revision=1,
            expected_version=99,
            actor_id="lead",
            idempotency_key="stale-publish",
        )

    archived = await service.archive(
        workspace_id=workspace_id,
        playbook_id=playbook.id,
        expected_version=1,
        actor_id="lead",
        idempotency_key="archive-command",
    )
    replayed = await service.archive(
        workspace_id=workspace_id,
        playbook_id=playbook.id,
        expected_version=1,
        actor_id="lead",
        idempotency_key="archive-command",
    )
    assert replayed.version == archived.version

    with pytest.raises(PlaybookArchived):
        await service.create_version(
            workspace_id=workspace_id,
            playbook_id=playbook.id,
            steps=low_risk_steps(),
            expected_version=2,
            actor_id="author",
            idempotency_key="archived-revision",
        )
