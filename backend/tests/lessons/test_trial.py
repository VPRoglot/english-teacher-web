import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.lessons.models import Lesson, LessonKind
from tests.factories import make_child, make_family
from tests.leads.conftest import make_lead
from tests.lessons.conftest import make_lesson

TRIAL_BODY = {"starts_at": "2026-10-20T15:00:00Z", "meeting_url": "https://meet.example/x"}


async def test_schedule_trial_creates_lesson_and_moves_lead(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    lead = await make_lead(db_session, status="contacted", child_name="Петя")

    r = await tutor_client.post(f"/api/admin/leads/{lead.id}/trial", json=TRIAL_BODY)

    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "trial" and body["status"] == "scheduled"
    assert body["duration_min"] == 30
    assert body["starts_at"].startswith("2026-10-20T15:00:00")
    assert body["meeting_url"] == "https://meet.example/x"
    assert body["join_url"] == "https://meet.example/x"
    assert body["series_id"] is None and body["is_detached"] is False
    assert body["warnings"] == []
    assert body["student"] == {
        "child_id": None,
        "lead_id": str(lead.id),
        "name": "Петя",
        "family_id": None,
        "family_name": None,
    }
    lesson = await db_session.get(Lesson, body["id"])
    assert lesson is not None
    assert lesson.kind is LessonKind.TRIAL
    assert lesson.lead_id == lead.id and lesson.child_id is None

    detail = (await tutor_client.get(f"/api/admin/leads/{lead.id}")).json()
    assert detail["status"] == "trial_scheduled"
    assert detail["history"][-1]["from_status"] == "contacted"
    assert detail["history"][-1]["to_status"] == "trial_scheduled"
    assert detail["history"][-1]["comment"] == "Пробное занятие 20.10.2026 18:00"


async def test_schedule_trial_from_new_with_explicit_duration(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    lead = await make_lead(db_session, status="new")

    r = await tutor_client.post(
        f"/api/admin/leads/{lead.id}/trial",
        json={"starts_at": "2026-10-20T15:00:00Z", "duration_min": 45},
    )

    assert r.status_code == 201
    assert r.json()["duration_min"] == 45
    assert r.json()["meeting_url"] is None and r.json()["join_url"] is None


async def test_trial_comment_uses_tutor_timezone(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    saved = await tutor_client.put(
        "/api/admin/settings", json={"timezone": "Asia/Yekaterinburg", "cancel_policy_hours": 24}
    )
    assert saved.status_code == 200
    lead = await make_lead(db_session, status="new")

    await tutor_client.post(f"/api/admin/leads/{lead.id}/trial", json=TRIAL_BODY)

    detail = (await tutor_client.get(f"/api/admin/leads/{lead.id}")).json()
    assert detail["history"][-1]["comment"] == "Пробное занятие 20.10.2026 20:00"


async def test_trial_overlap_returns_warning_but_saves(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    family = await make_family(db_session)
    child = await make_child(db_session, family)
    other = await make_lesson(
        db_session, child=child, starts_at=datetime(2026, 10, 20, 15, 15, tzinfo=UTC)
    )
    lead = await make_lead(db_session, status="new")

    r = await tutor_client.post(f"/api/admin/leads/{lead.id}/trial", json=TRIAL_BODY)

    assert r.status_code == 201
    assert [w["lesson_id"] for w in r.json()["warnings"]] == [str(other.id)]


async def test_double_click_creates_one_trial(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    lead = await make_lead(db_session, status="new")

    first = await tutor_client.post(f"/api/admin/leads/{lead.id}/trial", json=TRIAL_BODY)
    second = await tutor_client.post(f"/api/admin/leads/{lead.id}/trial", json=TRIAL_BODY)

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "invalid_status_transition"
    listed = await tutor_client.get(f"/api/admin/leads/{lead.id}/trial-lessons")
    assert len(listed.json()) == 1


@pytest.mark.parametrize("status", ["converted", "rejected", "trial_scheduled"])
async def test_trial_from_wrong_status_is_409(
    tutor_client: AsyncClient, db_session: AsyncSession, status: str
) -> None:
    lead = await make_lead(db_session, status=status)

    r = await tutor_client.post(f"/api/admin/leads/{lead.id}/trial", json=TRIAL_BODY)

    assert r.status_code == 409
    assert r.json()["error"]["code"] == "invalid_status_transition"
    assert list(await db_session.scalars(select(Lesson))) == []
    detail = (await tutor_client.get(f"/api/admin/leads/{lead.id}")).json()
    assert detail["status"] == status


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"starts_at": "2026-10-20T15:00:00"},
        {"starts_at": "2026-10-20T15:00:00Z", "duration_min": 10},
        {"starts_at": "2026-10-20T15:00:00Z", "duration_min": 241},
        {"starts_at": "2026-10-20T15:00:00Z", "meeting_url": "not a url"},
    ],
)
async def test_trial_validates_body(
    tutor_client: AsyncClient, db_session: AsyncSession, body: dict[str, Any]
) -> None:
    lead = await make_lead(db_session, status="new")

    r = await tutor_client.post(f"/api/admin/leads/{lead.id}/trial", json=body)

    assert r.status_code == 422
    detail = (await tutor_client.get(f"/api/admin/leads/{lead.id}")).json()
    assert detail["status"] == "new"


async def test_trial_then_convert_works(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    lead = await make_lead(db_session, status="new")
    trial = await tutor_client.post(f"/api/admin/leads/{lead.id}/trial", json=TRIAL_BODY)
    assert trial.status_code == 201

    r = await tutor_client.post(
        f"/api/admin/leads/{lead.id}/convert",
        json={
            "family_name": "Семья Маши",
            "child": {"full_name": "Маша"},
            "parent": {"full_name": "Анна Смирнова", "phone": "8 999 123 45 67"},
        },
    )

    assert r.status_code == 201
    lesson = await db_session.get(Lesson, trial.json()["id"])
    assert lesson is not None
    await db_session.refresh(lesson)
    assert lesson.lead_id == lead.id and lesson.child_id is None
    assert lesson.kind is LessonKind.TRIAL


async def test_rejecting_lead_keeps_trial_lesson(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    lead = await make_lead(db_session, status="new")
    trial = await tutor_client.post(f"/api/admin/leads/{lead.id}/trial", json=TRIAL_BODY)

    r = await tutor_client.patch(
        f"/api/admin/leads/{lead.id}", json={"status": "rejected", "reject_reason": "дорого"}
    )

    assert r.status_code == 200
    assert (await tutor_client.get(f"/api/admin/lessons/{trial.json()['id']}")).status_code == 200


async def test_trial_lessons_list_and_unknown_lead(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    lead = await make_lead(db_session, status="contacted", child_name="Петя")
    other = await make_lead(db_session, status="contacted")
    later = await make_lesson(
        db_session, lead=lead, starts_at=datetime(2026, 10, 25, 9, 0, tzinfo=UTC)
    )
    earlier = await make_lesson(
        db_session, lead=lead, starts_at=datetime(2026, 10, 21, 9, 0, tzinfo=UTC)
    )
    await make_lesson(db_session, lead=other)

    r = await tutor_client.get(f"/api/admin/leads/{lead.id}/trial-lessons")

    assert r.status_code == 200
    assert [x["id"] for x in r.json()] == [str(earlier.id), str(later.id)]
    assert r.json()[0]["student"]["name"] == "Петя"
    assert r.json()[0]["kind"] == "trial"

    missing = uuid.uuid4()
    for resp in (
        await tutor_client.get(f"/api/admin/leads/{missing}/trial-lessons"),
        await tutor_client.post(f"/api/admin/leads/{missing}/trial", json=TRIAL_BODY),
    ):
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "lead_not_found"


async def test_trial_lessons_of_anonymized_lead_is_404(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    lead = await make_lead(db_session, anonymized_at=datetime.now(UTC))

    r = await tutor_client.get(f"/api/admin/leads/{lead.id}/trial-lessons")

    assert r.status_code == 404
    assert r.json()["error"]["code"] == "lead_not_found"


PATHS = [
    ("POST", "/api/admin/leads/{id}/trial"),
    ("GET", "/api/admin/leads/{id}/trial-lessons"),
]


@pytest.mark.parametrize(("method", "path"), PATHS)
async def test_trial_is_hidden_from_family(
    parent_client: AsyncClient, method: str, path: str
) -> None:
    r = await parent_client.request(method, path.format(id=uuid.uuid4()), json=TRIAL_BODY)
    assert r.status_code == 404


@pytest.mark.parametrize(("method", "path"), PATHS)
async def test_trial_requires_login(client: AsyncClient, method: str, path: str) -> None:
    r = await client.request(method, path.format(id=uuid.uuid4()), json=TRIAL_BODY)
    assert r.status_code == 401
