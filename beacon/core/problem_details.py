from collections import deque
from collections.abc import Iterator, Mapping
from http import HTTPStatus

from fastapi import Request
from fastapi.responses import JSONResponse

from beacon.core.config import get_settings
from beacon.core.exceptions import AppError

PROBLEM_MEDIA_TYPE = "application/problem+json"


def _app_error_classes() -> Iterator[type[AppError]]:
    """Walk the AppError tree breadth-first, so the most generic class for a status comes first."""
    queue = deque([AppError])
    while queue:
        cls = queue.popleft()
        yield cls
        queue.extend(cls.__subclasses__())


def slug_for_status(status_code: int) -> str | None:
    """Reverse-index the exception hierarchy: each class stays the single source of its own slug."""
    for cls in _app_error_classes():
        if cls.status_code == status_code:
            return cls.slug
    return None


def title_for_status(status_code: int) -> str:
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "Error"


def problem_type(slug: str | None) -> str:
    if slug is None:
        return "about:blank"
    return f"{get_settings().base_url.rstrip('/')}/problems/{slug}"


def create_problem_response(
    request: Request,
    status_code: int,
    detail: str,
    slug: str | None = None,
    extensions: Mapping[str, object] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Create an RFC 9457 Problem Details response."""
    content: dict[str, object] = {
        "type": problem_type(slug),
        "title": title_for_status(status_code),
        "status": status_code,
        "detail": detail,
        "instance": request.url.path,
    }

    request_id = getattr(request.state, "request_id", None)
    if request_id is not None:
        content["request_id"] = request_id

    if extensions:
        content.update(extensions)

    return JSONResponse(
        status_code=status_code,
        content=content,
        headers=dict(headers) if headers else None,
        media_type=PROBLEM_MEDIA_TYPE,
    )
