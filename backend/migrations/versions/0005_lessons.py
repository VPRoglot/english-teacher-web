"""lessons

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-12 10:00:00.000000
"""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Типы создаются явно, а колонки их не создают (так же, как в 0004).
lesson_kind = postgresql.ENUM("regular", "trial", name="lesson_kind", create_type=False)
lesson_status = postgresql.ENUM(
    "scheduled",
    "completed",
    "cancelled",
    "cancelled_late",
    "no_show",
    name="lesson_status",
    create_type=False,
)


def _timestamps() -> list[sa.Column[datetime]]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    ]


def upgrade() -> None:
    bind = op.get_bind()
    lesson_kind.create(bind, checkfirst=True)
    lesson_status.create(bind, checkfirst=True)
    tutor_settings = op.create_table(
        "tutor_settings",
        sa.Column("id", sa.Integer(), autoincrement=False, nullable=False),
        sa.Column("timezone", sa.String(length=64), server_default="Europe/Moscow", nullable=False),
        sa.Column("cancel_policy_hours", sa.Integer(), server_default="24", nullable=False),
        *_timestamps(),
        sa.CheckConstraint("id = 1", name=op.f("ck_tutor_settings_singleton")),
        sa.CheckConstraint(
            "cancel_policy_hours BETWEEN 0 AND 168",
            name=op.f("ck_tutor_settings_cancel_policy_hours_range"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tutor_settings")),
    )
    op.bulk_insert(tutor_settings, [{"id": 1}])
    op.create_table(
        "lesson_series",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("child_id", sa.Uuid(), nullable=False),
        sa.Column("rrule", sa.String(length=200), nullable=False),
        sa.Column("local_start_time", sa.Time(), nullable=False),
        sa.Column("duration_min", sa.Integer(), nullable=False),
        sa.Column("meeting_url", sa.String(length=500), nullable=True),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("generated_through", sa.Date(), nullable=True),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "ends_on IS NULL OR ends_on >= starts_on",
            name=op.f("ck_lesson_series_ends_after_start"),
        ),
        sa.CheckConstraint(
            "duration_min BETWEEN 15 AND 240", name=op.f("ck_lesson_series_duration_range")
        ),
        sa.ForeignKeyConstraint(
            ["child_id"],
            ["children.id"],
            name=op.f("fk_lesson_series_child_id_children"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lesson_series")),
    )
    op.create_index(op.f("ix_lesson_series_child_id"), "lesson_series", ["child_id"], unique=False)
    op.create_table(
        "lessons",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("series_id", sa.Uuid(), nullable=True),
        sa.Column("child_id", sa.Uuid(), nullable=True),
        sa.Column("lead_id", sa.Uuid(), nullable=True),
        sa.Column("kind", lesson_kind, nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_min", sa.Integer(), nullable=False),
        sa.Column("meeting_url", sa.String(length=500), nullable=True),
        sa.Column("is_detached", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("status", lesson_status, server_default=sa.text("'scheduled'"), nullable=False),
        *_timestamps(),
        sa.CheckConstraint(
            "(child_id IS NULL) <> (lead_id IS NULL)", name=op.f("ck_lessons_exactly_one_owner")
        ),
        sa.CheckConstraint(
            "(kind = 'trial') = (lead_id IS NOT NULL)", name=op.f("ck_lessons_trial_has_lead")
        ),
        sa.CheckConstraint(
            "series_id IS NULL OR child_id IS NOT NULL", name=op.f("ck_lessons_series_has_child")
        ),
        sa.CheckConstraint(
            "duration_min BETWEEN 15 AND 240", name=op.f("ck_lessons_duration_range")
        ),
        sa.ForeignKeyConstraint(
            ["series_id"],
            ["lesson_series.id"],
            name=op.f("fk_lessons_series_id_lesson_series"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["child_id"],
            ["children.id"],
            name=op.f("fk_lessons_child_id_children"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["lead_id"],
            ["leads.id"],
            name=op.f("fk_lessons_lead_id_leads"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lessons")),
        sa.UniqueConstraint("series_id", "starts_at", name=op.f("uq_lessons_series_id_starts_at")),
    )
    op.create_index(op.f("ix_lessons_child_id"), "lessons", ["child_id"], unique=False)
    op.create_index(op.f("ix_lessons_lead_id"), "lessons", ["lead_id"], unique=False)
    op.create_index(op.f("ix_lessons_starts_at"), "lessons", ["starts_at"], unique=False)
    op.create_table(
        "lesson_notes",
        sa.Column("lesson_id", sa.Uuid(), nullable=False),
        sa.Column("shared_text", sa.Text(), server_default="", nullable=False),
        sa.Column("private_text", sa.Text(), server_default="", nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["lessons.id"],
            name=op.f("fk_lesson_notes_lesson_id_lessons"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("lesson_id", name=op.f("pk_lesson_notes")),
    )


def downgrade() -> None:
    op.drop_table("lesson_notes")
    op.drop_index(op.f("ix_lessons_starts_at"), table_name="lessons")
    op.drop_index(op.f("ix_lessons_lead_id"), table_name="lessons")
    op.drop_index(op.f("ix_lessons_child_id"), table_name="lessons")
    op.drop_table("lessons")
    op.drop_index(op.f("ix_lesson_series_child_id"), table_name="lesson_series")
    op.drop_table("lesson_series")
    op.drop_table("tutor_settings")
    bind = op.get_bind()
    lesson_status.drop(bind, checkfirst=True)
    lesson_kind.drop(bind, checkfirst=True)
