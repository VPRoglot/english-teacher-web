import uuid

from pydantic import BaseModel, Field

from app.auth.models import UserRole
from app.auth.passwords import PASSWORD_MAX_LENGTH


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
