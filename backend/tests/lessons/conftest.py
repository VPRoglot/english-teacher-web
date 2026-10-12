from collections.abc import AsyncIterator
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker
from taskiq import Context, InMemoryBroker, TaskiqMessage, TaskiqState

from app.families.models import Child
from app.leads.models import Lead
from app.lessons.models import Lesson, LessonKind, LessonSeries
from tests.factories import login, make_child, make_family, make_parent, make_tutor


@pytest.fixture
async def tutor_client(client: AsyncClient, db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    await make_tutor(db_session)
    await login(client, "tutor@example.com")
    yield client


@pytest.fixture
async def parent_client(
    client: AsyncClient, db_session: AsyncSession
) -> AsyncIterator[AsyncClient]:
    family = await make_family(db_session)
    await make_parent(db_session, family)
    await login(client, "parent@example.com")
    yield client


@pytest.fixture
async def child_client(client: AsyncClient, db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    family = await make_family(db_session)
    await make_child(db_session, family, username="masha")
    await login(client, "masha")
    yield client


async def make_series(session: AsyncSession, child: Child, **overrides: Any) -> LessonSeries:
    """Серия в БД без материализации занятий; `overrides` заменяют поля."""
    values: dict[str, Any] = {
        "child_id": child.id,
        "rrule": "FREQ=WEEKLY;BYDAY=TU",
        "local_start_time": time(10, 0),
        "duration_min": 60,
        "starts_on": date(2026, 10, 12),
    }
    values.update(overrides)
    series = LessonSeries(**values)
    session.add(series)
    await session.flush()
    return series


async def make_lesson(
    session: AsyncSession,
    *,
    child: Child | None = None,
    lead: Lead | None = None,
    series: LessonSeries | None = None,
    **overrides: Any,
) -> Lesson:
    """Занятие в БД. Владелец — `child` или `lead`; без них ребёнок берётся из `series`.

    Занятие заявки получает `kind=trial`, остальные — `regular`; `overrides` заменяют поля
    (в том числе `child_id`/`lead_id`/`kind` — для заведомо неверных строк).
    """
    child_id = child.id if child is not None else None
    if child is None and lead is None and series is not None:
        child_id = series.child_id
    values: dict[str, Any] = {
        "series_id": series.id if series is not None else None,
        "child_id": child_id,
        "lead_id": lead.id if lead is not None else None,
        "kind": LessonKind.TRIAL if lead is not None else LessonKind.REGULAR,
        "starts_at": datetime.now(UTC) + timedelta(days=1),
        "duration_min": 60,
    }
    values.update(overrides)
    if values["series_id"] is not None:
        # Занятие серии помнит дату вхождения; по умолчанию — дата его начала (UTC).
        values.setdefault("occurrence_date", values["starts_at"].date())
    lesson = Lesson(**values)
    session.add(lesson)
    await session.flush()
    return lesson


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
    return state


@pytest.fixture
def context(worker_state: TaskiqState) -> Context:
    broker = InMemoryBroker()
    broker.state = worker_state
    message = TaskiqMessage(task_id="t", task_name="n", labels={}, args=[], kwargs={})
    return Context(message, broker)
