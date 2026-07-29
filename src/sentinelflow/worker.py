"""Celery worker bootstrap and recoverable workflow dispatch task."""

import asyncio
from uuid import UUID

from celery import Celery

from sentinelflow.application import ApprovalService, WorkflowDispatcher, WorkflowService
from sentinelflow.config import Settings, get_settings
from sentinelflow.infrastructure import (
    Database,
    DryRunWorkflowStepExecutor,
    RedisCache,
    RedisWorkflowLeaseManager,
    SQLAlchemyApprovalUnitOfWork,
    SQLAlchemyWorkflowUnitOfWork,
    build_vendor_executor,
)


def create_celery_app(settings: Settings | None = None) -> Celery:
    """Create a JSON-only worker configured for reliable startup."""
    runtime_settings = settings or get_settings()
    redis_url = runtime_settings.redis_url.get_secret_value()
    app = Celery("sentinelflow", broker=redis_url, backend=redis_url)
    app.conf.update(
        accept_content=["json"],
        broker_connection_retry_on_startup=True,
        enable_utc=True,
        result_serializer="json",
        task_serializer="json",
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        task_track_started=True,
        timezone="UTC",
        worker_prefetch_multiplier=1,
        worker_hijack_root_logger=False,
    )
    return app


celery_app = create_celery_app()


async def _dispatch_workflow(workspace_id: UUID, workflow_id: UUID) -> dict[str, object]:
    settings = get_settings()
    database = Database(settings.database_url.get_secret_value())
    cache = RedisCache(settings.redis_url.get_secret_value())
    try:
        workflows = WorkflowService(lambda: SQLAlchemyWorkflowUnitOfWork(database.session_factory))
        approvals = ApprovalService(lambda: SQLAlchemyApprovalUnitOfWork(database.session_factory))
        executor = (
            DryRunWorkflowStepExecutor()
            if settings.workflow_execution_mode == "dry_run"
            else build_vendor_executor(settings)
        )
        dispatcher = WorkflowDispatcher(
            workflows,
            approvals,
            executor,
            RedisWorkflowLeaseManager(cache.client),
            lease_seconds=settings.workflow_dispatch_lease_seconds,
        )
        result = await dispatcher.dispatch(workspace_id, workflow_id)
        return {
            "workflow_id": str(result.workflow.id),
            "status": result.workflow.status.value,
            "transitions": result.transitions,
            "blocked_reason": result.blocked_reason,
        }
    finally:
        if "executor" in locals() and hasattr(executor, "aclose"):
            await executor.aclose()
        await database.close()
        await cache.close()


@celery_app.task(  # type: ignore[untyped-decorator]
    name="sentinelflow.dispatch_workflow",
    autoretry_for=(ConnectionError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def dispatch_workflow(workspace_id: str, workflow_id: str) -> dict[str, object]:
    """Advance a workflow with durable transitions and an ephemeral delivery lease."""
    return asyncio.run(_dispatch_workflow(UUID(workspace_id), UUID(workflow_id)))
