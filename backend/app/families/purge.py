import uuid
from dataclasses import dataclass, replace

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service as auth_service
from app.auth.sessions import SessionStore
from app.core.errors import Conflict, NotFound
from app.families.models import Child, Family, ParentProfile
from app.leads import service as leads_service
from app.leads.models import Lead
from app.lessons import service as lessons_service
from app.lessons.models import ChangeRequest, Lesson

log = structlog.get_logger("app.families")


@dataclass(frozen=True)
class PurgeSummary:
    family_name: str
    users: int
    children: int
    lessons: int
    change_requests: int
    leads: int
    # Только у результата purge_family: False — Redis был недоступен после коммита.
    sessions_revoked: bool = True


class FamilyNotFound(NotFound):
    code = "family_not_found"
    message = "Семья не найдена"


class FamilyNotArchived(Conflict):
    code = "family_not_archived"
    message = "Сначала переведите семью в архив"


@dataclass(frozen=True)
class _Scope:
    family_name: str
    child_ids: list[uuid.UUID]
    user_ids: list[uuid.UUID]
    lead_ids: list[uuid.UUID]


async def _scope(session: AsyncSession, family_id: uuid.UUID, *, lock: bool) -> _Scope:
    stmt = select(Family).where(Family.id == family_id)
    if lock:
        stmt = stmt.with_for_update()
    family = (await session.execute(stmt)).scalar_one_or_none()
    if family is None:
        raise FamilyNotFound
    if family.archived_at is None:
        raise FamilyNotArchived
    children = (
        await session.execute(select(Child.id, Child.user_id).where(Child.family_id == family_id))
    ).all()
    parent_ids = (
        (
            await session.execute(
                select(ParentProfile.user_id).where(ParentProfile.family_id == family_id)
            )
        )
        .scalars()
        .all()
    )
    lead_ids = (
        (await session.execute(select(Lead.id).where(Lead.family_id == family_id))).scalars().all()
    )
    return _Scope(
        family_name=family.name,
        child_ids=[c.id for c in children],
        user_ids=[*parent_ids, *(c.user_id for c in children if c.user_id is not None)],
        lead_ids=list(lead_ids),
    )


async def _summary(session: AsyncSession, scope: _Scope) -> PurgeSummary:
    lesson_filter = Lesson.child_id.in_(scope.child_ids) | Lesson.lead_id.in_(scope.lead_ids)
    lessons = await session.scalar(select(func.count()).select_from(Lesson).where(lesson_filter))
    requests = await session.scalar(
        select(func.count())
        .select_from(ChangeRequest)
        .where(ChangeRequest.lesson_id.in_(select(Lesson.id).where(lesson_filter)))
    )
    return PurgeSummary(
        family_name=scope.family_name,
        users=len(scope.user_ids),
        children=len(scope.child_ids),
        lessons=lessons or 0,
        change_requests=requests or 0,
        leads=len(scope.lead_ids),
    )


async def describe_purge(session: AsyncSession, family_id: uuid.UUID) -> PurgeSummary:
    """Что будет удалено; только чтение. Неархивная или несуществующая семья — ошибка."""
    return await _summary(session, await _scope(session, family_id, lock=False))


async def purge_family(session: AsyncSession, redis: Redis, family_id: uuid.UUID) -> PurgeSummary:
    """Физически удаляет архивную семью со всеми ПДн (152-ФЗ) в одной транзакции.

    Сессии Redis отзываются после коммита: при откате пользователи остаются в системе.
    """
    try:
        scope = await _scope(session, family_id, lock=True)
        summary = await _summary(session, scope)
        await lessons_service.delete_lessons_of_children(session, scope.child_ids)
        await lessons_service.delete_lessons_of_leads(session, scope.lead_ids)
        await leads_service.delete_family_leads(session, family_id)
        # Профили, дети (с сериями) и приглашения уходят каскадом.
        await session.execute(delete(Family).where(Family.id == family_id))
        await auth_service.delete_users(session, scope.user_ids)
        await session.commit()
    except BaseException:
        await session.rollback()
        raise
    # Данные уже удалены: сбой Redis не делает операцию неудачной. Оставшиеся сессии
    # недействительны — их пользователей больше нет, а Redis-ключи истекут сами.
    sessions_revoked = True
    store = SessionStore(redis)
    try:
        for user_id in scope.user_ids:
            await store.delete_all_for_user(user_id)
    except RedisError as exc:
        sessions_revoked = False
        log.warning(
            "family_purge_sessions_not_revoked",
            family_id=str(family_id),
            user_ids=[str(user_id) for user_id in scope.user_ids],
            error=type(exc).__name__,
        )
    summary = replace(summary, sessions_revoked=sessions_revoked)
    log.info(
        "family_purged",
        family_id=str(family_id),
        users=summary.users,
        children=summary.children,
        lessons=summary.lessons,
        change_requests=summary.change_requests,
        leads=summary.leads,
    )
    return summary
