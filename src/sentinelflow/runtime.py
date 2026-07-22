"""Runtime resource definitions shared by HTTP endpoints."""

from dataclasses import dataclass
from typing import Protocol


class HealthDependency(Protocol):
    """A dependency that can report availability without returning sensitive data."""

    async def check(self) -> None: ...

    async def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class RuntimeResources:
    """Process-owned infrastructure dependencies."""

    database: HealthDependency
    cache: HealthDependency
