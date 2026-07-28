import base64
from uuid import uuid4

import pytest

from sentinelflow.integrations import (
    APIKeyAuthentication,
    BasicAuthentication,
    BearerTokenAuthentication,
    CredentialReference,
    CredentialResolutionError,
    IntegrationConfigurationError,
    NoAuthentication,
)
from tests.unit.integrations.helpers import RecordingSecretManager, RejectingSecretManager


@pytest.mark.asyncio
async def test_bearer_auth_resolves_secret_in_workspace_scope() -> None:
    workspace_id = uuid4()
    reference = CredentialReference(uuid4())
    manager = RecordingSecretManager({(workspace_id, reference.reference_id): "token-value"})

    headers = await BearerTokenAuthentication(reference).headers(
        secret_manager=manager,
        workspace_id=workspace_id,
    )

    assert headers == {"Authorization": "Bearer token-value"}
    assert manager.calls == [(workspace_id, reference.reference_id)]


@pytest.mark.asyncio
async def test_api_key_and_basic_auth_materialize_only_headers() -> None:
    workspace_id = uuid4()
    api_key = CredentialReference(uuid4())
    username = CredentialReference(uuid4())
    password = CredentialReference(uuid4())
    manager = RecordingSecretManager(
        {
            (workspace_id, api_key.reference_id): "api-secret",
            (workspace_id, username.reference_id): "operator",
            (workspace_id, password.reference_id): "password",
        }
    )

    api_headers = await APIKeyAuthentication(api_key, "X-Service-Key").headers(
        secret_manager=manager,
        workspace_id=workspace_id,
    )
    basic_headers = await BasicAuthentication(username, password).headers(
        secret_manager=manager,
        workspace_id=workspace_id,
    )

    encoded = base64.b64encode(b"operator:password").decode("ascii")
    assert api_headers == {"X-Service-Key": "api-secret"}
    assert basic_headers == {"Authorization": f"Basic {encoded}"}


@pytest.mark.asyncio
async def test_no_authentication_does_not_resolve_a_secret() -> None:
    headers = await NoAuthentication().headers(
        secret_manager=RejectingSecretManager(),
        workspace_id=uuid4(),
    )

    assert headers == {}


@pytest.mark.asyncio
async def test_resolution_errors_do_not_disclose_reference_or_provider_error() -> None:
    workspace_id = uuid4()
    reference = CredentialReference(uuid4())
    manager = RecordingSecretManager({})

    with pytest.raises(CredentialResolutionError) as captured:
        await BearerTokenAuthentication(reference).headers(
            secret_manager=manager,
            workspace_id=workspace_id,
        )

    assert str(reference.reference_id) not in str(captured.value)


@pytest.mark.parametrize(
    ("factory", "message"),
    [
        (lambda: BearerTokenAuthentication(CredentialReference(uuid4()), "bad scheme!"), "scheme"),
        (lambda: APIKeyAuthentication(CredentialReference(uuid4()), "Bad\nHeader"), "header"),
    ],
)
def test_auth_configuration_rejects_header_injection(factory: object, message: str) -> None:
    with pytest.raises(IntegrationConfigurationError, match=message):
        factory()  # type: ignore[operator]
