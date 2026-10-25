from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import partial

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse
from scalar_fastapi import get_scalar_api_reference

from beacon.core import health
from beacon.core.config import get_settings
from beacon.core.exception_handlers import register_exception_handlers
from beacon.core.health import ReadinessCheck, register_readiness_checks
from beacon.core.logging import get_logger, setup_logging
from beacon.core.middlewares import setup_middlewares
from beacon.infrastructure.postgres.session import ping_postgres
from beacon.infrastructure.redis.client import ping_redis
from beacon.infrastructure.resources import Resources, build_resources

OPENAPI_URL = "/openapi.json"

logger = get_logger(__name__)

docs_router = APIRouter(include_in_schema=False)


def readiness_checks(resources: Resources) -> tuple[ReadinessCheck, ...]:
    return (
        ReadinessCheck("postgres", partial(ping_postgres, resources.engine)),
        ReadinessCheck("redis", partial(ping_redis, resources.redis)),
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()

    async with build_resources(settings) as resources:
        app.state.resources = resources
        register_readiness_checks(app, readiness_checks(resources))

        logger.info("app_started", service=settings.service_name, env=settings.environment)
        yield

    logger.info("app_stopped", service=settings.service_name)


@docs_router.get("/scalar")
async def scalar_docs(request: Request) -> HTMLResponse:
    app: FastAPI = request.app
    return get_scalar_api_reference(
        openapi_url=app.openapi_url or OPENAPI_URL,
        title=app.title,
    )


def create_app() -> FastAPI:
    """Build the application."""
    settings = get_settings()
    setup_logging()

    # `debug` is deliberately not wired to settings.debug_mode: it makes Starlette
    # answer 500s with a plain-text traceback instead of calling our handlers, so the
    # error contract would silently differ between local and production.
    app = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
        openapi_url=OPENAPI_URL if settings.enable_docs else None,
        docs_url="/docs" if settings.enable_docs else None,
        redoc_url="/redoc" if settings.enable_docs else None,
    )

    register_exception_handlers(app)
    setup_middlewares(app)

    app.include_router(health.router)
    if settings.enable_docs:
        app.include_router(docs_router)

    return app
