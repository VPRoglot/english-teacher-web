import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
from app.families.models import Child, Family
from app.lessons import service
from app.lessons.errors import LessonSlotTaken
from app.lessons.models import Lesson, LessonNote, LessonStatus
from app.lessons.schemas import LessonUpdate
from tests.factories import make_child, make_family
from tests.leads.conftest import make_lead
from tests.lessons.conftest import make_lesson, make_series

NOW = datetime.now(UTC)
SOON = NOW + timedelta(days=3)
PAST = NOW - timedelta(days=3)


def iso(moment: datetime) -> str:
    return moment.isoformat()


@pytest.fixture
async def family(db_session: AsyncSession) -> Family:
    return await make_family(db_session)


@pytest.fixture
async def child(db_session: AsyncSession, family: Family) -> Child:
    return await make_child(db_session, family, default_meeting_url="https://zoom.example/kid")


async def test_create_one_off_lesson_with_child_default_link(
    tutor_client: AsyncClient, child: Child, family: Family
) -> None:
    r = await tutor_client.post(
        "/api/admin/lessons",
        json={"child_id": str(child.id), "starts_at": "2026-10-20T15:00:00Z", "duration_min": 60},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "regular" and body["status"] == "scheduled"
    assert body["series_id"] is None and body["is_detached"] is False
    assert body["meeting_url"] is None
    assert body["join_url"] == "https://zoom.example/kid"
    assert body["warnings"] == []
    assert body["has_notes"] is False
    assert body["notes"] == {"shared_text": "", "private_text": ""}
    assert body["student"] == {
        "child_id": str(child.id),
        "lead_id": None,
        "name": "Маша",
        "family_id": str(family.id),
        "family_name": "Ивановы",
    }
    assert datetime.fromisoformat(body["starts_at"]) == datetime(2026, 10, 20, 15, tzinfo=UTC)
    assert (await tutor_client.get(f"/api/admin/lessons/{body['id']}")).status_code == 200


async def test_create_with_own_link_overrides_default(
    tutor_client: AsyncClient, child: Child
) -> None:
    r = await tutor_client.post(
        "/api/admin/lessons",
        json={
            "child_id": str(child.id),
            "starts_at": iso(SOON),
            "duration_min": 45,
            "meeting_url": "https://meet.example/own",
        },
    )
    assert r.status_code == 201
    assert r.json()["meeting_url"] == "https://meet.example/own"
    assert r.json()["join_url"] == "https://meet.example/own"


async def test_create_without_any_link_has_no_join_url(
    tutor_client: AsyncClient, db_session: AsyncSession, family: Family
) -> None:
    plain = await make_child(db_session, family, full_name="Петя")
    r = await tutor_client.post(
        "/api/admin/lessons",
        json={"child_id": str(plain.id), "starts_at": iso(SOON), "duration_min": 60},
    )
    assert r.status_code == 201
    assert r.json()["join_url"] is None


@pytest.mark.parametrize(
    "patch",
    [
        {"duration_min": 14},
        {"duration_min": 241},
        {"starts_at": "2026-10-20T15:00:00"},
        {"meeting_url": "not a url"},
        {"child_id": "nope"},
    ],
)
async def test_create_invalid_body_is_422(
    tutor_client: AsyncClient, child: Child, patch: dict[str, Any]
) -> None:
    body = {"child_id": str(child.id), "starts_at": iso(SOON), "duration_min": 60, **patch}
    r = await tutor_client.post("/api/admin/lessons", json=body)
    assert r.status_code == 422


async def test_duration_bounds_are_allowed(tutor_client: AsyncClient, child: Child) -> None:
    for minutes in (15, 240):
        r = await tutor_client.post(
            "/api/admin/lessons",
            json={"child_id": str(child.id), "starts_at": iso(SOON), "duration_min": minutes},
        )
        assert r.status_code == 201


async def test_create_for_archived_child_is_409(
    tutor_client: AsyncClient, db_session: AsyncSession, family: Family
) -> None:
    archived = await make_child(db_session, family, full_name="Архивный", archived=True)
    r = await tutor_client.post(
        "/api/admin/lessons",
        json={"child_id": str(archived.id), "starts_at": iso(SOON), "duration_min": 60},
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "child_archived"


async def test_create_for_archived_family_is_409(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    gone = await make_family(db_session, name="Архивные", archived=True)
    kid = await make_child(db_session, gone)
    r = await tutor_client.post(
        "/api/admin/lessons",
        json={"child_id": str(kid.id), "starts_at": iso(SOON), "duration_min": 60},
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "family_archived"


async def test_create_for_unknown_child_is_404(tutor_client: AsyncClient) -> None:
    r = await tutor_client.post(
        "/api/admin/lessons",
        json={"child_id": str(uuid.uuid4()), "starts_at": iso(SOON), "duration_min": 60},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "child_not_found"


async def test_overlap_is_a_warning_not_an_error(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    start = datetime(2026, 10, 20, 12, tzinfo=UTC)  # 15:00 по Москве
    first = await make_lesson(db_session, child=child, starts_at=start, duration_min=60)
    cancelled = await make_lesson(
        db_session,
        child=child,
        starts_at=start,
        duration_min=60,
        status=LessonStatus.CANCELLED,
    )
    assert cancelled.id != first.id
    r = await tutor_client.post(
        "/api/admin/lessons",
        json={
            "child_id": str(child.id),
            "starts_at": iso(start + timedelta(minutes=30)),
            "duration_min": 60,
        },
    )
    assert r.status_code == 201
    warnings = r.json()["warnings"]
    assert len(warnings) == 1
    assert warnings[0]["code"] == "overlap"
    assert warnings[0]["lesson_id"] == str(first.id)
    assert warnings[0]["message"] == "Пересекается с занятием «Маша» 20.10 15:00"
    assert datetime.fromisoformat(warnings[0]["starts_at"]) == start


async def test_adjacent_lessons_do_not_overlap(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    start = datetime(2026, 10, 20, 12, tzinfo=UTC)
    await make_lesson(db_session, child=child, starts_at=start, duration_min=60)
    r = await tutor_client.post(
        "/api/admin/lessons",
        json={
            "child_id": str(child.id),
            "starts_at": iso(start + timedelta(minutes=60)),
            "duration_min": 60,
        },
    )
    assert r.status_code == 201 and r.json()["warnings"] == []
    before = await tutor_client.post(
        "/api/admin/lessons",
        json={
            "child_id": str(child.id),
            "starts_at": iso(start - timedelta(minutes=30)),
            "duration_min": 30,
        },
    )
    assert before.json()["warnings"] == []


async def test_overlap_with_completed_and_no_show_and_trial(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    start = datetime(2026, 10, 20, 12, tzinfo=UTC)
    done = await make_lesson(
        db_session, child=child, starts_at=start, status=LessonStatus.COMPLETED
    )
    missed = await make_lesson(
        db_session, child=child, starts_at=start, status=LessonStatus.NO_SHOW
    )
    lead = await make_lead(db_session, child_name="Лена")
    trial = await make_lesson(db_session, lead=lead, starts_at=start, duration_min=30)
    late = await make_lesson(
        db_session, child=child, starts_at=start, status=LessonStatus.CANCELLED_LATE
    )
    r = await tutor_client.post(
        "/api/admin/lessons",
        json={"child_id": str(child.id), "starts_at": iso(start), "duration_min": 60},
    )
    ids = {w["lesson_id"] for w in r.json()["warnings"]}
    assert ids == {str(done.id), str(missed.id), str(trial.id)}
    assert str(late.id) not in ids
    messages = [w["message"] for w in r.json()["warnings"]]
    assert "Пересекается с занятием «Пробное: Лена» 20.10 15:00" in messages


async def test_warnings_are_capped_at_twenty(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    start = datetime(2026, 10, 20, 12, tzinfo=UTC)
    for _ in range(22):
        await make_lesson(db_session, child=child, starts_at=start)
    r = await tutor_client.post(
        "/api/admin/lessons",
        json={"child_id": str(child.id), "starts_at": iso(start), "duration_min": 60},
    )
    assert len(r.json()["warnings"]) == 20


async def test_list_by_range_and_child(
    tutor_client: AsyncClient, db_session: AsyncSession, family: Family, child: Child
) -> None:
    other = await make_child(db_session, family, full_name="Петя")
    lead = await make_lead(db_session, child_name="Лена")
    base = datetime(2026, 10, 20, 12, tzinfo=UTC)
    # Вне диапазона: накануне, ровно на конце (конец исключён) и позже.
    await make_lesson(db_session, child=child, starts_at=base - timedelta(days=1))
    inside_late = await make_lesson(db_session, child=other, starts_at=base + timedelta(hours=5))
    inside_early = await make_lesson(db_session, child=child, starts_at=base)
    trial = await make_lesson(db_session, lead=lead, starts_at=base + timedelta(hours=2))
    await make_lesson(db_session, child=child, starts_at=base + timedelta(days=1))
    await make_lesson(db_session, child=child, starts_at=base + timedelta(days=3))

    query = {"from": iso(base), "to": iso(base + timedelta(days=1))}
    r = await tutor_client.get("/api/admin/lessons", params=query)
    assert r.status_code == 200
    items = r.json()
    # [from, to): начало включено, конец исключён; порядок по времени.
    assert [i["id"] for i in items] == [
        str(inside_early.id),
        str(trial.id),
        str(inside_late.id),
    ]
    trial_item = items[1]
    assert trial_item["kind"] == "trial"
    assert trial_item["student"] == {
        "child_id": None,
        "lead_id": str(lead.id),
        "name": "Лена",
        "family_id": None,
        "family_name": None,
    }
    assert trial_item["join_url"] is None
    assert items[0]["has_notes"] is False

    filtered = await tutor_client.get(
        "/api/admin/lessons", params={**query, "child_id": str(other.id)}
    )
    assert [i["id"] for i in filtered.json()] == [str(inside_late.id)]


async def test_list_item_effective_link_and_series_flags(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    series = await make_series(db_session, child)
    base = datetime(2026, 10, 20, 12, tzinfo=UTC)
    await make_lesson(db_session, series=series, starts_at=base, is_detached=True)
    r = await tutor_client.get(
        "/api/admin/lessons", params={"from": iso(base), "to": iso(base + timedelta(hours=1))}
    )
    item = r.json()[0]
    assert item["series_id"] == str(series.id) and item["is_detached"] is True
    assert item["meeting_url"] is None and item["join_url"] == "https://zoom.example/kid"


@pytest.mark.parametrize(
    "query",
    [
        "from=2026-10-20T00:00:00Z&to=2026-10-19T00:00:00Z",
        "from=2026-10-20T00:00:00Z&to=2026-10-20T00:00:00Z",
        "from=2026-10-01T00:00:00Z&to=2026-12-15T00:00:00Z",
        "from=2026-10-01T00:00:00Z&to=2026-12-03T00:00:01Z",
        "from=2026-10-01T00:00:00&to=2026-10-02T00:00:00Z",
        "from=2026-10-01T00:00:00Z",
    ],
)
async def test_invalid_range_is_422(tutor_client: AsyncClient, query: str) -> None:
    r = await tutor_client.get(f"/api/admin/lessons?{query}")
    assert r.status_code == 422


async def test_range_error_shape(tutor_client: AsyncClient) -> None:
    r = await tutor_client.get(
        "/api/admin/lessons?from=2026-10-20T00:00:00Z&to=2026-10-19T00:00:00Z"
    )
    assert r.json()["error"]["details"] == {
        "fields": [
            {
                "loc": ["query", "to"],
                "message": "Период — не больше 62 дней, конец позже начала",
                "type": "range",
            }
        ]
    }


async def test_range_of_exactly_62_days_is_allowed(tutor_client: AsyncClient) -> None:
    r = await tutor_client.get(
        "/api/admin/lessons?from=2026-10-01T00:00:00Z&to=2026-12-02T00:00:00Z"
    )
    assert r.status_code == 200 and r.json() == []


async def test_get_unknown_lesson_is_404(tutor_client: AsyncClient) -> None:
    r = await tutor_client.get(f"/api/admin/lessons/{uuid.uuid4()}")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "lesson_not_found"
    assert r.json()["error"]["message"] == "Занятие не найдено"


async def test_get_lesson_detail(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    lesson = await make_lesson(db_session, child=child, starts_at=SOON)
    db_session.add(LessonNote(lesson_id=lesson.id, shared_text="Для семьи", private_text="Себе"))
    await db_session.flush()
    r = await tutor_client.get(f"/api/admin/lessons/{lesson.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["notes"] == {"shared_text": "Для семьи", "private_text": "Себе"}
    assert body["has_notes"] is True
    assert "created_at" in body and "warnings" not in body


async def test_moving_series_lesson_detaches_it(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    series = await make_series(db_session, child)
    lesson = await make_lesson(db_session, series=series, starts_at=SOON)
    occurrence = lesson.occurrence_date
    moved = SOON + timedelta(hours=2)
    r = await tutor_client.patch(f"/api/admin/lessons/{lesson.id}", json={"starts_at": iso(moved)})
    assert r.status_code == 200
    body = r.json()
    assert body["is_detached"] is True and body["series_id"] == str(series.id)
    assert datetime.fromisoformat(body["starts_at"]) == moved
    await db_session.refresh(lesson)
    assert lesson.occurrence_date == occurrence


async def test_changing_duration_or_link_of_series_lesson_keeps_it_attached(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    series = await make_series(db_session, child)
    lesson = await make_lesson(db_session, series=series, starts_at=SOON)
    r = await tutor_client.patch(
        f"/api/admin/lessons/{lesson.id}",
        json={"duration_min": 90, "meeting_url": "https://meet.example/x"},
    )
    assert r.status_code == 200
    assert r.json()["is_detached"] is False
    assert r.json()["duration_min"] == 90
    assert r.json()["meeting_url"] == "https://meet.example/x"
    # Тот же момент времени — не перенос.
    same = await tutor_client.patch(
        f"/api/admin/lessons/{lesson.id}", json={"starts_at": iso(SOON)}
    )
    assert same.json()["is_detached"] is False


async def test_null_meeting_url_clears_own_link(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    lesson = await make_lesson(
        db_session, child=child, starts_at=SOON, meeting_url="https://meet.example/own"
    )
    r = await tutor_client.patch(f"/api/admin/lessons/{lesson.id}", json={"meeting_url": None})
    assert r.status_code == 200
    assert r.json()["meeting_url"] is None
    assert r.json()["join_url"] == "https://zoom.example/kid"


async def test_empty_patch_changes_nothing(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    lesson = await make_lesson(db_session, child=child, starts_at=SOON)
    r = await tutor_client.patch(f"/api/admin/lessons/{lesson.id}", json={})
    assert r.status_code == 200
    assert datetime.fromisoformat(r.json()["starts_at"]) == SOON
    assert r.json()["warnings"] == []


@pytest.mark.parametrize(
    "body",
    [
        {"starts_at": None},
        {"duration_min": None},
        {"status": None},
        {"duration_min": 10},
        {"status": "finished"},
        {"starts_at": "2026-10-20T15:00:00"},
        {"unknown": 1},
    ],
)
async def test_invalid_patch_is_422(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child, body: dict[str, Any]
) -> None:
    lesson = await make_lesson(db_session, child=child, starts_at=SOON)
    r = await tutor_client.patch(f"/api/admin/lessons/{lesson.id}", json=body)
    assert r.status_code == 422


async def test_patch_unknown_lesson_is_404(tutor_client: AsyncClient) -> None:
    r = await tutor_client.patch(f"/api/admin/lessons/{uuid.uuid4()}", json={"duration_min": 30})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "lesson_not_found"


async def test_moving_onto_sibling_slot_is_409(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    series = await make_series(db_session, child)
    first = await make_lesson(db_session, series=series, starts_at=SOON)
    second = await make_lesson(db_session, series=series, starts_at=SOON + timedelta(days=7))
    r = await tutor_client.patch(
        f"/api/admin/lessons/{first.id}", json={"starts_at": iso(second.starts_at)}
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "lesson_slot_taken"
    assert r.json()["error"]["message"] == "В это время уже есть занятие этого расписания"


async def test_slot_taken_leaves_the_session_usable(db_session: AsyncSession, child: Child) -> None:
    series = await make_series(db_session, child)
    first = await make_lesson(db_session, series=series, starts_at=SOON)
    second = await make_lesson(db_session, series=series, starts_at=SOON + timedelta(days=7))
    first_id, second_start = first.id, second.starts_at
    with pytest.raises(LessonSlotTaken):
        await service.update_lesson(
            db_session, first_id, LessonUpdate(starts_at=second_start), now=NOW
        )
    # Сессия жива: можно продолжать работать в той же транзакции.
    saved = await service.update_lesson(
        db_session, first_id, LessonUpdate(duration_min=30), now=NOW
    )
    assert saved.duration_min == 30
    assert saved.starts_at == SOON


async def test_one_off_lesson_may_take_any_time(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    one = await make_lesson(db_session, child=child, starts_at=SOON)
    other = await make_lesson(db_session, child=child, starts_at=SOON + timedelta(days=1))
    r = await tutor_client.patch(
        f"/api/admin/lessons/{one.id}", json={"starts_at": iso(other.starts_at)}
    )
    assert r.status_code == 200
    assert [w["lesson_id"] for w in r.json()["warnings"]] == [str(other.id)]


async def test_completed_requires_started_lesson(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    future = await make_lesson(db_session, child=child, starts_at=SOON)
    r = await tutor_client.patch(f"/api/admin/lessons/{future.id}", json={"status": "completed"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "lesson_not_started"
    assert r.json()["error"]["message"] == "Отметить можно только начавшееся занятие"
    no_show = await tutor_client.patch(
        f"/api/admin/lessons/{future.id}", json={"status": "no_show"}
    )
    assert no_show.status_code == 409

    past = await make_lesson(db_session, child=child, starts_at=PAST)
    ok = await tutor_client.patch(f"/api/admin/lessons/{past.id}", json={"status": "completed"})
    assert ok.status_code == 200 and ok.json()["status"] == "completed"
    again = await tutor_client.patch(f"/api/admin/lessons/{past.id}", json={"status": "no_show"})
    assert again.status_code == 200 and again.json()["status"] == "no_show"


@pytest.mark.parametrize("status", ["cancelled", "cancelled_late"])
async def test_future_lesson_can_be_cancelled(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child, status: str
) -> None:
    future = await make_lesson(db_session, child=child, starts_at=SOON)
    r = await tutor_client.patch(f"/api/admin/lessons/{future.id}", json={"status": status})
    assert r.status_code == 200 and r.json()["status"] == status


async def test_returning_to_scheduled_is_allowed(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    past = await make_lesson(db_session, child=child, starts_at=PAST, status=LessonStatus.COMPLETED)
    r = await tutor_client.patch(f"/api/admin/lessons/{past.id}", json={"status": "scheduled"})
    assert r.status_code == 200 and r.json()["status"] == "scheduled"


@pytest.mark.parametrize("status", ["cancelled", "cancelled_late", "completed", "no_show"])
@pytest.mark.parametrize(
    "body",
    [
        {"starts_at": iso(SOON + timedelta(hours=1))},
        {"duration_min": 30},
        {"meeting_url": "https://meet.example/x"},
        {"meeting_url": None},
    ],
)
async def test_time_change_of_non_scheduled_lesson_is_409(
    tutor_client: AsyncClient,
    db_session: AsyncSession,
    child: Child,
    status: str,
    body: dict[str, Any],
) -> None:
    lesson = await make_lesson(db_session, child=child, starts_at=PAST, status=LessonStatus(status))
    r = await tutor_client.patch(f"/api/admin/lessons/{lesson.id}", json=body)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "lesson_not_editable"
    assert r.json()["error"]["message"] == (
        "Время, длительность и ссылку можно менять только у запланированного занятия"
    )


async def test_status_is_applied_before_editability_check(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    cancelled = await make_lesson(
        db_session, child=child, starts_at=SOON, status=LessonStatus.CANCELLED
    )
    moved = SOON + timedelta(hours=4)
    r = await tutor_client.patch(
        f"/api/admin/lessons/{cancelled.id}",
        json={"status": "scheduled", "starts_at": iso(moved), "duration_min": 45},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "scheduled" and r.json()["duration_min"] == 45
    assert datetime.fromisoformat(r.json()["starts_at"]) == moved

    # Обратное: одновременно отменить и перенести нельзя, и ничего не применяется.
    scheduled = await make_lesson(db_session, child=child, starts_at=SOON + timedelta(days=2))
    bad = await tutor_client.patch(
        f"/api/admin/lessons/{scheduled.id}",
        json={"status": "cancelled", "starts_at": iso(SOON + timedelta(days=5))},
    )
    assert bad.status_code == 409
    await db_session.refresh(scheduled)
    assert scheduled.status is LessonStatus.SCHEDULED
    assert scheduled.starts_at == SOON + timedelta(days=2)


async def test_failed_patch_applies_nothing(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    future = await make_lesson(db_session, child=child, starts_at=SOON, duration_min=60)
    r = await tutor_client.patch(
        f"/api/admin/lessons/{future.id}", json={"status": "completed", "duration_min": 30}
    )
    assert r.status_code == 409
    await db_session.refresh(future)
    assert future.status is LessonStatus.SCHEDULED and future.duration_min == 60


async def test_overlap_warnings_only_when_time_or_duration_changes(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    start = datetime(2026, 10, 20, 12, tzinfo=UTC)
    mine = await make_lesson(db_session, child=child, starts_at=start, duration_min=60)
    neighbour = await make_lesson(
        db_session, child=child, starts_at=start + timedelta(minutes=90), duration_min=60
    )
    # Свою же запись предупреждение не считает; соседа ещё нет в пересечении.
    shifted = await tutor_client.patch(
        f"/api/admin/lessons/{mine.id}", json={"starts_at": iso(start + timedelta(minutes=15))}
    )
    assert shifted.json()["warnings"] == []
    longer = await tutor_client.patch(f"/api/admin/lessons/{mine.id}", json={"duration_min": 120})
    assert [w["lesson_id"] for w in longer.json()["warnings"]] == [str(neighbour.id)]
    # Ссылка и повтор той же длительности пересечений не проверяют.
    link = await tutor_client.patch(
        f"/api/admin/lessons/{mine.id}", json={"meeting_url": "https://meet.example/x"}
    )
    assert link.json()["warnings"] == []
    same = await tutor_client.patch(f"/api/admin/lessons/{mine.id}", json={"duration_min": 120})
    assert same.json()["warnings"] == []


async def test_reactivating_cancelled_lesson_warns_about_overlap(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    start = datetime(2026, 10, 20, 12, tzinfo=UTC)
    taken = await make_lesson(db_session, child=child, starts_at=start)
    cancelled = await make_lesson(
        db_session, child=child, starts_at=start, status=LessonStatus.CANCELLED
    )
    r = await tutor_client.patch(f"/api/admin/lessons/{cancelled.id}", json={"status": "scheduled"})
    assert r.status_code == 200
    assert [w["lesson_id"] for w in r.json()["warnings"]] == [str(taken.id)]
    cancel_again = await tutor_client.patch(
        f"/api/admin/lessons/{cancelled.id}", json={"status": "cancelled"}
    )
    assert cancel_again.json()["warnings"] == []


async def test_delete_only_future_scheduled(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    future = await make_lesson(db_session, child=child, starts_at=SOON)
    past = await make_lesson(db_session, child=child, starts_at=PAST)
    cancelled = await make_lesson(
        db_session, child=child, starts_at=SOON, status=LessonStatus.CANCELLED
    )
    completed = await make_lesson(
        db_session, child=child, starts_at=SOON, status=LessonStatus.COMPLETED
    )

    for blocked in (past, cancelled, completed):
        r = await tutor_client.delete(f"/api/admin/lessons/{blocked.id}")
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "lesson_not_deletable"
        assert (
            r.json()["error"]["message"] == "Удалить можно только будущее запланированное занятие"
        )

    r = await tutor_client.delete(f"/api/admin/lessons/{future.id}")
    assert r.status_code == 204 and r.content == b""
    assert (await tutor_client.get(f"/api/admin/lessons/{future.id}")).status_code == 404
    assert await db_session.scalar(select(Lesson.id).where(Lesson.id == past.id)) == past.id


async def test_delete_unknown_lesson_is_404(tutor_client: AsyncClient) -> None:
    r = await tutor_client.delete(f"/api/admin/lessons/{uuid.uuid4()}")
    assert r.status_code == 404 and r.json()["error"]["code"] == "lesson_not_found"


async def test_delete_removes_notes_and_series_lesson(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    series = await make_series(db_session, child)
    lesson = await make_lesson(db_session, series=series, starts_at=SOON)
    db_session.add(LessonNote(lesson_id=lesson.id, shared_text="a", private_text="b"))
    await db_session.flush()
    assert (await tutor_client.delete(f"/api/admin/lessons/{lesson.id}")).status_code == 204
    assert (
        await db_session.scalar(select(LessonNote).where(LessonNote.lesson_id == lesson.id)) is None
    )


async def test_service_get_unknown_lesson_raises(db_session: AsyncSession) -> None:
    with pytest.raises(NotFound):
        await service.get_admin_lesson(db_session, uuid.uuid4())


PATHS = [
    ("GET", "/api/admin/lessons?from=2026-10-01T00:00:00Z&to=2026-10-02T00:00:00Z"),
    ("POST", "/api/admin/lessons"),
    ("GET", "/api/admin/lessons/{id}"),
    ("PATCH", "/api/admin/lessons/{id}"),
    ("DELETE", "/api/admin/lessons/{id}"),
    ("PUT", "/api/admin/lessons/{id}/notes"),
]


@pytest.mark.parametrize(("method", "path"), PATHS)
async def test_lessons_are_hidden_from_family(
    parent_client: AsyncClient, method: str, path: str
) -> None:
    r = await parent_client.request(method, path.format(id=uuid.uuid4()), json={})
    assert r.status_code == 404


@pytest.mark.parametrize(("method", "path"), PATHS)
async def test_lessons_require_login(client: AsyncClient, method: str, path: str) -> None:
    r = await client.request(method, path.format(id=uuid.uuid4()), json={})
    assert r.status_code == 401
