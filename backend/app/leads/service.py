import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import new_uuid7
from app.core.tasks import TaskQueue
from app.leads.models import Lead, LeadStatus, LeadStatusHistory
from app.leads.schemas import LeadCreate

log = structlog.get_logger("app.leads")

# Имя задачи живёт здесь, а не в notifications: Task 4 импортирует его отсюда,
# чтобы между пакетами не возник цикл notifications → leads.service.
NOTIFY_NEW_LEAD_TASK = "notifications.notify_new_lead"


async def create_lead(session: AsyncSession, data: LeadCreate) -> Lead:
    """Сохраняет заявку со статусом `new` и первой строкой истории `None → new`."""
    lead = Lead(
        id=new_uuid7(),
        parent_name=data.parent_name,
        child_name=data.child_name,
        child_age=data.child_age,
        phone=data.phone,
        contact_method=data.contact_method,
        messenger_handle=data.messenger_handle,
        goal=data.goal,
        preferred_time=data.preferred_time,
        status=LeadStatus.NEW,
        consent_at=datetime.now(UTC),
        utm_source=data.utm_source,
        utm_medium=data.utm_medium,
        utm_campaign=data.utm_campaign,
    )
    session.add(lead)
    session.add(LeadStatusHistory(lead_id=lead.id, from_status=None, to_status=LeadStatus.NEW))
    await session.flush()
    return lead


async def request_lead_notification(queue: TaskQueue, lead_id: uuid.UUID) -> None:
    """Просит worker уведомить репетитора о заявке.

    Сбой очереди не должен ронять ответ: заявка уже сохранена, а репетитор увидит её в админке.
    """
    try:
        await queue.enqueue(NOTIFY_NEW_LEAD_TASK, lead_id=str(lead_id))
    except Exception:
        log.warning("lead_notification_enqueue_failed", lead_id=str(lead_id), exc_info=True)
