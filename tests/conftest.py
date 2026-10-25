import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from beacon.core.config import get_settings

_TESTS_DIR = Path(__file__).resolve().parent

os.environ.setdefault("BEACON_ENV_FILE", str(_TESTS_DIR / ".env.test"))


@pytest.fixture(autouse=True)
def reset_settings_cache() -> Iterator[None]:
    """get_settings() is an lru_cache"""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
