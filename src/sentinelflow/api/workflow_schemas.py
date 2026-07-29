"""HTTP schemas for auditable workflow execution."""

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field

from sentinelflow.domain import (
    PlaybookStepKind,
    PlaybookStepRisk,
    RollbackStrategy,
    WorkflowEvent,
    WorkflowEventType,
    WorkflowRun,
    WorkflowStatus,
    WorkflowStepRun,
    WorkflowStepStatus,
)
from sentinelflow.domain.playbook import JsonObject


class CreateWorkflowRequest(BaseModel):
    incident_id: UUID
    playbook_id: UUID
    playbook_version: int = Field(ge=1)


class WorkflowMutationRequest(BaseModel):
    expected_version: int = Field(ge=1)


class WorkflowStepResultRequest(WorkflowMutationRequest):
    succeeded: bool
    output: JsonObject = Field(default_factory=dict)
    error_code: str | None = Field(default=None, max_length=100)
    retryable: bool = False


class WorkflowCompensationRequest(WorkflowMutationRequest):
    succeeded: bool
    error_code: str | None = Field(default=None, max_length=100)


class WorkflowStepResponse(BaseModel):
    id: UUID
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
    parameters: JsonObject
    continue_on_failure: bool
    condition: JsonObject | None
    rollback_parameters: JsonObject
    rollback_timeout_seconds: int
    status: WorkflowStepStatus
    attempt: int
    output: JsonObject
    last_error_code: str | None
    started_at: datetime | None
    finished_at: datetime | None

    @classmethod
    def from_domain(cls, step: WorkflowStepRun) -> Self:
        return cls(
            id=step.id,
            position=step.position,
            step_key=step.step_key,
            name=step.name,
            kind=step.kind,
            risk=step.risk,
            adapter=step.adapter,
            operation=step.operation,
            timeout_seconds=step.timeout_seconds,
            max_attempts=step.max_attempts,
            rollback_strategy=step.rollback_strategy,
            rollback_operation=step.rollback_operation,
            parameters=step.parameters,
            continue_on_failure=step.continue_on_failure,
            condition=(
                {
                    "field": step.condition.field,
                    "operator": step.condition.operator.value,
                    "value": step.condition.value,
                }
                if step.condition is not None
                else None
            ),
            rollback_parameters=step.rollback_parameters,
            rollback_timeout_seconds=step.rollback_timeout_seconds,
            status=step.status,
            attempt=step.attempt,
            output=step.output,
            last_error_code=step.last_error_code,
            started_at=step.started_at,
            finished_at=step.finished_at,
        )


class WorkflowResponse(BaseModel):
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
    started_at: datetime | None
    finished_at: datetime | None
    cancel_requested: bool
    steps: list[WorkflowStepResponse]

    @classmethod
    def from_domain(cls, workflow: WorkflowRun) -> Self:
        return cls(
            id=workflow.id,
            workspace_id=workflow.workspace_id,
            incident_id=workflow.incident_id,
            playbook_id=workflow.playbook_id,
            playbook_version_id=workflow.playbook_version_id,
            playbook_version=workflow.playbook_version,
            definition_hash=workflow.definition_hash,
            status=workflow.status,
            version=workflow.version,
            created_by=workflow.created_by,
            created_at=workflow.created_at,
            updated_at=workflow.updated_at,
            started_at=workflow.started_at,
            finished_at=workflow.finished_at,
            cancel_requested=workflow.cancel_requested,
            steps=[WorkflowStepResponse.from_domain(step) for step in workflow.steps],
        )


class WorkflowEventResponse(BaseModel):
    id: UUID
    workflow_id: UUID
    sequence: int
    event_type: WorkflowEventType
    actor_id: str
    data: JsonObject
    occurred_at: datetime

    @classmethod
    def from_domain(cls, event: WorkflowEvent) -> Self:
        return cls(
            id=event.id,
            workflow_id=event.workflow_id,
            sequence=event.sequence,
            event_type=event.event_type,
            actor_id=event.actor_id,
            data=event.data,
            occurred_at=event.occurred_at,
        )
