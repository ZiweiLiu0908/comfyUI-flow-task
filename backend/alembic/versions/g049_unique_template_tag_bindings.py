"""deduplicate template tag bindings

Revision ID: g049_unique_template_tag_bindings
Revises: g048_one_sentence_summary
Create Date: 2026-06-04

Ensure a template can bind many tags, but cannot bind the same tag more than once.
"""
from __future__ import annotations

from alembic import op


revision = "g049_unique_template_tag_bindings"
down_revision = "g048_one_sentence_summary"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # alembic_version.version_num 默认 VARCHAR(32)，本 revision ID 长 35 字符，先扩列
    op.execute(
        "ALTER TABLE alembic_version ALTER COLUMN version_num TYPE VARCHAR(64)"
    )
    op.execute(
        """
        DELETE FROM video_source_tags
        WHERE id IN (
          SELECT id
          FROM (
            SELECT
              id,
              ROW_NUMBER() OVER (
                PARTITION BY video_ai_template_id, tag_id
                ORDER BY created_at ASC, id ASC
              ) AS rn
            FROM video_source_tags
            WHERE video_ai_template_id IS NOT NULL
          ) dup
          WHERE dup.rn > 1
        )
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_video_source_tags_template_tag
        ON video_source_tags (video_ai_template_id, tag_id)
        WHERE video_ai_template_id IS NOT NULL
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ux_video_source_tags_template_tag")
