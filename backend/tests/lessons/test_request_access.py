from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.families.models import Child
from app.lessons.models import LessonNote
from tests.factories import make_child, make_family
from tests.leads.conftest import make_lead
from tests.lessons.conftest import make_change_request, make_lesson
from tests.lessons.test_cabinet_lessons import only_family


def future() -> dict[str, Any]:
    return {"starts_at": datetime.now(UTC) + timedelta(days=3)}


async def test_child_cannot_create_or_withdraw(
    child_client: AsyncClient, db_session: AsyncSession
) -> None:
    child = (await db_session.scalars(select(Child))).one()
    lesson = await make_lesson(db_session, child=child, **future())
    pending = await make_change_request(db_session, lesson)
    created = await child_client.post(
        f"/api/me/lessons/{lesson.id}/change-requests", json={"type": "cancel"}
    )
    assert created.status_code == 404
    withdrawn = await child_client.delete(f"/api/me/change-requests/{pending.id}")
    assert withdrawn.status_code == 404


async def test_other_family_gets_404(parent_client: AsyncClient, db_session: AsyncSession) -> None:
    other = await make_family(db_session, name="Петровы")
    stranger = await make_child(db_session, other, username="stranger")
    lesson = await make_lesson(db_session, child=stranger, **future())
    foreign = await make_change_request(db_session, lesson)
    created = await parent_client.post(
        f"/api/me/lessons/{lesson.id}/change-requests", json={"type": "cancel"}
    )
    assert created.status_code == 404
    assert created.json()["error"]["code"] == "lesson_not_found"
    withdrawn = await parent_client.delete(f"/api/me/change-requests/{foreign.id}")
    assert withdrawn.status_code == 404
    assert withdrawn.json()["error"]["code"] == "change_request_not_found"
    assert (await parent_client.get(f"/api/me/lessons/{lesson.id}")).status_code == 404


async def test_trial_lesson_not_requestable(
    parent_client: AsyncClient, db_session: AsyncSession
) -> None:
    lead = await make_lead(db_session)
    lesson = await make_lesson(db_session, lead=lead, **future())
    r = await parent_client.post(
        f"/api/me/lessons/{lesson.id}/change-requests", json={"type": "cancel"}
    )
    assert r.status_code == 404


async def test_family_response_has_no_private_fields(
    parent_client: AsyncClient, db_session: AsyncSession
) -> None:
    family = await only_family(db_session)
    child = await make_child(db_session, family)
    lesson = await make_lesson(db_session, child=child, **future())
    db_session.add(LessonNote(lesson_id=lesson.id, shared_text="ок", private_text="СЕКРЕТ-ЗАМЕТКА"))
    await db_session.flush()
    created = await parent_client.post(
        f"/api/me/lessons/{lesson.id}/change-requests", json={"type": "cancel"}
    )
    raw = await parent_client.get(f"/api/me/lessons/{lesson.id}")
    for text in (raw.text, created.text):
        assert "private" not in text
        assert "requested_by" not in text
        assert "СЕКРЕТ-ЗАМЕТКА" not in text
        assert "notified_at" not in text
