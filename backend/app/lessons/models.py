import uuid
from datetime import date, datetime, time
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    Enum,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    false,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPrimaryKeyMixin


class LessonKind(StrEnum):
    REGULAR = "regular"
    TRIAL = "trial"


class LessonStatus(StrEnum):
    SCHEDULED = "scheduled"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    CANCELLED_LATE = "cancelled_late"
    NO_SHOW = "no_show"


def _values(enum_class: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_class]


class TutorSettings(TimestampMixin, Base):
    """Настройки репетитора: единственная строка `id = 1`, её создаёт миграция."""

    __tablename__ = "tutor_settings"
    __table_args__ = (
        CheckConstraint("id = 1", name="singleton"),
        CheckConstraint("cancel_policy_hours BETWEEN 0 AND 168", name="cancel_policy_hours_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=False)
    timezone: Mapped[str] = mapped_column(String(64), server_default="Europe/Moscow")
    cancel_policy_hours: Mapped[int] = mapped_column(server_default="24")


class LessonSeries(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Регулярное правило занятий ребёнка; занятия из него создаются до `generated_through`."""

    __tablename__ = "lesson_series"
    __table_args__ = (
        CheckConstraint("ends_on IS NULL OR ends_on >= starts_on", name="ends_after_start"),
        CheckConstraint("duration_min BETWEEN 15 AND 240", name="duration_range"),
    )

    child_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("children.id", ondelete="CASCADE"), index=True
    )
    rrule: Mapped[str] = mapped_column(String(200))
    local_start_time: Mapped[time]
    duration_min: Mapped[int]
    meeting_url: Mapped[str | None] = mapped_column(String(500))
    starts_on: Mapped[date]
    ends_on: Mapped[date | None]
    # Фронтир генерации: занятия создаются только для местных дат после него.
    generated_through: Mapped[date | None]
    archived_at: Mapped[datetime | None]


class Lesson(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "lessons"
    __table_args__ = (
        CheckConstraint("(child_id IS NULL) <> (lead_id IS NULL)", name="exactly_one_owner"),
        CheckConstraint("(kind = 'trial') = (lead_id IS NOT NULL)", name="trial_has_lead"),
        CheckConstraint("series_id IS NULL OR child_id IS NOT NULL", name="series_has_child"),
        CheckConstraint("duration_min BETWEEN 15 AND 240", name="duration_range"),
        UniqueConstraint("series_id", "starts_at", name="uq_lessons_series_id_starts_at"),
    )

    series_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lesson_series.id", ondelete="CASCADE")
    )
    child_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("children.id", ondelete="CASCADE"), index=True
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[LessonKind] = mapped_column(
        Enum(LessonKind, name="lesson_kind", values_callable=_values)
    )
    starts_at: Mapped[datetime] = mapped_column(index=True)
    duration_min: Mapped[int]
    meeting_url: Mapped[str | None] = mapped_column(String(500))
    is_detached: Mapped[bool] = mapped_column(default=False, server_default=false())
    status: Mapped[LessonStatus] = mapped_column(
        Enum(LessonStatus, name="lesson_status", values_callable=_values),
        default=LessonStatus.SCHEDULED,
        server_default=text("'scheduled'"),
    )


class LessonNote(TimestampMixin, Base):
    """Заметки к занятию: `shared_text` видит семья, `private_text` — только репетитор."""

    __tablename__ = "lesson_notes"

    lesson_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"), primary_key=True
    )
    shared_text: Mapped[str] = mapped_column(Text, server_default="")
    private_text: Mapped[str] = mapped_column(Text, server_default="")
