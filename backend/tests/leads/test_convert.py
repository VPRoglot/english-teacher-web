from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Invitation
from app.families.models import Child, Family
from app.leads.models import LeadStatus, LeadStatusHistory
from tests.leads.conftest import make_lead

CONVERT_BODY = {
    "family_name": "Семья Маши",
    "child": {"full_name": "Маша"},
    "parent": {"full_name": "Анна Смирнова", "phone": "8 999 123 45 67"},
}


async def _count(session: AsyncSession, model: type) -> int:
    return await session.scalar(select(func.count()).select_from(model)) or 0


async def test_convert_creates_family_child_invitation_in_one_go(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    lead = await make_lead(db_session, status="trial_scheduled", child_name="Маша", child_age=9)

    r = await tutor_client.post(f"/api/admin/leads/{lead.id}/convert", json=CONVERT_BODY)

    assert r.status_code == 201
    body = r.json()
    assert "/invite/" in body["invitation"]["url"]
    assert body["invitation"]["expires_at"]

    family = await db_session.get(Family, body["family_id"])
    assert family is not None
    assert family.name == "Семья Маши"
    children = list(await db_session.scalars(select(Child).where(Child.family_id == family.id)))
    assert [c.full_name for c in children] == ["Маша"]
    invitation = await db_session.scalar(
        select(Invitation).where(Invitation.family_id == family.id)
    )
    assert invitation is not None
    assert invitation.prefill_full_name == "Анна Смирнова"
    assert invitation.prefill_phone == "+79991234567"

    await db_session.refresh(lead)
    assert lead.status is LeadStatus.CONVERTED
    assert str(lead.family_id) == body["family_id"]
    history = list(
        await db_session.scalars(
            select(LeadStatusHistory)
            .where(LeadStatusHistory.lead_id == lead.id)
            .order_by(LeadStatusHistory.changed_at)
        )
    )
    assert history[-1].from_status is LeadStatus.TRIAL_SCHEDULED
    assert history[-1].to_status is LeadStatus.CONVERTED
    assert history[-1].comment == "Создана семья Семья Маши"

    detail = (await tutor_client.get(f"/api/admin/leads/{lead.id}")).json()
    assert detail["status"] == "converted"
    assert detail["family_id"] == body["family_id"]
    assert detail["history"][-1]["comment"] == "Создана семья Семья Маши"


async def test_convert_requires_trial_scheduled(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    lead = await make_lead(db_session, status="new")
    families_before = await _count(db_session, Family)

    r = await tutor_client.post(f"/api/admin/leads/{lead.id}/convert", json=CONVERT_BODY)

    assert r.status_code == 409
    assert r.json()["error"]["code"] == "lead_not_convertible"
    assert r.json()["error"]["message"] == "Конвертировать можно после назначения пробного занятия"
    assert await _count(db_session, Family) == families_before
    await db_session.refresh(lead)
    assert lead.status is LeadStatus.NEW
    assert lead.family_id is None


async def test_second_convert_is_409_and_one_family_exists(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    lead = await make_lead(db_session, status="trial_scheduled")
    families_before = await _count(db_session, Family)
    url = f"/api/admin/leads/{lead.id}/convert"

    first = await tutor_client.post(url, json=CONVERT_BODY)
    second = await tutor_client.post(url, json=CONVERT_BODY)

    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "lead_not_convertible"
    assert await _count(db_session, Family) == families_before + 1


async def test_convert_validates_body(tutor_client: AsyncClient, db_session: AsyncSession) -> None:
    lead = await make_lead(db_session, status="trial_scheduled")
    url = f"/api/admin/leads/{lead.id}/convert"

    bad_phone = await tutor_client.post(
        url, json={**CONVERT_BODY, "parent": {"full_name": "Анна", "phone": "123"}}
    )
    assert bad_phone.status_code == 422
    assert bad_phone.json()["error"]["details"]["fields"][0]["loc"] == [
        "body",
        "parent",
        "phone",
    ]
    assert bad_phone.json()["error"]["details"]["fields"][0]["message"] == (
        "Укажите телефон в формате +7 999 123-45-67"
    )

    no_family = await tutor_client.post(url, json={**CONVERT_BODY, "family_name": " "})
    assert no_family.status_code == 422
    await db_session.refresh(lead)
    assert lead.status is LeadStatus.TRIAL_SCHEDULED
