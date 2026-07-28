"""Test doubles shared by Integration Adapter SDK tests."""

from dataclasses import dataclass, field
from uuid import UUID

from pydantic import SecretStr

from sentinelflow.integrations import CredentialReference, CredentialResolutionError


@dataclass
class RecordingSecretManager:
    """Workspace-aware secret manager that records all resolution requests."""

    values: dict[tuple[UUID, UUID], str]
    calls: list[tuple[UUID, UUID]] = field(default_factory=list)

    async def resolve(
        self,
        *,
        workspace_id: UUID,
        reference: CredentialReference,
    ) -> SecretStr:
        self.calls.append((workspace_id, reference.reference_id))
        try:
            value = self.values[(workspace_id, reference.reference_id)]
        except KeyError as exc:
            raise CredentialResolutionError() from exc
        return SecretStr(value)


class RejectingSecretManager:
    """Secret manager used to prove that unauthenticated calls perform no lookup."""

    async def resolve(
        self,
        *,
        workspace_id: UUID,
        reference: CredentialReference,
    ) -> SecretStr:
        del workspace_id, reference
        raise AssertionError("secret resolution was not expected")


@dataclass
class FakeClock:
    """Monotonic clock controlled by a test."""

    now: float = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds
