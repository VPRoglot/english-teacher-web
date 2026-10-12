from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.families.models import Child
from app.lessons.models import ChangeRequestStatus, ChangeRequestType, Lesson
from app.lessons.requests_service import lesson_ids_with_requests
from tests.factories import make_child, make_family
from tests.lessons.conftest import make_change_request, make_lesson

NOW = datetime(2026, 10, 12, 9, tzinfo=UTC)


@pytest.fixture
async def child(db_session: AsyncSession) -> Child:
    return await make_child(db_session, await make_family(db_session))


@pytest.fixture
async def lesson(db_session: AsyncSession, child: Child) -> Lesson:
    return await make_lesson(db_session, child=child)


async def test_defaults_and_enum_values(db_session: AsyncSession, lesson: Lesson) -> None:
    request = await make_change_request(db_session, lesson, type=ChangeRequestType.RESCHEDULE)
    await db_session.refresh(request)
    assert request.status is ChangeRequestStatus.PENDING
    assert request.resolved_at is None and request.notified_at is None
    assert [m.value for m in ChangeRequestType] == ["reschedule", "cancel"]
    assert [m.value for m in ChangeRequestStatus] == [
        "pending",
        "approved",
        "rejected",
        "withdrawn",
    ]


async def test_one_pending_per_lesson(db_session: AsyncSession, lesson: Lesson) -> None:
    await make_change_request(db_session, lesson)
    # другие статусы рядом с ждущим запросом допустимы
    await make_change_request(
        db_session,
        lesson,
        status=ChangeRequestStatus.REJECTED,
        resolved_at=NOW,
        tutor_response="Нельзя",
    )
    await make_change_request(
        db_session, lesson, status=ChangeRequestStatus.WITHDRAWN, resolved_at=NOW
    )
    with pytest.raises(IntegrityError, match="uq_change_requests_lesson_pending"):
        await make_change_request(db_session, lesson)


async def test_pending_on_other_lesson_is_allowed(
    db_session: AsyncSession, child: Child, lesson: Lesson
) -> None:
    other = await make_lesson(db_session, child=child)
    await make_change_request(db_session, lesson)
    await make_change_request(db_session, other)


async def test_resolved_at_matches_status(db_session: AsyncSession, lesson: Lesson) -> None:
    with pytest.raises(IntegrityError, match="resolved_consistent"):
        await make_change_request(db_session, lesson, resolved_at=NOW)


async def test_resolved_status_needs_resolved_at(db_session: AsyncSession, lesson: Lesson) -> None:
    with pytest.raises(IntegrityError, match="resolved_consistent"):
        await make_change_request(db_session, lesson, status=ChangeRequestStatus.APPROVED)


async def test_rejected_needs_response(db_session: AsyncSession, lesson: Lesson) -> None:
    with pytest.raises(IntegrityError, match="rejection_has_response"):
        await make_change_request(
            db_session, lesson, status=ChangeRequestStatus.REJECTED, resolved_at=NOW
        )


async def test_lesson_with_request_cannot_be_deleted_at_db_level(
    db_session: AsyncSession, lesson: Lesson
) -> None:
    await make_change_request(db_session, lesson)
    with pytest.raises(IntegrityError, match="fk_change_requests_lesson_id_lessons"):
        await db_session.delete(lesson)
        await db_session.flush()


async def test_lesson_ids_with_requests(
    db_session: AsyncSession, child: Child, lesson: Lesson
) -> None:
    withdrawn = await make_lesson(db_session, child=child)
    clean = await make_lesson(db_session, child=child)
    await make_change_request(db_session, lesson)
    await make_change_request(
        db_session, withdrawn, status=ChangeRequestStatus.WITHDRAWN, resolved_at=NOW
    )
    found = await lesson_ids_with_requests(db_session, [lesson.id, withdrawn.id, clean.id])
    assert found == {lesson.id, withdrawn.id}
    assert await lesson_ids_with_requests(db_session, []) == set()
