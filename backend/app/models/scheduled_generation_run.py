from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ScheduledGenerationRun(Base):
    """Per-owner run record for scheduled one-click generation."""

    __tablename__ = "scheduled_generation_runs"
    __table_args__ = (
        UniqueConstraint("owner_id", "trigger_key", name="uq_scheduled_generation_owner_trigger"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    trigger_key: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    target_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running", index=True)
    config_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    scope_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="filtered")
    scope_account_ids_snapshot: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    scope_filters_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    resolved_account_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    account_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_created_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    step_one_created_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unused_template_created_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    used_template_created_tasks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    shortfall_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class ScheduledGenerationRunItem(Base):
    """Per-account/template audit row for scheduled one-click generation."""

    __tablename__ = "scheduled_generation_run_items"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("scheduled_generation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    source_step: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    template_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    publication_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    major_category: Mapped[str | None] = mapped_column(String(40), nullable=True)
    total_views: Mapped[int | None] = mapped_column(Integer, nullable=True)
    threshold_views: Mapped[int | None] = mapped_column(Integer, nullable=True)
    repeat_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    subtask_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_task_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    skip_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
