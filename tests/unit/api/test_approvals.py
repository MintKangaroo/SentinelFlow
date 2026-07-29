from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

import httpx
import pytest

from sentinelflow.api import create_app
from sentinelflow.application import PlaybookService
from sentinelflow.config import Settings
from sentinelflow.infrastructure import SQLAlchemyPlaybookUnitOfWork
from sentinelflow.runtime import RuntimeResources
from tests.unit.api.test_incidents import FakeCache, write_headers
from tests.unit.approvals.test_service import waiting_workflow
from tests.unit.conftest import AdvancingClock
from tests.unit.playbooks.helpers import safe_response_steps


@pytest.mark.asyncio
async def test_approval_api_enforces_two_person_quorum(incident_runtime: Any) -> None:
    workspace_id = uuid4()
    playbooks = PlaybookService(
        lambda: SQLAlchemyPlaybookUnitOfWork(incident_runtime.database.session_factory),
        clock=AdvancingClock(),
    )
    playbook, _ = await playbooks.create(
        workspace_id=workspace_id,
        name="API approval",
        description="",
        steps=safe_response_steps(),
        actor_id="author",
        idempotency_key="api-approval-playbook",
    )
    incident, workflow = await waiting_workflow(
        incident_runtime,
        workspace_id=workspace_id,
        playbook_id=playbook.id,
        suffix="api",
    )
    app = create_app(
        settings=Settings(environment="test", cors_origins=[]),
        resources=RuntimeResources(database=incident_runtime.database, cache=FakeCache()),
    )
    transport = httpx.ASGITransport(app=app)
    expiration = datetime.now(UTC) + timedelta(hours=1)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        invalid = await client.post(
            "/api/v1/approvals",
            headers=write_headers(workspace_id, "api-approval-invalid"),
            json={
                "incident_id": str(incident.id),
                "workflow_id": str(workflow.id),
                "step_key": "approve_isolation",
                "action_summary": "Isolate endpoint",
                "risk": "critical",
                "required_approvals": 1,
                "eligible_roles": ["soc_lead"],
                "expires_at": expiration.isoformat(),
            },
        )
        created = await client.post(
            "/api/v1/approvals",
            headers=write_headers(workspace_id, "api-approval-create"),
            json={
                "incident_id": str(incident.id),
                "workflow_id": str(workflow.id),
                "step_key": "approve_isolation",
                "action_summary": "Isolate endpoint and revoke sessions",
                "risk": "critical",
                "required_approvals": 2,
                "eligible_roles": ["soc_lead", "incident_commander"],
                "expires_at": expiration.isoformat(),
            },
        )
        approval_id = created.json()["id"]
        first_headers = write_headers(workspace_id, "api-approval-first")
        first_headers.update(
            {
                "X-Actor-ID": "lead@example.com",
                "X-Actor-Role": "soc_lead",
            }
        )
        first = await client.post(
            f"/api/v1/approvals/{approval_id}/decisions",
            headers=first_headers,
            json={
                "expected_version": 1,
                "decision": "approve",
                "reason": "Scope reviewed",
            },
        )
        second_headers = write_headers(workspace_id, "api-approval-second")
        second_headers.update(
            {
                "X-Actor-ID": "commander@example.com",
                "X-Actor-Role": "incident_commander",
            }
        )
        second = await client.post(
            f"/api/v1/approvals/{approval_id}/decisions",
            headers=second_headers,
            json={
                "expected_version": 2,
                "decision": "approve",
                "reason": "Evidence reviewed",
            },
        )
        events = await client.get(
            f"/api/v1/approvals/{approval_id}/events",
            headers={"X-Workspace-ID": str(workspace_id)},
        )

    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "invalid_approval_policy"
    assert created.status_code == 201
    assert first.json()["status"] == "pending"
    assert first.json()["approval_count"] == 1
    assert second.json()["status"] == "approved"
    assert second.json()["approval_count"] == 2
    assert [event["sequence"] for event in events.json()] == [1, 2, 3]
