"""Занятие с запросом (в любом статусе) не удаляется и не правится правкой серии."""

from collections.abc import Iterator
from datetime import UTC, date, datetime, time, timedelta

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.families.models import Child
from app.lessons.admin_router import get_now
from app.lessons.models import ChangeRequestStatus, Lesson, LessonSeries
from tests.factories import make_child, make_family
from tests.lessons.conftest import make_change_request, make_lesson, make_series

NOW = datetime(2026, 10, 12, 9, tzinfo=UTC)  # пн 12:00 MSK


@pytest.fixture(autouse=True)
def frozen_now(app: FastAPI) -> Iterator[None]:
    app.dependency_overrides[get_now] = lambda: NOW
    yield
    app.dependency_overrides.pop(get_now, None)


@pytest.fixture
async def child(db_session: AsyncSession) -> Child:
    return await make_child(db_session, await make_family(db_session))


async def _rejected(db_session: AsyncSession, lesson: Lesson) -> None:
    await make_change_request(
        db_session,
        lesson,
        status=ChangeRequestStatus.REJECTED,
        resolved_at=NOW,
        tutor_response="Нет",
    )


async def _exists(db_session: AsyncSession, lesson_id: object) -> bool:
    return await db_session.scalar(select(Lesson.id).where(Lesson.id == lesson_id)) is not None


async def test_delete_lesson_with_request_is_409(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    # DELETE /api/admin/lessons берёт реальное время (не get_now): занятие обязано быть в будущем
    # по настоящим часам, иначе 409 был бы из-за прошедшего времени, а не из-за запроса.
    starts_at = datetime.now(UTC) + timedelta(days=30)
    lesson = await make_lesson(db_session, child=child, starts_at=starts_at)
    await _rejected(db_session, lesson)
    r = await tutor_client.delete(f"/api/admin/lessons/{lesson.id}")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "lesson_not_deletable"
    assert await _exists(db_session, lesson.id)


async def test_archive_series_keeps_lessons_with_requests(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    series = await make_series(db_session, child)
    kept = await make_lesson(
        db_session, series=series, starts_at=datetime(2026, 10, 20, 7, tzinfo=UTC)
    )
    gone = await make_lesson(
        db_session, series=series, starts_at=datetime(2026, 10, 27, 7, tzinfo=UTC)
    )
    await _rejected(db_session, kept)
    r = await tutor_client.delete(f"/api/admin/series/{series.id}")
    assert r.status_code == 204
    assert await _exists(db_session, kept.id)
    assert not await _exists(db_session, gone.id)


async def test_series_edit_keeps_lesson_with_request(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    series = await make_series(
        db_session,
        child,
        rrule="FREQ=WEEKLY;BYDAY=TU",
        local_start_time=time(10, 0),
        generated_through=date(2026, 12, 7),
    )
    on_tuesday = datetime(2026, 10, 20, 7, tzinfo=UTC)
    kept = await make_lesson(db_session, series=series, starts_at=on_tuesday)
    other = await make_lesson(
        db_session, series=series, starts_at=datetime(2026, 10, 27, 7, tzinfo=UTC)
    )
    await _rejected(db_session, kept)

    # Правка с той же серией (from_day = starts_on): дни меняются на среду.
    r = await tutor_client.patch(
        f"/api/admin/series/{series.id}?scope=this_and_following&from=2026-10-12",
        json={"rrule": "FREQ=WEEKLY;BYDAY=WE", "local_start_time": "12:00"},
    )
    assert r.status_code == 200, r.text

    await db_session.refresh(kept)
    assert kept.starts_at == on_tuesday and kept.series_id == series.id
    assert not await _exists(db_session, other.id)  # без запроса — ушло из расписания
    on_kept_date = (
        await db_session.scalars(
            select(Lesson).where(
                Lesson.series_id == series.id, Lesson.occurrence_date == kept.occurrence_date
            )
        )
    ).all()
    assert [lesson.id for lesson in on_kept_date] == [kept.id]
    rows = (
        await db_session.scalars(
            select(Lesson)
            .where(Lesson.series_id == series.id, Lesson.id != kept.id)
            .execution_options(populate_existing=True)
        )
    ).all()
    assert rows and all(lesson.starts_at.weekday() == 2 for lesson in rows)


async def test_series_edit_keeps_same_day_lesson_with_request_untouched(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    """Время серии меняется, а занятие с запросом остаётся с прежним временем."""
    series = await make_series(db_session, child, generated_through=date(2026, 12, 7))
    kept = await make_lesson(
        db_session, series=series, starts_at=datetime(2026, 10, 20, 7, tzinfo=UTC)
    )
    await _rejected(db_session, kept)
    r = await tutor_client.patch(
        f"/api/admin/series/{series.id}?scope=this_and_following&from=2026-10-12",
        json={"local_start_time": "19:00"},
    )
    assert r.status_code == 200, r.text
    await db_session.refresh(kept)
    assert kept.starts_at == datetime(2026, 10, 20, 7, tzinfo=UTC)
    stored = await db_session.get(LessonSeries, series.id)
    assert stored is not None and stored.local_start_time == time(19, 0)


async def test_admin_detail_reports_has_requests(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    with_request = await make_lesson(db_session, child=child)
    without = await make_lesson(db_session, child=child)
    await _rejected(db_session, with_request)

    r = await tutor_client.get(f"/api/admin/lessons/{with_request.id}")
    assert r.status_code == 200 and r.json()["has_requests"] is True
    r = await tutor_client.get(f"/api/admin/lessons/{without.id}")
    assert r.json()["has_requests"] is False
