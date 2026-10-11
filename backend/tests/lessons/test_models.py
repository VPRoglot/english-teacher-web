from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.families.models import Child
from app.lessons.models import (
    Lesson,
    LessonKind,
    LessonNote,
    LessonSeries,
    LessonStatus,
    TutorSettings,
)
from app.lessons.tutor_settings import get_timezone, get_tutor_settings
from tests.factories import make_child, make_family
from tests.leads.conftest import make_lead
from tests.lessons.conftest import make_lesson, make_series


async def test_settings_row_exists_with_defaults(db_session: AsyncSession) -> None:
    s = await get_tutor_settings(db_session)
    assert (s.id, s.timezone, s.cancel_policy_hours) == (1, "Europe/Moscow", 24)
    assert str(await get_timezone(db_session)) == "Europe/Moscow"


async def test_missing_settings_row_is_an_error(db_session: AsyncSession) -> None:
    await db_session.execute(delete(TutorSettings))
    with pytest.raises(RuntimeError):
        await get_tutor_settings(db_session)


async def test_second_settings_row_is_rejected(db_session: AsyncSession) -> None:
    db_session.add(TutorSettings(id=2))
    with pytest.raises(IntegrityError):
        await db_session.flush()


async def test_settings_hours_are_limited(db_session: AsyncSession) -> None:
    settings = await get_tutor_settings(db_session)
    settings.cancel_policy_hours = 169
    with pytest.raises(IntegrityError):
        await db_session.flush()


@pytest.mark.parametrize(
    ("owners", "overrides"),
    [
        ("", {}),  # нет владельца
        ("cl", {"kind": LessonKind.REGULAR}),  # два владельца
        ("cl", {"kind": LessonKind.TRIAL}),  # два владельца у пробного
        ("l", {"kind": LessonKind.REGULAR}),  # заявка без trial
        ("c", {"kind": LessonKind.TRIAL}),  # trial без заявки
        ("c", {"duration_min": 14}),
        ("c", {"duration_min": 241}),
    ],
)
async def test_lesson_checks_reject_invalid_rows(
    db_session: AsyncSession, owners: str, overrides: dict[str, Any]
) -> None:
    family = await make_family(db_session)
    child = await make_child(db_session, family)
    lead = await make_lead(db_session)
    with pytest.raises(IntegrityError):
        await make_lesson(
            db_session,
            child=child if "c" in owners else None,
            lead=lead if "l" in owners else None,
            **overrides,
        )


async def test_series_lesson_requires_a_child(db_session: AsyncSession) -> None:
    family = await make_family(db_session)
    child = await make_child(db_session, family)
    lead = await make_lead(db_session)
    series = await make_series(db_session, child)
    with pytest.raises(IntegrityError):
        await make_lesson(db_session, lead=lead, series=series)


async def test_valid_lessons_and_defaults(db_session: AsyncSession) -> None:
    family = await make_family(db_session)
    child = await make_child(db_session, family)
    lead = await make_lead(db_session)
    regular = await make_lesson(db_session, child=child)
    trial = await make_lesson(db_session, lead=lead)
    await db_session.refresh(regular)
    assert (regular.kind, regular.status, regular.is_detached) == (
        LessonKind.REGULAR,
        LessonStatus.SCHEDULED,
        False,
    )
    assert regular.meeting_url is None
    assert (trial.kind, trial.child_id, trial.lead_id) == (LessonKind.TRIAL, None, lead.id)


def test_enum_values_are_lowercase() -> None:
    assert [s.value for s in LessonStatus] == [
        "scheduled",
        "completed",
        "cancelled",
        "cancelled_late",
        "no_show",
    ]
    assert [k.value for k in LessonKind] == ["regular", "trial"]


@pytest.mark.parametrize(
    "overrides",
    [{"duration_min": 14}, {"duration_min": 241}, {"ends_on": date(2026, 10, 11)}],
)
async def test_series_checks_reject_invalid_rows(
    db_session: AsyncSession, overrides: dict[str, Any]
) -> None:
    family = await make_family(db_session)
    child = await make_child(db_session, family)
    with pytest.raises(IntegrityError):
        await make_series(db_session, child, **overrides)


async def test_series_defaults_and_boundaries(db_session: AsyncSession) -> None:
    family = await make_family(db_session)
    child = await make_child(db_session, family)
    series = await make_series(db_session, child, ends_on=date(2026, 10, 12), duration_min=15)
    assert series.generated_through is None
    assert series.archived_at is None
    assert series.meeting_url is None


async def test_series_slot_is_unique(db_session: AsyncSession) -> None:
    family = await make_family(db_session)
    child = await make_child(db_session, family)
    series = await make_series(db_session, child)
    when = datetime.now(UTC) + timedelta(days=3)
    await make_lesson(db_session, series=series, starts_at=when)
    with pytest.raises(IntegrityError):
        await make_lesson(db_session, series=series, starts_at=when)


async def test_standalone_lessons_may_share_a_time(db_session: AsyncSession) -> None:
    family = await make_family(db_session)
    child = await make_child(db_session, family)
    when = datetime.now(UTC) + timedelta(days=3)
    await make_lesson(db_session, child=child, starts_at=when)
    await make_lesson(db_session, child=child, starts_at=when)  # series_id NULL — не уникально


async def test_note_cascades_with_lesson(db_session: AsyncSession) -> None:
    family = await make_family(db_session)
    child = await make_child(db_session, family)
    lesson = await make_lesson(db_session, child=child)
    db_session.add(LessonNote(lesson_id=lesson.id))
    await db_session.flush()
    note = await db_session.get(LessonNote, lesson.id)
    assert note is not None
    await db_session.refresh(note)
    assert (note.shared_text, note.private_text) == ("", "")
    await db_session.execute(delete(Lesson).where(Lesson.id == lesson.id))
    assert await db_session.scalar(select(func.count()).select_from(LessonNote)) == 0


async def test_deleting_child_cascades_to_series_and_lessons(db_session: AsyncSession) -> None:
    family = await make_family(db_session)
    child = await make_child(db_session, family)
    series = await make_series(db_session, child)
    await make_lesson(db_session, series=series)
    await db_session.execute(delete(Child).where(Child.id == child.id))
    assert await db_session.scalar(select(func.count()).select_from(LessonSeries)) == 0
    assert await db_session.scalar(select(func.count()).select_from(Lesson)) == 0
