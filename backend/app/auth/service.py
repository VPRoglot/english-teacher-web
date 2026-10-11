import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import exists, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.identity import normalize_email
from app.auth.models import Invitation, PasswordReset, User, UserRole
from app.auth.passwords import (
    CHILD_PASSWORD_MIN_LENGTH,
    PASSWORD_MIN_LENGTH,
    hash_password,
    password_needs_rehash,
    validate_password,
    verify_password,
)
from app.auth.schemas import (
    AcceptInvitationRequest,
    ChildSummary,
    FamilySummary,
    InvitationInfo,
    MeResponse,
    PasswordResetInfo,
)
from app.auth.sessions import SessionStore
from app.auth.tokens import INVITATION_TTL, RESET_TTL, new_token, sha256_hex
from app.core.config import Settings
from app.core.errors import AppError, Conflict, NotFound, ValidationFailed
from app.families import service as families_service
from app.families.models import Family, ParentProfile

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


def build_link(settings: Settings, path: str, token: str) -> str:
    """Ссылка для человека; `path` — `invite` или `reset`."""
    return f"{settings.public_base_url}/{path}/{token}"


def _invitation_invalid() -> NotFound:
    return NotFound("Ссылка-приглашение недействительна или устарела", code="invitation_invalid")


def _reset_invalid() -> NotFound:
    return NotFound("Ссылка для смены пароля недействительна или устарела", code="reset_invalid")


async def _find_valid_invitation(
    session: AsyncSession, token: str, *, lock: bool = False
) -> Invitation:
    stmt = select(Invitation).where(Invitation.token_hash == sha256_hex(token))
    if lock:
        # Строка блокируется до конца транзакции: параллельный accept ждёт и затем видит used_at.
        # populate_existing — состояние перечитывается, даже если объект уже в сессии.
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    invitation = await session.scalar(stmt)
    if (
        invitation is None
        or invitation.used_at is not None
        or invitation.revoked_at is not None
        or invitation.expires_at <= datetime.now(UTC)
    ):
        raise _invitation_invalid()
    family = await families_service.get_family(session, invitation.family_id)
    if family is None or family.archived_at is not None:
        raise _invitation_invalid()
    return invitation


async def create_invitation(
    session: AsyncSession,
    *,
    family: Family,
    created_by: User,
    prefill_full_name: str | None,
    prefill_phone: str | None,
) -> tuple[str, Invitation]:
    """Новое приглашение в семью; прежние неиспользованные приглашения семьи отзываются."""
    now = datetime.now(UTC)
    await session.execute(
        update(Invitation)
        .where(
            Invitation.family_id == family.id,
            Invitation.used_at.is_(None),
            Invitation.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    token, token_hash = new_token()
    invitation = Invitation(
        token_hash=token_hash,
        family_id=family.id,
        prefill_full_name=prefill_full_name,
        prefill_phone=prefill_phone,
        expires_at=now + INVITATION_TTL,
        created_by=created_by.id,
    )
    session.add(invitation)
    await session.flush()
    return token, invitation


async def get_valid_invitation(session: AsyncSession, token: str) -> Invitation:
    return await _find_valid_invitation(session, token)


async def build_invitation_info(session: AsyncSession, invitation: Invitation) -> InvitationInfo:
    family = await families_service.get_family(session, invitation.family_id)
    if family is None:  # FK гарантирует существование
        raise RuntimeError(f"Семья {invitation.family_id} не найдена")
    return InvitationInfo(
        family_name=family.name,
        expires_at=invitation.expires_at,
        prefill_full_name=invitation.prefill_full_name,
        prefill_phone=invitation.prefill_phone,
    )


async def accept_invitation(
    session: AsyncSession, *, token: str, data: AcceptInvitationRequest
) -> User:
    """Создаёт родителя по приглашению. Коммит и сессия входа — на вызывающей стороне."""
    invitation = await _find_valid_invitation(session, token, lock=True)

    email = normalize_email(data.email)
    if await session.scalar(select(exists().where(User.email == email))):
        raise Conflict("Email уже используется", code="email_taken")
    validate_password(data.password)

    now = datetime.now(UTC)
    user = User(role=UserRole.PARENT, email=email, password_hash=hash_password(data.password))
    session.add(user)
    await session.flush()
    session.add(
        ParentProfile(
            user_id=user.id,
            family_id=invitation.family_id,
            full_name=data.full_name,
            phone=data.phone,
            consent_at=now,
        )
    )
    invitation.used_at = now
    await session.flush()
    return user


async def _find_valid_password_reset(
    session: AsyncSession, token: str, *, lock: bool = False
) -> PasswordReset:
    stmt = select(PasswordReset).where(PasswordReset.token_hash == sha256_hex(token))
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    reset = await session.scalar(stmt)
    if reset is None or reset.used_at is not None or reset.expires_at <= datetime.now(UTC):
        raise _reset_invalid()
    return reset


async def create_password_reset(
    session: AsyncSession, *, user: User, created_by: User
) -> tuple[str, PasswordReset]:
    """Новая ссылка сброса; прежние неиспользованные ссылки этого пользователя гасятся."""
    now = datetime.now(UTC)
    await session.execute(
        update(PasswordReset)
        .where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None))
        .values(used_at=now)
    )
    token, token_hash = new_token()
    reset = PasswordReset(
        token_hash=token_hash,
        user_id=user.id,
        expires_at=now + RESET_TTL,
        created_by=created_by.id,
    )
    session.add(reset)
    await session.flush()
    return token, reset


async def get_valid_password_reset(session: AsyncSession, token: str) -> PasswordReset:
    return await _find_valid_password_reset(session, token)


async def _get_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None:  # FK гарантирует существование
        raise RuntimeError(f"Пользователь {user_id} не найден")
    return user


async def build_password_reset_info(
    session: AsyncSession, reset: PasswordReset
) -> PasswordResetInfo:
    user = await _get_user(session, reset.user_id)
    return PasswordResetInfo(expires_at=reset.expires_at, login=user.email or user.username or "")


def _min_password_length(user: User) -> int:
    return CHILD_PASSWORD_MIN_LENGTH if user.role is UserRole.CHILD else PASSWORD_MIN_LENGTH


async def reset_password(
    session: AsyncSession, *, token: str, password: str, sessions: SessionStore
) -> User:
    """Задаёт новый пароль по ссылке и завершает все сессии пользователя."""
    reset = await _find_valid_password_reset(session, token, lock=True)
    user = await _get_user(session, reset.user_id)
    validate_password(password, min_length=_min_password_length(user))

    user.password_hash = hash_password(password)
    reset.used_at = datetime.now(UTC)
    await session.flush()
    await sessions.delete_all_for_user(user.id)
    return user


async def change_password(
    session: AsyncSession,
    *,
    user: User,
    current_password: str,
    new_password: str,
    sessions: SessionStore,
) -> None:
    """Меняет пароль и завершает все сессии; новую сессию выдаёт вызывающая сторона."""
    if not verify_password(user.password_hash, current_password):
        raise ValidationFailed(
            "Текущий пароль указан неверно",
            code="invalid_current_password",
            details={"field": "current_password"},
        )
    validate_password(new_password, min_length=_min_password_length(user))

    user.password_hash = hash_password(new_password)
    await session.flush()
    await sessions.delete_all_for_user(user.id)
