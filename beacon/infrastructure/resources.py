from collections.abc import AsyncGenerator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from beacon.core.config import Settings
from beacon.infrastructure.postgres.session import create_postgres_engine, create_session_factory
from beacon.infrastructure.redis.client import create_redis


@dataclass(frozen=True, slots=True)
class Resources:
    """Process-wide clients shared by every entrypoint: the API, consumers and the simulator."""

    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    redis: Redis


@asynccontextmanager
async def build_resources(settings: Settings) -> AsyncGenerator[Resources]:
    async with AsyncExitStack() as stack:
        engine = create_postgres_engine(settings)
        stack.push_async_callback(engine.dispose)

        redis = create_redis(settings)
        stack.push_async_callback(redis.aclose)

        yield Resources(
            engine=engine,
            session_factory=create_session_factory(engine),
            redis=redis,
        )
