"""store cart mutation request fingerprints

Revision ID: 9a874d18a4d2
Revises: 4d773da3c52e
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9a874d18a4d2"
down_revision: str | Sequence[str] | None = "4d773da3c52e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "idempotency_records",
        sa.Column("request_fingerprint", sa.String(length=64), nullable=True),
    )
def downgrade() -> None:
    op.drop_column("idempotency_records", "request_fingerprint")
