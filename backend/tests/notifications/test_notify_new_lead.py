import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from taskiq import Context, InMemoryBroker, TaskiqState

from app.core.config import Settings
from app.core.tasks import BrokerTaskQueue
from app.leads.models import ContactMethod, Lead
from app.leads.service import NOTIFY_NEW_LEAD_TASK
from app.notifications.notifier import DisabledNotifier, NotifyFailed, TelegramNotifier
from app.notifications.tasks import MAX_MESSAGE_LENGTH, _years, format_lead_message, notify_new_lead
from app.tasks import setup_worker
from tests.conftest import make_settings
from tests.notifications.conftest import PUBLIC_BASE_URL, FakeNotifier
from tests.notifications.helpers import make_lead

URL = "https://t.example/admin/leads/1"


def test_message_contains_name_age_contact_and_link() -> None:
    text = format_lead_message(
        make_lead(
            parent_name="Анна",
            child_name="Маша",
            child_age=9,
            contact_method=ContactMethod.TELEGRAM,
            messenger_handle="anna",
            phone="+79991234567",
        ),
        URL,
    )
    assert "Родитель: Анна" in text and "Ребёнок: Маша, 9 лет" in text
    assert "Связь: Telegram @anna · +79991234567" in text and text.endswith(URL)
    assert "Цель" not in text


def test_message_full_layout() -> None:
    text = format_lead_message(
        make_lead(goal="Подготовка к школе", preferred_time="вечером, после 17:00"), URL
    )
    assert text == (
        "Новая заявка на пробное занятие\n"
        "Родитель: Анна\n"
        "Ребёнок: Маша, 9 лет\n"
        "Связь: Telegram · +79991234567\n"
        "Цель: Подготовка к школе\n"
        "Удобное время: вечером, после 17:00\n"
        f"{URL}"
    )


def test_message_omits_empty_optional_lines() -> None:
    text = format_lead_message(make_lead(goal="", preferred_time=None), URL)
    assert "Цель" not in text and "Удобное время" not in text
    assert "\n\n" not in text


def test_message_without_handle_has_no_at_sign() -> None:
    text = format_lead_message(make_lead(messenger_handle=None), URL)
    assert "Связь: Telegram · +79991234567" in text
    assert "@" not in text


@pytest.mark.parametrize(
    ("method", "label"),
    [(ContactMethod.WHATSAPP, "WhatsApp"), (ContactMethod.PHONE, "Телефон")],
)
def test_message_contact_method_labels(method: ContactMethod, label: str) -> None:
    text = format_lead_message(make_lead(contact_method=method, messenger_handle="x"), URL)
    assert f"Связь: {label} · +79991234567" in text
    assert "@x" not in text


@pytest.mark.parametrize(
    ("age", "word"),
    [
        (1, "год"),
        (2, "года"),
        (4, "года"),
        (5, "лет"),
        (11, "лет"),
        (12, "лет"),
        (14, "лет"),
        (21, "год"),
        (22, "года"),
        (25, "лет"),
    ],
)
def test_years_declension(age: int, word: str) -> None:
    assert _years(age) == word


def test_message_is_plain_text_and_truncated() -> None:
    text = format_lead_message(make_lead(parent_name="<b>Анна</b> *_[x](y)", goal="я" * 5000), "u")
    assert "<b>Анна</b> *_[x](y)" in text
    assert len(text) <= MAX_MESSAGE_LENGTH and text.endswith("…")


async def test_task_sends_once_and_marks_notified(
    context: Context, db_lead: Lead, notifier: FakeNotifier, db_session: AsyncSession
) -> None:
    await notify_new_lead(str(db_lead.id), context)
    await notify_new_lead(str(db_lead.id), context)

    expected = format_lead_message(db_lead, f"{PUBLIC_BASE_URL}/admin/leads/{db_lead.id}")
    assert notifier.sent == [expected]
    await db_session.refresh(db_lead)
    assert db_lead.notified_at is not None


async def test_task_failure_leaves_lead_unnotified(
    context: Context, db_lead: Lead, notifier: FakeNotifier, db_session: AsyncSession
) -> None:
    notifier.error = NotifyFailed("Telegram ответил 500")
    with pytest.raises(NotifyFailed):
        await notify_new_lead(str(db_lead.id), context)

    await db_session.refresh(db_lead)
    assert db_lead.notified_at is None

    notifier.error = None  # повтор после восстановления Telegram доставляет сообщение
    await notify_new_lead(str(db_lead.id), context)
    assert len(notifier.sent) == 1
    await db_session.refresh(db_lead)
    assert db_lead.notified_at is not None


@pytest.mark.parametrize("lead_id", [str(uuid.uuid4()), "not-a-uuid"])
async def test_missing_lead_is_noop(context: Context, notifier: FakeNotifier, lead_id: str) -> None:
    with structlog.testing.capture_logs() as logs:
        await notify_new_lead(lead_id, context)
    assert notifier.sent == []
    assert [(e["event"], e["log_level"], e["reason"]) for e in logs] == [
        ("lead_notification_skipped", "info", "not_found")
    ]


async def test_already_notified_lead_is_skipped(
    context: Context, db_lead: Lead, notifier: FakeNotifier
) -> None:
    await notify_new_lead(str(db_lead.id), context)
    with structlog.testing.capture_logs() as logs:
        await notify_new_lead(str(db_lead.id), context)
    assert len(notifier.sent) == 1
    assert [(e["event"], e["log_level"], e["reason"]) for e in logs] == [
        ("lead_notification_skipped", "info", "already_notified")
    ]


@asynccontextmanager
async def _started_worker(settings: Settings) -> AsyncIterator[InMemoryBroker]:
    broker = InMemoryBroker()
    setup_worker(broker, settings)
    await broker.startup()
    try:
        yield broker
    finally:
        await broker.shutdown()


async def test_worker_uses_telegram_notifier_when_configured() -> None:
    settings = make_settings(telegram_bot_token="tok", telegram_chat_id="42")
    async with _started_worker(settings) as broker:
        assert isinstance(broker.state.notifier, TelegramNotifier)
        assert broker.state.public_base_url == settings.public_base_url


@pytest.mark.parametrize(
    "overrides", [{}, {"telegram_bot_token": "tok"}, {"telegram_chat_id": "42"}]
)
async def test_worker_uses_disabled_notifier_without_full_config(
    overrides: dict[str, str],
) -> None:
    async with _started_worker(make_settings(**overrides)) as broker:
        assert isinstance(broker.state.notifier, DisabledNotifier)


async def test_worker_runs_notify_task_end_to_end(
    worker_state: TaskiqState, db_lead: Lead, notifier: FakeNotifier, db_session: AsyncSession
) -> None:
    async with _started_worker(make_settings()) as broker:
        # Подменяем ресурсы, созданные setup_worker, на тестовые (БД в savepoint, fake notifier).
        broker.state.sessionmaker = worker_state.sessionmaker
        broker.state.notifier = notifier
        queue = BrokerTaskQueue(broker, timeout_seconds=5)
        await queue.enqueue(NOTIFY_NEW_LEAD_TASK, lead_id=str(db_lead.id))
        await broker.wait_all()
    assert len(notifier.sent) == 1
    await db_session.refresh(db_lead)
    assert db_lead.notified_at is not None
