"""change requests

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-12 18:00:00.000000
"""

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

change_request_type = postgresql.ENUM(
    "reschedule", "cancel", name="change_request_type", create_type=False
)
change_request_status = postgresql.ENUM(
    "pending",
    "approved",
    "rejected",
    "withdrawn",
    name="change_request_status",
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
    change_request_type.create(bind, checkfirst=True)
    change_request_status.create(bind, checkfirst=True)
    op.create_table(
        "change_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lesson_id", sa.Uuid(), nullable=False),
        sa.Column("requested_by", sa.Uuid(), nullable=False),
        sa.Column("type", change_request_type, nullable=False),
        sa.Column("proposed_text", sa.String(length=500), nullable=True),
        sa.Column("comment", sa.String(length=1000), nullable=True),
        sa.Column(
            "status", change_request_status, server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column("tutor_response", sa.String(length=1000), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        *_timestamps(),
        sa.CheckConstraint(
            "(status = 'pending') = (resolved_at IS NULL)",
            name=op.f("ck_change_requests_resolved_consistent"),
        ),
        sa.CheckConstraint(
            "status <> 'rejected' OR tutor_response IS NOT NULL",
            name=op.f("ck_change_requests_rejection_has_response"),
        ),
        sa.ForeignKeyConstraint(
            ["lesson_id"],
            ["lessons.id"],
            name=op.f("fk_change_requests_lesson_id_lessons"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["requested_by"],
            ["users.id"],
            name=op.f("fk_change_requests_requested_by_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_change_requests")),
    )
    op.create_index(
        op.f("ix_change_requests_lesson_id"), "change_requests", ["lesson_id"], unique=False
    )
    op.create_index(
        "uq_change_requests_lesson_pending",
        "change_requests",
        ["lesson_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("uq_change_requests_lesson_pending", table_name="change_requests")
    op.drop_index(op.f("ix_change_requests_lesson_id"), table_name="change_requests")
    op.drop_table("change_requests")
    bind = op.get_bind()
    change_request_status.drop(bind, checkfirst=True)
    change_request_type.drop(bind, checkfirst=True)
