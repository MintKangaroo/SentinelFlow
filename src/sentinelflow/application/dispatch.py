"""Recoverable workflow dispatch across approval and external-action boundaries."""

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID, uuid4

from sentinelflow.application.approvals import ApprovalService
from sentinelflow.application.incidents import utc_now
from sentinelflow.application.workflows import WorkflowService
from sentinelflow.domain import (
    ApprovalStatus,
    PlaybookStepRisk,
    WorkflowRun,
    WorkflowStatus,
    WorkflowStepRun,
    WorkflowStepStatus,
)
from sentinelflow.domain.playbook import JsonObject
from sentinelflow.integrations import (
    AdapterHTTPError,
    AdapterRequestError,
    AdapterTimeoutError,
    AdapterTransportError,
)


class WorkflowLeaseManager(Protocol):
    """Ephemeral lease preventing concurrent delivery of one workflow step."""

    async def acquire(self, key: str, owner: str, ttl_seconds: int) -> bool: ...

    async def release(self, key: str, owner: str) -> None: ...


class WorkflowStepExecutor(Protocol):
    """Execute one typed adapter operation behind a stable idempotency key."""

    async def execute(
        self,
        *,
        workflow: WorkflowRun,
        step: WorkflowStepRun,
        idempotency_key: str,
    ) -> JsonObject: ...

    async def compensate(
        self,
        *,
        workflow: WorkflowRun,
        step: WorkflowStepRun,
        idempotency_key: str,
    ) -> JsonObject: ...


class WorkflowDispatchScheduler(Protocol):
    """Schedule a recoverable workflow dispatch task."""

    async def schedule(self, workspace_id: UUID, workflow_id: UUID) -> None: ...


class NoopWorkflowDispatchScheduler:
    """Test and embedded scheduler that intentionally performs no delivery."""

    async def schedule(self, workspace_id: UUID, workflow_id: UUID) -> None:
        del workspace_id, workflow_id


@dataclass(frozen=True, slots=True)
class DispatchResult:
    """Outcome of one bounded dispatcher run."""

    workflow: WorkflowRun
    transitions: int
    blocked_reason: str


class WorkflowDispatcher:
    """Advance one workflow until it reaches a human, retry, or terminal boundary."""

    def __init__(
        self,
        workflows: WorkflowService,
        approvals: ApprovalService,
        executor: WorkflowStepExecutor,
        leases: WorkflowLeaseManager,
        *,
        clock: Callable[[], datetime] = utc_now,
        lease_seconds: int = 900,
        max_transitions: int = 50,
    ) -> None:
        self._workflows = workflows
        self._approvals = approvals
        self._executor = executor
        self._leases = leases
        self._clock = clock
        self._lease_seconds = lease_seconds
        self._max_transitions = max_transitions

    async def dispatch(self, workspace_id: UUID, workflow_id: UUID) -> DispatchResult:
        """Run bounded transitions and leave durable state at every boundary."""
        transitions = 0
        while transitions < self._max_transitions:
            workflow = await self._workflows.get(
                workspace_id=workspace_id,
                workflow_id=workflow_id,
            )
            if workflow.status is WorkflowStatus.PENDING:
                await self._workflows.start(
                    workspace_id=workspace_id,
                    workflow_id=workflow_id,
                    expected_version=workflow.version,
                    actor_id="worker@sentinelflow",
                    idempotency_key=f"dispatch:{workflow_id}:start",
                )
                transitions += 1
                continue
            if workflow.status is WorkflowStatus.AWAITING_APPROVAL:
                blocked = await self._handle_approval(workflow)
                transitions += int(not blocked)
                if blocked:
                    return DispatchResult(workflow, transitions, blocked)
                continue
            if workflow.status in {WorkflowStatus.RUNNING, WorkflowStatus.COMPENSATING}:
                advanced, reason = await self._handle_adapter_step(workflow)
                transitions += int(advanced)
                if not advanced:
                    return DispatchResult(workflow, transitions, reason)
                continue
            return DispatchResult(workflow, transitions, workflow.status.value)
        workflow = await self._workflows.get(
            workspace_id=workspace_id,
            workflow_id=workflow_id,
        )
        return DispatchResult(workflow, transitions, "transition_limit")

    async def _handle_approval(self, workflow: WorkflowRun) -> str | None:
        step = self._active_step(workflow, WorkflowStepStatus.WAITING_APPROVAL)
        requests = await self._approvals.list(
            workspace_id=workflow.workspace_id,
            status=None,
            workflow_id=workflow.id,
            limit=10,
            offset=0,
        )
        approval = next((item for item in requests if item.step_key == step.step_key), None)
        if approval is None:
            now = self._clock()
            await self._approvals.create(
                workspace_id=workflow.workspace_id,
                incident_id=workflow.incident_id,
                workflow_id=workflow.id,
                step_key=step.step_key,
                action_summary=step.name,
                risk=step.risk,
                required_approvals=self._required_approvers(step.risk),
                eligible_roles=("soc_lead", "incident_commander"),
                expires_at=now + timedelta(minutes=30),
                actor_id="worker@sentinelflow",
                idempotency_key=f"dispatch:{workflow.id}:approval:{step.step_key}",
            )
            return "approval_pending"
        if approval.status is ApprovalStatus.PENDING:
            if self._clock() >= approval.expires_at:
                approval = await self._approvals.expire(
                    workspace_id=workflow.workspace_id,
                    approval_id=approval.id,
                    expected_version=approval.version,
                    actor_id="worker@sentinelflow",
                    idempotency_key=f"dispatch:{approval.id}:expire:{approval.round}",
                )
                if approval.status is ApprovalStatus.EXPIRED:
                    # Expiration is a terminal negative decision for the workflow.
                    pass
                else:
                    return "approval_pending"
            else:
                return "approval_pending"
        approved = approval.status is ApprovalStatus.APPROVED
        await self._workflows.record_approval(
            workspace_id=workflow.workspace_id,
            workflow_id=workflow.id,
            step_key=step.step_key,
            approved=approved,
            expected_version=workflow.version,
            actor_id="approval-engine@sentinelflow",
            idempotency_key=f"dispatch:{workflow.id}:approval-result:{approval.round}",
        )
        return None

    async def _handle_adapter_step(self, workflow: WorkflowRun) -> tuple[bool, str]:
        expected_status = (
            WorkflowStepStatus.COMPENSATING
            if workflow.status is WorkflowStatus.COMPENSATING
            else WorkflowStepStatus.RUNNING
        )
        step = self._active_step(workflow, expected_status)
        owner = str(uuid4())
        lease_key = f"workflow:{workflow.workspace_id}:{workflow.id}:{step.step_key}"
        if not await self._leases.acquire(lease_key, owner, self._lease_seconds):
            return False, "step_leased"
        try:
            if workflow.status is WorkflowStatus.COMPENSATING:
                return await self._execute_compensation(workflow, step)
            return await self._execute_step(workflow, step)
        finally:
            await self._leases.release(lease_key, owner)

    async def _execute_step(self, workflow: WorkflowRun, step: WorkflowStepRun) -> tuple[bool, str]:
        key = f"workflow:{workflow.id}:{step.step_key}:attempt:{step.attempt}"
        try:
            async with asyncio.timeout(step.timeout_seconds):
                output = await self._executor.execute(
                    workflow=workflow,
                    step=step,
                    idempotency_key=key,
                )
        except TimeoutError:
            error_code = "step_timeout"
            retryable = True
        except AdapterRequestError as error:
            error_code, retryable = self._classify_adapter_error(error)
        except Exception:
            error_code = "adapter_unexpected_error"
            retryable = False
        else:
            await self._workflows.record_step_result(
                workspace_id=workflow.workspace_id,
                workflow_id=workflow.id,
                step_key=step.step_key,
                succeeded=True,
                output=output,
                error_code=None,
                expected_version=workflow.version,
                actor_id="worker@sentinelflow",
                idempotency_key=f"{key}:success",
            )
            return True, "advanced"
        failed = await self._workflows.record_step_result(
            workspace_id=workflow.workspace_id,
            workflow_id=workflow.id,
            step_key=step.step_key,
            succeeded=False,
            output={},
            error_code=error_code,
            retryable=retryable,
            expected_version=workflow.version,
            actor_id="worker@sentinelflow",
            idempotency_key=f"{key}:failure:{error_code}",
        )
        if retryable and step.attempt < step.max_attempts:
            await self._workflows.retry_step(
                workspace_id=workflow.workspace_id,
                workflow_id=workflow.id,
                step_key=step.step_key,
                expected_version=failed.version,
                actor_id="worker@sentinelflow",
                idempotency_key=f"{key}:retry",
            )
            return True, "retrying"
        return True, "failed"

    async def _execute_compensation(
        self, workflow: WorkflowRun, step: WorkflowStepRun
    ) -> tuple[bool, str]:
        key = f"workflow:{workflow.id}:{step.step_key}:compensation"
        error_code: str | None
        try:
            async with asyncio.timeout(step.rollback_timeout_seconds):
                await self._executor.compensate(
                    workflow=workflow,
                    step=step,
                    idempotency_key=key,
                )
        except TimeoutError:
            succeeded, error_code = False, "compensation_timeout"
        except AdapterRequestError as error:
            error_code, _retryable = self._classify_adapter_error(error)
            succeeded = False
        except Exception:
            succeeded, error_code = False, "compensation_unexpected_error"
        else:
            succeeded, error_code = True, None
        await self._workflows.record_compensation(
            workspace_id=workflow.workspace_id,
            workflow_id=workflow.id,
            step_key=step.step_key,
            succeeded=succeeded,
            error_code=error_code,
            expected_version=workflow.version,
            actor_id="worker@sentinelflow",
            idempotency_key=f"{key}:{'success' if succeeded else error_code}",
        )
        return True, "compensated" if succeeded else "compensation_failed"

    @staticmethod
    def _active_step(workflow: WorkflowRun, status: WorkflowStepStatus) -> WorkflowStepRun:
        return next(step for step in workflow.steps if step.status is status)

    @staticmethod
    def _required_approvers(risk: PlaybookStepRisk) -> int:
        return 2 if risk in {PlaybookStepRisk.HIGH, PlaybookStepRisk.CRITICAL} else 1

    @staticmethod
    def _classify_adapter_error(error: AdapterRequestError) -> tuple[str, bool]:
        if isinstance(error, AdapterTimeoutError):
            return "adapter_timeout", True
        if isinstance(error, AdapterTransportError):
            return "adapter_transport", True
        if isinstance(error, AdapterHTTPError):
            status = error.response.status_code
            return f"adapter_http_{status}", status == 429 or status >= 500
        return "adapter_request_failed", False
