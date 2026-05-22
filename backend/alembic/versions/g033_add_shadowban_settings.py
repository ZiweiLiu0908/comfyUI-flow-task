"""add shadowban settings

Revision ID: g033_add_shadowban_settings
Revises: g032_add_platform_binding_status
Create Date: 2026-05-22
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op


revision = "g033_add_shadowban_settings"
down_revision = "g032_add_platform_binding_status"
branch_labels = None
depends_on = None


def _has_column(table: str, column: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return column in {col["name"] for col in inspector.get_columns(table)}


def upgrade() -> None:
    if not _has_column("pipeline_settings", "shadowban_video_sample_count"):
        op.add_column(
            "pipeline_settings",
            sa.Column("shadowban_video_sample_count", sa.Integer(), nullable=False, server_default="7"),
        )
        op.alter_column("pipeline_settings", "shadowban_video_sample_count", server_default=None)
    if not _has_column("pipeline_settings", "shadowban_view_threshold"):
        op.add_column(
            "pipeline_settings",
            sa.Column("shadowban_view_threshold", sa.Integer(), nullable=False, server_default="0"),
        )
        op.alter_column("pipeline_settings", "shadowban_view_threshold", server_default=None)


def downgrade() -> None:
    if _has_column("pipeline_settings", "shadowban_view_threshold"):
        op.drop_column("pipeline_settings", "shadowban_view_threshold")
    if _has_column("pipeline_settings", "shadowban_video_sample_count"):
        op.drop_column("pipeline_settings", "shadowban_video_sample_count")
