from datetime import UTC, datetime
from uuid import uuid4

import pytest

from sentinelflow.domain import (
    ConditionOperator,
    InvalidPlaybookDefinition,
    Playbook,
    PlaybookArchived,
    PlaybookStatus,
    PlaybookStep,
    PlaybookStepKind,
    PlaybookStepRisk,
    PlaybookVersion,
    PlaybookVersionConflict,
    RollbackDefinition,
    RollbackStrategy,
    StepCondition,
)
from tests.unit.playbooks.helpers import low_risk_steps, safe_response_steps


def test_revision_hash_is_stable_and_sensitive_to_definition() -> None:
    now = datetime.now(UTC)
    workspace_id = uuid4()
    playbook_id = uuid4()
    first = PlaybookVersion.build(
        id=uuid4(),
        workspace_id=workspace_id,
        playbook_id=playbook_id,
        number=1,
        steps=safe_response_steps(),
        created_by="analyst",
        created_at=now,
    )
    replay = PlaybookVersion.build(
        id=uuid4(),
        workspace_id=workspace_id,
        playbook_id=playbook_id,
        number=1,
        steps=safe_response_steps(),
        created_by="analyst",
        created_at=now,
    )
    changed = PlaybookVersion.build(
        id=uuid4(),
        workspace_id=workspace_id,
        playbook_id=playbook_id,
        number=1,
        steps=low_risk_steps(),
        created_by="analyst",
        created_at=now,
    )

    assert first.definition_hash == replay.definition_hash
    assert first.definition_hash != changed.definition_hash
    assert len(first.definition_hash) == 64


@pytest.mark.parametrize(
    "steps,message",
    [
        (
            (
                PlaybookStep(
                    key="dangerous_action",
                    name="Dangerous action",
                    kind=PlaybookStepKind.ACTION,
                    risk=PlaybookStepRisk.CRITICAL,
                    adapter="patchtower",
                    operation="host.modify",
                    parameters={},
                ),
            ),
            "earlier approval",
        ),
        (
            (
                PlaybookStep(
                    key="approval",
                    name="Approval",
                    kind=PlaybookStepKind.APPROVAL,
                    risk=PlaybookStepRisk.HIGH,
                    adapter=None,
                    operation=None,
                    parameters={},
                ),
                PlaybookStep(
                    key="dangerous_action",
                    name="Dangerous action",
                    kind=PlaybookStepKind.ACTION,
                    risk=PlaybookStepRisk.CRITICAL,
                    adapter="patchtower",
                    operation="host.modify",
                    parameters={},
                ),
            ),
            "rollback",
        ),
    ],
)
def test_high_risk_actions_require_approval_and_rollback(
    steps: tuple[PlaybookStep, ...], message: str
) -> None:
    with pytest.raises(InvalidPlaybookDefinition, match=message):
        PlaybookVersion.build(
            id=uuid4(),
            workspace_id=uuid4(),
            playbook_id=uuid4(),
            number=1,
            steps=steps,
            created_by="analyst",
            created_at=datetime.now(UTC),
        )


def test_step_and_condition_reject_executable_or_unsafe_values() -> None:
    with pytest.raises(InvalidPlaybookDefinition, match="safe dotted"):
        StepCondition(
            field="incident.__class__",
            operator=ConditionOperator.EXISTS,
        )
    with pytest.raises(InvalidPlaybookDefinition, match="cannot include"):
        StepCondition(
            field="incident.severity",
            operator=ConditionOperator.EXISTS,
            value=True,
        )
    with pytest.raises(InvalidPlaybookDefinition, match="list"):
        StepCondition(
            field="incident.severity",
            operator=ConditionOperator.IN,
            value="critical",
        )
    with pytest.raises(InvalidPlaybookDefinition, match="Approval"):
        PlaybookStep(
            key="approve",
            name="Approve",
            kind=PlaybookStepKind.APPROVAL,
            risk=PlaybookStepRisk.LOW,
            adapter="unsafe",
            operation="execute",
            parameters={},
        )
    with pytest.raises(InvalidPlaybookDefinition, match="Only action"):
        PlaybookStep(
            key="validate",
            name="Validate",
            kind=PlaybookStepKind.VALIDATION,
            risk=PlaybookStepRisk.LOW,
            adapter="validator",
            operation="check",
            parameters={},
            rollback=RollbackDefinition(
                strategy=RollbackStrategy.RESTORE,
                operation="restore",
                parameters={},
            ),
        )


def test_playbook_aggregate_versions_publish_and_archive() -> None:
    now = datetime.now(UTC)
    playbook = Playbook(
        id=uuid4(),
        workspace_id=uuid4(),
        name="Contain endpoint",
        description="",
        status=PlaybookStatus.DRAFT,
        latest_version=1,
        active_version=None,
        version=1,
        created_at=now,
        updated_at=now,
    )

    previous, revision = playbook.create_revision(now, expected_version=1)
    assert (previous, revision, playbook.version) == (1, 2, 2)
    playbook.publish(1, now, expected_version=2)
    assert playbook.status is PlaybookStatus.ACTIVE
    assert playbook.active_version == 1
    playbook.archive(now, expected_version=3)
    assert playbook.archived_at == now

    with pytest.raises(PlaybookArchived):
        playbook.create_revision(now, expected_version=4)

    fresh = Playbook(
        id=uuid4(),
        workspace_id=uuid4(),
        name="Fresh",
        description="",
        status=PlaybookStatus.DRAFT,
        latest_version=1,
        active_version=None,
        version=1,
        created_at=now,
        updated_at=now,
    )
    with pytest.raises(PlaybookVersionConflict):
        fresh.publish(1, now, expected_version=9)
