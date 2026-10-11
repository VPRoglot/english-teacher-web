"""leads

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-11 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# lead_status используется в двух таблицах, поэтому типы создаются явно, а колонки их не создают.
lead_status = postgresql.ENUM(
    "new",
    "contacted",
    "trial_scheduled",
    "converted",
    "rejected",
    name="lead_status",
    create_type=False,
)
contact_method = postgresql.ENUM(
    "telegram", "whatsapp", "phone", name="contact_method", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    lead_status.create(bind, checkfirst=True)
    contact_method.create(bind, checkfirst=True)
    op.create_table(
        "leads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("parent_name", sa.String(length=100), nullable=False),
        sa.Column("child_name", sa.String(length=100), nullable=False),
        sa.Column("child_age", sa.Integer(), nullable=False),
        sa.Column("phone", sa.String(length=16), nullable=False),
        sa.Column("contact_method", contact_method, nullable=False),
        sa.Column("messenger_handle", sa.String(length=64), nullable=True),
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column("preferred_time", sa.String(length=200), nullable=True),
        sa.Column("status", lead_status, nullable=False),
        sa.Column("reject_reason", sa.String(length=500), nullable=True),
        sa.Column("tutor_comment", sa.Text(), nullable=True),
        sa.Column("family_id", sa.Uuid(), nullable=True),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("utm_source", sa.String(length=100), nullable=True),
        sa.Column("utm_medium", sa.String(length=100), nullable=True),
        sa.Column("utm_campaign", sa.String(length=100), nullable=True),
        sa.Column("notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("anonymized_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["family_id"],
            ["families.id"],
            name=op.f("fk_leads_family_id_families"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_leads")),
    )
    op.create_index(op.f("ix_leads_status"), "leads", ["status"], unique=False)
    op.create_index(op.f("ix_leads_created_at"), "leads", ["created_at"], unique=False)
    op.create_table(
        "lead_status_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("lead_id", sa.Uuid(), nullable=False),
        sa.Column("from_status", lead_status, nullable=True),
        sa.Column("to_status", lead_status, nullable=False),
        sa.Column("comment", sa.String(length=500), nullable=True),
        sa.Column(
            "changed_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["lead_id"],
            ["leads.id"],
            name=op.f("fk_lead_status_history_lead_id_leads"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lead_status_history")),
    )
    op.create_index(
        op.f("ix_lead_status_history_lead_id"), "lead_status_history", ["lead_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_lead_status_history_lead_id"), table_name="lead_status_history")
    op.drop_table("lead_status_history")
    op.drop_index(op.f("ix_leads_created_at"), table_name="leads")
    op.drop_index(op.f("ix_leads_status"), table_name="leads")
    op.drop_table("leads")
    bind = op.get_bind()
    contact_method.drop(bind, checkfirst=True)
    lead_status.drop(bind, checkfirst=True)
