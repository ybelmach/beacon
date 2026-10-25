import uuid

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from beacon.core.middlewares.request_id import REQUEST_ID_HEADER, RequestIDMiddleware, resolve_request_id


def _echo_state(request: Request) -> PlainTextResponse:
    return PlainTextResponse(request.state.request_id)


@pytest.fixture
def client() -> TestClient:
    app = Starlette(routes=[Route("/", _echo_state)])
    app.add_middleware(RequestIDMiddleware)
    return TestClient(app)


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


@pytest.mark.parametrize("inbound", ["abc", "0f9c1e2a-7b1d-4c1e-9a3b-2f6d8e4c1a7b", "trace.1:span_2", "x" * 128])
def test_valid_inbound_id_is_kept(inbound: str) -> None:
    assert resolve_request_id(inbound) == inbound


@pytest.mark.parametrize(
    "inbound",
    [None, "", "x" * 129, "has space", "line\nbreak", '{"json":1}', "ünïcode", "a/b"],
)
def test_invalid_inbound_id_is_replaced(inbound: str | None) -> None:
    resolved = resolve_request_id(inbound)

    assert resolved != inbound
    assert _is_uuid(resolved)


def test_valid_id_is_echoed_and_exposed_to_the_app(client: TestClient) -> None:
    example_header = "abc-123"
    response = client.get("/", headers={REQUEST_ID_HEADER: example_header})

    assert response.headers[REQUEST_ID_HEADER] == example_header
    assert response.text == example_header


def test_oversized_id_is_not_echoed(client: TestClient) -> None:
    response = client.get("/", headers={REQUEST_ID_HEADER: "a" * 5000})

    echoed = response.headers[REQUEST_ID_HEADER]
    assert _is_uuid(echoed)
    assert response.text == echoed


def test_missing_id_is_generated(client: TestClient) -> None:
    response = client.get("/")

    assert _is_uuid(response.headers[REQUEST_ID_HEADER])
