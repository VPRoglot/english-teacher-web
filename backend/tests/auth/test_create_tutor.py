import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User, UserRole
from app.auth.passwords import verify_password
from app.auth.service import create_tutor
from app.core.errors import Conflict, ValidationFailed


async def test_create_tutor_normalizes_email_and_hashes(db_session: AsyncSession) -> None:
    user = await create_tutor(db_session, email="  Tutor@Mail.RU ", password="secret-pass")
    assert user.role is UserRole.TUTOR
    assert user.email == "tutor@mail.ru"
    assert verify_password(user.password_hash, "secret-pass")


async def test_second_tutor_conflict(db_session: AsyncSession) -> None:
    await create_tutor(db_session, email="a@b.ru", password="secret-pass")
    with pytest.raises(Conflict) as e:
        await create_tutor(db_session, email="c@d.ru", password="secret-pass")
    assert e.value.code == "tutor_already_exists"


async def test_email_taken_conflict(db_session: AsyncSession) -> None:
    db_session.add(User(role=UserRole.PARENT, email="a@b.ru", password_hash="h"))
    await db_session.flush()
    with pytest.raises(Conflict) as e:
        await create_tutor(db_session, email="A@B.ru", password="secret-pass")
    assert e.value.code == "email_taken"


async def test_short_password_rejected(db_session: AsyncSession) -> None:
    with pytest.raises(ValidationFailed) as e:
        await create_tutor(db_session, email="a@b.ru", password="short")
    assert e.value.code == "password_too_short"


async def test_invalid_email_rejected(db_session: AsyncSession) -> None:
    with pytest.raises(ValidationFailed) as e:
        await create_tutor(db_session, email="not-an-email", password="secret-pass")
    assert e.value.code == "invalid_email"
