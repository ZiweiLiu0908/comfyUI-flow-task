from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TemplateSupplementRun(Base):
    """Per-account record for scheduled template supplementation."""

    __tablename__ = "template_supplement_runs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    trigger_key: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="running", index=True)
    target_unused_template_count: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    initial_unused_template_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_unused_template_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    requested_video_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    last_request_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    filters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    skip_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
