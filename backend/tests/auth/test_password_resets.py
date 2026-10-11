from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User
from app.auth.passwords import verify_password
from app.auth.service import build_link, create_password_reset
from app.auth.tokens import RESET_TTL, new_token, sha256_hex
from app.core.config import Settings
from tests.factories import TEST_PASSWORD, login, make_child, make_family, make_parent, make_tutor

NEW_PASSWORD = "New-Strong-9"


def test_new_token_returns_token_and_its_hash() -> None:
    token, token_hash = new_token()
    other, _ = new_token()

    assert token_hash == sha256_hex(token)
    assert token != other and len(token) >= 40


def test_build_link(settings: Settings) -> None:
    base = settings.public_base_url
    assert build_link(settings, "invite", "abc") == f"{base}/invite/abc"
    assert build_link(settings, "reset", "xyz") == f"{base}/reset/xyz"


async def test_reset_flow_kills_sessions(client: AsyncClient, db_session: AsyncSession) -> None:
    tutor = await make_tutor(db_session)
    fam = await make_family(db_session)
    parent = await make_parent(db_session, fam)
    await login(client, "parent@example.com")
    token, reset = await create_password_reset(db_session, user=parent, created_by=tutor)

    info = (await client.get(f"/api/auth/password-resets/{token}")).json()
    assert info["login"] == "parent@example.com"
    assert abs(datetime.fromisoformat(info["expires_at"]) - (datetime.now(UTC) + RESET_TTL)) < (
        timedelta(minutes=1)
    )
    r = await client.post(f"/api/auth/password-resets/{token}", json={"password": NEW_PASSWORD})

    assert r.status_code == 204
    assert (await client.get("/api/auth/me")).status_code == 401
    await db_session.refresh(reset)
    assert reset.used_at is not None
    await db_session.refresh(parent)
    assert verify_password(parent.password_hash, NEW_PASSWORD)
    await login(client, "parent@example.com", NEW_PASSWORD)


async def test_reset_info_shows_username_for_child(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tutor = await make_tutor(db_session)
    fam = await make_family(db_session)
    child = await make_child(db_session, fam, username="masha")
    assert child.user_id is not None
    user = await db_session.get(User, child.user_id)
    assert user is not None
    token, _ = await create_password_reset(db_session, user=user, created_by=tutor)

    r = await client.get(f"/api/auth/password-resets/{token}")

    assert r.status_code == 200 and r.json()["login"] == "masha"


async def test_reset_link_single_use(client: AsyncClient, db_session: AsyncSession) -> None:
    tutor = await make_tutor(db_session)
    fam = await make_family(db_session)
    parent = await make_parent(db_session, fam)
    token, _ = await create_password_reset(db_session, user=parent, created_by=tutor)
    first = await client.post(f"/api/auth/password-resets/{token}", json={"password": NEW_PASSWORD})
    assert first.status_code == 204

    again = await client.post(
        f"/api/auth/password-resets/{token}", json={"password": "Another-Pass-1"}
    )

    assert again.status_code == 404 and again.json()["error"]["code"] == "reset_invalid"
    assert (await client.get(f"/api/auth/password-resets/{token}")).status_code == 404
    await db_session.refresh(parent)
    assert verify_password(parent.password_hash, NEW_PASSWORD)


async def test_unknown_reset_token(client: AsyncClient) -> None:
    r = await client.get("/api/auth/password-resets/does-not-exist")

    assert r.status_code == 404 and r.json()["error"]["code"] == "reset_invalid"


async def test_expired_reset(client: AsyncClient, db_session: AsyncSession) -> None:
    tutor = await make_tutor(db_session)
    fam = await make_family(db_session)
    parent = await make_parent(db_session, fam)
    token, reset = await create_password_reset(db_session, user=parent, created_by=tutor)
    reset.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.flush()

    info = await client.get(f"/api/auth/password-resets/{token}")
    post = await client.post(f"/api/auth/password-resets/{token}", json={"password": NEW_PASSWORD})

    assert info.status_code == 404 and info.json()["error"]["code"] == "reset_invalid"
    assert post.status_code == 404 and post.json()["error"]["code"] == "reset_invalid"
    await db_session.refresh(parent)
    assert verify_password(parent.password_hash, TEST_PASSWORD)


async def test_child_reset_allows_six_chars(client: AsyncClient, db_session: AsyncSession) -> None:
    tutor = await make_tutor(db_session)
    fam = await make_family(db_session)
    child = await make_child(db_session, fam, username="masha")
    assert child.user_id is not None
    user = await db_session.get(User, child.user_id)
    assert user is not None
    token, _ = await create_password_reset(db_session, user=user, created_by=tutor)

    r = await client.post(f"/api/auth/password-resets/{token}", json={"password": "Ab3$xy"})

    assert r.status_code == 204
    await login(client, "masha", "Ab3$xy")


async def test_parent_reset_requires_eight_chars(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tutor = await make_tutor(db_session)
    fam = await make_family(db_session)
    parent = await make_parent(db_session, fam)
    token, reset = await create_password_reset(db_session, user=parent, created_by=tutor)

    r = await client.post(f"/api/auth/password-resets/{token}", json={"password": "Ab3$xy"})

    assert r.status_code == 422 and r.json()["error"]["code"] == "password_too_short"
    await db_session.refresh(reset)
    assert reset.used_at is None


async def test_common_password_rejected_on_reset(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tutor = await make_tutor(db_session)
    fam = await make_family(db_session)
    parent = await make_parent(db_session, fam)
    token, reset = await create_password_reset(db_session, user=parent, created_by=tutor)

    r = await client.post(f"/api/auth/password-resets/{token}", json={"password": "12345678"})

    assert r.status_code == 422 and r.json()["error"]["code"] == "password_too_common"
    await db_session.refresh(reset)
    assert reset.used_at is None


async def test_new_reset_invalidates_previous(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tutor = await make_tutor(db_session)
    fam = await make_family(db_session)
    parent = await make_parent(db_session, fam)
    other = await make_parent(db_session, fam, email="other@example.com")
    old_token, old = await create_password_reset(db_session, user=parent, created_by=tutor)
    other_token, _ = await create_password_reset(db_session, user=other, created_by=tutor)
    new_token_, new = await create_password_reset(db_session, user=parent, created_by=tutor)

    await db_session.refresh(old)
    await db_session.refresh(new)
    assert old.used_at is not None and new.used_at is None
    r = await client.post(f"/api/auth/password-resets/{old_token}", json={"password": NEW_PASSWORD})
    assert r.status_code == 404
    assert (await client.get(f"/api/auth/password-resets/{new_token_}")).status_code == 200
    # Сброс другого пользователя не затронут.
    assert (await client.get(f"/api/auth/password-resets/{other_token}")).status_code == 200
