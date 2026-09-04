from fastapi import status
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from beacon.core.logging import get_logger
from beacon.core.problem_details import create_problem_response

logger = get_logger(__name__)


class ProblemDetailsMiddleware:
    """Last line of defence: turns an unhandled exception into an RFC 7807 response.

    This has to be a middleware rather than an `Exception` handler. Starlette routes
    that handler to ServerErrorMiddleware, which always re-raises after responding so
    the server can log the crash – producing a second, unstructured traceback for every
    500. Terminating the exception here keeps exactly one structured record of it.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_tracking_start(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_tracking_start)
        except Exception as exc:
            logger.error(  # noqa: TRY400 – structlog takes the exception explicitly
                "unhandled_exception",
                exception_type=type(exc).__name__,
                path=scope["path"],
                exc_info=exc,
            )
            if response_started:
                # Status and headers are already on the wire; only the server can
                # end this exchange, so hand the exception back to it.
                raise
            response = create_problem_response(
                Request(scope),
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred",
                slug="internal-server-error",
            )
            await response(scope, receive, send)
