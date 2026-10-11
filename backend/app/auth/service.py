from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.identity import normalize_email
from app.auth.models import User, UserRole
from app.auth.passwords import hash_password, validate_password
from app.core.errors import Conflict


async def create_tutor(session: AsyncSession, *, email: str, password: str) -> User:
    """Создаёт единственного репетитора. Коммит — на вызывающей стороне."""
    email = normalize_email(email)
    validate_password(password)

    if await session.scalar(select(exists().where(User.role == UserRole.TUTOR))):
        raise Conflict("Репетитор уже создан", code="tutor_already_exists")
    if await session.scalar(select(exists().where(User.email == email))):
        raise Conflict("Email уже используется", code="email_taken")

    user = User(role=UserRole.TUTOR, email=email, password_hash=hash_password(password))
    session.add(user)
    await session.flush()
    return user
