from typing import Any
from uuid import uuid4

import pytest

from sentinelflow.domain import (
    IdempotencyConflict,
    IncidentEventType,
    IncidentNotFound,
    IncidentSeverity,
    IncidentStatus,
    InvalidIncidentTransition,
    VersionConflict,
)


@pytest.mark.asyncio
async def test_create_is_idempotent_and_workspace_isolated(incident_runtime: Any) -> None:
    workspace_id = uuid4()
    other_workspace_id = uuid4()
    service = incident_runtime.service

    created = await service.create(
        workspace_id=workspace_id,
        title="Malware beacon",
        description="Periodic outbound traffic",
        severity=IncidentSeverity.CRITICAL,
        actor_id="analyst@example.com",
        idempotency_key="create-001",
    )
    replayed = await service.create(
        workspace_id=workspace_id,
        title="Malware beacon",
        description="Periodic outbound traffic",
        severity=IncidentSeverity.CRITICAL,
        actor_id="analyst@example.com",
        idempotency_key="create-001",
    )

    assert replayed.id == created.id
    assert created.status is IncidentStatus.NEW
    assert created.version == 1
    with pytest.raises(IncidentNotFound):
        await service.get(workspace_id=other_workspace_id, incident_id=created.id)

    separate = await service.create(
        workspace_id=other_workspace_id,
        title="Separate workspace incident",
        description="",
        severity=IncidentSeverity.LOW,
        actor_id="other-analyst",
        idempotency_key="create-001",
    )
    assert separate.id != created.id


@pytest.mark.asyncio
async def test_idempotency_key_reuse_with_different_create_is_rejected(
    incident_runtime: Any,
) -> None:
    workspace_id = uuid4()
    service = incident_runtime.service
    await service.create(
        workspace_id=workspace_id,
        title="Original",
        description="",
        severity=IncidentSeverity.MEDIUM,
        actor_id="analyst",
        idempotency_key="shared-key",
    )

    with pytest.raises(IdempotencyConflict):
        await service.create(
            workspace_id=workspace_id,
            title="Different",
            description="",
            severity=IncidentSeverity.MEDIUM,
            actor_id="analyst",
            idempotency_key="shared-key",
        )


@pytest.mark.asyncio
async def test_transition_records_timeline_and_rejects_stale_or_invalid_writes(
    incident_runtime: Any,
) -> None:
    workspace_id = uuid4()
    service = incident_runtime.service
    incident = await service.create(
        workspace_id=workspace_id,
        title="Credential anomaly",
        description="",
        severity=IncidentSeverity.HIGH,
        actor_id="detector",
        idempotency_key="create-transition",
    )

    transitioned = await service.transition(
        workspace_id=workspace_id,
        incident_id=incident.id,
        target=IncidentStatus.TRIAGING,
        reason="Assigned to tier 1",
        expected_version=1,
        actor_id="lead-analyst",
        idempotency_key="transition-001",
    )
    replayed = await service.transition(
        workspace_id=workspace_id,
        incident_id=incident.id,
        target=IncidentStatus.TRIAGING,
        reason="Assigned to tier 1",
        expected_version=1,
        actor_id="lead-analyst",
        idempotency_key="transition-001",
    )

    assert transitioned.status is IncidentStatus.TRIAGING
    assert transitioned.version == 2
    assert replayed.version == 2

    with pytest.raises(VersionConflict):
        await service.transition(
            workspace_id=workspace_id,
            incident_id=incident.id,
            target=IncidentStatus.INVESTIGATING,
            reason="Stale client",
            expected_version=1,
            actor_id="analyst",
            idempotency_key="transition-stale",
        )

    with pytest.raises(InvalidIncidentTransition):
        await service.transition(
            workspace_id=workspace_id,
            incident_id=incident.id,
            target=IncidentStatus.RESPONDING,
            reason="Skipped required states",
            expected_version=2,
            actor_id="analyst",
            idempotency_key="transition-invalid",
        )

    with pytest.raises(IdempotencyConflict):
        await service.transition(
            workspace_id=workspace_id,
            incident_id=incident.id,
            target=IncidentStatus.INVESTIGATING,
            reason="Different reuse",
            expected_version=2,
            actor_id="lead-analyst",
            idempotency_key="transition-001",
        )

    with pytest.raises(IdempotencyConflict):
        await service.transition(
            workspace_id=workspace_id,
            incident_id=incident.id,
            target=IncidentStatus.TRIAGING,
            reason="Assigned to tier 1",
            expected_version=2,
            actor_id="lead-analyst",
            idempotency_key="transition-001",
        )


@pytest.mark.asyncio
async def test_notes_are_append_only_cursor_paginated_timeline_entries(
    incident_runtime: Any,
) -> None:
    workspace_id = uuid4()
    service = incident_runtime.service
    incident = await service.create(
        workspace_id=workspace_id,
        title="Suspicious process",
        description="",
        severity=IncidentSeverity.MEDIUM,
        actor_id="detector",
        idempotency_key="create-note",
    )

    note = await service.add_note(
        workspace_id=workspace_id,
        incident_id=incident.id,
        body="Memory image acquisition started",
        expected_version=1,
        actor_id="forensics",
        idempotency_key="note-001",
    )
    replayed = await service.add_note(
        workspace_id=workspace_id,
        incident_id=incident.id,
        body="Memory image acquisition started",
        expected_version=1,
        actor_id="forensics",
        idempotency_key="note-001",
    )
    timeline = await service.timeline(
        workspace_id=workspace_id,
        incident_id=incident.id,
        after_sequence=1,
        limit=1,
    )

    assert note.event_type is IncidentEventType.NOTE_ADDED
    assert note.sequence == 2
    assert replayed.id == note.id
    assert [event.id for event in timeline] == [note.id]

    with pytest.raises(IdempotencyConflict):
        await service.add_note(
            workspace_id=workspace_id,
            incident_id=incident.id,
            body="Changed body",
            expected_version=2,
            actor_id="forensics",
            idempotency_key="note-001",
        )

    with pytest.raises(IdempotencyConflict):
        await service.add_note(
            workspace_id=workspace_id,
            incident_id=incident.id,
            body="Memory image acquisition started",
            expected_version=2,
            actor_id="forensics",
            idempotency_key="note-001",
        )

    with pytest.raises(VersionConflict):
        await service.add_note(
            workspace_id=workspace_id,
            incident_id=incident.id,
            body="Stale note",
            expected_version=1,
            actor_id="forensics",
            idempotency_key="note-stale",
        )


@pytest.mark.asyncio
async def test_list_filters_and_paginates_within_workspace(incident_runtime: Any) -> None:
    workspace_id = uuid4()
    service = incident_runtime.service
    first = await service.create(
        workspace_id=workspace_id,
        title="First",
        description="",
        severity=IncidentSeverity.LOW,
        actor_id="analyst",
        idempotency_key="list-1",
    )
    second = await service.create(
        workspace_id=workspace_id,
        title="Second",
        description="",
        severity=IncidentSeverity.HIGH,
        actor_id="analyst",
        idempotency_key="list-2",
    )
    await service.transition(
        workspace_id=workspace_id,
        incident_id=first.id,
        target=IncidentStatus.TRIAGING,
        reason="Begin triage",
        expected_version=1,
        actor_id="analyst",
        idempotency_key="list-transition",
    )

    new_incidents = await service.list(
        workspace_id=workspace_id,
        status=IncidentStatus.NEW,
        limit=10,
        offset=0,
    )
    page = await service.list(
        workspace_id=workspace_id,
        status=None,
        limit=1,
        offset=1,
    )

    assert [incident.id for incident in new_incidents] == [second.id]
    assert len(page) == 1
