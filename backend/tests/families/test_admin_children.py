from datetime import UTC, datetime

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import open_client
from tests.factories import login, make_child, make_family

MISSING_ID = "019a0000-0000-7000-8000-000000000000"


async def test_add_and_update_child(tutor_client: AsyncClient, db_session: AsyncSession) -> None:
    fam = await make_family(db_session)

    r = await tutor_client.post(
        f"/api/admin/families/{fam.id}/children",
        json={
            "full_name": " Маша Иванова ",
            "birth_year": 2015,
            "english_level": "B1",
            "default_meeting_url": "https://zoom.us/j/123",
        },
    )

    assert r.status_code == 201
    child = r.json()
    assert child["full_name"] == "Маша Иванова"
    assert child["birth_year"] == 2015
    assert child["english_level"] == "B1"
    assert child["default_meeting_url"] == "https://zoom.us/j/123"
    assert child["archived_at"] is None
    assert child["account"] is None

    r = await tutor_client.patch(
        f"/api/admin/children/{child['id']}",
        json={"full_name": "Мария", "english_level": "A2", "birth_year": 2016},
    )
    assert r.status_code == 200
    assert r.json()["full_name"] == "Мария"
    assert r.json()["english_level"] == "A2"
    assert r.json()["birth_year"] == 2016
    assert r.json()["default_meeting_url"] == "https://zoom.us/j/123"

    r = await tutor_client.patch(
        f"/api/admin/children/{child['id']}",
        json={"birth_year": None, "english_level": None, "default_meeting_url": None},
    )
    assert r.json()["birth_year"] is None
    assert r.json()["english_level"] is None
    assert r.json()["default_meeting_url"] is None
    assert r.json()["full_name"] == "Мария"


async def test_child_validation(tutor_client: AsyncClient, db_session: AsyncSession) -> None:
    fam = await make_family(db_session)
    url = f"/api/admin/families/{fam.id}/children"
    next_year = datetime.now(UTC).year + 1

    bad_payloads = [
        {"full_name": "Маша", "birth_year": 1980},
        {"full_name": "Маша", "birth_year": next_year},
        {"full_name": "Маша", "default_meeting_url": "ftp://x"},
        {"full_name": "Маша", "default_meeting_url": "не ссылка"},
        {"full_name": "Маша", "default_meeting_url": "https://x.ru/" + "a" * 500},
        {"full_name": "Маша", "english_level": "D9"},
        {"full_name": ""},
        {"full_name": "я" * 201},
    ]
    for payload in bad_payloads:
        r = await tutor_client.post(url, json=payload)
        assert r.status_code == 422, payload

    ok = await tutor_client.post(url, json={"full_name": "Маша", "birth_year": next_year - 1})
    assert ok.status_code == 201
    child_url = f"/api/admin/children/{ok.json()['id']}"
    assert (await tutor_client.patch(child_url, json={"birth_year": 1980})).status_code == 422
    assert (await tutor_client.patch(child_url, json={"full_name": None})).status_code == 422


async def test_unknown_child_or_family_is_404(tutor_client: AsyncClient) -> None:
    patch = await tutor_client.patch(f"/api/admin/children/{MISSING_ID}", json={"full_name": "x"})
    account = await tutor_client.post(
        f"/api/admin/children/{MISSING_ID}/account",
        json={"username": "masha", "password": "Ab3$xy"},
    )
    add = await tutor_client.post(
        f"/api/admin/families/{MISSING_ID}/children", json={"full_name": "x"}
    )

    assert patch.status_code == 404
    assert account.status_code == 404
    assert add.status_code == 404


async def test_child_endpoints_are_tutor_only(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    fam = await make_family(db_session)
    child = await make_child(db_session, fam, username="masha")
    body = {"username": "masha", "password": "Ab3$xy"}

    anonymous = await client.post(f"/api/admin/children/{child.id}/account", json=body)
    await login(client, "masha")
    as_child_patch = await client.patch(f"/api/admin/children/{child.id}", json={"archived": True})
    as_child_account = await client.post(f"/api/admin/children/{child.id}/account", json=body)

    assert anonymous.status_code == 401
    assert as_child_patch.status_code == 404
    assert as_child_account.status_code == 404


async def test_set_child_account_then_child_logs_in(
    app: FastAPI, tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    fam = await make_family(db_session)
    child = await make_child(db_session, fam)

    r = await tutor_client.post(
        f"/api/admin/children/{child.id}/account",
        json={"username": " Masha.K ", "password": "Ab3$xy"},
    )

    assert r.status_code == 200
    assert r.json()["account"]["username"] == "masha.k"
    assert r.json()["account"]["is_active"] is True
    async with open_client(app) as kid:
        me = await login(kid, "masha.k", "Ab3$xy")
        assert me.json()["role"] == "child"


async def test_username_taken(tutor_client: AsyncClient, db_session: AsyncSession) -> None:
    fam = await make_family(db_session)
    await make_child(db_session, fam, full_name="Маша", username="masha")
    other = await make_child(db_session, fam, full_name="Петя")

    r = await tutor_client.post(
        f"/api/admin/children/{other.id}/account", json={"username": "MASHA", "password": "Ab3$xy"}
    )

    assert r.status_code == 409
    assert r.json()["error"]["code"] == "username_taken"


async def test_keeping_own_username_is_not_taken(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    fam = await make_family(db_session)
    child = await make_child(db_session, fam, username="masha")

    r = await tutor_client.post(
        f"/api/admin/children/{child.id}/account", json={"username": "Masha", "password": "Ab3$xy"}
    )

    assert r.status_code == 200
    assert r.json()["account"]["username"] == "masha"


async def test_cyrillic_username_rejected(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    fam = await make_family(db_session)
    child = await make_child(db_session, fam)

    r = await tutor_client.post(
        f"/api/admin/children/{child.id}/account", json={"username": "маша", "password": "Ab3$xy"}
    )

    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_username"


async def test_child_password_rules(tutor_client: AsyncClient, db_session: AsyncSession) -> None:
    fam = await make_family(db_session)
    child = await make_child(db_session, fam)
    url = f"/api/admin/children/{child.id}/account"

    short = await tutor_client.post(url, json={"username": "masha", "password": "Ab3$x"})
    common = await tutor_client.post(url, json={"username": "masha", "password": "qwerty"})
    too_long = await tutor_client.post(url, json={"username": "masha", "password": "a" * 129})
    six = await tutor_client.post(url, json={"username": "masha", "password": "Ab3$xy"})

    assert short.status_code == 422
    assert short.json()["error"]["code"] == "password_too_short"
    assert common.status_code == 422
    assert common.json()["error"]["code"] == "password_too_common"
    assert too_long.status_code == 422
    assert six.status_code == 200


async def test_changing_child_account_logs_child_out(
    app: FastAPI, tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    fam = await make_family(db_session)
    child = await make_child(db_session, fam, username="masha")
    async with open_client(app) as kid:
        await login(kid, "masha")

        r = await tutor_client.post(
            f"/api/admin/children/{child.id}/account",
            json={"username": "masha2", "password": "Zz9$new"},
        )

        assert r.status_code == 200
        assert (await kid.get("/api/auth/me")).status_code == 401
        old = await kid.post("/api/auth/login", json={"login": "masha", "password": "Zz9$new"})
        assert old.status_code == 401
        await login(kid, "masha2", "Zz9$new")


async def test_archive_child_deactivates_account(
    app: FastAPI, tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    fam = await make_family(db_session)
    child = await make_child(db_session, fam, username="masha")
    async with open_client(app) as kid:
        await login(kid, "masha")

        r = await tutor_client.patch(f"/api/admin/children/{child.id}", json={"archived": True})

        assert r.status_code == 200
        assert r.json()["archived_at"] is not None
        assert r.json()["account"]["is_active"] is False
        assert (await kid.get("/api/auth/me")).status_code == 401

        r = await tutor_client.patch(f"/api/admin/children/{child.id}", json={"archived": False})

        assert r.json()["archived_at"] is None
        assert r.json()["account"]["is_active"] is True
        await login(kid, "masha")


async def test_unarchive_child_in_archived_family_conflict(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    fam = await make_family(db_session, archived=True)
    child = await make_child(db_session, fam, archived=True)

    r = await tutor_client.patch(f"/api/admin/children/{child.id}", json={"archived": False})

    assert r.status_code == 409
    assert r.json()["error"]["code"] == "family_archived"


async def test_archived_child_account_is_conflict(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    fam = await make_family(db_session)
    child = await make_child(db_session, fam, archived=True)

    r = await tutor_client.post(
        f"/api/admin/children/{child.id}/account", json={"username": "masha", "password": "Ab3$xy"}
    )

    assert r.status_code == 409
    assert r.json()["error"]["code"] == "child_archived"


async def test_account_in_archived_family_is_conflict(
    tutor_client: AsyncClient, db_session: AsyncSession
) -> None:
    fam = await make_family(db_session, archived=True)
    child = await make_child(db_session, fam)

    r = await tutor_client.post(
        f"/api/admin/children/{child.id}/account", json={"username": "masha", "password": "Ab3$xy"}
    )

    assert r.status_code == 409
    assert r.json()["error"]["code"] == "family_archived"
