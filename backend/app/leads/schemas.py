import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationInfo,
    field_validator,
)
from pydantic_core import PydanticCustomError

from app.auth.schemas import LinkResponse
from app.core.phone import PHONE_ERROR, normalize_phone
from app.families.schemas import ChildCreate, FamilyName
from app.leads.models import ContactMethod, LeadStatus

CONSENT_ERROR = "Нужно согласие на обработку персональных данных"
REJECT_REASON_ERROR = "Укажите причину отказа"

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


class LeadHistoryItem(BaseModel):
    from_status: LeadStatus | None
    to_status: LeadStatus
    comment: str | None
    changed_at: datetime


class LeadListItem(BaseModel):
    id: uuid.UUID
    created_at: datetime
    parent_name: str
    child_name: str
    child_age: int
    phone: str
    contact_method: ContactMethod
    messenger_handle: str | None
    status: LeadStatus


class LeadList(BaseModel):
    items: list[LeadListItem]
    total: int


class LeadDetail(BaseModel):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    parent_name: str
    child_name: str
    child_age: int
    phone: str
    contact_method: ContactMethod
    messenger_handle: str | None
    goal: str | None
    preferred_time: str | None
    status: LeadStatus
    reject_reason: str | None
    tutor_comment: str | None
    family_id: uuid.UUID | None
    consent_at: datetime
    utm_source: str | None
    utm_medium: str | None
    utm_campaign: str | None
    notified_at: datetime | None
    history: list[LeadHistoryItem]


class LeadUpdate(BaseModel):
    """Ручное изменение заявки: статус (`contacted`/`rejected`), причина отказа, заметка."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # Только статусы, которые репетитор выставляет вручную; остальные — побочный эффект.
    status: Literal["contacted", "rejected"] | None = None
    comment: Annotated[str, StringConstraints(max_length=500)] | None = None
    # validate_default: правило «отказ требует причину» проверяется и когда поле не передано.
    reject_reason: Annotated[str, StringConstraints(min_length=1, max_length=500)] | None = Field(
        default=None, validate_default=True
    )
    tutor_comment: Annotated[str, StringConstraints(max_length=2000)] | None = None

    @field_validator("reject_reason", mode="after")
    @classmethod
    def _reason_matches_status(cls, value: str | None, info: ValidationInfo) -> str | None:
        if "status" not in info.data:  # статус сам не прошёл проверку — его ошибка уже есть
            return value
        rejected = info.data["status"] == "rejected"
        if rejected != (value is not None):
            raise PydanticCustomError("reject_reason_mismatch", REJECT_REASON_ERROR)
        return value


class LeadConvertParent(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    full_name: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    phone: str

    @field_validator("phone", mode="after")
    @classmethod
    def _normalize_phone(cls, value: str) -> str:
        try:
            return normalize_phone(value)
        except ValueError:
            raise PydanticCustomError("phone_invalid", PHONE_ERROR) from None


class LeadConvert(BaseModel):
    family_name: FamilyName
    child: ChildCreate
    parent: LeadConvertParent


class LeadConverted(BaseModel):
    family_id: uuid.UUID
    invitation: LinkResponse
