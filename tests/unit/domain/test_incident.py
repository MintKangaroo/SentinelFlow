from datetime import UTC, datetime
from uuid import uuid4

import pytest

from sentinelflow.domain import (
    Incident,
    IncidentSeverity,
    IncidentStatus,
    InvalidIncidentTransition,
)
from sentinelflow.domain.incident import ALLOWED_TRANSITIONS

NOW = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)


def make_incident(status: IncidentStatus = IncidentStatus.NEW) -> Incident:
    return Incident(
        id=uuid4(),
        workspace_id=uuid4(),
        title="Suspicious authentication",
        description="Multiple impossible-travel signals",
        severity=IncidentSeverity.HIGH,
        status=status,
        version=1,
        created_at=NOW,
        updated_at=NOW,
    )


@pytest.mark.parametrize(
    ("current", "target"),
    [(current, target) for current, targets in ALLOWED_TRANSITIONS.items() for target in targets],
)
def test_all_declared_lifecycle_edges_are_allowed(
    current: IncidentStatus, target: IncidentStatus
) -> None:
    incident = make_incident(current)

    previous = incident.transition(target, NOW)

    assert previous is current
    assert incident.status is target
    assert incident.version == 2


def test_undeclared_lifecycle_edge_is_rejected() -> None:
    incident = make_incident(IncidentStatus.NEW)

    with pytest.raises(InvalidIncidentTransition) as error:
        incident.transition(IncidentStatus.RESPONDING, NOW)

    assert error.value.current is IncidentStatus.NEW
    assert error.value.target is IncidentStatus.RESPONDING
    assert error.value.code == "invalid_incident_transition"


def test_resolve_close_and_reopen_manage_terminal_timestamps() -> None:
    incident = make_incident(IncidentStatus.VALIDATING)

    incident.transition(IncidentStatus.RESOLVED, NOW)
    assert incident.resolved_at == NOW

    incident.transition(IncidentStatus.CLOSED, NOW)
    assert incident.closed_at == NOW

    incident.transition(IncidentStatus.REOPENED, NOW)
    assert incident.resolved_at is None
    assert incident.closed_at is None


def test_timeline_entry_advances_aggregate_version() -> None:
    incident = make_incident()

    version = incident.record_timeline_entry(NOW)

    assert version == 2
    assert incident.version == 2
    assert incident.updated_at == NOW
