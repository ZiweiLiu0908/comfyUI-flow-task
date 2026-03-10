from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


# ── Tag schemas ──────────────────────────────────────────────────────────────

class TagCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    color: str | None = None  # e.g. "#6366f1"


class TagRead(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID | None
    name: str
    color: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── VideoSource schemas ──────────────────────────────────────────────────────

class VideoSourceParseRequest(BaseModel):
    source_url: str = Field(min_length=1)


class VideoSourceParseResult(BaseModel):
    """Parsed video info — not yet persisted to DB."""
    source_url: str
    platform: str | None = None
    blogger_name: str | None = None
    video_title: str | None = None
    video_desc: str | None = None
    video_url: str | None = None
    thumbnail_url: str | None = None
    view_count: int | None = None
    like_count: int | None = None
    favorite_count: int | None = None
    comment_count: int | None = None
    share_count: int | None = None
    publish_date: datetime | None = None
    duration: int | None = None
    width: int | None = None
    height: int | None = None
    aspect_ratio: float | None = None
    extra: dict | None = None
    # Set if source_url already exists in DB (deduplication)
    existing_id: uuid.UUID | None = None


class VideoSourceCreate(BaseModel):
    """Create a video source. Either supply only source_url (triggers yt-dlp parse),
    or supply all pre-parsed fields (from /parse endpoint) to skip re-parsing."""
    source_url: str = Field(min_length=1)
    # Pre-parsed fields from /parse — if any are provided, skip yt-dlp
    platform: str | None = None
    blogger_name: str | None = None
    video_title: str | None = None
    video_desc: str | None = None
    video_url: str | None = None
    thumbnail_url: str | None = None
    view_count: int | None = None
    like_count: int | None = None
    favorite_count: int | None = None
    comment_count: int | None = None
    share_count: int | None = None
    publish_date: datetime | None = None
    duration: int | None = None
    width: int | None = None
    height: int | None = None
    aspect_ratio: float | None = None
    extra: dict | None = None
    # New fields
    tag_ids: list[uuid.UUID] = Field(default_factory=list)
    repeatable: bool = False


class VideoSourceRead(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID | None
    platform: str | None
    blogger_name: str | None
    video_title: str | None
    video_desc: str | None
    source_url: str
    video_url: str | None
    thumbnail_url: str | None
    local_video_url: str | None
    download_status: str | None
    view_count: int | None
    like_count: int | None
    favorite_count: int | None
    comment_count: int | None
    share_count: int | None
    publish_date: datetime | None
    duration: int | None
    width: int | None
    height: int | None
    aspect_ratio: float | None
    extra: dict | None
    repeatable: bool
    tags: list[TagRead] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class VideoSourceListItem(BaseModel):
    id: uuid.UUID
    owner_id: uuid.UUID | None = None
    owner_username: str | None = None
    platform: str | None
    blogger_name: str | None
    video_title: str | None
    video_desc: str | None
    source_url: str
    video_url: str | None
    thumbnail_url: str | None
    local_video_url: str | None
    download_status: str | None
    view_count: int | None
    like_count: int | None
    favorite_count: int | None
    comment_count: int | None
    share_count: int | None
    publish_date: datetime | None
    duration: int | None
    width: int | None
    height: int | None
    aspect_ratio: float | None
    repeatable: bool = False
    tags: list[TagRead] = []
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class VideoSourceListResponse(BaseModel):
    items: list[VideoSourceListItem]
    total: int
    page: int
    page_size: int


class VideoSourceStatsResponse(BaseModel):
    total: int
    youtube_count: int
    tiktok_count: int
    recent_count: int  # added in past 7 days


class VideoSourceStatItem(BaseModel):
    """One daily data point for a video."""
    id: uuid.UUID
    video_source_id: uuid.UUID
    collected_at: datetime
    view_count: int | None
    like_count: int | None
    favorite_count: int | None
    comment_count: int | None
    share_count: int | None

    model_config = {"from_attributes": True}


class VideoSourceStatHistoryResponse(BaseModel):
    items: list[VideoSourceStatItem]
