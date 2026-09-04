from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import HTMLResponse
from scalar_fastapi import get_scalar_api_reference

from beacon.core import health
from beacon.core.config import get_settings
from beacon.core.exception_handlers import register_exception_handlers
from beacon.core.lifespan import lifespan
from beacon.core.logging import setup_logging
from beacon.core.middlewares import setup_middlewares

OPENAPI_URL = "/openapi.json"

docs_router = APIRouter(include_in_schema=False)


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
