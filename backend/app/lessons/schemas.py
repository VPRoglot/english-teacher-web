import uuid
from datetime import date, datetime, time
from typing import Annotated, Literal
from zoneinfo import available_timezones

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    field_validator,
)
from pydantic_core import PydanticCustomError

from app.families.schemas import MeetingUrl
from app.lessons.models import LessonKind, LessonStatus
from app.lessons.recurrence import InvalidRule, normalize_rule

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
    # Есть запрос на перенос или отмену (в любом статусе): такое занятие не удаляется.
    has_requests: bool


class LessonSaved(AdminLessonDetail):
    warnings: list[OverlapWarning]


class LessonCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    child_id: uuid.UUID
    starts_at: AwareDatetime
    duration_min: DurationMin
    meeting_url: MeetingUrl | None = None


class TrialCreate(BaseModel):
    """Пробное занятие заявки: длительность по умолчанию 30 минут."""

    model_config = ConfigDict(extra="forbid")

    starts_at: AwareDatetime
    duration_min: DurationMin = 30
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


def _normalized_rule(value: str) -> str:
    try:
        return normalize_rule(value)
    except InvalidRule as exc:
        raise PydanticCustomError("invalid_rrule", str(exc)) from exc


def _check_local_time(value: time) -> time:
    if value.tzinfo is not None:
        raise PydanticCustomError("local_time", "Время задаётся без часового пояса")
    if value.second or value.microsecond:
        raise PydanticCustomError("local_time", "Время задаётся с точностью до минуты")
    return value


# Каноническая запись правила; неподдерживаемое правило — 422 на поле `rrule`.
RRule = Annotated[str, Field(max_length=200), AfterValidator(_normalized_rule)]
# Местное время начала: часы и минуты, без секунд и без пояса.
LocalTime = Annotated[time, AfterValidator(_check_local_time)]


class SeriesCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    child_id: uuid.UUID
    rrule: RRule
    local_start_time: LocalTime
    duration_min: DurationMin
    meeting_url: MeetingUrl | None = None
    starts_on: date
    ends_on: date | None = None

    @field_validator("ends_on")
    @classmethod
    def _ends_after_start(cls, value: date | None, info: ValidationInfo) -> date | None:
        starts_on = info.data.get("starts_on")
        if value is not None and starts_on is not None and value < starts_on:
            raise PydanticCustomError("range", "Окончание не может быть раньше начала")
        return value


class SeriesUpdate(BaseModel):
    """Частичная правка: `meeting_url` и `ends_on` можно сбросить в `null`, остальные поля — нет."""

    model_config = ConfigDict(extra="forbid")

    rrule: RRule | None = None
    local_start_time: LocalTime | None = None
    duration_min: DurationMin | None = None
    meeting_url: MeetingUrl | None = None
    ends_on: date | None = None

    @field_validator("rrule", "local_start_time", "duration_min")
    @classmethod
    def _not_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("Поле не может быть пустым")
        return value


class SeriesDetail(BaseModel):
    id: uuid.UUID
    child_id: uuid.UUID
    child_name: str
    rrule: str
    local_start_time: time
    duration_min: int
    meeting_url: str | None
    starts_on: date
    ends_on: date | None
    archived_at: datetime | None


class SeriesSaved(BaseModel):
    series: SeriesDetail
    lessons_created: int
    # Правка серии: сколько занятий изменено на месте и сколько удалено, потому что их даты
    # ушли из расписания. При создании серии оба равны 0.
    lessons_updated: int
    lessons_removed: int
    warnings: list[OverlapWarning]


class LessonForFamily(BaseModel):
    """Занятие в кабинете семьи.

    Отдельный класс, а не наследник админских схем: поле, добавленное в админскую схему,
    не попадёт в ответ семье само.
    """

    id: uuid.UUID
    child_id: uuid.UUID
    child_name: str
    starts_at: datetime
    duration_min: int
    status: LessonStatus
    # Эффективная ссылка: своя у занятия, иначе ссылка ребёнка.
    join_url: str | None
    has_shared_note: bool


class LessonForFamilyDetail(LessonForFamily):
    # Общая заметка (Markdown); `None`, если она пуста.
    shared_note: str | None
