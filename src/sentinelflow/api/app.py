"""FastAPI application factory and process lifecycle."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from sentinelflow import __version__
from sentinelflow.api.approvals import router as approval_router
from sentinelflow.api.detections import router as detection_router
from sentinelflow.api.errors import install_error_handlers
from sentinelflow.api.health import router as health_router
from sentinelflow.api.incidents import router as incident_router
from sentinelflow.api.playbooks import router as playbook_router
from sentinelflow.api.reports import router as report_router
from sentinelflow.api.workflows import router as workflow_router
from sentinelflow.application import (
    ApprovalService,
    DetectionService,
    IncidentService,
    PlaybookService,
    WorkflowDispatchScheduler,
    WorkflowResultTokenSigner,
    WorkflowService,
)
from sentinelflow.config import Settings, get_settings
from sentinelflow.infrastructure import Database, RedisCache
from sentinelflow.observability import configure_telemetry
from sentinelflow.runtime import RuntimeResources


class ServiceInfo(BaseModel):
    """Public service metadata."""

    name: str
    version: str
    environment: str


def create_app(
    settings: Settings | None = None,
    resources: RuntimeResources | None = None,
    incident_service: IncidentService | None = None,
    playbook_service: PlaybookService | None = None,
    workflow_service: WorkflowService | None = None,
    approval_service: ApprovalService | None = None,
    detection_service: DetectionService | None = None,
    dispatch_scheduler: WorkflowDispatchScheduler | None = None,
    workflow_result_signer: WorkflowResultTokenSigner | None = None,
) -> FastAPI:
    """Build an isolated SentinelFlow API instance."""
    runtime_settings = settings or get_settings()
    owns_resources = resources is None
    runtime_resources = resources or RuntimeResources(
        database=Database(runtime_settings.database_url.get_secret_value()),
        cache=RedisCache(runtime_settings.redis_url.get_secret_value()),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.settings = runtime_settings
        app.state.resources = runtime_resources
        yield
        if owns_resources:
            await asyncio.gather(
                runtime_resources.database.close(),
                runtime_resources.cache.close(),
            )
        if app.state.tracer_provider is not None:
            app.state.tracer_provider.shutdown()

    app = FastAPI(
        title=runtime_settings.app_name,
        version=__version__,
        docs_url="/docs" if runtime_settings.environment != "production" else None,
        redoc_url=None,
        lifespan=lifespan,
    )
    app.state.incident_service = incident_service
    app.state.playbook_service = playbook_service
    app.state.workflow_service = workflow_service
    app.state.approval_service = approval_service
    app.state.detection_service = detection_service
    app.state.dispatch_scheduler = dispatch_scheduler
    app.state.workflow_result_signer = workflow_result_signer
    app.state.tracer_provider = configure_telemetry(app, runtime_settings)
    install_error_handlers(app)
    if runtime_settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=runtime_settings.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=[
                "Content-Type",
                "X-Request-ID",
                "X-Workspace-ID",
                "X-Actor-ID",
                "X-Actor-Role",
                "X-Workflow-Result-Token",
                "Idempotency-Key",
            ],
        )

    app.include_router(health_router, prefix=runtime_settings.api_prefix)
    app.include_router(incident_router, prefix=runtime_settings.api_prefix)
    app.include_router(playbook_router, prefix=runtime_settings.api_prefix)
    app.include_router(workflow_router, prefix=runtime_settings.api_prefix)
    app.include_router(approval_router, prefix=runtime_settings.api_prefix)
    app.include_router(detection_router, prefix=runtime_settings.api_prefix)
    app.include_router(report_router, prefix=runtime_settings.api_prefix)

    @app.get("/", response_model=ServiceInfo, tags=["system"])
    async def service_info() -> ServiceInfo:
        return ServiceInfo(
            name=runtime_settings.app_name,
            version=__version__,
            environment=runtime_settings.environment,
        )

    return app
