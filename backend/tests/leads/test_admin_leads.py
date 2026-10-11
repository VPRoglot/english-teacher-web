import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.leads.models import Lead, LeadStatus
from tests.leads.conftest import make_lead

ADMIN_ENDPOINTS = [
    ("GET", "/api/admin/leads"),
    ("GET", "/api/admin/leads/{id}"),
    ("PATCH", "/api/admin/leads/{id}"),
    ("POST", "/api/admin/leads/{id}/convert"),
]


async def test_list_filters_by_status_and_searches(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    now = datetime.now(UTC)
    old = await make_lead(
        db_session, parent_name="Ольга", child_name="Петя", created_at=now - timedelta(hours=2)
    )
    rejected = await make_lead(
        db_session,
        status="rejected",
        parent_name="Иван",
        child_name="Саша",
        created_at=now - timedelta(hours=1),
    )
    phoned = await make_lead(
        db_session,
        parent_name="Анна",
        child_name="Маша",
        phone="+79990001122",
        messenger_handle="masha_tg",
        created_at=now,
    )

    everything = (await tutor_client.get("/api/admin/leads")).json()
    assert everything["total"] == 3
    assert [i["id"] for i in everything["items"]] == [
        str(phoned.id),
        str(rejected.id),
        str(old.id),
    ]
    assert set(everything["items"][0]) == {
        "id",
        "created_at",
        "parent_name",
        "child_name",
        "child_age",
        "phone",
        "contact_method",
        "messenger_handle",
        "status",
    }

    by_status = (await tutor_client.get("/api/admin/leads", params={"status": "rejected"})).json()
    assert by_status["total"] == 1
    assert by_status["items"][0]["id"] == str(rejected.id)

    by_child = (await tutor_client.get("/api/admin/leads", params={"q": "маш"})).json()
    assert [i["id"] for i in by_child["items"]] == [str(phoned.id)]

    by_parent = (await tutor_client.get("/api/admin/leads", params={"q": "ОЛЬГ"})).json()
    assert [i["id"] for i in by_parent["items"]] == [str(old.id)]

    by_handle = (await tutor_client.get("/api/admin/leads", params={"q": "masha_tg"})).json()
    assert [i["id"] for i in by_handle["items"]] == [str(phoned.id)]

    by_at_handle = (await tutor_client.get("/api/admin/leads", params={"q": "@masha_tg"})).json()
    assert [i["id"] for i in by_at_handle["items"]] == [str(phoned.id)]

    by_phone = (await tutor_client.get("/api/admin/leads", params={"q": "0001122"})).json()
    assert [i["id"] for i in by_phone["items"]] == [str(phoned.id)]
    assert by_phone["total"] == 1


@pytest.mark.parametrize("q", ["8 999 123", "+7 999 123", "999123"])
async def test_phone_search_matches_with_leading_eight(
    tutor_client: AsyncClient, db_session: AsyncSession, q: str
) -> None:
    lead = await make_lead(db_session, phone="+79991234567")
    await make_lead(db_session, parent_name="Другая", phone="+78005553535")

    body = (await tutor_client.get("/api/admin/leads", params={"q": q})).json()

    assert [i["id"] for i in body["items"]] == [str(lead.id)]


async def test_search_ignores_wildcards_and_short_digit_strings(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    await make_lead(db_session, parent_name="Анна", phone="+79990001122")

    # «%» и «_» — обычные символы, а не шаблон; две цифры не ищут по телефону.
    for q in ["%", "_", "99"]:
        body = (await tutor_client.get("/api/admin/leads", params={"q": q})).json()
        assert body == {"items": [], "total": 0}, q


async def test_list_hides_anonymized_leads(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    await make_lead(db_session, anonymized_at=datetime.now(UTC))
    visible = await make_lead(db_session)

    body = (await tutor_client.get("/api/admin/leads")).json()

    assert body["total"] == 1
    assert body["items"][0]["id"] == str(visible.id)


async def test_list_paginates(tutor_client: AsyncClient, db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    ids = [
        str((await make_lead(db_session, created_at=now - timedelta(minutes=i))).id)
        for i in range(5)
    ]  # от новой к старой

    page = (await tutor_client.get("/api/admin/leads", params={"limit": 2, "offset": 2})).json()

    assert page["total"] == 5
    assert [i["id"] for i in page["items"]] == ids[2:4]


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"offset": -1}, {"q": "x" * 201}])
async def test_list_rejects_bad_params(
    tutor_client: AsyncClient, params: dict[str, str | int]
) -> None:
    assert (await tutor_client.get("/api/admin/leads", params=params)).status_code == 422


async def test_detail_includes_history(tutor_client: AsyncClient, db_session: AsyncSession) -> None:
    lead = await make_lead(db_session, goal="Для школы", utm_source="ads")

    r = await tutor_client.get(f"/api/admin/leads/{lead.id}")

    assert r.status_code == 200
    body = r.json()
    assert body["id"] == str(lead.id)
    assert body["goal"] == "Для школы"
    assert body["utm_source"] == "ads"
    assert body["family_id"] is None
    assert "anonymized_at" not in body
    assert [h["to_status"] for h in body["history"]] == ["new"]
    assert body["history"][0]["from_status"] is None


async def test_unknown_or_anonymized_lead_is_404(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    anonymized = await make_lead(db_session, anonymized_at=datetime.now(UTC))

    for lead_id in [uuid.uuid4(), anonymized.id]:
        r = await tutor_client.get(f"/api/admin/leads/{lead_id}")
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "lead_not_found"
        assert r.json()["error"]["message"] == "Заявка не найдена"


async def test_patch_contacted_writes_history(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    lead = await make_lead(db_session)

    r = await tutor_client.patch(
        f"/api/admin/leads/{lead.id}", json={"status": "contacted", "comment": "Позвонила"}
    )

    assert r.status_code == 200
    assert r.json()["status"] == "contacted"
    assert r.json()["history"][-1] | {"changed_at": None} == {
        "from_status": "new",
        "to_status": "contacted",
        "comment": "Позвонила",
        "changed_at": None,
    }
    assert len(r.json()["history"]) == 2


@pytest.mark.parametrize(
    ("current", "target"),
    [("converted", "contacted"), ("rejected", "rejected"), ("contacted", "contacted")],
)
async def test_forbidden_patch_is_409_and_changes_nothing(
    tutor_client: AsyncClient, db_session: AsyncSession, current: str, target: str
) -> None:
    lead = await make_lead(db_session, status=current)
    body = {"status": target, "comment": "x", "tutor_comment": "новая заметка"}
    if target == "rejected":
        body["reject_reason"] = "причина"

    r = await tutor_client.patch(f"/api/admin/leads/{lead.id}", json=body)

    assert r.status_code == 409
    assert r.json()["error"]["code"] == "invalid_status_transition"
    assert r.json()["error"]["message"] == "Так сменить статус нельзя"
    detail = (await tutor_client.get(f"/api/admin/leads/{lead.id}")).json()
    assert detail["status"] == current
    assert len(detail["history"]) == 1
    assert detail["tutor_comment"] is None


@pytest.mark.parametrize("status", ["trial_scheduled", "converted", "new", "bogus"])
async def test_manual_other_statuses_are_rejected_by_schema(
    tutor_client: AsyncClient, db_session: AsyncSession, status: str
) -> None:
    lead = await make_lead(db_session)

    r = await tutor_client.patch(f"/api/admin/leads/{lead.id}", json={"status": status})

    assert r.status_code == 422


async def test_reject_requires_reason_and_leaving_rejected_clears_it(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    lead = await make_lead(db_session)
    url = f"/api/admin/leads/{lead.id}"

    missing = await tutor_client.patch(url, json={"status": "rejected"})
    assert missing.status_code == 422
    error = missing.json()["error"]["details"]["fields"][0]
    assert error["loc"] == ["body", "reject_reason"]
    assert error["message"] == "Укажите причину отказа"

    stray = await tutor_client.patch(url, json={"status": "contacted", "reject_reason": "x"})
    assert stray.status_code == 422
    assert stray.json()["error"]["details"]["fields"][0]["loc"] == ["body", "reject_reason"]

    rejected = await tutor_client.patch(
        url, json={"status": "rejected", "reject_reason": "Дорого", "comment": "Отказ"}
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["reject_reason"] == "Дорого"

    back = await tutor_client.patch(url, json={"status": "contacted"})
    assert back.status_code == 200
    assert back.json()["status"] == "contacted"
    assert back.json()["reject_reason"] is None
    await db_session.refresh(lead)
    assert lead.reject_reason is None


async def test_tutor_comment_can_be_set_and_cleared(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    lead = await make_lead(db_session)
    url = f"/api/admin/leads/{lead.id}"

    set_ = await tutor_client.patch(url, json={"tutor_comment": "Перезвонить в пятницу"})
    assert set_.status_code == 200
    assert set_.json()["tutor_comment"] == "Перезвонить в пятницу"
    assert set_.json()["status"] == "new"
    assert len(set_.json()["history"]) == 1  # без смены статуса история не растёт

    untouched = await tutor_client.patch(url, json={"status": "contacted"})
    assert untouched.json()["tutor_comment"] == "Перезвонить в пятницу"

    cleared = await tutor_client.patch(url, json={"tutor_comment": None})
    assert cleared.status_code == 200
    assert cleared.json()["tutor_comment"] is None

    too_long = await tutor_client.patch(url, json={"tutor_comment": "x" * 2001})
    assert too_long.status_code == 422


async def test_comment_without_status_is_422(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    lead = await make_lead(db_session)

    r = await tutor_client.patch(f"/api/admin/leads/{lead.id}", json={"comment": "Позвонила"})

    assert r.status_code == 422
    (field,) = r.json()["error"]["details"]["fields"]
    assert field["loc"] == ["body", "comment"]
    assert field["message"] == "Комментарий сохраняется только вместе со сменой статуса"


async def test_patch_unknown_lead_is_404(tutor_client: AsyncClient) -> None:
    r = await tutor_client.patch(f"/api/admin/leads/{uuid.uuid4()}", json={"status": "contacted"})

    assert r.status_code == 404
    assert r.json()["error"]["code"] == "lead_not_found"


def _path(template: str, lead: Lead) -> str:
    return template.replace("{id}", str(lead.id))


@pytest.mark.parametrize(("method", "path"), ADMIN_ENDPOINTS)
async def test_leads_admin_requires_login(
    client: AsyncClient, db_session: AsyncSession, method: str, path: str
) -> None:
    lead = await make_lead(db_session)

    r = await client.request(method, _path(path, lead), json={})

    assert r.status_code == 401


@pytest.mark.parametrize(("method", "path"), ADMIN_ENDPOINTS)
async def test_leads_admin_is_hidden_from_parents(
    parent_client: AsyncClient, db_session: AsyncSession, method: str, path: str
) -> None:
    lead = await make_lead(db_session)

    r = await parent_client.request(method, _path(path, lead), json={})

    assert r.status_code == 404
    assert LeadStatus(lead.status) is LeadStatus.NEW
