"""Deterministic incident report projection for operators and auditors."""

import hashlib
import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel

from sentinelflow.api.dependencies import (
    get_approval_service,
    get_incident_service,
    get_workflow_service,
)
from sentinelflow.application import ApprovalService, IncidentService, WorkflowService

router = APIRouter(prefix="/reports", tags=["reports"])


class IncidentReportResponse(BaseModel):
    incident_id: UUID
    summary: str
    timeline: list[dict[str, object]]
    approvals: list[dict[str, object]]
    workflows: list[dict[str, object]]
    digest: str


@router.get("/incidents/{incident_id}", response_model=IncidentReportResponse)
async def incident_report(
    incident_id: UUID,
    workspace_id: Annotated[UUID, Header(alias="X-Workspace-ID")],
    incidents: Annotated[IncidentService, Depends(get_incident_service)],
    approvals: Annotated[ApprovalService, Depends(get_approval_service)],
    workflows: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> IncidentReportResponse:
    incident = await incidents.get(workspace_id=workspace_id, incident_id=incident_id)
    events = await incidents.timeline(
        workspace_id=workspace_id, incident_id=incident_id, after_sequence=0, limit=500
    )
    approval_items = await approvals.list(
        workspace_id=workspace_id, status=None, workflow_id=None, limit=200, offset=0
    )
    approval_items = [item for item in approval_items if item.incident_id == incident_id]
    timeline = [
        {
            "sequence": e.sequence,
            "type": e.event_type.value,
            "actor": e.actor_id,
            "occurred_at": e.occurred_at.isoformat(),
            "data": e.data,
        }
        for e in events
    ]
    approval_data = [
        {
            "id": str(a.id),
            "step_key": a.step_key,
            "status": a.status.value,
            "risk": a.risk.value,
            "required": a.required_approvals,
            "expires_at": a.expires_at.isoformat(),
        }
        for a in approval_items
    ]
    # Workflow projections are intentionally linked through the approval rows.
    workflow_data: list[dict[str, object]] = []
    for approval in approval_items:
        if approval.workflow_id is None:
            continue
        workflow = await workflows.get(workspace_id=workspace_id, workflow_id=approval.workflow_id)
        workflow_data.append(
            {
                "id": str(workflow.id),
                "status": workflow.status.value,
                "version": workflow.version,
                "steps": [s.status.value for s in workflow.steps],
            }
        )
    payload = {
        "incident_id": str(incident.id),
        "summary": incident.title,
        "timeline": timeline,
        "approvals": approval_data,
        "workflows": workflow_data,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return IncidentReportResponse(
        incident_id=incident.id,
        summary=incident.title,
        timeline=timeline,
        approvals=approval_data,
        workflows=workflow_data,
        digest=digest,
    )
