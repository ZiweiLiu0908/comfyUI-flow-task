from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TemplateUsageHistory(Base):
    """One row per video task that consumes a template."""

    __tablename__ = "template_usage_history"
    __table_args__ = (
        UniqueConstraint("video_task_id", name="uq_template_usage_history_video_task_id"),
        UniqueConstraint("template_id", "usage_index", name="uq_template_usage_history_template_usage_index"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    template_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("video_ai_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    video_task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("video_tasks.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    usage_index: Mapped[int] = mapped_column(Integer, nullable=False)
    used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    reuse_reason: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    source: Mapped[str | None] = mapped_column(String(30), nullable=True)
    source_step: Mapped[str | None] = mapped_column(String(60), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
