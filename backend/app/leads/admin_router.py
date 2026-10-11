import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.auth.deps import TutorUser
from app.core.db import DbSession
from app.core.errors import API_ERROR_RESPONSES
from app.leads import service as leads_service
from app.leads.models import LeadStatus
from app.leads.schemas import LeadConvert, LeadConverted, LeadDetail, LeadList, LeadUpdate

router = APIRouter(prefix="/admin", tags=["admin"], responses=API_ERROR_RESPONSES)


@router.get("/leads")
async def list_leads(
    _: TutorUser,
    session: DbSession,
    status: LeadStatus | None = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LeadList:
    return await leads_service.list_leads(session, status=status, q=q, limit=limit, offset=offset)


@router.get("/leads/{lead_id}")
async def get_lead(lead_id: uuid.UUID, _: TutorUser, session: DbSession) -> LeadDetail:
    return await leads_service.get_lead_detail(session, lead_id)


@router.patch("/leads/{lead_id}")
async def update_lead(
    lead_id: uuid.UUID, body: LeadUpdate, _: TutorUser, session: DbSession
) -> LeadDetail:
    return await leads_service.update_lead(session, lead_id, body)


@router.post("/leads/{lead_id}/convert", status_code=201)
async def convert_lead(
    lead_id: uuid.UUID,
    body: LeadConvert,
    request: Request,
    tutor: TutorUser,
    session: DbSession,
) -> LeadConverted:
    return await leads_service.convert_lead(
        session, lead_id, body, tutor=tutor, settings=request.app.state.settings
    )
