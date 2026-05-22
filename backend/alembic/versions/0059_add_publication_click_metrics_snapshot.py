"""add click_metrics_24h_snapshot to video_publications

Revision ID: 0059
Revises: 0058, g031_fix_kol_status
Create Date: 2026-05-22
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0059"
down_revision = ("0058", "g031_fix_kol_status")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "video_publications",
        sa.Column("click_metrics_24h_snapshot", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("video_publications", "click_metrics_24h_snapshot")
