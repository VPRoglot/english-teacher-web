import asyncio
from collections.abc import Awaitable, Callable

import structlog
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.errors import API_ERROR_RESPONSES

router = APIRouter(tags=["health"], responses=API_ERROR_RESPONSES)
log = structlog.get_logger("app.health")

CHECK_TIMEOUT_SECONDS = 2


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


async def _check(name: str, probe: Callable[[], Awaitable[object]]) -> str:
    try:
        async with asyncio.timeout(CHECK_TIMEOUT_SECONDS):
            await probe()
    except Exception as exc:
        log.warning("readiness_check_failed", check=name, error=repr(exc))
        return "error"
    return "ok"


@router.get("/health/ready")
async def ready(request: Request) -> JSONResponse:
    """Готовность для Docker и мониторинга; намеренно вне общего формата ошибок."""
    engine: AsyncEngine = request.app.state.engine
    redis: Redis = request.app.state.redis

    async def database() -> None:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

    async def redis_ping() -> None:
        await redis.ping()

    db_status, redis_status = await asyncio.gather(
        _check("database", database), _check("redis", redis_ping)
    )
    checks = {"database": db_status, "redis": redis_status}
    ok = all(v == "ok" for v in checks.values())
    return JSONResponse(
        {"status": "ok" if ok else "unavailable", "checks": checks},
        status_code=200 if ok else 503,
    )
