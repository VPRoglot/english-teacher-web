from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.lessons.models import ChangeRequest, ChangeRequestStatus, Lesson, LessonStatus
from tests.conftest import FakeTaskQueue
from tests.factories import make_child
from tests.lessons.conftest import make_change_request, make_lesson
from tests.lessons.test_cabinet_lessons import only_family

NOTIFY = "notifications.notify_change_request"


async def future_lesson(session: AsyncSession, **overrides: Any) -> Lesson:
    family = await only_family(session)
    child = await make_child(session, family)
    values: dict[str, Any] = {"starts_at": datetime.now(UTC) + timedelta(days=3)}
    values.update(overrides)
    return await make_lesson(session, child=child, **values)


def url(lesson_id: object) -> str:
    return f"/api/me/lessons/{lesson_id}/change-requests"


async def test_parent_requests_cancel_and_sees_it_on_lesson(
    parent_client: AsyncClient, db_session: AsyncSession, task_queue: FakeTaskQueue
) -> None:
    lesson = await future_lesson(db_session)
    r = await parent_client.post(url(lesson.id), json={"type": "cancel", "comment": "Заболела"})
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "pending"
    assert body["is_late"] is False
    assert task_queue.calls == [(NOTIFY, {"request_id": body["id"]})]
    detail = (await parent_client.get(f"/api/me/lessons/{lesson.id}")).json()
    assert detail["change_request"]["comment"] == "Заболела"
    assert detail["change_request"]["id"] == body["id"]


async def test_lesson_without_request_has_null(
    parent_client: AsyncClient, db_session: AsyncSession
) -> None:
    lesson = await future_lesson(db_session)
    detail = (await parent_client.get(f"/api/me/lessons/{lesson.id}")).json()
    assert detail["change_request"] is None


@pytest.mark.parametrize("proposed", [None, "", "   "])
async def test_reschedule_requires_proposed_text(
    parent_client: AsyncClient, db_session: AsyncSession, proposed: str | None
) -> None:
    lesson = await future_lesson(db_session)
    r = await parent_client.post(
        url(lesson.id), json={"type": "reschedule", "proposed_text": proposed}
    )
    assert r.status_code == 422
    fields = r.json()["error"]["details"]["fields"]
    assert fields[0]["loc"] == ["body", "proposed_text"]
    assert fields[0]["message"] == "Укажите удобное время"


async def test_reschedule_with_text_is_saved_trimmed(
    parent_client: AsyncClient, db_session: AsyncSession
) -> None:
    lesson = await future_lesson(db_session)
    r = await parent_client.post(
        url(lesson.id), json={"type": "reschedule", "proposed_text": "  в пятницу после 17  "}
    )
    assert r.status_code == 201
    assert r.json()["proposed_text"] == "в пятницу после 17"
    assert r.json()["is_late"] is False


async def test_cancel_rejects_proposed_text_and_blank_becomes_none(
    parent_client: AsyncClient, db_session: AsyncSession
) -> None:
    lesson = await future_lesson(db_session)
    bad = await parent_client.post(url(lesson.id), json={"type": "cancel", "proposed_text": "в пт"})
    assert bad.status_code == 422
    assert bad.json()["error"]["details"]["fields"][0]["loc"] == ["body", "proposed_text"]
    ok = await parent_client.post(url(lesson.id), json={"type": "cancel", "proposed_text": " "})
    assert ok.status_code == 201
    assert ok.json()["proposed_text"] is None


async def test_extra_fields_and_lengths_rejected(
    parent_client: AsyncClient, db_session: AsyncSession
) -> None:
    lesson = await future_lesson(db_session)
    extra = await parent_client.post(url(lesson.id), json={"type": "cancel", "status": "approved"})
    assert extra.status_code == 422
    long_comment = await parent_client.post(
        url(lesson.id), json={"type": "cancel", "comment": "x" * 1001}
    )
    assert long_comment.status_code == 422
    long_text = await parent_client.post(
        url(lesson.id), json={"type": "reschedule", "proposed_text": "x" * 501}
    )
    assert long_text.status_code == 422


async def test_second_pending_is_409(parent_client: AsyncClient, db_session: AsyncSession) -> None:
    lesson = await future_lesson(db_session)
    assert (await parent_client.post(url(lesson.id), json={"type": "cancel"})).status_code == 201
    r = await parent_client.post(url(lesson.id), json={"type": "cancel"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "change_request_exists"
    assert len((await db_session.scalars(select(ChangeRequest))).all()) == 1


@pytest.mark.parametrize("case", ["past", "cancelled", "completed"])
async def test_only_future_scheduled_lessons(
    parent_client: AsyncClient, db_session: AsyncSession, case: str
) -> None:
    cases: dict[str, dict[str, Any]] = {
        "past": {"starts_at": datetime.now(UTC) - timedelta(hours=1)},
        "cancelled": {"status": LessonStatus.CANCELLED},
        "completed": {
            "status": LessonStatus.COMPLETED,
            "starts_at": datetime.now(UTC) - timedelta(days=1),
        },
    }
    overrides = cases[case]
    lesson = await future_lesson(db_session, **overrides)
    r = await parent_client.post(url(lesson.id), json={"type": "cancel"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "lesson_not_requestable"


async def test_withdraw_then_new_request_allowed(
    parent_client: AsyncClient, db_session: AsyncSession
) -> None:
    lesson = await future_lesson(db_session)
    first = (await parent_client.post(url(lesson.id), json={"type": "cancel"})).json()
    w = await parent_client.delete(f"/api/me/change-requests/{first['id']}")
    assert w.status_code == 200
    assert w.json()["status"] == "withdrawn"
    assert w.json()["resolved_at"] is not None
    second = await parent_client.post(
        url(lesson.id), json={"type": "reschedule", "proposed_text": "завтра"}
    )
    assert second.status_code == 201


async def test_withdraw_resolved_is_409(
    parent_client: AsyncClient, db_session: AsyncSession
) -> None:
    lesson = await future_lesson(db_session)
    done = await make_change_request(
        db_session,
        lesson,
        status=ChangeRequestStatus.REJECTED,
        tutor_response="Нет окон",
        resolved_at=datetime.now(UTC),
    )
    r = await parent_client.delete(f"/api/me/change-requests/{done.id}")
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "change_request_not_pending"
    detail = (await parent_client.get(f"/api/me/lessons/{lesson.id}")).json()
    assert detail["change_request"]["tutor_response"] == "Нет окон"


async def test_withdraw_unknown_is_404(parent_client: AsyncClient) -> None:
    r = await parent_client.delete("/api/me/change-requests/019c0000-0000-7000-8000-000000000000")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "change_request_not_found"


async def test_late_flag_uses_request_time(
    parent_client: AsyncClient, db_session: AsyncSession
) -> None:
    # порог по умолчанию 24 ч, занятие через 10 ч
    lesson = await future_lesson(db_session, starts_at=datetime.now(UTC) + timedelta(hours=10))
    r = await parent_client.post(url(lesson.id), json={"type": "cancel"})
    assert r.status_code == 201
    assert r.json()["is_late"] is True
    detail = (await parent_client.get(f"/api/me/lessons/{lesson.id}")).json()
    assert detail["change_request"]["is_late"] is True


async def test_reschedule_is_never_late(
    parent_client: AsyncClient, db_session: AsyncSession
) -> None:
    lesson = await future_lesson(db_session, starts_at=datetime.now(UTC) + timedelta(hours=2))
    r = await parent_client.post(
        url(lesson.id), json={"type": "reschedule", "proposed_text": "позже"}
    )
    assert r.json()["is_late"] is False


async def test_request_saved_even_if_enqueue_fails(
    parent_client: AsyncClient, db_session: AsyncSession, task_queue: FakeTaskQueue
) -> None:
    task_queue.fail = True
    lesson = await future_lesson(db_session)
    r = await parent_client.post(url(lesson.id), json={"type": "cancel"})
    assert r.status_code == 201
    assert len((await db_session.scalars(select(ChangeRequest))).all()) == 1
