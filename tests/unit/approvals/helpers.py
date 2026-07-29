from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sentinelflow.domain import (
    ApprovalRequest,
    ApprovalStatus,
    PlaybookStepRisk,
)


def approval_request(
    *,
    risk: PlaybookStepRisk = PlaybookStepRisk.CRITICAL,
    required_approvals: int = 2,
) -> ApprovalRequest:
    now = datetime(2026, 7, 28, 1, 0, tzinfo=UTC)
    return ApprovalRequest(
        id=uuid4(),
        workspace_id=uuid4(),
        incident_id=uuid4(),
        workflow_id=uuid4(),
        step_key="approve_isolation",
        action_summary="Isolate endpoint and revoke active sessions",
        risk=risk,
        status=ApprovalStatus.PENDING,
        required_approvals=required_approvals,
        eligible_roles=("soc_lead", "incident_commander"),
        version=1,
        round=1,
        requested_by="requester@example.com",
        expires_at=now + timedelta(hours=1),
        created_at=now,
        updated_at=now,
    )
