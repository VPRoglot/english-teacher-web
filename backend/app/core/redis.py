from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis

from app.core.config import Settings


def create_redis(settings: Settings) -> "Redis":
    return Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
    )


def get_redis(request: Request) -> "Redis":
    redis: Redis = request.app.state.redis
    return redis


RedisClient = Annotated["Redis", Depends(get_redis)]
