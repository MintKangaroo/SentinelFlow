"""FastAPI dependency wiring for application services."""

from typing import cast

from fastapi import Request

from sentinelflow.application import (
    ApprovalService,
    DetectionService,
    IncidentService,
    NoopWorkflowDispatchScheduler,
    PlaybookService,
    WorkflowDispatchScheduler,
    WorkflowResultTokenSigner,
    WorkflowService,
)
from sentinelflow.infrastructure import (
    CeleryWorkflowDispatchScheduler,
    Database,
    SQLAlchemyApprovalUnitOfWork,
    SQLAlchemyIncidentUnitOfWork,
    SQLAlchemyPlaybookUnitOfWork,
    SQLAlchemyWorkflowUnitOfWork,
)


def get_approval_service(request: Request) -> ApprovalService:
    """Return an injected service or lazily wire the approval adapter."""
    service = cast(ApprovalService | None, request.app.state.approval_service)
    if service is not None:
        return service
    database = request.app.state.resources.database
    if not isinstance(database, Database):
        raise RuntimeError("Approval service requires a database session factory")
    service = ApprovalService(lambda: SQLAlchemyApprovalUnitOfWork(database.session_factory))
    request.app.state.approval_service = service
    return service


def get_detection_service(request: Request) -> DetectionService:
    service = cast(DetectionService | None, request.app.state.detection_service)
    if service is None:
        service = DetectionService(
            get_incident_service(request),
            request.app.state.settings.aisoc_webhook_secret.get_secret_value(),
        )
        request.app.state.detection_service = service
    return service


def get_dispatch_scheduler(request: Request) -> WorkflowDispatchScheduler:
    """Return the injected scheduler or a runtime-appropriate Celery adapter."""
    scheduler = cast(
        WorkflowDispatchScheduler | None,
        request.app.state.dispatch_scheduler,
    )
    if scheduler is not None:
        return scheduler
    if request.app.state.settings.environment == "test":
        scheduler = NoopWorkflowDispatchScheduler()
    else:
        from sentinelflow.worker import celery_app

        scheduler = CeleryWorkflowDispatchScheduler(celery_app)
    request.app.state.dispatch_scheduler = scheduler
    return scheduler


def get_workflow_result_signer(request: Request) -> WorkflowResultTokenSigner:
    """Return the process-local verifier for scoped workflow callback tokens."""
    signer = cast(
        WorkflowResultTokenSigner | None,
        request.app.state.workflow_result_signer,
    )
    if signer is None:
        signer = WorkflowResultTokenSigner(
            request.app.state.settings.workflow_result_signing_key.get_secret_value()
        )
        request.app.state.workflow_result_signer = signer
    return signer


def get_incident_service(request: Request) -> IncidentService:
    """Return an injected service or lazily wire the SQLAlchemy adapter."""
    service = cast(IncidentService | None, request.app.state.incident_service)
    if service is not None:
        return service

    database = request.app.state.resources.database
    if not isinstance(database, Database):
        raise RuntimeError("Incident service requires a database session factory")
    service = IncidentService(lambda: SQLAlchemyIncidentUnitOfWork(database.session_factory))
    request.app.state.incident_service = service
    return service


def get_playbook_service(request: Request) -> PlaybookService:
    """Return an injected service or lazily wire the playbook adapter."""
    service = cast(PlaybookService | None, request.app.state.playbook_service)
    if service is not None:
        return service

    database = request.app.state.resources.database
    if not isinstance(database, Database):
        raise RuntimeError("Playbook service requires a database session factory")
    service = PlaybookService(lambda: SQLAlchemyPlaybookUnitOfWork(database.session_factory))
    request.app.state.playbook_service = service
    return service


def get_workflow_service(request: Request) -> WorkflowService:
    """Return an injected service or lazily wire the workflow adapter."""
    service = cast(WorkflowService | None, request.app.state.workflow_service)
    if service is not None:
        return service
    database = request.app.state.resources.database
    if not isinstance(database, Database):
        raise RuntimeError("Workflow service requires a database session factory")
    service = WorkflowService(lambda: SQLAlchemyWorkflowUnitOfWork(database.session_factory))
    request.app.state.workflow_service = service
    return service
