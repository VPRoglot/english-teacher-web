from typing import Annotated
from zoneinfo import available_timezones

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from pydantic_core import PydanticCustomError

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
