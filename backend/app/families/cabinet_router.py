import uuid

from fastapi import APIRouter

from app.auth.deps import ParentUser
from app.auth.sessions import SessionStoreDep
from app.core.db import DbSession
from app.core.errors import API_ERROR_RESPONSES, NotFound
from app.families import service as families_service
from app.families.schemas import CabinetChild, ChildAccountSet
from app.families.scope import FamilyScopeDep

router = APIRouter(prefix="/me", tags=["cabinet"], responses=API_ERROR_RESPONSES)


@router.get("/children")
async def list_my_children(scope: FamilyScopeDep, session: DbSession) -> list[CabinetChild]:
    return await families_service.list_cabinet_children(session, scope.child_ids)


@router.post("/children/{child_id}/account")
async def set_my_child_account(
    child_id: uuid.UUID,
    body: ChildAccountSet,
    _: ParentUser,
    scope: FamilyScopeDep,
    session: DbSession,
    store: SessionStoreDep,
) -> CabinetChild:
    # Чужой и несуществующий ребёнок неразличимы: в обоих случаях один и тот же 404.
    if child_id not in scope.child_ids:
        raise NotFound()
    child = await families_service.get_child(session, child_id)
    await families_service.set_child_account(session, child, body, sessions=store)
    (cabinet_child,) = await families_service.list_cabinet_children(session, {child_id})
    return cabinet_child
