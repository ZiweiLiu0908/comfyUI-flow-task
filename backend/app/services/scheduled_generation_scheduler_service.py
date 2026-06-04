"""Scheduled one-click generation scheduler."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from croniter import croniter
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.pipeline_setting import PipelineSetting
from app.services.scheduled_generation_service import execute_scheduled_generation_for_owner


logger = logging.getLogger("app.scheduled_generation_scheduler")

_TZ = ZoneInfo("Asia/Shanghai")
_POLL_INTERVAL_SECONDS = 60
_DEFAULT_CRON = "0 10 * * *"

_scheduler_task: asyncio.Task | None = None
_scheduler_stop_event: asyncio.Event | None = None
_fired: dict[str, str] = {}


def start_scheduled_generation_scheduler() -> None:
    global _scheduler_task, _scheduler_stop_event
    if _scheduler_task is not None and not _scheduler_task.done():
        return
    _scheduler_stop_event = asyncio.Event()
    _scheduler_task = asyncio.get_running_loop().create_task(_start_scheduler_with_prefill(_scheduler_stop_event))
    logger.info("【定时一键生成调度器】已启动")


async def stop_scheduled_generation_scheduler() -> None:
    global _scheduler_task, _scheduler_stop_event
    stop_event, worker = _scheduler_stop_event, _scheduler_task
    _scheduler_stop_event = None
    _scheduler_task = None
    if stop_event:
        stop_event.set()
    if worker:
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass
    logger.info("【定时一键生成调度器】已停止")


async def _start_scheduler_with_prefill(stop_event: asyncio.Event) -> None:
    await _prefill_fired()
    await _scheduler_loop(stop_event)


async def _prefill_fired() -> None:
    try:
        now_local = datetime.now(timezone.utc).astimezone(_TZ)
        async with SessionLocal() as session:
            rows = list((await session.execute(
                select(PipelineSetting).where(PipelineSetting.scheduled_generation_enabled.is_(True))
            )).scalars().all())
        for row in rows:
            cron_expr = (row.scheduled_generation_cron or _DEFAULT_CRON).strip()
            if not croniter.is_valid(cron_expr):
                continue
            prev_fire = croniter(cron_expr, now_local, ret_type=datetime).get_prev(datetime)
            _fired[str(row.owner_id)] = prev_fire.strftime("%Y-%m-%d %H:%M")
    except Exception:
        logger.exception("【定时一键生成调度器】预填触发记录失败")


async def _scheduler_loop(stop_event: asyncio.Event) -> None:
    try:
        while not stop_event.is_set():
            try:
                await _run_once()
            except Exception:
                logger.exception("【定时一键生成调度器】轮询异常")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=_POLL_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                continue
    except asyncio.CancelledError:
        raise


async def _run_once() -> None:
    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone(_TZ)
    async with SessionLocal() as session:
        rows = list((await session.execute(
            select(PipelineSetting).where(PipelineSetting.scheduled_generation_enabled.is_(True))
        )).scalars().all())
    for row in rows:
        try:
            await _process_owner(row, now_utc=now_utc, now_local=now_local)
        except Exception:
            logger.exception("【定时一键生成调度器】处理用户 %s 失败", row.owner_id)


async def _process_owner(row: PipelineSetting, *, now_utc: datetime, now_local: datetime) -> None:
    cron_expr = (row.scheduled_generation_cron or _DEFAULT_CRON).strip()
    if not croniter.is_valid(cron_expr):
        logger.warning("【定时一键生成调度器】用户 %s cron 无效：%s", row.owner_id, cron_expr)
        return

    prev_fire_local = croniter(cron_expr, now_local, ret_type=datetime).get_prev(datetime)
    prev_fire_key = prev_fire_local.strftime("%Y-%m-%d %H:%M")
    prev_fire_utc = prev_fire_local.astimezone(timezone.utc)
    seconds_since_fire = (now_utc - prev_fire_utc).total_seconds()
    if seconds_since_fire < 0 or seconds_since_fire >= _POLL_INTERVAL_SECONDS * 1.5:
        return

    owner_key = str(row.owner_id)
    if _fired.get(owner_key) == prev_fire_key or row.scheduled_generation_last_trigger_key == prev_fire_key:
        return
    _fired[owner_key] = prev_fire_key

    async with SessionLocal() as session:
        current = await session.get(PipelineSetting, row.owner_id)
        if current is not None:
            current.scheduled_generation_last_trigger_key = prev_fire_key
            await session.commit()

    async with SessionLocal() as session:
        await execute_scheduled_generation_for_owner(
            session,
            owner_id=row.owner_id,
            trigger_key=prev_fire_key,
            now_local=now_local,
            config={
                "lookback_days": row.scheduled_generation_lookback_days or 2,
                "target_unpublished_count": row.scheduled_generation_target_unpublished_count or 5,
                "subtask_count": row.scheduled_generation_subtask_count or 1,
                "unused_template_months": row.scheduled_generation_unused_template_months or 3,
                "used_template_cooldown_days": row.scheduled_generation_used_template_cooldown_days or 30,
                "category_rules": row.scheduled_generation_category_rules or {},
            },
        )
