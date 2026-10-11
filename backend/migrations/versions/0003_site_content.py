"""site_content

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-11 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Замороженные заглушки блоков: миграция не импортирует app.*, чтобы не зависеть от будущих схем.
STUBS: dict[str, dict[str, object]] = {
    "hero": {
        "name": "Имя Фамилия",
        "title": "Английский для детей и подростков",
        "subtitle": (
            "Индивидуальные онлайн-занятия: разговорная практика, школьная программа, "
            "подготовка к ОГЭ и ЕГЭ"
        ),
        "photo_media_id": None,
        "cta_text": "Записаться на пробное",
    },
    "about": {
        "text": "Расскажите здесь о себе: опыт, подход к занятиям, чем вы отличаетесь.",
        "photo_media_id": None,
        "credentials": [],
    },
    "services": {
        "items": [
            {
                "title": "Пробное занятие",
                "description": "Знакомство, определение уровня и целей",
                "duration_min": 30,
                "price_rub": 0,
                "format": "Онлайн",
            }
        ]
    },
    "reviews": {"items": []},
    "faq": {
        "items": [
            {
                "question": "Как проходит пробное занятие?",
                "answer": "Знакомимся, определяем уровень и цели, обсуждаем расписание.",
            }
        ]
    },
    "contacts": {
        "telegram": None,
        "whatsapp": None,
        "phone": None,
        "email": None,
        "working_hours_text": None,
    },
}


def upgrade() -> None:
    site_blocks = op.create_table(
        "site_blocks",
        sa.Column("key", sa.String(length=32), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "key IN ('hero','about','services','reviews','faq','contacts')",
            name=op.f("ck_site_blocks_key_known"),
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_site_blocks")),
    )
    op.create_table(
        "media",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("s3_key", sa.String(length=200), nullable=False),
        sa.Column("content_type", sa.String(length=50), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media")),
        sa.UniqueConstraint("s3_key", name=op.f("uq_media_s3_key")),
    )
    op.bulk_insert(site_blocks, [{"key": key, "data": data} for key, data in STUBS.items()])


def downgrade() -> None:
    op.drop_table("media")
    op.drop_table("site_blocks")
