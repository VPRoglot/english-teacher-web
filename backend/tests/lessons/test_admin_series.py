import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.families.models import Child
from app.lessons.admin_router import get_now
from app.lessons.generation import materialize_all
from app.lessons.models import Lesson, LessonNote, LessonSeries, LessonStatus
from tests.factories import make_child, make_family
from tests.lessons.conftest import make_lesson, make_series

NOW = datetime(2026, 10, 12, 9, tzinfo=UTC)  # пн 12:00 MSK
SERIES_URL = "/api/admin/series"


@pytest.fixture(autouse=True)
def frozen_now(app: FastAPI) -> Iterator[None]:
    app.dependency_overrides[get_now] = lambda: NOW
    yield
    app.dependency_overrides.pop(get_now, None)


@pytest.fixture
async def child(db_session: AsyncSession) -> Child:
    return await make_child(db_session, await make_family(db_session))


def payload(child: Child, **overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "child_id": str(child.id),
        "rrule": "FREQ=WEEKLY;BYDAY=TU",
        "local_start_time": "18:00",
        "duration_min": 60,
        "starts_on": "2026-10-12",
    }
    body.update(overrides)
    return body


async def create(client: AsyncClient, child: Child, **overrides: Any) -> dict[str, Any]:
    r = await client.post(SERIES_URL, json=payload(child, **overrides))
    assert r.status_code == 201, r.text
    result: dict[str, Any] = r.json()
    return result


def patch_url(series_id: str | uuid.UUID, from_day: str, scope: str | None = None) -> str:
    scope_part = f"scope={scope or 'this_and_following'}&"
    return f"{SERIES_URL}/{series_id}?{scope_part}from={from_day}"


async def lessons_of(session: AsyncSession, series_id: str | uuid.UUID) -> list[Lesson]:
    stmt = (
        select(Lesson)
        .where(Lesson.series_id == uuid.UUID(str(series_id)))
        .order_by(Lesson.starts_at)
        .execution_options(populate_existing=True)
    )
    return list(await session.scalars(stmt))


async def by_date(session: AsyncSession, series_id: str | uuid.UUID) -> dict[date, Lesson]:
    return {
        lesson.occurrence_date: lesson
        for lesson in await lessons_of(session, series_id)
        if lesson.occurrence_date is not None
    }


async def reload_series(session: AsyncSession, series_id: str | uuid.UUID) -> LessonSeries:
    stmt = (
        select(LessonSeries)
        .where(LessonSeries.id == uuid.UUID(str(series_id)))
        .execution_options(populate_existing=True)
    )
    return (await session.scalars(stmt)).one()


# --- создание --------------------------------------------------------------------------------


async def test_create_series_materializes_eight_weeks(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    r = await tutor_client.post(
        SERIES_URL, json=payload(child, rrule="FREQ=WEEKLY;BYDAY=FR,TU", meeting_url=None)
    )
    assert r.status_code == 201
    body = r.json()
    series = body["series"]
    assert series["rrule"] == "FREQ=WEEKLY;BYDAY=TU,FR"
    assert body["lessons_created"] == 16
    assert body["warnings"] == []
    assert series["child_id"] == str(child.id)
    assert series["child_name"] == child.full_name
    assert series["starts_on"] == "2026-10-12" and series["ends_on"] is None
    assert series["archived_at"] is None and series["meeting_url"] is None
    assert series["duration_min"] == 60 and series["local_start_time"].startswith("18:00")

    rows = await lessons_of(db_session, series["id"])
    assert len(rows) == 16
    assert {lesson.kind.value for lesson in rows} == {"regular"}
    assert {lesson.starts_at.timetz() for lesson in rows} == {time(15, 0, tzinfo=UTC)}
    assert rows[0].starts_at == datetime(2026, 10, 13, 15, tzinfo=UTC)
    assert rows[-1].starts_at == datetime(2026, 12, 4, 15, tzinfo=UTC)


async def test_create_copies_meeting_url_and_ends_on(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    body = await create(
        tutor_client,
        child,
        meeting_url="https://meet.example/room",
        ends_on="2026-10-27",
    )
    assert body["lessons_created"] == 3  # 13.10, 20.10, 27.10
    assert body["series"]["meeting_url"] == "https://meet.example/room"
    assert body["series"]["ends_on"] == "2026-10-27"
    assert {
        lesson.meeting_url for lesson in await lessons_of(db_session, body["series"]["id"])
    } == {"https://meet.example/room"}


@pytest.mark.parametrize(
    ("overrides", "loc"),
    [
        ({"rrule": "FREQ=DAILY"}, ["body", "rrule"]),
        ({"rrule": "FREQ=WEEKLY;BYDAY=TU;COUNT=3"}, ["body", "rrule"]),
        ({"rrule": "FREQ=WEEKLY;BYDAY=" + "MO," * 100}, ["body", "rrule"]),
        ({"local_start_time": "18:00:30"}, ["body", "local_start_time"]),
        ({"local_start_time": "18:00+03:00"}, ["body", "local_start_time"]),
        ({"duration_min": 10}, ["body", "duration_min"]),
        ({"meeting_url": "javascript:alert(1)"}, ["body", "meeting_url"]),
        ({"ends_on": "2026-10-11"}, ["body", "ends_on"]),
    ],
)
async def test_invalid_create_is_422_on_field(
    tutor_client: AsyncClient,
    db_session: AsyncSession,
    child: Child,
    overrides: dict[str, Any],
    loc: list[str],
) -> None:
    r = await tutor_client.post(SERIES_URL, json=payload(child, **overrides))
    assert r.status_code == 422
    assert loc in [field["loc"] for field in r.json()["error"]["details"]["fields"]]
    assert await db_session.scalar(select(func.count()).select_from(LessonSeries)) == 0


async def test_create_rejects_unknown_fields(tutor_client: AsyncClient, child: Child) -> None:
    r = await tutor_client.post(SERIES_URL, json=payload(child, generated_through="2030-01-01"))
    assert r.status_code == 422


async def test_create_for_unknown_or_archived_child(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    ghost = Child(id=uuid.uuid4())
    r = await tutor_client.post(SERIES_URL, json=payload(ghost))
    assert r.status_code == 404
    family = await make_family(db_session, name="Петровы")
    archived = await make_child(db_session, family, full_name="Архивный", archived=True)
    r = await tutor_client.post(SERIES_URL, json=payload(archived))
    assert r.status_code == 409 and r.json()["error"]["code"] == "child_archived"


async def test_series_overlap_warnings(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    other = await make_child(db_session, await make_family(db_session, name="Сидоровы"))
    clash = await make_lesson(
        db_session,
        child=other,
        starts_at=datetime(2026, 10, 20, 15, 30, tzinfo=UTC),  # вт 20.10 18:30 MSK
    )
    body = await create(tutor_client, child)
    assert [w["lesson_id"] for w in body["warnings"]] == [str(clash.id)]
    assert body["warnings"][0]["code"] == "overlap"
    assert body["lessons_created"] == 8


# --- правка «с даты» -------------------------------------------------------------------------


async def test_split_this_and_following(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    created = await create(tutor_client, child, meeting_url="https://meet.example/old")
    old_id = created["series"]["id"]
    rows = await by_date(db_session, old_id)
    completed = rows[date(2026, 10, 13)]
    completed.status = LessonStatus.COMPLETED
    detached = rows[date(2026, 10, 27)]
    detached.starts_at = datetime(2026, 10, 28, 15, tzinfo=UTC)
    detached.is_detached = True
    cancelled = rows[date(2026, 11, 3)]
    cancelled.status = LessonStatus.CANCELLED
    noted = rows[date(2026, 11, 10)]
    db_session.add(LessonNote(lesson_id=noted.id, shared_text="к уроку", private_text="тайна"))
    await db_session.flush()
    noted_id = noted.id

    r = await tutor_client.patch(
        patch_url(old_id, "2026-10-20"), json={"local_start_time": "19:00", "duration_min": 45}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    new = body["series"]
    assert new["id"] != old_id
    assert new["starts_on"] == "2026-10-20" and new["ends_on"] is None
    assert new["local_start_time"].startswith("19:00") and new["duration_min"] == 45
    assert new["rrule"] == "FREQ=WEEKLY;BYDAY=TU" and new["child_id"] == str(child.id)
    assert new["meeting_url"] == "https://meet.example/old"
    assert body["lessons_created"] == 0 and body["warnings"] == []

    old = await reload_series(db_session, old_id)
    assert old.ends_on == date(2026, 10, 19) and old.archived_at is None

    old_rows = await by_date(db_session, old_id)
    new_rows = await by_date(db_session, new["id"])
    # прошедшее, отмеченное и отсоединённое осталось у старой серии без изменений
    assert set(old_rows) == {date(2026, 10, 13), date(2026, 10, 27), date(2026, 11, 3)}
    assert old_rows[date(2026, 10, 13)].status is LessonStatus.COMPLETED
    assert old_rows[date(2026, 10, 13)].starts_at == datetime(2026, 10, 13, 15, tzinfo=UTC)
    assert old_rows[date(2026, 10, 27)].starts_at == datetime(2026, 10, 28, 15, tzinfo=UTC)
    assert old_rows[date(2026, 10, 27)].is_detached
    assert old_rows[date(2026, 11, 3)].status is LessonStatus.CANCELLED
    # будущие scheduled — в новой серии, в 19:00 MSK = 16:00 UTC, без двойников
    assert sorted(new_rows) == [
        date(2026, 10, 20),
        date(2026, 11, 10),
        date(2026, 11, 17),
        date(2026, 11, 24),
        date(2026, 12, 1),
    ]
    for lesson in new_rows.values():
        assert lesson.starts_at.timetz() == time(16, 0, tzinfo=UTC)
        assert lesson.duration_min == 45
        assert lesson.status is LessonStatus.SCHEDULED
    # то же занятие, заметка на месте
    assert new_rows[date(2026, 11, 10)].id == noted_id
    note = await db_session.get(LessonNote, noted_id)
    assert note is not None and note.private_text == "тайна"
    assert new["id"] == str(new_rows[date(2026, 10, 20)].series_id)


async def test_split_does_not_resurrect_deleted_lessons(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    created = await create(tutor_client, child)
    old_id = created["series"]["id"]
    deleted = (await by_date(db_session, old_id))[date(2026, 11, 3)]
    await db_session.delete(deleted)
    await db_session.flush()

    r = await tutor_client.patch(
        patch_url(old_id, "2026-10-20"), json={"local_start_time": "19:00"}
    )
    assert r.status_code == 200
    new_rows = await by_date(db_session, r.json()["series"]["id"])
    assert date(2026, 11, 3) not in new_rows
    assert r.json()["lessons_created"] == 0
    assert len(new_rows) == 6  # 20.10, 27.10, 10.11 … 01.12


async def test_split_can_change_days_and_end(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    created = await create(tutor_client, child)
    old_id = created["series"]["id"]
    r = await tutor_client.patch(
        patch_url(old_id, "2026-10-27"),
        json={"rrule": "FREQ=WEEKLY;BYDAY=WE", "ends_on": "2026-11-18"},
    )
    assert r.status_code == 200
    body = r.json()
    new_rows = await by_date(db_session, body["series"]["id"])
    assert sorted(new_rows) == [
        date(2026, 10, 28),
        date(2026, 11, 4),
        date(2026, 11, 11),
        date(2026, 11, 18),
    ]
    assert body["lessons_created"] == 4
    assert body["series"]["ends_on"] == "2026-11-18"
    old_rows = await by_date(db_session, old_id)
    assert sorted(old_rows) == [date(2026, 10, 13), date(2026, 10, 20)]
    assert (await reload_series(db_session, old_id)).ends_on == date(2026, 10, 26)


async def test_edit_from_series_start_updates_in_place(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    created = await create(tutor_client, child, starts_on="2026-10-19")
    series_id = created["series"]["id"]
    before = {lesson.id: lesson.starts_at for lesson in await lessons_of(db_session, series_id)}
    assert len(before) == 7

    r = await tutor_client.patch(
        patch_url(series_id, "2026-10-19"),
        json={"local_start_time": "19:00", "meeting_url": "https://meet.example/new"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["series"]["id"] == series_id
    assert body["lessons_created"] == 0
    rows = await lessons_of(db_session, series_id)
    assert {lesson.id for lesson in rows} == set(before)  # те же занятия
    assert {lesson.starts_at.timetz() for lesson in rows} == {time(16, 0, tzinfo=UTC)}
    assert {lesson.meeting_url for lesson in rows} == {"https://meet.example/new"}
    assert await db_session.scalar(select(func.count()).select_from(LessonSeries)) == 1


async def test_edit_in_place_clears_nullable_fields_and_shrinks_end(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    created = await create(
        tutor_client, child, starts_on="2026-10-19", meeting_url="https://meet.example/old"
    )
    series_id = created["series"]["id"]
    r = await tutor_client.patch(
        patch_url(series_id, "2026-10-19"),
        json={"meeting_url": None, "ends_on": "2026-11-03"},
    )
    assert r.status_code == 200
    assert r.json()["series"]["meeting_url"] is None
    assert r.json()["series"]["ends_on"] == "2026-11-03"
    rows = await lessons_of(db_session, series_id)
    assert [lesson.occurrence_date for lesson in rows] == [
        date(2026, 10, 20),
        date(2026, 10, 27),
        date(2026, 11, 3),
    ]
    assert {lesson.meeting_url for lesson in rows} == {None}


async def test_edit_returns_overlap_warnings_for_updated_lessons(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    other = await make_child(db_session, await make_family(db_session, name="Сидоровы"))
    clash = await make_lesson(
        db_session,
        child=other,
        starts_at=datetime(2026, 10, 20, 16, 30, tzinfo=UTC),  # вт 20.10 19:30 MSK
    )
    created = await create(tutor_client, child)
    assert created["warnings"] == []
    r = await tutor_client.patch(
        patch_url(created["series"]["id"], "2026-10-20"), json={"local_start_time": "19:00"}
    )
    assert [w["lesson_id"] for w in r.json()["warnings"]] == [str(clash.id)]


async def test_noop_edit_does_not_split(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    created = await create(tutor_client, child)
    series_id = created["series"]["id"]
    r = await tutor_client.patch(
        patch_url(series_id, "2026-10-20"), json={"local_start_time": "18:00"}
    )
    assert r.status_code == 200
    assert r.json()["series"]["id"] == series_id and r.json()["lessons_created"] == 0
    assert await db_session.scalar(select(func.count()).select_from(LessonSeries)) == 1
    assert (await reload_series(db_session, series_id)).ends_on is None


async def test_from_in_past_or_after_end_is_422(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    created = await create(tutor_client, child, ends_on="2026-11-10")
    url_id = created["series"]["id"]

    past = await tutor_client.patch(patch_url(url_id, "2026-10-11"), json={"duration_min": 30})
    assert past.status_code == 422
    assert past.json()["error"]["details"]["fields"][0]["loc"] == ["query", "from"]
    assert past.json()["error"]["details"]["fields"][0]["message"] == "Дата не может быть в прошлом"

    after = await tutor_client.patch(patch_url(url_id, "2026-11-11"), json={"duration_min": 30})
    assert after.status_code == 422
    assert after.json()["error"]["details"]["fields"][0]["loc"] == ["query", "from"]

    before_start = await tutor_client.patch(
        patch_url(url_id, "2026-10-20"), json={"ends_on": "2026-10-19"}
    )
    assert before_start.status_code == 422
    assert before_start.json()["error"]["details"]["fields"][0]["loc"] == ["body", "ends_on"]

    # ничего не изменилось
    assert await db_session.scalar(select(func.count()).select_from(LessonSeries)) == 1
    assert (await reload_series(db_session, url_id)).ends_on == date(2026, 11, 10)


async def test_today_is_a_valid_from_day(tutor_client: AsyncClient, child: Child) -> None:
    created = await create(tutor_client, child)
    r = await tutor_client.patch(
        patch_url(created["series"]["id"], "2026-10-12"), json={"duration_min": 30}
    )
    assert r.status_code == 200


async def test_scope_is_required_and_validated(tutor_client: AsyncClient, child: Child) -> None:
    created = await create(tutor_client, child)
    series_id = created["series"]["id"]
    missing = await tutor_client.patch(
        f"{SERIES_URL}/{series_id}?from=2026-10-20", json={"duration_min": 30}
    )
    assert missing.status_code == 422
    assert ["query", "scope"] in [f["loc"] for f in missing.json()["error"]["details"]["fields"]]
    wrong = await tutor_client.patch(
        patch_url(series_id, "2026-10-20", scope="all"), json={"duration_min": 30}
    )
    assert wrong.status_code == 422
    no_from = await tutor_client.patch(
        f"{SERIES_URL}/{series_id}?scope=this_and_following", json={"duration_min": 30}
    )
    assert no_from.status_code == 422


async def test_update_validates_body(tutor_client: AsyncClient, child: Child) -> None:
    created = await create(tutor_client, child)
    url = patch_url(created["series"]["id"], "2026-10-20")
    for body in (
        {"rrule": "FREQ=DAILY"},
        {"rrule": None},
        {"local_start_time": None},
        {"duration_min": None},
        {"duration_min": 500},
        {"child_id": str(uuid.uuid4())},
        {"starts_on": "2026-10-21"},
    ):
        assert (await tutor_client.patch(url, json=body)).status_code == 422, body


async def test_update_unknown_or_archived_series(tutor_client: AsyncClient, child: Child) -> None:
    missing = await tutor_client.patch(
        patch_url(uuid.uuid4(), "2026-10-20"), json={"duration_min": 30}
    )
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "series_not_found"

    created = await create(tutor_client, child)
    series_id = created["series"]["id"]
    assert (await tutor_client.delete(f"{SERIES_URL}/{series_id}")).status_code == 204
    archived = await tutor_client.patch(
        patch_url(series_id, "2026-10-20"), json={"duration_min": 30}
    )
    assert archived.status_code == 409 and archived.json()["error"]["code"] == "series_archived"


# --- архивирование ---------------------------------------------------------------------------


async def test_archive_removes_future_undetached_scheduled(
    tutor_client: AsyncClient,
    db_session: AsyncSession,
    sessionmaker: async_sessionmaker[AsyncSession],
    child: Child,
) -> None:
    created = await create(tutor_client, child, starts_on="2026-10-01")
    series_id = created["series"]["id"]
    rows = await by_date(db_session, series_id)
    past_scheduled = await make_lesson(
        db_session,
        series=await reload_series(db_session, series_id),
        starts_at=datetime(2026, 10, 6, 15, tzinfo=UTC),
        occurrence_date=date(2026, 10, 6),
    )
    detached = rows[date(2026, 10, 20)]
    detached.is_detached = True
    detached.starts_at = datetime(2026, 10, 21, 15, tzinfo=UTC)
    completed = rows[date(2026, 10, 27)]
    completed.status = LessonStatus.COMPLETED
    cancelled = rows[date(2026, 11, 3)]
    cancelled.status = LessonStatus.CANCELLED
    noted = rows[date(2026, 11, 10)]
    db_session.add(LessonNote(lesson_id=noted.id, shared_text="x"))
    await db_session.flush()
    keep = {past_scheduled.id, detached.id, completed.id, cancelled.id}

    r = await tutor_client.delete(f"{SERIES_URL}/{series_id}")
    assert r.status_code == 204 and r.content == b""

    remaining = await lessons_of(db_session, series_id)
    assert {lesson.id for lesson in remaining} == keep
    assert (await reload_series(db_session, series_id)).archived_at == NOW
    assert await db_session.get(LessonNote, noted.id) is None  # заметки ушли каскадом
    # ежедневная задача архивную серию не трогает
    assert await materialize_all(sessionmaker, now=NOW + timedelta(days=30)) == 0
    assert {lesson.id for lesson in await lessons_of(db_session, series_id)} == keep

    again = await tutor_client.delete(f"{SERIES_URL}/{series_id}")
    assert again.status_code == 409 and again.json()["error"]["code"] == "series_archived"


async def test_archive_unknown_series_is_404(tutor_client: AsyncClient) -> None:
    r = await tutor_client.delete(f"{SERIES_URL}/{uuid.uuid4()}")
    assert r.status_code == 404 and r.json()["error"]["code"] == "series_not_found"


async def test_archive_leaves_other_series_alone(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    first = await create(tutor_client, child)
    second = await create(tutor_client, child, rrule="FREQ=WEEKLY;BYDAY=TH")
    assert (await tutor_client.delete(f"{SERIES_URL}/{first['series']['id']}")).status_code == 204
    assert len(await lessons_of(db_session, second["series"]["id"])) == 8


# --- список ----------------------------------------------------------------------------------


async def test_list_by_child_hides_archived_by_default(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    sibling = await make_child(db_session, await make_family(db_session, name="Сидоровы"))
    late = await create(tutor_client, child, starts_on="2026-11-02")
    early = await create(tutor_client, child, rrule="FREQ=WEEKLY;BYDAY=TH")
    done = await create(tutor_client, child, starts_on="2026-10-13")
    other = await create(tutor_client, sibling)
    await tutor_client.delete(f"{SERIES_URL}/{done['series']['id']}")

    r = await tutor_client.get(SERIES_URL, params={"child_id": str(child.id)})
    assert r.status_code == 200
    assert [s["id"] for s in r.json()] == [early["series"]["id"], late["series"]["id"]]
    assert r.json()[0]["child_name"] == child.full_name

    r = await tutor_client.get(SERIES_URL, params={"child_id": str(child.id), "archived": "true"})
    assert [s["id"] for s in r.json()] == [
        early["series"]["id"],
        done["series"]["id"],
        late["series"]["id"],
    ]
    assert r.json()[1]["archived_at"] is not None

    everyone = await tutor_client.get(SERIES_URL)
    assert {s["id"] for s in everyone.json()} == {
        early["series"]["id"],
        late["series"]["id"],
        other["series"]["id"],
    }


# --- права -----------------------------------------------------------------------------------


async def test_series_admin_only(
    client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    series = await make_series(db_session, child)
    any_id = uuid.uuid4()
    calls = [
        client.get(SERIES_URL),
        client.post(SERIES_URL, json=payload(child)),
        client.patch(patch_url(any_id, "2026-10-20"), json={"duration_min": 30}),
        client.delete(f"{SERIES_URL}/{series.id}"),
    ]
    for call in calls:
        assert (await call).status_code == 401


async def test_series_hidden_from_parent(
    parent_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    series = await make_series(db_session, child)
    assert (await parent_client.get(SERIES_URL)).status_code == 404
    assert (await parent_client.post(SERIES_URL, json=payload(child))).status_code == 404
    assert (
        await parent_client.patch(patch_url(series.id, "2026-10-20"), json={"duration_min": 30})
    ).status_code == 404
    assert (await parent_client.delete(f"{SERIES_URL}/{series.id}")).status_code == 404
