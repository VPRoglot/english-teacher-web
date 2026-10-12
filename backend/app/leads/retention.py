from datetime import datetime

from dateutil.relativedelta import relativedelta
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.leads.models import Lead, LeadStatus, LeadStatusHistory

ANONYMIZED_NAME = "Обезличено"
RETENTION = relativedelta(months=12)


async def anonymize_stale_leads(session: AsyncSession, *, now: datetime) -> int:
    """Обезличивает заявки не в статусе converted, неактивные не менее RETENTION.

    Срок считается от последней смены статуса, а без истории — от создания заявки.
    Остаются только данные для статистики (возраст, способ связи, статус, UTM, даты).
    Коммит делает вызывающая сторона. Возвращает число обезличенных заявок.
    """
    last_activity = func.coalesce(func.max(LeadStatusHistory.changed_at), Lead.created_at)
    stale_ids = (
        select(Lead.id)
        .outerjoin(LeadStatusHistory, LeadStatusHistory.lead_id == Lead.id)
        .where(Lead.status != LeadStatus.CONVERTED, Lead.anonymized_at.is_(None))
        .group_by(Lead.id)
        .having(last_activity <= now - RETENTION)
    )
    result = await session.execute(
        update(Lead)
        .where(Lead.id.in_(stale_ids))
        .values(
            parent_name=ANONYMIZED_NAME,
            child_name=ANONYMIZED_NAME,
            phone="",
            messenger_handle=None,
            goal=None,
            preferred_time=None,
            tutor_comment=None,
            reject_reason=None,
            anonymized_at=now,
        )
        .returning(Lead.id),
        execution_options={"synchronize_session": False},
    )
    lead_ids = list(result.scalars())
    if lead_ids:
        await session.execute(
            update(LeadStatusHistory)
            .where(LeadStatusHistory.lead_id.in_(lead_ids), LeadStatusHistory.comment.is_not(None))
            .values(comment=None)
            .returning(LeadStatusHistory.id)
        )
    return len(lead_ids)
