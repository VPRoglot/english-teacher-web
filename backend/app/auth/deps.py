from collections.abc import Awaitable, Callable
from typing import Annotated

from fastapi import Depends, Request

from app.auth.models import User, UserRole
from app.auth.sessions import SESSION_COOKIE, SessionStoreDep
from app.core.db import DbSession
from app.core.errors import NotAuthenticated, NotFound
from app.families import service as families_service


async def get_current_user(request: Request, session: DbSession, store: SessionStoreDep) -> User:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise NotAuthenticated()
    data = await store.get(token)
    if data is None:
        raise NotAuthenticated()

    user = await session.get(User, data.user_id)
    # Роль в сессии должна совпадать с ролью в БД: сессия не переживает смену роли.
    # Архив семьи или ученика закрывает доступ так же, как ручная блокировка.
    if (
        user is None
        or not user.is_active
        or user.role != data.role
        or await families_service.is_member_access_blocked(session, user)
    ):
        await store.delete(token)
        raise NotAuthenticated()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_roles(*roles: UserRole) -> Callable[..., Awaitable[User]]:
    """Зависимость: пользователь с одной из ролей; остальным — 404, чтобы не раскрывать раздел."""

    async def dependency(user: CurrentUser) -> User:
        if user.role not in roles:
            raise NotFound()
        return user

    return dependency


TutorUser = Annotated[User, Depends(require_roles(UserRole.TUTOR))]
ParentUser = Annotated[User, Depends(require_roles(UserRole.PARENT))]
FamilyMember = Annotated[User, Depends(require_roles(UserRole.PARENT, UserRole.CHILD))]
