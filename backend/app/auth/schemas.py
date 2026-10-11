import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.auth.models import UserRole
from app.auth.passwords import PASSWORD_MAX_LENGTH

FullName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class LoginRequest(BaseModel):
    login: str = Field(min_length=1, max_length=254)
    password: str = Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)


class ChildSummary(BaseModel):
    id: uuid.UUID
    full_name: str


class FamilySummary(BaseModel):
    id: uuid.UUID
    name: str


class MeResponse(BaseModel):
    id: uuid.UUID
    role: UserRole
    display_name: str
    email: str | None
    username: str | None
    family: FamilySummary | None
    children: list[ChildSummary]


class InvitationInfo(BaseModel):
    family_name: str
    expires_at: datetime
    prefill_full_name: str | None
    prefill_phone: str | None


class AcceptInvitationRequest(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=PASSWORD_MAX_LENGTH)
    full_name: FullName
    phone: str = Field(pattern=r"^\+?[0-9\s()-]{6,32}$")
    consent: Literal[True]


class PasswordResetInfo(BaseModel):
    expires_at: datetime
    login: str  # email или username: человек видит, для какого аккаунта меняет пароль


class ResetPasswordRequest(BaseModel):
    password: str = Field(max_length=PASSWORD_MAX_LENGTH)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(max_length=PASSWORD_MAX_LENGTH)
    new_password: str = Field(max_length=PASSWORD_MAX_LENGTH)


class LinkResponse(BaseModel):
    url: str
    expires_at: datetime
