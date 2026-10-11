import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import Enum, ForeignKey, Index, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin, UUIDPrimaryKeyMixin


class LeadStatus(StrEnum):
    NEW = "new"
    CONTACTED = "contacted"
    TRIAL_SCHEDULED = "trial_scheduled"
    CONVERTED = "converted"
    REJECTED = "rejected"


class ContactMethod(StrEnum):
    TELEGRAM = "telegram"
    WHATSAPP = "whatsapp"
    PHONE = "phone"


def _values(enum_class: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_class]


def _lead_status() -> Enum:
    return Enum(LeadStatus, name="lead_status", values_callable=_values)


class Lead(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "leads"
    __table_args__ = (Index("ix_leads_created_at", "created_at"),)  # created_at — из миксина

    parent_name: Mapped[str] = mapped_column(String(100))
    child_name: Mapped[str] = mapped_column(String(100))
    child_age: Mapped[int]
    phone: Mapped[str] = mapped_column(String(16))
    contact_method: Mapped[ContactMethod] = mapped_column(
        Enum(ContactMethod, name="contact_method", values_callable=_values)
    )
    messenger_handle: Mapped[str | None] = mapped_column(String(64))
    goal: Mapped[str | None] = mapped_column(Text)
    preferred_time: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[LeadStatus] = mapped_column(_lead_status(), default=LeadStatus.NEW, index=True)
    reject_reason: Mapped[str | None] = mapped_column(String(500))
    tutor_comment: Mapped[str | None] = mapped_column(Text)
    family_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("families.id", ondelete="SET NULL")
    )
    consent_at: Mapped[datetime]
    utm_source: Mapped[str | None] = mapped_column(String(100))
    utm_medium: Mapped[str | None] = mapped_column(String(100))
    utm_campaign: Mapped[str | None] = mapped_column(String(100))
    notified_at: Mapped[datetime | None]
    anonymized_at: Mapped[datetime | None]

    history: Mapped[list["LeadStatusHistory"]] = relationship(
        order_by="LeadStatusHistory.changed_at", passive_deletes="all"
    )


class LeadStatusHistory(UUIDPrimaryKeyMixin, Base):
    """Неизменяемая строка истории: только changed_at, без updated_at."""

    __tablename__ = "lead_status_history"

    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), index=True
    )
    from_status: Mapped[LeadStatus | None] = mapped_column(_lead_status())
    to_status: Mapped[LeadStatus] = mapped_column(_lead_status())
    comment: Mapped[str | None] = mapped_column(String(500))
    changed_at: Mapped[datetime] = mapped_column(server_default=func.now())
