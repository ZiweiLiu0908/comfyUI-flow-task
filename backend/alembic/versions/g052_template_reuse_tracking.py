"""add template reuse tracking

Revision ID: g052_template_reuse_tracking
Revises: g051_scheduled_generation
Create Date: 2026-06-04
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision = "g052_template_reuse_tracking"
down_revision = "g051_scheduled_generation"
branch_labels = None
depends_on = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    return name in set(inspect(bind).get_table_names())


def _columns(table: str) -> set[str]:
    bind = op.get_bind()
    return {c["name"] for c in inspect(bind).get_columns(table)}


def _drop_index_if_exists(name: str, table_name: str) -> None:
    bind = op.get_bind()
    indexes = {ix["name"] for ix in inspect(bind).get_indexes(table_name)}
    if name in indexes:
        op.drop_index(name, table_name=table_name)


def upgrade() -> None:
    video_task_cols = _columns("video_tasks")
    additions = [
        ("is_reused_template", sa.Column("is_reused_template", sa.Boolean(), nullable=False, server_default="false")),
        ("template_reuse_reason", sa.Column("template_reuse_reason", sa.String(40), nullable=True)),
        ("template_usage_index", sa.Column("template_usage_index", sa.Integer(), nullable=True)),
        ("template_used_at", sa.Column("template_used_at", sa.DateTime(timezone=True), nullable=True)),
        ("template_usage_source", sa.Column("template_usage_source", sa.String(30), nullable=True)),
        ("template_usage_source_step", sa.Column("template_usage_source_step", sa.String(60), nullable=True)),
    ]
    for name, column in additions:
        if name not in video_task_cols:
            op.add_column("video_tasks", column)
            if name == "is_reused_template":
                op.alter_column("video_tasks", name, server_default=None)

    indexes = {ix["name"] for ix in inspect(op.get_bind()).get_indexes("video_tasks")}
    if "ix_video_tasks_is_reused_template" not in indexes:
        op.create_index("ix_video_tasks_is_reused_template", "video_tasks", ["is_reused_template"])
    if "ix_video_tasks_template_reuse_reason" not in indexes:
        op.create_index("ix_video_tasks_template_reuse_reason", "video_tasks", ["template_reuse_reason"])

    if not _table_exists("template_usage_history"):
        op.create_table(
            "template_usage_history",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("owner_id", sa.Uuid(), nullable=False),
            sa.Column("account_id", sa.Uuid(), nullable=True),
            sa.Column("template_id", sa.Uuid(), nullable=False),
            sa.Column("video_task_id", sa.Uuid(), nullable=False),
            sa.Column("usage_index", sa.Integer(), nullable=False),
            sa.Column("used_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("reuse_reason", sa.String(40), nullable=True),
            sa.Column("source", sa.String(30), nullable=True),
            sa.Column("source_step", sa.String(60), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.ForeignKeyConstraint(["template_id"], ["video_ai_templates.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["video_task_id"], ["video_tasks.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id", name="template_usage_history_pkey"),
            sa.UniqueConstraint("video_task_id", name="uq_template_usage_history_video_task_id"),
            sa.UniqueConstraint("template_id", "usage_index", name="uq_template_usage_history_template_usage_index"),
        )
        op.create_index("ix_template_usage_history_owner_id", "template_usage_history", ["owner_id"])
        op.create_index("ix_template_usage_history_account_id", "template_usage_history", ["account_id"])
        op.create_index("ix_template_usage_history_template_id", "template_usage_history", ["template_id"])
        op.create_index("ix_template_usage_history_video_task_id", "template_usage_history", ["video_task_id"])
        op.create_index("ix_template_usage_history_used_at", "template_usage_history", ["used_at"])
        op.create_index("ix_template_usage_history_reuse_reason", "template_usage_history", ["reuse_reason"])


def downgrade() -> None:
    if _table_exists("template_usage_history"):
        for ix in (
            "ix_template_usage_history_reuse_reason",
            "ix_template_usage_history_used_at",
            "ix_template_usage_history_video_task_id",
            "ix_template_usage_history_template_id",
            "ix_template_usage_history_account_id",
            "ix_template_usage_history_owner_id",
        ):
            _drop_index_if_exists(ix, "template_usage_history")
        op.drop_table("template_usage_history")

    for ix in (
        "ix_video_tasks_template_reuse_reason",
        "ix_video_tasks_is_reused_template",
    ):
        _drop_index_if_exists(ix, "video_tasks")

    video_task_cols = _columns("video_tasks")
    for name in (
        "template_usage_source_step",
        "template_usage_source",
        "template_used_at",
        "template_usage_index",
        "template_reuse_reason",
        "is_reused_template",
    ):
        if name in video_task_cols:
            op.drop_column("video_tasks", name)
