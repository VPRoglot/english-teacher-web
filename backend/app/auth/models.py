from datetime import datetime
from enum import StrEnum

from sqlalchemy import CheckConstraint, Enum, Index, String, text, true
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, TimestampMixin, UUIDPrimaryKeyMixin


class UserRole(StrEnum):
    TUTOR = "tutor"
    PARENT = "parent"
    CHILD = "child"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("role = 'child' OR email IS NOT NULL", name="email_required"),
        CheckConstraint("role <> 'child' OR username IS NOT NULL", name="username_required"),
        CheckConstraint("email = lower(email)", name="email_lowercase"),
        CheckConstraint("username = lower(username)", name="username_lowercase"),
        # Репетитор в системе ровно один.
        Index(
            "uq_users_single_tutor", "role", unique=True, postgresql_where=text("role = 'tutor'")
        ),
    )

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", values_callable=lambda e: [m.value for m in e])
    )
    email: Mapped[str | None] = mapped_column(String(254), unique=True)
    username: Mapped[str | None] = mapped_column(String(32), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(server_default=true())
    last_login_at: Mapped[datetime | None]
