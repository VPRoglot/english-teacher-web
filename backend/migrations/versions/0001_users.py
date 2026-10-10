"""users

Revision ID: 0001
Revises:
Create Date: 2026-10-11 02:57:26.626703
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

user_role = sa.Enum("tutor", "parent", "child", name="user_role")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("email", sa.String(length=254), nullable=True),
        sa.Column("username", sa.String(length=32), nullable=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "role <> 'child' OR username IS NOT NULL", name=op.f("ck_users_username_required")
        ),
        sa.CheckConstraint(
            "role = 'child' OR email IS NOT NULL", name=op.f("ck_users_email_required")
        ),
        sa.CheckConstraint("email = lower(email)", name=op.f("ck_users_email_lowercase")),
        sa.CheckConstraint("username = lower(username)", name=op.f("ck_users_username_lowercase")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("email", name=op.f("uq_users_email")),
        sa.UniqueConstraint("username", name=op.f("uq_users_username")),
    )
    op.create_index(
        "uq_users_single_tutor",
        "users",
        ["role"],
        unique=True,
        postgresql_where=sa.text("role = 'tutor'"),
    )


def downgrade() -> None:
    op.drop_index("uq_users_single_tutor", table_name="users")
    op.drop_table("users")
    user_role.drop(op.get_bind(), checkfirst=True)
