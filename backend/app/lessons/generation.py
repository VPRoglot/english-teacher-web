"""Материализация серий: занятия создаются вперёд от «фронтира» `generated_through`.

Фронтир не даёт ежедневной задаче воскресить перенесённое или удалённое занятие серии:
создаются только даты после него. Занятие серии помнит `occurrence_date` — местную дату
вхождения правила; при переносе она не меняется, поэтому по ней смена пояса и правка
серии находят «то же» занятие и правят его на месте (id и заметки сохраняются), а не
пересоздают. `ON CONFLICT DO NOTHING` отвечает за идемпотентность повторов и гонок.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import structlog
from sqlalchemy import Select, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import new_uuid7
from app.families.models import Child, Family
from app.lessons.models import Lesson, LessonKind, LessonSeries, LessonStatus
from app.lessons.recurrence import occurrences

log = structlog.get_logger("app.lessons")

HORIZON_DAYS = 56  # 8 недель вперёд


def local_midnight(day: date, tz: ZoneInfo) -> datetime:
    """Начало местного дня в UTC (несуществующая полночь сдвигается вперёд)."""
    return datetime.combine(day, time.min, tzinfo=tz).astimezone(UTC)


def _local_instant(day: date, local_time: time, tz: ZoneInfo) -> datetime:
    return datetime.combine(day, local_time, tzinfo=tz).astimezone(UTC)


@dataclass(frozen=True)
class SeriesShape:
    """Правило серии до правки: нужно, чтобы отличить удалённое занятие от нового."""

    rrule: str
    starts_on: date
    ends_on: date | None
    local_start_time: time
    generated_through: date | None


def _dated_moments(
    series: LessonSeries | SeriesShape,
    *,
    tz: ZoneInfo,
    first_day: date,
    last_day: date,
) -> list[tuple[date, datetime]]:
    """Вхождения правила в окне: (местная дата, момент UTC)."""
    moments = occurrences(
        series.rrule,
        starts_on=series.starts_on,
        ends_on=series.ends_on,
        local_time=series.local_start_time,
        tz=tz,
        first_day=first_day,
        last_day=last_day,
    )
    # Дата вхождения — дата момента в поясе: перевод сдвигает время максимум на часы внутри дня.
    return [(moment.astimezone(tz).date(), moment) for moment in moments]


async def _insert_lessons(
    session: AsyncSession, series: LessonSeries, items: list[tuple[date, datetime]]
) -> list[Lesson]:
    """Вставка занятий серии; существующие слоты и даты тихо пропускаются (идемпотентность)."""
    if not items:
        return []
    stmt = (
        insert(Lesson)
        .values(
            [
                {
                    "id": new_uuid7(),
                    "series_id": series.id,
                    "child_id": series.child_id,
                    "kind": LessonKind.REGULAR,
                    "starts_at": moment,
                    "occurrence_date": day,
                    "duration_min": series.duration_min,
                    "meeting_url": series.meeting_url,
                    "is_detached": False,
                    "status": LessonStatus.SCHEDULED,
                }
                for day, moment in items
            ]
        )
        # Без цели: повтор гасят и UNIQUE (series_id, starts_at), и (series_id, occurrence_date).
        .on_conflict_do_nothing()
        .returning(Lesson)
    )
    result = await session.scalars(stmt, execution_options={"populate_existing": True})
    return sorted(result.all(), key=lambda lesson: lesson.starts_at)


async def materialize_series(
    session: AsyncSession, series: LessonSeries, *, tz: ZoneInfo, now: datetime
) -> list[Lesson]:
    """Создаёт занятия серии для местных дат после фронтира, до `сегодня + HORIZON_DAYS`.

    Вызывающий держит блокировку серии (`SELECT … FOR UPDATE`). Возвращает только созданные
    занятия; повторный вызов с тем же `now` ничего не создаёт.
    """
    today = now.astimezone(tz).date()
    horizon_end = today + timedelta(days=HORIZON_DAYS)
    first_day = max(series.starts_on, today)
    if series.generated_through is not None:
        first_day = max(first_day, series.generated_through + timedelta(days=1))

    items = [
        (day, moment)
        for day, moment in _dated_moments(series, tz=tz, first_day=first_day, last_day=horizon_end)
        if moment >= now
    ]
    created = await _insert_lessons(session, series, items)
    series.generated_through = max(series.generated_through or horizon_end, horizon_end)
    await session.flush()
    return created


async def shift_series_timezone(
    session: AsyncSession,
    series: LessonSeries,
    *,
    old_tz: ZoneInfo,
    new_tz: ZoneInfo,
    now: datetime,
) -> list[Lesson]:
    """Сохраняет местное время будущих занятий серии при смене пояса репетитора.

    Каждое будущее `scheduled` занятие без `is_detached` правится на месте: тот же id и
    заметки, `starts_at` = (`occurrence_date` + `local_start_time`) в новом поясе. Занятие,
    чей новый момент уже прошёл, тоже сдвигается (его нужно отметить), а не удаляется.
    Остальные занятия серии сохраняют свой момент. Если новый момент занят другим занятием
    серии, занятие остаётся как есть, а в лог идёт `series_shift_conflict`.
    Фронтир — местная дата, он не меняется. Вызывающий держит блокировку серии.
    """
    stmt = (
        select(Lesson)
        .where(
            Lesson.series_id == series.id,
            Lesson.status == LessonStatus.SCHEDULED,
            Lesson.is_detached.is_(False),
            Lesson.occurrence_date.is_not(None),
            Lesson.starts_at > now,
        )
        .order_by(Lesson.starts_at)
        .execution_options(populate_existing=True)
    )
    targets: list[tuple[Lesson, datetime]] = []
    for lesson in await session.scalars(stmt):
        if lesson.occurrence_date is None:  # отфильтровано в запросе; нужно для типов
            continue
        new_start = _local_instant(lesson.occurrence_date, series.local_start_time, new_tz)
        if new_start != lesson.starts_at:
            targets.append((lesson, new_start))
    # Сдвиг на фиксированное смещение в сторону конца: идём с конца, чтобы новый момент
    # одного занятия не упирался в ещё не сдвинутое соседнее.
    if targets and targets[0][1] > targets[0][0].starts_at:
        targets.reverse()

    shifted: list[Lesson] = []
    for lesson, new_start in targets:
        old_start = lesson.starts_at
        try:
            async with session.begin_nested():
                lesson.starts_at = new_start
                await session.flush()
        except IntegrityError:
            await session.refresh(lesson)
            log.warning(
                "series_shift_conflict",
                series_id=str(series.id),
                lesson_id=str(lesson.id),
                starts_at=old_start.isoformat(),
                wanted_starts_at=new_start.isoformat(),
                old_tz=old_tz.key,
                new_tz=new_tz.key,
            )
            continue
        shifted.append(lesson)
    return sorted(shifted, key=lambda lesson: lesson.starts_at)


def series_shape(series: LessonSeries) -> SeriesShape:
    return SeriesShape(
        rrule=series.rrule,
        starts_on=series.starts_on,
        ends_on=series.ends_on,
        local_start_time=series.local_start_time,
        generated_through=series.generated_through,
    )


@dataclass
class Reconciled:
    created: list[Lesson]
    updated: list[Lesson]  # существующие строки, изменённые на месте


def _is_replaceable(lesson: Lesson, now: datetime) -> bool:
    """Будущее неотмеченное неотсоединённое занятие: правка серии вправе его менять."""
    return (
        lesson.status is LessonStatus.SCHEDULED
        and not lesson.is_detached
        and lesson.starts_at > now
    )


async def reconcile_series(
    session: AsyncSession,
    series: LessonSeries,
    *,
    previous: SeriesShape,
    lessons_from: LessonSeries | None = None,
    from_day: date,
    tz: ZoneInfo,
    now: datetime,
) -> Reconciled:
    """Сверяет занятия с правилом серии после правки, по датам вхождения, начиная с `from_day`.

    `series` — серия после правки (при разделении — новая), `lessons_from` — чьи занятия
    сверяются (при разделении — старая серия), `previous` — снимок правила до правки.
    Для каждой даты нового расписания:
    - будущее неотмеченное неотсоединённое занятие правится на месте (время, длительность,
      ссылка, серия) — id и заметки сохраняются;
    - отмеченное, отсоединённое или начавшееся занятие остаётся, двойник не создаётся;
    - дата, которую раньше давало правило и по которой занятия нет, — удалена репетитором
      и не создаётся заново;
    - остальные даты получают новое занятие.
    Будущие неотмеченные занятия на датах, ушедших из расписания, удаляются.
    Вызывающий держит блокировку серий.
    """
    source = lessons_from or series
    today = now.astimezone(tz).date()
    start = max(from_day, series.starts_on, today)
    horizon = today + timedelta(days=HORIZON_DAYS)

    wanted = {
        day: moment
        for day, moment in _dated_moments(series, tz=tz, first_day=start, last_day=horizon)
        if moment >= now
    }
    previous_days: set[date] = set()
    if previous.generated_through is not None:
        previous_days = {
            day
            for day, _ in _dated_moments(
                previous, tz=tz, first_day=start, last_day=previous.generated_through
            )
        }

    stmt = (
        select(Lesson)
        .where(Lesson.series_id == source.id, Lesson.occurrence_date >= start)
        .execution_options(populate_existing=True)
    )
    existing = {
        lesson.occurrence_date: lesson
        for lesson in await session.scalars(stmt)
        if lesson.occurrence_date is not None
    }

    for day, lesson in existing.items():
        if day not in wanted and _is_replaceable(lesson, now):
            await session.delete(lesson)
    await session.flush()

    updated: list[Lesson] = []
    to_insert: list[tuple[date, datetime]] = []
    for day, moment in sorted(wanted.items()):
        current = existing.get(day)
        if current is None:
            if day not in previous_days:
                to_insert.append((day, moment))
        elif _is_replaceable(current, now) and await _apply_series_to_lesson(
            session, current, series, moment
        ):
            updated.append(current)
    created = await _insert_lessons(session, series, to_insert)

    series.generated_through = max(series.generated_through or start - timedelta(days=1), horizon)
    await session.flush()
    return Reconciled(created=created, updated=updated)


async def _apply_series_to_lesson(
    session: AsyncSession, lesson: Lesson, series: LessonSeries, moment: datetime
) -> bool:
    """Переносит параметры серии на занятие. Возвращает True, если оно изменилось."""
    if (
        lesson.starts_at == moment
        and lesson.duration_min == series.duration_min
        and lesson.meeting_url == series.meeting_url
        and lesson.series_id == series.id
    ):
        return False
    try:
        async with session.begin_nested():
            lesson.starts_at = moment
            lesson.duration_min = series.duration_min
            lesson.meeting_url = series.meeting_url
            lesson.series_id = series.id
            await session.flush()
    except IntegrityError:
        # Момент занят другим занятием серии (например, перенесённым вручную): оставляем как есть.
        await session.refresh(lesson)
        log.warning(
            "series_reconcile_conflict",
            series_id=str(series.id),
            lesson_id=str(lesson.id),
            wanted_starts_at=moment.isoformat(),
        )
        return False
    return True


def active_series_ids_stmt(today: date) -> Select[uuid.UUID]:
    """Серии, которым ещё нужны занятия: не архивные, не закончились, ребёнок и семья активны."""
    return (
        select(LessonSeries.id)
        .join(Child, Child.id == LessonSeries.child_id)
        .join(Family, Family.id == Child.family_id)
        .where(
            LessonSeries.archived_at.is_(None),
            or_(LessonSeries.ends_on.is_(None), LessonSeries.ends_on >= today),
            Child.archived_at.is_(None),
            Family.archived_at.is_(None),
        )
        .order_by(LessonSeries.id)
    )


async def lock_series(session: AsyncSession, series_id: uuid.UUID) -> LessonSeries | None:
    """Блокирует серию до конца транзакции и перечитывает её актуальное состояние."""
    stmt = (
        select(LessonSeries)
        .where(LessonSeries.id == series_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    return await session.scalar(stmt)


async def materialize_all(sessionmaker: async_sessionmaker[AsyncSession], *, now: datetime) -> int:
    """Доводит до горизонта все активные серии; у каждой серии своя транзакция.

    Сбой одной серии не мешает остальным: он логируется (`series_materialize_failed`), а в конце
    бросается исключение, чтобы задача повторилась. Повтор безопасен: фронтир серии сдвинут,
    вставка идемпотентна. Возвращает число созданных занятий.
    """
    # Отложенный импорт: tutor_settings использует этот модуль для смены пояса.
    from app.lessons.tutor_settings import get_timezone

    async with sessionmaker() as session:
        today = now.astimezone(await get_timezone(session)).date()
        series_ids = list(await session.scalars(active_series_ids_stmt(today)))

    created = 0
    failed = 0
    for series_id in series_ids:
        try:
            async with sessionmaker() as session:
                series = await lock_series(session, series_id)
                if series is None or series.archived_at is not None:
                    continue
                # Пояс читается под блокировкой серии: смена пояса сдвигает серию под той же
                # блокировкой, поэтому генерация по старому поясу не пересечётся со сдвигом.
                tz = await get_timezone(session)
                count = len(await materialize_series(session, series, tz=tz, now=now))
                await session.commit()
        except Exception:
            failed += 1
            log.error("series_materialize_failed", series_id=str(series_id), exc_info=True)
            continue
        created += count
    if failed:
        raise RuntimeError(f"Не удалось материализовать серий: {failed}")
    return created
