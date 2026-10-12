import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
from app.families import service as families_service
from app.families.models import Child, Family
from app.leads import service as leads_service
from app.leads.models import Lead
from app.lessons.errors import (
    LessonNotDeletable,
    LessonNotEditable,
    LessonNotFound,
    LessonNotStarted,
    LessonSlotTaken,
    ScheduleRangeInvalid,
)
from app.lessons.models import Lesson, LessonKind, LessonNote, LessonStatus
from app.lessons.overlaps import BUSY_STATUSES, find_overlaps
from app.lessons.schemas import (
    AdminLessonDetail,
    AdminLessonItem,
    LessonCreate,
    LessonForFamily,
    LessonForFamilyDetail,
    LessonNotes,
    LessonNotesUpdate,
    LessonSaved,
    LessonStudent,
    LessonUpdate,
    OverlapWarning,
    TrialCreate,
)
from app.lessons.tutor_settings import get_timezone

MAX_RANGE = timedelta(days=62)
# Эти статусы можно выставить только начавшемуся занятию.
_STARTED_ONLY = (LessonStatus.COMPLETED, LessonStatus.NO_SHOW)
_SLOT_CONSTRAINT = "uq_lessons_series_id_starts_at"


def check_range(start: datetime, end: datetime) -> None:
    """Период запроса занятий: `start < end` и не больше 62 дней, иначе 422."""
    if not start < end or end - start > MAX_RANGE:
        raise ScheduleRangeInvalid


def _student(
    lesson: Lesson, child: Child | None, family: Family | None, lead: Lead | None
) -> LessonStudent:
    if lead is not None:
        return LessonStudent(
            child_id=None,
            lead_id=lead.id,
            name=lead.child_name,
            family_id=None,
            family_name=None,
        )
    if child is None or family is None:  # CHECK lessons.exactly_one_owner + FK
        raise RuntimeError(f"У занятия {lesson.id} нет владельца")
    return LessonStudent(
        child_id=child.id,
        lead_id=None,
        name=child.full_name,
        family_id=family.id,
        family_name=family.name,
    )


def _item_data(
    lesson: Lesson,
    child: Child | None,
    family: Family | None,
    lead: Lead | None,
    *,
    has_notes: bool,
) -> dict[str, Any]:
    # Эффективная ссылка (уточнение 4): своя, иначе ссылка ученика; у пробного — только своя.
    join_url = lesson.meeting_url or (child.default_meeting_url if child is not None else None)
    return {
        "id": lesson.id,
        "kind": lesson.kind,
        "status": lesson.status,
        "starts_at": lesson.starts_at,
        "duration_min": lesson.duration_min,
        "series_id": lesson.series_id,
        "is_detached": lesson.is_detached,
        "meeting_url": lesson.meeting_url,
        "join_url": join_url,
        "student": _student(lesson, child, family, lead),
        "has_notes": has_notes,
    }


def _joined(*columns: Any) -> Select[Any]:
    return (
        select(Lesson, Child, Family, Lead, *columns)
        .outerjoin(Child, Child.id == Lesson.child_id)
        .outerjoin(Family, Family.id == Child.family_id)
        .outerjoin(Lead, Lead.id == Lesson.lead_id)
    )


def _items_stmt() -> Select[Any]:
    """Выборка карточек занятий по возрастанию времени; условия добавляет вызывающий."""
    has_notes = exists().where(
        LessonNote.lesson_id == Lesson.id,
        or_(LessonNote.shared_text != "", LessonNote.private_text != ""),
    )
    return _joined(has_notes).order_by(Lesson.starts_at, Lesson.id)


async def _run_items(session: AsyncSession, stmt: Select[Any]) -> list[AdminLessonItem]:
    return [
        AdminLessonItem(**_item_data(lesson, child, family, lead, has_notes=noted))
        for lesson, child, family, lead, noted in await session.execute(stmt)
    ]


async def list_admin_lessons(
    session: AsyncSession, *, start: datetime, end: datetime, child_id: uuid.UUID | None
) -> list[AdminLessonItem]:
    """Занятия с `starts_at ∈ [start, end)` по возрастанию времени."""
    stmt = _items_stmt().where(Lesson.starts_at >= start, Lesson.starts_at < end)
    if child_id is not None:
        stmt = stmt.where(Lesson.child_id == child_id)
    return await _run_items(session, stmt)


async def get_admin_lesson(session: AsyncSession, lesson_id: uuid.UUID) -> AdminLessonDetail:
    stmt = _joined(LessonNote).outerjoin(LessonNote, LessonNote.lesson_id == Lesson.id)
    stmt = stmt.where(Lesson.id == lesson_id)
    row = (await session.execute(stmt.execution_options(populate_existing=True))).one_or_none()
    if row is None:
        raise LessonNotFound
    lesson, child, family, lead, note = row
    notes = LessonNotes(
        shared_text=note.shared_text if note else "",
        private_text=note.private_text if note else "",
    )
    return AdminLessonDetail(
        **_item_data(
            lesson, child, family, lead, has_notes=bool(notes.shared_text or notes.private_text)
        ),
        notes=notes,
        created_at=lesson.created_at,
    )


async def _saved(
    session: AsyncSession, lesson_id: uuid.UUID, warnings: list[OverlapWarning]
) -> LessonSaved:
    detail = await get_admin_lesson(session, lesson_id)
    return LessonSaved(**detail.model_dump(), warnings=warnings)


async def create_lesson(session: AsyncSession, data: LessonCreate, *, now: datetime) -> LessonSaved:
    """Разовое занятие ученика (`kind=regular`, вне серии); прошлое время допустимо.

    `now` в сигнатуре для единообразия с остальными операциями: создание от него не зависит.
    """
    child = await families_service.get_active_child(session, data.child_id)
    tz = await get_timezone(session)
    warnings = await find_overlaps(
        session, starts_at=data.starts_at, duration_min=data.duration_min, tz=tz
    )
    lesson = Lesson(
        child_id=child.id,
        kind=LessonKind.REGULAR,
        starts_at=data.starts_at,
        duration_min=data.duration_min,
        meeting_url=str(data.meeting_url) if data.meeting_url else None,
    )
    session.add(lesson)
    await session.flush()
    return await _saved(session, lesson.id, warnings)


async def schedule_trial(
    session: AsyncSession, lead_id: uuid.UUID, data: TrialCreate, *, now: datetime
) -> LessonSaved:
    """Пробное занятие заявки (уточнение 11): заявка уходит в `trial_scheduled`.

    Статус меняется первым: он блокирует заявку и отсекает повторный запрос (409) до создания
    занятия. Время может быть любым, в том числе прошедшим, поэтому `now` не используется
    (параметр — для единообразия с остальными операциями). Пересечения — только предупреждения.
    """
    tz = await get_timezone(session)
    local = data.starts_at.astimezone(tz)
    lead = await leads_service.schedule_trial_status(
        session, lead_id, comment=f"Пробное занятие {local:%d.%m.%Y %H:%M}"
    )
    warnings = await find_overlaps(
        session, starts_at=data.starts_at, duration_min=data.duration_min, tz=tz
    )
    lesson = Lesson(
        lead_id=lead.id,
        child_id=None,
        kind=LessonKind.TRIAL,
        starts_at=data.starts_at,
        duration_min=data.duration_min,
        meeting_url=str(data.meeting_url) if data.meeting_url else None,
    )
    session.add(lesson)
    await session.flush()
    return await _saved(session, lesson.id, warnings)


async def list_trial_lessons(session: AsyncSession, lead_id: uuid.UUID) -> list[AdminLessonItem]:
    """Все пробные занятия заявки по возрастанию времени; нет заявки — `LeadNotFound`."""
    await leads_service.ensure_lead_visible(session, lead_id)
    stmt = _items_stmt().where(Lesson.lead_id == lead_id, Lesson.kind == LessonKind.TRIAL)
    return await _run_items(session, stmt)


async def _lock_lesson(session: AsyncSession, lesson_id: uuid.UUID) -> Lesson:
    stmt = (
        select(Lesson)
        .where(Lesson.id == lesson_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    lesson = await session.scalar(stmt)
    if lesson is None:
        raise LessonNotFound
    return lesson


async def update_lesson(
    session: AsyncSession, lesson_id: uuid.UUID, data: LessonUpdate, *, now: datetime
) -> LessonSaved:
    """Правка занятия (уточнение 7); все проверки идут до первого изменения.

    `status` применяется первым: допустимость правки времени, длительности и ссылки
    определяется итоговым статусом. Пересечения считаются при смене времени или длительности
    и при возврате занятия из отменённого в учитываемый статус.
    """
    lesson = await _lock_lesson(session, lesson_id)
    fields = data.model_fields_set

    new_status = data.status if data.status is not None else lesson.status
    if new_status in _STARTED_ONLY and lesson.starts_at > now:
        raise LessonNotStarted
    if fields & {"starts_at", "duration_min", "meeting_url"} and new_status is not (
        LessonStatus.SCHEDULED
    ):
        raise LessonNotEditable

    moved = data.starts_at is not None and data.starts_at != lesson.starts_at
    resized = data.duration_min is not None and data.duration_min != lesson.duration_min
    reactivated = new_status in BUSY_STATUSES and lesson.status not in BUSY_STATUSES

    try:
        # Изменения — внутри савепоинта (он сам сбрасывает накопленное при входе, поэтому правки
        # не могут быть сделаны до него): нарушение уникальности не должно убить транзакцию.
        async with session.begin_nested():
            lesson.status = new_status
            if data.starts_at is not None and moved:
                lesson.starts_at = data.starts_at
                if lesson.series_id is not None:
                    lesson.is_detached = True
            if data.duration_min is not None:
                lesson.duration_min = data.duration_min
            if "meeting_url" in fields:
                lesson.meeting_url = str(data.meeting_url) if data.meeting_url else None
            await session.flush()
    except IntegrityError as exc:
        if _SLOT_CONSTRAINT not in str(exc.orig):
            raise
        raise LessonSlotTaken from exc

    warnings: list[OverlapWarning] = []
    if moved or resized or reactivated:
        warnings = await find_overlaps(
            session,
            starts_at=lesson.starts_at,
            duration_min=lesson.duration_min,
            tz=await get_timezone(session),
            exclude_ids=[lesson.id],
        )
    return await _saved(session, lesson.id, warnings)


async def delete_lesson(session: AsyncSession, lesson_id: uuid.UUID, *, now: datetime) -> None:
    """Удаляет только будущее занятие в статусе `scheduled`; заметки уходят каскадом БД."""
    lesson = await _lock_lesson(session, lesson_id)
    if lesson.status is not LessonStatus.SCHEDULED or lesson.starts_at <= now:
        raise LessonNotDeletable
    await session.delete(lesson)
    await session.flush()


async def save_notes(
    session: AsyncSession, lesson_id: uuid.UUID, data: LessonNotesUpdate
) -> LessonNotes:
    # Блокировка занятия: заметки не пишутся в строку, которую параллельно удаляют.
    await _lock_lesson(session, lesson_id)
    stmt = pg_insert(LessonNote).values(
        lesson_id=lesson_id, shared_text=data.shared_text, private_text=data.private_text
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[LessonNote.lesson_id],
        set_={
            "shared_text": stmt.excluded.shared_text,
            "private_text": stmt.excluded.private_text,
            "updated_at": func.now(),
        },
    )
    await session.execute(stmt)
    return LessonNotes(shared_text=data.shared_text, private_text=data.private_text)


def _family_data(lesson: Lesson, child: Child, shared_text: str | None) -> dict[str, Any]:
    return {
        "id": lesson.id,
        "child_id": child.id,
        "child_name": child.full_name,
        "starts_at": lesson.starts_at,
        "duration_min": lesson.duration_min,
        "status": lesson.status,
        "join_url": lesson.meeting_url or child.default_meeting_url,
        "has_shared_note": bool(shared_text and shared_text.strip()),
    }


def _family_stmt(child_ids: frozenset[uuid.UUID]) -> Select[Any]:
    """Регулярные занятия детей из области доступа с общей заметкой.

    Колонка `private_text` в выборку не входит: до семьи она не доходит даже в памяти.
    """
    columns: list[Any] = [Lesson, Child, LessonNote.shared_text]
    return (
        select(*columns)
        .join(Child, Child.id == Lesson.child_id)
        .outerjoin(LessonNote, LessonNote.lesson_id == Lesson.id)
        .where(Lesson.kind == LessonKind.REGULAR, Lesson.child_id.in_(child_ids))
    )


async def list_family_lessons(
    session: AsyncSession,
    child_ids: frozenset[uuid.UUID],
    *,
    start: datetime,
    end: datetime,
    child_id: uuid.UUID | None,
) -> list[LessonForFamily]:
    """Занятия детей семьи с `starts_at ∈ [start, end)`; `child_id` вне области — 404."""
    if child_id is not None and child_id not in child_ids:
        raise NotFound("Ученик не найден", code="child_not_found")
    stmt = _family_stmt(child_ids).where(Lesson.starts_at >= start, Lesson.starts_at < end)
    if child_id is not None:
        stmt = stmt.where(Lesson.child_id == child_id)
    stmt = stmt.order_by(Lesson.starts_at, Lesson.id)
    return [
        LessonForFamily(**_family_data(lesson, child, shared))
        for lesson, child, shared in await session.execute(stmt)
    ]


async def get_family_lesson(
    session: AsyncSession, child_ids: frozenset[uuid.UUID], lesson_id: uuid.UUID
) -> LessonForFamilyDetail:
    """Занятие из области доступа; чужое, пробное или несуществующее — `LessonNotFound`."""
    stmt = _family_stmt(child_ids).where(Lesson.id == lesson_id)
    row = (await session.execute(stmt.execution_options(populate_existing=True))).one_or_none()
    if row is None:
        raise LessonNotFound
    lesson, child, shared = row
    return LessonForFamilyDetail(
        **_family_data(lesson, child, shared),
        shared_note=shared if shared and shared.strip() else None,
    )
