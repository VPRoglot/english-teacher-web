"""Админ-операции над сериями занятий: создание, правка «с даты», архивирование, список."""

import uuid
from collections.abc import Collection
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.families import service as families_service
from app.families.models import Child
from app.lessons.errors import SeriesArchived, SeriesDateInvalid, SeriesNotFound
from app.lessons.generation import (
    lock_series,
    materialize_series,
    reconcile_series,
    series_shape,
)
from app.lessons.models import Lesson, LessonSeries, LessonStatus
from app.lessons.overlaps import MAX_WARNINGS, find_overlaps
from app.lessons.requests_service import lesson_ids_with_requests
from app.lessons.schemas import (
    OverlapWarning,
    SeriesCreate,
    SeriesDetail,
    SeriesSaved,
    SeriesUpdate,
)
from app.lessons.tutor_settings import get_timezone


def _detail(series: LessonSeries, child_name: str) -> SeriesDetail:
    return SeriesDetail(
        id=series.id,
        child_id=series.child_id,
        child_name=child_name,
        rrule=series.rrule,
        local_start_time=series.local_start_time,
        duration_min=series.duration_min,
        meeting_url=series.meeting_url,
        starts_on=series.starts_on,
        ends_on=series.ends_on,
        archived_at=series.archived_at,
    )


async def _warnings(
    session: AsyncSession, lessons: Collection[Lesson], *, tz: ZoneInfo
) -> list[OverlapWarning]:
    """Пересечения созданных и изменённых занятий с остальными (не больше `MAX_WARNINGS`).

    Занятия самой правки друг с другом не сравниваются; одно и то же чужое занятие
    попадает в предупреждения один раз.
    """
    own_ids = {lesson.id for lesson in lessons}
    found: dict[uuid.UUID, OverlapWarning] = {}
    for lesson in sorted(lessons, key=lambda item: item.starts_at):
        if len(found) >= MAX_WARNINGS:
            break
        for warning in await find_overlaps(
            session,
            starts_at=lesson.starts_at,
            duration_min=lesson.duration_min,
            tz=tz,
            exclude_ids=own_ids,
        ):
            found.setdefault(warning.lesson_id, warning)
    return sorted(found.values(), key=lambda item: (item.starts_at, item.lesson_id))[:MAX_WARNINGS]


async def _saved(
    session: AsyncSession,
    series: LessonSeries,
    *,
    created: Collection[Lesson] = (),
    updated: Collection[Lesson] = (),
    removed: int = 0,
    tz: ZoneInfo,
) -> SeriesSaved:
    child = await session.get(Child, series.child_id)
    if child is None:  # FK lesson_series.child_id
        raise RuntimeError(f"У серии {series.id} нет ученика")
    return SeriesSaved(
        series=_detail(series, child.full_name),
        lessons_created=len(created),
        lessons_updated=len(updated),
        lessons_removed=removed,
        warnings=await _warnings(session, [*created, *updated], tz=tz),
    )


async def list_series(
    session: AsyncSession, *, child_id: uuid.UUID | None, include_archived: bool
) -> list[SeriesDetail]:
    stmt = (
        select(LessonSeries, Child.full_name)
        .join(Child, Child.id == LessonSeries.child_id)
        .order_by(LessonSeries.starts_on, LessonSeries.id)
    )
    if child_id is not None:
        stmt = stmt.where(LessonSeries.child_id == child_id)
    if not include_archived:
        stmt = stmt.where(LessonSeries.archived_at.is_(None))
    return [_detail(series, name) for series, name in await session.execute(stmt)]


async def create_series(session: AsyncSession, data: SeriesCreate, *, now: datetime) -> SeriesSaved:
    """Серия ребёнка; занятия на 8 недель вперёд создаются сразу, в той же транзакции."""
    child = await families_service.get_active_child(session, data.child_id)
    tz = await get_timezone(session, lock=True)
    series = LessonSeries(
        child_id=child.id,
        rrule=data.rrule,
        local_start_time=data.local_start_time,
        duration_min=data.duration_min,
        meeting_url=str(data.meeting_url) if data.meeting_url else None,
        starts_on=data.starts_on,
        ends_on=data.ends_on,
    )
    session.add(series)
    await session.flush()
    created = await materialize_series(session, series, tz=tz, now=now)
    return await _saved(session, series, created=created, tz=tz)


@dataclass(frozen=True)
class _Rule:
    """Параметры серии, которые может менять правка."""

    rrule: str
    local_start_time: time
    duration_min: int
    meeting_url: str | None
    ends_on: date | None


def _merged(series: LessonSeries, data: SeriesUpdate) -> _Rule:
    fields = data.model_fields_set
    return _Rule(
        rrule=data.rrule if data.rrule is not None else series.rrule,
        local_start_time=(
            data.local_start_time if data.local_start_time is not None else series.local_start_time
        ),
        duration_min=data.duration_min if data.duration_min is not None else series.duration_min,
        meeting_url=(
            (str(data.meeting_url) if data.meeting_url else None)
            if "meeting_url" in fields
            else series.meeting_url
        ),
        ends_on=data.ends_on if "ends_on" in fields else series.ends_on,
    )


async def update_series(
    session: AsyncSession,
    series_id: uuid.UUID,
    data: SeriesUpdate,
    *,
    from_day: date,
    now: datetime,
) -> SeriesSaved:
    """Правка «эта и последующие» с местной даты `from_day`.

    - `from_day <= starts_on` — серия правится на месте;
    - иначе серия разделяется: у старой `ends_on = from_day − 1`, новая начинается с `from_day`.

    Занятия не пересоздаются, а сверяются по дате вхождения (`reconcile_series`): будущие
    запланированные правятся на месте (id и заметки сохраняются, при разделении переходят в
    новую серию), прошедшие, отмеченные и отсоединённые остаются у прежней серии, удалённые
    не воскресают. Правка, не меняющая ни одного параметра, серию не разделяет.
    """
    # Порядок блокировок как у смены пояса: настройки (FOR SHARE) → серия.
    tz = await get_timezone(session, lock=True)
    series = await lock_series(session, series_id)
    if series is None:
        raise SeriesNotFound
    if series.archived_at is not None:
        raise SeriesArchived

    if from_day < now.astimezone(tz).date():
        raise SeriesDateInvalid(["query", "from"], "Дата не может быть в прошлом")
    if series.ends_on is not None and from_day > series.ends_on:
        raise SeriesDateInvalid(["query", "from"], "Дата позже окончания расписания")
    rule = _merged(series, data)
    if rule.ends_on is not None and rule.ends_on < max(from_day, series.starts_on):
        raise SeriesDateInvalid(["body", "ends_on"], "Окончание не может быть раньше начала")

    current = _Rule(
        series.rrule,
        series.local_start_time,
        series.duration_min,
        series.meeting_url,
        series.ends_on,
    )
    if rule == current:
        return await _saved(session, series, tz=tz)

    previous = series_shape(series)
    if from_day <= series.starts_on:
        target = series
        target.rrule = rule.rrule
        target.local_start_time = rule.local_start_time
        target.duration_min = rule.duration_min
        target.meeting_url = rule.meeting_url
        target.ends_on = rule.ends_on
        reconcile_from = series.starts_on
        lessons_from = None
    else:
        target = LessonSeries(
            child_id=series.child_id,
            rrule=rule.rrule,
            local_start_time=rule.local_start_time,
            duration_min=rule.duration_min,
            meeting_url=rule.meeting_url,
            starts_on=from_day,
            ends_on=rule.ends_on,
        )
        session.add(target)
        series.ends_on = from_day - timedelta(days=1)
        reconcile_from = from_day
        lessons_from = series
    await session.flush()

    result = await reconcile_series(
        session,
        target,
        previous=previous,
        lessons_from=lessons_from,
        from_day=reconcile_from,
        tz=tz,
        now=now,
    )
    return await _saved(
        session,
        target,
        created=result.created,
        updated=result.updated,
        removed=result.removed,
        tz=tz,
    )


async def archive_series(session: AsyncSession, series_id: uuid.UUID, *, now: datetime) -> None:
    """Завершает серию: будущие запланированные неотсоединённые занятия удаляются.

    Занятия, у которых есть запрос (в любом статусе), остаются.
    """
    series = await lock_series(session, series_id)
    if series is None:
        raise SeriesNotFound
    if series.archived_at is not None:
        raise SeriesArchived
    series.archived_at = now
    # Сначала блокируем кандидатов (порядок блокировок: серия → занятие), потом смотрим запросы:
    # запрос, созданный параллельно, ждёт нашей блокировки и не получает RESTRICT-ошибку.
    candidates = list(
        await session.scalars(
            select(Lesson.id)
            .where(
                Lesson.series_id == series.id,
                Lesson.status == LessonStatus.SCHEDULED,
                Lesson.is_detached.is_(False),
                Lesson.starts_at > now,
            )
            .order_by(Lesson.id)
            .with_for_update()
        )
    )
    protected = await lesson_ids_with_requests(session, candidates)
    doomed = [lesson_id for lesson_id in candidates if lesson_id not in protected]
    if doomed:
        await session.execute(delete(Lesson).where(Lesson.id.in_(doomed)))
    await session.flush()


async def archive_child_series(
    session: AsyncSession, child_ids: Collection[uuid.UUID], *, now: datetime
) -> int:
    """Завершает каждую активную серию этих детей; возвращает число завершённых серий.

    Серии блокируются в порядке id, поэтому параллельные архивы не взаимоблокируются. Серия,
    которую успели завершить между выборкой и блокировкой, пропускается.
    """
    if not child_ids:
        return 0
    series_ids = await session.scalars(
        select(LessonSeries.id)
        .where(LessonSeries.child_id.in_(child_ids), LessonSeries.archived_at.is_(None))
        .order_by(LessonSeries.id)
    )
    ended = 0
    for series_id in list(series_ids):
        try:
            await archive_series(session, series_id, now=now)
        except SeriesArchived:
            continue
        ended += 1
    return ended
