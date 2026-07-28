from datetime import UTC, datetime
from uuid import uuid4

from sentinelflow.domain import (
    PlaybookStepKind,
    PlaybookStepRisk,
    RollbackStrategy,
    WorkflowRun,
    WorkflowStatus,
    WorkflowStepRun,
)


def workflow_run() -> WorkflowRun:
    now = datetime(2026, 7, 28, 1, 0, tzinfo=UTC)
    workspace_id = uuid4()
    workflow_id = uuid4()
    specs = [
        ("enrich", PlaybookStepKind.ENRICHMENT, PlaybookStepRisk.LOW, None),
        ("approve", PlaybookStepKind.APPROVAL, PlaybookStepRisk.HIGH, None),
        (
            "isolate",
            PlaybookStepKind.ACTION,
            PlaybookStepRisk.CRITICAL,
            "endpoint.release",
        ),
        ("validate", PlaybookStepKind.VALIDATION, PlaybookStepRisk.LOW, None),
    ]
    steps = [
        WorkflowStepRun(
            id=uuid4(),
            workspace_id=workspace_id,
            workflow_id=workflow_id,
            position=position,
            step_key=key,
            name=key.title(),
            kind=kind,
            risk=risk,
            adapter=None if kind is PlaybookStepKind.APPROVAL else "adapter",
            operation=None if kind is PlaybookStepKind.APPROVAL else f"{key}.execute",
            timeout_seconds=300,
            max_attempts=3,
            rollback_strategy=(RollbackStrategy.COMPENSATE if rollback is not None else None),
            rollback_operation=rollback,
        )
        for position, (key, kind, risk, rollback) in enumerate(specs)
    ]
    return WorkflowRun(
        id=workflow_id,
        workspace_id=workspace_id,
        incident_id=uuid4(),
        playbook_id=uuid4(),
        playbook_version_id=uuid4(),
        playbook_version=1,
        definition_hash="a" * 64,
        status=WorkflowStatus.PENDING,
        version=1,
        created_by="analyst",
        created_at=now,
        updated_at=now,
        steps=steps,
    )
