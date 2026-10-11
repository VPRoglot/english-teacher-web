from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator
from pydantic_core import PydanticCustomError

from app.core.phone import PHONE_ERROR, normalize_phone
from app.leads.models import ContactMethod

CONSENT_ERROR = "Нужно согласие на обработку персональных данных"

_Text100 = Annotated[str, StringConstraints(max_length=100)]


class LeadCreate(BaseModel):
    """Заявка на пробное занятие из публичной формы."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    parent_name: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    child_name: Annotated[str, StringConstraints(min_length=1, max_length=100)]
    child_age: Annotated[int, Field(ge=3, le=18)]
    phone: str
    contact_method: ContactMethod
    messenger_handle: Annotated[str, StringConstraints(max_length=64)] | None = None
    goal: Annotated[str, StringConstraints(max_length=1000)] | None = None
    preferred_time: Annotated[str, StringConstraints(max_length=200)] | None = None
    consent: Literal[True]
    utm_source: _Text100 | None = None
    utm_medium: _Text100 | None = None
    utm_campaign: _Text100 | None = None
    captcha_token: Annotated[str, StringConstraints(max_length=5000)] | None = None
    # Honeypot: скрытое поле формы, человек его не заполняет.
    website: Annotated[str, StringConstraints(max_length=200)] | None = None

    @field_validator(
        "messenger_handle",
        "goal",
        "preferred_time",
        "utm_source",
        "utm_medium",
        "utm_campaign",
        mode="before",
    )
    @classmethod
    def _blank_to_none(cls, value: Any) -> Any:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("phone", mode="after")
    @classmethod
    def _normalize_phone(cls, value: str) -> str:
        try:
            return normalize_phone(value)
        except ValueError:
            raise PydanticCustomError("phone_invalid", PHONE_ERROR) from None

    @field_validator("consent", mode="before")
    @classmethod
    def _require_consent(cls, value: Any) -> Any:
        if value is not True:
            raise PydanticCustomError("consent_required", CONSENT_ERROR)
        return value


class LeadAccepted(BaseModel):
    accepted: Literal[True] = True
