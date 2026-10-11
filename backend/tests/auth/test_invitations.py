import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient
from redis.asyncio import Redis
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User, UserRole
from app.auth.service import create_invitation
from app.auth.tokens import INVITATION_TTL, sha256_hex
from app.families.models import ParentProfile
from tests.factories import TEST_PASSWORD, login, make_family, make_parent, make_tutor


def _accept_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "email": " Anna@Mail.RU ",
        "password": TEST_PASSWORD,
        "full_name": "Анна Иванова",
        "phone": "+7 (999) 000-00-00",
        "consent": True,
    }
    body.update(overrides)
    return body


async def _parents_count(session: AsyncSession) -> int:
    return int(
        await session.scalar(
            select(func.count()).select_from(User).where(User.role == UserRole.PARENT)
        )
        or 0
    )


async def test_invitation_info(client: AsyncClient, db_session: AsyncSession) -> None:
    tutor = await make_tutor(db_session)
    fam = await make_family(db_session, name="Петровы")
    token, _ = await create_invitation(
        db_session,
        family=fam,
        created_by=tutor,
        prefill_full_name="Анна",
        prefill_phone="+79990000000",
    )

    r = await client.get(f"/api/auth/invitations/{token}")

    assert r.status_code == 200
    body = r.json()
    assert body["family_name"] == "Петровы"
    assert body["prefill_full_name"] == "Анна"
    assert body["prefill_phone"] == "+79990000000"
    expires_at = datetime.fromisoformat(body["expires_at"])
    expected = datetime.now(UTC) + INVITATION_TTL
    assert abs(expires_at - expected) < timedelta(minutes=1)
    assert INVITATION_TTL == timedelta(days=7)


async def test_invitation_stores_only_token_hash(db_session: AsyncSession) -> None:
    tutor = await make_tutor(db_session)
    fam = await make_family(db_session)

    token, invitation = await create_invitation(
        db_session, family=fam, created_by=tutor, prefill_full_name=None, prefill_phone=None
    )

    assert invitation.token_hash == sha256_hex(token)
    assert token not in invitation.token_hash


async def test_unknown_token_invalid(client: AsyncClient) -> None:
    r = await client.get("/api/auth/invitations/does-not-exist")

    assert r.status_code == 404
    assert r.json()["error"]["code"] == "invitation_invalid"


async def test_accept_creates_parent_and_logs_in(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tutor = await make_tutor(db_session)
    fam = await make_family(db_session)
    token, invitation = await create_invitation(
        db_session, family=fam, created_by=tutor, prefill_full_name="Анна", prefill_phone=None
    )

    r = await client.post(f"/api/auth/invitations/{token}/accept", json=_accept_body())

    assert r.status_code == 201
    body = r.json()
    assert body["role"] == "parent" and body["email"] == "anna@mail.ru"
    assert body["display_name"] == "Анна Иванова"
    assert body["family"] == {"id": str(fam.id), "name": fam.name}
    assert "session" in r.cookies
    profile = await db_session.get(ParentProfile, uuid.UUID(body["id"]))
    assert profile is not None
    assert profile.consent_at is not None and profile.family_id == fam.id
    assert profile.phone == "+7 (999) 000-00-00"
    user = await db_session.get(User, uuid.UUID(body["id"]))
    assert user is not None and user.role is UserRole.PARENT
    await db_session.refresh(invitation)
    assert invitation.used_at is not None
    assert (await client.get("/api/auth/me")).status_code == 200


async def test_accept_replaces_existing_session_cookie(
    client: AsyncClient, db_session: AsyncSession, redis: Redis
) -> None:
    tutor = await make_tutor(db_session)
    fam = await make_family(db_session)
    await login(client, "tutor@example.com")
    previous = client.cookies["session"]
    token, _ = await create_invitation(
        db_session, family=fam, created_by=tutor, prefill_full_name=None, prefill_phone=None
    )

    r = await client.post(f"/api/auth/invitations/{token}/accept", json=_accept_body())

    assert r.status_code == 201
    assert client.cookies["session"] != previous
    assert await redis.exists(f"session:{sha256_hex(previous)}") == 0
    assert (await client.get("/api/auth/me")).json()["role"] == "parent"


async def test_accept_twice_fails(client: AsyncClient, db_session: AsyncSession) -> None:
    tutor = await make_tutor(db_session)
    fam = await make_family(db_session)
    token, _ = await create_invitation(
        db_session, family=fam, created_by=tutor, prefill_full_name=None, prefill_phone=None
    )
    assert (
        await client.post(f"/api/auth/invitations/{token}/accept", json=_accept_body())
    ).status_code == 201

    r = await client.post(
        f"/api/auth/invitations/{token}/accept", json=_accept_body(email="second@mail.ru")
    )

    assert r.status_code == 404
    assert r.json()["error"]["code"] == "invitation_invalid"
    assert await _parents_count(db_session) == 1
    assert (await client.get(f"/api/auth/invitations/{token}")).status_code == 404


async def test_expired_invitation(client: AsyncClient, db_session: AsyncSession) -> None:
    tutor = await make_tutor(db_session)
    fam = await make_family(db_session)
    token, invitation = await create_invitation(
        db_session, family=fam, created_by=tutor, prefill_full_name=None, prefill_phone=None
    )
    invitation.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    await db_session.flush()

    info = await client.get(f"/api/auth/invitations/{token}")
    accept = await client.post(f"/api/auth/invitations/{token}/accept", json=_accept_body())

    assert info.status_code == 404 and info.json()["error"]["code"] == "invitation_invalid"
    assert accept.status_code == 404 and accept.json()["error"]["code"] == "invitation_invalid"
    assert await _parents_count(db_session) == 0


async def test_new_invitation_revokes_previous(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tutor = await make_tutor(db_session)
    fam = await make_family(db_session)
    old_token, old = await create_invitation(
        db_session, family=fam, created_by=tutor, prefill_full_name=None, prefill_phone=None
    )
    new_token, new = await create_invitation(
        db_session, family=fam, created_by=tutor, prefill_full_name=None, prefill_phone=None
    )

    await db_session.refresh(old)
    await db_session.refresh(new)
    assert old.revoked_at is not None and new.revoked_at is None
    assert (await client.get(f"/api/auth/invitations/{old_token}")).status_code == 404
    r = await client.post(f"/api/auth/invitations/{old_token}/accept", json=_accept_body())
    assert r.status_code == 404
    assert (await client.get(f"/api/auth/invitations/{new_token}")).status_code == 200


async def test_new_invitation_keeps_other_family_invitations(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tutor = await make_tutor(db_session)
    fam_a = await make_family(db_session, name="А")
    fam_b = await make_family(db_session, name="Б")
    token_a, _ = await create_invitation(
        db_session, family=fam_a, created_by=tutor, prefill_full_name=None, prefill_phone=None
    )
    await create_invitation(
        db_session, family=fam_b, created_by=tutor, prefill_full_name=None, prefill_phone=None
    )

    assert (await client.get(f"/api/auth/invitations/{token_a}")).status_code == 200


async def test_archived_family_invitation_invalid(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tutor = await make_tutor(db_session)
    fam = await make_family(db_session, archived=True)
    token, _ = await create_invitation(
        db_session, family=fam, created_by=tutor, prefill_full_name=None, prefill_phone=None
    )

    info = await client.get(f"/api/auth/invitations/{token}")
    accept = await client.post(f"/api/auth/invitations/{token}/accept", json=_accept_body())

    assert info.status_code == 404 and info.json()["error"]["code"] == "invitation_invalid"
    assert accept.status_code == 404 and accept.json()["error"]["code"] == "invitation_invalid"
    assert await _parents_count(db_session) == 0


async def test_consent_required(client: AsyncClient, db_session: AsyncSession) -> None:
    tutor = await make_tutor(db_session)
    fam = await make_family(db_session)
    token, _ = await create_invitation(
        db_session, family=fam, created_by=tutor, prefill_full_name=None, prefill_phone=None
    )

    r = await client.post(f"/api/auth/invitations/{token}/accept", json=_accept_body(consent=False))

    assert r.status_code == 422
    error = r.json()["error"]
    assert error["code"] == "validation_error"
    assert ["body", "consent"] in [f["loc"] for f in error["details"]["fields"]]
    assert await _parents_count(db_session) == 0


async def test_invalid_phone_rejected(client: AsyncClient, db_session: AsyncSession) -> None:
    tutor = await make_tutor(db_session)
    fam = await make_family(db_session)
    token, _ = await create_invitation(
        db_session, family=fam, created_by=tutor, prefill_full_name=None, prefill_phone=None
    )

    r = await client.post(
        f"/api/auth/invitations/{token}/accept", json=_accept_body(phone="not a phone")
    )

    assert r.status_code == 422
    assert ["body", "phone"] in [f["loc"] for f in r.json()["error"]["details"]["fields"]]


async def test_email_taken(client: AsyncClient, db_session: AsyncSession) -> None:
    tutor = await make_tutor(db_session)
    fam = await make_family(db_session)
    await make_parent(db_session, fam, email="anna@mail.ru")
    token, invitation = await create_invitation(
        db_session, family=fam, created_by=tutor, prefill_full_name=None, prefill_phone=None
    )

    r = await client.post(f"/api/auth/invitations/{token}/accept", json=_accept_body())

    assert r.status_code == 409 and r.json()["error"]["code"] == "email_taken"
    await db_session.refresh(invitation)
    assert invitation.used_at is None


async def test_invalid_email_rejected_and_invitation_kept(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tutor = await make_tutor(db_session)
    fam = await make_family(db_session)
    token, invitation = await create_invitation(
        db_session, family=fam, created_by=tutor, prefill_full_name=None, prefill_phone=None
    )

    r = await client.post(
        f"/api/auth/invitations/{token}/accept", json=_accept_body(email="not-an-email")
    )

    assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_email"
    await db_session.refresh(invitation)
    assert invitation.used_at is None


async def test_common_password_rejected_on_accept(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tutor = await make_tutor(db_session)
    fam = await make_family(db_session)
    token, invitation = await create_invitation(
        db_session, family=fam, created_by=tutor, prefill_full_name=None, prefill_phone=None
    )

    r = await client.post(
        f"/api/auth/invitations/{token}/accept", json=_accept_body(password="12345678")
    )

    assert r.status_code == 422 and r.json()["error"]["code"] == "password_too_common"
    await db_session.refresh(invitation)
    assert invitation.used_at is None
    assert await _parents_count(db_session) == 0


async def test_invitation_row_is_locked_when_accepting(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """Приглашение читается под `FOR UPDATE`: параллельный accept ждёт и затем видит used_at."""
    tutor = await make_tutor(db_session)
    fam = await make_family(db_session)
    token, _ = await create_invitation(
        db_session, family=fam, created_by=tutor, prefill_full_name=None, prefill_phone=None
    )
    statements: list[str] = []

    def record(
        conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool
    ) -> None:
        statements.append(statement)

    connection = db_session.sync_session.get_bind()
    event.listen(connection, "before_cursor_execute", record)
    try:
        r = await client.post(f"/api/auth/invitations/{token}/accept", json=_accept_body())
    finally:
        event.remove(connection, "before_cursor_execute", record)

    assert r.status_code == 201
    assert any("FROM invitations" in s and "FOR UPDATE" in s for s in statements)
