"""Auditable workflow execution state machine over immutable playbook revisions."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sentinelflow.domain.playbook import (
    JsonObject,
    PlaybookStepKind,
    PlaybookStepRisk,
    RollbackStrategy,
)


class WorkflowStatus(StrEnum):
    """Explicit lifecycle for one workflow run."""

    PENDING = "pending"
    RUNNING = "running"
    AWAITING_APPROVAL = "awaiting_approval"
    COMPENSATING = "compensating"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowStepStatus(StrEnum):
    """Execution state for one snapshotted step."""

    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"


class WorkflowEventType(StrEnum):
    """Append-only workflow decisions and execution outcomes."""

    CREATED = "workflow_created"
    STARTED = "workflow_started"
    STEP_SUCCEEDED = "workflow_step_succeeded"
    STEP_FAILED = "workflow_step_failed"
    STEP_RETRIED = "workflow_step_retried"
    APPROVAL_RECORDED = "workflow_approval_recorded"
    CANCEL_REQUESTED = "workflow_cancel_requested"
    COMPENSATION_RECORDED = "workflow_compensation_recorded"
    TIMED_OUT = "workflow_step_timed_out"


class WorkflowError(Exception):
    """Base class for stable workflow failures."""

    code = "workflow_error"


class WorkflowNotFound(WorkflowError):
    code = "workflow_not_found"

    def __init__(self) -> None:
        super().__init__("Workflow was not found in this workspace")


class WorkflowDependencyNotFound(WorkflowError):
    code = "workflow_dependency_not_found"

    def __init__(self) -> None:
        super().__init__("Incident or playbook revision was not found in this workspace")


class InvalidWorkflowTransition(WorkflowError):
    code = "invalid_workflow_transition"


class WorkflowVersionConflict(WorkflowError):
    code = "workflow_version_conflict"

    def __init__(self, expected: int, actual: int) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(f"Expected workflow version {expected}, current version is {actual}")


class WorkflowIdempotencyConflict(WorkflowError):
    code = "workflow_idempotency_conflict"

    def __init__(self) -> None:
        super().__init__("Idempotency key was already used for a different workflow operation")


class ConcurrentWorkflowWrite(WorkflowError):
    code = "concurrent_workflow_write"

    def __init__(self) -> None:
        super().__init__("Workflow changed concurrently; reload it and retry")


@dataclass(slots=True)
class WorkflowStepRun:
    """One execution record snapshotted from a playbook step."""

    id: UUID
    workspace_id: UUID
    workflow_id: UUID
    position: int
    step_key: str
    name: str
    kind: PlaybookStepKind
    risk: PlaybookStepRisk
    adapter: str | None
    operation: str | None
    timeout_seconds: int
    max_attempts: int
    rollback_strategy: RollbackStrategy | None
    rollback_operation: str | None
    status: WorkflowStepStatus = WorkflowStepStatus.PENDING
    attempt: int = 0
    output: JsonObject = field(default_factory=dict)
    last_error_code: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def start(self, occurred_at: datetime) -> None:
        if self.status not in {WorkflowStepStatus.PENDING, WorkflowStepStatus.FAILED}:
            raise InvalidWorkflowTransition("Only pending or failed steps can start")
        if self.attempt >= self.max_attempts:
            raise InvalidWorkflowTransition("Workflow step retry budget is exhausted")
        self.status = WorkflowStepStatus.RUNNING
        self.attempt += 1
        self.started_at = occurred_at
        self.finished_at = None
        self.last_error_code = None


@dataclass(slots=True)
class WorkflowRun:
    """Aggregate controlling one sequential playbook execution."""

    id: UUID
    workspace_id: UUID
    incident_id: UUID
    playbook_id: UUID
    playbook_version_id: UUID
    playbook_version: int
    definition_hash: str
    status: WorkflowStatus
    version: int
    created_by: str
    created_at: datetime
    updated_at: datetime
    steps: list[WorkflowStepRun]
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancel_requested: bool = False

    def __post_init__(self) -> None:
        positions = [step.position for step in self.steps]
        if not self.steps or positions != list(range(len(self.steps))):
            raise InvalidWorkflowTransition("Workflow steps must have contiguous positions")
        if any(step.workflow_id != self.id for step in self.steps):
            raise InvalidWorkflowTransition("Workflow steps must belong to their aggregate")

    def start(self, occurred_at: datetime, expected_version: int) -> None:
        """Start a pending run and activate its first step."""
        self._expect_version(expected_version)
        if self.status is not WorkflowStatus.PENDING:
            raise InvalidWorkflowTransition("Only pending workflows can start")
        self.status = WorkflowStatus.RUNNING
        self.started_at = occurred_at
        self._activate_next(occurred_at)
        self._advance_version(occurred_at)

    def record_step_result(
        self,
        *,
        step_key: str,
        succeeded: bool,
        output: JsonObject,
        error_code: str | None,
        occurred_at: datetime,
        expected_version: int,
    ) -> None:
        """Record the current adapter step result and choose the next boundary."""
        self._expect_version(expected_version)
        if self.status is not WorkflowStatus.RUNNING:
            raise InvalidWorkflowTransition("Workflow is not executing a step")
        step = self._step(step_key)
        if step.status is not WorkflowStepStatus.RUNNING:
            raise InvalidWorkflowTransition("Only the running step can record a result")
        step.output = output
        step.finished_at = occurred_at
        if succeeded:
            step.status = WorkflowStepStatus.SUCCEEDED
            self._activate_next(occurred_at)
        else:
            step.status = WorkflowStepStatus.FAILED
            step.last_error_code = error_code or "step_failed"
            self.status = WorkflowStatus.FAILED
            self.finished_at = occurred_at
            if step.attempt >= step.max_attempts:
                self._begin_compensation(occurred_at)
        self._advance_version(occurred_at)

    def retry_step(self, *, step_key: str, occurred_at: datetime, expected_version: int) -> None:
        """Retry a failed step while its bounded budget remains."""
        self._expect_version(expected_version)
        if self.status is not WorkflowStatus.FAILED:
            raise InvalidWorkflowTransition("Only failed workflows can retry")
        step = self._step(step_key)
        if step.status is not WorkflowStepStatus.FAILED:
            raise InvalidWorkflowTransition("Only a failed step can retry")
        step.start(occurred_at)
        self.status = WorkflowStatus.RUNNING
        self.finished_at = None
        self._advance_version(occurred_at)

    def record_approval(
        self,
        *,
        step_key: str,
        approved: bool,
        occurred_at: datetime,
        expected_version: int,
    ) -> None:
        """Resume or reject the workflow at a human decision boundary."""
        self._expect_version(expected_version)
        if self.status is not WorkflowStatus.AWAITING_APPROVAL:
            raise InvalidWorkflowTransition("Workflow is not awaiting approval")
        step = self._step(step_key)
        if step.status is not WorkflowStepStatus.WAITING_APPROVAL:
            raise InvalidWorkflowTransition("Approval step is not waiting")
        step.finished_at = occurred_at
        if approved:
            step.status = WorkflowStepStatus.SUCCEEDED
            self.status = WorkflowStatus.RUNNING
            self._activate_next(occurred_at)
        else:
            step.status = WorkflowStepStatus.FAILED
            step.last_error_code = "approval_rejected"
            self.status = WorkflowStatus.FAILED
            self.finished_at = occurred_at
            self._begin_compensation(occurred_at)
        self._advance_version(occurred_at)

    def request_cancel(self, occurred_at: datetime, expected_version: int) -> None:
        """Cancel before execution or compensate already-applied actions."""
        self._expect_version(expected_version)
        if self.status in {
            WorkflowStatus.SUCCEEDED,
            WorkflowStatus.CANCELLED,
            WorkflowStatus.COMPENSATING,
        }:
            raise InvalidWorkflowTransition("Workflow cannot be cancelled in its current state")
        self.cancel_requested = True
        for step in self.steps:
            if step.status in {
                WorkflowStepStatus.PENDING,
                WorkflowStepStatus.RUNNING,
                WorkflowStepStatus.WAITING_APPROVAL,
            }:
                step.status = WorkflowStepStatus.SKIPPED
                step.finished_at = occurred_at
        self._begin_compensation(occurred_at)
        if self.status is not WorkflowStatus.COMPENSATING:
            self.status = WorkflowStatus.CANCELLED
            self.finished_at = occurred_at
        self._advance_version(occurred_at)

    def record_compensation(
        self,
        *,
        step_key: str,
        succeeded: bool,
        error_code: str | None,
        occurred_at: datetime,
        expected_version: int,
    ) -> None:
        """Record one rollback result and continue in reverse order."""
        self._expect_version(expected_version)
        if self.status is not WorkflowStatus.COMPENSATING:
            raise InvalidWorkflowTransition("Workflow is not compensating")
        step = self._step(step_key)
        if step.status is not WorkflowStepStatus.COMPENSATING:
            raise InvalidWorkflowTransition("Step is not the active compensation")
        step.finished_at = occurred_at
        if not succeeded:
            step.status = WorkflowStepStatus.FAILED
            step.last_error_code = error_code or "compensation_failed"
            self.status = WorkflowStatus.FAILED
            self.finished_at = occurred_at
        else:
            step.status = WorkflowStepStatus.COMPENSATED
            if not self._activate_compensation(occurred_at):
                self.status = (
                    WorkflowStatus.CANCELLED if self.cancel_requested else WorkflowStatus.FAILED
                )
                self.finished_at = occurred_at
        self._advance_version(occurred_at)

    def timeout_current(self, occurred_at: datetime, expected_version: int) -> str:
        """Fail the active adapter step with a stable timeout error."""
        self._expect_version(expected_version)
        if self.status is not WorkflowStatus.RUNNING:
            raise InvalidWorkflowTransition("Workflow has no running step to time out")
        step = next(
            (
                candidate
                for candidate in self.steps
                if candidate.status is WorkflowStepStatus.RUNNING
            ),
            None,
        )
        if step is None:
            raise InvalidWorkflowTransition("Workflow has no running step to time out")
        self.record_step_result(
            step_key=step.step_key,
            succeeded=False,
            output={},
            error_code="step_timeout",
            occurred_at=occurred_at,
            expected_version=expected_version,
        )
        return step.step_key

    def _activate_next(self, occurred_at: datetime) -> None:
        next_step = next(
            (
                step
                for step in sorted(self.steps, key=lambda candidate: candidate.position)
                if step.status is WorkflowStepStatus.PENDING
            ),
            None,
        )
        if next_step is None:
            self.status = WorkflowStatus.SUCCEEDED
            self.finished_at = occurred_at
            return
        if next_step.kind is PlaybookStepKind.APPROVAL:
            next_step.status = WorkflowStepStatus.WAITING_APPROVAL
            next_step.started_at = occurred_at
            self.status = WorkflowStatus.AWAITING_APPROVAL
            return
        next_step.start(occurred_at)
        self.status = WorkflowStatus.RUNNING

    def _begin_compensation(self, occurred_at: datetime) -> None:
        if self._activate_compensation(occurred_at):
            self.status = WorkflowStatus.COMPENSATING

    def _activate_compensation(self, occurred_at: datetime) -> bool:
        candidate = next(
            (
                step
                for step in sorted(self.steps, key=lambda item: item.position, reverse=True)
                if step.status is WorkflowStepStatus.SUCCEEDED
                and step.kind is PlaybookStepKind.ACTION
                and step.rollback_operation is not None
            ),
            None,
        )
        if candidate is None:
            return False
        candidate.status = WorkflowStepStatus.COMPENSATING
        candidate.started_at = occurred_at
        candidate.finished_at = None
        return True

    def _step(self, step_key: str) -> WorkflowStepRun:
        step = next((candidate for candidate in self.steps if candidate.step_key == step_key), None)
        if step is None:
            raise InvalidWorkflowTransition("Workflow step does not exist")
        return step

    def _expect_version(self, expected_version: int) -> None:
        if self.version != expected_version:
            raise WorkflowVersionConflict(expected_version, self.version)

    def _advance_version(self, occurred_at: datetime) -> None:
        self.version += 1
        self.updated_at = occurred_at


@dataclass(frozen=True, slots=True)
class WorkflowEvent:
    """Immutable workflow command and result event."""

    id: UUID
    workspace_id: UUID
    workflow_id: UUID
    sequence: int
    event_type: WorkflowEventType
    actor_id: str
    idempotency_key: str
    data: JsonObject
    occurred_at: datetime
