import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from functools import partial
from typing import Literal

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from beacon.core.config import get_settings
from beacon.core.logging import get_logger

logger = get_logger(__name__)

PROBE_PATHS = frozenset({"/healthz", "/readyz"})

_UNCONFIGURED = "unconfigured"

router = APIRouter()


@dataclass(frozen=True, slots=True)
class ReadinessCheck:
    name: str
    # None when the lifespan never attached the resource – startup failed or was skipped.
    probe: Callable[[], Awaitable[None]] | None


class LivenessResponse(BaseModel):
    status: Literal["ok"]


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, str]


async def check_postgres(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))


async def check_redis(client: Redis) -> None:
    await client.ping()


def readiness_checks(request: Request) -> tuple[ReadinessCheck, ...]:
    """Resources are attached by the lifespan; a missing one is reported, never raised."""
    state = request.app.state
    engine: AsyncEngine | None = getattr(state, "engine", None)
    redis: Redis | None = getattr(state, "redis", None)

    return (
        ReadinessCheck("postgres", partial(check_postgres, engine) if engine is not None else None),
        ReadinessCheck("redis", partial(check_redis, redis) if redis is not None else None),
    )


async def _run_check(check: ReadinessCheck, timeout_seconds: float) -> tuple[str, str]:
    if check.probe is None:
        logger.warning("readiness_check_unconfigured", check=check.name)
        return check.name, _UNCONFIGURED

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
    checks = readiness_checks(request)
    timeout = get_settings().readiness_timeout_seconds
    results = await asyncio.gather(*(_run_check(check, timeout) for check in checks))

    outcomes = dict(results)
    ready = all(outcome == "ok" for outcome in outcomes.values())

    if not ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(status="ready" if ready else "not_ready", checks=outcomes)
