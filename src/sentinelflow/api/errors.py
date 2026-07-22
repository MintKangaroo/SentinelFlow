"""Stable HTTP error envelope for incident domain failures."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from sentinelflow.domain import IncidentError, IncidentNotFound


class ErrorDetail(BaseModel):
    """Machine-readable error detail."""

    code: str
    message: str


class ErrorResponse(BaseModel):
    """Top-level API error envelope."""

    error: ErrorDetail


def install_error_handlers(app: FastAPI) -> None:
    """Register sanitized mappings from domain failures to HTTP responses."""

    @app.exception_handler(IncidentError)
    async def handle_incident_error(_request: Request, error: IncidentError) -> JSONResponse:
        status_code = (
            status.HTTP_404_NOT_FOUND
            if isinstance(error, IncidentNotFound)
            else status.HTTP_409_CONFLICT
        )
        response = ErrorResponse(error=ErrorDetail(code=error.code, message=str(error)))
        return JSONResponse(status_code=status_code, content=response.model_dump())
