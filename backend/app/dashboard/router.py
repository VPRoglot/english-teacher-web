from fastapi import APIRouter

from app.auth.deps import TutorUser
from app.core.db import DbSession
from app.core.errors import API_ERROR_RESPONSES
from app.dashboard import service
from app.dashboard.schemas import DashboardResponse
from app.lessons.admin_router import Now

router = APIRouter(prefix="/admin", tags=["admin"], responses=API_ERROR_RESPONSES)


@router.get("/dashboard")
async def get_dashboard(_: TutorUser, session: DbSession, now: Now) -> DashboardResponse:
    return await service.get_dashboard(session, now=now)
