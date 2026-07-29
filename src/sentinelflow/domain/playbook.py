"""Versioned response playbooks and security-focused definition validation."""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from uuid import UUID

type JsonPrimitive = str | int | float | bool | None
type JsonValue = JsonPrimitive | list[JsonValue] | dict[str, JsonValue]
type JsonObject = dict[str, JsonValue]

STEP_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
REFERENCE_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,99}$")


class PlaybookStatus(StrEnum):
    """Lifecycle of the playbook aggregate, independent from immutable revisions."""

    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class PlaybookStepKind(StrEnum):
    """Supported workflow step boundaries."""

    ENRICHMENT = "enrichment"
    APPROVAL = "approval"
    ACTION = "action"
    VALIDATION = "validation"
    NOTIFICATION = "notification"


class PlaybookStepRisk(StrEnum):
    """Risk used to determine mandatory human and rollback controls."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConditionOperator(StrEnum):
    """Small, declarative condition language without executable expressions."""

    EQUALS = "equals"
    NOT_EQUALS = "not_equals"
    CONTAINS = "contains"
    EXISTS = "exists"
    IN = "in"


class RollbackStrategy(StrEnum):
    """Explicit recovery strategies allowed for response actions."""

    COMPENSATE = "compensate"
    RESTORE = "restore"


class PlaybookEventType(StrEnum):
    """Append-only changes to a playbook aggregate."""

    CREATED = "playbook_created"
    VERSION_CREATED = "playbook_version_created"
    PUBLISHED = "playbook_published"
    ARCHIVED = "playbook_archived"


class PlaybookError(Exception):
    """Base class for safely reportable playbook errors."""

    code = "playbook_error"


class PlaybookNotFound(PlaybookError):
    """The playbook does not exist in the caller's workspace."""

    code = "playbook_not_found"

    def __init__(self) -> None:
        super().__init__("Playbook was not found in this workspace")


class PlaybookVersionNotFound(PlaybookError):
    """The requested immutable revision does not exist."""

    code = "playbook_version_not_found"

    def __init__(self) -> None:
        super().__init__("Playbook version was not found in this workspace")


class InvalidPlaybookDefinition(PlaybookError):
    """The proposed definition violates a stable domain invariant."""

    code = "invalid_playbook_definition"


class PlaybookVersionConflict(PlaybookError):
    """The caller attempted to update a stale aggregate."""

    code = "playbook_version_conflict"

    def __init__(self, expected: int, actual: int) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(f"Expected playbook version {expected}, current version is {actual}")


class PlaybookArchived(PlaybookError):
    """Archived playbooks cannot receive new revisions or be published."""

    code = "playbook_archived"

    def __init__(self) -> None:
        super().__init__("Archived playbooks cannot be changed")


class PlaybookIdempotencyConflict(PlaybookError):
    """An idempotency key was reused for another playbook operation."""

    code = "playbook_idempotency_conflict"

    def __init__(self) -> None:
        super().__init__("Idempotency key was already used for a different playbook operation")


class ConcurrentPlaybookWrite(PlaybookError):
    """Persistence rejected a stale or conflicting playbook write."""

    code = "concurrent_playbook_write"

    def __init__(self) -> None:
        super().__init__("Playbook changed concurrently; reload it and retry")


@dataclass(frozen=True, slots=True)
class StepCondition:
    """Declarative condition evaluated by a future workflow engine."""

    field: str
    operator: ConditionOperator
    value: JsonValue = None

    def __post_init__(self) -> None:
        if not REFERENCE_PATTERN.fullmatch(self.field) or "__" in self.field:
            raise InvalidPlaybookDefinition("Condition field must be a safe dotted reference")
        if self.operator is ConditionOperator.EXISTS and self.value is not None:
            raise InvalidPlaybookDefinition("The exists condition cannot include a value")
        if self.operator is ConditionOperator.IN and not isinstance(self.value, list):
            raise InvalidPlaybookDefinition("The in condition requires a list value")


@dataclass(frozen=True, slots=True)
class RollbackDefinition:
    """Compensation executed only through an adapter operation."""

    strategy: RollbackStrategy
    operation: str
    parameters: JsonObject
    timeout_seconds: int = 300

    def __post_init__(self) -> None:
        if not REFERENCE_PATTERN.fullmatch(self.operation):
            raise InvalidPlaybookDefinition("Rollback operation must be a safe operation reference")
        if not 1 <= self.timeout_seconds <= 3600:
            raise InvalidPlaybookDefinition("Rollback timeout must be between 1 and 3600 seconds")


@dataclass(frozen=True, slots=True)
class PlaybookStep:
    """One typed and non-executable playbook step."""

    key: str
    name: str
    kind: PlaybookStepKind
    risk: PlaybookStepRisk
    adapter: str | None
    operation: str | None
    parameters: JsonObject
    timeout_seconds: int = 300
    continue_on_failure: bool = False
    condition: StepCondition | None = None
    rollback: RollbackDefinition | None = None

    def __post_init__(self) -> None:
        if not STEP_KEY_PATTERN.fullmatch(self.key):
            raise InvalidPlaybookDefinition(
                "Step key must start with a letter and contain only lowercase letters, digits, or _"
            )
        if not self.name.strip():
            raise InvalidPlaybookDefinition("Step name must not be blank")
        if not 1 <= self.timeout_seconds <= 3600:
            raise InvalidPlaybookDefinition("Step timeout must be between 1 and 3600 seconds")

        if self.kind is PlaybookStepKind.APPROVAL:
            if self.adapter is not None or self.operation is not None:
                raise InvalidPlaybookDefinition("Approval steps cannot call an adapter operation")
            if self.rollback is not None:
                raise InvalidPlaybookDefinition("Approval steps cannot define rollback")
            if self.condition is not None:
                raise InvalidPlaybookDefinition("Approval guard steps cannot be conditional")
            return

        if self.adapter is None or not REFERENCE_PATTERN.fullmatch(self.adapter):
            raise InvalidPlaybookDefinition("Executable steps require a safe adapter reference")
        if self.operation is None or not REFERENCE_PATTERN.fullmatch(self.operation):
            raise InvalidPlaybookDefinition("Executable steps require a safe operation reference")
        if self.rollback is not None and self.kind is not PlaybookStepKind.ACTION:
            raise InvalidPlaybookDefinition("Only action steps can define rollback")


@dataclass(slots=True)
class Playbook:
    """Workspace-scoped playbook aggregate with immutable definitions."""

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
    archived_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise InvalidPlaybookDefinition("Playbook name must not be blank")
        if self.latest_version < 1 or self.version < 1:
            raise InvalidPlaybookDefinition("Playbook versions must be positive")
        if self.active_version is not None and not 1 <= self.active_version <= self.latest_version:
            raise InvalidPlaybookDefinition("Active revision must reference an existing version")
        if self.status is PlaybookStatus.ACTIVE and self.active_version is None:
            raise InvalidPlaybookDefinition("Active playbooks require an active revision")

    def create_revision(self, occurred_at: datetime, expected_version: int) -> tuple[int, int]:
        """Allocate the next immutable revision and return prior/new row versions."""
        self._assert_mutable(expected_version)
        previous_version = self.version
        self.latest_version += 1
        self.version += 1
        self.updated_at = occurred_at
        return previous_version, self.latest_version

    def publish(self, revision: int, occurred_at: datetime, expected_version: int) -> int:
        """Select one existing immutable revision as active."""
        self._assert_mutable(expected_version)
        if revision < 1 or revision > self.latest_version:
            raise PlaybookVersionNotFound
        previous_version = self.version
        self.active_version = revision
        self.status = PlaybookStatus.ACTIVE
        self.version += 1
        self.updated_at = occurred_at
        return previous_version

    def archive(self, occurred_at: datetime, expected_version: int) -> int:
        """Make the aggregate permanently read-only."""
        self._assert_mutable(expected_version)
        previous_version = self.version
        self.status = PlaybookStatus.ARCHIVED
        self.version += 1
        self.updated_at = occurred_at
        self.archived_at = occurred_at
        return previous_version

    def _assert_mutable(self, expected_version: int) -> None:
        if self.status is PlaybookStatus.ARCHIVED:
            raise PlaybookArchived
        if self.version != expected_version:
            raise PlaybookVersionConflict(expected_version, self.version)


@dataclass(frozen=True, slots=True)
class PlaybookVersion:
    """Content-addressed immutable playbook revision."""

    id: UUID
    workspace_id: UUID
    playbook_id: UUID
    number: int
    steps: tuple[PlaybookStep, ...]
    definition_hash: str
    created_by: str
    created_at: datetime

    @classmethod
    def build(
        cls,
        *,
        id: UUID,
        workspace_id: UUID,
        playbook_id: UUID,
        number: int,
        steps: tuple[PlaybookStep, ...],
        created_by: str,
        created_at: datetime,
    ) -> "PlaybookVersion":
        """Validate and hash a revision before it crosses the persistence boundary."""
        if number < 1:
            raise InvalidPlaybookDefinition("Playbook revision number must be positive")
        if not created_by.strip():
            raise InvalidPlaybookDefinition("Playbook revision author must not be blank")
        validate_steps(steps)
        encoded = json.dumps(
            [step_to_dict(step) for step in steps],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode()
        return cls(
            id=id,
            workspace_id=workspace_id,
            playbook_id=playbook_id,
            number=number,
            steps=steps,
            definition_hash=sha256(encoded).hexdigest(),
            created_by=created_by,
            created_at=created_at,
        )


@dataclass(frozen=True, slots=True)
class PlaybookEvent:
    """Immutable playbook audit event and idempotency record."""

    id: UUID
    workspace_id: UUID
    playbook_id: UUID
    sequence: int
    event_type: PlaybookEventType
    actor_id: str
    idempotency_key: str
    data: JsonObject
    occurred_at: datetime


def validate_steps(steps: tuple[PlaybookStep, ...]) -> None:
    """Enforce ordering and recovery invariants for a whole definition."""
    if not 1 <= len(steps) <= 50:
        raise InvalidPlaybookDefinition("A playbook must contain between 1 and 50 steps")
    keys = [step.key for step in steps]
    if len(set(keys)) != len(keys):
        raise InvalidPlaybookDefinition("Playbook step keys must be unique")

    approval_seen = False
    for step in steps:
        if step.kind is PlaybookStepKind.APPROVAL:
            approval_seen = True
            continue
        if step.kind is not PlaybookStepKind.ACTION:
            continue
        if step.risk in {PlaybookStepRisk.HIGH, PlaybookStepRisk.CRITICAL}:
            if not approval_seen:
                raise InvalidPlaybookDefinition(
                    "High-risk and critical actions require an earlier approval step"
                )
            if step.rollback is None:
                raise InvalidPlaybookDefinition(
                    "High-risk and critical actions require an explicit rollback definition"
                )


def step_to_dict(step: PlaybookStep) -> JsonObject:
    """Return a stable JSON representation used for hashing and persistence."""
    condition: JsonValue = None
    if step.condition is not None:
        condition = {
            "field": step.condition.field,
            "operator": step.condition.operator.value,
            "value": step.condition.value,
        }
    rollback: JsonValue = None
    if step.rollback is not None:
        rollback = {
            "strategy": step.rollback.strategy.value,
            "operation": step.rollback.operation,
            "parameters": step.rollback.parameters,
            "timeout_seconds": step.rollback.timeout_seconds,
        }
    return {
        "key": step.key,
        "name": step.name,
        "kind": step.kind.value,
        "risk": step.risk.value,
        "adapter": step.adapter,
        "operation": step.operation,
        "parameters": step.parameters,
        "timeout_seconds": step.timeout_seconds,
        "continue_on_failure": step.continue_on_failure,
        "condition": condition,
        "rollback": rollback,
    }


def step_from_dict(data: JsonObject) -> PlaybookStep:
    """Hydrate a validated step from trusted persistence data."""
    raw_condition = data.get("condition")
    condition = None
    if isinstance(raw_condition, dict):
        condition = StepCondition(
            field=str(raw_condition["field"]),
            operator=ConditionOperator(str(raw_condition["operator"])),
            value=raw_condition.get("value"),
        )
    raw_rollback = data.get("rollback")
    rollback = None
    if isinstance(raw_rollback, dict):
        raw_parameters = raw_rollback.get("parameters", {})
        rollback = RollbackDefinition(
            strategy=RollbackStrategy(str(raw_rollback["strategy"])),
            operation=str(raw_rollback["operation"]),
            parameters=dict(raw_parameters) if isinstance(raw_parameters, dict) else {},
            timeout_seconds=int(str(raw_rollback.get("timeout_seconds", 300))),
        )
    raw_parameters = data.get("parameters", {})
    return PlaybookStep(
        key=str(data["key"]),
        name=str(data["name"]),
        kind=PlaybookStepKind(str(data["kind"])),
        risk=PlaybookStepRisk(str(data["risk"])),
        adapter=str(data["adapter"]) if data.get("adapter") is not None else None,
        operation=str(data["operation"]) if data.get("operation") is not None else None,
        parameters=dict(raw_parameters) if isinstance(raw_parameters, dict) else {},
        timeout_seconds=int(str(data.get("timeout_seconds", 300))),
        continue_on_failure=bool(data.get("continue_on_failure", False)),
        condition=condition,
        rollback=rollback,
    )
