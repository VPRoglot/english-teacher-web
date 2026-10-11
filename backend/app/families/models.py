import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPrimaryKeyMixin


class EnglishLevel(StrEnum):
    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"


class Family(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "families"

    name: Mapped[str] = mapped_column(String(200))
    tutor_comment: Mapped[str | None] = mapped_column(Text)
    archived_at: Mapped[datetime | None]


class ParentProfile(TimestampMixin, Base):
    __tablename__ = "parent_profiles"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), index=True
    )
    full_name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str] = mapped_column(String(32))
    consent_at: Mapped[datetime]


class Child(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "children"
    __table_args__ = (CheckConstraint("birth_year BETWEEN 1990 AND 2100", name="birth_year_range"),)

    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("families.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), unique=True
    )
    full_name: Mapped[str] = mapped_column(String(200))
    birth_year: Mapped[int | None]
    english_level: Mapped[EnglishLevel | None] = mapped_column(
        Enum(EnglishLevel, name="english_level", values_callable=lambda e: [m.value for m in e])
    )
    default_meeting_url: Mapped[str | None] = mapped_column(String(500))
    archived_at: Mapped[datetime | None]
