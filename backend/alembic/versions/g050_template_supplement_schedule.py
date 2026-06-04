"""add template supplement schedule

Revision ID: g050_template_supplement_schedule
Revises: g049_unique_template_tag_bindings
Create Date: 2026-06-04
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision = "g050_template_supplement_schedule"
down_revision = "g049_unique_template_tag_bindings"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    return name in set(inspect(bind).get_table_names())


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    return {c["name"] for c in inspect(bind).get_columns(table)}


def upgrade() -> None:
    pipeline_cols = _columns("pipeline_settings")
    additions = [
        ("template_supplement_schedule_enabled", sa.Column("template_supplement_schedule_enabled", sa.Boolean(), nullable=False, server_default="false")),
        ("template_supplement_schedule_cron", sa.Column("template_supplement_schedule_cron", sa.String(100), nullable=True)),
        ("template_supplement_target_unused_count", sa.Column("template_supplement_target_unused_count", sa.Integer(), nullable=False, server_default="10")),
        ("template_supplement_filters", sa.Column("template_supplement_filters", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json"))),
        ("template_supplement_max_rounds", sa.Column("template_supplement_max_rounds", sa.Integer(), nullable=False, server_default="2")),
        ("template_supplement_last_trigger_key", sa.Column("template_supplement_last_trigger_key", sa.String(20), nullable=True)),
    ]
    for name, column in additions:
        if name not in pipeline_cols:
            op.add_column("pipeline_settings", column)
            if name in {
                "template_supplement_schedule_enabled",
                "template_supplement_target_unused_count",
                "template_supplement_filters",
                "template_supplement_max_rounds",
            }:
                op.alter_column("pipeline_settings", name, server_default=None)

    item_cols = _columns("external_supplement_request_items")
    item_additions = [
        ("target_unused_template_count", sa.Column("target_unused_template_count", sa.Integer(), nullable=True)),
        ("initial_unused_template_count", sa.Column("initial_unused_template_count", sa.Integer(), nullable=True)),
        ("current_unused_template_count", sa.Column("current_unused_template_count", sa.Integer(), nullable=True)),
        ("requested_video_count", sa.Column("requested_video_count", sa.Integer(), nullable=True)),
        ("round_index", sa.Column("round_index", sa.Integer(), nullable=False, server_default="1")),
        ("schedule_run_id", sa.Column("schedule_run_id", sa.Uuid(), nullable=True)),
    ]
    for name, column in item_additions:
        if name not in item_cols:
            op.add_column("external_supplement_request_items", column)
            if name == "round_index":
                op.alter_column("external_supplement_request_items", name, server_default=None)
    if "schedule_run_id" not in item_cols:
        op.create_index(
            "ix_external_supplement_request_items_schedule_run_id",
            "external_supplement_request_items",
            ["schedule_run_id"],
        )

    if not _table_exists("template_supplement_runs"):
        op.create_table(
            "template_supplement_runs",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("owner_id", sa.Uuid(), nullable=True),
            sa.Column("trigger_key", sa.String(20), nullable=False),
            sa.Column("account_id", sa.Uuid(), nullable=False),
            sa.Column("mode", sa.String(20), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="running"),
            sa.Column("target_unused_template_count", sa.Integer(), nullable=False, server_default="10"),
            sa.Column("initial_unused_template_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("current_unused_template_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("requested_video_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("completed_rounds", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("max_rounds", sa.Integer(), nullable=False, server_default="2"),
            sa.Column("last_request_id", sa.Uuid(), nullable=True),
            sa.Column("filters", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("skip_reason", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id", name="template_supplement_runs_pkey"),
        )
        op.create_index("ix_template_supplement_runs_owner_id", "template_supplement_runs", ["owner_id"])
        op.create_index("ix_template_supplement_runs_trigger_key", "template_supplement_runs", ["trigger_key"])
        op.create_index("ix_template_supplement_runs_account_id", "template_supplement_runs", ["account_id"])
        op.create_index("ix_template_supplement_runs_status", "template_supplement_runs", ["status"])
        op.create_index("ix_template_supplement_runs_last_request_id", "template_supplement_runs", ["last_request_id"])


def downgrade() -> None:
    if _table_exists("template_supplement_runs"):
        for ix in (
            "ix_template_supplement_runs_last_request_id",
            "ix_template_supplement_runs_status",
            "ix_template_supplement_runs_account_id",
            "ix_template_supplement_runs_trigger_key",
            "ix_template_supplement_runs_owner_id",
        ):
            op.drop_index(ix, table_name="template_supplement_runs")
        op.drop_table("template_supplement_runs")

    item_cols = _columns("external_supplement_request_items")
    if "schedule_run_id" in item_cols:
        op.drop_index("ix_external_supplement_request_items_schedule_run_id", table_name="external_supplement_request_items")
    for name in (
        "schedule_run_id",
        "round_index",
        "requested_video_count",
        "current_unused_template_count",
        "initial_unused_template_count",
        "target_unused_template_count",
    ):
        if name in item_cols:
            op.drop_column("external_supplement_request_items", name)

    pipeline_cols = _columns("pipeline_settings")
    for name in (
        "template_supplement_last_trigger_key",
        "template_supplement_max_rounds",
        "template_supplement_filters",
        "template_supplement_target_unused_count",
        "template_supplement_schedule_cron",
        "template_supplement_schedule_enabled",
    ):
        if name in pipeline_cols:
            op.drop_column("pipeline_settings", name)
