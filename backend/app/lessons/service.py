import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import Select, exists, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.families import service as families_service
from app.families.models import Child, Family
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
    LessonNotes,
    LessonNotesUpdate,
    LessonSaved,
    LessonStudent,
    LessonUpdate,
    OverlapWarning,
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


async def list_admin_lessons(
    session: AsyncSession, *, start: datetime, end: datetime, child_id: uuid.UUID | None
) -> list[AdminLessonItem]:
    """Занятия с `starts_at ∈ [start, end)` по возрастанию времени."""
    has_notes = exists().where(
        LessonNote.lesson_id == Lesson.id,
        or_(LessonNote.shared_text != "", LessonNote.private_text != ""),
    )
    stmt = (
        _joined(has_notes)
        .where(Lesson.starts_at >= start, Lesson.starts_at < end)
        .order_by(Lesson.starts_at, Lesson.id)
    )
    if child_id is not None:
        stmt = stmt.where(Lesson.child_id == child_id)
    return [
        AdminLessonItem(**_item_data(lesson, child, family, lead, has_notes=noted))
        for lesson, child, family, lead, noted in await session.execute(stmt)
    ]


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
    if not await session.scalar(select(exists().where(Lesson.id == lesson_id))):
        raise LessonNotFound
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
