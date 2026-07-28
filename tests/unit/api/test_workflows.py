from typing import Any
from uuid import uuid4

import httpx
import pytest

from sentinelflow.api import create_app
from sentinelflow.application import PlaybookService
from sentinelflow.config import Settings
from sentinelflow.domain import IncidentSeverity
from sentinelflow.infrastructure import SQLAlchemyPlaybookUnitOfWork
from sentinelflow.runtime import RuntimeResources
from tests.unit.api.test_incidents import FakeCache, write_headers
from tests.unit.conftest import AdvancingClock
from tests.unit.playbooks.helpers import safe_response_steps


@pytest.mark.asyncio
async def test_workflow_api_create_start_result_and_approval(incident_runtime: Any) -> None:
    workspace_id = uuid4()
    incident = await incident_runtime.service.create(
        workspace_id=workspace_id,
        title="API workflow",
        description="",
        severity=IncidentSeverity.HIGH,
        actor_id="detector",
        idempotency_key="api-workflow-incident",
    )
    playbook_service = PlaybookService(
        lambda: SQLAlchemyPlaybookUnitOfWork(incident_runtime.database.session_factory),
        clock=AdvancingClock(),
    )
    playbook, _ = await playbook_service.create(
        workspace_id=workspace_id,
        name="API containment",
        description="",
        steps=safe_response_steps(),
        actor_id="author",
        idempotency_key="api-workflow-playbook",
    )
    app = create_app(
        settings=Settings(environment="test", cors_origins=[]),
        resources=RuntimeResources(database=incident_runtime.database, cache=FakeCache()),
    )
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        created = await client.post(
            "/api/v1/workflows",
            headers=write_headers(workspace_id, "api-workflow-create"),
            json={
                "incident_id": str(incident.id),
                "playbook_id": str(playbook.id),
                "playbook_version": 1,
            },
        )
        workflow_id = created.json()["id"]
        started = await client.post(
            f"/api/v1/workflows/{workflow_id}/start",
            headers=write_headers(workspace_id, "api-workflow-start"),
            json={"expected_version": 1},
        )
        enriched = await client.post(
            f"/api/v1/workflows/{workflow_id}/steps/enrich_asset/result",
            headers=write_headers(workspace_id, "api-workflow-enrich"),
            json={
                "expected_version": 2,
                "succeeded": True,
                "output": {"asset": "host-1"},
            },
        )
        approved = await client.post(
            f"/api/v1/workflows/{workflow_id}/steps/approve_isolation/approval",
            headers=write_headers(workspace_id, "api-workflow-approve"),
            json={"expected_version": 3, "approved": True},
        )
        events = await client.get(
            f"/api/v1/workflows/{workflow_id}/events",
            headers={"X-Workspace-ID": str(workspace_id)},
        )

    assert created.status_code == 201
    assert created.json()["definition_hash"]
    assert started.json()["steps"][0]["status"] == "running"
    assert enriched.json()["status"] == "awaiting_approval"
    assert approved.json()["steps"][2]["status"] == "running"
    assert [event["sequence"] for event in events.json()] == [1, 2, 3, 4]
