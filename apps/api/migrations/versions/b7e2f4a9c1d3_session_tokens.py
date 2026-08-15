"""add session tokens for customer write auth

Revision ID: b7e2f4a9c1d3
Revises: f36d52ad71c8
Create Date: 2026-08-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7e2f4a9c1d3"
down_revision: str | Sequence[str] | None = "f36d52ad71c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sessions",
        sa.Column("session_id", sa.String(length=80), nullable=False),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("session_id"),
    )
    op.create_index(op.f("ix_sessions_token"), "sessions", ["token"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_sessions_token"), table_name="sessions")
    op.drop_table("sessions")
