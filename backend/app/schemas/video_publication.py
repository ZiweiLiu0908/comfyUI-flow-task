import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class VideoPublicationCreate(BaseModel):
    """创建发布任务请求"""
    sub_task_id: uuid.UUID
    video_url: str
    original_video_url: str | None = None  # 拼接前的原始视频URL，为空时等于video_url
    video_type: str | None = None  # "persona" | "traffic"
    title: str
    description: str | None = None
    tags: list[str] | None = None
    channels: list[dict]  # [{platform, channel_id, title?, description?, tags?, privacy_level?}]
    callback_url: str | None = None


class VideoPublicationChannelStatus(BaseModel):
    """单个渠道的发布状态"""
    platform: str
    channel_id: str
    channel_name: str | None = None
    status: str  # pending, uploading, completed, failed
    platform_video_id: str | None = None
    platform_video_url: str | None = None
    upload_id: int | str | None = None
    error_message: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    uploaded_at: datetime | None = None


class VideoPublicationRead(BaseModel):
    """发布任务读取"""
    id: uuid.UUID
    sub_task_id: uuid.UUID
    open_api_task_id: str | None = None
    external_id: str | None = None
    status: str
    total_channels: int
    completed_channels: int
    failed_channels: int
    channels_status: list[VideoPublicationChannelStatus] | None = None
    metrics_snapshot: "VideoPublicationMetricsSnapshot | None" = None
    promotion_code: str | None = None
    ext_products: list | None = None
    error_message: str | None = None
    callback_received: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class VideoPublicationDetailRead(VideoPublicationRead):
    """发布任务详情（包含请求数据）"""
    request_payload: dict | None = None
    response_data: dict | None = None


class VideoPublicationMetricsVideoInfo(BaseModel):
    thumbnail_url: str | None = None
    duration: int | float | None = None
    published_at: datetime | None = None


class VideoPublicationMetricsStats(BaseModel):
    # TikTok 字段名
    view_count: int | float | None = None
    like_count: int | float | None = None
    comment_count: int | float | None = None
    share_count: int | float | None = None
    # YouTube 字段名
    views: int | float | None = None
    likes: int | float | None = None
    comments: int | float | None = None
    shares: int | float | None = None
    engaged_views: int | float | None = None
    average_view_duration: int | float | None = None
    average_view_percentage: int | float | None = None
    # Instagram 字段名
    reach_count: int | float | None = None
    save_count: int | float | None = None


class VideoPublicationMetricsChannel(BaseModel):
    platform: Literal["tiktok", "youtube", "instagram"] | str
    channel_id: str | None = None
    channel_name: str | None = None
    status: str | None = None
    platform_video_id: str | None = None
    platform_video_url: str | None = None
    video_info: VideoPublicationMetricsVideoInfo | None = None
    stats: VideoPublicationMetricsStats | None = None


class VideoPublicationMetricsSnapshot(BaseModel):
    status: str | None = None
    total_channels: int = 0
    completed_channels: int = 0
    failed_channels: int = 0
    synced_at: datetime | None = None
    channels: list[VideoPublicationMetricsChannel] = Field(default_factory=list)


class VideoPublicationStatsChannel(VideoPublicationMetricsChannel):
    pass


class VideoPublicationStatsListItem(BaseModel):
    id: uuid.UUID
    sub_task_id: uuid.UUID
    task_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    account_name: str | None = None
    account_type: str | None = None
    status: str
    video_url: str | None = None
    published_at: datetime | None = None
    title: str | None = None
    description: str | None = None
    promotion_code: str | None = None
    ext_products: list | None = None
    social_bindings: list | None = None
    channels_status: list[VideoPublicationChannelStatus] | None = None
    metrics_snapshot: VideoPublicationMetricsSnapshot | None = None
    metrics_channels: list[VideoPublicationStatsChannel] = Field(default_factory=list)
    total_views: int = 0
    total_likes: int = 0
    total_comments: int = 0
    total_shares: int = 0
    avg_view_percentage: float | None = None
    kol_link_clicks: int | None = None
    video_click_rate: float | None = None
    category_key: str | None = None
    category_label: str | None = None
    major_category: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class VideoPublicationStatsListResponse(BaseModel):
    items: list[VideoPublicationStatsListItem]
    total: int
    page: int
    page_size: int


class VideoPublicationStatsQuery(BaseModel):
    platform: str | None = None
    account_id: uuid.UUID | None = None
    date_from: date | None = None
    date_to: date | None = None
    keyword: str | None = None
    category_indices: list[str] | None = None
    unclassified: bool = False
    promotion_code_filter: str | None = None  # 'with' | 'without' | None
    sort_by: str = "published_at"
    sort_order: str = "desc"
    page: int = 1
    page_size: int = 20


class VideoPublicationStatusUpdate(BaseModel):
    """更新发布任务状态（用于回调）

    兼容两种回调来源：
    - B 侧（callback.echooo.link）：带 timestamp/signature 等签名字段
    - C 侧 RPA（rpa-linux1:3001）：不带签名字段，body 是完整 task 对象
      （额外字段如 client_id / video_url / channels[].real_channel_id /
      channels[].route / channels[].job_id / channels[].b_task_id 等
      通过 channels: list[dict] passthrough 兼容，model_config 默认 ignore extra）
    """
    task_id: str  # Open API task_id
    external_id: str | None = None
    status: str
    total_channels: int | None = None
    completed_channels: int | None = None
    failed_channels: int | None = None
    channels: list[dict] | None = None
    completed_at: datetime | None = None
    timestamp: int | None = None  # B 侧带，C 侧不带
