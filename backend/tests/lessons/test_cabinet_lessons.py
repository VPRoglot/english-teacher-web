from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.families.models import Family
from app.lessons.models import Lesson, LessonNote, LessonStatus
from tests.factories import make_child
from tests.lessons.conftest import make_lesson

NOW = datetime.now(UTC)
PRIVATE = "Сложности с Past Simple"
MISSING_ID = "019c0000-0000-7000-8000-000000000000"


def week() -> dict[str, str]:
    return {"from": NOW.isoformat(), "to": (NOW + timedelta(days=7)).isoformat()}


async def only_family(session: AsyncSession) -> Family:
    """Единственная семья теста — семья клиента `parent_client`."""
    return (await session.scalars(select(Family))).one()


async def add_note(session: AsyncSession, lesson: Lesson, shared: str, private: str) -> None:
    session.add(LessonNote(lesson_id=lesson.id, shared_text=shared, private_text=private))
    await session.flush()


async def test_parent_sees_all_children_lessons_with_shared_note_only(
    parent_client: AsyncClient, db_session: AsyncSession
) -> None:
    family = await only_family(db_session)
    masha = await make_child(db_session, family, full_name="Маша")
    petya = await make_child(db_session, family, full_name="Петя")
    first = await make_lesson(db_session, child=masha, starts_at=NOW + timedelta(days=1))
    second = await make_lesson(db_session, child=petya, starts_at=NOW + timedelta(days=2))
    await add_note(db_session, first, "Молодец", PRIVATE)

    listing = await parent_client.get("/api/me/lessons", params=week())
    assert listing.status_code == 200
    items = listing.json()
    assert [i["id"] for i in items] == [str(first.id), str(second.id)]
    assert set(items[0]) == {
        "id",
        "child_id",
        "child_name",
        "starts_at",
        "duration_min",
        "status",
        "join_url",
        "has_shared_note",
    }
    assert items[0]["child_id"] == str(masha.id)
    assert items[0]["child_name"] == "Маша"
    assert items[0]["duration_min"] == 60
    assert items[0]["status"] == "scheduled"
    assert items[0]["has_shared_note"] is True
    assert items[1]["child_name"] == "Петя"
    assert items[1]["has_shared_note"] is False
    assert PRIVATE not in listing.text and "private" not in listing.text

    detail = await parent_client.get(f"/api/me/lessons/{first.id}")
    assert detail.status_code == 200
    assert detail.json()["shared_note"] == "Молодец"
    assert detail.json()["has_shared_note"] is True
    assert "private" not in detail.text and "Сложности" not in detail.text

    no_note = await parent_client.get(f"/api/me/lessons/{second.id}")
    assert no_note.json()["shared_note"] is None
    assert no_note.json()["has_shared_note"] is False


async def test_blank_shared_note_is_treated_as_empty(
    parent_client: AsyncClient, db_session: AsyncSession
) -> None:
    child = await make_child(db_session, await only_family(db_session))
    lesson = await make_lesson(db_session, child=child)
    await add_note(db_session, lesson, "  \n ", PRIVATE)

    r = await parent_client.get(f"/api/me/lessons/{lesson.id}")
    assert r.json()["shared_note"] is None
    assert r.json()["has_shared_note"] is False
    listing = await parent_client.get("/api/me/lessons", params=week())
    assert listing.json()[0]["has_shared_note"] is False


async def test_child_filter_and_range(parent_client: AsyncClient, db_session: AsyncSession) -> None:
    family = await only_family(db_session)
    masha = await make_child(db_session, family, full_name="Маша")
    petya = await make_child(db_session, family, full_name="Петя")
    inside = await make_lesson(db_session, child=masha, starts_at=NOW + timedelta(days=1))
    await make_lesson(db_session, child=petya, starts_at=NOW + timedelta(days=2))
    await make_lesson(db_session, child=masha, starts_at=NOW + timedelta(days=10))
    # Правая граница диапазона не включается, левая включается.
    await make_lesson(db_session, child=masha, starts_at=NOW + timedelta(days=7))
    on_start = await make_lesson(db_session, child=masha, starts_at=NOW)

    filtered = await parent_client.get(
        "/api/me/lessons", params={**week(), "child_id": str(masha.id)}
    )
    assert [i["id"] for i in filtered.json()] == [str(on_start.id), str(inside.id)]

    everyone = await parent_client.get("/api/me/lessons", params=week())
    assert len(everyone.json()) == 3


async def test_range_is_validated(parent_client: AsyncClient) -> None:
    too_long = await parent_client.get(
        "/api/me/lessons",
        params={"from": NOW.isoformat(), "to": (NOW + timedelta(days=63)).isoformat()},
    )
    assert too_long.status_code == 422
    reversed_range = await parent_client.get(
        "/api/me/lessons",
        params={"from": NOW.isoformat(), "to": (NOW - timedelta(days=1)).isoformat()},
    )
    assert reversed_range.status_code == 422
    assert (await parent_client.get("/api/me/lessons")).status_code == 422
    exactly_62 = await parent_client.get(
        "/api/me/lessons",
        params={"from": NOW.isoformat(), "to": (NOW + timedelta(days=62)).isoformat()},
    )
    assert exactly_62.status_code == 200


async def test_join_url_falls_back_to_child_default(
    parent_client: AsyncClient, db_session: AsyncSession
) -> None:
    child = await make_child(
        db_session, await only_family(db_session), default_meeting_url="https://zoom.example/kid"
    )
    own = await make_lesson(db_session, child=child, meeting_url="https://zoom.example/own")
    fallback = await make_lesson(db_session, child=child, starts_at=NOW + timedelta(days=2))

    own_detail = await parent_client.get(f"/api/me/lessons/{own.id}")
    assert own_detail.json()["join_url"] == "https://zoom.example/own"
    fallback_detail = await parent_client.get(f"/api/me/lessons/{fallback.id}")
    assert fallback_detail.json()["join_url"] == "https://zoom.example/kid"
    listing = await parent_client.get("/api/me/lessons", params=week())
    assert [i["join_url"] for i in listing.json()] == [
        "https://zoom.example/own",
        "https://zoom.example/kid",
    ]


async def test_cancelled_lessons_keep_their_status(
    parent_client: AsyncClient, db_session: AsyncSession
) -> None:
    child = await make_child(db_session, await only_family(db_session))
    lesson = await make_lesson(db_session, child=child, status=LessonStatus.CANCELLED_LATE)
    r = await parent_client.get(f"/api/me/lessons/{lesson.id}")
    assert r.json()["status"] == "cancelled_late"


async def test_unknown_lesson_is_404(parent_client: AsyncClient) -> None:
    r = await parent_client.get(f"/api/me/lessons/{MISSING_ID}")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "lesson_not_found"


async def test_unknown_child_filter_is_404(parent_client: AsyncClient) -> None:
    r = await parent_client.get("/api/me/lessons", params={**week(), "child_id": MISSING_ID})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "child_not_found"


async def test_anonymous_gets_401(client: AsyncClient) -> None:
    assert (await client.get("/api/me/lessons", params=week())).status_code == 401
    assert (await client.get(f"/api/me/lessons/{MISSING_ID}")).status_code == 401
