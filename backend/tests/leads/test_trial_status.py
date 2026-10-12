import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.leads import service
from app.leads.models import LeadStatus, LeadStatusHistory
from tests.leads.conftest import make_lead


@pytest.mark.parametrize("status", ["new", "contacted"])
async def test_schedule_trial_status_writes_history(db_session: AsyncSession, status: str) -> None:
    lead = await make_lead(db_session, status=status)

    result = await service.schedule_trial_status(
        db_session, lead.id, comment="Пробное занятие 20.10.2026 18:00"
    )

    assert result.id == lead.id
    assert result.status is LeadStatus.TRIAL_SCHEDULED
    # Строку выбираем по to_status, а не по времени: часы Windows грубые, и строка фабрики
    # и строка сервиса могут получить одинаковый changed_at.
    rows = list(
        await db_session.scalars(
            select(LeadStatusHistory).where(
                LeadStatusHistory.lead_id == lead.id,
                LeadStatusHistory.to_status == LeadStatus.TRIAL_SCHEDULED,
            )
        )
    )
    assert len(rows) == 1
    last = rows[0]
    assert last.from_status is LeadStatus(status)
    assert last.to_status is LeadStatus.TRIAL_SCHEDULED
    assert last.comment == "Пробное занятие 20.10.2026 18:00"


@pytest.mark.parametrize("status", ["trial_scheduled", "converted", "rejected"])
async def test_schedule_trial_status_rejects_wrong_status(
    db_session: AsyncSession, status: str
) -> None:
    lead = await make_lead(db_session, status=status)

    with pytest.raises(service.InvalidStatusTransition):
        await service.schedule_trial_status(db_session, lead.id, comment="x")

    assert lead.status is LeadStatus(status)


async def test_schedule_trial_status_unknown_lead(db_session: AsyncSession) -> None:
    with pytest.raises(service.LeadNotFound):
        await service.schedule_trial_status(db_session, uuid.uuid4(), comment="x")


async def test_ensure_lead_visible_accepts_existing_lead(db_session: AsyncSession) -> None:
    lead = await make_lead(db_session)

    await service.ensure_lead_visible(db_session, lead.id)


async def test_ensure_lead_visible_rejects_unknown_and_anonymized(
    db_session: AsyncSession,
) -> None:
    anonymized = await make_lead(db_session, anonymized_at=datetime.now(UTC))

    for lead_id in (uuid.uuid4(), anonymized.id):
        with pytest.raises(service.LeadNotFound):
            await service.ensure_lead_visible(db_session, lead_id)
