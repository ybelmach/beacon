from collections.abc import Iterator

import pytest
import structlog
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient
from structlog.typing import EventDict

from beacon.core.middlewares.logging import AccessLogMiddleware


def _ok(_request: object) -> PlainTextResponse:
    return PlainTextResponse("ok")


@pytest.fixture
def captured() -> Iterator[list[EventDict]]:
    structlog.reset_defaults()
    with structlog.testing.capture_logs() as logs:
        yield logs
    structlog.reset_defaults()


def test_query_string_is_not_logged(captured: list[EventDict]) -> None:
    app = Starlette(routes=[Route("/items", _ok)])
    app.add_middleware(AccessLogMiddleware)

    TestClient(app).get("/items", params={"token": "s3cr3t"})

    [entry] = [e for e in captured if e["event"] == "request_completed"]
    assert entry["path"] == "/items"
    assert entry["status_code"] == 200
    assert "query" not in entry
    assert "s3cr3t" not in repr(captured)
