"""Incident aggregate, state transitions, and append-only timeline events."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

type EventData = dict[str, str | int | bool | None]


class IncidentStatus(StrEnum):
    """Explicit lifecycle states for an incident."""

    NEW = "new"
    TRIAGING = "triaging"
    INVESTIGATING = "investigating"
    AWAITING_APPROVAL = "awaiting_approval"
    RESPONDING = "responding"
    VALIDATING = "validating"
    RESOLVED = "resolved"
    CLOSED = "closed"
    REOPENED = "reopened"


class IncidentSeverity(StrEnum):
    """Operator-facing incident severity."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentEventType(StrEnum):
    """Timeline event types available in the incident milestone."""

    CREATED = "incident_created"
    STATUS_CHANGED = "status_changed"
    NOTE_ADDED = "note_added"


ALLOWED_TRANSITIONS: dict[IncidentStatus, frozenset[IncidentStatus]] = {
    IncidentStatus.NEW: frozenset({IncidentStatus.TRIAGING, IncidentStatus.CLOSED}),
    IncidentStatus.TRIAGING: frozenset(
        {IncidentStatus.INVESTIGATING, IncidentStatus.RESOLVED, IncidentStatus.CLOSED}
    ),
    IncidentStatus.INVESTIGATING: frozenset(
        {IncidentStatus.AWAITING_APPROVAL, IncidentStatus.RESOLVED, IncidentStatus.CLOSED}
    ),
    IncidentStatus.AWAITING_APPROVAL: frozenset(
        {IncidentStatus.INVESTIGATING, IncidentStatus.RESPONDING, IncidentStatus.CLOSED}
    ),
    IncidentStatus.RESPONDING: frozenset(
        {IncidentStatus.VALIDATING, IncidentStatus.AWAITING_APPROVAL}
    ),
    IncidentStatus.VALIDATING: frozenset({IncidentStatus.RESPONDING, IncidentStatus.RESOLVED}),
    IncidentStatus.RESOLVED: frozenset({IncidentStatus.CLOSED, IncidentStatus.REOPENED}),
    IncidentStatus.CLOSED: frozenset({IncidentStatus.REOPENED}),
    IncidentStatus.REOPENED: frozenset({IncidentStatus.TRIAGING}),
}


class IncidentError(Exception):
    """Base class for stable, safely reportable incident errors."""

    code = "incident_error"


class IncidentNotFound(IncidentError):
    """The incident does not exist in the caller's workspace."""

    code = "incident_not_found"

    def __init__(self) -> None:
        super().__init__("Incident was not found in this workspace")


class InvalidIncidentTransition(IncidentError):
    """The requested lifecycle edge is not permitted."""

    code = "invalid_incident_transition"

    def __init__(self, current: IncidentStatus, target: IncidentStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Cannot transition incident from {current.value} to {target.value}")


class VersionConflict(IncidentError):
    """The client attempted to mutate a stale aggregate version."""

    code = "incident_version_conflict"

    def __init__(self, expected: int, actual: int) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(f"Expected incident version {expected}, current version is {actual}")


class IdempotencyConflict(IncidentError):
    """An idempotency key was reused for a different operation."""

    code = "idempotency_conflict"

    def __init__(self) -> None:
        super().__init__("Idempotency key was already used for a different operation")


class ConcurrentIncidentWrite(IncidentError):
    """Persistence detected a write after another concurrent mutation."""

    code = "concurrent_incident_write"

    def __init__(self) -> None:
        super().__init__("Incident changed concurrently; reload it and retry")


@dataclass(slots=True)
class Incident:
    """Incident aggregate with optimistic versioning."""

    id: UUID
    workspace_id: UUID
    title: str
    description: str
    severity: IncidentSeverity
    status: IncidentStatus
    version: int
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None = None
    closed_at: datetime | None = None

    def transition(self, target: IncidentStatus, occurred_at: datetime) -> IncidentStatus:
        """Apply a valid state transition and return the previous state."""
        current = self.status
        if target not in ALLOWED_TRANSITIONS[current]:
            raise InvalidIncidentTransition(current, target)

        self.status = target
        self.version += 1
        self.updated_at = occurred_at
        if target is IncidentStatus.RESOLVED:
            self.resolved_at = occurred_at
        elif target is IncidentStatus.CLOSED:
            self.closed_at = occurred_at
        elif target is IncidentStatus.REOPENED:
            self.resolved_at = None
            self.closed_at = None
        return current

    def record_timeline_entry(self, occurred_at: datetime) -> int:
        """Advance the aggregate version for a non-transition timeline mutation."""
        self.version += 1
        self.updated_at = occurred_at
        return self.version


@dataclass(frozen=True, slots=True)
class IncidentEvent:
    """Immutable entry in an incident timeline."""

    id: UUID
    workspace_id: UUID
    incident_id: UUID
    sequence: int
    event_type: IncidentEventType
    actor_id: str
    idempotency_key: str
    data: EventData
    occurred_at: datetime
