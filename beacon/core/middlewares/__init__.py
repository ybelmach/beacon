from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from beacon.core.config import get_settings
from beacon.core.health import PROBE_PATHS
from beacon.core.middlewares.errors import ProblemDetailsMiddleware
from beacon.core.middlewares.logging import AccessLogMiddleware
from beacon.core.middlewares.request_id import RequestIDMiddleware

__all__ = [
    "AccessLogMiddleware",
    "ProblemDetailsMiddleware",
    "RequestIDMiddleware",
    "setup_middlewares",
]


def setup_middlewares(app: FastAPI) -> None:
    """Wire the middleware stack.

    `add_middleware` prepends, so this reads inside-out: the resulting order on the way
    in is CORS -> RequestID -> AccessLog -> ProblemDetails -> router. ProblemDetails sits
    innermost so a crash is already a 500 response by the time AccessLog records it, and
    CORS sits outermost so even an error response carries the right headers.
    """
    settings = get_settings()

    app.add_middleware(ProblemDetailsMiddleware)
    app.add_middleware(
        AccessLogMiddleware,
        exclude_paths=PROBE_PATHS,
        log_started=settings.debug_mode,
    )
    app.add_middleware(RequestIDMiddleware)

    if settings.cors_origins:
        # Outermost on purpose: preflight is a browser-to-browser negotiation that never
        # reaches a route, so it gets no request id and no access-log line.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=settings.cors_allow_credentials,
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
            expose_headers=["X-Request-ID"],
        )
