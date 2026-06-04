"""add one_sentence_summary to blogger tagging and tiktok_bloggers

Revision ID: g048_one_sentence_summary
Revises: g047_tagging_callback_nullable
Create Date: 2026-06-04

新增博主一句话总结字段：
  - blogger_tagging_results.account_one_sentence_summary TEXT
  - tiktok_bloggers.one_sentence_summary TEXT
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "g048_one_sentence_summary"
down_revision = "g047_tagging_callback_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE blogger_tagging_results "
        "ADD COLUMN IF NOT EXISTS account_one_sentence_summary TEXT"
    )
    op.execute(
        "ALTER TABLE tiktok_bloggers "
        "ADD COLUMN IF NOT EXISTS one_sentence_summary TEXT"
    )
    # alembic_version.version_num 默认 VARCHAR(32)，后续 revision ID 更长时会溢出，扩到 64
    op.execute(
        "ALTER TABLE alembic_version "
        "ALTER COLUMN version_num TYPE VARCHAR(64)"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE tiktok_bloggers DROP COLUMN IF EXISTS one_sentence_summary")
    op.execute("ALTER TABLE blogger_tagging_results DROP COLUMN IF EXISTS account_one_sentence_summary")
