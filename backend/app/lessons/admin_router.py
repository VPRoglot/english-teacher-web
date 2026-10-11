from datetime import UTC, datetime

from fastapi import APIRouter

from app.auth.deps import TutorUser
from app.core.db import DbSession
from app.core.errors import API_ERROR_RESPONSES
from app.lessons import tutor_settings
from app.lessons.schemas import ScheduleSettings, TutorSettingsUpdate

router = APIRouter(prefix="/admin", tags=["admin"], responses=API_ERROR_RESPONSES)


@router.get("/settings")
async def get_tutor_settings_admin(_: TutorUser, session: DbSession) -> ScheduleSettings:
    return ScheduleSettings.model_validate(await tutor_settings.get_tutor_settings(session))


@router.put("/settings")
async def update_tutor_settings_admin(
    body: TutorSettingsUpdate, _: TutorUser, session: DbSession
) -> ScheduleSettings:
    updated = await tutor_settings.update_tutor_settings(session, body, now=datetime.now(UTC))
    return ScheduleSettings.model_validate(updated)
