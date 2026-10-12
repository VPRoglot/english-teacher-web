import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.families.models import Child
from app.lessons.models import Lesson, LessonNote
from tests.factories import make_child, make_family
from tests.lessons.conftest import make_lesson

SOON = datetime.now(UTC) + timedelta(days=3)


@pytest.fixture
async def lesson(db_session: AsyncSession) -> Lesson:
    child: Child = await make_child(db_session, await make_family(db_session))
    return await make_lesson(db_session, child=child, starts_at=SOON)


async def test_notes_upsert_and_show_in_detail(
    tutor_client: AsyncClient, db_session: AsyncSession, lesson: Lesson
) -> None:
    url = f"/api/admin/lessons/{lesson.id}/notes"
    first = await tutor_client.put(url, json={"shared_text": "v1", "private_text": "секрет"})
    assert first.status_code == 200
    assert first.json() == {"shared_text": "v1", "private_text": "секрет"}
    second = await tutor_client.put(url, json={"shared_text": "v2", "private_text": ""})
    assert second.json() == {"shared_text": "v2", "private_text": ""}

    rows = await db_session.scalar(
        select(func.count()).select_from(LessonNote).where(LessonNote.lesson_id == lesson.id)
    )
    assert rows == 1
    detail = await tutor_client.get(f"/api/admin/lessons/{lesson.id}")
    assert detail.json()["notes"] == {"shared_text": "v2", "private_text": ""}
    assert detail.json()["has_notes"] is True

    start = SOON - timedelta(hours=1)
    listing = await tutor_client.get(
        "/api/admin/lessons",
        params={"from": start.isoformat(), "to": (start + timedelta(days=1)).isoformat()},
    )
    assert [(i["id"], i["has_notes"]) for i in listing.json()] == [(str(lesson.id), True)]


async def test_empty_notes_do_not_count_as_notes(tutor_client: AsyncClient, lesson: Lesson) -> None:
    r = await tutor_client.put(
        f"/api/admin/lessons/{lesson.id}/notes", json={"shared_text": "", "private_text": ""}
    )
    assert r.status_code == 200
    detail = await tutor_client.get(f"/api/admin/lessons/{lesson.id}")
    assert detail.json()["has_notes"] is False


async def test_notes_limit_is_20000_characters(tutor_client: AsyncClient, lesson: Lesson) -> None:
    url = f"/api/admin/lessons/{lesson.id}/notes"
    ok = await tutor_client.put(url, json={"shared_text": "я" * 20000, "private_text": "x"})
    assert ok.status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        {"shared_text": "я" * 20001, "private_text": ""},
        {"shared_text": "", "private_text": "я" * 20001},
        {"shared_text": "a"},
        {"shared_text": None, "private_text": ""},
    ],
)
async def test_notes_too_long_or_incomplete_is_422(
    tutor_client: AsyncClient, lesson: Lesson, body: dict[str, Any]
) -> None:
    r = await tutor_client.put(f"/api/admin/lessons/{lesson.id}/notes", json=body)
    assert r.status_code == 422


async def test_notes_of_unknown_lesson_is_404(tutor_client: AsyncClient) -> None:
    r = await tutor_client.put(
        f"/api/admin/lessons/{uuid.uuid4()}/notes", json={"shared_text": "", "private_text": ""}
    )
    assert r.status_code == 404 and r.json()["error"]["code"] == "lesson_not_found"


async def test_notes_lock_the_lesson_before_upsert(
    tutor_client: AsyncClient, lesson: Lesson, sql_log: list[str]
) -> None:
    r = await tutor_client.put(
        f"/api/admin/lessons/{lesson.id}/notes", json={"shared_text": "x", "private_text": "y"}
    )

    assert r.status_code == 200
    lock = next(i for i, s in enumerate(sql_log) if "FROM lessons" in s and "FOR UPDATE" in s)
    upsert = next(i for i, s in enumerate(sql_log) if "INSERT INTO lesson_notes" in s)
    assert lock < upsert
