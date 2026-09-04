import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from beacon.core.config import get_settings

_TESTS_DIR = Path(__file__).resolve().parent

# Settings resolve BEACON_ENV_FILE on every construction, so pointing it here keeps the
# developer's real .env out of the suite – otherwise log level, CORS and debug flags
# would differ between a laptop and CI. setdefault, so an explicit value still wins.
os.environ.setdefault("BEACON_ENV_FILE", str(_TESTS_DIR / ".env.test"))


@pytest.fixture(autouse=True)
def reset_settings_cache() -> Iterator[None]:
    """get_settings() is an lru_cache; without this one test's overrides leak into the next."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
