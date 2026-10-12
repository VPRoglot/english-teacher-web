from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.families.models import Child
from app.lessons import generation
from app.lessons.generation import (
    HORIZON_DAYS,
    materialize_all,
    materialize_series,
    reconcile_series,
    series_shape,
)
from app.lessons.models import Lesson, LessonKind, LessonNote, LessonSeries, LessonStatus
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


async def _materialized(
    session: AsyncSession, child: Child, **overrides: object
) -> tuple[LessonSeries, list[Lesson]]:
    """Серия пн/чт 10:00 MSK с 01.10, материализованная на NOW: 16 занятий (15.10 … 07.12)."""
    values: dict[str, object] = {"rrule": "FREQ=WEEKLY;BYDAY=MO,TH", "starts_on": date(2026, 10, 1)}
    values.update(overrides)
    series = await make_series(session, child, **values)
    created = await materialize_series(session, series, tz=MSK, now=NOW)
    return series, created


async def _add_note(session: AsyncSession, lesson: Lesson, text: str) -> None:
    session.add(LessonNote(lesson_id=lesson.id, shared_text=text))
    await session.flush()


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
        and lesson.occurrence_date == lesson.starts_at.astimezone(MSK).date()
        for lesson in created
    )
    assert len(await _lessons(db_session, series.id)) == 16


async def test_second_run_creates_nothing(db_session: AsyncSession, child: Child) -> None:
    series, _ = await _materialized(db_session, child)
    assert await materialize_series(db_session, series, tz=MSK, now=NOW) == []
    assert len(await _lessons(db_session, series.id)) == 16


async def test_retry_with_reset_frontier_creates_no_duplicates(
    db_session: AsyncSession, child: Child
) -> None:
    series, _ = await _materialized(db_session, child)
    series.generated_through = None  # повтор после сбоя до сохранения фронтира
    assert await materialize_series(db_session, series, tz=MSK, now=NOW) == []
    assert len(await _lessons(db_session, series.id)) == 16


async def test_next_day_run_adds_only_new_dates(db_session: AsyncSession, child: Child) -> None:
    series, _ = await _materialized(db_session, child)
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
    series, created = await _materialized(db_session, child)
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


# --- смена часового пояса: сдвиг на месте ---------------------------------------------------


async def test_timezone_change_shifts_lessons_in_place(
    db_session: AsyncSession, child: Child
) -> None:
    series, created = await _materialized(db_session, child)
    detached, cancelled, deleted, noted, plain = (created[i] for i in (0, 1, 2, 3, 4))
    detached.is_detached = True
    cancelled.status = LessonStatus.CANCELLED
    await _add_note(db_session, noted, "заметка заранее")
    deleted_date = deleted.occurrence_date
    await db_session.delete(deleted)
    one_off_at = datetime(2026, 10, 20, 6, tzinfo=UTC)
    one_off = await make_lesson(db_session, child=child, starts_at=one_off_at)
    await db_session.flush()
    ids_before = {lesson.id for lesson in created} - {deleted.id}

    settings = await update_tutor_settings(
        db_session,
        TutorSettingsUpdate(timezone="Asia/Yekaterinburg", cancel_policy_hours=24),
        now=NOW,
    )

    assert settings.timezone == "Asia/Yekaterinburg"
    rows = await _lessons(db_session, series.id)
    by_id = {lesson.id: lesson for lesson in rows}
    # ни одного нового занятия и ни одного потерянного: те же строки с теми же id
    assert set(by_id) == ids_before
    assert deleted_date not in {lesson.occurrence_date for lesson in rows}
    # будущие scheduled: местные 10:00 теперь в YEKT = 05:00 UTC
    shifted = [lesson for lesson in rows if lesson.id not in {detached.id, cancelled.id}]
    assert {lesson.starts_at.hour for lesson in shifted} == {5}
    assert by_id[noted.id].starts_at == datetime(2026, 10, 26, 5, tzinfo=UTC)
    assert by_id[plain.id].id == plain.id
    # отсоединённое и отменённое, разовое — прежний момент, двойников нет
    assert by_id[detached.id].starts_at == datetime(2026, 10, 15, 7, tzinfo=UTC)
    assert by_id[cancelled.id].starts_at == datetime(2026, 10, 19, 7, tzinfo=UTC)
    dates = [lesson.occurrence_date for lesson in rows]
    assert len(dates) == len(set(dates))
    await db_session.refresh(one_off)
    assert one_off.starts_at == one_off_at
    # заметка пережила сдвиг
    note = await db_session.get(LessonNote, noted.id)
    assert note is not None and note.shared_text == "заметка заранее"
    # фронтир — местная дата — не меняется
    assert series.generated_through == date(2026, 12, 7)


async def test_timezone_change_shifts_lesson_whose_new_instant_is_past(
    db_session: AsyncSession, child: Child
) -> None:
    series, created = await _materialized(
        db_session, child, rrule="FREQ=WEEKLY;BYDAY=MO", local_start_time=time(18, 0)
    )
    today_lesson = created[0]  # пн 12.10 18:00 MSK = 15:00 UTC, ещё впереди
    assert today_lesson.starts_at == datetime(2026, 10, 12, 15, tzinfo=UTC)

    await update_tutor_settings(
        db_session,
        TutorSettingsUpdate(timezone="Pacific/Auckland", cancel_policy_hours=24),
        now=NOW,
    )

    # 18:00 NZDT (UTC+13) = 05:00 UTC — раньше now: занятие сдвинуто, а не удалено
    row = await db_session.get(Lesson, today_lesson.id, populate_existing=True)
    assert row is not None
    assert row.starts_at == datetime(2026, 10, 12, 5, tzinfo=UTC)
    assert len(await _lessons(db_session, series.id)) == len(created)


async def test_timezone_shift_conflict_leaves_lesson_unchanged_and_warns(
    db_session: AsyncSession, child: Child
) -> None:
    series, created = await _materialized(db_session, child)
    blocked = created[0]  # чт 15.10 07:00 UTC → в YEKT должен стать 05:00 UTC
    await make_lesson(
        db_session,
        series=series,
        starts_at=datetime(2026, 10, 15, 5, tzinfo=UTC),
        is_detached=True,
        occurrence_date=date(2026, 10, 14),
    )
    with structlog.testing.capture_logs() as logs:
        await update_tutor_settings(
            db_session,
            TutorSettingsUpdate(timezone="Asia/Yekaterinburg", cancel_policy_hours=24),
            now=NOW,
        )
    await db_session.refresh(blocked)
    assert blocked.starts_at == datetime(2026, 10, 15, 7, tzinfo=UTC)
    conflicts = [e for e in logs if e["event"] == "series_shift_conflict"]
    assert [(e["log_level"], e["lesson_id"]) for e in conflicts] == [("warning", str(blocked.id))]
    others = [lesson for lesson in created[1:] if lesson.status is LessonStatus.SCHEDULED]
    for lesson in others:
        await db_session.refresh(lesson)
    assert {lesson.starts_at.hour for lesson in others} == {5}


async def test_settings_update_without_timezone_change_keeps_lessons(
    db_session: AsyncSession, child: Child
) -> None:
    series, created = await _materialized(db_session, child)
    await update_tutor_settings(
        db_session, TutorSettingsUpdate(timezone="Europe/Moscow", cancel_policy_hours=3), now=NOW
    )
    assert [(lesson.id, lesson.starts_at) for lesson in await _lessons(db_session, series.id)] == [
        (lesson.id, lesson.starts_at) for lesson in created
    ]


# --- правка серии: сверка по дате вхождения -------------------------------------------------


async def test_reconcile_in_place_updates_times_and_keeps_ids_notes_and_marked(
    db_session: AsyncSession, child: Child
) -> None:
    series, created = await _materialized(db_session, child)
    detached, cancelled, deleted, noted = (created[i] for i in (0, 1, 2, 3))
    detached.is_detached = True
    cancelled.status = LessonStatus.CANCELLED
    await _add_note(db_session, noted, "к уроку")
    deleted_date = deleted.occurrence_date
    await db_session.delete(deleted)
    await db_session.flush()
    previous = series_shape(series)

    series.local_start_time = time(12, 0)
    series.duration_min = 90
    series.meeting_url = "https://meet.example/new"
    result = await reconcile_series(
        db_session, series, previous=previous, from_day=date(2026, 10, 12), tz=MSK, now=NOW
    )

    rows = await _lessons(db_session, series.id)
    by_id = {lesson.id: lesson for lesson in rows}
    assert len(rows) == 15  # без новых и без двойников
    assert deleted_date not in {lesson.occurrence_date for lesson in rows}
    assert result.created == []
    updated_ids = {lesson.id for lesson in result.updated}
    expected = {lesson.id for lesson in created} - {detached.id, cancelled.id, deleted.id}
    assert updated_ids == expected
    for lesson_id in updated_ids:
        lesson = by_id[lesson_id]
        assert lesson.starts_at.hour == 9  # 12:00 MSK
        assert (lesson.duration_min, lesson.meeting_url) == (90, "https://meet.example/new")
    assert by_id[noted.id].starts_at == datetime(2026, 10, 26, 9, tzinfo=UTC)
    note = await db_session.get(LessonNote, noted.id)
    assert note is not None and note.shared_text == "к уроку"
    # отсоединённое и отменённое остались как были, без двойников на своих датах
    assert by_id[detached.id].starts_at == datetime(2026, 10, 15, 7, tzinfo=UTC)
    assert by_id[cancelled.id].starts_at == datetime(2026, 10, 19, 7, tzinfo=UTC)
    assert by_id[cancelled.id].status is LessonStatus.CANCELLED
    dates = [lesson.occurrence_date for lesson in rows]
    assert len(dates) == len(set(dates))


async def test_reconcile_conflict_leaves_lesson_unchanged_and_warns(
    db_session: AsyncSession, child: Child
) -> None:
    series, created = await _materialized(db_session, child)
    blocked = created[0]  # чт 15.10 07:00 UTC → при 12:00 MSK должно стать 09:00 UTC
    await make_lesson(
        db_session,
        series=series,
        starts_at=datetime(2026, 10, 15, 9, tzinfo=UTC),
        is_detached=True,
        occurrence_date=date(2026, 10, 14),
    )
    previous = series_shape(series)
    series.local_start_time = time(12, 0)
    with structlog.testing.capture_logs() as logs:
        result = await reconcile_series(
            db_session, series, previous=previous, from_day=date(2026, 10, 12), tz=MSK, now=NOW
        )
    await db_session.refresh(blocked)
    assert blocked.starts_at == datetime(2026, 10, 15, 7, tzinfo=UTC)
    assert blocked.id not in {lesson.id for lesson in result.updated}
    assert len(result.updated) == 15  # 16 занятий без заблокированного
    conflicts = [e for e in logs if e["event"] == "series_reconcile_conflict"]
    assert [(e["log_level"], e["lesson_id"]) for e in conflicts] == [("warning", str(blocked.id))]


async def test_reconcile_from_later_day_leaves_earlier_lessons_alone(
    db_session: AsyncSession, child: Child
) -> None:
    series, created = await _materialized(db_session, child)
    previous = series_shape(series)
    series.local_start_time = time(12, 0)
    await reconcile_series(
        db_session, series, previous=previous, from_day=date(2026, 10, 20), tz=MSK, now=NOW
    )
    rows = await _lessons(db_session, series.id)
    assert [lesson.id for lesson in rows] == [lesson.id for lesson in created]
    cut = date(2026, 10, 20)
    assert {row.starts_at.hour for row in rows if row.starts_at.date() < cut} == {7}
    assert {row.starts_at.hour for row in rows if row.starts_at.date() >= cut} == {9}


async def test_reconcile_day_change_replaces_dates_and_ignores_deleted_old_occurrence(
    db_session: AsyncSession, child: Child
) -> None:
    series = await make_series(
        db_session, child, rrule="FREQ=WEEKLY;BYDAY=TU", starts_on=date(2026, 10, 1)
    )
    created = await materialize_series(db_session, series, tz=MSK, now=NOW)
    assert [lesson.occurrence_date for lesson in created][:2] == [
        date(2026, 10, 13),
        date(2026, 10, 20),
    ]
    old_ids = {lesson.id for lesson in created}
    await db_session.delete(created[1])  # вт 20.10 удалён репетитором
    await db_session.flush()
    previous = series_shape(series)

    series.rrule = "FREQ=WEEKLY;BYDAY=WE"
    result = await reconcile_series(
        db_session, series, previous=previous, from_day=date(2026, 10, 12), tz=MSK, now=NOW
    )

    rows = await _lessons(db_session, series.id)
    assert not old_ids & {lesson.id for lesson in rows}  # все вторники ушли
    assert result.updated == []
    # среды 14.10 … 02.12, включая 21.10 — удалённый вторник 20.10 её не блокирует
    assert [lesson.occurrence_date for lesson in rows] == [
        date(2026, 10, 14) + timedelta(weeks=n) for n in range(8)
    ]
    assert date(2026, 10, 21) in {lesson.occurrence_date for lesson in rows}
    assert len(result.created) == 8
    assert all(lesson.starts_at.hour == 7 for lesson in rows)


async def test_reconcile_does_not_resurrect_deleted_occurrence(
    db_session: AsyncSession, child: Child
) -> None:
    series, created = await _materialized(db_session, child)
    deleted_date = created[5].occurrence_date
    await db_session.delete(created[5])
    await db_session.flush()
    previous = series_shape(series)
    series.duration_min = 30
    await reconcile_series(
        db_session, series, previous=previous, from_day=date(2026, 10, 12), tz=MSK, now=NOW
    )
    rows = await _lessons(db_session, series.id)
    assert len(rows) == 15
    assert deleted_date not in {lesson.occurrence_date for lesson in rows}


async def test_reconcile_adds_dates_beyond_previous_frontier_and_new_days(
    db_session: AsyncSession, child: Child
) -> None:
    series, created = await _materialized(db_session, child)
    previous = series_shape(series)
    series.rrule = "FREQ=WEEKLY;BYDAY=MO,TH,SA"
    result = await reconcile_series(
        db_session, series, previous=previous, from_day=date(2026, 10, 12), tz=MSK, now=NOW
    )
    # субботы 17.10 … 05.12 — 8 новых дат; прежние 16 занятий не тронуты по id
    assert len(result.created) == 8
    new_dates = [lesson.occurrence_date for lesson in result.created]
    assert new_dates == [date(2026, 10, 17) + timedelta(weeks=n) for n in range(8)]
    assert result.updated == []
    rows = await _lessons(db_session, series.id)
    assert {lesson.id for lesson in created} <= {lesson.id for lesson in rows}


async def test_reconcile_as_split_moves_updated_lessons_to_new_series(
    db_session: AsyncSession, child: Child
) -> None:
    old, created = await _materialized(db_session, child)
    detached, cancelled = created[4], created[5]  # чт 29.10 и пн 02.11 — после 20.10
    detached.is_detached = True
    cancelled.status = LessonStatus.CANCELLED
    await db_session.flush()
    previous = series_shape(old)

    old.ends_on = date(2026, 10, 19)
    new = await make_series(
        db_session,
        child,
        rrule=old.rrule,
        starts_on=date(2026, 10, 20),
        local_start_time=time(12, 0),
        duration_min=90,
    )
    result = await reconcile_series(
        db_session,
        new,
        previous=previous,
        lessons_from=old,
        from_day=date(2026, 10, 20),
        tz=MSK,
        now=NOW,
    )

    old_rows = await _lessons(db_session, old.id)
    new_rows = await _lessons(db_session, new.id)
    assert result.created == []
    before = [lesson for lesson in created if lesson.starts_at.date() < date(2026, 10, 20)]
    after = [lesson for lesson in created if lesson.starts_at.date() >= date(2026, 10, 20)]
    marked = {detached.id, cancelled.id}
    # прошлые, отсоединённое и отменённое остались у старой серии с прежним временем
    assert {lesson.id for lesson in old_rows} == {lesson.id for lesson in before} | marked
    assert all(lesson.starts_at.hour == 7 for lesson in old_rows)
    # остальные scheduled будущие переехали в новую серию и получили новое время и длительность
    assert {lesson.id for lesson in new_rows} == {lesson.id for lesson in after} - marked
    assert {lesson.id for lesson in result.updated} == {lesson.id for lesson in new_rows}
    assert all(
        lesson.series_id == new.id and lesson.starts_at.hour == 9 and lesson.duration_min == 90
        for lesson in new_rows
    )
    assert new.generated_through == date(2026, 12, 7)


# --- materialize_all ------------------------------------------------------------------------


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


async def test_materialize_all_continues_after_a_failing_series_and_then_raises(
    db_session: AsyncSession,
    sessionmaker: async_sessionmaker[AsyncSession],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    family = await make_family(db_session)
    first = await make_series(
        db_session, await make_child(db_session, family, full_name="А"), starts_on=date(2026, 10, 1)
    )
    second = await make_series(
        db_session, await make_child(db_session, family, full_name="Б"), starts_on=date(2026, 10, 1)
    )
    real = generation.materialize_series
    broken_id = min(first.id, second.id)  # серии обходятся по возрастанию id: сбой — у первой

    async def flaky(
        session: AsyncSession, series: LessonSeries, *, tz: ZoneInfo, now: datetime
    ) -> list[Lesson]:
        if series.id == broken_id:
            raise RuntimeError("сбой серии")
        return await real(session, series, tz=tz, now=now)

    monkeypatch.setattr(generation, "materialize_series", flaky)

    with structlog.testing.capture_logs() as logs, pytest.raises(RuntimeError, match="1"):
        await materialize_all(sessionmaker, now=NOW)

    healthy_id = second.id if broken_id == first.id else first.id
    assert len(await _lessons(db_session, healthy_id)) == 8
    assert await _lessons(db_session, broken_id) == []
    failures = [e for e in logs if e["event"] == "series_materialize_failed"]
    assert [(e["log_level"], e["series_id"]) for e in failures] == [("error", str(broken_id))]
    assert failures[0]["exc_info"] is True

    # повтор (как ретрай задачи) без сбоя доводит упавшую серию и не дублирует остальные
    monkeypatch.setattr(generation, "materialize_series", real)
    assert await materialize_all(sessionmaker, now=NOW) == 8
    total = await db_session.scalar(select(func.count()).select_from(Lesson))
    assert total == 16
