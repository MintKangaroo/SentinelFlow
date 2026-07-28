"""FastAPI dependency wiring for application services."""

from typing import cast

from fastapi import Request

from sentinelflow.application import IncidentService, PlaybookService, WorkflowService
from sentinelflow.infrastructure import (
    Database,
    SQLAlchemyIncidentUnitOfWork,
    SQLAlchemyPlaybookUnitOfWork,
    SQLAlchemyWorkflowUnitOfWork,
)


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
