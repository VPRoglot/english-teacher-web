import uuid

import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User, UserRole
from app.core.errors import NotAuthenticated
from app.families.scope import get_family_scope
from tests.conftest import open_client
from tests.factories import login, make_child, make_family, make_parent, make_tutor


async def test_parent_sees_only_active_children_of_own_family(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    a = await make_family(db_session, name="A")
    b = await make_family(db_session, name="B")
    await make_parent(db_session, a)
    await make_child(db_session, a, full_name="Маша")
    await make_child(db_session, a, full_name="Петя", archived=True)
    await make_child(db_session, b, full_name="Чужой")
    await login(client, "parent@example.com")

    r = await client.get("/api/me/children")

    assert r.status_code == 200
    assert [c["full_name"] for c in r.json()] == ["Маша"]


async def test_cabinet_child_fields_and_order(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    fam = await make_family(db_session)
    await make_parent(db_session, fam)
    await make_child(db_session, fam, full_name="Яна")
    await make_child(db_session, fam, full_name="Аня", username="anya")
    await login(client, "parent@example.com")

    r = await client.get("/api/me/children")

    assert [c["full_name"] for c in r.json()] == ["Аня", "Яна"]
    assert set(r.json()[0]) == {"id", "full_name", "birth_year", "english_level", "username"}
    assert [c["username"] for c in r.json()] == ["anya", None]


async def test_child_sees_only_self(client: AsyncClient, db_session: AsyncSession) -> None:
    fam = await make_family(db_session)
    me = await make_child(db_session, fam, full_name="Маша", username="masha")
    await make_child(db_session, fam, full_name="Петя", username="petya")
    await login(client, "masha")

    r = await client.get("/api/me/children")

    assert r.status_code == 200
    assert [(c["id"], c["username"]) for c in r.json()] == [(str(me.id), "masha")]


async def test_parent_sets_child_account(
    client: AsyncClient, db_session: AsyncSession, app: FastAPI
) -> None:
    fam = await make_family(db_session)
    await make_parent(db_session, fam)
    child = await make_child(db_session, fam, full_name="Маша")
    await login(client, "parent@example.com")

    r = await client.post(
        f"/api/me/children/{child.id}/account", json={"username": "Masha.K", "password": "Ab3$xy"}
    )

    assert r.status_code == 200
    assert r.json()["id"] == str(child.id)
    assert r.json()["username"] == "masha.k"
    async with open_client(app) as kid:
        me = await login(kid, "masha.k", "Ab3$xy")
        assert me.json()["role"] == "child"
    listed = await client.get("/api/me/children")
    assert listed.json()[0]["username"] == "masha.k"


async def test_parent_cannot_touch_other_family_child(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    a = await make_family(db_session, name="A")
    b = await make_family(db_session, name="B")
    await make_parent(db_session, a)
    foreign = await make_child(db_session, b, full_name="Чужой")
    await login(client, "parent@example.com")

    r = await client.post(
        f"/api/me/children/{foreign.id}/account", json={"username": "hack", "password": "Ab3$xy"}
    )
    missing = await client.post(
        f"/api/me/children/{uuid.uuid4()}/account", json={"username": "hack", "password": "Ab3$xy"}
    )

    assert r.status_code == 404
    assert r.json() == missing.json()
    await db_session.refresh(foreign)
    assert foreign.user_id is None


async def test_parent_cannot_set_account_of_archived_child(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    fam = await make_family(db_session)
    await make_parent(db_session, fam)
    child = await make_child(db_session, fam, archived=True)
    await login(client, "parent@example.com")

    r = await client.post(
        f"/api/me/children/{child.id}/account", json={"username": "kid", "password": "Ab3$xy"}
    )

    assert r.status_code == 404


async def test_parent_account_errors_use_child_rules(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    fam = await make_family(db_session)
    await make_parent(db_session, fam)
    await make_child(db_session, fam, full_name="Маша", username="masha")
    other = await make_child(db_session, fam, full_name="Петя")
    await login(client, "parent@example.com")

    taken = await client.post(
        f"/api/me/children/{other.id}/account", json={"username": "MASHA", "password": "Ab3$xy"}
    )
    weak = await client.post(
        f"/api/me/children/{other.id}/account", json={"username": "petya", "password": "ab"}
    )

    assert taken.status_code == 409
    assert taken.json()["error"]["code"] == "username_taken"
    assert weak.status_code == 422


async def test_child_cannot_set_accounts(client: AsyncClient, db_session: AsyncSession) -> None:
    fam = await make_family(db_session)
    me = await make_child(db_session, fam, username="masha")
    await login(client, "masha")

    r = await client.post(
        f"/api/me/children/{me.id}/account", json={"username": "new", "password": "Ab3$xy"}
    )

    assert r.status_code == 404


async def test_tutor_has_no_cabinet(tutor_client: AsyncClient) -> None:
    assert (await tutor_client.get("/api/me/children")).status_code == 404


async def test_cabinet_requires_login(client: AsyncClient) -> None:
    assert (await client.get("/api/me/children")).status_code == 401


async def test_scope_child_ids(db_session: AsyncSession) -> None:
    fam = await make_family(db_session)
    parent = await make_parent(db_session, fam)
    kid = await make_child(db_session, fam, full_name="Маша", username="masha")
    sibling = await make_child(db_session, fam, full_name="Петя")
    await make_child(db_session, fam, full_name="Архив", archived=True)
    other = await make_family(db_session, name="Other")
    await make_child(db_session, other, full_name="Чужой")
    kid_user = await db_session.get(User, kid.user_id)
    assert kid_user is not None

    parent_scope = await get_family_scope(parent, db_session)
    child_scope = await get_family_scope(kid_user, db_session)

    assert parent_scope.family_id == fam.id
    assert parent_scope.child_ids == frozenset({kid.id, sibling.id})
    assert child_scope.family_id == fam.id
    assert child_scope.child_ids == frozenset({kid.id})


async def test_scope_rejects_archived_child_and_missing_profile(db_session: AsyncSession) -> None:
    fam = await make_family(db_session)
    archived = await make_child(db_session, fam, username="old", archived=True)
    archived_user = await db_session.get(User, archived.user_id)
    assert archived_user is not None
    tutor = await make_tutor(db_session)

    with pytest.raises(NotAuthenticated):
        await get_family_scope(archived_user, db_session)
    with pytest.raises(NotAuthenticated):
        await get_family_scope(tutor, db_session)


async def test_scope_rejects_parent_without_profile(db_session: AsyncSession) -> None:
    orphan = User(role=UserRole.PARENT, email="orphan@example.com", password_hash="x")
    db_session.add(orphan)
    await db_session.flush()

    with pytest.raises(NotAuthenticated):
        await get_family_scope(orphan, db_session)


async def test_parent_without_children_sees_empty_list(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await make_parent(db_session, await make_family(db_session))
    await login(client, "parent@example.com")

    r = await client.get("/api/me/children")

    assert r.status_code == 200
    assert r.json() == []
