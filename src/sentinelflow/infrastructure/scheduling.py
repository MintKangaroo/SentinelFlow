"""Celery scheduling adapter for workflow dispatch."""

from uuid import UUID

from celery import Celery


class CeleryWorkflowDispatchScheduler:
    """Enqueue one idempotent workflow-dispatch task."""

    def __init__(self, app: Celery) -> None:
        self._app = app

    async def schedule(self, workspace_id: UUID, workflow_id: UUID) -> None:
        self._app.send_task(
            "sentinelflow.dispatch_workflow",
            args=[str(workspace_id), str(workflow_id)],
        )
