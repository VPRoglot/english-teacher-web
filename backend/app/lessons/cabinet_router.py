import uuid
from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import AwareDatetime

from app.auth.deps import FamilyMember, ParentUser
from app.core.db import DbSession
from app.core.errors import API_ERROR_RESPONSES
from app.core.tasks import TaskQueueDep
from app.families.scope import FamilyScopeDep
from app.lessons import requests_service, tutor_settings
from app.lessons import service as lessons_service
from app.lessons.admin_router import Now
from app.lessons.schemas import (
    ChangeRequestCreate,
    ChangeRequestForFamily,
    LessonForFamily,
    LessonForFamilyDetail,
    ScheduleSettings,
)

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


@router.post("/lessons/{lesson_id}/change-requests", status_code=201)
async def create_change_request(
    lesson_id: uuid.UUID,
    body: ChangeRequestCreate,
    user: ParentUser,
    scope: FamilyScopeDep,
    session: DbSession,
    queue: TaskQueueDep,
    now: Now,
) -> ChangeRequestForFamily:
    created = await requests_service.create_change_request(
        session, scope.child_ids, lesson_id, body, user=user, now=now
    )
    # Коммит до постановки задачи: worker должен увидеть закоммиченный запрос.
    await session.commit()
    await requests_service.request_change_notification(queue, created.id)
    return created


@router.delete("/change-requests/{request_id}")
async def withdraw_change_request(
    request_id: uuid.UUID, _: ParentUser, scope: FamilyScopeDep, session: DbSession, now: Now
) -> ChangeRequestForFamily:
    return await requests_service.withdraw_change_request(
        session, scope.child_ids, request_id, now=now
    )
