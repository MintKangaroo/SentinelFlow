from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from sentinelflow.application import (
    ApprovalService,
    PlaybookService,
    WorkflowDispatcher,
    WorkflowService,
)
from sentinelflow.domain import (
    ApprovalDecisionValue,
    ApprovalStatus,
    IncidentSeverity,
    PlaybookStepKind,
    WorkflowStatus,
)
from sentinelflow.infrastructure import (
    SQLAlchemyApprovalUnitOfWork,
    SQLAlchemyPlaybookUnitOfWork,
    SQLAlchemyWorkflowUnitOfWork,
)
from sentinelflow.integrations import (
    AdapterHTTPError,
    AdapterResponse,
    AdapterTransportError,
)
from tests.unit.conftest import AdvancingClock
from tests.unit.playbooks.helpers import safe_response_steps


class MemoryLeaseManager:
    def __init__(self, *, available: bool = True) -> None:
        self.available = available
        self.held: set[str] = set()

    async def acquire(self, key: str, owner: str, ttl_seconds: int) -> bool:
        del ttl_seconds
        if not self.available or key in self.held:
            return False
        self.held.add(key)
        return bool(owner)

    async def release(self, key: str, owner: str) -> None:
        del owner
        self.held.discard(key)


class RecordingExecutor:
    def __init__(
        self,
        *,
        transient_failures: int = 0,
        fail_validation: bool = False,
    ) -> None:
        self.transient_failures = transient_failures
        self.fail_validation = fail_validation
        self.calls: list[str] = []
        self.compensations: list[str] = []

    async def execute(self, *, workflow: Any, step: Any, idempotency_key: str) -> Any:
        del workflow
        self.calls.append(idempotency_key)
        if self.transient_failures:
            self.transient_failures -= 1
            raise AdapterTransportError("test-adapter")
        if self.fail_validation and step.kind is PlaybookStepKind.VALIDATION:
            raise AdapterHTTPError(
                "test-adapter",
                AdapterResponse(status_code=400, headers={}, content=b""),
            )
        return {"evidence": step.step_key, "external_side_effect": False}

    async def compensate(self, *, workflow: Any, step: Any, idempotency_key: str) -> Any:
        del workflow
        self.compensations.append(idempotency_key)
        return {"compensated": step.step_key}


async def dispatcher_runtime(
    incident_runtime: Any,
    executor: RecordingExecutor,
    lease: MemoryLeaseManager | None = None,
) -> tuple[Any, WorkflowService, ApprovalService, WorkflowDispatcher]:
    workspace_id = uuid4()
    incident = await incident_runtime.service.create(
        workspace_id=workspace_id,
        title="Dispatcher incident",
        description="",
        severity=IncidentSeverity.CRITICAL,
        actor_id="detector",
        idempotency_key=f"dispatch-incident-{uuid4()}",
    )
    playbooks = PlaybookService(
        lambda: SQLAlchemyPlaybookUnitOfWork(incident_runtime.database.session_factory),
        clock=AdvancingClock(),
    )
    playbook, _ = await playbooks.create(
        workspace_id=workspace_id,
        name="Dispatch playbook",
        description="",
        steps=safe_response_steps(),
        actor_id="author",
        idempotency_key=f"dispatch-playbook-{uuid4()}",
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
        idempotency_key=f"dispatch-workflow-{uuid4()}",
    )
    approvals = ApprovalService(
        lambda: SQLAlchemyApprovalUnitOfWork(incident_runtime.database.session_factory),
        clock=AdvancingClock(),
    )
    dispatcher = WorkflowDispatcher(
        workflows,
        approvals,
        executor,
        lease or MemoryLeaseManager(),
        clock=lambda: datetime(2026, 7, 22, 12, 0, tzinfo=UTC),
    )
    return workflow, workflows, approvals, dispatcher


async def approve_current(
    workflow: Any,
    approvals: ApprovalService,
) -> None:
    request = (
        await approvals.list(
            workspace_id=workflow.workspace_id,
            status=ApprovalStatus.PENDING,
            workflow_id=workflow.id,
            limit=10,
            offset=0,
        )
    )[0]
    await approvals.decide(
        workspace_id=workflow.workspace_id,
        approval_id=request.id,
        decision=ApprovalDecisionValue.APPROVE,
        actor_role="soc_lead",
        reason="Scope reviewed",
        expected_version=1,
        actor_id="lead@example.com",
        idempotency_key=f"dispatch-approval-one-{workflow.id}",
    )
    await approvals.decide(
        workspace_id=workflow.workspace_id,
        approval_id=request.id,
        decision=ApprovalDecisionValue.APPROVE,
        actor_role="incident_commander",
        reason="Evidence reviewed",
        expected_version=2,
        actor_id="commander@example.com",
        idempotency_key=f"dispatch-approval-two-{workflow.id}",
    )


@pytest.mark.asyncio
async def test_dispatcher_runs_to_approval_then_terminal_success(
    incident_runtime: Any,
) -> None:
    executor = RecordingExecutor()
    workflow, workflows, approvals, dispatcher = await dispatcher_runtime(
        incident_runtime, executor
    )
    blocked = await dispatcher.dispatch(workflow.workspace_id, workflow.id)
    assert blocked.blocked_reason == "approval_pending"
    assert blocked.transitions == 2
    await approve_current(workflow, approvals)
    finished = await dispatcher.dispatch(workflow.workspace_id, workflow.id)
    persisted = await workflows.get(
        workspace_id=workflow.workspace_id,
        workflow_id=workflow.id,
    )
    assert finished.blocked_reason == "succeeded"
    assert persisted.status is WorkflowStatus.SUCCEEDED
    assert len(executor.calls) == 3


@pytest.mark.asyncio
async def test_dispatcher_retries_transient_failure_with_stable_attempts(
    incident_runtime: Any,
) -> None:
    executor = RecordingExecutor(transient_failures=2)
    workflow, workflows, _approvals, dispatcher = await dispatcher_runtime(
        incident_runtime, executor
    )
    result = await dispatcher.dispatch(workflow.workspace_id, workflow.id)
    persisted = await workflows.get(
        workspace_id=workflow.workspace_id,
        workflow_id=workflow.id,
    )
    assert result.blocked_reason == "approval_pending"
    assert persisted.steps[0].attempt == 3
    assert len(executor.calls) == 3


@pytest.mark.asyncio
async def test_dispatcher_respects_delivery_lease(incident_runtime: Any) -> None:
    executor = RecordingExecutor()
    workflow, _workflows, _approvals, dispatcher = await dispatcher_runtime(
        incident_runtime,
        executor,
        MemoryLeaseManager(available=False),
    )
    result = await dispatcher.dispatch(workflow.workspace_id, workflow.id)
    assert result.blocked_reason == "step_leased"
    assert result.transitions == 1
    assert executor.calls == []


@pytest.mark.asyncio
async def test_non_retryable_validation_failure_compensates_action(
    incident_runtime: Any,
) -> None:
    executor = RecordingExecutor(fail_validation=True)
    workflow, workflows, approvals, dispatcher = await dispatcher_runtime(
        incident_runtime, executor
    )
    await dispatcher.dispatch(workflow.workspace_id, workflow.id)
    await approve_current(workflow, approvals)
    result = await dispatcher.dispatch(workflow.workspace_id, workflow.id)
    persisted = await workflows.get(
        workspace_id=workflow.workspace_id,
        workflow_id=workflow.id,
    )
    assert result.blocked_reason == "failed"
    assert persisted.status is WorkflowStatus.FAILED
    assert len(executor.compensations) == 1
