"""Kubernetes- and Compose-compatible health endpoints."""

import asyncio
from typing import Literal

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from sentinelflow.runtime import HealthDependency, RuntimeResources

router = APIRouter(prefix="/health", tags=["health"])


class LivenessResponse(BaseModel):
    """Stable liveness response schema."""

    status: Literal["ok"] = "ok"


class ReadinessResponse(BaseModel):
    """Dependency readiness without exception or credential disclosure."""

    status: Literal["ready", "not_ready"]
    checks: dict[str, Literal["ok", "error"]]


async def _check_dependency(
    dependency: HealthDependency, timeout_seconds: float
) -> Literal["ok", "error"]:
    try:
        await asyncio.wait_for(dependency.check(), timeout=timeout_seconds)
    except Exception:
        return "error"
    return "ok"


@router.get("/live", response_model=LivenessResponse)
async def liveness() -> LivenessResponse:
    """Report whether the API process can serve requests."""
    return LivenessResponse()


@router.get("/ready", response_model=ReadinessResponse)
async def readiness(request: Request) -> ReadinessResponse | JSONResponse:
    """Report database and cache availability."""
    resources: RuntimeResources = request.app.state.resources
    timeout_seconds: float = request.app.state.settings.dependency_timeout_seconds
    database, cache = await asyncio.gather(
        _check_dependency(resources.database, timeout_seconds),
        _check_dependency(resources.cache, timeout_seconds),
    )
    response = ReadinessResponse(
        status="ready" if database == cache == "ok" else "not_ready",
        checks={"database": database, "redis": cache},
    )
    if response.status == "not_ready":
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=response.model_dump(),
        )
    return response
