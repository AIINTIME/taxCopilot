from redis.asyncio import Redis

from app.core.config import get_settings

redis_client: Redis | None = None


async def connect_redis() -> Redis:
    global redis_client
    settings = get_settings()
    redis_client = Redis.from_url(settings.redis_url, decode_responses=True)
    await redis_client.ping()
    return redis_client


def get_redis() -> Redis:
    if redis_client is None:
        raise RuntimeError("Redis is not connected")
    return redis_client


async def close_redis() -> None:
    if redis_client is not None:
        await redis_client.aclose()
