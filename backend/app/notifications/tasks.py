import uuid
from datetime import UTC, datetime
from typing import Annotated

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from taskiq import AsyncBroker, Context, TaskiqDepends

from app.core.telegram import TELEGRAM_HANDLE_RE
from app.leads.models import ContactMethod, Lead
from app.leads.service import NOTIFY_NEW_LEAD_TASK
from app.notifications.notifier import DisabledNotifier

log = structlog.get_logger("app.notifications")

MAX_MESSAGE_LENGTH = 4096  # лимит Telegram на текст сообщения

_CONTACT_METHOD_LABELS = {
    ContactMethod.TELEGRAM: "Telegram",
    ContactMethod.WHATSAPP: "WhatsApp",
    ContactMethod.PHONE: "Телефон",
}


def _years(n: int) -> str:
    """Склонение после числа: 1 год, 2 года, 5 лет."""
    if 11 <= n % 100 <= 14:
        return "лет"
    match n % 10:
        case 1:
            return "год"
        case 2 | 3 | 4:
            return "года"
        case _:
            return "лет"


def format_lead_message(lead: Lead, admin_url: str) -> str:
    """Текст для репетитора: обычный текст (без разметки), не длиннее лимита Telegram.

    Только то, что разрешает спека (4.5 п.1) и политика конфиденциальности: имя родителя,
    возраст ребёнка, способ связи с контактом и ссылка на заявку.
    """
    contact = _CONTACT_METHOD_LABELS[lead.contact_method]
    if lead.contact_method is ContactMethod.TELEGRAM and lead.messenger_handle:
        handle = lead.messenger_handle
        # «@» только перед настоящим именем пользователя; произвольный ввод печатается как есть.
        contact += f" @{handle}" if TELEGRAM_HANDLE_RE.fullmatch(handle) else f" {handle}"
    lines = [
        "Новая заявка на пробное занятие",
        f"Родитель: {lead.parent_name}",
        f"Возраст ребёнка: {lead.child_age} {_years(lead.child_age)}",
        f"Связь: {contact} · {lead.phone}",
        admin_url,
    ]
    text = "\n".join(lines)
    if len(text) > MAX_MESSAGE_LENGTH:
        text = text[: MAX_MESSAGE_LENGTH - 1] + "…"
    return text


async def notify_new_lead(lead_id: str, context: Annotated[Context, TaskiqDepends()]) -> None:
    """Шлёт репетитору сообщение о заявке ровно один раз.

    Исключение отправки не гасится: DelayedRetryMiddleware повторит задачу, а `notified_at`
    остаётся пустым. Строка заявки заблокирована до коммита, поэтому две одновременные
    доставки одной задачи не отправят два сообщения.
    """
    state = context.state
    async with state.sessionmaker() as session:
        lead = await _lock_lead(session, lead_id)
        if lead is None:
            log.info("lead_notification_skipped", lead_id=lead_id, reason="not_found")
            return
        if lead.notified_at is not None:
            log.info("lead_notification_skipped", lead_id=lead_id, reason="already_notified")
            return
        if isinstance(state.notifier, DisabledNotifier):
            # Telegram не настроен: заявка остаётся недоставленной и видна только в админке.
            log.warning("lead_notification_skipped", lead_id=lead_id, reason="disabled")
            return
        admin_url = f"{state.public_base_url}/admin/leads/{lead.id}"
        await state.notifier.send(format_lead_message(lead, admin_url))
        lead.notified_at = datetime.now(UTC)
        await session.commit()


async def _lock_lead(session: AsyncSession, lead_id: str) -> Lead | None:
    try:
        parsed_id = uuid.UUID(lead_id)
    except ValueError:
        return None
    stmt = (
        select(Lead)
        .where(Lead.id == parsed_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return await session.scalar(stmt)


def register_tasks(broker: AsyncBroker) -> None:
    broker.register_task(
        notify_new_lead, task_name=NOTIFY_NEW_LEAD_TASK, retry_on_error=True, max_retries=5
    )
