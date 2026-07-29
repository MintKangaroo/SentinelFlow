"""Risk-based human approval policies for protected workflow actions."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from sentinelflow.domain.playbook import JsonObject, PlaybookStepRisk


class ApprovalStatus(StrEnum):
    """Lifecycle of one renewable approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class ApprovalDecisionValue(StrEnum):
    """An authenticated human decision."""

    APPROVE = "approve"
    REJECT = "reject"


class ApprovalEventType(StrEnum):
    """Append-only approval policy events."""

    CREATED = "approval_created"
    DECISION_RECORDED = "approval_decision_recorded"
    EXPIRED = "approval_expired"
    RENEWED = "approval_renewed"
    CANCELLED = "approval_cancelled"


class ApprovalError(Exception):
    """Base class for stable approval failures."""

    code = "approval_error"


class ApprovalNotFound(ApprovalError):
    code = "approval_not_found"

    def __init__(self) -> None:
        super().__init__("Approval request was not found in this workspace")


class ApprovalDependencyNotFound(ApprovalError):
    code = "approval_dependency_not_found"

    def __init__(self) -> None:
        super().__init__("Workflow approval step was not found in this workspace")


class InvalidApprovalPolicy(ApprovalError):
    code = "invalid_approval_policy"


class InvalidApprovalTransition(ApprovalError):
    code = "invalid_approval_transition"


class ApprovalVersionConflict(ApprovalError):
    code = "approval_version_conflict"

    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(f"Expected approval version {expected}, current version is {actual}")


class ApprovalIdempotencyConflict(ApprovalError):
    code = "approval_idempotency_conflict"


class ConcurrentApprovalWrite(ApprovalError):
    code = "concurrent_approval_write"


@dataclass(frozen=True, slots=True)
class ApprovalDecision:
    """Immutable decision retained across approval rounds."""

    id: UUID
    workspace_id: UUID
    approval_id: UUID
    round: int
    actor_id: str
    actor_role: str
    decision: ApprovalDecisionValue
    reason: str
    occurred_at: datetime


@dataclass(slots=True)
class ApprovalRequest:
    """Aggregate enforcing quorum, role, separation-of-duty, and expiration."""

    id: UUID
    workspace_id: UUID
    incident_id: UUID
    workflow_id: UUID
    step_key: str
    action_summary: str
    risk: PlaybookStepRisk
    status: ApprovalStatus
    required_approvals: int
    eligible_roles: tuple[str, ...]
    version: int
    round: int
    requested_by: str
    expires_at: datetime
    created_at: datetime
    updated_at: datetime
    decisions: list[ApprovalDecision] = field(default_factory=list)
    decided_at: datetime | None = None
    cancelled_at: datetime | None = None

    def __post_init__(self) -> None:
        minimum = 2 if self.risk in {PlaybookStepRisk.HIGH, PlaybookStepRisk.CRITICAL} else 1
        if not 1 <= self.required_approvals <= 5 or self.required_approvals < minimum:
            raise InvalidApprovalPolicy(
                f"{self.risk.value} actions require at least {minimum} approver(s)"
            )
        if not self.step_key or not self.action_summary.strip():
            raise InvalidApprovalPolicy("Step key and action summary are required")
        if not self.eligible_roles or len(set(self.eligible_roles)) != len(self.eligible_roles):
            raise InvalidApprovalPolicy("Eligible approver roles must be non-empty and unique")
        if self.expires_at <= self.created_at:
            raise InvalidApprovalPolicy("Approval expiration must be after creation")

    @property
    def current_decisions(self) -> list[ApprovalDecision]:
        return [decision for decision in self.decisions if decision.round == self.round]

    @property
    def approval_count(self) -> int:
        return sum(
            decision.decision is ApprovalDecisionValue.APPROVE
            for decision in self.current_decisions
        )

    def decide(
        self,
        *,
        decision_id: UUID,
        actor_id: str,
        actor_role: str,
        decision: ApprovalDecisionValue,
        reason: str,
        occurred_at: datetime,
        expected_version: int,
    ) -> ApprovalDecision:
        self._expect_version(expected_version)
        if self.status is not ApprovalStatus.PENDING:
            raise InvalidApprovalTransition("Only pending approval requests accept decisions")
        if occurred_at >= self.expires_at:
            raise InvalidApprovalTransition("Approval request has expired")
        if actor_role not in self.eligible_roles:
            raise InvalidApprovalTransition("Actor role is not eligible for this approval")
        if self.risk in {PlaybookStepRisk.HIGH, PlaybookStepRisk.CRITICAL} and (
            actor_id == self.requested_by
        ):
            raise InvalidApprovalTransition("Requester cannot approve a high-risk action")
        if any(item.actor_id == actor_id for item in self.current_decisions):
            raise InvalidApprovalTransition("Actor already decided in this approval round")
        if decision is ApprovalDecisionValue.REJECT and not reason.strip():
            raise InvalidApprovalTransition("A rejection reason is required")
        record = ApprovalDecision(
            id=decision_id,
            workspace_id=self.workspace_id,
            approval_id=self.id,
            round=self.round,
            actor_id=actor_id,
            actor_role=actor_role,
            decision=decision,
            reason=reason.strip(),
            occurred_at=occurred_at,
        )
        self.decisions.append(record)
        if decision is ApprovalDecisionValue.REJECT:
            self.status = ApprovalStatus.REJECTED
            self.decided_at = occurred_at
        elif self.approval_count >= self.required_approvals:
            self.status = ApprovalStatus.APPROVED
            self.decided_at = occurred_at
        self._advance(occurred_at)
        return record

    def expire(self, occurred_at: datetime, expected_version: int) -> None:
        self._expect_version(expected_version)
        if self.status is not ApprovalStatus.PENDING or occurred_at < self.expires_at:
            raise InvalidApprovalTransition("Approval request is not eligible for expiration")
        self.status = ApprovalStatus.EXPIRED
        self.decided_at = occurred_at
        self._advance(occurred_at)

    def renew(
        self,
        *,
        expires_at: datetime,
        occurred_at: datetime,
        expected_version: int,
    ) -> None:
        self._expect_version(expected_version)
        if self.status not in {ApprovalStatus.EXPIRED, ApprovalStatus.REJECTED}:
            raise InvalidApprovalTransition("Only expired or rejected approvals can be renewed")
        if expires_at <= occurred_at:
            raise InvalidApprovalTransition("Renewed expiration must be in the future")
        self.round += 1
        self.status = ApprovalStatus.PENDING
        self.expires_at = expires_at
        self.decided_at = None
        self._advance(occurred_at)

    def cancel(self, occurred_at: datetime, expected_version: int) -> None:
        self._expect_version(expected_version)
        if self.status is not ApprovalStatus.PENDING:
            raise InvalidApprovalTransition("Only pending approvals can be cancelled")
        self.status = ApprovalStatus.CANCELLED
        self.cancelled_at = occurred_at
        self._advance(occurred_at)

    def _expect_version(self, expected_version: int) -> None:
        if self.version != expected_version:
            raise ApprovalVersionConflict(expected_version, self.version)

    def _advance(self, occurred_at: datetime) -> None:
        self.version += 1
        self.updated_at = occurred_at


@dataclass(frozen=True, slots=True)
class ApprovalEvent:
    """Immutable approval command event and idempotency record."""

    id: UUID
    workspace_id: UUID
    approval_id: UUID
    sequence: int
    event_type: ApprovalEventType
    actor_id: str
    idempotency_key: str
    data: JsonObject
    occurred_at: datetime
