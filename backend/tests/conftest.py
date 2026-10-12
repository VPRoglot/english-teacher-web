from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import pytest
from alembic import command
from alembic.config import Config
from asgi_lifespan import LifespanManager
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from minio import Minio
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from starlette.types import ASGIApp
from taskiq import Context, InMemoryBroker, TaskiqMessage, TaskiqState
from testcontainers.community.minio import MinioContainer
from testcontainers.community.postgres import PostgresContainer
from testcontainers.community.redis import RedisContainer

from app.core.config import Settings
from app.core.db import get_db_session
from app.core.tasks import get_task_queue
from app.main import create_app

BACKEND_DIR = Path(__file__).resolve().parent.parent
MINIO_BUCKET = "media-test"


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
def minio() -> Iterator[MinioContainer]:
    # minio/minio убран с Docker Hub; рабочий образ — chainguard (только тег latest).
    # Ключи доступа 2026-й версии задаются MINIO_ROOT_*; MINIO_ACCESS_KEY из testcontainers устарел.
    container = MinioContainer("cgr.dev/chainguard/minio:latest")
    container.with_env("MINIO_ROOT_USER", container.access_key)
    container.with_env("MINIO_ROOT_PASSWORD", container.secret_key)
    with container:
        container.get_client().make_bucket(MINIO_BUCKET)
        yield container


@pytest.fixture(scope="session")
def minio_client(minio: MinioContainer) -> Minio:
    return minio.get_client()


@pytest.fixture(scope="session")
def migrated_db(postgres_url: str) -> str:
    command.upgrade(alembic_config(postgres_url), "head")
    return postgres_url


@pytest.fixture(scope="session")
async def redis(redis_url: str) -> AsyncIterator[Redis]:
    client = Redis.from_url(redis_url, decode_responses=True)
    yield client
    await client.aclose()


def make_settings(**overrides: Any) -> Settings:
    """Settings без .env и с заглушками для обязательных полей.

    Все места, где Settings собираются руками, берут их здесь: новая обязательная
    настройка добавляется один раз.
    """
    values: dict[str, Any] = {
        "_env_file": None,
        "database_url": "postgresql+asyncpg://u:p@h/db",
        "redis_url": "redis://h",
        "revalidate_secret": "test-revalidate-secret",
        "s3_bucket": MINIO_BUCKET,
        "s3_access_key": "test-access-key",
        "s3_secret_key": "test-secret-key",
        # Необязательные ключи: None, чтобы значения из окружения разработчика не просачивались.
        "smartcaptcha_server_key": None,
        "telegram_bot_token": None,
        "telegram_chat_id": None,
    }
    return Settings(**{**values, **overrides})


@pytest.fixture
def settings(postgres_url: str, redis_url: str, minio: MinioContainer) -> Settings:
    s3 = minio.get_config()
    return make_settings(
        app_env="test",
        database_url=postgres_url,
        redis_url=redis_url,
        log_json=False,
        s3_endpoint_url=f"http://{s3['endpoint']}",
        s3_access_key=s3["access_key"],
        s3_secret_key=s3["secret_key"],
    )


@pytest.fixture
def retry_sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Подменяет паузу между повторами задач (тесты не ждут) и записывает её длительность."""
    sleeps: list[float] = []

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr("app.core.tasks.sleep", fake_sleep)
    return sleeps


class FakeTaskQueue:
    """Очередь задач для API-тестов: запоминает постановки; при `fail` падает, как Redis."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.fail = False

    async def enqueue(self, task_name: str, /, **kwargs: Any) -> None:
        if self.fail:
            raise ConnectionError("redis недоступен")
        self.calls.append((task_name, kwargs))


@pytest.fixture
def task_queue() -> FakeTaskQueue:
    return FakeTaskQueue()


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
def sessionmaker(db_session: AsyncSession) -> async_sessionmaker[AsyncSession]:
    """Фабрика сессий на соединении тестовой транзакции: каждая сессия — свой savepoint.

    Так `materialize_all` открывает по сессии на серию и коммитит их, а данные теста
    остаются видны и откатываются вместе с внешней транзакцией.
    """
    assert isinstance(db_session.bind, AsyncConnection)
    return async_sessionmaker(
        db_session.bind, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )


@pytest.fixture
def worker_state(sessionmaker: async_sessionmaker[AsyncSession]) -> TaskiqState:
    state = TaskiqState()
    state.sessionmaker = sessionmaker
    state.http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    state.heartbeat_materialize_url = None
    state.heartbeat_anonymize_url = None
    return state


@pytest.fixture
def context(worker_state: TaskiqState) -> Context:
    broker = InMemoryBroker()
    broker.state = worker_state
    message = TaskiqMessage(task_id="t", task_name="n", labels={}, args=[], kwargs={})
    return Context(message, broker)


@pytest.fixture
async def app(
    settings: Settings, db_session: AsyncSession, redis: Redis, task_queue: FakeTaskQueue
) -> FastAPI:
    await redis.flushdb()  # rate limit и сессии не текут между тестами
    application = create_app(settings)

    async def _session() -> AsyncIterator[AsyncSession]:
        yield db_session

    application.dependency_overrides[get_db_session] = _session
    application.dependency_overrides[get_task_queue] = lambda: task_queue
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
