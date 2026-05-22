from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PipelineSetting(Base):
    __tablename__ = "pipeline_settings"

    owner_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)

    # 视频理解（在 outfit_detailing 之后执行）— 共用 model/temperature
    understand_model: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    understand_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")  # 兼容遗留列，已弃用
    understand_temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.3)
    # 视频理解 - 4 个分支 prompt（按 content_intent 选择）
    understand_prompt_beauty_show: Mapped[str] = mapped_column(Text, nullable=False, default="")
    understand_prompt_knowledge: Mapped[str] = mapped_column(Text, nullable=False, default="")
    understand_prompt_persona_story: Mapped[str] = mapped_column(Text, nullable=False, default="")
    understand_prompt_trend_meme: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # 意图识别（intent_classify）— JSON 输出，在 outfit_detailing 之后、视频理解之前
    intent_classify_model: Mapped[str] = mapped_column(String(200), nullable=False, default="gemini-3.1-pro-preview")
    intent_classify_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    intent_classify_temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.3)

    # 第二阶段：抽帧生图（Nano2）
    imagegen_model: Mapped[str] = mapped_column(String(200), nullable=False, default="gemini-3.1-flash-image-preview")
    imagegen_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    imagegen_size: Mapped[str] = mapped_column(String(20), nullable=False, default="9:16")
    imagegen_quality: Mapped[str] = mapped_column(String(10), nullable=False, default="2K")

    # 第三阶段：拆分图片（Segment API）
    splitting_api_url: Mapped[str] = mapped_column(String(500), nullable=False, default="http://34.21.127.95:8080")

    # 第四阶段：去脸（Face Removing API）
    face_removing_api_url: Mapped[str] = mapped_column(String(500), nullable=False, default="http://34.86.216.234:8001")
    face_removing_score_thresh: Mapped[float] = mapped_column(Float, nullable=False, default=0.3)
    face_removing_margin_scale: Mapped[float] = mapped_column(Float, nullable=False, default=0.2)
    face_removing_head_top_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)

    # 第五阶段：图片超分（Pillow LANCZOS）
    upscaling_scale: Mapped[int] = mapped_column(nullable=False, default=1024)

    # 步骤2b：Gemini 识别 Unique 穿搭
    outfit_select_model: Mapped[str] = mapped_column(String(200), nullable=False, default="gemini-3.1-pro-preview")
    outfit_select_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    outfit_select_temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.3)

    # 步骤3a：对每个 unique 穿搭图理解单品
    outfit_detail_model: Mapped[str] = mapped_column(String(200), nullable=False, default="gemini-3.1-pro-preview")
    outfit_detail_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    outfit_detail_temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.3)

    # 步骤3b：单品图生成
    product_imagegen_model: Mapped[str] = mapped_column(String(200), nullable=False, default="gemini-3.1-flash-image-preview")
    product_imagegen_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    product_imagegen_size: Mapped[str] = mapped_column(String(20), nullable=False, default="1:1")
    product_imagegen_quality: Mapped[str] = mapped_column(String(10), nullable=False, default="2K")

    # 步骤3c：新造型图生成
    outfit_regen_model: Mapped[str] = mapped_column(String(200), nullable=False, default="gemini-3.1-flash-image-preview")
    outfit_regen_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    outfit_regen_size: Mapped[str] = mapped_column(String(20), nullable=False, default="9:16")
    outfit_regen_quality: Mapped[str] = mapped_column(String(10), nullable=False, default="2K")

    # AI 账号生成配置
    ai_account_analysis_sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    ai_account_video_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ai_account_video_model: Mapped[str] = mapped_column(String(200), nullable=False, default="gemini-3.1-pro-preview")
    ai_account_name_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ai_account_avatar_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ai_account_photo_image_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ai_account_name_model: Mapped[str] = mapped_column(String(200), nullable=False, default="gemini-3.1-pro-preview")
    ai_account_avatar_model: Mapped[str] = mapped_column(String(200), nullable=False, default="gemini-3.1-flash-image-preview")
    # 批量生成名称/handle/签名 Prompt（两个分支）
    ai_account_exclusive_name_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ai_account_shared_name_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    ai_account_avatar_size: Mapped[str] = mapped_column(String(20), nullable=False, default="1:1")
    ai_account_avatar_quality: Mapped[str] = mapped_column(String(10), nullable=False, default="1K")

    # 标签搜索（Hashtag Search）
    hashtag_search_top_n: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    hashtag_filter_model: Mapped[str] = mapped_column(String(200), nullable=False, default="gemini-3.1-pro-preview")
    hashtag_filter_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # 关键词生成配置
    keyword_gen_model: Mapped[str] = mapped_column(String(200), nullable=False, default="gemini-3.1-pro-preview")
    keyword_gen_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    keyword_gen_count: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    keyword_gen_temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)

    # 候选库搜索配置（按用户独立）
    candidate_max_bloggers: Mapped[int] = mapped_column(Integer, nullable=False, default=20)
    candidate_exclusive_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    candidate_max_videos_per_blogger: Mapped[int] = mapped_column(Integer, nullable=False, default=100)
    candidate_max_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    candidate_retry_delay_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    candidate_min_play_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    candidate_publish_after_date: Mapped[str | None] = mapped_column(String(20), nullable=True)  # 格式 YYYY-MM-DD，空=不限制
    candidate_shared_top_n: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    # 候选库 AI 审核配置
    candidate_ai_review_enabled: Mapped[bool] = mapped_column(nullable=False, default=False)
    candidate_ai_review_model: Mapped[str] = mapped_column(String(200), nullable=False, default="gemini-3.1-pro-preview")
    candidate_ai_review_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # 候选库定时抓取
    candidate_schedule_enabled: Mapped[bool] = mapped_column(nullable=False, default=False)
    candidate_schedule_cron: Mapped[str | None] = mapped_column(String(100), nullable=True)
    candidate_search_interval_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0=不间隔
    # 人脸选择配置
    face_select_model: Mapped[str] = mapped_column(String(200), nullable=False, default="gemini-3.1-pro-preview")
    face_select_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # 视频分类配置
    video_classify_model: Mapped[str] = mapped_column(String(200), nullable=False, default="gemini-3.1-pro-preview")
    video_classify_prompt: Mapped[str] = mapped_column(Text, nullable=False, default="")
    video_classify_temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.7)

    # 视频分类聚合阈值
    classify_min_sample: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    classify_single_top1_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    classify_single_diff_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.15)
    classify_dual_top1_lower: Mapped[float] = mapped_column(Float, nullable=False, default=0.35)
    classify_dual_top1_upper: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    classify_dual_top2_threshold: Mapped[float] = mapped_column(Float, nullable=False, default=0.2)

    # 账号分级判定规则（test=实验号 / dev=常规号 / prod=正式号）
    tier_video_sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=7)        # 最近 N 条视频
    tier_avg_play_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=700)      # 均播阈值
    tier_activity_days: Mapped[int] = mapped_column(Integer, nullable=False, default=7)             # 最近 N 天
    tier_min_video_count: Mapped[int] = mapped_column(Integer, nullable=False, default=6)           # 最近 N 天最少发视频数
    tier_daily_formal_growth_min_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)   # 正式号每日新增比例下限
    tier_daily_formal_growth_max_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.06)  # 正式号每日新增比例上限

    # 「最近 N 条子任务的成功率」公式里 N 的样本量
    sub_task_success_sample_size: Mapped[int] = mapped_column(Integer, nullable=False, default=10)

    # Shadowban 判定：最近 N 条有播放量数据的视频均 <= 阈值则标记账号
    shadowban_video_sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=7)
    shadowban_view_threshold: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # 「有CTA」版本的 9 个 prompt（与同名无 _cta 字段对应；启用见 video_task.cta）
    outfit_select_prompt_cta: Mapped[str] = mapped_column(Text, nullable=False, default="")
    outfit_detail_prompt_cta: Mapped[str] = mapped_column(Text, nullable=False, default="")
    intent_classify_prompt_cta: Mapped[str] = mapped_column(Text, nullable=False, default="")
    understand_prompt_beauty_show_cta: Mapped[str] = mapped_column(Text, nullable=False, default="")
    understand_prompt_knowledge_cta: Mapped[str] = mapped_column(Text, nullable=False, default="")
    understand_prompt_persona_story_cta: Mapped[str] = mapped_column(Text, nullable=False, default="")
    understand_prompt_trend_meme_cta: Mapped[str] = mapped_column(Text, nullable=False, default="")
    product_imagegen_prompt_cta: Mapped[str] = mapped_column(Text, nullable=False, default="")
    outfit_regen_prompt_cta: Mapped[str] = mapped_column(Text, nullable=False, default="")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
