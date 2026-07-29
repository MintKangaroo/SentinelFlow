"""Stable HTTP error envelopes for safely reportable domain failures."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from sentinelflow.domain import (
    ApprovalDependencyNotFound,
    ApprovalError,
    ApprovalNotFound,
    IncidentError,
    IncidentNotFound,
    InvalidApprovalPolicy,
    InvalidPlaybookDefinition,
    InvalidWorkflowResultToken,
    PlaybookError,
    PlaybookNotFound,
    PlaybookVersionNotFound,
    WorkflowDependencyNotFound,
    WorkflowError,
    WorkflowNotFound,
)


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

    @app.exception_handler(ApprovalError)
    async def handle_approval_error(_request: Request, error: ApprovalError) -> JSONResponse:
        if isinstance(error, (ApprovalNotFound, ApprovalDependencyNotFound)):
            status_code = status.HTTP_404_NOT_FOUND
        elif isinstance(error, InvalidApprovalPolicy):
            status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
        else:
            status_code = status.HTTP_409_CONFLICT
        response = ErrorResponse(error=ErrorDetail(code=error.code, message=str(error)))
        return JSONResponse(status_code=status_code, content=response.model_dump())

    @app.exception_handler(PlaybookError)
    async def handle_playbook_error(_request: Request, error: PlaybookError) -> JSONResponse:
        if isinstance(error, (PlaybookNotFound, PlaybookVersionNotFound)):
            status_code = status.HTTP_404_NOT_FOUND
        elif isinstance(error, InvalidPlaybookDefinition):
            status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
        else:
            status_code = status.HTTP_409_CONFLICT
        response = ErrorResponse(error=ErrorDetail(code=error.code, message=str(error)))
        return JSONResponse(status_code=status_code, content=response.model_dump())

    @app.exception_handler(WorkflowError)
    async def handle_workflow_error(_request: Request, error: WorkflowError) -> JSONResponse:
        if isinstance(error, (WorkflowNotFound, WorkflowDependencyNotFound)):
            status_code = status.HTTP_404_NOT_FOUND
        elif isinstance(error, InvalidWorkflowResultToken):
            status_code = status.HTTP_401_UNAUTHORIZED
        else:
            status_code = status.HTTP_409_CONFLICT
        response = ErrorResponse(error=ErrorDetail(code=error.code, message=str(error)))
        return JSONResponse(status_code=status_code, content=response.model_dump())
