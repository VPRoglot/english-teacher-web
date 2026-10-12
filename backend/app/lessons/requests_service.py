"""Запросы на перенос и отмену занятий."""

import uuid
from collections.abc import Collection
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy import Select, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.core.tasks import TaskQueue
from app.families.models import Child, Family, ParentProfile
from app.lessons.errors import (
    ChangeRequestExists,
    ChangeRequestNotFound,
    ChangeRequestNotPending,
    ChangeRequestOutdated,
    LessonNotFound,
    LessonNotRequestable,
    LessonSlotTaken,
    NewStartsAtRequired,
)
from app.lessons.late_cancel import is_late_cancel
from app.lessons.models import (
    ChangeRequest,
    ChangeRequestStatus,
    ChangeRequestType,
    Lesson,
    LessonKind,
    LessonStatus,
)
from app.lessons.overlaps import find_overlaps
from app.lessons.schemas import (
    ChangeRequestAdminItem,
    ChangeRequestApprove,
    ChangeRequestChild,
    ChangeRequestCreate,
    ChangeRequestFamily,
    ChangeRequestForFamily,
    ChangeRequestLesson,
    ChangeRequestReject,
    ChangeRequestResolved,
    OverlapWarning,
)

NOTIFY_CHANGE_REQUEST_TASK = "notifications.notify_change_request"
_PENDING_CONSTRAINT = "uq_change_requests_lesson_pending"
_SLOT_CONSTRAINT = "uq_lessons_series_id_starts_at"
MAX_ADMIN_REQUESTS = 200

log = structlog.get_logger("app.lessons")


async def lesson_ids_with_requests(
    session: AsyncSession, lesson_ids: Collection[uuid.UUID]
) -> set[uuid.UUID]:
    """Id занятий из `lesson_ids`, у которых есть запрос в любом статусе (одним запросом)."""
    if not lesson_ids:
        return set()
    stmt = select(ChangeRequest.lesson_id).where(ChangeRequest.lesson_id.in_(lesson_ids)).distinct()
    return set(await session.scalars(stmt))


async def _policy_hours(session: AsyncSession) -> int:
    from app.lessons.tutor_settings import get_tutor_settings  # цикл: tutor_settings → generation

    return (await get_tutor_settings(session)).cancel_policy_hours


def _in_scope(lesson: Lesson, child_ids: frozenset[uuid.UUID]) -> bool:
    return (
        lesson.kind is LessonKind.REGULAR
        and lesson.child_id is not None
        and lesson.child_id in child_ids
    )


def family_view(
    request: ChangeRequest, lesson: Lesson, *, policy_hours: int
) -> ChangeRequestForFamily:
    """Запрос в схеме для семьи (без автора и служебных полей).

    Поздней бывает только отмена; решает момент подачи (`created_at`), а не текущий.
    """
    is_late = request.type is ChangeRequestType.CANCEL and is_late_cancel(
        requested_at=request.created_at, starts_at=lesson.starts_at, policy_hours=policy_hours
    )
    return ChangeRequestForFamily(
        id=request.id,
        type=request.type,
        status=request.status,
        proposed_text=request.proposed_text,
        comment=request.comment,
        tutor_response=request.tutor_response,
        created_at=request.created_at,
        resolved_at=request.resolved_at,
        is_late=is_late,
    )


async def latest_request(session: AsyncSession, lesson_id: uuid.UUID) -> ChangeRequest | None:
    """Последний запрос занятия в любом статусе (`id` — UUIDv7 — разводит равные `created_at`)."""
    stmt = (
        select(ChangeRequest)
        .where(ChangeRequest.lesson_id == lesson_id)
        .order_by(ChangeRequest.created_at.desc(), ChangeRequest.id.desc())
        .limit(1)
        .execution_options(populate_existing=True)
    )
    return await session.scalar(stmt)


async def create_change_request(
    session: AsyncSession,
    child_ids: frozenset[uuid.UUID],
    lesson_id: uuid.UUID,
    data: ChangeRequestCreate,
    *,
    user: User,
    now: datetime,
) -> ChangeRequestForFamily:
    """Запрос на перенос или отмену будущего запланированного занятия ребёнка семьи.

    Занятие блокируется до коммита: два одновременных запроса выстраиваются в очередь, второй
    видит первый. Если гонка всё же прошла мимо проверки, частичный уникальный индекс даёт тот
    же 409 (вставка в савепоинте, транзакция остаётся рабочей).
    """
    from app.lessons.service import _lock_lesson  # service импортирует этот модуль

    lesson = await _lock_lesson(session, lesson_id)
    if not _in_scope(lesson, child_ids):
        raise LessonNotFound
    if lesson.status is not LessonStatus.SCHEDULED or lesson.starts_at <= now:
        raise LessonNotRequestable
    pending = await session.scalar(
        select(ChangeRequest.id).where(
            ChangeRequest.lesson_id == lesson.id,
            ChangeRequest.status == ChangeRequestStatus.PENDING,
        )
    )
    if pending is not None:
        raise ChangeRequestExists

    comment = data.comment.strip() if data.comment is not None else ""
    request = ChangeRequest(
        lesson_id=lesson.id,
        requested_by=user.id,
        type=data.type,
        proposed_text=data.proposed_text,
        comment=comment or None,
        created_at=now,
    )
    try:
        async with session.begin_nested():
            session.add(request)
            await session.flush()
    except IntegrityError as exc:
        if _PENDING_CONSTRAINT not in str(exc.orig):
            raise
        raise ChangeRequestExists from exc
    policy = await _policy_hours(session)
    return family_view(request, lesson, policy_hours=policy)


async def withdraw_change_request(
    session: AsyncSession,
    child_ids: frozenset[uuid.UUID],
    request_id: uuid.UUID,
    *,
    now: datetime,
) -> ChangeRequestForFamily:
    """Отзыв ждущего запроса любым родителем семьи; чужой или несуществующий — 404.

    Порядок блокировок общий с обработкой запроса репетитором: занятие → запрос.
    """
    from app.lessons.service import _lock_lesson  # service импортирует этот модуль

    lesson_id = await session.scalar(
        select(ChangeRequest.lesson_id).where(ChangeRequest.id == request_id)
    )
    if lesson_id is None:
        raise ChangeRequestNotFound
    lesson = await _lock_lesson(session, lesson_id)
    if not _in_scope(lesson, child_ids):
        raise ChangeRequestNotFound
    stmt = (
        select(ChangeRequest)
        .where(ChangeRequest.id == request_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    request = await session.scalar(stmt)
    if request is None:
        raise ChangeRequestNotFound
    if request.status is not ChangeRequestStatus.PENDING:
        raise ChangeRequestNotPending
    request.status = ChangeRequestStatus.WITHDRAWN
    request.resolved_at = now
    await session.flush()
    policy = await _policy_hours(session)
    return family_view(request, lesson, policy_hours=policy)


async def request_change_notification(queue: TaskQueue, request_id: uuid.UUID) -> None:
    """Просит worker уведомить репетитора о запросе.

    Сбой очереди не ломает ответ: запрос уже сохранён и виден в админке.
    """
    try:
        await queue.enqueue(NOTIFY_CHANGE_REQUEST_TASK, request_id=str(request_id))
    except Exception:
        log.warning("change_request_enqueue_failed", request_id=str(request_id), exc_info=True)


def _admin_stmt() -> Select[Any]:
    """Запросы с занятием, учеником, семьёй и ФИО автора (read-only join, правило R8)."""
    columns: list[Any] = [ChangeRequest, Lesson, Child, Family, ParentProfile.full_name]
    return (
        select(*columns)
        .join(Lesson, Lesson.id == ChangeRequest.lesson_id)
        .join(Child, Child.id == Lesson.child_id)
        .join(Family, Family.id == Child.family_id)
        .outerjoin(ParentProfile, ParentProfile.user_id == ChangeRequest.requested_by)
    )


def _admin_item(
    request: ChangeRequest,
    lesson: Lesson,
    child: Child,
    family: Family,
    author: str | None,
    *,
    policy_hours: int,
) -> dict[str, Any]:
    is_late = request.type is ChangeRequestType.CANCEL and is_late_cancel(
        requested_at=request.created_at, starts_at=lesson.starts_at, policy_hours=policy_hours
    )
    return {
        "id": request.id,
        "type": request.type,
        "status": request.status,
        "proposed_text": request.proposed_text,
        "comment": request.comment,
        "tutor_response": request.tutor_response,
        "created_at": request.created_at,
        "resolved_at": request.resolved_at,
        "is_late": is_late,
        "lesson": ChangeRequestLesson(
            id=lesson.id,
            starts_at=lesson.starts_at,
            duration_min=lesson.duration_min,
            status=lesson.status,
        ),
        "child": ChangeRequestChild(id=child.id, full_name=child.full_name),
        "family": ChangeRequestFamily(id=family.id, name=family.name),
        "requested_by_name": author or "",
    }


async def list_admin_requests(
    session: AsyncSession, *, status: ChangeRequestStatus | None
) -> list[ChangeRequestAdminItem]:
    """Очередь: ждущие — старейшие первыми, остальные — недавно рассмотренные первыми."""
    stmt = _admin_stmt()
    if status is ChangeRequestStatus.PENDING:
        stmt = stmt.order_by(ChangeRequest.created_at, ChangeRequest.id)
    elif status is None:
        stmt = stmt.order_by(ChangeRequest.created_at.desc(), ChangeRequest.id.desc())
    else:
        stmt = stmt.order_by(ChangeRequest.resolved_at.desc(), ChangeRequest.id.desc())
    if status is not None:
        stmt = stmt.where(ChangeRequest.status == status)
    stmt = stmt.limit(MAX_ADMIN_REQUESTS).execution_options(populate_existing=True)
    policy = await _policy_hours(session)
    return [
        ChangeRequestAdminItem(
            **_admin_item(request, lesson, child, family, author, policy_hours=policy)
        )
        for request, lesson, child, family, author in await session.execute(stmt)
    ]


async def pending_summary(
    session: AsyncSession, *, limit: int
) -> tuple[list[ChangeRequestAdminItem], int]:
    """Дашборд: до `limit` старейших ждущих запросов и общее число ждущих."""
    pending = ChangeRequest.status == ChangeRequestStatus.PENDING
    total = await session.scalar(select(func.count()).select_from(ChangeRequest).where(pending))
    stmt = (
        _admin_stmt()
        .where(pending)
        .order_by(ChangeRequest.created_at, ChangeRequest.id)
        .limit(limit)
        .execution_options(populate_existing=True)
    )
    policy = await _policy_hours(session)
    items = [
        ChangeRequestAdminItem(
            **_admin_item(request, lesson, child, family, author, policy_hours=policy)
        )
        for request, lesson, child, family, author in await session.execute(stmt)
    ]
    return items, total or 0


async def _resolved(
    session: AsyncSession, request_id: uuid.UUID, warnings: list[OverlapWarning]
) -> ChangeRequestResolved:
    stmt = _admin_stmt().where(ChangeRequest.id == request_id)
    row = (await session.execute(stmt.execution_options(populate_existing=True))).one()
    request, lesson, child, family, author = row
    policy = await _policy_hours(session)
    item = _admin_item(request, lesson, child, family, author, policy_hours=policy)
    return ChangeRequestResolved(**item, warnings=warnings)


async def _lock_request(session: AsyncSession, request_id: uuid.UUID) -> ChangeRequest:
    stmt = (
        select(ChangeRequest)
        .where(ChangeRequest.id == request_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    request = await session.scalar(stmt)
    if request is None:
        raise ChangeRequestNotFound
    return request


async def approve_change_request(
    session: AsyncSession,
    request_id: uuid.UUID,
    data: ChangeRequestApprove,
    *,
    now: datetime,
) -> ChangeRequestResolved:
    """Одобрение: отмена или перенос занятия и закрытие запроса одной транзакцией.

    Порядок блокировок (занятие → запрос) общий с отзывом запроса семьёй. Срок занятия не
    проверяется (уточнение 3), но занятие обязано быть `scheduled`. Статус отмены решает момент
    подачи запроса, порог берётся на момент одобрения.
    """
    from app.lessons.service import _lock_lesson  # service импортирует этот модуль
    from app.lessons.tutor_settings import get_timezone

    lesson_id = await session.scalar(
        select(ChangeRequest.lesson_id).where(ChangeRequest.id == request_id)
    )
    if lesson_id is None:
        raise ChangeRequestNotFound
    lesson = await _lock_lesson(session, lesson_id)
    request = await _lock_request(session, request_id)
    if request.status is not ChangeRequestStatus.PENDING:
        raise ChangeRequestNotPending
    if lesson.status is not LessonStatus.SCHEDULED:
        raise ChangeRequestOutdated

    warnings: list[OverlapWarning] = []
    if request.type is ChangeRequestType.CANCEL:
        late = is_late_cancel(
            requested_at=request.created_at,
            starts_at=lesson.starts_at,
            policy_hours=await _policy_hours(session),
        )
        lesson.status = LessonStatus.CANCELLED_LATE if late else LessonStatus.CANCELLED
        request.status = ChangeRequestStatus.APPROVED
        request.resolved_at = now
        await session.flush()
    else:
        if data.new_starts_at is None:
            raise NewStartsAtRequired
        try:
            # Савепоинт: нарушение уникальности не должно убить транзакцию запроса.
            async with session.begin_nested():
                lesson.starts_at = data.new_starts_at
                if lesson.series_id is not None:
                    lesson.is_detached = True
                request.status = ChangeRequestStatus.APPROVED
                request.resolved_at = now
                await session.flush()
        except IntegrityError as exc:
            if _SLOT_CONSTRAINT not in str(exc.orig):
                raise
            raise LessonSlotTaken from exc
        warnings = await find_overlaps(
            session,
            starts_at=lesson.starts_at,
            duration_min=lesson.duration_min,
            tz=await get_timezone(session),
            exclude_ids=[lesson.id],
        )
    return await _resolved(session, request.id, warnings)


async def reject_change_request(
    session: AsyncSession,
    request_id: uuid.UUID,
    data: ChangeRequestReject,
    *,
    now: datetime,
) -> ChangeRequestResolved:
    """Отклонение ждущего запроса с ответом семье; занятие не меняется (даже устаревшее)."""
    from app.lessons.service import _lock_lesson  # service импортирует этот модуль

    lesson_id = await session.scalar(
        select(ChangeRequest.lesson_id).where(ChangeRequest.id == request_id)
    )
    if lesson_id is None:
        raise ChangeRequestNotFound
    await _lock_lesson(session, lesson_id)  # порядок блокировок: занятие → запрос
    request = await _lock_request(session, request_id)
    if request.status is not ChangeRequestStatus.PENDING:
        raise ChangeRequestNotPending
    request.status = ChangeRequestStatus.REJECTED
    request.tutor_response = data.tutor_response
    request.resolved_at = now
    await session.flush()
    return await _resolved(session, request.id, [])
