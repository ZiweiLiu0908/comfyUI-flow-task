import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class VideoTask(Base):
    __tablename__ = "video_tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(index=True, nullable=False)
    account_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), index=True, nullable=True)
    template_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), index=True, nullable=True)
    target_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)

    # Status lifecycle: pending → generating → reviewing → stashed/decision_rejected → queued → publishing → published/publish_failed
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True)

    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    is_prompt_updated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    duration: Mapped[str] = mapped_column(String(50), nullable=False)
    shots: Mapped[list | None] = mapped_column(JSON, nullable=True)
    has_face: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # 是否走「有CTA」一套提示词（创建任务时按 account.product_code_mode 计算：with_code=True）
    cta: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # AI 模板成功写回 shots 后标记为 True，一键重试时跳过已处理完成的任务
    ai_retry_done: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 模板复用审计：所有使用已使用模板创建的总任务都会打标，原因用于队列优先级和排查。
    is_reused_template: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    template_reuse_reason: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    template_usage_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    template_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    template_usage_source: Mapped[str | None] = mapped_column(String(30), nullable=True)
    template_usage_source_step: Mapped[str | None] = mapped_column(String(60), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    sub_tasks: Mapped[list["VideoSubTask"]] = relationship(
        "VideoSubTask",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="VideoSubTask.sub_index",
    )


class VideoSubTask(Base):
    __tablename__ = "video_sub_tasks"
    __table_args__ = (
        UniqueConstraint("task_id", "sub_index", name="uq_video_sub_tasks_task_sub_index"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("video_tasks.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    sub_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # Status lifecycle: pending → generating → reviewing → stashed/decision_rejected → queued → publishing → published/publish_failed
    # stashed: user approved the video; score-based routing decides queued or abandoned
    # decision_rejected: user explicitly rejected the video
    # abandoned: system-abandoned (e.g. sibling selected, or score too low)
    # publish_failed: video was sent to publishing but the publication failed (can retry → stashed)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True)

    # 视频 URL：GCS 后端时存的是 V4 签名链（7 天）；旧 CDN 后端时是公开 CDN 链接。
    # GCS 签名快过期前会被 app.utils.gcs_signing 自动续签并直接覆写本列。
    # 详见 app.utils.gcs_signing.ensure_sub_task_signed_url。
    result_video_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Manual note written by the user
    manual_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Operator: the reviewer who submitted the note/score (for aggregation)
    operator: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    # NG (穿帮) detection: simplified
    has_ng: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # List of NG timestamps: [{"second": 10, "frame": 5}, ...]
    ng_timestamps: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Multi-dimension scoring: {"audio_visual": 3, "character_realism": 4, ...}
    dimension_scores: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Weighted total score 0-100 (computed from dimension_scores)
    weighted_total_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # True when this sub-task's video was chosen by the user for publishing
    selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Queue order for manual sorting in publish queue (only used when status=queued)
    queue_order: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Pre-generated publish metadata (title, description, hashtags) produced when sub-task enters queued.
    # Format: {"status": "pending"|"generating"|"done"|"failed", "title": "...", "description": "...", "hashtags": [...]}
    publish_meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    task: Mapped["VideoTask"] = relationship("VideoTask", back_populates="sub_tasks")
    publications: Mapped[list["VideoPublication"]] = relationship(
        "VideoPublication",
        back_populates="sub_task",
        cascade="all, delete-orphan",
    )
