import pytest
from pydantic import ValidationError

from sentinelflow.config import Settings


def test_settings_normalize_api_prefix_and_redact_connections() -> None:
    settings = Settings(api_prefix="/control/")

    assert settings.api_prefix == "/control"
    assert str(settings.database_url) == "**********"
    assert str(settings.redis_url) == "**********"


def test_settings_accept_root_prefix() -> None:
    assert Settings(api_prefix="/").api_prefix == "/"


def test_settings_reject_relative_api_prefix() -> None:
    with pytest.raises(ValidationError, match="must start"):
        Settings(api_prefix="api")
