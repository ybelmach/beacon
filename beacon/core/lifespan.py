from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI

from beacon.core.config import get_settings
from beacon.core.logging import get_logger
from beacon.infrastructure.postgres.session import create_postgres_engine, create_session_factory
from beacon.infrastructure.redis.client import create_redis

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings = get_settings()

    # Each resource registers its teardown the moment it exists, so a failure while
    # acquiring the next one still unwinds everything acquired before it.
    async with AsyncExitStack() as stack:
        engine = create_postgres_engine()
        stack.push_async_callback(engine.dispose)

        redis = create_redis()
        stack.push_async_callback(redis.aclose)

        app.state.engine = engine
        app.state.session_factory = create_session_factory(engine)
        app.state.redis = redis

        logger.info("app_started", service=settings.service_name, env=settings.environment)
        yield

    logger.info("app_stopped", service=settings.service_name)
