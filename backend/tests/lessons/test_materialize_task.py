import importlib
import sys
from collections.abc import Iterator
from datetime import date, time
from typing import Any

import pytest
import structlog
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from taskiq import Context, InMemoryBroker, TaskiqState
from taskiq.schedule_sources import LabelScheduleSource

from app.core.config import get_settings
from app.families.models import Child
from app.lessons.models import Lesson
from app.lessons.tasks import MATERIALIZE_SERIES_TASK, materialize_series_task
from app.tasks import setup_worker
from tests.conftest import make_settings
from tests.factories import make_child, make_family
from tests.lessons.conftest import make_series


@pytest.fixture
async def db_series(db_session: AsyncSession) -> Child:
    child = await make_child(db_session, await make_family(db_session))
    await make_series(
        db_session,
        child,
        rrule="FREQ=WEEKLY;BYDAY=MO,TH",
        starts_on=date(2020, 1, 1),
        local_start_time=time(10, 0),
    )
    return child


async def _count(session: AsyncSession) -> int:
    return await session.scalar(select(func.count()).select_from(Lesson)) or 0


def test_task_is_registered_with_daily_cron() -> None:
    broker = setup_worker(InMemoryBroker(), make_settings())
    task = broker.find_task(MATERIALIZE_SERIES_TASK)
    assert task is not None
    assert task.labels["schedule"] == [{"cron": "0 1 * * *"}]
    assert task.labels["retry_on_error"] is True
    assert task.labels["max_retries"] == 5


async def test_task_materializes_active_series(
    context: Context, db_series: Child, db_session: AsyncSession
) -> None:
    with structlog.testing.capture_logs() as logs:
        await materialize_series_task(context)
    created = await _count(db_session)
    assert 14 <= created <= 18  # 8 недель, два занятия в неделю
    assert [(e["event"], e["log_level"], e["created"]) for e in logs] == [
        ("series_materialized", "info", created)
    ]


async def test_materialize_task_pings_heartbeat(
    context: Context, db_series: Child, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = SecretStr("https://hc.example/ping/uuid")
    context.state.heartbeat_materialize_url = url
    pings: list[tuple[Any, Any, str]] = []

    async def fake_ping(http: Any, ping_url: Any, *, name: str) -> None:
        pings.append((http, ping_url, name))

    monkeypatch.setattr("app.lessons.tasks.ping_heartbeat", fake_ping)

    await materialize_series_task(context)

    assert pings == [(context.state.http, url, "materialize_series")]


async def test_materialize_task_failure_sends_no_heartbeat(
    context: Context, monkeypatch: pytest.MonkeyPatch
) -> None:
    pings: list[str] = []

    async def fake_ping(http: Any, ping_url: Any, *, name: str) -> None:
        pings.append(name)

    async def failing(*_a: Any, **_k: Any) -> int:
        raise RuntimeError("db down")

    monkeypatch.setattr("app.lessons.tasks.ping_heartbeat", fake_ping)
    monkeypatch.setattr("app.lessons.tasks.materialize_all", failing)

    with pytest.raises(RuntimeError):
        await materialize_series_task(context)

    assert pings == []


async def test_task_is_idempotent(
    context: Context, db_series: Child, db_session: AsyncSession
) -> None:
    await materialize_series_task(context)
    first = await _count(db_session)
    with structlog.testing.capture_logs() as logs:
        await materialize_series_task(context)
    assert await _count(db_session) == first
    assert logs[0]["created"] == 0


async def test_worker_runs_task_end_to_end(
    worker_state: TaskiqState, db_series: Child, db_session: AsyncSession
) -> None:
    broker = InMemoryBroker()
    setup_worker(broker, make_settings())
    await broker.startup()
    try:
        # Подменяем сессии, созданные setup_worker, на тестовые (БД в savepoint).
        broker.state.sessionmaker = worker_state.sessionmaker
        task = broker.find_task(MATERIALIZE_SERIES_TASK)
        assert task is not None
        await task.kiq()
        await broker.wait_all()
    finally:
        await broker.shutdown()
    assert await _count(db_session) > 0


@pytest.fixture
def worker_module_importable(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Импорт `app.worker` читает настройки и настраивает логи: даём ему тестовое окружение."""
    env = {
        "DATABASE_URL": "postgresql+asyncpg://u:p@h/db",
        "REDIS_URL": "redis://h",
        "REVALIDATE_SECRET": "test-revalidate-secret",
        "S3_BUCKET": "b",
        "S3_ACCESS_KEY": "k",
        "S3_SECRET_KEY": "s",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr("app.core.logging.configure_logging", lambda *_a, **_k: None)
    get_settings.cache_clear()
    for name in ("app.worker", "app.scheduler"):
        sys.modules.pop(name, None)
    yield
    for name in ("app.worker", "app.scheduler"):
        sys.modules.pop(name, None)
    get_settings.cache_clear()


@pytest.mark.usefixtures("worker_module_importable")
async def test_scheduler_reads_labels_from_worker_broker() -> None:
    scheduler = importlib.import_module("app.scheduler").scheduler
    worker = importlib.import_module("app.worker")
    assert scheduler.broker is worker.broker
    sources = [s for s in scheduler.sources if isinstance(s, LabelScheduleSource)]
    assert len(sources) == 1
    await sources[0].startup()  # собирает расписания из меток задач брокера worker
    schedules = await sources[0].get_schedules()
    assert (MATERIALIZE_SERIES_TASK, "0 1 * * *") in [(s.task_name, s.cron) for s in schedules]
