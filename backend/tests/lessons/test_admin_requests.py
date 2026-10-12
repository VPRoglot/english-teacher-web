"""Очередь запросов в админке: список, одобрение, отклонение."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.families.models import Child
from app.lessons.admin_router import get_now
from app.lessons.models import (
    ChangeRequest,
    ChangeRequestStatus,
    ChangeRequestType,
    Lesson,
    LessonStatus,
)
from tests.factories import login, make_child, make_family, make_parent, make_tutor
from tests.lessons.conftest import make_change_request, make_lesson, make_series

NOW = datetime(2026, 10, 12, 9, tzinfo=UTC)
LESSON_START = NOW + timedelta(days=2)


@pytest.fixture(autouse=True)
def frozen_now(app: FastAPI) -> Iterator[None]:
    app.dependency_overrides[get_now] = lambda: NOW
    yield
    app.dependency_overrides.pop(get_now, None)


@pytest.fixture
async def child(db_session: AsyncSession) -> Child:
    return await make_child(db_session, await make_family(db_session), full_name="Маша")


def approve_url(request_id: object) -> str:
    return f"/api/admin/change-requests/{request_id}/approve"


def reject_url(request_id: object) -> str:
    return f"/api/admin/change-requests/{request_id}/reject"


async def request_for(
    session: AsyncSession,
    child: Child,
    *,
    lesson_overrides: dict[str, Any] | None = None,
    **overrides: Any,
) -> tuple[Lesson, ChangeRequest]:
    values: dict[str, Any] = {"starts_at": LESSON_START}
    values.update(lesson_overrides or {})
    lesson = await make_lesson(session, child=child, **values)
    request = await make_change_request(session, lesson, **overrides)
    return lesson, request


async def test_list_pending_oldest_first_with_context(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    _, newer = await request_for(db_session, child, created_at=NOW - timedelta(hours=1))
    older_lesson, older = await request_for(
        db_session,
        child,
        lesson_overrides={"starts_at": LESSON_START + timedelta(days=1)},
        created_at=NOW - timedelta(hours=5),
        type=ChangeRequestType.RESCHEDULE,
        proposed_text="в пятницу",
    )
    await request_for(
        db_session,
        child,
        lesson_overrides={"starts_at": LESSON_START + timedelta(days=2)},
        status=ChangeRequestStatus.WITHDRAWN,
        resolved_at=NOW,
    )
    r = await tutor_client.get("/api/admin/change-requests")
    assert r.status_code == 200
    items = r.json()
    assert [i["id"] for i in items] == [str(older.id), str(newer.id)]
    first = items[0]
    assert first["type"] == "reschedule"
    assert first["proposed_text"] == "в пятницу"
    assert first["lesson"]["id"] == str(older_lesson.id)
    assert first["lesson"]["status"] == "scheduled"
    assert first["lesson"]["duration_min"] == 60
    assert first["child"] == {"id": str(child.id), "full_name": "Маша"}
    assert first["family"]["id"] == str(child.family_id)
    assert first["family"]["name"] == "Ивановы"
    assert first["is_late"] is False
    assert isinstance(first["requested_by_name"], str)


async def test_list_other_statuses_resolved_desc(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    _, early = await request_for(
        db_session,
        child,
        status=ChangeRequestStatus.WITHDRAWN,
        resolved_at=NOW - timedelta(hours=3),
    )
    _, late = await request_for(
        db_session,
        child,
        lesson_overrides={"starts_at": LESSON_START + timedelta(days=1)},
        status=ChangeRequestStatus.WITHDRAWN,
        resolved_at=NOW - timedelta(hours=1),
    )
    await request_for(
        db_session, child, lesson_overrides={"starts_at": LESSON_START + timedelta(days=2)}
    )
    r = await tutor_client.get("/api/admin/change-requests", params={"status": "withdrawn"})
    assert [i["id"] for i in r.json()] == [str(late.id), str(early.id)]


async def test_requested_by_name_is_parent_full_name(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    parent = await make_parent(db_session, await make_family(db_session), full_name="Анна Иванова")
    await request_for(db_session, child, requested_by=parent)
    items = (await tutor_client.get("/api/admin/change-requests")).json()
    assert items[0]["requested_by_name"] == "Анна Иванова"


async def test_approve_cancel_on_time(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    # Подан за 30 ч до начала при пороге 24.
    lesson, request = await request_for(
        db_session, child, created_at=LESSON_START - timedelta(hours=30)
    )
    r = await tutor_client.post(approve_url(request.id), json={})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "approved"
    assert body["resolved_at"] is not None
    assert body["is_late"] is False
    assert body["lesson"]["status"] == "cancelled"
    assert body["warnings"] == []
    await db_session.refresh(lesson)
    assert lesson.status is LessonStatus.CANCELLED
    await db_session.refresh(request)
    assert request.status is ChangeRequestStatus.APPROVED
    assert request.resolved_at == NOW


async def test_approve_cancel_late_uses_request_time(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    # Подан за 10 ч до начала; момент одобрения (NOW, за 2 суток) значения не имеет.
    lesson, request = await request_for(
        db_session, child, created_at=LESSON_START - timedelta(hours=10)
    )
    r = await tutor_client.post(approve_url(request.id), json={})
    assert r.status_code == 200
    assert r.json()["is_late"] is True
    assert r.json()["lesson"]["status"] == "cancelled_late"
    await db_session.refresh(lesson)
    assert lesson.status is LessonStatus.CANCELLED_LATE


async def test_approve_reschedule_detaches_and_warns(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    series = await make_series(db_session, child)
    lesson, request = await request_for(
        db_session,
        child,
        lesson_overrides={"series_id": series.id},
        type=ChangeRequestType.RESCHEDULE,
        proposed_text="позже",
    )
    new_start = LESSON_START + timedelta(days=1, hours=3)
    other = await make_lesson(db_session, child=child, starts_at=new_start + timedelta(minutes=30))
    r = await tutor_client.post(
        approve_url(request.id), json={"new_starts_at": new_start.isoformat()}
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "approved"
    assert body["lesson"]["status"] == "scheduled"
    assert body["lesson"]["starts_at"].startswith(new_start.strftime("%Y-%m-%dT%H:%M"))
    assert body["warnings"][0]["code"] == "overlap"
    assert body["warnings"][0]["lesson_id"] == str(other.id)
    await db_session.refresh(lesson)
    assert lesson.starts_at == new_start
    assert lesson.is_detached is True


async def test_approve_reschedule_oneoff_stays_not_detached(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    lesson, request = await request_for(db_session, child, type=ChangeRequestType.RESCHEDULE)
    new_start = LESSON_START + timedelta(days=1)
    r = await tutor_client.post(
        approve_url(request.id), json={"new_starts_at": new_start.isoformat()}
    )
    assert r.status_code == 200
    await db_session.refresh(lesson)
    assert lesson.starts_at == new_start
    assert lesson.is_detached is False


async def test_reschedule_without_time_is_422(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    lesson, request = await request_for(db_session, child, type=ChangeRequestType.RESCHEDULE)
    r = await tutor_client.post(approve_url(request.id), json={})
    assert r.status_code == 422
    field = r.json()["error"]["details"]["fields"][0]
    assert field["loc"] == ["body", "new_starts_at"]
    assert field["message"] == "Укажите новое время"
    await db_session.refresh(request)
    assert request.status is ChangeRequestStatus.PENDING
    await db_session.refresh(lesson)
    assert lesson.starts_at == LESSON_START


async def test_reject_requires_response_and_family_sees_it(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    family = await make_family(db_session)
    parent = await make_parent(db_session, family)
    child = await make_child(db_session, family)
    lesson, request = await request_for(db_session, child, requested_by=parent)
    await make_tutor(db_session)
    await login(client, "tutor@example.com")

    for blank in ("", "   "):
        r = await client.post(reject_url(request.id), json={"tutor_response": blank})
        assert r.status_code == 422
        field = r.json()["error"]["details"]["fields"][0]
        assert field["loc"] == ["body", "tutor_response"]
        assert field["message"] == "Напишите ответ родителю"
    assert (await client.post(reject_url(request.id), json={})).status_code == 422

    r = await client.post(reject_url(request.id), json={"tutor_response": "  В это время занят  "})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "rejected"
    assert body["tutor_response"] == "В это время занят"
    assert body["resolved_at"] is not None
    assert body["warnings"] == []
    assert body["lesson"]["status"] == "scheduled"

    await login(client, "parent@example.com")
    detail = (await client.get(f"/api/me/lessons/{lesson.id}")).json()
    assert detail["change_request"]["status"] == "rejected"
    assert detail["change_request"]["tutor_response"] == "В это время занят"


async def test_outdated_request_cannot_be_approved_but_can_be_rejected(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    lesson, request = await request_for(db_session, child, type=ChangeRequestType.RESCHEDULE)
    patched = await tutor_client.patch(
        f"/api/admin/lessons/{lesson.id}", json={"status": "cancelled"}
    )
    assert patched.status_code == 200
    new_start = LESSON_START + timedelta(days=1)
    r = await tutor_client.post(
        approve_url(request.id), json={"new_starts_at": new_start.isoformat()}
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "change_request_outdated"
    assert r.json()["error"]["message"] == "Занятие уже изменено — отклоните запрос с комментарием"
    await db_session.refresh(lesson)
    assert lesson.status is LessonStatus.CANCELLED
    assert lesson.starts_at == LESSON_START
    await db_session.refresh(request)
    assert request.status is ChangeRequestStatus.PENDING

    rejected = await tutor_client.post(reject_url(request.id), json={"tutor_response": "Уже снято"})
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"


async def test_resolve_twice_is_409(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    _, request = await request_for(db_session, child)
    assert (await tutor_client.post(approve_url(request.id), json={})).status_code == 200
    for r in (
        await tutor_client.post(approve_url(request.id), json={}),
        await tutor_client.post(reject_url(request.id), json={"tutor_response": "Нет"}),
    ):
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "change_request_not_pending"


async def test_withdrawn_cannot_be_approved(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    lesson, request = await request_for(
        db_session, child, status=ChangeRequestStatus.WITHDRAWN, resolved_at=NOW
    )
    r = await tutor_client.post(approve_url(request.id), json={})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "change_request_not_pending"
    await db_session.refresh(lesson)
    assert lesson.status is LessonStatus.SCHEDULED


async def test_slot_taken_on_reschedule_is_409(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    series = await make_series(db_session, child)
    taken = LESSON_START + timedelta(days=7)
    await make_lesson(db_session, series=series, starts_at=taken)
    lesson, request = await request_for(
        db_session,
        child,
        lesson_overrides={"series_id": series.id},
        type=ChangeRequestType.RESCHEDULE,
    )
    r = await tutor_client.post(approve_url(request.id), json={"new_starts_at": taken.isoformat()})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "lesson_slot_taken"
    await db_session.refresh(request)
    assert request.status is ChangeRequestStatus.PENDING
    await db_session.refresh(lesson)
    assert lesson.starts_at == LESSON_START
    assert lesson.is_detached is False


async def test_unknown_request_is_404(tutor_client: AsyncClient) -> None:
    missing = uuid.uuid4()
    for r in (
        await tutor_client.post(approve_url(missing), json={}),
        await tutor_client.post(reject_url(missing), json={"tutor_response": "Нет"}),
    ):
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "change_request_not_found"


ENDPOINTS = [
    ("GET", "/api/admin/change-requests", None),
    ("POST", f"/api/admin/change-requests/{uuid.uuid4()}/approve", {}),
    ("POST", f"/api/admin/change-requests/{uuid.uuid4()}/reject", {"tutor_response": "Нет"}),
]


@pytest.mark.parametrize(("method", "path", "payload"), ENDPOINTS)
async def test_requests_admin_only(
    client: AsyncClient, db_session: AsyncSession, method: str, path: str, payload: Any
) -> None:
    anonymous = await client.request(method, path, json=payload)
    assert anonymous.status_code == 401
    await make_parent(db_session, await make_family(db_session))
    await login(client, "parent@example.com")
    r = await client.request(method, path, json=payload)
    assert r.status_code == 404
