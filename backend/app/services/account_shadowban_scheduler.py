"""
Account shadowban scheduler
===========================
每天北京时间 08:30 扫描 AI 博主最近有播放量数据的 N 条发布视频：
若这些视频播放量均 <= 阈值，则把账号状态置为 shadowban。shadowban 状态不可自动恢复。
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from croniter import croniter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.pipeline_setting import PipelineSetting
from app.models.video_publication import VideoPublication
from app.models.video_task import VideoSubTask, VideoTask

logger = logging.getLogger("app.account_shadowban_scheduler")

_CRON_EXPR = "30 8 * * *"
_POLL_INTERVAL_SECONDS = 60
_TZ = ZoneInfo("Asia/Shanghai")

_scheduler_task: asyncio.Task | None = None
_scheduler_stop_event: asyncio.Event | None = None
_last_fire_key: str | None = None
_run_lock = asyncio.Lock()


@dataclass
class ShadowbanThresholds:
    video_sample_count: int = 7
    view_threshold: int = 0


def _to_non_negative_int(value) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _views_from_snapshot(snapshot) -> int | None:
    if not isinstance(snapshot, dict):
        return None
    total = 0
    has_value = False
    for channel in snapshot.get("channels") or []:
        if not isinstance(channel, dict):
            continue
        stats = channel.get("stats") or {}
        if not isinstance(stats, dict):
            continue
        platform = str(channel.get("platform") or "").lower()
        keys = ("views", "view_count") if platform == "youtube" else ("view_count", "views")
        for key in keys:
            if key in stats:
                value = _to_non_negative_int(stats.get(key))
                if value is not None:
                    total += value
                    has_value = True
                    break
    return total if has_value else None


async def _load_thresholds_by_owner(
    session: AsyncSession,
    owner_ids: set[uuid.UUID],
) -> dict[uuid.UUID, ShadowbanThresholds]:
    if not owner_ids:
        return {}
    rows = (
        await session.execute(
            select(PipelineSetting).where(PipelineSetting.owner_id.in_(owner_ids))
        )
    ).scalars().all()
    result: dict[uuid.UUID, ShadowbanThresholds] = {}
    for row in rows:
        result[row.owner_id] = ShadowbanThresholds(
            video_sample_count=max(int(row.shadowban_video_sample_count or 7), 1),
            view_threshold=max(int(row.shadowban_view_threshold or 0), 0),
        )
    return result


async def run_shadowban_evaluation(
    session: AsyncSession,
    owner_id: uuid.UUID | None = None,
) -> dict:
    account_stmt = select(Account).where(Account.platform_binding_status != "shadowban")
    if owner_id is not None:
        account_stmt = account_stmt.where(Account.owner_id == owner_id)
    accounts = list((await session.execute(account_stmt)).scalars().all())
    if not accounts:
        return {"checked": 0, "updated": 0, "insufficient": 0}

    account_ids = [account.id for account in accounts]
    owner_ids = {account.owner_id for account in accounts if account.owner_id is not None}
    thresholds_by_owner = await _load_thresholds_by_owner(session, owner_ids)

    rows = (
        await session.execute(
            select(
                VideoTask.account_id,
                VideoPublication.metrics_snapshot,
                VideoPublication.completed_at,
                VideoPublication.created_at,
            )
            .join(VideoSubTask, VideoSubTask.id == VideoPublication.sub_task_id)
            .join(VideoTask, VideoTask.id == VideoSubTask.task_id)
            .where(VideoTask.account_id.in_(account_ids))
            .where(VideoPublication.status.in_(["completed", "partial"]))
            .order_by(
                VideoTask.account_id,
                VideoPublication.completed_at.desc().nullslast(),
                VideoPublication.created_at.desc(),
            )
        )
    ).all()

    views_by_account: dict[uuid.UUID, list[int]] = {account.id: [] for account in accounts}
    thresholds_for_account: dict[uuid.UUID, ShadowbanThresholds] = {}
    for account in accounts:
        if account.owner_id is not None:
            thresholds_for_account[account.id] = thresholds_by_owner.get(account.owner_id, ShadowbanThresholds())
        else:
            thresholds_for_account[account.id] = ShadowbanThresholds()

    for account_id, snapshot, _completed_at, _created_at in rows:
        threshold = thresholds_for_account.get(account_id, ShadowbanThresholds())
        if len(views_by_account[account_id]) >= threshold.video_sample_count:
            continue
        views = _views_from_snapshot(snapshot)
        if views is None:
            continue
        views_by_account[account_id].append(views)

    updated = 0
    insufficient = 0
    for account in accounts:
        threshold = thresholds_for_account[account.id]
        samples = views_by_account[account.id]
        if len(samples) < threshold.video_sample_count:
            insufficient += 1
            continue
        if all(value <= threshold.view_threshold for value in samples):
            account.platform_binding_status = "shadowban"
            updated += 1

    return {"checked": len(accounts), "updated": updated, "insufficient": insufficient}


def start_account_shadowban_scheduler() -> None:
    global _scheduler_task, _scheduler_stop_event
    if _scheduler_task is not None and not _scheduler_task.done():
        return
    _scheduler_stop_event = asyncio.Event()
    _scheduler_task = asyncio.get_running_loop().create_task(
        _scheduler_loop(_scheduler_stop_event)
    )
    logger.info("【账号 Shadowban】调度器已启动，触发规则：北京时间 %s", _CRON_EXPR)


async def stop_account_shadowban_scheduler() -> None:
    global _scheduler_task, _scheduler_stop_event
    stop_event, worker = _scheduler_stop_event, _scheduler_task
    _scheduler_stop_event = None
    _scheduler_task = None
    if stop_event is not None:
        stop_event.set()
    if worker is None:
        return
    worker.cancel()
    try:
        await worker
    except asyncio.CancelledError:
        pass
    logger.info("【账号 Shadowban】调度器已停止")


async def _scheduler_loop(stop_event: asyncio.Event) -> None:
    global _last_fire_key
    now_local = datetime.now(timezone.utc).astimezone(_TZ)
    cron = croniter(_CRON_EXPR, now_local)
    prev_local: datetime = cron.get_prev(datetime)
    _last_fire_key = prev_local.strftime("%Y-%m-%d %H:%M")

    try:
        while not stop_event.is_set():
            try:
                await _check_and_maybe_fire()
            except Exception:
                logger.exception("【账号 Shadowban】调度异常")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=_POLL_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                continue
    except asyncio.CancelledError:
        raise


async def _check_and_maybe_fire() -> None:
    global _last_fire_key
    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone(_TZ)
    cron = croniter(_CRON_EXPR, now_local)
    prev_local: datetime = cron.get_prev(datetime)
    fire_key = prev_local.strftime("%Y-%m-%d %H:%M")

    seconds_since = (now_local - prev_local).total_seconds()
    if seconds_since < 0 or seconds_since >= _POLL_INTERVAL_SECONDS * 1.5:
        return
    if fire_key == _last_fire_key:
        return

    _last_fire_key = fire_key
    logger.info("【账号 Shadowban】命中触发点 %s（北京时间），开始评估", fire_key)
    from app.db.session import SessionLocal

    async with _run_lock:
        async with SessionLocal() as session:
            result = await run_shadowban_evaluation(session)
            await session.commit()
    logger.info(
        "【账号 Shadowban】评估完成 checked=%s updated=%s insufficient=%s",
        result["checked"],
        result["updated"],
        result["insufficient"],
    )
