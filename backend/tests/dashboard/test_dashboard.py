"""Дашборд администратора: новые заявки, ждущие запросы, «нужно отметить», сегодня."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.families.models import Child
from app.lessons.admin_router import get_now
from app.lessons.models import ChangeRequestStatus, LessonStatus
from tests.factories import make_child, make_family
from tests.leads.conftest import make_lead
from tests.lessons.conftest import make_change_request, make_lesson

NOW = datetime(2026, 10, 12, 12, tzinfo=UTC)  # 15:00 MSK, 17:00 Екатеринбург
URL = "/api/admin/dashboard"


@pytest.fixture(autouse=True)
def frozen_now(app: FastAPI) -> Iterator[None]:
    app.dependency_overrides[get_now] = lambda: NOW
    yield
    app.dependency_overrides.pop(get_now, None)


@pytest.fixture
async def child(db_session: AsyncSession) -> Child:
    return await make_child(db_session, await make_family(db_session), full_name="Маша")


async def test_dashboard_sections(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    for i in range(6):
        await make_lead(
            db_session, status="new", child_name=f"Новый {i}", created_at=NOW - timedelta(hours=i)
        )
    await make_lead(db_session, status="contacted", child_name="Связались")

    base = NOW + timedelta(days=3)
    pending = []
    for i, age in enumerate((1, 5, 3)):
        lesson = await make_lesson(db_session, child=child, starts_at=base + timedelta(hours=i))
        if i < 2:
            pending.append(
                await make_change_request(db_session, lesson, created_at=NOW - timedelta(hours=age))
            )
        else:
            await make_change_request(
                db_session,
                lesson,
                status=ChangeRequestStatus.REJECTED,
                tutor_response="нет",
                resolved_at=NOW,
            )

    for i in range(12):
        await make_lesson(db_session, child=child, starts_at=NOW - timedelta(days=2, hours=i))
    await make_lesson(
        db_session,
        child=child,
        starts_at=NOW - timedelta(days=5),
        status=LessonStatus.COMPLETED,
    )

    # Сегодня в Москве: 12 октября 00:00–24:00 MSK = 11 окт 21:00 – 12 окт 21:00 UTC.
    inside = await make_lesson(
        db_session, child=child, starts_at=datetime(2026, 10, 12, 20, 30, tzinfo=UTC)
    )
    await make_lesson(db_session, child=child, starts_at=datetime(2026, 10, 12, 21, 30, tzinfo=UTC))
    await make_lesson(
        db_session,
        child=child,
        starts_at=datetime(2026, 10, 12, 15, tzinfo=UTC),
        status=LessonStatus.CANCELLED,
    )
    await make_lesson(
        db_session,
        child=child,
        starts_at=datetime(2026, 10, 12, 16, tzinfo=UTC),
        status=LessonStatus.CANCELLED_LATE,
    )

    r = await tutor_client.get(URL)

    assert r.status_code == 200
    body = r.json()
    assert body["timezone"] == "Europe/Moscow"
    assert body["new_leads"]["total"] == 6
    assert [x["child_name"] for x in body["new_leads"]["items"]] == [f"Новый {i}" for i in range(5)]
    assert body["pending_requests"]["total"] == 2
    assert [x["id"] for x in body["pending_requests"]["items"]] == [
        str(pending[1].id),
        str(pending[0].id),
    ]
    assert body["pending_requests"]["items"][0]["child"]["full_name"] == "Маша"
    marking = body["needs_marking"]
    assert marking["total"] == 12
    assert len(marking["items"]) == 10
    starts = [x["starts_at"] for x in marking["items"]]
    assert starts == sorted(starts)
    assert all(x["status"] == "scheduled" for x in marking["items"])
    assert [x["id"] for x in body["today"]] == [str(inside.id)]


async def test_today_follows_tutor_timezone(
    tutor_client: AsyncClient, db_session: AsyncSession, child: Child
) -> None:
    r = await tutor_client.put(
        "/api/admin/settings", json={"timezone": "Asia/Yekaterinburg", "cancel_policy_hours": 24}
    )
    assert r.status_code == 200
    # Сегодня в Екатеринбурге: 11 окт 19:00 – 12 окт 19:00 UTC.
    early = await make_lesson(
        db_session, child=child, starts_at=datetime(2026, 10, 11, 20, tzinfo=UTC)
    )
    late = await make_lesson(
        db_session, child=child, starts_at=datetime(2026, 10, 12, 18, 30, tzinfo=UTC)
    )
    await make_lesson(db_session, child=child, starts_at=datetime(2026, 10, 12, 19, 30, tzinfo=UTC))
    await make_lesson(db_session, child=child, starts_at=datetime(2026, 10, 11, 18, 30, tzinfo=UTC))

    body = (await tutor_client.get(URL)).json()

    assert body["timezone"] == "Asia/Yekaterinburg"
    assert [x["id"] for x in body["today"]] == [str(early.id), str(late.id)]


async def test_dashboard_empty(tutor_client: AsyncClient) -> None:
    body = (await tutor_client.get(URL)).json()
    assert body["new_leads"] == {"items": [], "total": 0}
    assert body["pending_requests"] == {"items": [], "total": 0}
    assert body["needs_marking"] == {"items": [], "total": 0}
    assert body["today"] == []


async def test_dashboard_admin_only(client: AsyncClient, parent_client: AsyncClient) -> None:
    assert (await parent_client.get(URL)).status_code == 404


async def test_dashboard_requires_session(client: AsyncClient) -> None:
    assert (await client.get(URL)).status_code == 401
