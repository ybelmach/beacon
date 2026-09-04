from redis.asyncio import Redis

from beacon.core.config import get_settings


def create_redis() -> Redis:
    settings = get_settings()
    return Redis.from_url(
        settings.redis_dsn,
        decode_responses=True,
        health_check_interval=30,
        socket_connect_timeout=settings.redis_socket_timeout_seconds,
        socket_timeout=settings.redis_socket_timeout_seconds,
    )
