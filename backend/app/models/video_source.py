from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Integer, JSON, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class VideoSource(Base):
    __tablename__ = "video_sources"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    platform: Mapped[str | None] = mapped_column(String(50), nullable=True)
    blogger_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    video_title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    video_desc: Mapped[str | None] = mapped_column(Text, nullable=True, comment="Video description")
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    video_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    local_video_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    download_status: Mapped[str | None] = mapped_column(String(20), nullable=True, default="idle")
    view_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    like_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    favorite_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comment_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    share_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    publish_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Video duration in seconds")
    width: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Video width in pixels")
    height: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="Video height in pixels")
    aspect_ratio: Mapped[float | None] = mapped_column(Float, nullable=True, comment="Video aspect ratio (width/height)")
    extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    repeatable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    tags: Mapped[list["Tag"]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "Tag",
        secondary="video_source_tags",
        lazy="selectin",
    )
