"""Workspace-isolated Incident lifecycle and Timeline routes."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status

from sentinelflow.api.dependencies import get_incident_service
from sentinelflow.api.errors import ErrorResponse
from sentinelflow.api.schemas import (
    AddIncidentNoteRequest,
    CreateIncidentRequest,
    IncidentEventResponse,
    IncidentResponse,
    TransitionIncidentRequest,
)
from sentinelflow.application import IncidentService
from sentinelflow.domain import IncidentStatus

router = APIRouter(prefix="/incidents", tags=["incidents"])

WorkspaceHeader = Annotated[UUID, Header(alias="X-Workspace-ID")]
ActorHeader = Annotated[
    str,
    Header(alias="X-Actor-ID", min_length=1, max_length=200),
]
IdempotencyHeader = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=200),
]
IncidentServiceDependency = Annotated[IncidentService, Depends(get_incident_service)]

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Incident not found in workspace"},
    409: {"model": ErrorResponse, "description": "Lifecycle or concurrency conflict"},
}


@router.post(
    "",
    response_model=IncidentResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: ERROR_RESPONSES[409]},
)
async def create_incident(
    payload: CreateIncidentRequest,
    workspace_id: WorkspaceHeader,
    actor_id: ActorHeader,
    idempotency_key: IdempotencyHeader,
    service: IncidentServiceDependency,
) -> IncidentResponse:
    """Create a new workspace-scoped incident."""
    incident = await service.create(
        workspace_id=workspace_id,
        title=payload.title,
        description=payload.description,
        severity=payload.severity,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
    )
    return IncidentResponse.from_domain(incident)


@router.get("", response_model=list[IncidentResponse])
async def list_incidents(
    workspace_id: WorkspaceHeader,
    service: IncidentServiceDependency,
    status_filter: Annotated[IncidentStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=10000)] = 0,
) -> list[IncidentResponse]:
    """List incidents without crossing a workspace boundary."""
    incidents = await service.list(
        workspace_id=workspace_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return [IncidentResponse.from_domain(incident) for incident in incidents]


@router.get("/{incident_id}", response_model=IncidentResponse, responses=ERROR_RESPONSES)
async def get_incident(
    incident_id: UUID,
    workspace_id: WorkspaceHeader,
    service: IncidentServiceDependency,
) -> IncidentResponse:
    """Get one incident from the caller's workspace."""
    incident = await service.get(workspace_id=workspace_id, incident_id=incident_id)
    return IncidentResponse.from_domain(incident)


@router.post(
    "/{incident_id}/transitions",
    response_model=IncidentResponse,
    responses=ERROR_RESPONSES,
)
async def transition_incident(
    incident_id: UUID,
    payload: TransitionIncidentRequest,
    workspace_id: WorkspaceHeader,
    actor_id: ActorHeader,
    idempotency_key: IdempotencyHeader,
    service: IncidentServiceDependency,
) -> IncidentResponse:
    """Move an incident through one permitted lifecycle edge."""
    incident = await service.transition(
        workspace_id=workspace_id,
        incident_id=incident_id,
        target=payload.target_status,
        reason=payload.reason,
        expected_version=payload.expected_version,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
    )
    return IncidentResponse.from_domain(incident)


@router.post(
    "/{incident_id}/notes",
    response_model=IncidentEventResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
)
async def add_incident_note(
    incident_id: UUID,
    payload: AddIncidentNoteRequest,
    workspace_id: WorkspaceHeader,
    actor_id: ActorHeader,
    idempotency_key: IdempotencyHeader,
    service: IncidentServiceDependency,
) -> IncidentEventResponse:
    """Append an operator note to an incident timeline."""
    timeline_event = await service.add_note(
        workspace_id=workspace_id,
        incident_id=incident_id,
        body=payload.body,
        expected_version=payload.expected_version,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
    )
    return IncidentEventResponse.from_domain(timeline_event)


@router.get(
    "/{incident_id}/timeline",
    response_model=list[IncidentEventResponse],
    responses=ERROR_RESPONSES,
)
async def get_incident_timeline(
    incident_id: UUID,
    workspace_id: WorkspaceHeader,
    service: IncidentServiceDependency,
    after_sequence: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[IncidentEventResponse]:
    """Return ordered timeline entries after a sequence cursor."""
    timeline = await service.timeline(
        workspace_id=workspace_id,
        incident_id=incident_id,
        after_sequence=after_sequence,
        limit=limit,
    )
    return [IncidentEventResponse.from_domain(timeline_event) for timeline_event in timeline]
