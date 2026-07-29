from dataclasses import replace
from datetime import timedelta
from uuid import uuid4

import pytest

from sentinelflow.domain import (
    ApprovalDecisionValue,
    ApprovalStatus,
    ApprovalVersionConflict,
    InvalidApprovalPolicy,
    InvalidApprovalTransition,
    PlaybookStepRisk,
)
from tests.unit.approvals.helpers import approval_request


def test_high_risk_policy_requires_quorum_and_valid_definition() -> None:
    with pytest.raises(InvalidApprovalPolicy, match="at least 2"):
        approval_request(required_approvals=1)
    with pytest.raises(InvalidApprovalPolicy, match="non-empty and unique"):
        replace(approval_request(), eligible_roles=("soc_lead", "soc_lead"))
    with pytest.raises(InvalidApprovalPolicy, match="expiration"):
        request = approval_request()
        replace(request, expires_at=request.created_at)
    with pytest.raises(InvalidApprovalPolicy, match="required"):
        replace(approval_request(), action_summary=" ")


def test_quorum_enforces_role_separation_and_unique_actors() -> None:
    approval = approval_request()
    now = approval.created_at + timedelta(minutes=5)
    with pytest.raises(ApprovalVersionConflict):
        approval.decide(
            decision_id=uuid4(),
            actor_id="lead@example.com",
            actor_role="soc_lead",
            decision=ApprovalDecisionValue.APPROVE,
            reason="Reviewed",
            occurred_at=now,
            expected_version=9,
        )
    with pytest.raises(InvalidApprovalTransition, match="Requester"):
        approval.decide(
            decision_id=uuid4(),
            actor_id=approval.requested_by,
            actor_role="soc_lead",
            decision=ApprovalDecisionValue.APPROVE,
            reason="Self approval",
            occurred_at=now,
            expected_version=1,
        )
    with pytest.raises(InvalidApprovalTransition, match="role"):
        approval.decide(
            decision_id=uuid4(),
            actor_id="viewer@example.com",
            actor_role="viewer",
            decision=ApprovalDecisionValue.APPROVE,
            reason="Not eligible",
            occurred_at=now,
            expected_version=1,
        )
    first = approval.decide(
        decision_id=uuid4(),
        actor_id="lead@example.com",
        actor_role="soc_lead",
        decision=ApprovalDecisionValue.APPROVE,
        reason="Scope confirmed",
        occurred_at=now,
        expected_version=1,
    )
    assert first.round == 1
    assert approval.status is ApprovalStatus.PENDING
    assert approval.approval_count == 1
    with pytest.raises(InvalidApprovalTransition, match="already"):
        approval.decide(
            decision_id=uuid4(),
            actor_id="lead@example.com",
            actor_role="soc_lead",
            decision=ApprovalDecisionValue.APPROVE,
            reason="Again",
            occurred_at=now,
            expected_version=2,
        )
    approval.decide(
        decision_id=uuid4(),
        actor_id="commander@example.com",
        actor_role="incident_commander",
        decision=ApprovalDecisionValue.APPROVE,
        reason="Evidence reviewed",
        occurred_at=now + timedelta(minutes=1),
        expected_version=2,
    )
    assert approval.status.value == ApprovalStatus.APPROVED.value
    assert approval.decided_at is not None


def test_rejection_requires_reason_and_ends_round() -> None:
    approval = approval_request()
    now = approval.created_at + timedelta(minutes=2)
    with pytest.raises(InvalidApprovalTransition, match="reason"):
        approval.decide(
            decision_id=uuid4(),
            actor_id="lead@example.com",
            actor_role="soc_lead",
            decision=ApprovalDecisionValue.REJECT,
            reason="",
            occurred_at=now,
            expected_version=1,
        )
    approval.decide(
        decision_id=uuid4(),
        actor_id="lead@example.com",
        actor_role="soc_lead",
        decision=ApprovalDecisionValue.REJECT,
        reason="Target scope is too broad",
        occurred_at=now,
        expected_version=1,
    )
    assert approval.status is ApprovalStatus.REJECTED
    with pytest.raises(InvalidApprovalTransition, match="pending"):
        approval.decide(
            decision_id=uuid4(),
            actor_id="commander@example.com",
            actor_role="incident_commander",
            decision=ApprovalDecisionValue.APPROVE,
            reason="Late",
            occurred_at=now,
            expected_version=2,
        )


def test_expiration_renewal_and_cancellation_preserve_history() -> None:
    approval = approval_request()
    with pytest.raises(InvalidApprovalTransition, match="expiration"):
        approval.expire(approval.created_at, expected_version=1)
    approval.expire(approval.expires_at, expected_version=1)
    assert approval.status is ApprovalStatus.EXPIRED
    with pytest.raises(InvalidApprovalTransition, match="future"):
        approval.renew(
            expires_at=approval.expires_at,
            occurred_at=approval.expires_at,
            expected_version=2,
        )
    approval.renew(
        expires_at=approval.expires_at + timedelta(hours=1),
        occurred_at=approval.expires_at,
        expected_version=2,
    )
    assert approval.status.value == ApprovalStatus.PENDING.value
    assert approval.round == 2
    assert approval.current_decisions == []
    approval.cancel(approval.expires_at, expected_version=3)
    assert approval.status.value == ApprovalStatus.CANCELLED.value
    with pytest.raises(InvalidApprovalTransition, match="pending"):
        approval.cancel(approval.expires_at, expected_version=4)


def test_low_risk_allows_one_approver_and_expired_decision_is_rejected() -> None:
    approval = approval_request(risk=PlaybookStepRisk.LOW, required_approvals=1)
    with pytest.raises(InvalidApprovalTransition, match="expired"):
        approval.decide(
            decision_id=uuid4(),
            actor_id="lead@example.com",
            actor_role="soc_lead",
            decision=ApprovalDecisionValue.APPROVE,
            reason="Too late",
            occurred_at=approval.expires_at,
            expected_version=1,
        )
