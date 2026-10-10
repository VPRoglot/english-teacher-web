import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User, UserRole


async def _flush_expecting(session: AsyncSession, user: User, constraint: str) -> None:
    session.add(user)
    with pytest.raises(IntegrityError, match=constraint):
        await session.flush()


async def test_child_without_username_rejected(db_session: AsyncSession) -> None:
    user = User(role=UserRole.CHILD, password_hash="h")
    await _flush_expecting(db_session, user, "ck_users_username_required")


async def test_parent_without_email_rejected(db_session: AsyncSession) -> None:
    user = User(role=UserRole.PARENT, password_hash="h")
    await _flush_expecting(db_session, user, "ck_users_email_required")


async def test_uppercase_email_rejected_by_db(db_session: AsyncSession) -> None:
    user = User(role=UserRole.PARENT, email="A@b.ru", password_hash="h")
    await _flush_expecting(db_session, user, "ck_users_email_lowercase")


async def test_uppercase_username_rejected_by_db(db_session: AsyncSession) -> None:
    user = User(role=UserRole.CHILD, username="Masha", password_hash="h")
    await _flush_expecting(db_session, user, "ck_users_username_lowercase")


async def test_second_tutor_rejected_by_db(db_session: AsyncSession) -> None:
    db_session.add(User(role=UserRole.TUTOR, email="a@b.ru", password_hash="h"))
    await db_session.flush()
    second = User(role=UserRole.TUTOR, email="c@d.ru", password_hash="h")
    await _flush_expecting(db_session, second, "uq_users_single_tutor")


async def test_duplicate_email_rejected_by_db(db_session: AsyncSession) -> None:
    db_session.add(User(role=UserRole.PARENT, email="p@b.ru", password_hash="h"))
    await db_session.flush()
    dup = User(role=UserRole.PARENT, email="p@b.ru", password_hash="h")
    await _flush_expecting(db_session, dup, "uq_users_email")


async def test_user_gets_uuid7_and_timestamps(db_session: AsyncSession) -> None:
    user = User(role=UserRole.PARENT, email="p@b.ru", password_hash="h")
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    assert user.id.version == 7
    assert user.created_at.tzinfo is not None
    assert user.is_active is True
    assert user.last_login_at is None
