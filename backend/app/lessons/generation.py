"""Материализация серий: занятия создаются вперёд от «фронтира» `generated_through`.

Фронтир не даёт ежедневной задаче воскресить перенесённое или удалённое занятие серии:
создаются только даты после него. `UNIQUE (series_id, starts_at)` и `ON CONFLICT DO NOTHING`
отвечают лишь за идемпотентность повторов и гонок.
"""

import uuid
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import Select, delete, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.db import new_uuid7
from app.families.models import Child, Family
from app.lessons.models import (
    Lesson,
    LessonKind,
    LessonSeries,
    LessonStatus,
    TutorSettings,
)
from app.lessons.recurrence import occurrences

HORIZON_DAYS = 56  # 8 недель вперёд


def local_midnight(day: date, tz: ZoneInfo) -> datetime:
    """Начало местного дня в UTC (несуществующая полночь сдвигается вперёд)."""
    return datetime.combine(day, time.min, tzinfo=tz).astimezone(UTC)


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

    moments = [
        moment
        for moment in occurrences(
            series.rrule,
            starts_on=series.starts_on,
            ends_on=series.ends_on,
            local_time=series.local_start_time,
            tz=tz,
            first_day=first_day,
            last_day=horizon_end,
        )
        if moment >= now
    ]
    created: list[Lesson] = []
    if moments:
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
                        "duration_min": series.duration_min,
                        "meeting_url": series.meeting_url,
                        "is_detached": False,
                        "status": LessonStatus.SCHEDULED,
                    }
                    for moment in moments
                ]
            )
            .on_conflict_do_nothing(constraint="uq_lessons_series_id_starts_at")
            .returning(Lesson)
        )
        result = await session.scalars(stmt, execution_options={"populate_existing": True})
        created = sorted(result.all(), key=lambda lesson: lesson.starts_at)
    series.generated_through = max(series.generated_through or horizon_end, horizon_end)
    await session.flush()
    return created


async def regenerate_series_from(
    session: AsyncSession,
    series: LessonSeries,
    *,
    from_day: date,
    tz: ZoneInfo,
    now: datetime,
) -> list[Lesson]:
    """Пересоздаёт будущие занятия серии с местной даты `from_day`.

    Удаляются только `scheduled` без `is_detached` с `starts_at >= max(начало from_day, now)`:
    прошедшие, отмеченные и отсоединённые занятия остаются. Вызывающий держит блокировку серии.
    """
    threshold = max(local_midnight(from_day, tz), now)
    await session.execute(
        delete(Lesson)
        .where(
            Lesson.series_id == series.id,
            Lesson.status == LessonStatus.SCHEDULED,
            Lesson.is_detached.is_(False),
            Lesson.starts_at >= threshold,
        )
        .execution_options(synchronize_session="fetch")
    )
    series.generated_through = from_day - timedelta(days=1)
    return await materialize_series(session, series, tz=tz, now=now)


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


async def _tutor_timezone(session: AsyncSession) -> ZoneInfo:
    settings = await session.get(TutorSettings, 1, populate_existing=True)
    if settings is None:
        raise RuntimeError("В tutor_settings нет строки id=1: примените миграции")
    return ZoneInfo(settings.timezone)


async def materialize_all(sessionmaker: async_sessionmaker[AsyncSession], *, now: datetime) -> int:
    """Доводит до горизонта все активные серии; у каждой серии своя транзакция.

    Возвращает число созданных занятий. Повторный запуск безопасен: фронтир серии
    сдвинут, а вставка идемпотентна.
    """
    async with sessionmaker() as session:
        today = now.astimezone(await _tutor_timezone(session)).date()
        series_ids = list(await session.scalars(active_series_ids_stmt(today)))

    created = 0
    for series_id in series_ids:
        async with sessionmaker() as session:
            series = await lock_series(session, series_id)
            if series is None or series.archived_at is not None:
                continue
            # Пояс читается под блокировкой серии: смена пояса перегенерирует серию под той же
            # блокировкой, поэтому генерация по старому поясу не пересечётся с перегенерацией.
            tz = await _tutor_timezone(session)
            created += len(await materialize_series(session, series, tz=tz, now=now))
            await session.commit()
    return created
