"""Права доступа к занятиям в кабинете: чужие семьи, брат/сестра, пробные, архив, private_text."""

from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.lessons.models import LessonNote
from tests.factories import login, make_child, make_family, make_parent
from tests.leads.conftest import make_lead
from tests.lessons.conftest import make_lesson

NOW = datetime.now(UTC)
PRIVATE = "Приватно: путает Past Simple"
SHARED = "Общая заметка для семьи"


def week() -> dict[str, str]:
    return {"from": NOW.isoformat(), "to": (NOW + timedelta(days=7)).isoformat()}


async def lesson_with_note(session: AsyncSession, child, **overrides):  # type: ignore[no-untyped-def]
    lesson = await make_lesson(session, child=child, starts_at=NOW + timedelta(days=1), **overrides)
    session.add(LessonNote(lesson_id=lesson.id, shared_text=SHARED, private_text=PRIVATE))
    await session.flush()
    return lesson


async def test_parent_of_family_a_gets_404_for_family_b(
    parent_client: AsyncClient, db_session: AsyncSession
) -> None:
    family_a_child = await make_child(
        db_session, await _family_of(db_session, "Ивановы"), full_name="Своя"
    )
    own = await lesson_with_note(db_session, family_a_child)
    family_b = await make_family(db_session, name="Петровы")
    child_b = await make_child(db_session, family_b, full_name="Чужой")
    foreign = await lesson_with_note(db_session, child_b)

    r = await parent_client.get(f"/api/me/lessons/{foreign.id}")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "lesson_not_found"
    assert SHARED not in r.text and "Чужой" not in r.text

    by_child = await parent_client.get(
        "/api/me/lessons", params={**week(), "child_id": str(child_b.id)}
    )
    assert by_child.status_code == 404
    assert by_child.json()["error"]["code"] == "child_not_found"

    listing = await parent_client.get("/api/me/lessons", params=week())
    assert [i["id"] for i in listing.json()] == [str(own.id)]
    assert "Чужой" not in listing.text


async def _family_of(session: AsyncSession, name: str):  # type: ignore[no-untyped-def]
    from sqlalchemy import select

    from app.families.models import Family

    return (await session.scalars(select(Family).where(Family.name == name))).one()


async def test_child_sees_only_own_lessons(
    child_client: AsyncClient, db_session: AsyncSession
) -> None:
    masha = await _child_named(db_session, "Маша")
    family = await _family_of(db_session, "Ивановы")
    brother = await make_child(db_session, family, full_name="Вася")
    own = await lesson_with_note(db_session, masha)
    siblings = await lesson_with_note(db_session, brother)

    r = await child_client.get(f"/api/me/lessons/{siblings.id}")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "lesson_not_found"

    listing = await child_client.get("/api/me/lessons", params=week())
    assert [i["id"] for i in listing.json()] == [str(own.id)]

    by_brother = await child_client.get(
        "/api/me/lessons", params={**week(), "child_id": str(brother.id)}
    )
    assert by_brother.status_code == 404
    assert by_brother.json()["error"]["code"] == "child_not_found"

    own_detail = await child_client.get(f"/api/me/lessons/{own.id}")
    assert own_detail.status_code == 200
    assert own_detail.json()["shared_note"] == SHARED


async def _child_named(session: AsyncSession, name: str):  # type: ignore[no-untyped-def]
    from sqlalchemy import select

    from app.families.models import Child

    return (await session.scalars(select(Child).where(Child.full_name == name))).one()


async def test_trial_lessons_never_reach_cabinet(
    parent_client: AsyncClient, db_session: AsyncSession
) -> None:
    child = await make_child(db_session, await _family_of(db_session, "Ивановы"))
    regular = await make_lesson(db_session, child=child)
    lead = await make_lead(db_session)
    trial = await make_lesson(db_session, lead=lead, starts_at=NOW + timedelta(days=2))

    listing = await parent_client.get("/api/me/lessons", params=week())
    assert [i["id"] for i in listing.json()] == [str(regular.id)]
    r = await parent_client.get(f"/api/me/lessons/{trial.id}")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "lesson_not_found"


async def test_archived_child_lessons_hidden_from_parent(
    parent_client: AsyncClient, db_session: AsyncSession
) -> None:
    family = await _family_of(db_session, "Ивановы")
    active = await make_child(db_session, family, full_name="Активная")
    archived = await make_child(db_session, family, full_name="Архивный", archived=True)
    visible = await make_lesson(db_session, child=active)
    hidden = await make_lesson(db_session, child=archived, starts_at=NOW + timedelta(days=2))

    listing = await parent_client.get("/api/me/lessons", params=week())
    assert [i["id"] for i in listing.json()] == [str(visible.id)]
    assert (await parent_client.get(f"/api/me/lessons/{hidden.id}")).status_code == 404
    by_child = await parent_client.get(
        "/api/me/lessons", params={**week(), "child_id": str(archived.id)}
    )
    assert by_child.status_code == 404


async def test_archived_family_loses_access(client: AsyncClient, db_session: AsyncSession) -> None:
    family = await make_family(db_session, name="Архивные")
    await make_parent(db_session, family, email="old@example.com")
    child = await make_child(db_session, family)
    lesson = await make_lesson(db_session, child=child)
    await login(client, "old@example.com")
    assert (await client.get(f"/api/me/lessons/{lesson.id}")).status_code == 200

    from datetime import UTC as _UTC
    from datetime import datetime as _dt

    family.archived_at = _dt.now(_UTC)
    await db_session.flush()
    assert (await client.get(f"/api/me/lessons/{lesson.id}")).status_code == 401
    assert (await client.get("/api/me/lessons", params=week())).status_code == 401


@pytest.mark.parametrize("role", ["parent", "child"])
@pytest.mark.parametrize(
    "path", ["/api/me/lessons", "/api/me/lessons/{id}", "/api/me/schedule-settings"]
)
async def test_no_private_text_anywhere_in_family_responses(
    client: AsyncClient, db_session: AsyncSession, role: str, path: str
) -> None:
    family = await make_family(db_session)
    if role == "parent":
        await make_parent(db_session, family)
        child = await make_child(db_session, family, full_name="Маша")
        await login(client, "parent@example.com")
    else:
        child = await make_child(db_session, family, full_name="Маша", username="masha")
        await login(client, "masha")
    lesson = await lesson_with_note(db_session, child)

    r = await client.get(path.format(id=lesson.id), params=week())
    assert r.status_code == 200, r.text
    assert "private" not in r.text.lower()
    assert PRIVATE not in r.text and "Приватно" not in r.text


async def test_tutor_gets_404_on_cabinet_lessons(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    child = await make_child(db_session, await make_family(db_session))
    lesson = await make_lesson(db_session, child=child)
    listing = await tutor_client.get("/api/me/lessons", params=week())
    assert listing.status_code == 404
    detail = await tutor_client.get(f"/api/me/lessons/{lesson.id}")
    assert detail.status_code == 404
