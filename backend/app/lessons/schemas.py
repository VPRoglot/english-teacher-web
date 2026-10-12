import uuid
from datetime import datetime
from typing import Annotated, Literal
from zoneinfo import available_timezones

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)
from pydantic_core import PydanticCustomError

from app.families.schemas import MeetingUrl
from app.lessons.models import LessonKind, LessonStatus

TIMEZONE_ERROR = "Неизвестный часовой пояс"


class ScheduleSettings(BaseModel):
    """Настройки расписания, которые нужны и репетитору, и кабинету семьи."""

    model_config = ConfigDict(from_attributes=True)

    timezone: str
    cancel_policy_hours: int


class TutorSettingsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timezone: Annotated[str, StringConstraints(max_length=64)]
    cancel_policy_hours: Annotated[int, Field(ge=0, le=168)]

    @field_validator("timezone")
    @classmethod
    def _known_timezone(cls, value: str) -> str:
        if value not in available_timezones():
            raise PydanticCustomError("unknown_timezone", TIMEZONE_ERROR)
        return value


DurationMin = Annotated[int, Field(ge=15, le=240)]
NoteText = Annotated[str, StringConstraints(max_length=20000)]


class OverlapWarning(BaseModel):
    code: Literal["overlap"]
    message: str
    lesson_id: uuid.UUID
    starts_at: datetime


class LessonStudent(BaseModel):
    """Кому принадлежит занятие: ученику или (пробное) заявке — тогда `family_*` пусты."""

    child_id: uuid.UUID | None
    lead_id: uuid.UUID | None
    name: str
    family_id: uuid.UUID | None
    family_name: str | None


class AdminLessonItem(BaseModel):
    id: uuid.UUID
    kind: LessonKind
    status: LessonStatus
    starts_at: datetime
    duration_min: int
    series_id: uuid.UUID | None
    is_detached: bool
    # Собственная ссылка занятия; `join_url` — эффективная (своя, иначе ссылка ученика).
    meeting_url: str | None
    join_url: str | None
    student: LessonStudent
    has_notes: bool


class LessonNotes(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    shared_text: str
    private_text: str


class AdminLessonDetail(AdminLessonItem):
    notes: LessonNotes
    created_at: datetime


class LessonSaved(AdminLessonDetail):
    warnings: list[OverlapWarning]


class LessonCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    child_id: uuid.UUID
    starts_at: AwareDatetime
    duration_min: DurationMin
    meeting_url: MeetingUrl | None = None


class LessonUpdate(BaseModel):
    """Частичная правка: `meeting_url: null` очищает ссылку, остальные поля не принимают null."""

    model_config = ConfigDict(extra="forbid")

    starts_at: AwareDatetime | None = None
    duration_min: DurationMin | None = None
    meeting_url: MeetingUrl | None = None
    status: LessonStatus | None = None

    @field_validator("starts_at", "duration_min", "status")
    @classmethod
    def _not_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("Поле не может быть пустым")
        return value


class LessonNotesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shared_text: NoteText
    private_text: NoteText
