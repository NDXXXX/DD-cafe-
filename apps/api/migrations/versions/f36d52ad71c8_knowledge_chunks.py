"""add knowledge chunks and index status

Revision ID: f36d52ad71c8
Revises: 9a874d18a4d2
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f36d52ad71c8"
down_revision: str | Sequence[str] | None = "9a874d18a4d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "knowledge_documents",
        sa.Column("content_sha256", sa.String(length=64), server_default="", nullable=False),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("index_status", sa.String(length=20), server_default="pending", nullable=False),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("index_error", sa.Text(), nullable=True),
    )
    op.add_column(
        "knowledge_documents",
        sa.Column("indexed_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        op.f("ix_knowledge_documents_index_status"),
        "knowledge_documents",
        ["index_status"],
        unique=False,
    )
    op.create_table(
        "knowledge_chunks",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("document_id", sa.String(length=64), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["knowledge_documents.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("document_id", "chunk_index"),
    )
    op.create_index(
        op.f("ix_knowledge_chunks_document_id"),
        "knowledge_chunks",
        ["document_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_knowledge_chunks_document_id"), table_name="knowledge_chunks")
    op.drop_table("knowledge_chunks")
    op.drop_index(
        op.f("ix_knowledge_documents_index_status"),
        table_name="knowledge_documents",
    )
    op.drop_column("knowledge_documents", "indexed_at")
    op.drop_column("knowledge_documents", "index_error")
    op.drop_column("knowledge_documents", "index_status")
    op.drop_column("knowledge_documents", "content_sha256")
