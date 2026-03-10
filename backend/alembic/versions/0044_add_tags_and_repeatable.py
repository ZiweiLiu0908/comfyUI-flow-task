"""Add tags table, video_source_tags junction, and repeatable column to video_sources

Revision ID: 0044
Revises: 0043
Create Date: 2026-03-10 18:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # 1. Create tags table (if not exists)
    if "tags" not in existing_tables:
        op.create_table(
            "tags",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column("name", sa.String(100), nullable=False),
            sa.Column("color", sa.String(20), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        )
        op.create_index("ix_tags_owner_id", "tags", ["owner_id"])

    # 2. Create video_source_tags junction table (if not exists)
    if "video_source_tags" not in existing_tables:
        op.create_table(
            "video_source_tags",
            sa.Column(
                "video_source_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("video_sources.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column(
                "tag_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("tags.id", ondelete="CASCADE"),
                primary_key=True,
            ),
        )

    # 3. Add repeatable column to video_sources (if not exists)
    vs_cols = {c["name"] for c in inspector.get_columns("video_sources")}
    if "repeatable" not in vs_cols:
        op.add_column(
            "video_sources",
            sa.Column("repeatable", sa.Boolean(), nullable=False, server_default="false"),
        )


def downgrade() -> None:
    op.execute("ALTER TABLE video_sources DROP COLUMN IF EXISTS repeatable")
    op.execute("DROP TABLE IF EXISTS video_source_tags")
    op.execute("DROP INDEX IF EXISTS ix_tags_owner_id")
    op.execute("DROP TABLE IF EXISTS tags")
