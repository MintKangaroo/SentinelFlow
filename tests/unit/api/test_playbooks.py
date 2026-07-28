from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest

from sentinelflow.api import create_app
from sentinelflow.config import Settings
from sentinelflow.runtime import RuntimeResources
from tests.unit.api.test_incidents import FakeCache, write_headers


def valid_steps() -> list[dict[str, object]]:
    return [
        {
            "key": "approve",
            "name": "Approve isolation",
            "kind": "approval",
            "risk": "high",
            "parameters": {},
        },
        {
            "key": "isolate",
            "name": "Isolate endpoint",
            "kind": "action",
            "risk": "critical",
            "adapter": "patchtower",
            "operation": "endpoint.isolate",
            "parameters": {"target": "${incident.asset_id}"},
            "rollback": {
                "strategy": "compensate",
                "operation": "endpoint.release",
                "parameters": {"target": "${incident.asset_id}"},
            },
        },
    ]


@pytest.mark.asyncio
async def test_playbook_api_versions_publish_and_workspace_isolation(
    incident_runtime: Any,
) -> None:
    workspace_id = uuid4()
    other_workspace_id = uuid4()
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
            "/api/v1/playbooks",
            headers=write_headers(workspace_id, "api-playbook-create"),
            json={
                "name": "  Critical containment  ",
                "description": "Isolate and validate",
                "steps": valid_steps(),
            },
        )
        playbook_id = created.json()["playbook"]["id"]
        listed = await client.get(
            "/api/v1/playbooks?status=draft",
            headers={"X-Workspace-ID": str(workspace_id)},
        )
        revised = await client.post(
            f"/api/v1/playbooks/{playbook_id}/versions",
            headers=write_headers(workspace_id, "api-playbook-v2"),
            json={"expected_version": 1, "steps": valid_steps()},
        )
        published = await client.post(
            f"/api/v1/playbooks/{playbook_id}/versions/2/publish",
            headers=write_headers(workspace_id, "api-playbook-publish"),
            json={"expected_version": 2},
        )
        versions = await client.get(
            f"/api/v1/playbooks/{playbook_id}/versions",
            headers={"X-Workspace-ID": str(workspace_id)},
        )
        events = await client.get(
            f"/api/v1/playbooks/{playbook_id}/events",
            headers={"X-Workspace-ID": str(workspace_id)},
        )
        hidden = await client.get(
            f"/api/v1/playbooks/{playbook_id}",
            headers={"X-Workspace-ID": str(other_workspace_id)},
        )

    assert created.status_code == 201
    assert created.json()["playbook"]["name"] == "Critical containment"
    assert len(created.json()["revision"]["definition_hash"]) == 64
    assert len(listed.json()) == 1
    assert revised.json()["revision"]["number"] == 2
    assert published.json()["status"] == "active"
    assert published.json()["active_version"] == 2
    assert [version["number"] for version in versions.json()] == [2, 1]
    assert len(events.json()) == 3
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "playbook_not_found"


@pytest.mark.asyncio
async def test_playbook_api_rejects_unguarded_high_risk_action(
    incident_runtime: Any,
) -> None:
    workspace_id: UUID = uuid4()
    app = create_app(
        settings=Settings(environment="test", cors_origins=[]),
        resources=RuntimeResources(database=incident_runtime.database, cache=FakeCache()),
    )
    transport = httpx.ASGITransport(app=app)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        response = await client.post(
            "/api/v1/playbooks",
            headers=write_headers(workspace_id, "invalid-playbook"),
            json={
                "name": "Unsafe",
                "steps": [
                    {
                        "key": "isolate",
                        "name": "Isolate",
                        "kind": "action",
                        "risk": "critical",
                        "adapter": "patchtower",
                        "operation": "endpoint.isolate",
                    }
                ],
            },
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_playbook_definition"
