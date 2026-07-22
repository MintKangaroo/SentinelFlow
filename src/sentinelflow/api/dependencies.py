"""FastAPI dependency wiring for application services."""

from typing import cast

from fastapi import Request

from sentinelflow.application import IncidentService
from sentinelflow.infrastructure import Database, SQLAlchemyIncidentUnitOfWork


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
