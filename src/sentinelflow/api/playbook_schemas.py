"""HTTP schemas for versioned response playbooks."""

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from sentinelflow.domain import (
    ConditionOperator,
    Playbook,
    PlaybookEvent,
    PlaybookEventType,
    PlaybookStatus,
    PlaybookStep,
    PlaybookStepKind,
    PlaybookStepRisk,
    PlaybookVersion,
    RollbackDefinition,
    RollbackStrategy,
    StepCondition,
)
from sentinelflow.domain.playbook import JsonObject, JsonValue, step_to_dict


class StepConditionInput(BaseModel):
    """Declarative, non-executable step condition."""

    field: str = Field(min_length=1, max_length=100)
    operator: ConditionOperator
    value: JsonValue = None

    def to_domain(self) -> StepCondition:
        return StepCondition(field=self.field, operator=self.operator, value=self.value)


class RollbackDefinitionInput(BaseModel):
    """Explicit compensation for a response action."""

    strategy: RollbackStrategy
    operation: str = Field(min_length=1, max_length=100)
    parameters: JsonObject = Field(default_factory=dict)
    timeout_seconds: int = Field(default=300, ge=1, le=3600)

    def to_domain(self) -> RollbackDefinition:
        return RollbackDefinition(
            strategy=self.strategy,
            operation=self.operation,
            parameters=self.parameters,
            timeout_seconds=self.timeout_seconds,
        )


class PlaybookStepInput(BaseModel):
    """Typed step accepted in an immutable revision."""

    key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=200)
    kind: PlaybookStepKind
    risk: PlaybookStepRisk = PlaybookStepRisk.LOW
    adapter: str | None = Field(default=None, max_length=100)
    operation: str | None = Field(default=None, max_length=100)
    parameters: JsonObject = Field(default_factory=dict)
    timeout_seconds: int = Field(default=300, ge=1, le=3600)
    continue_on_failure: bool = False
    condition: StepConditionInput | None = None
    rollback: RollbackDefinitionInput | None = None

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("step name must not be blank")
        return value

    def to_domain(self) -> PlaybookStep:
        return PlaybookStep(
            key=self.key,
            name=self.name,
            kind=self.kind,
            risk=self.risk,
            adapter=self.adapter,
            operation=self.operation,
            parameters=self.parameters,
            timeout_seconds=self.timeout_seconds,
            continue_on_failure=self.continue_on_failure,
            condition=self.condition.to_domain() if self.condition is not None else None,
            rollback=self.rollback.to_domain() if self.rollback is not None else None,
        )


class CreatePlaybookRequest(BaseModel):
    """Create a playbook and revision one."""

    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    steps: list[PlaybookStepInput] = Field(min_length=1, max_length=50)

    @field_validator("name")
    @classmethod
    def name_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("playbook name must not be blank")
        return value

    def domain_steps(self) -> tuple[PlaybookStep, ...]:
        return tuple(step.to_domain() for step in self.steps)


class CreatePlaybookVersionRequest(BaseModel):
    """Append a revision after an optimistic concurrency check."""

    expected_version: int = Field(ge=1)
    steps: list[PlaybookStepInput] = Field(min_length=1, max_length=50)

    def domain_steps(self) -> tuple[PlaybookStep, ...]:
        return tuple(step.to_domain() for step in self.steps)


class PlaybookMutationRequest(BaseModel):
    """Expected row version for publish and archive commands."""

    expected_version: int = Field(ge=1)


class PlaybookResponse(BaseModel):
    """Public playbook identity and revision pointers."""

    id: UUID
    workspace_id: UUID
    name: str
    description: str
    status: PlaybookStatus
    latest_version: int
    active_version: int | None
    version: int
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None

    @classmethod
    def from_domain(cls, playbook: Playbook) -> Self:
        return cls(
            id=playbook.id,
            workspace_id=playbook.workspace_id,
            name=playbook.name,
            description=playbook.description,
            status=playbook.status,
            latest_version=playbook.latest_version,
            active_version=playbook.active_version,
            version=playbook.version,
            created_at=playbook.created_at,
            updated_at=playbook.updated_at,
            archived_at=playbook.archived_at,
        )


class PlaybookStepResponse(PlaybookStepInput):
    """Stable serialized playbook step."""

    @classmethod
    def from_domain(cls, step: PlaybookStep) -> Self:
        return cls.model_validate(step_to_dict(step))


class PlaybookVersionResponse(BaseModel):
    """Public immutable revision including its content hash."""

    id: UUID
    workspace_id: UUID
    playbook_id: UUID
    number: int
    steps: list[PlaybookStepResponse]
    definition_hash: str
    created_by: str
    created_at: datetime

    @classmethod
    def from_domain(cls, version: PlaybookVersion) -> Self:
        return cls(
            id=version.id,
            workspace_id=version.workspace_id,
            playbook_id=version.playbook_id,
            number=version.number,
            steps=[PlaybookStepResponse.from_domain(step) for step in version.steps],
            definition_hash=version.definition_hash,
            created_by=version.created_by,
            created_at=version.created_at,
        )


class PlaybookDetailResponse(BaseModel):
    """Combined command response for identity and created revision."""

    playbook: PlaybookResponse
    revision: PlaybookVersionResponse


class PlaybookEventResponse(BaseModel):
    """Public append-only playbook audit entry."""

    id: UUID
    playbook_id: UUID
    sequence: int
    event_type: PlaybookEventType
    actor_id: str
    data: JsonObject
    occurred_at: datetime

    @classmethod
    def from_domain(cls, event: PlaybookEvent) -> Self:
        return cls(
            id=event.id,
            playbook_id=event.playbook_id,
            sequence=event.sequence,
            event_type=event.event_type,
            actor_id=event.actor_id,
            data=event.data,
            occurred_at=event.occurred_at,
        )
