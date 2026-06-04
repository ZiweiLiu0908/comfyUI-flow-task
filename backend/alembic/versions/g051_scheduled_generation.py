"""add scheduled one-click generation

Revision ID: g051_scheduled_generation
Revises: g050_template_supplement_schedule
Create Date: 2026-06-04
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision = "g051_scheduled_generation"
down_revision = "g050_template_supplement_schedule"
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
        ("scheduled_generation_enabled", sa.Column("scheduled_generation_enabled", sa.Boolean(), nullable=False, server_default="false")),
        ("scheduled_generation_cron", sa.Column("scheduled_generation_cron", sa.String(100), nullable=True)),
        ("scheduled_generation_lookback_days", sa.Column("scheduled_generation_lookback_days", sa.Integer(), nullable=False, server_default="2")),
        ("scheduled_generation_target_unpublished_count", sa.Column("scheduled_generation_target_unpublished_count", sa.Integer(), nullable=False, server_default="5")),
        ("scheduled_generation_subtask_count", sa.Column("scheduled_generation_subtask_count", sa.Integer(), nullable=False, server_default="1")),
        ("scheduled_generation_unused_template_months", sa.Column("scheduled_generation_unused_template_months", sa.Integer(), nullable=False, server_default="3")),
        ("scheduled_generation_used_template_cooldown_days", sa.Column("scheduled_generation_used_template_cooldown_days", sa.Integer(), nullable=False, server_default="30")),
        ("scheduled_generation_category_rules", sa.Column("scheduled_generation_category_rules", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json"))),
        ("scheduled_generation_last_trigger_key", sa.Column("scheduled_generation_last_trigger_key", sa.String(20), nullable=True)),
    ]
    for name, column in additions:
        if name not in pipeline_cols:
            op.add_column("pipeline_settings", column)
            if name in {
                "scheduled_generation_enabled",
                "scheduled_generation_lookback_days",
                "scheduled_generation_target_unpublished_count",
                "scheduled_generation_subtask_count",
                "scheduled_generation_unused_template_months",
                "scheduled_generation_used_template_cooldown_days",
                "scheduled_generation_category_rules",
            }:
                op.alter_column("pipeline_settings", name, server_default=None)

    if not _table_exists("scheduled_generation_runs"):
        op.create_table(
            "scheduled_generation_runs",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("owner_id", sa.Uuid(), nullable=False),
            sa.Column("trigger_key", sa.String(20), nullable=False),
            sa.Column("target_date", sa.Date(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="running"),
            sa.Column("config_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'::json")),
            sa.Column("account_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("total_created_tasks", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("step_one_created_tasks", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("unused_template_created_tasks", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("used_template_created_tasks", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("shortfall_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("id", name="scheduled_generation_runs_pkey"),
            sa.UniqueConstraint("owner_id", "trigger_key", name="uq_scheduled_generation_owner_trigger"),
        )
        op.create_index("ix_scheduled_generation_runs_owner_id", "scheduled_generation_runs", ["owner_id"])
        op.create_index("ix_scheduled_generation_runs_trigger_key", "scheduled_generation_runs", ["trigger_key"])
        op.create_index("ix_scheduled_generation_runs_target_date", "scheduled_generation_runs", ["target_date"])
        op.create_index("ix_scheduled_generation_runs_status", "scheduled_generation_runs", ["status"])

    if not _table_exists("scheduled_generation_run_items"):
        op.create_table(
            "scheduled_generation_run_items",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("run_id", sa.Uuid(), nullable=False),
            sa.Column("owner_id", sa.Uuid(), nullable=False),
            sa.Column("account_id", sa.Uuid(), nullable=True),
            sa.Column("source_step", sa.String(40), nullable=False),
            sa.Column("template_id", sa.Uuid(), nullable=True),
            sa.Column("publication_id", sa.Uuid(), nullable=True),
            sa.Column("major_category", sa.String(40), nullable=True),
            sa.Column("total_views", sa.Integer(), nullable=True),
            sa.Column("threshold_views", sa.Integer(), nullable=True),
            sa.Column("repeat_count", sa.Integer(), nullable=True),
            sa.Column("subtask_count", sa.Integer(), nullable=True),
            sa.Column("created_task_ids", sa.JSON(), nullable=True),
            sa.Column("skip_reason", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["run_id"], ["scheduled_generation_runs.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id", name="scheduled_generation_run_items_pkey"),
        )
        op.create_index("ix_scheduled_generation_run_items_run_id", "scheduled_generation_run_items", ["run_id"])
        op.create_index("ix_scheduled_generation_run_items_owner_id", "scheduled_generation_run_items", ["owner_id"])
        op.create_index("ix_scheduled_generation_run_items_account_id", "scheduled_generation_run_items", ["account_id"])
        op.create_index("ix_scheduled_generation_run_items_source_step", "scheduled_generation_run_items", ["source_step"])
        op.create_index("ix_scheduled_generation_run_items_template_id", "scheduled_generation_run_items", ["template_id"])
        op.create_index("ix_scheduled_generation_run_items_publication_id", "scheduled_generation_run_items", ["publication_id"])


def downgrade() -> None:
    if _table_exists("scheduled_generation_run_items"):
        for ix in (
            "ix_scheduled_generation_run_items_publication_id",
            "ix_scheduled_generation_run_items_template_id",
            "ix_scheduled_generation_run_items_source_step",
            "ix_scheduled_generation_run_items_account_id",
            "ix_scheduled_generation_run_items_owner_id",
            "ix_scheduled_generation_run_items_run_id",
        ):
            op.drop_index(ix, table_name="scheduled_generation_run_items")
        op.drop_table("scheduled_generation_run_items")

    if _table_exists("scheduled_generation_runs"):
        for ix in (
            "ix_scheduled_generation_runs_status",
            "ix_scheduled_generation_runs_target_date",
            "ix_scheduled_generation_runs_trigger_key",
            "ix_scheduled_generation_runs_owner_id",
        ):
            op.drop_index(ix, table_name="scheduled_generation_runs")
        op.drop_table("scheduled_generation_runs")

    pipeline_cols = _columns("pipeline_settings")
    for name in (
        "scheduled_generation_last_trigger_key",
        "scheduled_generation_category_rules",
        "scheduled_generation_used_template_cooldown_days",
        "scheduled_generation_unused_template_months",
        "scheduled_generation_subtask_count",
        "scheduled_generation_target_unpublished_count",
        "scheduled_generation_lookback_days",
        "scheduled_generation_cron",
        "scheduled_generation_enabled",
    ):
        if name in pipeline_cols:
            op.drop_column("pipeline_settings", name)
