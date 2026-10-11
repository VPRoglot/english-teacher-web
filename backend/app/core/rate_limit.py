from dataclasses import dataclass

from redis.asyncio import Redis


@dataclass(frozen=True)
class RateLimit:
    limit: int
    window_seconds: int


class RateLimiter:
    """Счётчик с фиксированным окном на ключ: окно стартует с первой попытки."""

    def __init__(self, redis: Redis, prefix: str = "rl") -> None:
        self._redis = redis
        self._prefix = prefix

    def _key(self, key: str) -> str:
        return f"{self._prefix}:{key}"

    async def retry_after(self, key: str, rule: RateLimit) -> int | None:
        """Секунды до конца окна, если лимит исчерпан; иначе `None`."""
        redis_key = self._key(key)
        count = await self._redis.get(redis_key)
        if count is None or int(count) < rule.limit:
            return None
        ttl = await self._redis.ttl(redis_key)
        return ttl if ttl > 0 else rule.window_seconds

    async def hit(self, key: str, rule: RateLimit) -> None:
        redis_key = self._key(key)
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.incr(redis_key)
            pipe.expire(redis_key, rule.window_seconds, nx=True)
            await pipe.execute()

    async def reset(self, key: str) -> None:
        await self._redis.delete(self._key(key))
