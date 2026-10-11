from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from starlette.types import ASGIApp
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

from app.core.config import Settings
from app.core.db import get_db_session
from app.main import create_app

BACKEND_DIR = Path(__file__).resolve().parent.parent


def alembic_config(database_url: str) -> Config:
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    cfg.attributes["configure_logger"] = False  # не перетирать логирование тестов
    return cfg


@pytest.fixture(scope="session")
def postgres_url() -> Iterator[str]:
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as pg:
        yield pg.get_connection_url()


@pytest.fixture(scope="session")
def redis_url() -> Iterator[str]:
    with RedisContainer("redis:7-alpine") as r:
        yield f"redis://{r.get_container_host_ip()}:{r.get_exposed_port(6379)}/0"


@pytest.fixture(scope="session")
def migrated_db(postgres_url: str) -> str:
    command.upgrade(alembic_config(postgres_url), "head")
    return postgres_url


@pytest.fixture(scope="session")
async def redis(redis_url: str) -> AsyncIterator[Redis]:
    client = Redis.from_url(redis_url, decode_responses=True)
    yield client
    await client.aclose()


@pytest.fixture
def settings(postgres_url: str, redis_url: str) -> Settings:
    return Settings(
        _env_file=None,
        app_env="test",
        database_url=postgres_url,
        redis_url=redis_url,
        log_json=False,
    )


@pytest.fixture(scope="session")
async def engine(migrated_db: str) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(migrated_db)
    yield eng
    await eng.dispose()


@pytest.fixture
async def db_session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    async with engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(
            bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False
        )
        try:
            yield session
        finally:
            await session.close()
            await trans.rollback()


@pytest.fixture
async def app(settings: Settings, db_session: AsyncSession, redis: Redis) -> FastAPI:
    await redis.flushdb()  # rate limit и сессии не текут между тестами
    application = create_app(settings)

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    application.dependency_overrides[get_db_session] = _session
    return application


@asynccontextmanager
async def open_client(
    app: FastAPI, *, asgi: ASGIApp | None = None, raise_app_exceptions: bool = True
) -> AsyncIterator[AsyncClient]:
    """Клиент по HTTPS с уже полученным CSRF-токеном (cookie + заголовок).

    `asgi` позволяет обернуть приложение (например, записать порядок событий ответа).
    """
    transport = ASGITransport(app=asgi or app, raise_app_exceptions=raise_app_exceptions)
    async with (
        LifespanManager(app),
        AsyncClient(transport=transport, base_url="https://test") as c,
    ):
        r = await c.get("/api/auth/csrf")
        assert r.status_code == 204
        c.headers["X-CSRF-Token"] = c.cookies["csrf_token"]
        yield c


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    async with open_client(app) as c:
        yield c
