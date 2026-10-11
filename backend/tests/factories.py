from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import User, UserRole
from app.auth.passwords import hash_password
from app.families.models import Child, Family, ParentProfile

TEST_PASSWORD = "Correct-Horse-7"


async def make_tutor(
    session: AsyncSession, *, email: str = "tutor@example.com", password: str = TEST_PASSWORD
) -> User:
    user = User(role=UserRole.TUTOR, email=email, password_hash=hash_password(password))
    session.add(user)
    await session.flush()
    return user


async def make_family(
    session: AsyncSession, *, name: str = "Ивановы", archived: bool = False
) -> Family:
    family = Family(name=name, archived_at=datetime.now(UTC) if archived else None)
    session.add(family)
    await session.flush()
    return family


async def make_parent(
    session: AsyncSession,
    family: Family,
    *,
    email: str = "parent@example.com",
    password: str = TEST_PASSWORD,
    full_name: str = "Анна Иванова",
    phone: str = "+79990000000",
    is_active: bool = True,
) -> User:
    user = User(
        role=UserRole.PARENT,
        email=email,
        password_hash=hash_password(password),
        is_active=is_active,
    )
    session.add(user)
    await session.flush()
    session.add(
        ParentProfile(
            user_id=user.id,
            family_id=family.id,
            full_name=full_name,
            phone=phone,
            consent_at=datetime.now(UTC),
        )
    )
    await session.flush()
    return user


async def make_child(
    session: AsyncSession,
    family: Family,
    *,
    full_name: str = "Маша",
    username: str | None = None,
    password: str = TEST_PASSWORD,
    archived: bool = False,
) -> Child:
    now = datetime.now(UTC)
    user_id = None
    if username is not None:
        user = User(
            role=UserRole.CHILD,
            username=username,
            password_hash=hash_password(password),
            is_active=not archived,
        )
        session.add(user)
        await session.flush()
        user_id = user.id
    child = Child(
        family_id=family.id,
        user_id=user_id,
        full_name=full_name,
        archived_at=now if archived else None,
    )
    session.add(child)
    await session.flush()
    return child
