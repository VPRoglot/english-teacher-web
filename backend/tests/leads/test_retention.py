from datetime import UTC, datetime
from typing import Any

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.leads.models import Lead, LeadStatus, LeadStatusHistory
from app.leads.retention import ANONYMIZED_NAME, anonymize_stale_leads
from app.lessons.models import Lesson
from tests.leads.conftest import make_lead
from tests.lessons.conftest import make_lesson

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
LONG_AGO = datetime(2023, 1, 1, tzinfo=UTC)


async def _lead_with_status_at(
    session: AsyncSession, status: str, changed_at: datetime, **overrides: Any
) -> Lead:
    """Заявка, созданная давно, с последним переходом в `status` в момент `changed_at`."""
    values: dict[str, Any] = {
        "created_at": LONG_AGO,
        "messenger_handle": "masha_tg",
        "goal": "Разговорный английский",
        "preferred_time": "вечером",
        "tutor_comment": "Перезвонить",
        "reject_reason": "Дорого" if status == "rejected" else None,
        "utm_source": "yandex",
        "utm_medium": "cpc",
        "utm_campaign": "spring",
    }
    values.update(overrides)
    lead = await make_lead(session, status=status, **values)
    session.add(
        LeadStatusHistory(
            lead_id=lead.id,
            from_status=LeadStatus.NEW,
            to_status=LeadStatus(status),
            comment="Личный комментарий",
            changed_at=changed_at,
        )
    )
    await session.flush()
    return lead


async def test_rejected_older_than_12_months_anonymized(db_session: AsyncSession) -> None:
    lead = await _lead_with_status_at(
        db_session, "rejected", datetime(2025, 10, 13, 11, 59, tzinfo=UTC)
    )
    keep = {
        "child_age": lead.child_age,
        "contact_method": lead.contact_method,
        "status": lead.status,
        "utm_source": "yandex",
        "utm_medium": "cpc",
        "utm_campaign": "spring",
        "consent_at": lead.consent_at,
        "created_at": lead.created_at,
    }

    assert await anonymize_stale_leads(db_session, now=NOW) == 1

    await db_session.refresh(lead)
    assert lead.parent_name == ANONYMIZED_NAME == "Обезличено"
    assert lead.child_name == ANONYMIZED_NAME
    assert lead.phone == ""
    assert lead.messenger_handle is None
    assert lead.goal is None
    assert lead.preferred_time is None
    assert lead.tutor_comment is None
    assert lead.reject_reason is None
    assert lead.anonymized_at == NOW
    for field, value in keep.items():
        assert getattr(lead, field) == value
    comments = (
        await db_session.scalars(
            select(LeadStatusHistory.comment).where(LeadStatusHistory.lead_id == lead.id)
        )
    ).all()
    assert len(comments) == 2
    assert all(c is None for c in comments)


async def test_exact_boundary(db_session: AsyncSession) -> None:
    on_boundary = await _lead_with_status_at(
        db_session, "rejected", datetime(2025, 10, 13, 12, 0, tzinfo=UTC)
    )
    just_after = await _lead_with_status_at(
        db_session, "rejected", datetime(2025, 10, 13, 12, 1, tzinfo=UTC)
    )

    assert await anonymize_stale_leads(db_session, now=NOW) == 1

    await db_session.refresh(on_boundary)
    await db_session.refresh(just_after)
    assert on_boundary.anonymized_at == NOW
    assert just_after.anonymized_at is None
    assert just_after.parent_name == "Анна"


async def test_recent_status_change_keeps_lead(db_session: AsyncSession) -> None:
    lead = await _lead_with_status_at(
        db_session, "contacted", datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
    )

    assert await anonymize_stale_leads(db_session, now=NOW) == 0

    await db_session.refresh(lead)
    assert lead.anonymized_at is None
    assert lead.phone == "+79991234567"


async def test_stale_new_lead_anonymized(db_session: AsyncSession) -> None:
    lead = await make_lead(
        db_session, status="new", created_at=datetime(2025, 9, 1, tzinfo=UTC), goal="Цель"
    )

    assert await anonymize_stale_leads(db_session, now=NOW) == 1

    await db_session.refresh(lead)
    assert lead.anonymized_at == NOW
    assert lead.status == LeadStatus.NEW
    assert lead.goal is None


async def test_converted_never_anonymized(db_session: AsyncSession) -> None:
    lead = await _lead_with_status_at(
        db_session, "converted", datetime(2023, 10, 13, 12, 0, tzinfo=UTC)
    )

    assert await anonymize_stale_leads(db_session, now=NOW) == 0

    await db_session.refresh(lead)
    assert lead.anonymized_at is None
    assert lead.parent_name == "Анна"


async def test_already_anonymized_skipped_and_idempotent(db_session: AsyncSession) -> None:
    lead = await _lead_with_status_at(db_session, "rejected", datetime(2025, 1, 1, tzinfo=UTC))

    assert await anonymize_stale_leads(db_session, now=NOW) == 1
    later = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)
    assert await anonymize_stale_leads(db_session, now=later) == 0

    await db_session.refresh(lead)
    assert lead.anonymized_at == NOW


async def test_lead_without_history_uses_created_at(db_session: AsyncSession) -> None:
    old = await make_lead(db_session, created_at=datetime(2025, 10, 13, 12, 0, tzinfo=UTC))
    fresh = await make_lead(db_session, created_at=datetime(2025, 10, 13, 12, 1, tzinfo=UTC))
    for lead in (old, fresh):
        for row in (
            await db_session.scalars(
                select(LeadStatusHistory).where(LeadStatusHistory.lead_id == lead.id)
            )
        ).all():
            await db_session.delete(row)
    await db_session.flush()

    assert await anonymize_stale_leads(db_session, now=NOW) == 1

    await db_session.refresh(old)
    await db_session.refresh(fresh)
    assert old.anonymized_at == NOW
    assert fresh.anonymized_at is None


async def test_anonymized_lead_hidden_from_admin(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    lead = await make_lead(db_session, created_at=datetime(2025, 1, 1, tzinfo=UTC))
    visible = await make_lead(db_session, created_at=datetime.now(UTC))
    assert (await tutor_client.get(f"/api/admin/leads/{lead.id}")).status_code == 200
    assert (await tutor_client.get("/api/admin/dashboard")).json()["new_leads"]["total"] == 2

    assert await anonymize_stale_leads(db_session, now=NOW) == 1

    assert (await tutor_client.get(f"/api/admin/leads/{lead.id}")).status_code == 404
    listing = (await tutor_client.get("/api/admin/leads")).json()
    assert [i["id"] for i in listing["items"]] == [str(visible.id)]
    dashboard = (await tutor_client.get("/api/admin/dashboard")).json()
    assert dashboard["new_leads"]["total"] == 1


async def test_trial_lesson_kept(db_session: AsyncSession) -> None:
    lead = await make_lead(db_session, created_at=datetime(2025, 1, 1, tzinfo=UTC))
    lesson = await make_lesson(db_session, lead=lead)

    assert await anonymize_stale_leads(db_session, now=NOW) == 1

    kept = await db_session.get(Lesson, lesson.id, populate_existing=True)
    assert kept is not None
    assert kept.lead_id == lead.id
