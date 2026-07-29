"""HTTP schemas for risk-based approval requests."""

from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from sentinelflow.domain import (
    ApprovalDecision,
    ApprovalDecisionValue,
    ApprovalEvent,
    ApprovalEventType,
    ApprovalRequest,
    ApprovalStatus,
    PlaybookStepRisk,
)
from sentinelflow.domain.playbook import JsonObject


class CreateApprovalRequest(BaseModel):
    incident_id: UUID
    workflow_id: UUID
    step_key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")
    action_summary: str = Field(min_length=1, max_length=300)
    risk: PlaybookStepRisk
    required_approvals: int = Field(ge=1, le=5)
    eligible_roles: list[str] = Field(min_length=1, max_length=10)
    expires_at: datetime

    @field_validator("eligible_roles")
    @classmethod
    def validate_roles(cls, roles: list[str]) -> list[str]:
        normalized = [role.strip().lower() for role in roles]
        if any(not role or len(role) > 100 for role in normalized):
            raise ValueError("roles must contain 1-100 characters")
        if len(set(normalized)) != len(normalized):
            raise ValueError("roles must be unique")
        return normalized

    @field_validator("expires_at")
    @classmethod
    def validate_expiration(cls, expires_at: datetime) -> datetime:
        if expires_at.tzinfo is None or expires_at.utcoffset() is None:
            raise ValueError("expires_at must include a timezone")
        return expires_at


class ApprovalMutationRequest(BaseModel):
    expected_version: int = Field(ge=1)


class ApprovalDecisionRequest(ApprovalMutationRequest):
    decision: ApprovalDecisionValue
    reason: str = Field(default="", max_length=1000)


class RenewApprovalRequest(ApprovalMutationRequest):
    expires_at: datetime
    reason: str = Field(min_length=1, max_length=1000)

    @field_validator("expires_at")
    @classmethod
    def validate_expiration(cls, expires_at: datetime) -> datetime:
        if expires_at.tzinfo is None or expires_at.utcoffset() is None:
            raise ValueError("expires_at must include a timezone")
        return expires_at


class ApprovalDecisionResponse(BaseModel):
    id: UUID
    round: int
    actor_id: str
    actor_role: str
    decision: ApprovalDecisionValue
    reason: str
    occurred_at: datetime

    @classmethod
    def from_domain(cls, decision: ApprovalDecision) -> Self:
        return cls(
            id=decision.id,
            round=decision.round,
            actor_id=decision.actor_id,
            actor_role=decision.actor_role,
            decision=decision.decision,
            reason=decision.reason,
            occurred_at=decision.occurred_at,
        )


class ApprovalResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    incident_id: UUID
    workflow_id: UUID
    step_key: str
    action_summary: str
    risk: PlaybookStepRisk
    status: ApprovalStatus
    required_approvals: int
    approval_count: int
    eligible_roles: list[str]
    version: int
    round: int
    requested_by: str
    expires_at: datetime
    created_at: datetime
    updated_at: datetime
    decided_at: datetime | None
    cancelled_at: datetime | None
    decisions: list[ApprovalDecisionResponse]

    @classmethod
    def from_domain(cls, approval: ApprovalRequest) -> Self:
        return cls(
            id=approval.id,
            workspace_id=approval.workspace_id,
            incident_id=approval.incident_id,
            workflow_id=approval.workflow_id,
            step_key=approval.step_key,
            action_summary=approval.action_summary,
            risk=approval.risk,
            status=approval.status,
            required_approvals=approval.required_approvals,
            approval_count=approval.approval_count,
            eligible_roles=list(approval.eligible_roles),
            version=approval.version,
            round=approval.round,
            requested_by=approval.requested_by,
            expires_at=approval.expires_at,
            created_at=approval.created_at,
            updated_at=approval.updated_at,
            decided_at=approval.decided_at,
            cancelled_at=approval.cancelled_at,
            decisions=[
                ApprovalDecisionResponse.from_domain(decision) for decision in approval.decisions
            ],
        )


class ApprovalEventResponse(BaseModel):
    id: UUID
    approval_id: UUID
    sequence: int
    event_type: ApprovalEventType
    actor_id: str
    data: JsonObject
    occurred_at: datetime

    @classmethod
    def from_domain(cls, event: ApprovalEvent) -> Self:
        return cls(
            id=event.id,
            approval_id=event.approval_id,
            sequence=event.sequence,
            event_type=event.event_type,
            actor_id=event.actor_id,
            data=event.data,
            occurred_at=event.occurred_at,
        )
