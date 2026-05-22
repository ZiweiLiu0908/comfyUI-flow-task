from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text, Uuid
from sqlalchemy.dialects.postgresql import JSON as PGJSON
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    account_name: Mapped[str] = mapped_column(String(200), nullable=False)
    account_handle: Mapped[str | None] = mapped_column(String(200), nullable=True)
    account_signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    account_type: Mapped[str] = mapped_column(String(20), nullable=False, default="exclusive")  # "persona" | "shared" | "exclusive"
    product_code_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="without_code")  # "with_code" | "without_code"
    face_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="face")  # "face" | "no_face"
    gender: Mapped[str] = mapped_column(String(20), nullable=False, default="female")  # "male" | "female" | "unisex"
    account_tier: Mapped[str] = mapped_column(String(20), nullable=False, default="test", index=True)  # "test"=实验号 | "dev"=常规号 | "prod"=正式号
    style_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_appearance: Mapped[str | None] = mapped_column(Text, nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)  # 博主照片（AI选出的候选）
    performance_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    hashtags: Mapped[list | None] = mapped_column(JSON, nullable=True)  # TikTok hashtag 列表
    platform_binding_status: Mapped[str] = mapped_column(String(30), nullable=False, default="unbound", index=True)

    # AI 生成状态
    ai_generation_status: Mapped[str] = mapped_column(String(40), nullable=False, default="idle")
    ai_generation_state: Mapped[dict | None] = mapped_column(PGJSON, nullable=True)  # 生成过程状态
    ai_generation_error: Mapped[str | None] = mapped_column(Text, nullable=True)  # 错误信息

    # 视频分类聚合
    classification_status: Mapped[str] = mapped_column(String(20), nullable=False, default="idle")  # idle | running
    classification_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # single|dual|chaos|insufficient|none
    classification_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Scheduled publish config
    publish_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    publish_cron: Mapped[str | None] = mapped_column(String(100), nullable=True)
    publish_window_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    publish_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    publish_last_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    publish_scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # KOL 创建 + 短链
    kol_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # 站内稳定 user_id（接口 data.user_id），长链 kolUserId 用它
    kol_provision_status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")  # pending | success | failed
    kol_provision_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
