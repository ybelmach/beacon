import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Literal

from fastapi import APIRouter, FastAPI, Request, Response, status
from pydantic import BaseModel

from beacon.core.config import get_settings
from beacon.core.logging import get_logger

logger = get_logger(__name__)

PROBE_PATHS = frozenset({"/healthz", "/readyz"})

router = APIRouter()


@dataclass(frozen=True, slots=True)
class ReadinessCheck:
    name: str
    probe: Callable[[], Awaitable[None]]


class LivenessResponse(BaseModel):
    status: Literal["ok"]


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, str]


def register_readiness_checks(app: FastAPI, checks: Sequence[ReadinessCheck]) -> None:
    """Called by the entrypoint once its resources exist."""
    app.state.readiness_checks = tuple(checks)


def _registered_checks(request: Request) -> tuple[ReadinessCheck, ...] | None:
    return getattr(request.app.state, "readiness_checks", None)


async def _run_check(check: ReadinessCheck, timeout_seconds: float) -> tuple[str, str]:
    try:
        async with asyncio.timeout(timeout_seconds):
            await check.probe()
    except TimeoutError:
        logger.warning("readiness_check_timeout", check=check.name, timeout=timeout_seconds)
        return check.name, "timeout"
    except Exception as exc:  # noqa: BLE001 – a readiness probe reports, not fails
        logger.warning("readiness_check_failed", check=check.name, error=type(exc).__name__)
        return check.name, f"error: {type(exc).__name__}"

    return check.name, "ok"


@router.get(
    "/healthz",
    summary="Liveness probe",
    response_model=LivenessResponse,
    include_in_schema=False,
)
async def healthz() -> LivenessResponse:
    return LivenessResponse(status="ok")


@router.get(
    "/readyz",
    summary="Readiness probe",
    response_model=ReadinessResponse,
    include_in_schema=False,
)
async def readyz(request: Request, response: Response) -> ReadinessResponse:
    checks = _registered_checks(request)
    if checks is None:
        logger.warning("readiness_checks_not_registered")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadinessResponse(status="not_ready", checks={})

    timeout = get_settings().readiness_timeout_seconds
    results = await asyncio.gather(*(_run_check(check, timeout) for check in checks))

    outcomes = dict(results)
    ready = all(outcome == "ok" for outcome in outcomes.values())

    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(status="ready" if ready else "not_ready", checks=outcomes)
