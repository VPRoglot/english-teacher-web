import time

from httpx import AsyncClient, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.main import create_app
from tests.conftest import open_client


async def _ready(settings: Settings) -> tuple[Response, float]:
    app = create_app(settings)
    async with open_client(app) as c:
        assert (await c.get("/api/health")).status_code == 200
        started = time.monotonic()
        r = await c.get("/api/health/ready")
        return r, time.monotonic() - started


async def test_ready_ok(client: AsyncClient) -> None:
    r = await client.get("/api/health/ready")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "checks": {"database": "ok", "redis": "ok"}}


async def test_ready_reports_database_down_quickly(settings: Settings) -> None:
    broken = settings.model_copy(update={"database_url": "postgresql+asyncpg://u:p@127.0.0.1:1/x"})
    r, elapsed = await _ready(broken)
    assert elapsed < 3
    assert r.status_code == 503
    assert r.json() == {"status": "unavailable", "checks": {"database": "error", "redis": "ok"}}


async def test_ready_reports_redis_down(settings: Settings) -> None:
    broken = settings.model_copy(update={"redis_url": "redis://127.0.0.1:1/0"})
    r, elapsed = await _ready(broken)
    assert elapsed < 3
    assert r.status_code == 503
    assert r.json() == {"status": "unavailable", "checks": {"database": "ok", "redis": "error"}}


async def test_db_session_fixture_is_isolated(db_session: AsyncSession) -> None:
    await db_session.execute(text("CREATE TEMP TABLE t (x int)"))
    assert (await db_session.execute(text("SELECT 1"))).scalar_one() == 1
