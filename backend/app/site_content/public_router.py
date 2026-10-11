from fastapi import APIRouter, Request

from app.core.config import Settings
from app.core.db import DbSession
from app.core.errors import API_ERROR_RESPONSES
from app.site_content import service as site_service
from app.site_content.schemas import PublicSite

router = APIRouter(prefix="/public", tags=["public"], responses=API_ERROR_RESPONSES)


@router.get("/site")
async def get_public_site(request: Request, session: DbSession) -> PublicSite:
    settings: Settings = request.app.state.settings
    return await site_service.get_public_site(session, settings)
