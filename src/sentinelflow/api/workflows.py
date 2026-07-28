"""Workspace-isolated auditable workflow routes."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status

from sentinelflow.api.dependencies import get_workflow_service
from sentinelflow.api.errors import ErrorResponse
from sentinelflow.api.workflow_schemas import (
    CreateWorkflowRequest,
    WorkflowApprovalRequest,
    WorkflowCompensationRequest,
    WorkflowEventResponse,
    WorkflowMutationRequest,
    WorkflowResponse,
    WorkflowStepResultRequest,
)
from sentinelflow.application import WorkflowService
from sentinelflow.domain import WorkflowStatus

router = APIRouter(prefix="/workflows", tags=["workflows"])

WorkspaceHeader = Annotated[UUID, Header(alias="X-Workspace-ID")]
ActorHeader = Annotated[str, Header(alias="X-Actor-ID", min_length=1, max_length=200)]
IdempotencyHeader = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=200),
]
WorkflowServiceDependency = Annotated[WorkflowService, Depends(get_workflow_service)]

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Workflow or dependency not found"},
    409: {"model": ErrorResponse, "description": "Workflow state or concurrency conflict"},
}


@router.post(
    "",
    response_model=WorkflowResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
)
async def create_workflow(
    payload: CreateWorkflowRequest,
    workspace_id: WorkspaceHeader,
    actor_id: ActorHeader,
    idempotency_key: IdempotencyHeader,
    service: WorkflowServiceDependency,
) -> WorkflowResponse:
    workflow = await service.create(
        workspace_id=workspace_id,
        incident_id=payload.incident_id,
        playbook_id=payload.playbook_id,
        playbook_version=payload.playbook_version,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
    )
    return WorkflowResponse.from_domain(workflow)


@router.get("", response_model=list[WorkflowResponse])
async def list_workflows(
    workspace_id: WorkspaceHeader,
    service: WorkflowServiceDependency,
    status_filter: Annotated[WorkflowStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=10000)] = 0,
) -> list[WorkflowResponse]:
    workflows = await service.list(
        workspace_id=workspace_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return [WorkflowResponse.from_domain(workflow) for workflow in workflows]


@router.get("/{workflow_id}", response_model=WorkflowResponse, responses=ERROR_RESPONSES)
async def get_workflow(
    workflow_id: UUID,
    workspace_id: WorkspaceHeader,
    service: WorkflowServiceDependency,
) -> WorkflowResponse:
    workflow = await service.get(workspace_id=workspace_id, workflow_id=workflow_id)
    return WorkflowResponse.from_domain(workflow)


async def _simple_mutation(
    *,
    operation: str,
    workflow_id: UUID,
    payload: WorkflowMutationRequest,
    workspace_id: UUID,
    actor_id: str,
    idempotency_key: str,
    service: WorkflowService,
) -> WorkflowResponse:
    method = service.start if operation == "start" else service.cancel
    workflow = await method(
        workspace_id=workspace_id,
        workflow_id=workflow_id,
        expected_version=payload.expected_version,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
    )
    return WorkflowResponse.from_domain(workflow)


@router.post("/{workflow_id}/start", response_model=WorkflowResponse, responses=ERROR_RESPONSES)
async def start_workflow(
    workflow_id: UUID,
    payload: WorkflowMutationRequest,
    workspace_id: WorkspaceHeader,
    actor_id: ActorHeader,
    idempotency_key: IdempotencyHeader,
    service: WorkflowServiceDependency,
) -> WorkflowResponse:
    return await _simple_mutation(
        operation="start",
        workflow_id=workflow_id,
        payload=payload,
        workspace_id=workspace_id,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        service=service,
    )


@router.post("/{workflow_id}/cancel", response_model=WorkflowResponse, responses=ERROR_RESPONSES)
async def cancel_workflow(
    workflow_id: UUID,
    payload: WorkflowMutationRequest,
    workspace_id: WorkspaceHeader,
    actor_id: ActorHeader,
    idempotency_key: IdempotencyHeader,
    service: WorkflowServiceDependency,
) -> WorkflowResponse:
    return await _simple_mutation(
        operation="cancel",
        workflow_id=workflow_id,
        payload=payload,
        workspace_id=workspace_id,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        service=service,
    )


@router.post(
    "/{workflow_id}/steps/{step_key}/result",
    response_model=WorkflowResponse,
    responses=ERROR_RESPONSES,
)
async def record_step_result(
    workflow_id: UUID,
    step_key: str,
    payload: WorkflowStepResultRequest,
    workspace_id: WorkspaceHeader,
    actor_id: ActorHeader,
    idempotency_key: IdempotencyHeader,
    service: WorkflowServiceDependency,
) -> WorkflowResponse:
    workflow = await service.record_step_result(
        workspace_id=workspace_id,
        workflow_id=workflow_id,
        step_key=step_key,
        succeeded=payload.succeeded,
        output=payload.output,
        error_code=payload.error_code,
        expected_version=payload.expected_version,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
    )
    return WorkflowResponse.from_domain(workflow)


@router.post(
    "/{workflow_id}/steps/{step_key}/retry",
    response_model=WorkflowResponse,
    responses=ERROR_RESPONSES,
)
async def retry_workflow_step(
    workflow_id: UUID,
    step_key: str,
    payload: WorkflowMutationRequest,
    workspace_id: WorkspaceHeader,
    actor_id: ActorHeader,
    idempotency_key: IdempotencyHeader,
    service: WorkflowServiceDependency,
) -> WorkflowResponse:
    workflow = await service.retry_step(
        workspace_id=workspace_id,
        workflow_id=workflow_id,
        step_key=step_key,
        expected_version=payload.expected_version,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
    )
    return WorkflowResponse.from_domain(workflow)


@router.post(
    "/{workflow_id}/steps/{step_key}/approval",
    response_model=WorkflowResponse,
    responses=ERROR_RESPONSES,
)
async def record_workflow_approval(
    workflow_id: UUID,
    step_key: str,
    payload: WorkflowApprovalRequest,
    workspace_id: WorkspaceHeader,
    actor_id: ActorHeader,
    idempotency_key: IdempotencyHeader,
    service: WorkflowServiceDependency,
) -> WorkflowResponse:
    workflow = await service.record_approval(
        workspace_id=workspace_id,
        workflow_id=workflow_id,
        step_key=step_key,
        approved=payload.approved,
        expected_version=payload.expected_version,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
    )
    return WorkflowResponse.from_domain(workflow)


@router.post(
    "/{workflow_id}/steps/{step_key}/compensation",
    response_model=WorkflowResponse,
    responses=ERROR_RESPONSES,
)
async def record_workflow_compensation(
    workflow_id: UUID,
    step_key: str,
    payload: WorkflowCompensationRequest,
    workspace_id: WorkspaceHeader,
    actor_id: ActorHeader,
    idempotency_key: IdempotencyHeader,
    service: WorkflowServiceDependency,
) -> WorkflowResponse:
    workflow = await service.record_compensation(
        workspace_id=workspace_id,
        workflow_id=workflow_id,
        step_key=step_key,
        succeeded=payload.succeeded,
        error_code=payload.error_code,
        expected_version=payload.expected_version,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
    )
    return WorkflowResponse.from_domain(workflow)


@router.post(
    "/{workflow_id}/steps/{step_key}/timeout",
    response_model=WorkflowResponse,
    responses=ERROR_RESPONSES,
)
async def timeout_workflow_step(
    workflow_id: UUID,
    step_key: str,
    payload: WorkflowMutationRequest,
    workspace_id: WorkspaceHeader,
    actor_id: ActorHeader,
    idempotency_key: IdempotencyHeader,
    service: WorkflowServiceDependency,
) -> WorkflowResponse:
    workflow = await service.timeout_step(
        workspace_id=workspace_id,
        workflow_id=workflow_id,
        step_key=step_key,
        expected_version=payload.expected_version,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
    )
    return WorkflowResponse.from_domain(workflow)


@router.get(
    "/{workflow_id}/events",
    response_model=list[WorkflowEventResponse],
    responses=ERROR_RESPONSES,
)
async def list_workflow_events(
    workflow_id: UUID,
    workspace_id: WorkspaceHeader,
    service: WorkflowServiceDependency,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[WorkflowEventResponse]:
    events = await service.events(workspace_id=workspace_id, workflow_id=workflow_id, limit=limit)
    return [WorkflowEventResponse.from_domain(event) for event in events]
