import asyncio
import subprocess
import sys
from collections import Counter
from datetime import UTC, datetime

import pytest
from argon2 import PasswordHasher
from fastapi import FastAPI
from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User, UserRole
from app.auth.passwords import password_needs_rehash, verify_password
from app.auth.service import DUMMY_PASSWORD_HASH, build_me
from app.auth.sessions import SessionStore
from app.core.db import get_db_session
from tests.conftest import BACKEND_DIR, open_client
from tests.factories import (
    TEST_PASSWORD,
    login,
    make_child,
    make_family,
    make_parent,
    make_tutor,
)

WRONG_PASSWORD = "wrong-pass-1"


async def _attempt(client: AsyncClient, login_: str, password: str = WRONG_PASSWORD) -> int:
    r = await client.post("/api/auth/login", json={"login": login_, "password": password})
    return r.status_code


async def test_login_parent_sets_cookie_and_returns_me(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    fam = await make_family(db_session)
    await make_parent(db_session, fam)
    await make_child(db_session, fam, full_name="Маша")
    await make_child(db_session, fam, full_name="Архивный", archived=True)

    r = await client.post(
        "/api/auth/login", json={"login": " Parent@Example.com ", "password": TEST_PASSWORD}
    )

    assert r.status_code == 200
    me = r.json()
    assert me["role"] == "parent" and me["display_name"] == "Анна Иванова"
    assert me["email"] == "parent@example.com" and me["username"] is None
    assert me["family"]["name"] == "Ивановы"
    assert [c["full_name"] for c in me["children"]] == ["Маша"]
    cookie = r.headers["set-cookie"].lower()
    assert "session=" in cookie and "httponly" in cookie and "secure" in cookie
    assert "samesite=lax" in cookie and "max-age=2592000" in cookie
    assert (await client.get("/api/auth/me")).json() == me


async def test_login_child_by_username(client: AsyncClient, db_session: AsyncSession) -> None:
    fam = await make_family(db_session)
    child = await make_child(db_session, fam, full_name="Маша", username="masha")
    await make_child(db_session, fam, full_name="Петя", username="petya")

    me = (await login(client, "MASHA")).json()

    assert me["role"] == "child" and me["display_name"] == "Маша"
    assert me["username"] == "masha" and me["email"] is None
    assert me["family"]["name"] == "Ивановы"
    assert me["children"] == [{"id": str(child.id), "full_name": "Маша"}]


async def test_login_tutor(client: AsyncClient, db_session: AsyncSession) -> None:
    await make_tutor(db_session)

    r = await login(client, "tutor@example.com")

    me = r.json()
    assert me["role"] == "tutor" and me["display_name"] == "tutor@example.com"
    assert me["family"] is None and me["children"] == []
    assert "max-age=604800" in r.headers["set-cookie"].lower()


async def test_login_updates_last_login_and_rehashes_weak_hash(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    fam = await make_family(db_session)
    user = await make_parent(db_session, fam)
    user.password_hash = PasswordHasher(time_cost=1, memory_cost=8, parallelism=1).hash(
        TEST_PASSWORD
    )
    await db_session.flush()
    assert password_needs_rehash(user.password_hash)
    before = datetime.now(UTC)

    await login(client, "parent@example.com")

    await db_session.refresh(user)
    assert user.last_login_at is not None and user.last_login_at >= before
    assert not password_needs_rehash(user.password_hash)
    assert verify_password(user.password_hash, TEST_PASSWORD)


async def test_wrong_password_and_unknown_login_look_the_same(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    fam = await make_family(db_session)
    await make_parent(db_session, fam)

    r1 = await client.post(
        "/api/auth/login", json={"login": "parent@example.com", "password": WRONG_PASSWORD}
    )
    r2 = await client.post(
        "/api/auth/login", json={"login": "nobody@example.com", "password": WRONG_PASSWORD}
    )

    assert r1.status_code == r2.status_code == 401
    assert r1.json() == r2.json()
    assert r1.json()["error"]["code"] == "invalid_credentials"
    assert r1.json()["error"]["message"] == "Неверный логин или пароль"
    assert "set-cookie" not in r1.headers and "set-cookie" not in r2.headers


async def test_inactive_user_cannot_login_even_with_correct_password(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    fam = await make_family(db_session)
    await make_parent(db_session, fam, is_active=False)

    r = await client.post(
        "/api/auth/login", json={"login": "parent@example.com", "password": TEST_PASSWORD}
    )

    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_credentials"
    assert "set-cookie" not in r.headers


async def test_me_requires_session(client: AsyncClient) -> None:
    r = await client.get("/api/auth/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "not_authenticated"


async def test_me_rejects_unknown_session_token(client: AsyncClient) -> None:
    client.cookies.set("session", "not-a-real-token")
    r = await client.get("/api/auth/me")
    assert r.status_code == 401 and r.json()["error"]["code"] == "not_authenticated"


async def test_sixth_attempt_is_rate_limited_even_with_correct_password(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    fam = await make_family(db_session)
    await make_parent(db_session, fam)
    for _ in range(5):
        assert await _attempt(client, "parent@example.com") == 401

    r = await client.post(
        "/api/auth/login", json={"login": "parent@example.com", "password": TEST_PASSWORD}
    )

    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
    assert r.json()["error"]["code"] == "rate_limited"
    assert "set-cookie" not in r.headers
    # Другой логин с того же IP не затронут лимитом пары.
    await make_parent(db_session, fam, email="other@example.com")
    assert (
        await client.post(
            "/api/auth/login", json={"login": "other@example.com", "password": TEST_PASSWORD}
        )
    ).status_code == 200


async def test_pair_limit_ignores_login_case_and_spaces(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    fam = await make_family(db_session)
    await make_parent(db_session, fam)
    variants = [
        "parent@example.com",
        "PARENT@example.com",
        " parent@example.com",
        "Parent@EXAMPLE.com",
    ]
    for i in range(5):
        assert await _attempt(client, variants[i % len(variants)]) == 401

    assert await _attempt(client, "parent@example.com", TEST_PASSWORD) == 429


async def test_ip_limit_after_30_failures(client: AsyncClient) -> None:
    for i in range(30):
        assert await _attempt(client, f"user{i}@example.com") == 401

    assert await _attempt(client, "someone-else@example.com") == 429


async def test_success_resets_pair_counter(client: AsyncClient, db_session: AsyncSession) -> None:
    fam = await make_family(db_session)
    await make_parent(db_session, fam)
    for _ in range(4):
        assert await _attempt(client, "parent@example.com") == 401
    await login(client, "parent@example.com")

    for _ in range(4):
        assert await _attempt(client, "parent@example.com") == 401


async def test_login_rotates_session(
    client: AsyncClient, db_session: AsyncSession, redis: Redis
) -> None:
    fam = await make_family(db_session)
    await make_parent(db_session, fam)
    await login(client, "parent@example.com")
    first = client.cookies["session"]
    store = SessionStore(redis)
    assert await store.get(first) is not None

    await login(client, "parent@example.com")

    assert client.cookies["session"] != first
    assert await store.get(first) is None
    assert (await client.get("/api/auth/me")).status_code == 200


async def test_failed_login_keeps_existing_session(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    fam = await make_family(db_session)
    await make_parent(db_session, fam)
    await login(client, "parent@example.com")

    assert await _attempt(client, "parent@example.com") == 401

    assert (await client.get("/api/auth/me")).status_code == 200


async def test_logout(client: AsyncClient, db_session: AsyncSession, redis: Redis) -> None:
    fam = await make_family(db_session)
    await make_parent(db_session, fam)
    await login(client, "parent@example.com")
    token = client.cookies["session"]

    r = await client.post("/api/auth/logout")

    assert r.status_code == 204
    assert 'session=""' in r.headers["set-cookie"] or "session=;" in r.headers["set-cookie"]
    assert await SessionStore(redis).get(token) is None
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_logout_without_session_is_204(client: AsyncClient) -> None:
    assert (await client.post("/api/auth/logout")).status_code == 204


async def test_logout_requires_csrf(client: AsyncClient) -> None:
    del client.headers["X-CSRF-Token"]
    r = await client.post("/api/auth/logout")
    assert r.status_code == 403 and r.json()["error"]["code"] == "csrf_failed"


async def test_deactivated_user_session_is_rejected(
    client: AsyncClient, db_session: AsyncSession, redis: Redis
) -> None:
    fam = await make_family(db_session)
    user = await make_parent(db_session, fam)
    await login(client, "parent@example.com")
    token = client.cookies["session"]
    user.is_active = False
    await db_session.flush()

    assert (await client.get("/api/auth/me")).status_code == 401
    assert await SessionStore(redis).get(token) is None


async def test_sessions_of_archived_members_are_rejected(
    app: FastAPI, db_session: AsyncSession, redis: Redis
) -> None:
    # Архив выставлен прямо в БД (без отзыва сессий): доступ закрывает сама проверка архива.
    fam = await make_family(db_session)
    await make_parent(db_session, fam)
    await make_child(db_session, fam, full_name="Маша", username="masha")
    other_fam = await make_family(db_session, name="Петровы")
    other_kid = await make_child(db_session, other_fam, full_name="Петя", username="petya")
    async with open_client(app) as parent_c, open_client(app) as kid_c, open_client(app) as other_c:
        await login(parent_c, "parent@example.com")
        await login(kid_c, "masha")
        await login(other_c, "petya")
        tokens = [c.cookies["session"] for c in (parent_c, kid_c, other_c)]
        fam.archived_at = datetime.now(UTC)
        other_kid.archived_at = datetime.now(UTC)
        await db_session.flush()

        for c in (parent_c, kid_c, other_c):
            assert (await c.get("/api/auth/me")).status_code == 401
        store = SessionStore(redis)
        for token in tokens:
            assert await store.get(token) is None

        fam.archived_at = None
        other_kid.archived_at = None
        await db_session.flush()
        await login(parent_c, "parent@example.com")
        await login(kid_c, "masha")
        await login(other_c, "petya")


async def test_archived_members_cannot_login(client: AsyncClient, db_session: AsyncSession) -> None:
    archived_fam = await make_family(db_session, archived=True)
    await make_parent(db_session, archived_fam)
    await make_child(db_session, archived_fam, full_name="Маша", username="masha")
    fam = await make_family(db_session, name="Петровы")
    await make_child(db_session, fam, full_name="Петя", username="petya", archived=True)
    await make_tutor(db_session)

    for login_ in ("parent@example.com", "masha", "petya"):
        r = await client.post("/api/auth/login", json={"login": login_, "password": TEST_PASSWORD})
        assert r.status_code == 401, login_
        assert r.json()["error"]["code"] == "invalid_credentials"
        assert "set-cookie" not in r.headers
    await login(client, "tutor@example.com")


async def test_session_with_changed_role_is_rejected(
    client: AsyncClient, db_session: AsyncSession, redis: Redis
) -> None:
    fam = await make_family(db_session)
    user = await make_parent(db_session, fam)
    await login(client, "parent@example.com")
    token = client.cookies["session"]
    user.role = UserRole.TUTOR
    await db_session.flush()

    assert (await client.get("/api/auth/me")).status_code == 401
    assert await SessionStore(redis).get(token) is None


async def test_session_of_deleted_user_is_rejected(
    client: AsyncClient, db_session: AsyncSession, redis: Redis
) -> None:
    await make_tutor(db_session)
    await login(client, "tutor@example.com")
    token = client.cookies["session"]
    user = await db_session.scalar(select(User).where(User.email == "tutor@example.com"))
    assert user is not None
    await db_session.delete(user)
    await db_session.flush()

    assert (await client.get("/api/auth/me")).status_code == 401
    assert await SessionStore(redis).get(token) is None


async def test_password_field_length_limit(client: AsyncClient) -> None:
    r = await client.post("/api/auth/login", json={"login": "a@b.co", "password": "x" * 129})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


async def test_empty_login_or_password_is_rejected(client: AsyncClient) -> None:
    for body in ({"login": "", "password": "x"}, {"login": "a@b.co", "password": ""}):
        assert (await client.post("/api/auth/login", json=body)).status_code == 422


def test_dummy_hash_is_a_valid_hash_of_an_unknown_password() -> None:
    assert not verify_password(DUMMY_PASSWORD_HASH, TEST_PASSWORD)
    assert DUMMY_PASSWORD_HASH.startswith("$argon2id$")


async def test_build_me_fails_loudly_on_parent_without_profile(db_session: AsyncSession) -> None:
    user = User(role=UserRole.PARENT, email="orphan@example.com", password_hash="x")
    db_session.add(user)
    await db_session.flush()

    with pytest.raises(RuntimeError):
        await build_me(db_session, user)


async def test_build_me_fails_loudly_on_child_user_without_card(db_session: AsyncSession) -> None:
    user = User(role=UserRole.CHILD, username="orphan", password_hash="x")
    db_session.add(user)
    await db_session.flush()

    with pytest.raises(RuntimeError):
        await build_me(db_session, user)


def test_app_import_registers_families_tables() -> None:
    """`invitations` ссылается на `families`: цепочка импортов приложения обязана подключить обе."""
    code = (
        "from app.main import create_app\n"
        "from app.core.db import Base\n"
        "missing = {'families', 'parent_profiles', 'children'} - set(Base.metadata.tables)\n"
        "assert not missing, missing\n"
        "Base.metadata.sorted_tables\n"
    )
    result = subprocess.run(  # noqa: S603 (свой интерпретатор и константный код)
        [sys.executable, "-c", code], cwd=BACKEND_DIR, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr


async def test_successful_logins_do_not_consume_ip_budget(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    fam = await make_family(db_session)
    await make_parent(db_session, fam)
    for i in range(29):
        assert await _attempt(client, f"user{i}@example.com") == 401
    for _ in range(3):
        await login(client, "parent@example.com")

    assert await _attempt(client, "another@example.com") == 401  # 30-я неудача — ещё не 429
    assert await _attempt(client, "another2@example.com") == 429


async def test_concurrent_burst_cannot_bypass_pair_limit(app: FastAPI) -> None:
    # Каждый запрос — своя сессия БД (как в проде); логин несуществующий, данных в БД не создаётся.
    del app.dependency_overrides[get_db_session]
    async with open_client(app) as c:
        responses = await asyncio.gather(
            *[
                c.post(
                    "/api/auth/login",
                    json={"login": "nobody@example.com", "password": WRONG_PASSWORD},
                )
                for _ in range(10)
            ]
        )

    codes = Counter(r.status_code for r in responses)
    assert codes[401] == 5 and codes[429] == 5, codes
    assert all(int(r.headers["Retry-After"]) > 0 for r in responses if r.status_code == 429)
