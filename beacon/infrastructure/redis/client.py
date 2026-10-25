from redis.asyncio import Redis

from beacon.core.config import Settings


def create_redis(settings: Settings) -> Redis:
    return Redis.from_url(
        settings.redis_dsn,
        decode_responses=True,
        health_check_interval=30,
        socket_connect_timeout=settings.redis_socket_timeout_seconds,
        socket_timeout=settings.redis_socket_timeout_seconds,
    )


async def ping_redis(client: Redis) -> None:
    await client.ping()
