from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest

from sentinelflow.api import create_app
from sentinelflow.config import Settings
from sentinelflow.runtime import RuntimeResources


class FakeCache:
    async def check(self) -> None:
        return None

    async def close(self) -> None:
        return None


def write_headers(workspace_id: UUID, key: str) -> dict[str, str]:
    return {
        "X-Workspace-ID": str(workspace_id),
        "X-Actor-ID": "analyst@example.com",
        "Idempotency-Key": key,
    }


@pytest.mark.asyncio
async def test_incident_api_lifecycle_timeline_and_workspace_isolation(
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
        missing_headers = await client.post(
            "/api/v1/incidents",
            json={"title": "Missing headers", "severity": "high"},
        )
        created = await client.post(
            "/api/v1/incidents",
            headers=write_headers(workspace_id, "api-create"),
            json={
                "title": "  Suspicious login  ",
                "description": "Impossible travel",
                "severity": "high",
            },
        )
        incident_id = created.json()["id"]
        listed = await client.get(
            "/api/v1/incidents?status=new",
            headers={"X-Workspace-ID": str(workspace_id)},
        )
        transitioned = await client.post(
            f"/api/v1/incidents/{incident_id}/transitions",
            headers=write_headers(workspace_id, "api-transition"),
            json={
                "target_status": "triaging",
                "reason": "  Assigned to analyst  ",
                "expected_version": 1,
            },
        )
        note = await client.post(
            f"/api/v1/incidents/{incident_id}/notes",
            headers=write_headers(workspace_id, "api-note"),
            json={"body": "  Identity logs preserved  ", "expected_version": 2},
        )
        timeline = await client.get(
            f"/api/v1/incidents/{incident_id}/timeline?after_sequence=0",
            headers={"X-Workspace-ID": str(workspace_id)},
        )
        hidden = await client.get(
            f"/api/v1/incidents/{incident_id}",
            headers={"X-Workspace-ID": str(other_workspace_id)},
        )
        invalid = await client.post(
            f"/api/v1/incidents/{incident_id}/transitions",
            headers=write_headers(workspace_id, "api-invalid"),
            json={
                "target_status": "responding",
                "reason": "Skip states",
                "expected_version": 3,
            },
        )

    assert missing_headers.status_code == 422
    assert created.status_code == 201
    assert created.json()["title"] == "Suspicious login"
    assert created.json()["workspace_id"] == str(workspace_id)
    assert len(listed.json()) == 1
    assert transitioned.status_code == 200
    assert transitioned.json()["status"] == "triaging"
    assert transitioned.json()["version"] == 2
    assert note.status_code == 201
    assert note.json()["data"] == {"body": "Identity logs preserved"}
    assert [event["event_type"] for event in timeline.json()] == [
        "incident_created",
        "status_changed",
        "note_added",
    ]
    assert hidden.status_code == 404
    assert hidden.json()["error"]["code"] == "incident_not_found"
    assert invalid.status_code == 409
    assert invalid.json()["error"]["code"] == "invalid_incident_transition"


@pytest.mark.asyncio
async def test_incident_api_validates_blank_content(incident_runtime: Any) -> None:
    workspace_id = uuid4()
    app = create_app(
        settings=Settings(environment="test", cors_origins=[]),
        resources=RuntimeResources(database=incident_runtime.database, cache=FakeCache()),
        incident_service=incident_runtime.service,
    )
    transport = httpx.ASGITransport(app=app)

    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        response = await client.post(
            "/api/v1/incidents",
            headers=write_headers(workspace_id, "blank-title"),
            json={"title": "   ", "severity": "low"},
        )

    assert response.status_code == 422
