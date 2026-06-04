from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ExternalPlatform = Literal["youtube", "tiktok", "instagram"]


class ExternalAccountChannelRead(BaseModel):
    platform: ExternalPlatform | str
    channel_status: str = "active"
    channel_source: str = "openapi"
    channel_id: str | None = None
    channel_name: str | None = None
    username: str | None = None
    avatar_url: str | None = None
    kol_long_link: str | None = None
    kol_short_link: str | None = None
    bound_at: datetime | None = None


class ExternalAccountListItem(BaseModel):
    account_id: uuid.UUID
    account_name: str
    account_handle: str | None = None
    account_signature: str | None = None
    gender: str
    account_type: str
    account_tier: str
    avatar_url: str | None = None
    photo_url: str | None = None
    hashtags: list[str] | None = None
    created_at: datetime
    updated_at: datetime
    platforms: list[ExternalAccountChannelRead] = Field(default_factory=list)


class ExternalAccountListResponse(BaseModel):
    items: list[ExternalAccountListItem]
    total: int
    page: int
    page_size: int


class ExternalVideoMetrics(BaseModel):
    views: int = 0
    likes: int = 0
    comments: int = 0
    shares: int = 0


class ExternalPlatformVideoItem(BaseModel):
    publication_id: uuid.UUID
    task_id: uuid.UUID | None = None
    sub_task_id: uuid.UUID
    status: str
    title: str | None = None
    description: str | None = None
    video_url: str | None = None
    platform_video_id: str | None = None
    platform_video_url: str | None = None
    thumbnail_url: str | None = None
    published_at: datetime | None = None
    promotion_code: str | None = None
    metrics: ExternalVideoMetrics = Field(default_factory=ExternalVideoMetrics)


class ExternalPlatformVideosResponse(BaseModel):
    account_id: uuid.UUID
    platform: ExternalPlatform | str
    channel: ExternalAccountChannelRead
    items: list[ExternalPlatformVideoItem]
    total: int
    page: int
    page_size: int
