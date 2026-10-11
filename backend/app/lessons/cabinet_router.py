from fastapi import APIRouter

from app.auth.deps import FamilyMember
from app.core.db import DbSession
from app.core.errors import API_ERROR_RESPONSES
from app.lessons import tutor_settings
from app.lessons.schemas import ScheduleSettings

router = APIRouter(prefix="/me", tags=["cabinet"], responses=API_ERROR_RESPONSES)


@router.get("/schedule-settings")
async def get_schedule_settings(_: FamilyMember, session: DbSession) -> ScheduleSettings:
    return ScheduleSettings.model_validate(await tutor_settings.get_tutor_settings(session))
