"""add scheduled scope fields

Revision ID: g053_schedule_scope_fields
Revises: g052_template_reuse_tracking
Create Date: 2026-06-05
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision = "g053_schedule_scope_fields"
down_revision = "g052_template_reuse_tracking"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    return name in set(inspect(bind).get_table_names())


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    return {c["name"] for c in inspect(bind).get_columns(table)}


def _add_columns(table: str, additions: list[tuple[str, sa.Column]], drop_defaults: set[str]) -> None:
    if not _table_exists(table):
        return
    cols = _columns(table)
    for name, column in additions:
        if name not in cols:
            op.add_column(table, column)
            if name in drop_defaults:
                op.alter_column(table, name, server_default=None)


def upgrade() -> None:
    json_empty_object = sa.text("'{}'::json")
    json_empty_array = sa.text("'[]'::json")

    _add_columns(
        "pipeline_settings",
        [
            ("template_supplement_scope_mode", sa.Column("template_supplement_scope_mode", sa.String(20), nullable=False, server_default="filtered")),
            ("template_supplement_scope_account_ids", sa.Column("template_supplement_scope_account_ids", sa.JSON(), nullable=False, server_default=json_empty_array)),
            ("template_supplement_scope_filters", sa.Column("template_supplement_scope_filters", sa.JSON(), nullable=False, server_default=json_empty_object)),
            ("scheduled_generation_scope_mode", sa.Column("scheduled_generation_scope_mode", sa.String(20), nullable=False, server_default="filtered")),
            ("scheduled_generation_scope_account_ids", sa.Column("scheduled_generation_scope_account_ids", sa.JSON(), nullable=False, server_default=json_empty_array)),
            ("scheduled_generation_scope_filters", sa.Column("scheduled_generation_scope_filters", sa.JSON(), nullable=False, server_default=json_empty_object)),
        ],
        {
            "template_supplement_scope_mode",
            "template_supplement_scope_account_ids",
            "template_supplement_scope_filters",
            "scheduled_generation_scope_mode",
            "scheduled_generation_scope_account_ids",
            "scheduled_generation_scope_filters",
        },
    )

    run_scope_additions = [
        ("scope_mode", sa.Column("scope_mode", sa.String(20), nullable=False, server_default="filtered")),
        ("scope_account_ids_snapshot", sa.Column("scope_account_ids_snapshot", sa.JSON(), nullable=False, server_default=json_empty_array)),
        ("scope_filters_snapshot", sa.Column("scope_filters_snapshot", sa.JSON(), nullable=False, server_default=json_empty_object)),
        ("resolved_account_count", sa.Column("resolved_account_count", sa.Integer(), nullable=False, server_default="0")),
    ]
    _add_columns(
        "scheduled_generation_runs",
        run_scope_additions,
        {"scope_mode", "scope_account_ids_snapshot", "scope_filters_snapshot", "resolved_account_count"},
    )
    _add_columns(
        "template_supplement_runs",
        run_scope_additions,
        {"scope_mode", "scope_account_ids_snapshot", "scope_filters_snapshot", "resolved_account_count"},
    )


def downgrade() -> None:
    for table in ("template_supplement_runs", "scheduled_generation_runs"):
        if not _table_exists(table):
            continue
        cols = _columns(table)
        for name in (
            "resolved_account_count",
            "scope_filters_snapshot",
            "scope_account_ids_snapshot",
            "scope_mode",
        ):
            if name in cols:
                op.drop_column(table, name)

    if _table_exists("pipeline_settings"):
        cols = _columns("pipeline_settings")
        for name in (
            "scheduled_generation_scope_filters",
            "scheduled_generation_scope_account_ids",
            "scheduled_generation_scope_mode",
            "template_supplement_scope_filters",
            "template_supplement_scope_account_ids",
            "template_supplement_scope_mode",
        ):
            if name in cols:
                op.drop_column("pipeline_settings", name)
