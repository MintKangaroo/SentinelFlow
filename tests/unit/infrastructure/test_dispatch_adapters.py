from typing import Any, cast
from uuid import UUID

import pytest
from celery import Celery
from pydantic import SecretStr
from redis.asyncio import Redis

from sentinelflow.config import Settings
from sentinelflow.infrastructure import (
    CeleryWorkflowDispatchScheduler,
    DryRunWorkflowStepExecutor,
    RedisWorkflowLeaseManager,
    build_vendor_executor,
)
from sentinelflow.integrations import IntegrationConfigurationError
from tests.unit.workflows.helpers import workflow_run


class FakeRedis:
    def __init__(self) -> None:
        self.set_calls: list[tuple[Any, ...]] = []
        self.eval_calls: list[tuple[Any, ...]] = []

    async def set(self, *args: Any, **kwargs: Any) -> str:
        self.set_calls.append((*args, kwargs))
        return "OK"

    async def eval(self, *args: Any) -> int:
        self.eval_calls.append(args)
        return 1


class FakeCelery:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[str]]] = []

    def send_task(self, name: str, args: list[str]) -> None:
        self.calls.append((name, args))


@pytest.mark.asyncio
async def test_redis_lease_acquires_and_releases_only_by_owner() -> None:
    redis = FakeRedis()
    manager = RedisWorkflowLeaseManager(cast(Redis, redis))
    assert await manager.acquire("workflow:key", "owner", 60) is True
    await manager.release("workflow:key", "owner")
    assert redis.set_calls[0][0:2] == (
        "sentinelflow:lease:workflow:key",
        "owner",
    )
    assert redis.eval_calls[0][-2:] == (
        "sentinelflow:lease:workflow:key",
        "owner",
    )


@pytest.mark.asyncio
async def test_celery_scheduler_and_dry_run_executor_are_explicit() -> None:
    celery = FakeCelery()
    scheduler = CeleryWorkflowDispatchScheduler(cast(Celery, celery))
    workflow = workflow_run()
    await scheduler.schedule(workflow.workspace_id, workflow.id)
    assert celery.calls == [
        (
            "sentinelflow.dispatch_workflow",
            [str(workflow.workspace_id), str(workflow.id)],
        )
    ]

    executor = DryRunWorkflowStepExecutor()
    output = await executor.execute(
        workflow=workflow,
        step=workflow.steps[0],
        idempotency_key="dry-run",
    )
    rollback = await executor.compensate(
        workflow=workflow,
        step=workflow.steps[2],
        idempotency_key="dry-run-rollback",
    )
    assert output["external_side_effect"] is False
    assert output["mode"] == "dry_run"
    assert rollback["operation"] == "endpoint.release"


def test_vendor_runtime_fails_closed_and_builds_configured_registry() -> None:
    with pytest.raises(IntegrationConfigurationError):
        build_vendor_executor(Settings(environment="test"))
    workspace = UUID("11111111-1111-4111-8111-111111111111")
    with pytest.raises(IntegrationConfigurationError):
        build_vendor_executor(
            Settings(
                environment="test",
                integration_workspace_id=workspace,
                patchtower_base_url="https://patchtower.test",
            )
        )
    executor = build_vendor_executor(
        Settings(
            environment="test",
            integration_workspace_id=workspace,
            patchtower_base_url="https://patchtower.test",
            patchtower_token=SecretStr("token-value"),
        )
    )
    assert executor is not None
