import uuid
from datetime import UTC, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field, HttpUrl, StringConstraints, field_validator

from app.auth.passwords import PASSWORD_MAX_LENGTH
from app.auth.schemas import ChildSummary
from app.families.models import EnglishLevel

MIN_BIRTH_YEAR = 1990
MAX_URL_LENGTH = 500

FamilyName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
ChildName = FamilyName
TutorComment = Annotated[str, StringConstraints(max_length=2000)]


def _check_birth_year(year: int) -> int:
    # Верхняя граница — текущий год на момент проверки, а не на момент старта сервера.
    max_year = datetime.now(UTC).year
    if not MIN_BIRTH_YEAR <= year <= max_year:
        raise ValueError(f"Год рождения: от {MIN_BIRTH_YEAR} до {max_year}")
    return year


def _check_url_length(url: HttpUrl) -> HttpUrl:
    if len(str(url)) > MAX_URL_LENGTH:
        raise ValueError(f"Ссылка длиннее {MAX_URL_LENGTH} символов")
    return url


BirthYear = Annotated[int, AfterValidator(_check_birth_year)]
MeetingUrl = Annotated[HttpUrl, AfterValidator(_check_url_length)]


class FamilyCreate(BaseModel):
    name: FamilyName
    tutor_comment: TutorComment | None = None


class FamilyUpdate(BaseModel):
    name: FamilyName | None = None
    tutor_comment: TutorComment | None = None
    archived: bool | None = None

    @field_validator("name")
    @classmethod
    def _name_not_null(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("Название семьи не может быть пустым")
        return value


class InvitationCreate(BaseModel):
    prefill_full_name: str | None = Field(default=None, max_length=200)
    prefill_phone: str | None = Field(default=None, max_length=32)


class ChildCreate(BaseModel):
    full_name: ChildName
    birth_year: BirthYear | None = None
    english_level: EnglishLevel | None = None
    default_meeting_url: MeetingUrl | None = None


class ChildUpdate(BaseModel):
    full_name: ChildName | None = None
    birth_year: BirthYear | None = None
    english_level: EnglishLevel | None = None
    default_meeting_url: MeetingUrl | None = None
    archived: bool | None = None

    @field_validator("full_name")
    @classmethod
    def _full_name_not_null(cls, value: str | None) -> str | None:
        if value is None:
            raise ValueError("Имя ребёнка не может быть пустым")
        return value


class ChildAccountSet(BaseModel):
    username: str = Field(max_length=64)
    password: str = Field(max_length=PASSWORD_MAX_LENGTH)


class CabinetChild(BaseModel):
    id: uuid.UUID
    full_name: str
    birth_year: int | None
    english_level: EnglishLevel | None
    username: str | None


class UserStatusUpdate(BaseModel):
    is_active: bool


class ChildAccount(BaseModel):
    user_id: uuid.UUID
    username: str
    is_active: bool


class ChildDetail(BaseModel):
    id: uuid.UUID
    full_name: str
    birth_year: int | None
    english_level: EnglishLevel | None
    default_meeting_url: str | None
    archived_at: datetime | None
    account: ChildAccount | None


class ParentDetail(BaseModel):
    user_id: uuid.UUID
    full_name: str
    phone: str
    email: str
    is_active: bool
    last_login_at: datetime | None


class PendingInvitation(BaseModel):
    created_at: datetime
    expires_at: datetime


class FamilyDetail(BaseModel):
    id: uuid.UUID
    name: str
    tutor_comment: str | None
    archived_at: datetime | None
    created_at: datetime
    parents: list[ParentDetail]
    children: list[ChildDetail]
    pending_invitation: PendingInvitation | None


class FamilyListItem(BaseModel):
    id: uuid.UUID
    name: str
    archived_at: datetime | None
    parent_names: list[str]
    children: list[ChildSummary]
