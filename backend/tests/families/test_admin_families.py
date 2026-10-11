from datetime import UTC, datetime, timedelta

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import Invitation
from tests.conftest import open_client
from tests.factories import TEST_PASSWORD, login, make_child, make_family, make_parent

MISSING_ID = "019a0000-0000-7000-8000-000000000000"


async def test_parent_cannot_reach_admin(client: AsyncClient, db_session: AsyncSession) -> None:
    fam = await make_family(db_session)
    await make_parent(db_session, fam)
    await login(client, "parent@example.com")

    for method, url in [
        ("GET", "/api/admin/families"),
        ("POST", "/api/admin/families"),
        ("GET", f"/api/admin/families/{fam.id}"),
        ("PATCH", f"/api/admin/families/{fam.id}"),
        ("POST", f"/api/admin/families/{fam.id}/invitations"),
        ("POST", f"/api/admin/families/{fam.id}/children"),
    ]:
        r = await client.request(method, url, json={"name": "x"})
        assert r.status_code == 404, url


async def test_child_cannot_reach_admin(client: AsyncClient, db_session: AsyncSession) -> None:
    fam = await make_family(db_session)
    await make_child(db_session, fam, username="masha")
    await login(client, "masha")

    assert (await client.get("/api/admin/families")).status_code == 404


async def test_anonymous_admin_is_401(client: AsyncClient, db_session: AsyncSession) -> None:
    fam = await make_family(db_session)

    for method, url in [
        ("GET", "/api/admin/families"),
        ("POST", "/api/admin/families"),
        ("GET", f"/api/admin/families/{fam.id}"),
        ("POST", f"/api/admin/families/{fam.id}/invitations"),
    ]:
        r = await client.request(method, url, json={"name": "x"})
        assert r.status_code == 401, url


async def test_create_and_get_family(tutor_client: AsyncClient) -> None:
    r = await tutor_client.post(
        "/api/admin/families", json={"name": "  Сидоровы ", "tutor_comment": "по вторникам"}
    )

    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Сидоровы"
    assert body["tutor_comment"] == "по вторникам"
    assert body["archived_at"] is None
    assert body["parents"] == []
    assert body["children"] == []
    assert body["pending_invitation"] is None

    got = await tutor_client.get(f"/api/admin/families/{body['id']}")
    assert got.status_code == 200
    assert got.json() == body


async def test_create_family_validation(tutor_client: AsyncClient) -> None:
    for payload in [{"name": ""}, {"name": "   "}, {"name": "x" * 201}, {}]:
        r = await tutor_client.post("/api/admin/families", json=payload)
        assert r.status_code == 422, payload
    r = await tutor_client.post(
        "/api/admin/families", json={"name": "a", "tutor_comment": "x" * 2001}
    )
    assert r.status_code == 422


async def test_unknown_family_is_404(tutor_client: AsyncClient) -> None:
    assert (await tutor_client.get(f"/api/admin/families/{MISSING_ID}")).status_code == 404
    patch = await tutor_client.patch(f"/api/admin/families/{MISSING_ID}", json={"name": "x"})
    assert patch.status_code == 404
    invite = await tutor_client.post(f"/api/admin/families/{MISSING_ID}/invitations")
    assert invite.status_code == 404


async def test_list_families_sorted_with_children_and_parents(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    b = await make_family(db_session, name="Борисовы")
    a = await make_family(db_session, name="Андреевы")
    await make_parent(db_session, a, email="a@example.com", full_name="Анна Андреева")
    await make_child(db_session, a, full_name="Маша")
    await make_child(db_session, a, full_name="Архивный", archived=True)

    r = await tutor_client.get("/api/admin/families")

    assert r.status_code == 200
    items = r.json()
    assert [i["name"] for i in items] == ["Андреевы", "Борисовы"]
    assert items[0]["parent_names"] == ["Анна Андреева"]
    assert [c["full_name"] for c in items[0]["children"]] == ["Маша"]
    assert items[1]["parent_names"] == []
    assert items[1]["children"] == []
    assert items[1]["id"] == str(b.id)


async def test_list_families_archived_filter(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    await make_family(db_session, name="Живые")
    await make_family(db_session, name="Старые", archived=True)

    active = await tutor_client.get("/api/admin/families")
    archived = await tutor_client.get("/api/admin/families", params={"archived": "true"})

    assert [i["name"] for i in active.json()] == ["Живые"]
    assert [i["name"] for i in archived.json()] == ["Старые"]
    assert archived.json()[0]["archived_at"] is not None


async def test_search_by_family_parent_and_child_name(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    fam = await make_family(db_session, name="Ивановы")
    await make_parent(db_session, fam, full_name="Анна Иванова")
    await make_child(db_session, fam, full_name="Маша")
    other = await make_family(db_session, name="Петровы")
    await make_parent(db_session, other, email="p@example.com", full_name="Пётр Петров")

    async def names(q: str) -> list[str]:
        r = await tutor_client.get("/api/admin/families", params={"q": q})
        assert r.status_code == 200
        return [i["name"] for i in r.json()]

    assert await names("анна") == ["Ивановы"]
    assert await names("маш") == ["Ивановы"]
    assert await names("ПЕТРОВЫ") == ["Петровы"]
    assert await names("нет такого") == []


async def test_search_escapes_like_wildcards(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    await make_family(db_session, name="Ивановы")
    await make_family(db_session, name="Скидка 50% и_ещё")
    await make_family(db_session, name="Back\\slash")

    async def names(q: str) -> list[str]:
        r = await tutor_client.get("/api/admin/families", params={"q": q})
        return [i["name"] for i in r.json()]

    assert await names("%") == ["Скидка 50% и_ещё"]
    assert await names("_") == ["Скидка 50% и_ещё"]
    assert await names("\\") == ["Back\\slash"]
    assert await names("0% и_е") == ["Скидка 50% и_ещё"]


async def test_update_family_fields(tutor_client: AsyncClient, db_session: AsyncSession) -> None:
    fam = await make_family(db_session)

    r = await tutor_client.patch(
        f"/api/admin/families/{fam.id}", json={"name": "Новые", "tutor_comment": "заметка"}
    )
    assert r.status_code == 200
    assert r.json()["name"] == "Новые"
    assert r.json()["tutor_comment"] == "заметка"

    r = await tutor_client.patch(f"/api/admin/families/{fam.id}", json={"tutor_comment": None})
    assert r.json()["tutor_comment"] is None
    assert r.json()["name"] == "Новые"

    r = await tutor_client.patch(f"/api/admin/families/{fam.id}", json={"name": None})
    assert r.status_code == 422


async def test_family_detail_lists_parents_and_children(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    fam = await make_family(db_session)
    await make_parent(db_session, fam, full_name="Анна Иванова", phone="+79991112233")
    await make_child(db_session, fam, full_name="Яна", archived=True)
    await make_child(db_session, fam, full_name="Маша", username="masha")
    await make_child(db_session, fam, full_name="Боря")

    r = await tutor_client.get(f"/api/admin/families/{fam.id}")

    body = r.json()
    assert len(body["parents"]) == 1
    parent = body["parents"][0]
    assert parent["full_name"] == "Анна Иванова"
    assert parent["phone"] == "+79991112233"
    assert parent["email"] == "parent@example.com"
    assert parent["is_active"] is True
    assert parent["last_login_at"] is None
    # активные сначала (по имени), архивные — в конце
    assert [c["full_name"] for c in body["children"]] == ["Боря", "Маша", "Яна"]
    assert body["children"][0]["account"] is None
    assert body["children"][1]["account"]["username"] == "masha"
    assert body["children"][1]["account"]["is_active"] is True
    assert body["children"][2]["archived_at"] is not None


async def test_invitation_link(tutor_client: AsyncClient, db_session: AsyncSession) -> None:
    fam = await make_family(db_session)

    r = await tutor_client.post(
        f"/api/admin/families/{fam.id}/invitations", json={"prefill_full_name": "Анна"}
    )

    assert r.status_code == 201
    assert r.json()["url"].startswith("http://localhost:3000/invite/")
    expires_at = datetime.fromisoformat(r.json()["expires_at"])
    assert abs(expires_at - (datetime.now(UTC) + timedelta(days=7))) < timedelta(minutes=1)
    token = r.json()["url"].rsplit("/", 1)[1]
    info = await tutor_client.get(f"/api/auth/invitations/{token}")
    assert info.json()["prefill_full_name"] == "Анна"
    detail = (await tutor_client.get(f"/api/admin/families/{fam.id}")).json()
    assert detail["pending_invitation"] is not None
    assert detail["pending_invitation"]["expires_at"] == r.json()["expires_at"]


async def test_invitation_without_body_and_new_one_revokes_old(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    fam = await make_family(db_session)

    first = await tutor_client.post(f"/api/admin/families/{fam.id}/invitations")
    second = await tutor_client.post(f"/api/admin/families/{fam.id}/invitations", json={})

    assert first.status_code == 201
    assert second.status_code == 201
    first_token = first.json()["url"].rsplit("/", 1)[1]
    assert (await tutor_client.get(f"/api/auth/invitations/{first_token}")).status_code == 404
    second_token = second.json()["url"].rsplit("/", 1)[1]
    assert (await tutor_client.get(f"/api/auth/invitations/{second_token}")).status_code == 200


async def test_pending_invitation_ignores_used_and_expired(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    fam = await make_family(db_session)
    r = await tutor_client.post(f"/api/admin/families/{fam.id}/invitations")
    assert r.status_code == 201
    invitation = await db_session.scalar(select(Invitation).where(Invitation.family_id == fam.id))
    assert invitation is not None

    invitation.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    await db_session.flush()
    detail = (await tutor_client.get(f"/api/admin/families/{fam.id}")).json()
    assert detail["pending_invitation"] is None

    invitation.expires_at = datetime.now(UTC) + timedelta(days=1)
    invitation.used_at = datetime.now(UTC)
    await db_session.flush()
    detail = (await tutor_client.get(f"/api/admin/families/{fam.id}")).json()
    assert detail["pending_invitation"] is None


async def test_invitation_validation_and_archived_family(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    fam = await make_family(db_session)
    archived = await make_family(db_session, name="Старые", archived=True)

    too_long = await tutor_client.post(
        f"/api/admin/families/{fam.id}/invitations", json={"prefill_phone": "1" * 33}
    )
    in_archive = await tutor_client.post(f"/api/admin/families/{archived.id}/invitations")

    assert too_long.status_code == 422
    assert in_archive.status_code == 409
    assert in_archive.json()["error"]["code"] == "family_archived"


async def test_archive_family_logs_out_members(
    app: FastAPI, tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    fam = await make_family(db_session)
    await make_parent(db_session, fam)
    await make_child(db_session, fam, full_name="Маша", username="masha")
    async with open_client(app) as parent_client, open_client(app) as kid:
        await login(parent_client, "parent@example.com")
        await login(kid, "masha")

        r = await tutor_client.patch(f"/api/admin/families/{fam.id}", json={"archived": True})

        assert r.status_code == 200
        assert r.json()["archived_at"] is not None
        # Архив не трогает ручную блокировку: is_active — только решение репетитора.
        assert all(p["is_active"] is True for p in r.json()["parents"])
        assert all(c["account"]["is_active"] is True for c in r.json()["children"])
        assert (await parent_client.get("/api/auth/me")).status_code == 401
        assert (await kid.get("/api/auth/me")).status_code == 401
        for login_ in ("parent@example.com", "masha"):
            relogin = await parent_client.post(
                "/api/auth/login", json={"login": login_, "password": "Correct-Horse-7"}
            )
            assert relogin.status_code == 401, login_
            assert relogin.json()["error"]["code"] == "invalid_credentials"

        r = await tutor_client.patch(f"/api/admin/families/{fam.id}", json={"archived": False})

        assert r.json()["archived_at"] is None
        await login(parent_client, "parent@example.com")
        await login(kid, "masha")


async def _login_status(app: FastAPI, login_: str) -> int:
    async with open_client(app) as c:
        r = await c.post("/api/auth/login", json={"login": login_, "password": TEST_PASSWORD})
        return r.status_code


async def test_unarchive_family_keeps_archived_child_locked_out(
    app: FastAPI, tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    fam = await make_family(db_session)
    await make_child(db_session, fam, full_name="Маша", username="masha")
    await make_child(db_session, fam, full_name="Яна", username="yana", archived=True)

    await tutor_client.patch(f"/api/admin/families/{fam.id}", json={"archived": True})
    await tutor_client.patch(f"/api/admin/families/{fam.id}", json={"archived": False})

    assert await _login_status(app, "masha") == 200
    assert await _login_status(app, "yana") == 401


async def test_unarchive_family_keeps_manually_blocked_parent_blocked(
    app: FastAPI, tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    fam = await make_family(db_session)
    parent = await make_parent(db_session, fam)
    blocked = await tutor_client.patch(f"/api/admin/users/{parent.id}", json={"is_active": False})
    assert blocked.status_code == 204

    await tutor_client.patch(f"/api/admin/families/{fam.id}", json={"archived": True})
    r = await tutor_client.patch(f"/api/admin/families/{fam.id}", json={"archived": False})

    assert r.json()["parents"][0]["is_active"] is False
    await db_session.refresh(parent)
    assert parent.is_active is False
    assert await _login_status(app, "parent@example.com") == 401


async def test_unarchive_of_active_family_does_not_touch_users(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    fam = await make_family(db_session)
    parent = await make_parent(db_session, fam)
    parent.is_active = False
    await db_session.flush()

    r = await tutor_client.patch(f"/api/admin/families/{fam.id}", json={"archived": False})

    assert r.status_code == 200
    assert r.json()["parents"][0]["is_active"] is False


async def test_add_child_to_archived_family_conflict(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    fam = await make_family(db_session, archived=True)

    r = await tutor_client.post(
        f"/api/admin/families/{fam.id}/children", json={"full_name": "Маша"}
    )

    assert r.status_code == 409
    assert r.json()["error"]["code"] == "family_archived"
