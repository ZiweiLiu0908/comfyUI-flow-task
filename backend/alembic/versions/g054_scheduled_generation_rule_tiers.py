"""add scheduled generation rule tier audit fields

Revision ID: g054_scheduled_generation_rule_tiers
Revises: g053_schedule_scope_fields
Create Date: 2026-06-05
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision = "g054_scheduled_generation_rule_tiers"
down_revision = "g053_schedule_scope_fields"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    return name in set(inspect(bind).get_table_names())


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    return {c["name"] for c in inspect(bind).get_columns(table)}


def upgrade() -> None:
    if not _table_exists("scheduled_generation_run_items"):
        return
    cols = _columns("scheduled_generation_run_items")
    additions = [
        ("matched_rule_label", sa.Column("matched_rule_label", sa.String(40), nullable=True)),
        ("threshold_min_views", sa.Column("threshold_min_views", sa.Integer(), nullable=True)),
        ("threshold_max_views", sa.Column("threshold_max_views", sa.Integer(), nullable=True)),
        ("matched_rule_snapshot", sa.Column("matched_rule_snapshot", sa.JSON(), nullable=True)),
    ]
    for name, column in additions:
        if name not in cols:
            op.add_column("scheduled_generation_run_items", column)


def downgrade() -> None:
    if not _table_exists("scheduled_generation_run_items"):
        return
    cols = _columns("scheduled_generation_run_items")
    for name in (
        "matched_rule_snapshot",
        "threshold_max_views",
        "threshold_min_views",
        "matched_rule_label",
    ):
        if name in cols:
            op.drop_column("scheduled_generation_run_items", name)
