import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Invitation, PasswordReset, User, UserRole
from app.auth.service import delete_users
from app.auth.sessions import SessionStore
from app.auth.tokens import sha256_hex
from app.core.errors import AppError
from app.families.models import Child, Family, ParentProfile
from app.families.purge import PurgeSummary, describe_purge, purge_family
from app.leads.models import Lead, LeadStatus, LeadStatusHistory
from app.lessons.models import (
    ChangeRequest,
    ChangeRequestStatus,
    Lesson,
    LessonNote,
    LessonSeries,
)
from tests.factories import make_child, make_family, make_parent, make_tutor
from tests.leads.conftest import make_lead
from tests.lessons.conftest import make_change_request, make_lesson, make_series

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


@dataclass
class FamilyGraph:
    family_id: uuid.UUID
    user_ids: list[uuid.UUID]
    child_ids: list[uuid.UUID]
    lead_id: uuid.UUID
    tokens: list[str] = field(default_factory=list)


async def build_graph(
    session: AsyncSession,
    redis: Redis,
    tutor: User,
    *,
    tag: str,
    archived: bool = True,
) -> FamilyGraph:
    family = await make_family(session, name=f"Семья {tag}", archived=archived)
    p1 = await make_parent(session, family, email=f"p1-{tag}@example.com")
    p2 = await make_parent(session, family, email=f"p2-{tag}@example.com")
    c1 = await make_child(session, family, full_name=f"Маша {tag}", username=f"masha-{tag}")
    c2 = await make_child(session, family, full_name=f"Петя {tag}", username=f"petya-{tag}")
    series = await make_series(session, c1)
    start = NOW + timedelta(days=1)
    lesson1 = await make_lesson(session, series=series, starts_at=start)
    lesson2 = await make_lesson(session, series=series, starts_at=start + timedelta(days=7))
    lesson3 = await make_lesson(session, child=c2, starts_at=start)
    session.add(LessonNote(lesson_id=lesson1.id, shared_text="общее", private_text="личное"))
    await make_change_request(session, lesson2, requested_by=p1)
    await make_change_request(
        session,
        lesson3,
        requested_by=p2,
        status=ChangeRequestStatus.REJECTED,
        resolved_at=NOW,
        tutor_response="Нет",
    )
    session.add(
        Invitation(
            token_hash=sha256_hex(f"inv-{tag}"),
            family_id=family.id,
            expires_at=NOW + timedelta(days=7),
            created_by=tutor.id,
        )
    )
    session.add(
        PasswordReset(
            token_hash=sha256_hex(f"reset-{tag}"),
            user_id=p1.id,
            expires_at=NOW + timedelta(days=1),
            created_by=tutor.id,
        )
    )
    lead = await make_lead(session, status="converted", family_id=family.id)
    session.add(
        LeadStatusHistory(
            lead_id=lead.id,
            from_status=LeadStatus.NEW,
            to_status=LeadStatus.CONVERTED,
            changed_at=NOW,
        )
    )
    await make_lesson(session, lead=lead, starts_at=start)
    await session.flush()
    user_ids = [p1.id, p2.id, *[u for u in (c1.user_id, c2.user_id) if u is not None]]
    store = SessionStore(redis)
    tokens = [await store.create(uid, UserRole.PARENT) for uid in user_ids]
    await session.commit()  # purge коммитит сам, поэтому исходные данные тоже фиксируются
    return FamilyGraph(family.id, user_ids, [c1.id, c2.id], lead.id, tokens)


async def count(session: AsyncSession, *conditions: tuple[type, object]) -> int:
    total = 0
    for model, condition in conditions:
        total += (
            await session.scalar(select(func.count()).select_from(model).where(condition))  # type: ignore[arg-type]
            or 0
        )
    return total


async def family_rows(session: AsyncSession, g: FamilyGraph) -> dict[str, int]:
    lessons = select(Lesson.id).where(
        Lesson.child_id.in_(g.child_ids) | (Lesson.lead_id == g.lead_id)
    )
    counts = {
        "families": await count(session, (Family, Family.id == g.family_id)),
        "parent_profiles": await count(
            session, (ParentProfile, ParentProfile.user_id.in_(g.user_ids))
        ),
        "children": await count(session, (Child, Child.family_id == g.family_id)),
        "users": await count(session, (User, User.id.in_(g.user_ids))),
        "lesson_series": await count(
            session, (LessonSeries, LessonSeries.child_id.in_(g.child_ids))
        ),
        "lessons": await count(session, (Lesson, Lesson.id.in_(lessons))),
        "lesson_notes": await count(session, (LessonNote, LessonNote.lesson_id.in_(lessons))),
        "change_requests": await count(
            session, (ChangeRequest, ChangeRequest.lesson_id.in_(lessons))
        ),
        "invitations": await count(session, (Invitation, Invitation.family_id == g.family_id)),
        "password_resets": await count(
            session, (PasswordReset, PasswordReset.user_id.in_(g.user_ids))
        ),
        "leads": await count(session, (Lead, Lead.id == g.lead_id)),
        "lead_status_history": await count(
            session, (LeadStatusHistory, LeadStatusHistory.lead_id == g.lead_id)
        ),
    }
    return counts


EXPECTED_FULL = {
    "families": 1,
    "parent_profiles": 2,
    "children": 2,
    "users": 4,
    "lesson_series": 1,
    "lessons": 4,
    "lesson_notes": 1,
    "change_requests": 2,
    "invitations": 1,
    "password_resets": 1,
    "leads": 1,
    "lead_status_history": 2,
}


@pytest.fixture
async def tutor(db_session: AsyncSession) -> User:
    return await make_tutor(db_session)


async def sessions_alive(redis: Redis, g: FamilyGraph) -> int:
    return sum([await redis.exists(f"session:{sha256_hex(t)}") for t in g.tokens])


async def test_purge_removes_everything(
    db_session: AsyncSession, redis: Redis, tutor: User
) -> None:
    a = await build_graph(db_session, redis, tutor, tag="a")
    await build_graph(db_session, redis, tutor, tag="b")
    assert await family_rows(db_session, a) == EXPECTED_FULL

    summary = await purge_family(db_session, redis, a.family_id)

    assert summary == PurgeSummary(
        family_name="Семья a", users=4, children=2, lessons=4, change_requests=2, leads=1
    )
    assert set((await family_rows(db_session, a)).values()) == {0}


async def test_purge_keeps_other_family_and_tutor(
    db_session: AsyncSession, redis: Redis, tutor: User
) -> None:
    a = await build_graph(db_session, redis, tutor, tag="a")
    b = await build_graph(db_session, redis, tutor, tag="b")

    await purge_family(db_session, redis, a.family_id)

    assert await family_rows(db_session, b) == EXPECTED_FULL
    assert await db_session.get(User, tutor.id) is not None


async def test_purge_revokes_sessions(db_session: AsyncSession, redis: Redis, tutor: User) -> None:
    a = await build_graph(db_session, redis, tutor, tag="a")
    b = await build_graph(db_session, redis, tutor, tag="b")
    assert await sessions_alive(redis, a) == 4

    await purge_family(db_session, redis, a.family_id)

    assert await sessions_alive(redis, a) == 0
    assert await sessions_alive(redis, b) == 4


async def test_purge_requires_archived(db_session: AsyncSession, redis: Redis, tutor: User) -> None:
    a = await build_graph(db_session, redis, tutor, tag="a", archived=False)

    with pytest.raises(AppError) as exc:
        await purge_family(db_session, redis, a.family_id)

    assert exc.value.code == "family_not_archived"
    assert exc.value.message == "Сначала переведите семью в архив"
    assert await family_rows(db_session, a) == EXPECTED_FULL
    assert await sessions_alive(redis, a) == 4


async def test_purge_unknown_family(db_session: AsyncSession, redis: Redis) -> None:
    with pytest.raises(AppError) as exc:
        await purge_family(db_session, redis, uuid.uuid4())
    assert exc.value.code == "family_not_found"
    with pytest.raises(AppError) as exc2:
        await describe_purge(db_session, uuid.uuid4())
    assert exc2.value.code == "family_not_found"


async def test_describe_purge_is_read_only(
    db_session: AsyncSession, redis: Redis, tutor: User
) -> None:
    a = await build_graph(db_session, redis, tutor, tag="a")

    summary = await describe_purge(db_session, a.family_id)

    assert summary.users == 4
    assert summary.lessons == 4
    assert await family_rows(db_session, a) == EXPECTED_FULL


async def test_purge_is_atomic(
    db_session: AsyncSession, redis: Redis, tutor: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = await build_graph(db_session, redis, tutor, tag="a")

    async def boom(session: AsyncSession, user_ids: object) -> int:
        await delete_users(session, [])  # к моменту сбоя часть удалений уже выполнена
        raise RuntimeError("boom")

    monkeypatch.setattr("app.auth.service.delete_users", boom)

    with pytest.raises(RuntimeError):
        await purge_family(db_session, redis, a.family_id)

    assert await family_rows(db_session, a) == EXPECTED_FULL
    assert await sessions_alive(redis, a) == 4
