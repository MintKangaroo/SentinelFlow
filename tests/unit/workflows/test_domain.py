from datetime import UTC, datetime, timedelta

import pytest

from sentinelflow.domain import (
    InvalidWorkflowTransition,
    WorkflowStatus,
    WorkflowStepStatus,
    WorkflowVersionConflict,
)
from tests.unit.workflows.helpers import workflow_run


def tick(offset: int) -> datetime:
    return datetime(2026, 7, 28, 2, 0, tzinfo=UTC) + timedelta(seconds=offset)


def test_successful_workflow_respects_approval_boundary() -> None:
    workflow = workflow_run()
    workflow.start(tick(1), expected_version=1)
    assert workflow.steps[0].status is WorkflowStepStatus.RUNNING

    workflow.record_step_result(
        step_key="enrich",
        succeeded=True,
        output={"asset": "host-1"},
        error_code=None,
        occurred_at=tick(2),
        expected_version=2,
    )
    assert workflow.status is WorkflowStatus.AWAITING_APPROVAL
    assert workflow.steps[1].status is WorkflowStepStatus.WAITING_APPROVAL

    workflow.record_approval(
        step_key="approve",
        approved=True,
        occurred_at=tick(3),
        expected_version=3,
    )
    assert workflow.steps[2].status is WorkflowStepStatus.RUNNING

    workflow.record_step_result(
        step_key="isolate",
        succeeded=True,
        output={"isolated": True},
        error_code=None,
        occurred_at=tick(4),
        expected_version=4,
    )
    workflow.record_step_result(
        step_key="validate",
        succeeded=True,
        output={"contained": True},
        error_code=None,
        occurred_at=tick(5),
        expected_version=5,
    )
    assert workflow.status.value == WorkflowStatus.SUCCEEDED.value
    assert workflow.finished_at == tick(5)


def test_retry_budget_is_bounded() -> None:
    workflow = workflow_run()
    workflow.start(tick(1), 1)
    for attempt in range(1, 4):
        workflow.record_step_result(
            step_key="enrich",
            succeeded=False,
            output={},
            error_code="dependency_unavailable",
            occurred_at=tick(attempt * 2),
            expected_version=workflow.version,
        )
        if attempt < 3:
            workflow.retry_step(
                step_key="enrich",
                occurred_at=tick(attempt * 2 + 1),
                expected_version=workflow.version,
            )

    assert workflow.status is WorkflowStatus.FAILED
    assert workflow.steps[0].attempt == 3
    with pytest.raises(InvalidWorkflowTransition, match="budget"):
        workflow.retry_step(
            step_key="enrich",
            occurred_at=tick(10),
            expected_version=workflow.version,
        )


def test_failure_compensates_applied_actions_in_reverse() -> None:
    workflow = workflow_run()
    workflow.start(tick(1), 1)
    workflow.record_step_result(
        step_key="enrich",
        succeeded=True,
        output={},
        error_code=None,
        occurred_at=tick(2),
        expected_version=2,
    )
    workflow.record_approval(
        step_key="approve",
        approved=True,
        occurred_at=tick(3),
        expected_version=3,
    )
    workflow.record_step_result(
        step_key="isolate",
        succeeded=True,
        output={},
        error_code=None,
        occurred_at=tick(4),
        expected_version=4,
    )
    for attempt in range(3):
        workflow.record_step_result(
            step_key="validate",
            succeeded=False,
            output={},
            error_code="validation_failed",
            occurred_at=tick(5 + attempt * 2),
            expected_version=workflow.version,
        )
        if attempt < 2:
            workflow.retry_step(
                step_key="validate",
                occurred_at=tick(6 + attempt * 2),
                expected_version=workflow.version,
            )

    assert workflow.status.value == WorkflowStatus.COMPENSATING.value
    assert workflow.steps[2].status is WorkflowStepStatus.COMPENSATING
    workflow.record_compensation(
        step_key="isolate",
        succeeded=True,
        error_code=None,
        occurred_at=tick(12),
        expected_version=workflow.version,
    )
    assert workflow.steps[2].status.value == WorkflowStepStatus.COMPENSATED.value
    assert workflow.status.value == WorkflowStatus.FAILED.value


def test_cancellation_compensates_and_stale_version_is_rejected() -> None:
    workflow = workflow_run()
    with pytest.raises(WorkflowVersionConflict):
        workflow.start(tick(1), expected_version=99)
    workflow.start(tick(1), expected_version=1)
    workflow.record_step_result(
        step_key="enrich",
        succeeded=True,
        output={},
        error_code=None,
        occurred_at=tick(2),
        expected_version=2,
    )
    workflow.record_approval(
        step_key="approve",
        approved=True,
        occurred_at=tick(3),
        expected_version=3,
    )
    workflow.record_step_result(
        step_key="isolate",
        succeeded=True,
        output={},
        error_code=None,
        occurred_at=tick(4),
        expected_version=4,
    )
    workflow.request_cancel(tick(5), expected_version=5)
    assert workflow.status is WorkflowStatus.COMPENSATING
    workflow.record_compensation(
        step_key="isolate",
        succeeded=True,
        error_code=None,
        occurred_at=tick(6),
        expected_version=6,
    )
    assert workflow.status.value == WorkflowStatus.CANCELLED.value
