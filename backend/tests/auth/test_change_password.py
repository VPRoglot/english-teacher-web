from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.passwords import verify_password
from tests.conftest import open_client
from tests.factories import TEST_PASSWORD, login, make_family, make_parent

NEW_PASSWORD = "New-Strong-9"


async def test_change_password_keeps_current_device_and_logs_out_others(
    client: AsyncClient, db_session: AsyncSession, app: FastAPI
) -> None:
    fam = await make_family(db_session)
    parent = await make_parent(db_session, fam)
    await login(client, "parent@example.com")
    async with open_client(app) as other:
        await login(other, "parent@example.com")
        old_cookie = client.cookies["session"]

        r = await client.post(
            "/api/auth/password",
            json={"current_password": TEST_PASSWORD, "new_password": NEW_PASSWORD},
        )

        assert r.status_code == 204
        assert client.cookies["session"] != old_cookie
        assert (await client.get("/api/auth/me")).status_code == 200
        assert (await other.get("/api/auth/me")).status_code == 401
    await db_session.refresh(parent)
    assert verify_password(parent.password_hash, NEW_PASSWORD)
    await login(client, "parent@example.com", NEW_PASSWORD)


async def test_wrong_current_password(client: AsyncClient, db_session: AsyncSession) -> None:
    fam = await make_family(db_session)
    parent = await make_parent(db_session, fam)
    await login(client, "parent@example.com")

    r = await client.post(
        "/api/auth/password",
        json={"current_password": "wrong-pass-1", "new_password": NEW_PASSWORD},
    )

    assert r.status_code == 422
    error = r.json()["error"]
    assert error["code"] == "invalid_current_password"
    assert error["details"]["field"] == "current_password"
    await db_session.refresh(parent)
    assert verify_password(parent.password_hash, TEST_PASSWORD)
    assert (await client.get("/api/auth/me")).status_code == 200


async def test_new_password_is_validated(client: AsyncClient, db_session: AsyncSession) -> None:
    fam = await make_family(db_session)
    await make_parent(db_session, fam)
    await login(client, "parent@example.com")

    common = await client.post(
        "/api/auth/password",
        json={"current_password": TEST_PASSWORD, "new_password": "12345678"},
    )
    short = await client.post(
        "/api/auth/password",
        json={"current_password": TEST_PASSWORD, "new_password": "Ab3$xy"},
    )

    assert common.status_code == 422 and common.json()["error"]["code"] == "password_too_common"
    assert short.status_code == 422 and short.json()["error"]["code"] == "password_too_short"


async def test_change_password_requires_login(client: AsyncClient) -> None:
    r = await client.post(
        "/api/auth/password",
        json={"current_password": TEST_PASSWORD, "new_password": NEW_PASSWORD},
    )

    assert r.status_code == 401
