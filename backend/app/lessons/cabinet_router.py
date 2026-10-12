import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import AwareDatetime

from app.auth.deps import FamilyMember
from app.core.db import DbSession
from app.core.errors import API_ERROR_RESPONSES
from app.families.scope import FamilyScopeDep
from app.lessons import service as lessons_service
from app.lessons import tutor_settings
from app.lessons.schemas import LessonForFamily, LessonForFamilyDetail, ScheduleSettings

router = APIRouter(prefix="/me", tags=["cabinet"], responses=API_ERROR_RESPONSES)


@router.get("/schedule-settings")
async def get_schedule_settings(_: FamilyMember, session: DbSession) -> ScheduleSettings:
    return ScheduleSettings.model_validate(await tutor_settings.get_tutor_settings(session))


@router.get("/lessons")
async def list_my_lessons(
    from_: Annotated[AwareDatetime, Query(alias="from")],
    to: AwareDatetime,
    scope: FamilyScopeDep,
    session: DbSession,
    child_id: uuid.UUID | None = None,
) -> list[LessonForFamily]:
    lessons_service.check_range(from_, to)
    return await lessons_service.list_family_lessons(
        session, scope.child_ids, start=from_, end=to, child_id=child_id
    )


@router.get("/lessons/{lesson_id}")
async def get_my_lesson(
    lesson_id: uuid.UUID, scope: FamilyScopeDep, session: DbSession
) -> LessonForFamilyDetail:
    return await lessons_service.get_family_lesson(session, scope.child_ids, lesson_id)
