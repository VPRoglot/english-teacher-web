import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends

from app.auth.deps import FamilyMember
from app.auth.models import UserRole
from app.core.db import DbSession
from app.core.errors import NotAuthenticated
from app.families import service


@dataclass(frozen=True)
class FamilyScope:
    """Границы данных участника семьи: данные других семей и архивных детей недоступны."""

    family_id: uuid.UUID
    child_ids: frozenset[uuid.UUID]


async def get_family_scope(user: FamilyMember, session: DbSession) -> FamilyScope:
    # `get_current_user` уже отсекает участников архива; повтор — защита для прямых вызовов.
    if await service.is_member_access_blocked(session, user):
        raise NotAuthenticated()
    if user.role is UserRole.PARENT:
        profile = await service.get_parent_profile(session, user.id)
        if profile is None:
            raise NotAuthenticated()
        children = await service.list_active_children(session, profile.family_id)
        return FamilyScope(profile.family_id, frozenset(c.id for c in children))

    child = await service.get_child_by_user(session, user.id)
    if child is None:
        raise NotAuthenticated()
    return FamilyScope(child.family_id, frozenset({child.id}))


FamilyScopeDep = Annotated[FamilyScope, Depends(get_family_scope)]
