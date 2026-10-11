from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from taskiq import Context, InMemoryBroker, TaskiqMessage, TaskiqState

from app.leads.models import Lead
from app.notifications.notifier import NotifyFailed
from tests.notifications.helpers import make_lead

PUBLIC_BASE_URL = "https://t.example"


class FakeNotifier:
    """Notifier для тестов задачи: запоминает тексты; при `error` падает, как Telegram."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.error: NotifyFailed | None = None

    async def send(self, text: str) -> None:
        if self.error is not None:
            raise self.error
        self.sent.append(text)


@pytest.fixture
def notifier() -> FakeNotifier:
    return FakeNotifier()


@pytest.fixture
def worker_state(db_session: AsyncSession, notifier: FakeNotifier) -> TaskiqState:
    """Состояние worker с сессией тестовой БД.

    `sessionmaker` отдаёт ту же savepoint-сессию `db_session`: `commit()` задачи
    лишь закрывает savepoint, а сессию тест закроет сам.
    """

    @asynccontextmanager
    async def sessionmaker() -> AsyncIterator[AsyncSession]:
        yield db_session

    state = TaskiqState()
    state.sessionmaker = sessionmaker
    state.notifier = notifier
    state.public_base_url = PUBLIC_BASE_URL
    return state


@pytest.fixture
def context(worker_state: TaskiqState) -> Context:
    broker = InMemoryBroker()
    broker.state = worker_state
    message = TaskiqMessage(task_id="t", task_name="n", labels={}, args=[], kwargs={})
    return Context(message, broker)


@pytest.fixture
async def db_lead(db_session: AsyncSession) -> Lead:
    lead = make_lead()
    db_session.add(lead)
    await db_session.flush()
    return lead
