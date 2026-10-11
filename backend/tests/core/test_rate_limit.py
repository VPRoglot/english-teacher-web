from collections.abc import AsyncIterator

import pytest
from asgi_lifespan import LifespanManager
from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis

from app.core.config import Settings
from app.core.errors import NotAuthenticated, RateLimited
from app.core.rate_limit import RateLimit, RateLimiter
from app.main import create_app

RULE = RateLimit(limit=3, window_seconds=60)

routes = APIRouter(prefix="/api/_t")


@routes.get("/limited")
async def raise_limited() -> None:
    raise RateLimited(42)


@routes.get("/unauthenticated")
async def raise_unauthenticated() -> None:
    raise NotAuthenticated


@pytest.fixture
async def clean_redis(redis: Redis) -> Redis:
    await redis.flushdb()
    return redis


@pytest.fixture
async def tclient(settings: Settings) -> AsyncIterator[AsyncClient]:
    app = create_app(settings)
    app.include_router(routes)
    async with (
        LifespanManager(app),
        AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c,
    ):
        yield c


async def test_allows_until_limit(clean_redis: Redis) -> None:
    rl = RateLimiter(clean_redis)
    for _ in range(2):
        await rl.hit("k", RULE)
    assert await rl.retry_after("k", RULE) is None
    await rl.hit("k", RULE)
    ra = await rl.retry_after("k", RULE)
    assert ra is not None
    assert 1 <= ra <= 60


async def test_window_is_not_extended_by_hits(clean_redis: Redis) -> None:
    rl = RateLimiter(clean_redis)
    await rl.hit("k", RULE)
    await clean_redis.expire("rl:k", 5)
    await rl.hit("k", RULE)
    assert await clean_redis.ttl("rl:k") <= 5


async def test_reset_and_key_isolation(clean_redis: Redis) -> None:
    rl = RateLimiter(clean_redis)
    for _ in range(3):
        await rl.hit("a", RULE)
    assert await rl.retry_after("a", RULE) is not None
    assert await rl.retry_after("b", RULE) is None
    await rl.reset("a")
    assert await rl.retry_after("a", RULE) is None
    assert await clean_redis.exists("rl:a") == 0


async def test_retry_after_without_ttl_falls_back_to_window(clean_redis: Redis) -> None:
    await clean_redis.set("rl:k", 3)  # счётчик без TTL — не должно случаться
    assert await RateLimiter(clean_redis).retry_after("k", RULE) == 60


async def test_rate_limited_response_has_retry_after(tclient: AsyncClient) -> None:
    r = await tclient.get("/api/_t/limited")
    assert r.status_code == 429
    assert r.headers["Retry-After"] == "42"
    assert r.json()["error"]["code"] == "rate_limited"
    assert r.json()["error"]["details"] == {"retry_after": 42}


async def test_not_authenticated_response(tclient: AsyncClient) -> None:
    r = await tclient.get("/api/_t/unauthenticated")
    assert r.status_code == 401
    assert r.json()["error"] == {
        "code": "not_authenticated",
        "message": "Требуется вход",
        "details": {},
    }
    assert "Retry-After" not in r.headers
