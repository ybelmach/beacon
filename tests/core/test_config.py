from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from beacon.core.config import Settings

_ENV_TEST = Path(__file__).resolve().parents[1] / ".env.test"
_STRONG_KEY = "a" * 32


def make_settings(**overrides: Any) -> Settings:
    return Settings(_env_file=_ENV_TEST, **overrides)  # pyright: ignore[reportCallIssue]


@pytest.mark.parametrize("environment", ["local", "test"])
def test_weak_secret_key_is_allowed_in_throwaway_environments(environment: str) -> None:
    settings = make_settings(environment=environment, secret_key="change-me")

    assert settings.secret_key.get_secret_value() == "change-me"


@pytest.mark.parametrize("environment", ["dev", "staging", "production"])
@pytest.mark.parametrize("secret_key", ["change-me", "CHANGE-ME", "test-secret-key", "short-but-not-a-placeholder"])
def test_weak_secret_key_is_rejected_elsewhere(environment: str, secret_key: str) -> None:
    with pytest.raises(ValidationError, match="secret_key must be a random value"):
        make_settings(environment=environment, secret_key=secret_key)


def test_strong_secret_key_is_accepted_in_production() -> None:
    settings = make_settings(environment="production", secret_key=_STRONG_KEY)

    assert settings.secret_key.get_secret_value() == _STRONG_KEY


def test_secret_key_is_masked_in_repr() -> None:
    settings = make_settings(environment="production", secret_key=_STRONG_KEY)

    assert _STRONG_KEY not in repr(settings)


def test_unknown_environment_is_rejected() -> None:
    with pytest.raises(ValidationError, match="environment"):
        make_settings(environment="prod")
