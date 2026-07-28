from typing import Any
from uuid import uuid4

import pytest

from sentinelflow.application import PlaybookService, WorkflowService
from sentinelflow.domain import IncidentSeverity, WorkflowIdempotencyConflict, WorkflowStatus
from sentinelflow.infrastructure import (
    SQLAlchemyPlaybookUnitOfWork,
    SQLAlchemyWorkflowUnitOfWork,
)
from tests.unit.conftest import AdvancingClock
from tests.unit.playbooks.helpers import safe_response_steps


@pytest.mark.asyncio
async def test_service_snapshots_revision_and_records_idempotent_events(
    incident_runtime: Any,
) -> None:
    workspace_id = uuid4()
    incident = await incident_runtime.service.create(
        workspace_id=workspace_id,
        title="Workflow incident",
        description="",
        severity=IncidentSeverity.CRITICAL,
        actor_id="detector",
        idempotency_key="workflow-incident",
    )
    playbooks = PlaybookService(
        lambda: SQLAlchemyPlaybookUnitOfWork(incident_runtime.database.session_factory),
        clock=AdvancingClock(),
    )
    playbook, revision = await playbooks.create(
        workspace_id=workspace_id,
        name="Containment",
        description="",
        steps=safe_response_steps(),
        actor_id="author",
        idempotency_key="workflow-playbook",
    )
    workflows = WorkflowService(
        lambda: SQLAlchemyWorkflowUnitOfWork(incident_runtime.database.session_factory),
        clock=AdvancingClock(),
    )
    workflow = await workflows.create(
        workspace_id=workspace_id,
        incident_id=incident.id,
        playbook_id=playbook.id,
        playbook_version=1,
        actor_id="operator",
        idempotency_key="workflow-create",
    )
    replayed = await workflows.create(
        workspace_id=workspace_id,
        incident_id=incident.id,
        playbook_id=playbook.id,
        playbook_version=1,
        actor_id="operator",
        idempotency_key="workflow-create",
    )
    started = await workflows.start(
        workspace_id=workspace_id,
        workflow_id=workflow.id,
        expected_version=1,
        actor_id="worker",
        idempotency_key="workflow-start",
    )
    start_replay = await workflows.start(
        workspace_id=workspace_id,
        workflow_id=workflow.id,
        expected_version=1,
        actor_id="worker",
        idempotency_key="workflow-start",
    )

    assert replayed.id == workflow.id
    assert workflow.definition_hash == revision.definition_hash
    assert len(workflow.steps) == len(revision.steps)
    assert started.status is WorkflowStatus.RUNNING
    assert start_replay.version == started.version

    with pytest.raises(WorkflowIdempotencyConflict):
        await workflows.start(
            workspace_id=workspace_id,
            workflow_id=workflow.id,
            expected_version=2,
            actor_id="worker",
            idempotency_key="workflow-start",
        )
