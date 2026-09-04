import logging
import sys
from functools import partial
from types import TracebackType

import structlog
from structlog.processors import CallsiteParameter
from structlog.types import EventDict, Processor, WrappedLogger

from beacon.core.config import Settings, get_settings

_MANAGED_LOGGERS = (
    "uvicorn",
    "uvicorn.error",
    "sqlalchemy",
    "aiokafka",
    "asyncio",
)

_QUIET_LOGGERS = ("sqlalchemy.engine", "aiokafka.consumer.group_coordinator")


def _add_service_context(
    service: str,
    env: str,
    _logger: WrappedLogger,
    _method_name: str,
    event_dict: EventDict,
) -> EventDict:
    """Stamp every line with who emitted it – the same code runs as api, consumer and simulator.

    Bound to its values once via `partial` at setup: this runs on every single record.
    """
    event_dict.setdefault("service", service)
    event_dict.setdefault("env", env)
    return event_dict


def _drop_color_message(_logger: WrappedLogger, _method_name: str, event_dict: EventDict) -> EventDict:
    """uvicorn duplicates every message under `color_message`; drop the copy."""
    event_dict.pop("color_message", None)
    return event_dict


def _shared_processors(settings: Settings) -> list[Processor]:
    """Processors applied to structlog and stdlib records alike."""
    processors: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        partial(_add_service_context, settings.service_name, settings.environment),
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
    ]

    if settings.debug_mode:
        processors.append(
            structlog.processors.CallsiteParameterAdder(
                {CallsiteParameter.FILENAME, CallsiteParameter.LINENO},
            )
        )

    return processors


def _renderers(settings: Settings) -> list[Processor]:
    if settings.log_format == "console":
        return [structlog.dev.ConsoleRenderer(colors=True)]

    return [
        structlog.processors.ExceptionRenderer(
            structlog.tracebacks.ExceptionDictTransformer(show_locals=False),
        ),
        structlog.processors.JSONRenderer(),
    ]


def setup_logging() -> None:
    """Configure structlog and stdlib logging. Idempotent; call once at process start."""
    settings = get_settings()
    shared = _shared_processors(settings)

    structlog.configure(
        processors=[
            *shared,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=[*shared, structlog.stdlib.ExtraAdder(), _drop_color_message],
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            *_renderers(settings),
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    for existing in root.handlers[:]:
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(logging.getLevelNamesMapping()[settings.log_level])

    for name in _MANAGED_LOGGERS:
        managed = logging.getLogger(name)
        managed.handlers.clear()
        managed.propagate = True

    access_logger = logging.getLogger("uvicorn.access")
    access_logger.handlers.clear()
    access_logger.disabled = True

    if not settings.debug_mode:
        for name in _QUIET_LOGGERS:
            logging.getLogger(name).setLevel(logging.WARNING)

    _install_excepthooks()


def _install_excepthooks() -> None:
    """Route crashes through the same pipeline — consumers die outside any request."""

    def handle_exception(
        exc_type: type[BaseException],
        exc_value: BaseException,
        exc_traceback: TracebackType | None,
    ) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        get_logger("beacon.crash").critical(
            "uncaught_exception",
            exc_info=(exc_type, exc_value, exc_traceback),
        )

    sys.excepthook = handle_exception


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
