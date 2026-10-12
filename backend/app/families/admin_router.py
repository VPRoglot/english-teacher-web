import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response

from app.auth import service as auth_service
from app.auth.deps import TutorUser
from app.auth.schemas import LinkResponse
from app.auth.sessions import SessionStoreDep
from app.core.db import DbSession
from app.core.errors import API_ERROR_RESPONSES
from app.families import service as families_service
from app.families.schemas import (
    ChildAccountSet,
    ChildCreate,
    ChildDetail,
    ChildUpdate,
    FamilyCreate,
    FamilyDetail,
    FamilyListItem,
    FamilyUpdate,
    InvitationCreate,
    UserStatusUpdate,
)
from app.lessons.admin_router import Now
from app.lessons.series_service import archive_child_series

router = APIRouter(prefix="/admin", tags=["admin"], responses=API_ERROR_RESPONSES)


@router.get("/families")
async def list_families(
    _: TutorUser,
    session: DbSession,
    q: Annotated[str | None, Query(max_length=200)] = None,
    archived: bool = False,
) -> list[FamilyListItem]:
    return await families_service.list_families(session, q=q, archived=archived)


@router.post("/families", status_code=201)
async def create_family(body: FamilyCreate, _: TutorUser, session: DbSession) -> FamilyDetail:
    family = await families_service.create_family(session, body)
    return await families_service.get_family_detail(session, family.id)


@router.get("/families/{family_id}")
async def get_family(family_id: uuid.UUID, _: TutorUser, session: DbSession) -> FamilyDetail:
    return await families_service.get_family_detail(session, family_id)


@router.patch("/families/{family_id}")
async def update_family(
    family_id: uuid.UUID,
    body: FamilyUpdate,
    _: TutorUser,
    session: DbSession,
    store: SessionStoreDep,
    now: Now,
) -> FamilyDetail:
    family = await families_service.get_family(session, family_id)
    was_active = family is not None and family.archived_at is None
    detail = await families_service.update_family(session, family_id, body, sessions=store)
    if body.archived is True and was_active:
        child_ids = await families_service.list_child_ids(session, family_id)
        await archive_child_series(session, child_ids, now=now)
    return detail


@router.post("/families/{family_id}/invitations", status_code=201)
async def create_family_invitation(
    family_id: uuid.UUID,
    request: Request,
    tutor: TutorUser,
    session: DbSession,
    body: InvitationCreate | None = None,
) -> LinkResponse:
    body = body or InvitationCreate()
    family = await families_service.get_active_family(session, family_id)
    token, invitation = await auth_service.create_invitation(
        session,
        family=family,
        created_by=tutor,
        prefill_full_name=body.prefill_full_name,
        prefill_phone=body.prefill_phone,
    )
    url = auth_service.build_link(request.app.state.settings, "invite", token)
    return LinkResponse(url=url, expires_at=invitation.expires_at)


@router.post("/families/{family_id}/children", status_code=201)
async def add_child(
    family_id: uuid.UUID, body: ChildCreate, _: TutorUser, session: DbSession
) -> ChildDetail:
    return await families_service.add_child(session, family_id, body)


@router.patch("/children/{child_id}")
async def update_child(
    child_id: uuid.UUID,
    body: ChildUpdate,
    _: TutorUser,
    session: DbSession,
    store: SessionStoreDep,
    now: Now,
) -> ChildDetail:
    was_active = (await families_service.get_child(session, child_id)).archived_at is None
    detail = await families_service.update_child(session, child_id, body, sessions=store)
    if body.archived is True and was_active:
        await archive_child_series(session, [child_id], now=now)
    return detail


@router.post("/children/{child_id}/account")
async def set_child_account_admin(
    child_id: uuid.UUID,
    body: ChildAccountSet,
    _: TutorUser,
    session: DbSession,
    store: SessionStoreDep,
) -> ChildDetail:
    child = await families_service.get_child(session, child_id)
    child = await families_service.set_child_account(session, child, body, sessions=store)
    return await families_service.get_child_detail(session, child)


@router.post("/users/{user_id}/reset-link", status_code=201)
async def create_reset_link(
    user_id: uuid.UUID, request: Request, tutor: TutorUser, session: DbSession
) -> LinkResponse:
    user = await families_service.get_family_user(session, user_id)
    token, reset = await auth_service.create_password_reset(session, user=user, created_by=tutor)
    url = auth_service.build_link(request.app.state.settings, "reset", token)
    return LinkResponse(url=url, expires_at=reset.expires_at)


@router.patch("/users/{user_id}", status_code=204, response_class=Response)
async def update_user_status(
    user_id: uuid.UUID,
    body: UserStatusUpdate,
    _: TutorUser,
    session: DbSession,
    store: SessionStoreDep,
) -> Response:
    user = await families_service.get_family_user(session, user_id)
    await families_service.set_user_active(session, user, body.is_active, sessions=store)
    return Response(status_code=204)
