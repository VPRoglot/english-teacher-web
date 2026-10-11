from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.leads.models import ContactMethod, Lead, LeadStatus, LeadStatusHistory
from tests.factories import make_family


def _lead(**overrides: object) -> Lead:
    fields: dict[str, object] = {
        "parent_name": "Анна",
        "child_name": "Маша",
        "child_age": 9,
        "phone": "+79991234567",
        "contact_method": ContactMethod.TELEGRAM,
        "consent_at": datetime.now(UTC),
    }
    return Lead(**{**fields, **overrides})


async def test_lead_defaults(db_session: AsyncSession) -> None:
    lead = _lead()
    db_session.add(lead)
    await db_session.flush()
    await db_session.refresh(lead)
    assert lead.status is LeadStatus.NEW
    assert lead.family_id is None
    assert lead.notified_at is None
    assert lead.anonymized_at is None
    assert lead.created_at is not None


async def test_history_is_ordered_and_cascades(db_session: AsyncSession) -> None:
    lead = _lead()
    db_session.add(lead)
    await db_session.flush()
    now = datetime.now(UTC)
    # Вставляем в обратном порядке: порядок должен определяться changed_at, а не вставкой.
    db_session.add_all(
        [
            LeadStatusHistory(
                lead_id=lead.id,
                from_status=LeadStatus.NEW,
                to_status=LeadStatus.CONTACTED,
                changed_at=now,
            ),
            LeadStatusHistory(
                lead_id=lead.id,
                from_status=None,
                to_status=LeadStatus.NEW,
                changed_at=now - timedelta(minutes=5),
            ),
        ]
    )
    await db_session.flush()
    await db_session.refresh(lead, attribute_names=["history"])
    assert [h.to_status for h in lead.history] == [LeadStatus.NEW, LeadStatus.CONTACTED]
    assert lead.history[0].from_status is None

    await db_session.delete(lead)
    await db_session.flush()
    count = await db_session.scalar(select(func.count()).select_from(LeadStatusHistory))
    assert count == 0


async def test_history_changed_at_defaults_to_now(db_session: AsyncSession) -> None:
    lead = _lead()
    db_session.add(lead)
    await db_session.flush()
    entry = LeadStatusHistory(lead_id=lead.id, to_status=LeadStatus.NEW)
    db_session.add(entry)
    await db_session.flush()
    await db_session.refresh(entry)
    assert entry.changed_at is not None


async def test_family_delete_sets_lead_family_null(db_session: AsyncSession) -> None:
    family = await make_family(db_session)
    lead = _lead(family_id=family.id)
    db_session.add(lead)
    await db_session.flush()
    await db_session.delete(family)
    await db_session.flush()
    await db_session.refresh(lead)
    assert lead.family_id is None
