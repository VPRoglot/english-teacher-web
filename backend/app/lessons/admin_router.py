import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Response
from pydantic import AwareDatetime

from app.auth.deps import TutorUser
from app.core.db import DbSession
from app.core.errors import API_ERROR_RESPONSES
from app.lessons import requests_service, series_service, tutor_settings
from app.lessons import service as lessons_service
from app.lessons.models import ChangeRequestStatus
from app.lessons.schemas import (
    AdminLessonDetail,
    AdminLessonItem,
    ChangeRequestAdminItem,
    ChangeRequestApprove,
    ChangeRequestReject,
    ChangeRequestResolved,
    LessonCreate,
    LessonNotes,
    LessonNotesUpdate,
    LessonSaved,
    LessonUpdate,
    ScheduleSettings,
    SeriesCreate,
    SeriesDetail,
    SeriesSaved,
    SeriesUpdate,
    TrialCreate,
    TutorSettingsUpdate,
)

router = APIRouter(prefix="/admin", tags=["admin"], responses=API_ERROR_RESPONSES)


def get_now() -> datetime:
    """Текущий момент; зависимость, чтобы тесты могли его подменить."""
    return datetime.now(UTC)


Now = Annotated[datetime, Depends(get_now)]


@router.get("/settings")
async def get_tutor_settings_admin(_: TutorUser, session: DbSession) -> ScheduleSettings:
    return ScheduleSettings.model_validate(await tutor_settings.get_tutor_settings(session))


@router.put("/settings")
async def update_tutor_settings_admin(
    body: TutorSettingsUpdate, _: TutorUser, session: DbSession
) -> ScheduleSettings:
    updated = await tutor_settings.update_tutor_settings(session, body, now=datetime.now(UTC))
    return ScheduleSettings.model_validate(updated)


@router.get("/lessons")
async def list_lessons(
    from_: Annotated[AwareDatetime, Query(alias="from")],
    to: AwareDatetime,
    _: TutorUser,
    session: DbSession,
    child_id: uuid.UUID | None = None,
) -> list[AdminLessonItem]:
    lessons_service.check_range(from_, to)
    return await lessons_service.list_admin_lessons(session, start=from_, end=to, child_id=child_id)


@router.post("/lessons", status_code=201)
async def create_lesson(body: LessonCreate, _: TutorUser, session: DbSession) -> LessonSaved:
    return await lessons_service.create_lesson(session, body, now=datetime.now(UTC))


@router.get("/lessons/{lesson_id}")
async def get_lesson(lesson_id: uuid.UUID, _: TutorUser, session: DbSession) -> AdminLessonDetail:
    return await lessons_service.get_admin_lesson(session, lesson_id)


@router.patch("/lessons/{lesson_id}")
async def update_lesson(
    lesson_id: uuid.UUID, body: LessonUpdate, _: TutorUser, session: DbSession
) -> LessonSaved:
    return await lessons_service.update_lesson(session, lesson_id, body, now=datetime.now(UTC))


@router.delete("/lessons/{lesson_id}", status_code=204, response_class=Response)
async def delete_lesson(lesson_id: uuid.UUID, _: TutorUser, session: DbSession) -> Response:
    await lessons_service.delete_lesson(session, lesson_id, now=datetime.now(UTC))
    return Response(status_code=204)


@router.put("/lessons/{lesson_id}/notes")
async def save_lesson_notes(
    lesson_id: uuid.UUID, body: LessonNotesUpdate, _: TutorUser, session: DbSession
) -> LessonNotes:
    return await lessons_service.save_notes(session, lesson_id, body)


@router.get("/series")
async def list_series(
    _: TutorUser,
    session: DbSession,
    child_id: uuid.UUID | None = None,
    archived: bool = False,
) -> list[SeriesDetail]:
    return await series_service.list_series(session, child_id=child_id, include_archived=archived)


@router.post("/series", status_code=201)
async def create_series(
    body: SeriesCreate, _: TutorUser, session: DbSession, now: Now
) -> SeriesSaved:
    return await series_service.create_series(session, body, now=now)


@router.patch("/series/{series_id}")
async def update_series(
    series_id: uuid.UUID,
    body: SeriesUpdate,
    scope: Literal["this_and_following"],
    from_: Annotated[date, Query(alias="from")],
    _: TutorUser,
    session: DbSession,
    now: Now,
) -> SeriesSaved:
    # `scope` обязателен: других режимов правки нет, но параметр закрепляет смысл `from`.
    return await series_service.update_series(session, series_id, body, from_day=from_, now=now)


@router.delete("/series/{series_id}", status_code=204, response_class=Response)
async def archive_series(
    series_id: uuid.UUID, _: TutorUser, session: DbSession, now: Now
) -> Response:
    await series_service.archive_series(session, series_id, now=now)
    return Response(status_code=204)


@router.post("/leads/{lead_id}/trial", status_code=201)
async def schedule_trial(
    lead_id: uuid.UUID, body: TrialCreate, _: TutorUser, session: DbSession, now: Now
) -> LessonSaved:
    return await lessons_service.schedule_trial(session, lead_id, body, now=now)


@router.get("/leads/{lead_id}/trial-lessons")
async def list_trial_lessons(
    lead_id: uuid.UUID, _: TutorUser, session: DbSession
) -> list[AdminLessonItem]:
    return await lessons_service.list_trial_lessons(session, lead_id)


@router.get("/change-requests")
async def list_change_requests(
    _: TutorUser,
    session: DbSession,
    status: ChangeRequestStatus | None = None,
) -> list[ChangeRequestAdminItem]:
    """Очередь запросов; без `status` — все статусы.

    Порядок без фильтра: сначала ждущие (старейшие первыми), затем рассмотренные по
    `resolved_at` от новых к старым.
    """
    return await requests_service.list_admin_requests(session, status=status)


@router.post("/change-requests/{request_id}/approve")
async def approve_change_request(
    request_id: uuid.UUID,
    body: ChangeRequestApprove,
    _: TutorUser,
    session: DbSession,
    now: Now,
) -> ChangeRequestResolved:
    return await requests_service.approve_change_request(session, request_id, body, now=now)


@router.post("/change-requests/{request_id}/reject")
async def reject_change_request(
    request_id: uuid.UUID,
    body: ChangeRequestReject,
    _: TutorUser,
    session: DbSession,
    now: Now,
) -> ChangeRequestResolved:
    return await requests_service.reject_change_request(session, request_id, body, now=now)
