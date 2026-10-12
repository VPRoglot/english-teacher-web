from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.families.models import Child
from app.lessons.admin_router import get_now
from app.lessons.models import Lesson, LessonSeries
from tests.factories import make_child, make_family
from tests.lessons.conftest import make_change_request, make_lesson, make_series

NOW = datetime(2026, 10, 12, 9, tzinfo=UTC)


@pytest.fixture(autouse=True)
def frozen_now(app: FastAPI) -> Iterator[None]:
    app.dependency_overrides[get_now] = lambda: NOW
    yield
    app.dependency_overrides.pop(get_now, None)


async def _series_with_lessons(
    session: AsyncSession, child: Child
) -> tuple[LessonSeries, Lesson, Lesson, Lesson]:
    series = await make_series(session, child)
    past = await make_lesson(session, series=series, starts_at=NOW - timedelta(days=7))
    future = await make_lesson(session, series=series, starts_at=NOW + timedelta(days=7))
    with_request = await make_lesson(session, series=series, starts_at=NOW + timedelta(days=14))
    await make_change_request(session, with_request)
    return series, past, future, with_request


async def _ids(session: AsyncSession, series: LessonSeries) -> set[UUID]:
    rows = await session.scalars(select(Lesson.id).where(Lesson.series_id == series.id))
    return set(rows)


async def _archived_at(session: AsyncSession, series: LessonSeries) -> datetime | None:
    await session.refresh(series)
    return series.archived_at


async def test_archiving_child_ends_series_and_future_lessons(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    child = await make_child(db_session, await make_family(db_session))
    series, past, _, with_request = await _series_with_lessons(db_session, child)

    r = await tutor_client.patch(f"/api/admin/children/{child.id}", json={"archived": True})
    assert r.status_code == 200, r.text

    assert await _archived_at(db_session, series) == NOW
    assert await _ids(db_session, series) == {past.id, with_request.id}


async def test_archiving_family_ends_all_children_series(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    family = await make_family(db_session)
    first = await make_child(db_session, family, full_name="Маша")
    second = await make_child(db_session, family, full_name="Петя")
    other = await make_child(db_session, await make_family(db_session, name="Чужие"))
    s1, *_ = await _series_with_lessons(db_session, first)
    s2, past2, _, request2 = await _series_with_lessons(db_session, second)
    s3, _, future3, _ = await _series_with_lessons(db_session, other)

    r = await tutor_client.patch(f"/api/admin/families/{family.id}", json={"archived": True})
    assert r.status_code == 200, r.text

    assert await _archived_at(db_session, s1) == NOW
    assert await _archived_at(db_session, s2) == NOW
    assert await _ids(db_session, s2) == {past2.id, request2.id}
    assert await _archived_at(db_session, s3) is None
    assert future3.id in await _ids(db_session, s3)


async def test_unarchive_does_not_restore_series(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    child = await make_child(db_session, await make_family(db_session))
    series, past, _, with_request = await _series_with_lessons(db_session, child)
    url = f"/api/admin/children/{child.id}"
    assert (await tutor_client.patch(url, json={"archived": True})).status_code == 200

    assert (await tutor_client.patch(url, json={"archived": False})).status_code == 200

    assert await _archived_at(db_session, series) == NOW
    assert await _ids(db_session, series) == {past.id, with_request.id}


async def test_repeat_archive_patch_is_harmless(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    child = await make_child(db_session, await make_family(db_session))
    series, past, _, with_request = await _series_with_lessons(db_session, child)
    url = f"/api/admin/children/{child.id}"
    assert (await tutor_client.patch(url, json={"archived": True})).status_code == 200

    assert (await tutor_client.patch(url, json={"archived": True})).status_code == 200

    assert await _archived_at(db_session, series) == NOW
    assert await _ids(db_session, series) == {past.id, with_request.id}


async def test_series_created_after_unarchive_survives_repeat_patch(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    child = await make_child(db_session, await make_family(db_session))
    url = f"/api/admin/children/{child.id}"
    assert (await tutor_client.patch(url, json={"archived": True})).status_code == 200
    assert (await tutor_client.patch(url, json={"archived": False})).status_code == 200
    fresh = await make_series(db_session, child)
    future = await make_lesson(db_session, series=fresh, starts_at=NOW + timedelta(days=7))

    assert (await tutor_client.patch(url, json={"archived": False})).status_code == 200

    assert await _archived_at(db_session, fresh) is None
    assert future.id in await _ids(db_session, fresh)
