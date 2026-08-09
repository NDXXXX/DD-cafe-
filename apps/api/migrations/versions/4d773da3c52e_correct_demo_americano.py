"""correct demo americano

Revision ID: 4d773da3c52e
Revises: 7255765012cd
Create Date: 2026-08-09 06:15:00
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4d773da3c52e"
down_revision: str | Sequence[str] | None = "7255765012cd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _update_americano(
    name: str,
    description: str,
    tags: list[str],
    aliases: list[str],
) -> None:
    op.execute(
        sa.text(
            """
            UPDATE menu_items
            SET name = :name,
                description = :description,
                tags = CAST(:tags AS JSON),
                aliases = CAST(:aliases AS JSON)
            WHERE id = 'sea-salt-americano'
            """
        ).bindparams(
            name=name,
            description=description,
            tags=json.dumps(tags, ensure_ascii=False),
            aliases=json.dumps(aliases, ensure_ascii=False),
        )
    )


def upgrade() -> None:
    _update_americano(
        name="美式",
        description="双份浓缩与水，干净清爽，不加奶也不额外加糖。",
        tags=["黑咖啡", "无奶", "清爽"],
        aliases=["经典美式", "美式咖啡", "冰美式", "热美式", "Americano"],
    )


def downgrade() -> None:
    _update_americano(
        name="海盐焦糖美式",
        description="清爽美式带一点海盐焦糖香，不加奶也有层次。",
        tags=["黑咖啡", "微甜", "清爽"],
        aliases=["美式", "海盐美式", "焦糖美式"],
    )
