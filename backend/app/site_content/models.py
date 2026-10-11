from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import CheckConstraint, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, UUIDPrimaryKeyMixin


class BlockKey(StrEnum):
    HERO = "hero"
    ABOUT = "about"
    SERVICES = "services"
    REVIEWS = "reviews"
    FAQ = "faq"
    CONTACTS = "contacts"


_KNOWN_KEYS = ",".join(f"'{key.value}'" for key in BlockKey)


class SiteBlock(Base):
    __tablename__ = "site_blocks"
    __table_args__ = (CheckConstraint(f"key IN ({_KNOWN_KEYS})", name="key_known"),)

    key: Mapped[str] = mapped_column(String(32), primary_key=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class Media(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "media"

    s3_key: Mapped[str] = mapped_column(String(200), unique=True)
    content_type: Mapped[str] = mapped_column(String(50))
    size_bytes: Mapped[int]
    width: Mapped[int]
    height: Mapped[int]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
