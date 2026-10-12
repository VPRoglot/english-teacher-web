import re
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import ColumnElement, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service as auth_service
from app.auth.models import User
from app.auth.schemas import LinkResponse
from app.core.config import Settings
from app.core.db import new_uuid7
from app.core.errors import Conflict, NotFound
from app.core.tasks import TaskQueue
from app.families import service as families_service
from app.families.schemas import FamilyCreate
from app.leads.models import Lead, LeadStatus, LeadStatusHistory
from app.leads.schemas import (
    LeadConvert,
    LeadConverted,
    LeadCreate,
    LeadDetail,
    LeadHistoryItem,
    LeadList,
    LeadListItem,
    LeadUpdate,
)
from app.leads.status import can_transition

log = structlog.get_logger("app.leads")

_MIN_PHONE_SEARCH_DIGITS = 3


class InvalidStatusTransition(Conflict):
    code = "invalid_status_transition"
    message = "Так сменить статус нельзя"


class LeadNotConvertible(Conflict):
    code = "lead_not_convertible"
    message = "Конвертировать можно после назначения пробного занятия"


class LeadNotFound(NotFound):
    code = "lead_not_found"
    message = "Заявка не найдена"


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


def _like_pattern(q: str) -> str:
    """Подстрока для ILIKE: `\\`, `%` и `_` из запроса ищутся как обычные символы."""
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


async def list_leads(
    session: AsyncSession, *, status: LeadStatus | None, q: str | None, limit: int, offset: int
) -> LeadList:
    conditions: list[ColumnElement[bool]] = [Lead.anonymized_at.is_(None)]
    if status is not None:
        conditions.append(Lead.status == status)
    if q and q.strip():
        text = q.strip()
        pattern = _like_pattern(text)
        matches = [
            Lead.parent_name.ilike(pattern, escape="\\"),
            Lead.child_name.ilike(pattern, escape="\\"),
            # В базе ник хранится без «@», а в поиск его вводят как в Telegram.
            Lead.messenger_handle.ilike(_like_pattern(text.removeprefix("@") or text), escape="\\"),
        ]
        digits = re.sub(r"\D", "", text)
        if len(digits) >= _MIN_PHONE_SEARCH_DIGITS:
            matches.append(Lead.phone.ilike(f"%{digits}%"))  # в phone только «+» и цифры
            if digits.startswith("8") and len(digits) > _MIN_PHONE_SEARCH_DIGITS:
                # «8 999 …» — это «+7 999 …»: телефон хранится в международном виде.
                matches.append(Lead.phone.ilike(f"%7{digits[1:]}%"))
        conditions.append(or_(*matches))

    total = await session.scalar(select(func.count()).select_from(Lead).where(*conditions))
    leads = await session.scalars(
        select(Lead)
        .where(*conditions)
        .order_by(Lead.created_at.desc(), Lead.id.desc())
        .limit(limit)
        .offset(offset)
    )
    return LeadList(
        items=[LeadListItem.model_validate(lead, from_attributes=True) for lead in leads],
        total=total or 0,
    )


async def _get_lead(session: AsyncSession, lead_id: uuid.UUID, *, lock: bool = False) -> Lead:
    stmt = select(Lead).where(Lead.id == lead_id, Lead.anonymized_at.is_(None))
    if lock:
        # Строка блокируется до конца транзакции: параллельная смена статуса или
        # конвертация ждёт и затем видит уже новый статус.
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    lead = await session.scalar(stmt)
    if lead is None:
        raise LeadNotFound
    return lead


async def _detail(session: AsyncSession, lead: Lead) -> LeadDetail:
    # История читается явным запросом, а не лениво через `lead.history`: в async-сессии
    # ленивая загрузка недоступна, а после записи связь осталась бы устаревшей.
    rows = await session.scalars(
        select(LeadStatusHistory)
        .where(LeadStatusHistory.lead_id == lead.id)
        .order_by(LeadStatusHistory.changed_at, LeadStatusHistory.id)
    )
    return LeadDetail.model_validate(
        {
            **{name: getattr(lead, name) for name in LeadDetail.model_fields if name != "history"},
            "history": [LeadHistoryItem.model_validate(r, from_attributes=True) for r in rows],
        }
    )


def _add_history(
    session: AsyncSession, lead: Lead, to_status: LeadStatus, comment: str | None
) -> None:
    # changed_at задаётся явно: server_default now() — это начало транзакции,
    # и строки одной транзакции не различались бы по порядку.
    session.add(
        LeadStatusHistory(
            lead_id=lead.id,
            from_status=lead.status,
            to_status=to_status,
            comment=comment,
            changed_at=datetime.now(UTC),
        )
    )


async def get_lead_detail(session: AsyncSession, lead_id: uuid.UUID) -> LeadDetail:
    return await _detail(session, await _get_lead(session, lead_id))


async def update_lead(session: AsyncSession, lead_id: uuid.UUID, data: LeadUpdate) -> LeadDetail:
    lead = await _get_lead(session, lead_id, lock=True)
    # Допустимость перехода проверяется до любых изменений: при отказе ничего не остаётся.
    target = LeadStatus(data.status) if data.status is not None else None
    if target is not None and not can_transition(lead.status, target):
        raise InvalidStatusTransition
    if target is not None:
        _add_history(session, lead, target, data.comment)
        lead.status = target
        lead.reject_reason = data.reject_reason  # None при уходе из rejected — причина очищается
    if "tutor_comment" in data.model_fields_set:
        lead.tutor_comment = data.tutor_comment or None
    await session.flush()
    await session.refresh(lead)  # updated_at выставляет БД
    return await _detail(session, lead)


async def schedule_trial_status(session: AsyncSession, lead_id: uuid.UUID, *, comment: str) -> Lead:
    """Переводит заявку в `trial_scheduled` (вызывается при назначении пробного занятия).

    Заявка блокируется (`FOR UPDATE`): повторное назначение ждёт и затем видит новый статус,
    поэтому из двух параллельных запросов успешен один. Допустимость перехода берётся из
    таблицы переходов; при отказе ничего не меняется.
    """
    lead = await _get_lead(session, lead_id, lock=True)
    if not can_transition(lead.status, LeadStatus.TRIAL_SCHEDULED):
        raise InvalidStatusTransition
    _add_history(session, lead, LeadStatus.TRIAL_SCHEDULED, comment)
    lead.status = LeadStatus.TRIAL_SCHEDULED
    await session.flush()
    return lead


async def convert_lead(
    session: AsyncSession,
    lead_id: uuid.UUID,
    data: LeadConvert,
    *,
    tutor: User,
    settings: Settings,
) -> LeadConverted:
    lead = await _get_lead(session, lead_id, lock=True)
    if lead.status is not LeadStatus.TRIAL_SCHEDULED:
        raise LeadNotConvertible
    family = await families_service.create_family(session, FamilyCreate(name=data.family_name))
    await families_service.add_child(session, family.id, data.child)
    token, invitation = await auth_service.create_invitation(
        session,
        family=family,
        created_by=tutor,
        prefill_full_name=data.parent.full_name,
        prefill_phone=data.parent.phone,
    )
    _add_history(session, lead, LeadStatus.CONVERTED, f"Создана семья {family.name}")
    lead.status = LeadStatus.CONVERTED
    lead.family_id = family.id
    await session.flush()
    url = auth_service.build_link(settings, "invite", token)
    return LeadConverted(
        family_id=family.id, invitation=LinkResponse(url=url, expires_at=invitation.expires_at)
    )
