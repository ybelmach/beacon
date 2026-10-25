from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from beacon.infrastructure.resources import Resources


def get_resources(request: Request) -> Resources:
    resources: Resources = request.app.state.resources
    return resources


ResourcesDep = Annotated[Resources, Depends(get_resources)]


async def get_session(resources: ResourcesDep) -> AsyncIterator[AsyncSession]:
    """One session per request, never committed here: the service owns the transaction."""
    async with resources.session_factory() as session:
        yield session


def get_redis(resources: ResourcesDep) -> Redis:
    return resources.redis


SessionDep = Annotated[AsyncSession, Depends(get_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]
