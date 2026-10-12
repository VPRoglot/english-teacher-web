import uuid
from collections.abc import Collection
from datetime import UTC, datetime

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.identity import normalize_username
from app.auth.models import Invitation, User, UserRole
from app.auth.passwords import CHILD_PASSWORD_MIN_LENGTH, hash_password, validate_password
from app.auth.schemas import ChildSummary
from app.auth.sessions import SessionStore
from app.core.errors import Conflict, NotFound
from app.families.models import Child, Family, ParentProfile
from app.families.schemas import (
    CabinetChild,
    ChildAccount,
    ChildAccountSet,
    ChildCreate,
    ChildDetail,
    ChildUpdate,
    FamilyCreate,
    FamilyDetail,
    FamilyListItem,
    FamilyUpdate,
    ParentDetail,
    PendingInvitation,
)


async def get_parent_profile(session: AsyncSession, user_id: uuid.UUID) -> ParentProfile | None:
    return await session.get(ParentProfile, user_id)


async def get_family(session: AsyncSession, family_id: uuid.UUID) -> Family | None:
    return await session.get(Family, family_id)


async def list_active_children(session: AsyncSession, family_id: uuid.UUID) -> list[Child]:
    result = await session.scalars(
        select(Child)
        .where(Child.family_id == family_id, Child.archived_at.is_(None))
        .order_by(Child.full_name)
    )
    return list(result)


async def get_child_by_user(session: AsyncSession, user_id: uuid.UUID) -> Child | None:
    return await session.scalar(select(Child).where(Child.user_id == user_id))


async def is_member_access_blocked(session: AsyncSession, user: User) -> bool:
    """Доступ закрыт архивом: родитель архивной семьи, архивный ученик или ученик архивной семьи.

    Ручная блокировка (`users.is_active`) проверяется отдельно; архив её не меняет.
    Репетитора проверка не касается.
    """
    if user.role is UserRole.PARENT:
        stmt = (
            select(Family.archived_at.is_not(None))
            .join(ParentProfile, ParentProfile.family_id == Family.id)
            .where(ParentProfile.user_id == user.id)
        )
    elif user.role is UserRole.CHILD:
        stmt = (
            select(or_(Child.archived_at.is_not(None), Family.archived_at.is_not(None)))
            .join(Family, Family.id == Child.family_id)
            .where(Child.user_id == user.id)
        )
    else:
        return False
    return bool(await session.scalar(stmt))


async def list_cabinet_children(
    session: AsyncSession, child_ids: Collection[uuid.UUID]
) -> list[CabinetChild]:
    """Дети для кабинета семьи: только перечисленные id, с логином и статусом учётки (если есть)."""
    if not child_ids:
        return []
    return [
        CabinetChild(
            id=child.id,
            full_name=child.full_name,
            birth_year=child.birth_year,
            english_level=child.english_level,
            username=username,
            is_active=is_active,
        )
        for child, username, is_active in await session.execute(
            select(Child, User.username, User.is_active)
            .outerjoin(User, User.id == Child.user_id)
            .where(Child.id.in_(child_ids))
            .order_by(Child.full_name, Child.id)
        )
    ]


def _like_pattern(q: str) -> str:
    """Подстрока для ILIKE: `\\`, `%` и `_` из запроса ищутся как обычные символы."""
    escaped = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _family_archived() -> Conflict:
    return Conflict("Семья в архиве", code="family_archived")


def _child_detail(child: Child, user: User | None) -> ChildDetail:
    account = None
    if user is not None:
        if user.username is None:  # CHECK users.username_required гарантирует логин у ребёнка
            raise RuntimeError(f"У ребёнка {user.id} нет логина")
        account = ChildAccount(user_id=user.id, username=user.username, is_active=user.is_active)
    return ChildDetail(
        id=child.id,
        full_name=child.full_name,
        birth_year=child.birth_year,
        english_level=child.english_level,
        default_meeting_url=child.default_meeting_url,
        archived_at=child.archived_at,
        account=account,
    )


async def list_families(
    session: AsyncSession, *, q: str | None, archived: bool
) -> list[FamilyListItem]:
    stmt = select(Family).where(
        Family.archived_at.is_not(None) if archived else Family.archived_at.is_(None)
    )
    if q and q.strip():
        pattern = _like_pattern(q.strip())
        stmt = stmt.where(
            or_(
                Family.name.ilike(pattern, escape="\\"),
                exists().where(
                    ParentProfile.family_id == Family.id,
                    ParentProfile.full_name.ilike(pattern, escape="\\"),
                ),
                exists().where(
                    Child.family_id == Family.id, Child.full_name.ilike(pattern, escape="\\")
                ),
            )
        )
    families = list(await session.scalars(stmt.order_by(Family.name, Family.id)))
    if not families:
        return []

    ids = [f.id for f in families]
    parent_names: dict[uuid.UUID, list[str]] = {f.id: [] for f in families}
    for family_id, full_name in await session.execute(
        select(ParentProfile.family_id, ParentProfile.full_name)
        .where(ParentProfile.family_id.in_(ids))
        .order_by(ParentProfile.full_name)
    ):
        parent_names[family_id].append(full_name)
    children: dict[uuid.UUID, list[ChildSummary]] = {f.id: [] for f in families}
    for child in await session.scalars(
        select(Child)
        .where(Child.family_id.in_(ids), Child.archived_at.is_(None))
        .order_by(Child.full_name)
    ):
        children[child.family_id].append(ChildSummary(id=child.id, full_name=child.full_name))

    return [
        FamilyListItem(
            id=f.id,
            name=f.name,
            archived_at=f.archived_at,
            parent_names=parent_names[f.id],
            children=children[f.id],
        )
        for f in families
    ]


async def create_family(session: AsyncSession, data: FamilyCreate) -> Family:
    family = Family(name=data.name, tutor_comment=data.tutor_comment)
    session.add(family)
    await session.flush()
    return family


async def _require_family(session: AsyncSession, family_id: uuid.UUID) -> Family:
    family = await get_family(session, family_id)
    if family is None:
        raise NotFound("Семья не найдена", code="family_not_found")
    return family


async def get_active_family(session: AsyncSession, family_id: uuid.UUID) -> Family:
    """Семья для изменений: несуществующая — `NotFound`, архивная — `Conflict`."""
    family = await _require_family(session, family_id)
    if family.archived_at is not None:
        raise _family_archived()
    return family


async def get_family_detail(session: AsyncSession, family_id: uuid.UUID) -> FamilyDetail:
    family = await _require_family(session, family_id)

    parents = [
        ParentDetail(
            user_id=user.id,
            full_name=profile.full_name,
            phone=profile.phone,
            email=user.email or "",
            is_active=user.is_active,
            last_login_at=user.last_login_at,
        )
        for profile, user in await session.execute(
            select(ParentProfile, User)
            .join(User, User.id == ParentProfile.user_id)
            .where(ParentProfile.family_id == family_id)
            .order_by(ParentProfile.full_name)
        )
    ]
    children = [
        _child_detail(child, user)
        for child, user in await session.execute(
            select(Child, User)
            .outerjoin(User, User.id == Child.user_id)
            .where(Child.family_id == family_id)
            .order_by(Child.archived_at.is_not(None), Child.full_name, Child.id)
        )
    ]
    invitation = await session.scalar(
        select(Invitation)
        .where(
            Invitation.family_id == family_id,
            Invitation.used_at.is_(None),
            Invitation.revoked_at.is_(None),
            Invitation.expires_at > datetime.now(UTC),
        )
        .order_by(Invitation.created_at.desc())
        .limit(1)
    )
    return FamilyDetail(
        id=family.id,
        name=family.name,
        tutor_comment=family.tutor_comment,
        archived_at=family.archived_at,
        created_at=family.created_at,
        parents=parents,
        children=children,
        pending_invitation=(
            PendingInvitation(created_at=invitation.created_at, expires_at=invitation.expires_at)
            if invitation
            else None
        ),
    )


async def _family_member_ids(session: AsyncSession, family_id: uuid.UUID) -> list[uuid.UUID]:
    """Учётки семьи: родители и все дети с логином (включая архивных)."""
    parents = await session.scalars(
        select(ParentProfile.user_id).where(ParentProfile.family_id == family_id)
    )
    kids = await session.scalars(
        select(Child.user_id).where(Child.family_id == family_id, Child.user_id.is_not(None))
    )
    return [*parents, *(k for k in kids if k is not None)]


async def update_family(
    session: AsyncSession, family_id: uuid.UUID, data: FamilyUpdate, *, sessions: SessionStore
) -> FamilyDetail:
    """Архив закрывает доступ участникам (см. `is_member_access_blocked`), не трогая `is_active`:
    ручная блокировка репетитора переживает архивирование и возврат из архива."""
    family = await _require_family(session, family_id)
    if data.name is not None:
        family.name = data.name
    if "tutor_comment" in data.model_fields_set:
        family.tutor_comment = data.tutor_comment

    logged_out: list[uuid.UUID] = []
    if data.archived is True and family.archived_at is None:
        family.archived_at = datetime.now(UTC)
        logged_out = await _family_member_ids(session, family_id)
    elif data.archived is False and family.archived_at is not None:
        family.archived_at = None
    await session.flush()
    for user_id in logged_out:
        await sessions.delete_all_for_user(user_id)
    return await get_family_detail(session, family_id)


async def add_child(session: AsyncSession, family_id: uuid.UUID, data: ChildCreate) -> ChildDetail:
    family = await get_active_family(session, family_id)
    child = Child(
        family_id=family.id,
        full_name=data.full_name,
        birth_year=data.birth_year,
        english_level=data.english_level,
        default_meeting_url=str(data.default_meeting_url) if data.default_meeting_url else None,
    )
    session.add(child)
    await session.flush()
    return _child_detail(child, None)


async def get_child(session: AsyncSession, child_id: uuid.UUID) -> Child:
    child = await session.get(Child, child_id)
    if child is None:
        raise NotFound("Ученик не найден", code="child_not_found")
    return child


async def get_active_child(session: AsyncSession, child_id: uuid.UUID) -> Child:
    """Ребёнок для новых занятий: нет — `NotFound`, он или его семья в архиве — `Conflict`."""
    child = await get_child(session, child_id)
    if child.archived_at is not None:
        raise Conflict("Ученик в архиве", code="child_archived")
    await get_active_family(session, child.family_id)
    return child


async def get_child_detail(session: AsyncSession, child: Child) -> ChildDetail:
    user = await session.get(User, child.user_id) if child.user_id else None
    return _child_detail(child, user)


async def update_child(
    session: AsyncSession, child_id: uuid.UUID, data: ChildUpdate, *, sessions: SessionStore
) -> ChildDetail:
    child = await get_child(session, child_id)
    fields = data.model_fields_set
    if data.full_name is not None:
        child.full_name = data.full_name
    if "birth_year" in fields:
        child.birth_year = data.birth_year
    if "english_level" in fields:
        child.english_level = data.english_level
    if "default_meeting_url" in fields:
        url = data.default_meeting_url
        child.default_meeting_url = str(url) if url else None

    # Как и архив семьи, архив ученика не трогает `is_active` его учётки.
    deactivated: uuid.UUID | None = None
    if data.archived is True and child.archived_at is None:
        child.archived_at = datetime.now(UTC)
        deactivated = child.user_id
    elif data.archived is False and child.archived_at is not None:
        await get_active_family(session, child.family_id)
        child.archived_at = None
    await session.flush()
    if deactivated:
        await sessions.delete_all_for_user(deactivated)
    return await get_child_detail(session, child)


async def set_child_account(
    session: AsyncSession, child: Child, data: ChildAccountSet, *, sessions: SessionStore
) -> Child:
    """Создаёт учётку ребёнка или меняет её логин и пароль (старые сессии завершаются)."""
    if child.archived_at is not None:
        raise Conflict("Ученик в архиве", code="child_archived")
    await get_active_family(session, child.family_id)

    username = normalize_username(data.username)
    taken = await session.scalar(
        select(exists().where(User.username == username, User.id != child.user_id))
    )
    if taken:
        raise Conflict("Логин уже занят", code="username_taken")
    validate_password(data.password, min_length=CHILD_PASSWORD_MIN_LENGTH)
    password_hash = hash_password(data.password)

    user = await session.get(User, child.user_id) if child.user_id else None
    if user is None:
        user = User(role=UserRole.CHILD, username=username, password_hash=password_hash)
        session.add(user)
        await session.flush()
        child.user_id = user.id
        await session.flush()
        return child

    user.username = username
    user.password_hash = password_hash
    await session.flush()
    await sessions.delete_all_for_user(user.id)
    return child


async def get_family_user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    if user is None or user.role not in (UserRole.PARENT, UserRole.CHILD):
        raise NotFound("Пользователь не найден", code="user_not_found")
    return user


async def set_user_active(
    session: AsyncSession, user: User, is_active: bool, *, sessions: SessionStore
) -> None:
    """Ручная блокировка. Снятие блокировки с участника архива доступ не открывает:
    его закрывает архив (`is_member_access_blocked`)."""
    user.is_active = is_active
    await session.flush()
    if not is_active:
        await sessions.delete_all_for_user(user.id)
