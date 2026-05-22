import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, JSON, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class VideoPublication(Base):
    """
    视频发布任务表
    追踪通过 Open API 发布视频的任务状态
    """
    __tablename__ = "video_publications"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # 关联的子任务
    sub_task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("video_sub_tasks.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # Open API 返回的任务 ID
    open_api_task_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    # 外部 ID（用于关联 Open API 的 external_id，这里使用 sub_task_id）
    external_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # 发布状态（从 Open API 同步）
    # pending → processing → uploading → completed/partial/failed
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True)

    # 发布请求数据（用于重试和审计）
    request_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 带货口令：8位数字字符串，发布时生成并传给外部发布接口
    promotion_code: Mapped[str | None] = mapped_column(String(8), nullable=True, unique=True)

    # 外部商品信息快照；发布时从 video_tasks.shots[].ext_products 聚合
    ext_products: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Open API 返回的完整响应
    response_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 各渠道发布状态（Open API 返回的列表格式）
    channels_status: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # 发布后指标快照（由外部同步或人工写入）
    metrics_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 发布满 24h 后的点击/播放快照，用于统计页 CTR 固化
    click_metrics_24h_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 格式: [
    #   {
    #     "platform": "youtube", "channel_id": "UCxxx", "channel_name": "...",
    #     "status": "completed",  # pending / uploading / completed / failed
    #     "platform_video_id": "Nf4DjLPXaEY", "platform_video_url": "https://...",
    #     "upload_id": 16, "error_message": null,
    #     "created_at": "...", "updated_at": "...", "uploaded_at": "..."
    #   },
    #   {
    #     "platform": "tiktok", "channel_id": "...", "channel_name": "...",
    #     "status": "failed", "platform_video_id": null, "platform_video_url": null,
    #     "upload_id": 18, "error_message": "Failed to download video",
    #     "created_at": "...", "updated_at": "...", "uploaded_at": null
    #   }
    # ]

    # 统计信息
    total_channels: Mapped[int] = mapped_column(default=0)
    completed_channels: Mapped[int] = mapped_column(default=0)
    failed_channels: Mapped[int] = mapped_column(default=0)

    # 回调信息
    callback_received: Mapped[bool] = mapped_column(Boolean, default=False)
    callback_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # 错误信息
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # 关系
    sub_task: Mapped["VideoSubTask"] = relationship(
        "VideoSubTask",
        back_populates="publications",
    )
