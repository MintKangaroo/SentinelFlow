"""Workspace-isolated versioned response playbook routes."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status

from sentinelflow.api.dependencies import get_playbook_service
from sentinelflow.api.errors import ErrorResponse
from sentinelflow.api.playbook_schemas import (
    CreatePlaybookRequest,
    CreatePlaybookVersionRequest,
    PlaybookDetailResponse,
    PlaybookEventResponse,
    PlaybookMutationRequest,
    PlaybookResponse,
    PlaybookVersionResponse,
)
from sentinelflow.application import PlaybookService
from sentinelflow.domain import PlaybookStatus

router = APIRouter(prefix="/playbooks", tags=["playbooks"])

WorkspaceHeader = Annotated[UUID, Header(alias="X-Workspace-ID")]
ActorHeader = Annotated[str, Header(alias="X-Actor-ID", min_length=1, max_length=200)]
IdempotencyHeader = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=200),
]
PlaybookServiceDependency = Annotated[PlaybookService, Depends(get_playbook_service)]

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Playbook or revision not found"},
    409: {"model": ErrorResponse, "description": "Lifecycle or concurrency conflict"},
    422: {"model": ErrorResponse, "description": "Invalid playbook definition"},
}


@router.post(
    "",
    response_model=PlaybookDetailResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
)
async def create_playbook(
    payload: CreatePlaybookRequest,
    workspace_id: WorkspaceHeader,
    actor_id: ActorHeader,
    idempotency_key: IdempotencyHeader,
    service: PlaybookServiceDependency,
) -> PlaybookDetailResponse:
    """Create a playbook and its first immutable revision."""
    playbook, revision = await service.create(
        workspace_id=workspace_id,
        name=payload.name,
        description=payload.description,
        steps=payload.domain_steps(),
        actor_id=actor_id,
        idempotency_key=idempotency_key,
    )
    return PlaybookDetailResponse(
        playbook=PlaybookResponse.from_domain(playbook),
        revision=PlaybookVersionResponse.from_domain(revision),
    )


@router.get("", response_model=list[PlaybookResponse])
async def list_playbooks(
    workspace_id: WorkspaceHeader,
    service: PlaybookServiceDependency,
    status_filter: Annotated[PlaybookStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=10000)] = 0,
) -> list[PlaybookResponse]:
    """List workspace-scoped playbooks."""
    playbooks = await service.list(
        workspace_id=workspace_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return [PlaybookResponse.from_domain(playbook) for playbook in playbooks]


@router.get("/{playbook_id}", response_model=PlaybookResponse, responses=ERROR_RESPONSES)
async def get_playbook(
    playbook_id: UUID,
    workspace_id: WorkspaceHeader,
    service: PlaybookServiceDependency,
) -> PlaybookResponse:
    """Get one playbook from the caller's workspace."""
    playbook = await service.get(workspace_id=workspace_id, playbook_id=playbook_id)
    return PlaybookResponse.from_domain(playbook)


@router.post(
    "/{playbook_id}/versions",
    response_model=PlaybookDetailResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
)
async def create_playbook_version(
    playbook_id: UUID,
    payload: CreatePlaybookVersionRequest,
    workspace_id: WorkspaceHeader,
    actor_id: ActorHeader,
    idempotency_key: IdempotencyHeader,
    service: PlaybookServiceDependency,
) -> PlaybookDetailResponse:
    """Append a validated immutable revision."""
    playbook, revision = await service.create_version(
        workspace_id=workspace_id,
        playbook_id=playbook_id,
        steps=payload.domain_steps(),
        expected_version=payload.expected_version,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
    )
    return PlaybookDetailResponse(
        playbook=PlaybookResponse.from_domain(playbook),
        revision=PlaybookVersionResponse.from_domain(revision),
    )


@router.get(
    "/{playbook_id}/versions",
    response_model=list[PlaybookVersionResponse],
    responses=ERROR_RESPONSES,
)
async def list_playbook_versions(
    playbook_id: UUID,
    workspace_id: WorkspaceHeader,
    service: PlaybookServiceDependency,
) -> list[PlaybookVersionResponse]:
    """List immutable revisions newest first."""
    versions = await service.list_versions(workspace_id=workspace_id, playbook_id=playbook_id)
    return [PlaybookVersionResponse.from_domain(version) for version in versions]


@router.get(
    "/{playbook_id}/versions/{revision}",
    response_model=PlaybookVersionResponse,
    responses=ERROR_RESPONSES,
)
async def get_playbook_version(
    playbook_id: UUID,
    revision: int,
    workspace_id: WorkspaceHeader,
    service: PlaybookServiceDependency,
) -> PlaybookVersionResponse:
    """Get one content-addressed immutable revision."""
    version = await service.get_version(
        workspace_id=workspace_id,
        playbook_id=playbook_id,
        number=revision,
    )
    return PlaybookVersionResponse.from_domain(version)


@router.post(
    "/{playbook_id}/versions/{revision}/publish",
    response_model=PlaybookResponse,
    responses=ERROR_RESPONSES,
)
async def publish_playbook_version(
    playbook_id: UUID,
    revision: int,
    payload: PlaybookMutationRequest,
    workspace_id: WorkspaceHeader,
    actor_id: ActorHeader,
    idempotency_key: IdempotencyHeader,
    service: PlaybookServiceDependency,
) -> PlaybookResponse:
    """Make one immutable revision active."""
    playbook = await service.publish(
        workspace_id=workspace_id,
        playbook_id=playbook_id,
        revision=revision,
        expected_version=payload.expected_version,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
    )
    return PlaybookResponse.from_domain(playbook)


@router.post(
    "/{playbook_id}/archive",
    response_model=PlaybookResponse,
    responses=ERROR_RESPONSES,
)
async def archive_playbook(
    playbook_id: UUID,
    payload: PlaybookMutationRequest,
    workspace_id: WorkspaceHeader,
    actor_id: ActorHeader,
    idempotency_key: IdempotencyHeader,
    service: PlaybookServiceDependency,
) -> PlaybookResponse:
    """Make a playbook permanently read-only."""
    playbook = await service.archive(
        workspace_id=workspace_id,
        playbook_id=playbook_id,
        expected_version=payload.expected_version,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
    )
    return PlaybookResponse.from_domain(playbook)


@router.get(
    "/{playbook_id}/events",
    response_model=list[PlaybookEventResponse],
    responses=ERROR_RESPONSES,
)
async def list_playbook_events(
    playbook_id: UUID,
    workspace_id: WorkspaceHeader,
    service: PlaybookServiceDependency,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[PlaybookEventResponse]:
    """Return the append-only change history."""
    events = await service.events(
        workspace_id=workspace_id,
        playbook_id=playbook_id,
        limit=limit,
    )
    return [PlaybookEventResponse.from_domain(event) for event in events]
