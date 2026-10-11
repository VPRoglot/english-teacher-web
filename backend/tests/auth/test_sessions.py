import json
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import Response
from redis.asyncio import Redis

from app.auth.models import UserRole
from app.auth.sessions import (
    SESSION_COOKIE,
    SESSION_TTL,
    SessionStore,
    clear_session_cookie,
    set_session_cookie,
)
from app.auth.tokens import sha256_hex
from app.core.config import Settings
from app.core.db import new_uuid7

DAY = 86400


async def test_create_and_get(redis: Redis) -> None:
    store = SessionStore(redis)
    uid = new_uuid7()
    token = await store.create(uid, UserRole.PARENT)
    data = await store.get(token)
    assert data
    assert data.user_id == uid
    assert data.role is UserRole.PARENT
    assert abs(datetime.now(UTC) - data.created_at) < timedelta(minutes=1)
    assert await redis.ttl(f"session:{sha256_hex(token)}") > 29 * DAY


async def test_stored_json_format(redis: Redis) -> None:
    uid = new_uuid7()
    token = await SessionStore(redis).create(uid, UserRole.TUTOR)
    raw = await redis.get(f"session:{sha256_hex(token)}")
    assert raw is not None
    payload = json.loads(raw)
    assert payload["user_id"] == str(uid)
    assert payload["role"] == "tutor"
    assert datetime.fromisoformat(payload["created_at"]).utcoffset() == timedelta(0)


async def test_create_indexes_session_for_user(redis: Redis) -> None:
    uid = new_uuid7()
    token = await SessionStore(redis).create(uid, UserRole.TUTOR)
    assert await redis.smembers(f"user_sessions:{uid}") == {sha256_hex(token)}
    assert await redis.ttl(f"user_sessions:{uid}") > 29 * DAY


async def test_token_not_stored_in_plain(redis: Redis) -> None:
    token = await SessionStore(redis).create(new_uuid7(), UserRole.CHILD)
    keys = await redis.keys("*")
    assert keys
    assert all(token not in k for k in keys)
    for key in keys:
        if await redis.type(key) == "string":
            assert token not in (await redis.get(key) or "")
        else:
            assert all(token not in m for m in await redis.smembers(key))


@pytest.mark.parametrize(
    ("role", "days"), [(UserRole.TUTOR, 7), (UserRole.PARENT, 30), (UserRole.CHILD, 30)]
)
async def test_get_extends_ttl(redis: Redis, role: UserRole, days: int) -> None:
    store = SessionStore(redis)
    token = await store.create(new_uuid7(), role)
    key = f"session:{sha256_hex(token)}"
    await redis.expire(key, 10)
    await store.get(token)
    assert (days - 1) * DAY < await redis.ttl(key) <= days * DAY


async def test_get_extends_index_ttl_so_revocation_still_works(redis: Redis) -> None:
    store = SessionStore(redis)
    uid = new_uuid7()
    token = await store.create(uid, UserRole.PARENT)
    index = f"user_sessions:{uid}"
    await redis.expire(index, 5)
    assert await store.get(token) is not None
    assert await redis.ttl(index) > 29 * DAY
    assert await store.delete_all_for_user(uid) == 1
    assert await store.get(token) is None


async def test_unknown_and_corrupt_tokens(redis: Redis) -> None:
    store = SessionStore(redis)
    assert await store.get("nope") is None
    await redis.set(f"session:{sha256_hex('bad')}", "{not json")
    assert await store.get("bad") is None
    await redis.set(f"session:{sha256_hex('wrong-shape')}", '{"user_id": "x"}')
    assert await store.get("wrong-shape") is None


async def test_delete_removes_key_and_index_entry(redis: Redis) -> None:
    store = SessionStore(redis)
    uid = new_uuid7()
    t1 = await store.create(uid, UserRole.PARENT)
    t2 = await store.create(uid, UserRole.PARENT)
    await store.delete(t1)
    assert await store.get(t1) is None
    assert await store.get(t2) is not None
    assert await redis.smembers(f"user_sessions:{uid}") == {sha256_hex(t2)}


async def test_delete_unknown_token_is_noop(redis: Redis) -> None:
    await SessionStore(redis).delete("never-existed")


async def test_delete_all_for_user(redis: Redis) -> None:
    store = SessionStore(redis)
    uid = new_uuid7()
    t1 = await store.create(uid, UserRole.PARENT)
    t2 = await store.create(uid, UserRole.PARENT)
    other = await store.create(new_uuid7(), UserRole.PARENT)
    assert await store.delete_all_for_user(uid) == 2
    assert await store.get(t1) is None
    assert await store.get(t2) is None
    assert await store.get(other)
    assert await redis.exists(f"user_sessions:{uid}") == 0


async def test_delete_all_counts_only_existing_sessions(redis: Redis) -> None:
    store = SessionStore(redis)
    uid = new_uuid7()
    alive = await store.create(uid, UserRole.PARENT)
    expired = await store.create(uid, UserRole.PARENT)
    await redis.delete(f"session:{sha256_hex(expired)}")  # TTL истёк, хэш остался в индексе
    assert await store.delete_all_for_user(uid) == 1
    assert await store.get(alive) is None


async def test_delete_all_for_user_without_sessions(redis: Redis) -> None:
    assert await SessionStore(redis).delete_all_for_user(new_uuid7()) == 0


def test_ttl_per_role() -> None:
    assert SESSION_TTL == {
        UserRole.TUTOR: timedelta(days=7),
        UserRole.PARENT: timedelta(days=30),
        UserRole.CHILD: timedelta(days=30),
    }


@pytest.mark.parametrize(
    ("role", "days"), [(UserRole.TUTOR, 7), (UserRole.PARENT, 30), (UserRole.CHILD, 30)]
)
def test_set_session_cookie(settings: Settings, role: UserRole, days: int) -> None:
    response = Response()
    set_session_cookie(response, "tok123", role, settings)
    header = response.headers["set-cookie"]
    assert header.startswith(f"{SESSION_COOKIE}=tok123;")
    assert f"Max-Age={days * DAY}" in header
    assert "HttpOnly" in header
    assert "Secure" in header
    assert "SameSite=lax" in header
    assert "Path=/" in header


def test_set_session_cookie_not_secure_when_disabled(settings: Settings) -> None:
    response = Response()
    insecure = settings.model_copy(update={"session_cookie_secure": False})
    set_session_cookie(response, "tok", UserRole.TUTOR, insecure)
    assert "Secure" not in response.headers["set-cookie"]


def test_clear_session_cookie(settings: Settings) -> None:
    response = Response()
    clear_session_cookie(response, settings)
    header = response.headers["set-cookie"]
    assert header.startswith(f'{SESSION_COOKIE}=""; ')
    assert "Max-Age=0" in header
    assert "HttpOnly" in header
    assert "Secure" in header
    assert "SameSite=lax" in header
    assert "Path=/" in header
