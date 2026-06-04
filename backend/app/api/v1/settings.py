from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenData, require_current_user
from app.db.session import get_db
from app.schemas.settings import (
    CandidateConfigPayload,
    PipelineSettingsPayload,
    ScheduledGenerationConfigPayload,
    TemplateSupplementConfigPayload,
)
from app.schemas.topic import KeywordGenConfigPayload
from app.services.channel_status_poller import run_channel_status_check
from app.services.channel_name_sync_scheduler import run_channel_name_sync
from app.services.pipeline_settings_service import get_or_create_pipeline_settings, update_pipeline_settings
from app.services.system_settings_service import get_or_create_system_settings

router = APIRouter(prefix="/settings", tags=["settings"])
logger = logging.getLogger("app.settings")


# ---------------------------------------------------------------------------
# System settings (global, single-row)
# ---------------------------------------------------------------------------

class SystemSettingsPayload(BaseModel):
    use_seedance_api: bool = False


@router.get("/system", response_model=SystemSettingsPayload)
async def get_system_settings(
    token: TokenData = Depends(require_current_user),
    session: AsyncSession = Depends(get_db),
) -> SystemSettingsPayload:
    row = await get_or_create_system_settings(session)
    return SystemSettingsPayload(use_seedance_api=row.use_seedance_api)


@router.put("/system", response_model=SystemSettingsPayload)
async def put_system_settings(
    payload: SystemSettingsPayload,
    token: TokenData = Depends(require_current_user),
    session: AsyncSession = Depends(get_db),
) -> SystemSettingsPayload:
    row = await get_or_create_system_settings(session)
    row.use_seedance_api = payload.use_seedance_api
    await session.commit()
    await session.refresh(row)
    return SystemSettingsPayload(use_seedance_api=row.use_seedance_api)


# ---------------------------------------------------------------------------
# 手动触发频道状态检查
# ---------------------------------------------------------------------------

@router.post("/check-channel-status")
async def trigger_check_channel_status(
    token: TokenData = Depends(require_current_user),
) -> dict:
    """立即执行一次频道授权状态检查（通常每小时自动触发一次）。"""
    result = await run_channel_status_check()
    return {"status": "ok", "checked": result["checked"], "changed": result["changed"]}


def _format_sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.get("/check-channel-status/stream")
async def stream_check_channel_status(
    request: Request,
    token: TokenData = Depends(require_current_user),
) -> StreamingResponse:
    """以 SSE 方式流式执行频道授权状态检查。"""
    async def event_stream():
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        async def emit(event: str, payload: dict) -> None:
            await queue.put(_format_sse(event, payload))

        async def run_check() -> None:
            try:
                await emit("queued", {"message": "检查任务已创建，等待执行"})
                await run_channel_status_check(
                    progress_callback=lambda payload: emit(payload["event"], payload),
                    should_stop=request.is_disconnected,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Streamed channel status check failed")
                await emit("error", {"message": "频道状态检查失败，请稍后重试"})
            finally:
                await queue.put(None)

        worker = asyncio.create_task(run_check())

        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
                if await request.is_disconnected():
                    break
        finally:
            if not worker.done():
                worker.cancel()
                try:
                    await worker
                except asyncio.CancelledError:
                    pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# 手动触发频道名称同步
# ---------------------------------------------------------------------------

@router.post("/sync-channel-names")
async def trigger_sync_channel_names(
    token: TokenData = Depends(require_current_user),
) -> dict:
    result = await run_channel_name_sync()
    return {"status": "ok", "checked": result["checked"], "updated": result["updated"]}


@router.get("/sync-channel-names/stream")
async def stream_sync_channel_names(
    request: Request,
    token: TokenData = Depends(require_current_user),
) -> StreamingResponse:
    """以 SSE 方式流式执行频道名称同步。"""
    async def event_stream():
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        async def emit(event: str, payload: dict) -> None:
            await queue.put(_format_sse(event, payload))

        async def run_sync() -> None:
            try:
                await emit("queued", {"message": "同步任务已创建，等待执行"})
                await run_channel_name_sync(
                    progress_callback=lambda payload: emit(payload["event"], payload),
                    should_stop=request.is_disconnected,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Streamed channel name sync failed")
                await emit("error", {"message": "频道名称同步失败，请稍后重试"})
            finally:
                await queue.put(None)

        worker = asyncio.create_task(run_sync())

        try:
            while True:
                item = await queue.get()
                if item is None:
                    break
                yield item
                if await request.is_disconnected():
                    break
        finally:
            if not worker.done():
                worker.cancel()
                try:
                    await worker
                except asyncio.CancelledError:
                    pass

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Pipeline settings (per-user)
# ---------------------------------------------------------------------------

@router.get("/pipeline", response_model=PipelineSettingsPayload)
async def get_pipeline_settings(
    token: TokenData = Depends(require_current_user),
    session: AsyncSession = Depends(get_db),
) -> PipelineSettingsPayload:
    row = await get_or_create_pipeline_settings(session, owner_id=token.user_id)
    return PipelineSettingsPayload.model_validate(row, from_attributes=True)


@router.put("/pipeline", response_model=PipelineSettingsPayload)
async def put_pipeline_settings(
    payload: PipelineSettingsPayload,
    token: TokenData = Depends(require_current_user),
    session: AsyncSession = Depends(get_db),
) -> PipelineSettingsPayload:
    row = await update_pipeline_settings(session, owner_id=token.user_id, payload=payload)
    return PipelineSettingsPayload.model_validate(row, from_attributes=True)


# ---------------------------------------------------------------------------
# 定时一键生成配置（per-user）
# ---------------------------------------------------------------------------

@router.get("/scheduled-generation-config", response_model=ScheduledGenerationConfigPayload)
async def get_scheduled_generation_config(
    token: TokenData = Depends(require_current_user),
    session: AsyncSession = Depends(get_db),
) -> ScheduledGenerationConfigPayload:
    row = await get_or_create_pipeline_settings(session, owner_id=token.user_id)
    return ScheduledGenerationConfigPayload(
        scheduled_generation_enabled=row.scheduled_generation_enabled,
        scheduled_generation_cron=row.scheduled_generation_cron or "0 10 * * *",
        scheduled_generation_lookback_days=row.scheduled_generation_lookback_days or 2,
        scheduled_generation_target_unpublished_count=row.scheduled_generation_target_unpublished_count or 5,
        scheduled_generation_subtask_count=row.scheduled_generation_subtask_count or 1,
        scheduled_generation_unused_template_months=row.scheduled_generation_unused_template_months or 3,
        scheduled_generation_used_template_cooldown_days=row.scheduled_generation_used_template_cooldown_days or 30,
        scheduled_generation_category_rules=row.scheduled_generation_category_rules or {},
    )


@router.put("/scheduled-generation-config", response_model=ScheduledGenerationConfigPayload)
async def put_scheduled_generation_config(
    payload: ScheduledGenerationConfigPayload,
    token: TokenData = Depends(require_current_user),
    session: AsyncSession = Depends(get_db),
) -> ScheduledGenerationConfigPayload:
    row = await get_or_create_pipeline_settings(session, owner_id=token.user_id)
    row.scheduled_generation_enabled = bool(payload.scheduled_generation_enabled)
    row.scheduled_generation_cron = payload.scheduled_generation_cron or "0 10 * * *"
    row.scheduled_generation_lookback_days = max(int(payload.scheduled_generation_lookback_days or 2), 1)
    row.scheduled_generation_target_unpublished_count = max(int(payload.scheduled_generation_target_unpublished_count or 5), 1)
    row.scheduled_generation_subtask_count = max(int(payload.scheduled_generation_subtask_count or 1), 1)
    row.scheduled_generation_unused_template_months = max(int(payload.scheduled_generation_unused_template_months or 3), 1)
    row.scheduled_generation_used_template_cooldown_days = max(int(payload.scheduled_generation_used_template_cooldown_days or 30), 1)
    row.scheduled_generation_category_rules = payload.scheduled_generation_category_rules or {}
    await session.commit()
    await session.refresh(row)
    return ScheduledGenerationConfigPayload(
        scheduled_generation_enabled=row.scheduled_generation_enabled,
        scheduled_generation_cron=row.scheduled_generation_cron,
        scheduled_generation_lookback_days=row.scheduled_generation_lookback_days,
        scheduled_generation_target_unpublished_count=row.scheduled_generation_target_unpublished_count,
        scheduled_generation_subtask_count=row.scheduled_generation_subtask_count,
        scheduled_generation_unused_template_months=row.scheduled_generation_unused_template_months,
        scheduled_generation_used_template_cooldown_days=row.scheduled_generation_used_template_cooldown_days,
        scheduled_generation_category_rules=row.scheduled_generation_category_rules or {},
    )


# ---------------------------------------------------------------------------
# Keyword generation config (per-user, isolated save)
# ---------------------------------------------------------------------------

@router.get("/keyword-gen-config", response_model=KeywordGenConfigPayload)
async def get_keyword_gen_config(
    token: TokenData = Depends(require_current_user),
    session: AsyncSession = Depends(get_db),
) -> KeywordGenConfigPayload:
    row = await get_or_create_pipeline_settings(session, owner_id=token.user_id)
    return KeywordGenConfigPayload(
        keyword_gen_model=row.keyword_gen_model,
        keyword_gen_prompt=row.keyword_gen_prompt,
        keyword_gen_count=row.keyword_gen_count,
        keyword_gen_temperature=row.keyword_gen_temperature,
    )


@router.put("/keyword-gen-config", response_model=KeywordGenConfigPayload)
async def put_keyword_gen_config(
    payload: KeywordGenConfigPayload,
    token: TokenData = Depends(require_current_user),
    session: AsyncSession = Depends(get_db),
) -> KeywordGenConfigPayload:
    row = await get_or_create_pipeline_settings(session, owner_id=token.user_id)
    updates = payload.model_dump(exclude_none=True)
    for field, value in updates.items():
        setattr(row, field, value)
    await session.commit()
    await session.refresh(row)
    return KeywordGenConfigPayload(
        keyword_gen_model=row.keyword_gen_model,
        keyword_gen_prompt=row.keyword_gen_prompt,
        keyword_gen_count=row.keyword_gen_count,
        keyword_gen_temperature=row.keyword_gen_temperature,
    )


# ---------------------------------------------------------------------------
# 候选库配置（per-user，独立保存）
# ---------------------------------------------------------------------------

@router.get("/candidate-config", response_model=CandidateConfigPayload)
async def get_candidate_config(
    token: TokenData = Depends(require_current_user),
    session: AsyncSession = Depends(get_db),
) -> CandidateConfigPayload:
    row = await get_or_create_pipeline_settings(session, owner_id=token.user_id)
    return CandidateConfigPayload(
        candidate_max_bloggers=row.candidate_max_bloggers,
        candidate_exclusive_threshold=row.candidate_exclusive_threshold,
        candidate_max_videos_per_blogger=row.candidate_max_videos_per_blogger,
        candidate_max_duration_seconds=row.candidate_max_duration_seconds,
        candidate_retry_delay_seconds=row.candidate_retry_delay_seconds,
        candidate_min_play_count=row.candidate_min_play_count,
        candidate_publish_after_date=row.candidate_publish_after_date,
        candidate_shared_top_n=row.candidate_shared_top_n,
        candidate_ai_review_enabled=row.candidate_ai_review_enabled,
        candidate_ai_review_model=row.candidate_ai_review_model,
        candidate_ai_review_prompt=row.candidate_ai_review_prompt,
        candidate_schedule_enabled=row.candidate_schedule_enabled,
        candidate_schedule_cron=row.candidate_schedule_cron,
    )


@router.put("/candidate-config", response_model=CandidateConfigPayload)
async def put_candidate_config(
    payload: CandidateConfigPayload,
    token: TokenData = Depends(require_current_user),
    session: AsyncSession = Depends(get_db),
) -> CandidateConfigPayload:
    row = await get_or_create_pipeline_settings(session, owner_id=token.user_id)
    row.candidate_max_bloggers = payload.candidate_max_bloggers
    row.candidate_exclusive_threshold = payload.candidate_exclusive_threshold
    row.candidate_max_videos_per_blogger = payload.candidate_max_videos_per_blogger
    row.candidate_max_duration_seconds = payload.candidate_max_duration_seconds
    row.candidate_retry_delay_seconds = payload.candidate_retry_delay_seconds
    row.candidate_min_play_count = payload.candidate_min_play_count
    row.candidate_publish_after_date = payload.candidate_publish_after_date
    row.candidate_shared_top_n = payload.candidate_shared_top_n
    row.candidate_ai_review_enabled = payload.candidate_ai_review_enabled
    row.candidate_ai_review_model = payload.candidate_ai_review_model
    row.candidate_ai_review_prompt = payload.candidate_ai_review_prompt
    row.candidate_schedule_enabled = payload.candidate_schedule_enabled
    row.candidate_schedule_cron = payload.candidate_schedule_cron
    await session.commit()
    await session.refresh(row)
    return CandidateConfigPayload(
        candidate_max_bloggers=row.candidate_max_bloggers,
        candidate_exclusive_threshold=row.candidate_exclusive_threshold,
        candidate_max_videos_per_blogger=row.candidate_max_videos_per_blogger,
        candidate_max_duration_seconds=row.candidate_max_duration_seconds,
        candidate_retry_delay_seconds=row.candidate_retry_delay_seconds,
        candidate_min_play_count=row.candidate_min_play_count,
        candidate_publish_after_date=row.candidate_publish_after_date,
        candidate_shared_top_n=row.candidate_shared_top_n,
        candidate_ai_review_enabled=row.candidate_ai_review_enabled,
        candidate_ai_review_model=row.candidate_ai_review_model,
        candidate_ai_review_prompt=row.candidate_ai_review_prompt,
        candidate_schedule_enabled=row.candidate_schedule_enabled,
        candidate_schedule_cron=row.candidate_schedule_cron,
    )


# ---------------------------------------------------------------------------
# 模板定时补充配置（per-user）
# ---------------------------------------------------------------------------

@router.get("/template-supplement-config", response_model=TemplateSupplementConfigPayload)
async def get_template_supplement_config(
    token: TokenData = Depends(require_current_user),
    session: AsyncSession = Depends(get_db),
) -> TemplateSupplementConfigPayload:
    row = await get_or_create_pipeline_settings(session, owner_id=token.user_id)
    return TemplateSupplementConfigPayload(
        template_supplement_schedule_enabled=row.template_supplement_schedule_enabled,
        template_supplement_schedule_cron=row.template_supplement_schedule_cron or "0 10 * * *",
        template_supplement_target_unused_count=row.template_supplement_target_unused_count or 10,
        template_supplement_filters=row.template_supplement_filters or {},
        template_supplement_max_rounds=row.template_supplement_max_rounds or 2,
    )


@router.put("/template-supplement-config", response_model=TemplateSupplementConfigPayload)
async def put_template_supplement_config(
    payload: TemplateSupplementConfigPayload,
    token: TokenData = Depends(require_current_user),
    session: AsyncSession = Depends(get_db),
) -> TemplateSupplementConfigPayload:
    row = await get_or_create_pipeline_settings(session, owner_id=token.user_id)
    row.template_supplement_schedule_enabled = bool(payload.template_supplement_schedule_enabled)
    row.template_supplement_schedule_cron = payload.template_supplement_schedule_cron or "0 10 * * *"
    row.template_supplement_target_unused_count = max(int(payload.template_supplement_target_unused_count or 10), 1)
    row.template_supplement_filters = payload.template_supplement_filters or {}
    row.template_supplement_max_rounds = max(int(payload.template_supplement_max_rounds or 2), 1)
    await session.commit()
    await session.refresh(row)
    return TemplateSupplementConfigPayload(
        template_supplement_schedule_enabled=row.template_supplement_schedule_enabled,
        template_supplement_schedule_cron=row.template_supplement_schedule_cron,
        template_supplement_target_unused_count=row.template_supplement_target_unused_count,
        template_supplement_filters=row.template_supplement_filters or {},
        template_supplement_max_rounds=row.template_supplement_max_rounds,
    )
