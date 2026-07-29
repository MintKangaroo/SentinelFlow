"""Workspace-isolated human approval routes."""

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status

from sentinelflow.api.approval_schemas import (
    ApprovalDecisionRequest,
    ApprovalEventResponse,
    ApprovalMutationRequest,
    ApprovalResponse,
    CreateApprovalRequest,
    RenewApprovalRequest,
)
from sentinelflow.api.dependencies import get_approval_service, get_dispatch_scheduler
from sentinelflow.api.errors import ErrorResponse
from sentinelflow.application import ApprovalService, WorkflowDispatchScheduler
from sentinelflow.domain import ApprovalStatus

router = APIRouter(prefix="/approvals", tags=["approvals"])

WorkspaceHeader = Annotated[UUID, Header(alias="X-Workspace-ID")]
ActorHeader = Annotated[str, Header(alias="X-Actor-ID", min_length=1, max_length=200)]
ActorRoleHeader = Annotated[
    str,
    Header(alias="X-Actor-Role", min_length=1, max_length=100),
]
IdempotencyHeader = Annotated[
    str,
    Header(alias="Idempotency-Key", min_length=1, max_length=200),
]
ApprovalServiceDependency = Annotated[ApprovalService, Depends(get_approval_service)]
DispatchSchedulerDependency = Annotated[
    WorkflowDispatchScheduler,
    Depends(get_dispatch_scheduler),
]

ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": ErrorResponse, "description": "Approval or workflow step not found"},
    409: {"model": ErrorResponse, "description": "Approval policy or concurrency conflict"},
    422: {"model": ErrorResponse, "description": "Invalid risk policy"},
}


@router.post(
    "",
    response_model=ApprovalResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
)
async def create_approval(
    payload: CreateApprovalRequest,
    workspace_id: WorkspaceHeader,
    actor_id: ActorHeader,
    idempotency_key: IdempotencyHeader,
    service: ApprovalServiceDependency,
) -> ApprovalResponse:
    approval = await service.create(
        workspace_id=workspace_id,
        incident_id=payload.incident_id,
        workflow_id=payload.workflow_id,
        step_key=payload.step_key,
        action_summary=payload.action_summary,
        risk=payload.risk,
        required_approvals=payload.required_approvals,
        eligible_roles=tuple(payload.eligible_roles),
        expires_at=payload.expires_at,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
    )
    return ApprovalResponse.from_domain(approval)


@router.get("", response_model=list[ApprovalResponse])
async def list_approvals(
    workspace_id: WorkspaceHeader,
    service: ApprovalServiceDependency,
    status_filter: Annotated[ApprovalStatus | None, Query(alias="status")] = None,
    workflow_id: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=10000)] = 0,
) -> list[ApprovalResponse]:
    approvals = await service.list(
        workspace_id=workspace_id,
        status=status_filter,
        workflow_id=workflow_id,
        limit=limit,
        offset=offset,
    )
    return [ApprovalResponse.from_domain(approval) for approval in approvals]


@router.get("/{approval_id}", response_model=ApprovalResponse, responses=ERROR_RESPONSES)
async def get_approval(
    approval_id: UUID,
    workspace_id: WorkspaceHeader,
    service: ApprovalServiceDependency,
) -> ApprovalResponse:
    approval = await service.get(workspace_id=workspace_id, approval_id=approval_id)
    return ApprovalResponse.from_domain(approval)


@router.post(
    "/{approval_id}/decisions",
    response_model=ApprovalResponse,
    responses=ERROR_RESPONSES,
)
async def record_approval_decision(
    approval_id: UUID,
    payload: ApprovalDecisionRequest,
    workspace_id: WorkspaceHeader,
    actor_id: ActorHeader,
    actor_role: ActorRoleHeader,
    idempotency_key: IdempotencyHeader,
    service: ApprovalServiceDependency,
    scheduler: DispatchSchedulerDependency,
) -> ApprovalResponse:
    approval = await service.decide(
        workspace_id=workspace_id,
        approval_id=approval_id,
        decision=payload.decision,
        actor_role=actor_role.strip().lower(),
        reason=payload.reason,
        expected_version=payload.expected_version,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
    )
    if approval.status is not ApprovalStatus.PENDING:
        await scheduler.schedule(workspace_id, approval.workflow_id)
    return ApprovalResponse.from_domain(approval)


async def _simple_mutation(
    *,
    operation: str,
    approval_id: UUID,
    payload: ApprovalMutationRequest,
    workspace_id: UUID,
    actor_id: str,
    idempotency_key: str,
    service: ApprovalService,
) -> ApprovalResponse:
    method = service.expire if operation == "expire" else service.cancel
    approval = await method(
        workspace_id=workspace_id,
        approval_id=approval_id,
        expected_version=payload.expected_version,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
    )
    return ApprovalResponse.from_domain(approval)


@router.post(
    "/{approval_id}/expire",
    response_model=ApprovalResponse,
    responses=ERROR_RESPONSES,
)
async def expire_approval(
    approval_id: UUID,
    payload: ApprovalMutationRequest,
    workspace_id: WorkspaceHeader,
    actor_id: ActorHeader,
    idempotency_key: IdempotencyHeader,
    service: ApprovalServiceDependency,
    scheduler: DispatchSchedulerDependency,
) -> ApprovalResponse:
    response = await _simple_mutation(
        operation="expire",
        approval_id=approval_id,
        payload=payload,
        workspace_id=workspace_id,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        service=service,
    )
    await scheduler.schedule(workspace_id, response.workflow_id)
    return response


@router.post(
    "/{approval_id}/renew",
    response_model=ApprovalResponse,
    responses=ERROR_RESPONSES,
)
async def renew_approval(
    approval_id: UUID,
    payload: RenewApprovalRequest,
    workspace_id: WorkspaceHeader,
    actor_id: ActorHeader,
    idempotency_key: IdempotencyHeader,
    service: ApprovalServiceDependency,
) -> ApprovalResponse:
    approval = await service.renew(
        workspace_id=workspace_id,
        approval_id=approval_id,
        expires_at=payload.expires_at,
        reason=payload.reason,
        expected_version=payload.expected_version,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
    )
    return ApprovalResponse.from_domain(approval)


@router.post(
    "/{approval_id}/cancel",
    response_model=ApprovalResponse,
    responses=ERROR_RESPONSES,
)
async def cancel_approval(
    approval_id: UUID,
    payload: ApprovalMutationRequest,
    workspace_id: WorkspaceHeader,
    actor_id: ActorHeader,
    idempotency_key: IdempotencyHeader,
    service: ApprovalServiceDependency,
    scheduler: DispatchSchedulerDependency,
) -> ApprovalResponse:
    response = await _simple_mutation(
        operation="cancel",
        approval_id=approval_id,
        payload=payload,
        workspace_id=workspace_id,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        service=service,
    )
    await scheduler.schedule(workspace_id, response.workflow_id)
    return response


@router.get(
    "/{approval_id}/events",
    response_model=list[ApprovalEventResponse],
    responses=ERROR_RESPONSES,
)
async def list_approval_events(
    approval_id: UUID,
    workspace_id: WorkspaceHeader,
    service: ApprovalServiceDependency,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[ApprovalEventResponse]:
    events = await service.events(
        workspace_id=workspace_id,
        approval_id=approval_id,
        limit=limit,
    )
    return [ApprovalEventResponse.from_domain(event) for event in events]
