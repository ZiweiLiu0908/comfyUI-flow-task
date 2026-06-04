from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ExternalSupplementRequestItem(Base):
    """Per-account progress for a vendor supplement request."""

    __tablename__ = "external_supplement_request_items"
    __table_args__ = (
        UniqueConstraint(
            "request_id",
            "account_id",
            name="uq_external_supplement_request_items_request_account",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("external_supplement_requests.request_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(20), nullable=False)
    blogger_handle: Mapped[str | None] = mapped_column(String(200), nullable=True)
    target_video_count: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    target_unused_template_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    initial_unused_template_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_unused_template_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    requested_video_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    round_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    schedule_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    completed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duplicated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    processing_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_received: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )
