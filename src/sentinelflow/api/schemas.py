"""HTTP request and response schemas for incidents and timeline events."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from sentinelflow.domain import (
    Incident,
    IncidentEvent,
    IncidentEventType,
    IncidentSeverity,
    IncidentStatus,
)
from sentinelflow.domain.incident import EventData


class CreateIncidentRequest(BaseModel):
    """Input accepted when an operator creates an incident."""

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    severity: IncidentSeverity

    @field_validator("title")
    @classmethod
    def title_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be blank")
        return value


class TransitionIncidentRequest(BaseModel):
    """Explicit state transition with optimistic concurrency."""

    target_status: IncidentStatus
    reason: str = Field(min_length=1, max_length=2000)
    expected_version: int = Field(ge=1)

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("reason must not be blank")
        return value


class AddIncidentNoteRequest(BaseModel):
    """Append-only operator note."""

    body: str = Field(min_length=1, max_length=8000)
    expected_version: int = Field(ge=1)

    @field_validator("body")
    @classmethod
    def body_must_not_be_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("body must not be blank")
        return value


class IncidentResponse(BaseModel):
    """Public incident representation."""

    id: UUID
    workspace_id: UUID
    title: str
    description: str
    severity: IncidentSeverity
    status: IncidentStatus
    version: int
    created_at: datetime
    updated_at: datetime
    resolved_at: datetime | None
    closed_at: datetime | None

    @classmethod
    def from_domain(cls, incident: Incident) -> "IncidentResponse":
        return cls(
            id=incident.id,
            workspace_id=incident.workspace_id,
            title=incident.title,
            description=incident.description,
            severity=incident.severity,
            status=incident.status,
            version=incident.version,
            created_at=incident.created_at,
            updated_at=incident.updated_at,
            resolved_at=incident.resolved_at,
            closed_at=incident.closed_at,
        )


class IncidentEventResponse(BaseModel):
    """Public append-only timeline entry."""

    id: UUID
    incident_id: UUID
    sequence: int
    event_type: IncidentEventType
    actor_id: str
    data: EventData
    occurred_at: datetime

    @classmethod
    def from_domain(cls, timeline_event: IncidentEvent) -> "IncidentEventResponse":
        return cls(
            id=timeline_event.id,
            incident_id=timeline_event.incident_id,
            sequence=timeline_event.sequence,
            event_type=timeline_event.event_type,
            actor_id=timeline_event.actor_id,
            data=timeline_event.data,
            occurred_at=timeline_event.occurred_at,
        )
