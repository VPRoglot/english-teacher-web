from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import open_client
from tests.factories import TEST_PASSWORD, login, make_child, make_family, make_parent

MISSING_ID = "019a0000-0000-7000-8000-000000000000"


async def test_reset_link_for_parent(
    app: FastAPI, tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    fam = await make_family(db_session)
    parent = await make_parent(db_session, fam)

    r = await tutor_client.post(f"/api/admin/users/{parent.id}/reset-link")

    assert r.status_code == 201
    assert r.json()["url"].startswith("http://localhost:3000/reset/")
    token = r.json()["url"].rsplit("/", 1)[1]
    info = await tutor_client.get(f"/api/auth/password-resets/{token}")
    assert info.status_code == 200
    assert info.json()["login"] == "parent@example.com"
    done = await tutor_client.post(
        f"/api/auth/password-resets/{token}", json={"password": "Brand-New-Pass-1"}
    )
    assert done.status_code == 204
    async with open_client(app) as c:
        await login(c, "parent@example.com", "Brand-New-Pass-1")


async def test_reset_link_for_child(tutor_client: AsyncClient, db_session: AsyncSession) -> None:
    fam = await make_family(db_session)
    child = await make_child(db_session, fam, username="masha")
    assert child.user_id is not None

    r = await tutor_client.post(f"/api/admin/users/{child.user_id}/reset-link")

    assert r.status_code == 201
    token = r.json()["url"].rsplit("/", 1)[1]
    info = await tutor_client.get(f"/api/auth/password-resets/{token}")
    assert info.json()["login"] == "masha"


async def test_reset_link_for_tutor_is_404(tutor_client: AsyncClient) -> None:
    me = await tutor_client.get("/api/auth/me")

    tutor_id = me.json()["id"]

    r = await tutor_client.post(f"/api/admin/users/{tutor_id}/reset-link")
    patch = await tutor_client.patch(f"/api/admin/users/{tutor_id}", json={"is_active": False})

    assert r.status_code == 404
    assert patch.status_code == 404
    assert (await tutor_client.get("/api/auth/me")).status_code == 200


async def test_unknown_user_is_404(tutor_client: AsyncClient) -> None:
    reset = await tutor_client.post(f"/api/admin/users/{MISSING_ID}/reset-link")
    patch = await tutor_client.patch(f"/api/admin/users/{MISSING_ID}", json={"is_active": False})

    assert reset.status_code == 404
    assert patch.status_code == 404


async def test_user_endpoints_are_tutor_only(client: AsyncClient, db_session: AsyncSession) -> None:
    fam = await make_family(db_session)
    parent = await make_parent(db_session, fam)
    other = await make_parent(db_session, fam, email="other@example.com")

    anonymous = await client.post(f"/api/admin/users/{other.id}/reset-link")
    await login(client, "parent@example.com")
    forbidden_reset = await client.post(f"/api/admin/users/{other.id}/reset-link")
    forbidden_patch = await client.patch(f"/api/admin/users/{parent.id}", json={"is_active": False})

    assert anonymous.status_code == 401
    assert forbidden_reset.status_code == 404
    assert forbidden_patch.status_code == 404


async def test_deactivate_user_kills_sessions(
    app: FastAPI, tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    fam = await make_family(db_session)
    parent = await make_parent(db_session, fam)
    async with open_client(app) as parent_client:
        await login(parent_client, "parent@example.com")

        r = await tutor_client.patch(f"/api/admin/users/{parent.id}", json={"is_active": False})

        assert r.status_code == 204
        assert (await parent_client.get("/api/auth/me")).status_code == 401
        relogin = await parent_client.post(
            "/api/auth/login", json={"login": "parent@example.com", "password": "Correct-Horse-7"}
        )
        assert relogin.status_code == 401

        r = await tutor_client.patch(f"/api/admin/users/{parent.id}", json={"is_active": True})

        assert r.status_code == 204
        await login(parent_client, "parent@example.com")


async def test_unblocking_archived_member_does_not_restore_access(
    app: FastAPI, tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    # is_active — только ручная блокировка; доступ участникам архива закрыт самим архивом.
    archived_fam = await make_family(db_session, name="Старые", archived=True)
    parent = await make_parent(db_session, archived_fam, is_active=False)
    fam = await make_family(db_session)
    child = await make_child(db_session, fam, username="masha", archived=True, is_active=False)
    assert child.user_id is not None

    r1 = await tutor_client.patch(f"/api/admin/users/{parent.id}", json={"is_active": True})
    r2 = await tutor_client.patch(f"/api/admin/users/{child.user_id}", json={"is_active": True})

    assert r1.status_code == r2.status_code == 204
    await db_session.refresh(parent)
    assert parent.is_active is True
    async with open_client(app) as c:
        for login_ in ("parent@example.com", "masha"):
            r = await c.post("/api/auth/login", json={"login": login_, "password": TEST_PASSWORD})
            assert r.status_code == 401, login_


async def test_status_update_requires_boolean(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    fam = await make_family(db_session)
    parent = await make_parent(db_session, fam)

    r = await tutor_client.patch(f"/api/admin/users/{parent.id}", json={})

    assert r.status_code == 422
