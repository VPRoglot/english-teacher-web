import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.identity import normalize_email
from app.auth.models import User, UserRole
from app.auth.passwords import (
    hash_password,
    password_needs_rehash,
    validate_password,
    verify_password,
)
from app.auth.schemas import ChildSummary, FamilySummary, MeResponse
from app.core.errors import AppError, Conflict
from app.families import service as families_service

# Хеш случайной строки: проверка пароля несуществующего пользователя занимает столько же времени,
# сколько настоящая, и по времени ответа нельзя отличить «нет такого логина».
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(16))


class InvalidCredentials(AppError):  # noqa: N818 (как NotFound и др.: имя без суффикса Error)
    """Один ответ для неверного пароля, неизвестного логина и неактивного пользователя."""

    status_code = 401
    code = "invalid_credentials"
    message = "Неверный логин или пароль"


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


def normalize_login(login: str) -> str:
    """Email и username хранятся в нижнем регистре; вход допускает любой регистр и пробелы."""
    return login.strip().lower()


async def authenticate(session: AsyncSession, *, login: str, password: str) -> User | None:
    """Пользователь по логину (email или username) и паролю; иначе `None`.

    Пароль проверяется всегда — и для несуществующего, и для неактивного пользователя.
    """
    login = normalize_login(login)
    user = await session.scalar(
        select(User).where(or_(User.email == login, User.username == login))
    )
    if user is None:
        verify_password(DUMMY_PASSWORD_HASH, password)
        return None
    if not verify_password(user.password_hash, password) or not user.is_active:
        return None

    user.last_login_at = datetime.now(UTC)
    if password_needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)
    await session.flush()
    return user


async def _family_summary(session: AsyncSession, family_id: uuid.UUID) -> FamilySummary:
    family = await families_service.get_family(session, family_id)
    if family is None:  # FK гарантирует существование; None — рассинхронизация данных
        raise RuntimeError(f"Семья {family_id} не найдена")
    return FamilySummary(id=family.id, name=family.name)


async def build_me(session: AsyncSession, user: User) -> MeResponse:
    family: FamilySummary | None = None
    children: list[ChildSummary] = []
    display_name = user.email or ""

    if user.role is UserRole.PARENT:
        profile = await families_service.get_parent_profile(session, user.id)
        if profile is None:
            raise RuntimeError(f"У родителя {user.id} нет профиля")
        display_name = profile.full_name
        family = await _family_summary(session, profile.family_id)
        children = [
            ChildSummary(id=c.id, full_name=c.full_name)
            for c in await families_service.list_active_children(session, profile.family_id)
        ]
    elif user.role is UserRole.CHILD:
        child = await families_service.get_child_by_user(session, user.id)
        if child is None:
            raise RuntimeError(f"У ребёнка {user.id} нет карточки")
        display_name = child.full_name
        family = await _family_summary(session, child.family_id)
        children = [ChildSummary(id=child.id, full_name=child.full_name)]

    return MeResponse(
        id=user.id,
        role=user.role,
        display_name=display_name,
        email=user.email,
        username=user.username,
        family=family,
        children=children,
    )
