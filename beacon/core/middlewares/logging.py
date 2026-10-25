import time
from collections.abc import Collection

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from beacon.core.logging import get_logger

logger = get_logger("beacon.access")


class AccessLogMiddleware:
    """Emits one structured line per request, with status and duration."""

    def __init__(self, app: ASGIApp, *, exclude_paths: Collection[str] = (), log_started: bool = False) -> None:
        self.app = app
        self.exclude_paths = frozenset(exclude_paths)
        self.log_started = log_started

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in self.exclude_paths:
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        log = logger.bind(
            method=scope["method"],
            path=scope["path"],
            client_ip=client[0] if client else None,
        )

        if self.log_started:
            log.info("request_started")

        status_code: int | None = None

        async def send_capturing_status(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        started = time.perf_counter()
        try:
            await self.app(scope, receive, send_capturing_status)
        except Exception as exc:
            log.error(  # noqa: TRY400 – traceback is logged once, by the exception handler
                "request_failed",
                exception_type=type(exc).__name__,
                duration_ms=_elapsed_ms(started),
            )
            raise

        log.info("request_completed", status_code=status_code, duration_ms=_elapsed_ms(started))


def _elapsed_ms(started: float) -> float:
    return round((time.perf_counter() - started) * 1000, 2)
