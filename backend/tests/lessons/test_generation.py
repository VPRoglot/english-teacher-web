from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.families.models import Child
from app.lessons.generation import (
    HORIZON_DAYS,
    materialize_all,
    materialize_series,
    regenerate_series_from,
)
from app.lessons.models import Lesson, LessonKind, LessonStatus
from app.lessons.schemas import TutorSettingsUpdate
from app.lessons.tutor_settings import update_tutor_settings
from tests.factories import make_child, make_family
from tests.lessons.conftest import make_lesson, make_series

MSK = ZoneInfo("Europe/Moscow")
NOW = datetime(2026, 10, 12, 9, tzinfo=UTC)  # пн 12:00 MSK


@pytest.fixture
async def child(db_session: AsyncSession) -> Child:
    return await make_child(db_session, await make_family(db_session))


async def _lessons(session: AsyncSession, series_id: UUID) -> list[Lesson]:
    stmt = (
        select(Lesson)
        .where(Lesson.series_id == series_id)
        .order_by(Lesson.starts_at)
        .execution_options(populate_existing=True)
    )
    return list(await session.scalars(stmt))


def test_horizon_is_eight_weeks() -> None:
    assert HORIZON_DAYS == 56


async def test_materialize_creates_eight_weeks_and_moves_frontier(
    db_session: AsyncSession, child: Child
) -> None:
    series = await make_series(
        db_session,
        child,
        rrule="FREQ=WEEKLY;BYDAY=MO,TH",
        local_start_time=time(10, 0),
        starts_on=date(2026, 10, 1),
        meeting_url="https://meet.example/s",
        duration_min=45,
    )
    created = await materialize_series(db_session, series, tz=MSK, now=NOW)
    # 12.10 10:00 MSK уже прошло → первое занятие чт 15.10; последнее ≤ 07.12; 16 занятий
    assert created[0].starts_at == datetime(2026, 10, 15, 7, tzinfo=UTC)
    assert created[-1].starts_at == datetime(2026, 12, 7, 7, tzinfo=UTC)
    assert len(created) == 16
    assert series.generated_through == date(2026, 12, 7)
    assert all(lesson.meeting_url == series.meeting_url for lesson in created)
    assert all(
        lesson.child_id == child.id
        and lesson.series_id == series.id
        and lesson.kind is LessonKind.REGULAR
        and lesson.duration_min == 45
        and lesson.status is LessonStatus.SCHEDULED
        and not lesson.is_detached
        and lesson.id is not None
        for lesson in created
    )
    assert len(await _lessons(db_session, series.id)) == 16


async def test_second_run_creates_nothing(db_session: AsyncSession, child: Child) -> None:
    series = await make_series(
        db_session, child, rrule="FREQ=WEEKLY;BYDAY=MO,TH", starts_on=date(2026, 10, 1)
    )
    assert len(await materialize_series(db_session, series, tz=MSK, now=NOW)) == 16
    assert await materialize_series(db_session, series, tz=MSK, now=NOW) == []
    assert len(await _lessons(db_session, series.id)) == 16


async def test_next_day_run_adds_only_new_dates(db_session: AsyncSession, child: Child) -> None:
    series = await make_series(
        db_session, child, rrule="FREQ=WEEKLY;BYDAY=MO,TH", starts_on=date(2026, 10, 1)
    )
    await materialize_series(db_session, series, tz=MSK, now=NOW)
    created = await materialize_series(db_session, series, tz=MSK, now=NOW + timedelta(days=3))
    # горизонт 15.10 + 56 = 10.12 (чт); фронтир был 07.12
    assert [lesson.starts_at for lesson in created] == [datetime(2026, 12, 10, 7, tzinfo=UTC)]
    assert series.generated_through == date(2026, 12, 10)
    assert len(await _lessons(db_session, series.id)) == 17


async def test_series_starting_beyond_horizon_creates_nothing_yet(
    db_session: AsyncSession, child: Child
) -> None:
    series = await make_series(db_session, child, starts_on=date(2027, 3, 2))
    assert await materialize_series(db_session, series, tz=MSK, now=NOW) == []
    assert series.generated_through == date(2026, 12, 7)
    later_now = datetime(2027, 3, 1, tzinfo=UTC)
    later = await materialize_series(db_session, series, tz=MSK, now=later_now)
    assert later
    assert later[0].starts_at == datetime(2027, 3, 2, 7, tzinfo=UTC)


async def test_series_respects_ends_on(db_session: AsyncSession, child: Child) -> None:
    series = await make_series(
        db_session,
        child,
        rrule="FREQ=WEEKLY;BYDAY=TU",
        starts_on=date(2026, 10, 1),
        ends_on=date(2026, 10, 20),
    )
    created = await materialize_series(db_session, series, tz=MSK, now=NOW)
    assert [lesson.starts_at.date() for lesson in created] == [
        date(2026, 10, 13),
        date(2026, 10, 20),
    ]


async def test_moved_and_deleted_lessons_do_not_come_back(
    db_session: AsyncSession, child: Child
) -> None:
    series = await make_series(
        db_session, child, rrule="FREQ=WEEKLY;BYDAY=MO,TH", starts_on=date(2026, 10, 1)
    )
    created = await materialize_series(db_session, series, tz=MSK, now=NOW)
    moved, deleted = created[2], created[3]
    old_moved, old_deleted = moved.starts_at, deleted.starts_at
    moved.starts_at = old_moved + timedelta(hours=1)
    moved.is_detached = True
    await db_session.delete(deleted)
    await db_session.flush()

    for days in (1, 2, 30):
        await materialize_series(db_session, series, tz=MSK, now=NOW + timedelta(days=days))

    starts = {lesson.starts_at for lesson in await _lessons(db_session, series.id)}
    assert old_moved not in starts
    assert old_deleted not in starts
    assert moved.starts_at in starts


async def test_regenerate_from_keeps_past_marked_and_detached(
    db_session: AsyncSession, child: Child
) -> None:
    series = await make_series(
        db_session,
        child,
        rrule="FREQ=WEEKLY;BYDAY=MO,TH",
        local_start_time=time(10, 0),
        starts_on=date(2026, 10, 1),
    )
    past = await make_lesson(
        db_session, series=series, starts_at=datetime(2026, 10, 8, 7, tzinfo=UTC)
    )
    created = await materialize_series(db_session, series, tz=MSK, now=NOW)
    completed, cancelled, detached = created[0], created[1], created[2]
    completed.status = LessonStatus.COMPLETED
    cancelled.status = LessonStatus.CANCELLED
    detached.is_detached = True
    await db_session.flush()
    kept = {past.id, completed.id, cancelled.id, detached.id}
    old_replaced = {lesson.id for lesson in created} - kept

    series.local_start_time = time(12, 0)
    regenerated = await regenerate_series_from(
        db_session, series, from_day=date(2026, 10, 12), tz=MSK, now=NOW
    )

    rows = await _lessons(db_session, series.id)
    by_id = {lesson.id: lesson for lesson in rows}
    assert kept <= by_id.keys()
    assert not old_replaced & by_id.keys()
    assert by_id[past.id].starts_at == datetime(2026, 10, 8, 7, tzinfo=UTC)
    assert by_id[completed.id].starts_at == datetime(2026, 10, 15, 7, tzinfo=UTC)
    new = [lesson for lesson in rows if lesson.id not in kept]
    # 12:00 MSK = 09:00 UTC; пн 12.10 12:00 == now — ещё не прошло; пн/чт до 07.12 — 17 дат
    assert len(new) == 17 == len(regenerated)
    assert {lesson.starts_at.hour for lesson in new} == {9}
    assert all(lesson.status is LessonStatus.SCHEDULED and not lesson.is_detached for lesson in new)
    assert series.generated_through == date(2026, 12, 7)


async def test_regenerate_from_later_day_leaves_earlier_lessons(
    db_session: AsyncSession, child: Child
) -> None:
    series = await make_series(
        db_session, child, rrule="FREQ=WEEKLY;BYDAY=MO,TH", starts_on=date(2026, 10, 1)
    )
    created = await materialize_series(db_session, series, tz=MSK, now=NOW)
    series.local_start_time = time(12, 0)
    await regenerate_series_from(db_session, series, from_day=date(2026, 10, 20), tz=MSK, now=NOW)
    rows = await _lessons(db_session, series.id)
    before = [lesson for lesson in rows if lesson.starts_at.date() < date(2026, 10, 20)]
    assert [lesson.id for lesson in before] == [
        lesson.id for lesson in created if lesson.starts_at.date() < date(2026, 10, 20)
    ]
    assert {lesson.starts_at.hour for lesson in before} == {7}
    after = [lesson for lesson in rows if lesson.starts_at.date() >= date(2026, 10, 20)]
    assert {lesson.starts_at.hour for lesson in after} == {9}


async def test_timezone_change_keeps_local_wall_time(
    db_session: AsyncSession, child: Child
) -> None:
    series = await make_series(
        db_session,
        child,
        rrule="FREQ=WEEKLY;BYDAY=MO,TH",
        local_start_time=time(10, 0),
        starts_on=date(2026, 10, 1),
    )
    created = await materialize_series(db_session, series, tz=MSK, now=NOW)
    detached = created[0]
    detached.is_detached = True
    one_off_at = datetime(2026, 10, 20, 6, tzinfo=UTC)
    one_off = await make_lesson(db_session, child=child, starts_at=one_off_at)
    await db_session.flush()

    settings = await update_tutor_settings(
        db_session,
        TutorSettingsUpdate(timezone="Asia/Yekaterinburg", cancel_policy_hours=24),
        now=NOW,
    )

    assert settings.timezone == "Asia/Yekaterinburg"
    rows = await _lessons(db_session, series.id)
    regular = [lesson for lesson in rows if lesson.id != detached.id]
    # пн 12.10 10:00 YEKT (05:00 UTC) уже прошло; чт 15.10 … пн 07.12 — 16 дат
    assert len(regular) == 16
    assert {lesson.starts_at.hour for lesson in regular} == {5}
    assert detached.starts_at == datetime(2026, 10, 15, 7, tzinfo=UTC)
    await db_session.refresh(one_off)
    assert one_off.starts_at == one_off_at


async def test_settings_update_without_timezone_change_keeps_lessons(
    db_session: AsyncSession, child: Child
) -> None:
    series = await make_series(
        db_session, child, rrule="FREQ=WEEKLY;BYDAY=MO,TH", starts_on=date(2026, 10, 1)
    )
    created = await materialize_series(db_session, series, tz=MSK, now=NOW)
    await update_tutor_settings(
        db_session, TutorSettingsUpdate(timezone="Europe/Moscow", cancel_policy_hours=3), now=NOW
    )
    assert [lesson.id for lesson in await _lessons(db_session, series.id)] == [
        lesson.id for lesson in created
    ]


async def test_materialize_all_skips_archived(
    db_session: AsyncSession, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    family = await make_family(db_session, name="Активные")
    active_child = await make_child(db_session, family, full_name="Активный")
    archived_child = await make_child(db_session, family, full_name="Архивный", archived=True)
    archived_family = await make_family(db_session, name="Архив", archived=True)
    child_of_archived_family = await make_child(db_session, archived_family)

    active = await make_series(db_session, active_child, starts_on=date(2026, 10, 1))
    archived_series = await make_series(
        db_session, active_child, starts_on=date(2026, 10, 1), archived_at=NOW
    )
    ended = await make_series(
        db_session, active_child, starts_on=date(2026, 9, 1), ends_on=date(2026, 10, 11)
    )
    of_archived_child = await make_series(db_session, archived_child, starts_on=date(2026, 10, 1))
    of_archived_family = await make_series(
        db_session, child_of_archived_family, starts_on=date(2026, 10, 1)
    )

    created = await materialize_all(sessionmaker, now=NOW)

    counts = {
        series.id: len(await _lessons(db_session, series.id))
        for series in (active, archived_series, ended, of_archived_child, of_archived_family)
    }
    assert counts[active.id] == 8  # вт: 13.10 … 01.12
    assert counts[archived_series.id] == counts[ended.id] == 0
    assert counts[of_archived_child.id] == counts[of_archived_family.id] == 0
    assert created == 8
    assert await materialize_all(sessionmaker, now=NOW) == 0


async def test_materialize_all_uses_tutor_timezone_and_series_ending_in_future(
    db_session: AsyncSession, child: Child, sessionmaker: async_sessionmaker[AsyncSession]
) -> None:
    series = await make_series(
        db_session,
        child,
        rrule="FREQ=WEEKLY;BYDAY=MO",
        local_start_time=time(10, 0),
        starts_on=date(2026, 10, 5),
        ends_on=date(2026, 10, 19),
    )
    # 12.10 21:30 UTC — в Москве уже вторник 13.10, понедельник 12.10 прошёл, остаётся 19.10
    created = await materialize_all(sessionmaker, now=datetime(2026, 10, 12, 21, 30, tzinfo=UTC))
    assert created == 1
    rows = await _lessons(db_session, series.id)
    assert [lesson.starts_at for lesson in rows] == [datetime(2026, 10, 19, 7, tzinfo=UTC)]
