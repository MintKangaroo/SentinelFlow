from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import pytest

from sentinelflow.application import ApprovalService, PlaybookService, WorkflowService
from sentinelflow.domain import (
    ApprovalDecisionValue,
    ApprovalIdempotencyConflict,
    ApprovalStatus,
    IncidentSeverity,
    PlaybookStepRisk,
)
from sentinelflow.infrastructure import (
    SQLAlchemyApprovalUnitOfWork,
    SQLAlchemyPlaybookUnitOfWork,
    SQLAlchemyWorkflowUnitOfWork,
)
from tests.unit.conftest import AdvancingClock
from tests.unit.playbooks.helpers import safe_response_steps


class MutableClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 7, 28, 4, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.current


async def waiting_workflow(
    incident_runtime: Any,
    *,
    workspace_id: Any,
    playbook_id: Any,
    suffix: str,
) -> tuple[Any, Any]:
    incident = await incident_runtime.service.create(
        workspace_id=workspace_id,
        title=f"Approval incident {suffix}",
        description="",
        severity=IncidentSeverity.CRITICAL,
        actor_id="detector",
        idempotency_key=f"approval-incident-{suffix}",
    )
    service = WorkflowService(
        lambda: SQLAlchemyWorkflowUnitOfWork(incident_runtime.database.session_factory),
        clock=AdvancingClock(),
    )
    workflow = await service.create(
        workspace_id=workspace_id,
        incident_id=incident.id,
        playbook_id=playbook_id,
        playbook_version=1,
        actor_id="requester@example.com",
        idempotency_key=f"approval-workflow-{suffix}",
    )
    workflow = await service.start(
        workspace_id=workspace_id,
        workflow_id=workflow.id,
        expected_version=1,
        actor_id="worker",
        idempotency_key=f"approval-start-{suffix}",
    )
    workflow = await service.record_step_result(
        workspace_id=workspace_id,
        workflow_id=workflow.id,
        step_key="enrich_asset",
        succeeded=True,
        output={},
        error_code=None,
        expected_version=2,
        actor_id="worker",
        idempotency_key=f"approval-enrich-{suffix}",
    )
    return incident, workflow


@pytest.mark.asyncio
async def test_service_persists_quorum_and_idempotent_decisions(
    incident_runtime: Any,
) -> None:
    workspace_id = uuid4()
    playbooks = PlaybookService(
        lambda: SQLAlchemyPlaybookUnitOfWork(incident_runtime.database.session_factory),
        clock=AdvancingClock(),
    )
    playbook, _ = await playbooks.create(
        workspace_id=workspace_id,
        name="Approval playbook",
        description="",
        steps=safe_response_steps(),
        actor_id="author",
        idempotency_key="approval-playbook",
    )
    incident, workflow = await waiting_workflow(
        incident_runtime,
        workspace_id=workspace_id,
        playbook_id=playbook.id,
        suffix="quorum",
    )
    clock = MutableClock()
    approvals = ApprovalService(
        lambda: SQLAlchemyApprovalUnitOfWork(incident_runtime.database.session_factory),
        clock=clock,
    )
    approval = await approvals.create(
        workspace_id=workspace_id,
        incident_id=incident.id,
        workflow_id=workflow.id,
        step_key="approve_isolation",
        action_summary="Isolate endpoint",
        risk=PlaybookStepRisk.CRITICAL,
        required_approvals=2,
        eligible_roles=("soc_lead", "incident_commander"),
        expires_at=clock.current + timedelta(hours=1),
        actor_id="requester@example.com",
        idempotency_key="approval-create",
    )
    replay = await approvals.create(
        workspace_id=workspace_id,
        incident_id=incident.id,
        workflow_id=workflow.id,
        step_key="approve_isolation",
        action_summary="Isolate endpoint",
        risk=PlaybookStepRisk.CRITICAL,
        required_approvals=2,
        eligible_roles=("soc_lead", "incident_commander"),
        expires_at=clock.current + timedelta(hours=1),
        actor_id="requester@example.com",
        idempotency_key="approval-create",
    )
    first = await approvals.decide(
        workspace_id=workspace_id,
        approval_id=approval.id,
        decision=ApprovalDecisionValue.APPROVE,
        actor_role="soc_lead",
        reason="Scope reviewed",
        expected_version=1,
        actor_id="lead@example.com",
        idempotency_key="approval-first",
    )
    first_replay = await approvals.decide(
        workspace_id=workspace_id,
        approval_id=approval.id,
        decision=ApprovalDecisionValue.APPROVE,
        actor_role="soc_lead",
        reason="Scope reviewed",
        expected_version=1,
        actor_id="lead@example.com",
        idempotency_key="approval-first",
    )
    second = await approvals.decide(
        workspace_id=workspace_id,
        approval_id=approval.id,
        decision=ApprovalDecisionValue.APPROVE,
        actor_role="incident_commander",
        reason="Evidence reviewed",
        expected_version=2,
        actor_id="commander@example.com",
        idempotency_key="approval-second",
    )

    assert replay.id == approval.id
    assert first.status is ApprovalStatus.PENDING
    assert first_replay.version == 2
    assert second.status is ApprovalStatus.APPROVED
    assert second.approval_count == 2
    assert (await approvals.get(workspace_id=workspace_id, approval_id=approval.id)).version == 3
    assert (
        len(
            await approvals.list(
                workspace_id=workspace_id,
                status=ApprovalStatus.APPROVED,
                workflow_id=workflow.id,
                limit=10,
                offset=0,
            )
        )
        == 1
    )
    assert [
        event.sequence
        for event in await approvals.events(
            workspace_id=workspace_id,
            approval_id=approval.id,
            limit=10,
        )
    ] == [1, 2, 3]
    with pytest.raises(ApprovalIdempotencyConflict):
        await approvals.decide(
            workspace_id=workspace_id,
            approval_id=approval.id,
            decision=ApprovalDecisionValue.APPROVE,
            actor_role="incident_commander",
            reason="Changed replay",
            expected_version=2,
            actor_id="commander@example.com",
            idempotency_key="approval-second",
        )


@pytest.mark.asyncio
async def test_service_expires_renews_and_cancels(incident_runtime: Any) -> None:
    workspace_id = uuid4()
    playbooks = PlaybookService(
        lambda: SQLAlchemyPlaybookUnitOfWork(incident_runtime.database.session_factory),
        clock=AdvancingClock(),
    )
    playbook, _ = await playbooks.create(
        workspace_id=workspace_id,
        name="Renewal playbook",
        description="",
        steps=safe_response_steps(),
        actor_id="author",
        idempotency_key="renewal-playbook",
    )
    incident, workflow = await waiting_workflow(
        incident_runtime,
        workspace_id=workspace_id,
        playbook_id=playbook.id,
        suffix="renewal",
    )
    clock = MutableClock()
    approvals = ApprovalService(
        lambda: SQLAlchemyApprovalUnitOfWork(incident_runtime.database.session_factory),
        clock=clock,
    )
    approval = await approvals.create(
        workspace_id=workspace_id,
        incident_id=incident.id,
        workflow_id=workflow.id,
        step_key="approve_isolation",
        action_summary="Isolate endpoint",
        risk=PlaybookStepRisk.HIGH,
        required_approvals=2,
        eligible_roles=("soc_lead", "incident_commander"),
        expires_at=clock.current + timedelta(minutes=5),
        actor_id="requester@example.com",
        idempotency_key="renewal-create",
    )
    clock.current += timedelta(minutes=5)
    expired = await approvals.expire(
        workspace_id=workspace_id,
        approval_id=approval.id,
        expected_version=1,
        actor_id="system",
        idempotency_key="renewal-expire",
    )
    renewed = await approvals.renew(
        workspace_id=workspace_id,
        approval_id=approval.id,
        expires_at=clock.current + timedelta(hours=1),
        reason="Evidence package updated",
        expected_version=2,
        actor_id="requester@example.com",
        idempotency_key="renewal-renew",
    )
    cancelled = await approvals.cancel(
        workspace_id=workspace_id,
        approval_id=approval.id,
        expected_version=3,
        actor_id="requester@example.com",
        idempotency_key="renewal-cancel",
    )
    assert expired.status is ApprovalStatus.EXPIRED
    assert renewed.round == 2
    assert cancelled.status is ApprovalStatus.CANCELLED
