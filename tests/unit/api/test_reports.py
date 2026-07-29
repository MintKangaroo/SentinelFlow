from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from sentinelflow.api.reports import incident_report


@pytest.mark.asyncio
async def test_incident_report_contains_evidence_and_stable_digest() -> None:
    workspace = uuid4()
    incident_id = uuid4()
    incident = SimpleNamespace(id=incident_id, title="Credential theft")
    event = SimpleNamespace(
        sequence=1,
        event_type=SimpleNamespace(value="incident_created"),
        actor_id="ai-soc",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        data={"severity": "high"},
    )
    incident_service = SimpleNamespace(
        get=lambda **_: _value(incident),
        timeline=lambda **_: _value([event]),
    )
    approval_service = SimpleNamespace(list=lambda **_: _value([]))
    workflow_service = SimpleNamespace()
    first = await incident_report(
        incident_id, workspace, incident_service, approval_service, workflow_service
    )
    second = await incident_report(
        incident_id, workspace, incident_service, approval_service, workflow_service
    )
    assert first.summary == "Credential theft"
    assert first.timeline[0]["actor"] == "ai-soc"
    assert first.digest == second.digest


async def _value(value):
    return value
