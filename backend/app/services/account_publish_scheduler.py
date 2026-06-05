"""
Account publish scheduler
=========================
每 60 秒轮询一次，对所有启用了定时发布的 AI 博主账号（Account.publish_enabled=True）：
1. 用 croniter 按北京时间判断上一个触发点是否在本轮 poll 窗口内
2. 用数据库字段 publish_last_triggered_at 去重（防止重启重复触发）
3. 若命中：随机延迟 0~publish_window_minutes 分钟后执行
4. 执行时从该账号 queued 队列优先取爆款复用任务，再按 queue_order 取前 publish_count 个子任务，并发发布
5. 多账号之间并发处理（asyncio.gather）
"""
from __future__ import annotations

import asyncio
import logging
import random
import uuid
from datetime import datetime, timedelta, timezone

import pytz
from croniter import croniter
from sqlalchemy import case, select
from sqlalchemy.orm import selectinload

from app.db.session import SessionLocal
from app.models.account import Account
from app.models.account_channel_reservation import AccountChannelReservation
from app.models.video_task import VideoSubTask, VideoTask

logger = logging.getLogger("app.account_publish_scheduler")

_POLL_INTERVAL_SECONDS = 600.0
_TZ = pytz.timezone("Asia/Shanghai")

_scheduler_task: asyncio.Task | None = None
_scheduler_stop_event: asyncio.Event | None = None

def start_account_publish_scheduler() -> None:
    global _scheduler_task, _scheduler_stop_event
    if _scheduler_task is not None and not _scheduler_task.done():
        return
    _scheduler_stop_event = asyncio.Event()
    _scheduler_task = asyncio.get_running_loop().create_task(
        _scheduler_loop(_scheduler_stop_event)
    )
    logger.info("【定时发布调度器】已启动，轮询间隔 %d 秒", int(_POLL_INTERVAL_SECONDS))


async def stop_account_publish_scheduler() -> None:
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
    logger.info("【定时发布调度器】已停止")


async def _scheduler_loop(stop_event: asyncio.Event) -> None:
    try:
        while not stop_event.is_set():
            try:
                await _run_once()
            except Exception:
                logger.exception("【定时发布调度器】轮询异常")
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
        result = await session.execute(
            select(Account).where(Account.publish_enabled.is_(True))
        )
        accounts: list[Account] = list(result.scalars().all())

    if not accounts:
        return

    logger.debug(
        "【定时发布调度器】轮询时间 %s（北京时间 %s），共 %d 个已启用账号",
        now_utc.strftime("%H:%M:%S UTC"),
        now_local.strftime("%H:%M:%S"),
        len(accounts),
    )

    # 多账号并发处理
    await asyncio.gather(
        *[_process_account(account, now_utc=now_utc, now_local=now_local) for account in accounts],
        return_exceptions=True,
    )


async def _process_account(account: Account, *, now_utc: datetime, now_local: datetime) -> None:
    cron_expr = (account.publish_cron or "").strip()
    if not cron_expr:
        return

    if not croniter.is_valid(cron_expr):
        logger.warning(
            "【定时发布】账号 %s（%s）的 Cron 表达式 %r 无效，跳过",
            account.id, account.account_name, cron_expr,
        )
        return

    account_id = account.id

    # ── 检查数据库里是否有待执行的延迟任务 ───────────────────────────────────
    scheduled_at = account.publish_scheduled_at
    if scheduled_at is not None:
        if scheduled_at.tzinfo is None:
            scheduled_at = scheduled_at.replace(tzinfo=timezone.utc)
        if now_utc >= scheduled_at:
            logger.info(
                "【定时发布】账号 %s（%s）随机延迟结束，开始发布（计划时间：%s UTC）",
                account_id, account.account_name, scheduled_at.strftime("%H:%M:%S"),
            )
            # 清空 scheduled_at，写入 last_triggered_at
            async with SessionLocal() as session:
                acct = await session.get(Account, account_id)
                if acct is None:
                    return
                acct.publish_scheduled_at = None
                acct.publish_last_triggered_at = now_utc
                await session.commit()
            await _do_publish(account)
        else:
            remaining = (scheduled_at - now_utc).total_seconds()
            logger.debug(
                "【定时发布】账号 %s（%s）等待随机延迟，剩余 %.0f 秒",
                account_id, account.account_name, remaining,
            )
        return

    # ── 计算上一个 cron 触发点（北京时间） ────────────────────────────────────
    cron = croniter(cron_expr, now_local, ret_type=datetime)
    prev_fire_local: datetime = cron.get_prev(datetime)
    prev_fire_key = prev_fire_local.strftime("%Y-%m-%d %H:%M")
    prev_fire_utc = prev_fire_local.astimezone(timezone.utc)
    seconds_since_fire = (now_utc - prev_fire_utc).total_seconds()

    logger.debug(
        "【定时发布】账号 %s（%s）Cron=%r，上次触发点=%s（%.0f 秒前）",
        account_id, account.account_name, cron_expr, prev_fire_key, seconds_since_fire,
    )

    # 触发点必须在 poll 窗口内
    if seconds_since_fire < 0 or seconds_since_fire >= _POLL_INTERVAL_SECONDS * 1.5:
        return

    # ── 数据库去重：上次触发时间是否已覆盖此触发点 ───────────────────────────
    if account.publish_last_triggered_at is not None:
        last = account.publish_last_triggered_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if last >= prev_fire_utc:
            logger.debug(
                "【定时发布】账号 %s（%s）触发点 %s 已发布过（上次触发：%s），跳过",
                account_id, account.account_name, prev_fire_key,
                last.strftime("%H:%M UTC"),
            )
            return

    logger.info(
        "【定时发布】账号 %s（%s）命中触发点 %s（北京时间），距触发 %.0f 秒，准备发布",
        account_id, account.account_name, prev_fire_key, seconds_since_fire,
    )

    # ── 随机延迟：计算 fire_at，写入数据库 ──────────────────────────────────
    window_minutes = account.publish_window_minutes or 0
    if window_minutes > 0:
        delay_seconds = random.randint(0, window_minutes * 60)
        fire_at = now_utc + timedelta(seconds=delay_seconds)
        async with SessionLocal() as session:
            acct = await session.get(Account, account_id)
            if acct is None:
                return
            acct.publish_scheduled_at = fire_at
            await session.commit()
        logger.info(
            "【定时发布】账号 %s（%s）设置随机延迟 %d 秒（窗口 %d 分钟），将于 %s UTC 发布",
            account_id, account.account_name,
            delay_seconds, window_minutes,
            fire_at.strftime("%H:%M:%S"),
        )
    else:
        # 无延迟：直接写 last_triggered_at 并发布
        async with SessionLocal() as session:
            acct = await session.get(Account, account_id)
            if acct is None:
                return
            acct.publish_last_triggered_at = now_utc
            await session.commit()
        logger.info("【定时发布】账号 %s（%s）无随机延迟，立即开始发布", account_id, account.account_name)
        await _do_publish(account)


async def _do_publish(account: Account) -> None:
    """从队列取前 N 个 queued 子任务，按顺序串行发布"""
    publish_count = max(1, account.publish_count or 1)
    channels = await _build_channels(account.id)

    if not channels:
        logger.warning(
            "【定时发布】账号 %s（%s）未配置发布渠道，跳过",
            account.id, account.account_name,
        )
        return

    # 加载该账号 owner 的自动发布 AI 配置
    ai_config = await _load_auto_publish_config(account)

    async with SessionLocal() as session:
        result = await session.execute(
            select(VideoSubTask)
            .join(VideoTask, VideoSubTask.task_id == VideoTask.id)
            .where(
                VideoTask.account_id == account.id,
                VideoSubTask.status == "queued",
                VideoSubTask.result_video_url.isnot(None),
                VideoSubTask.publish_meta["status"].as_string() == "done",
            )
            .order_by(
                case((VideoTask.template_reuse_reason == "high_performance_reuse", 0), else_=1),
                VideoSubTask.queue_order.asc().nullslast(),
                VideoSubTask.created_at.asc(),
            )
            .limit(publish_count)
            .options(selectinload(VideoSubTask.task))
        )
        sub_tasks: list[VideoSubTask] = list(result.scalars().all())

    if not sub_tasks:
        logger.info("【定时发布】账号 %s（%s）发布队列为空，无需发布", account.id, account.account_name)
        return

    logger.info(
        "【定时发布】账号 %s（%s）准备发布 %d 个视频到 %d 个渠道",
        account.id, account.account_name, len(sub_tasks), len(channels),
    )

    # 同一账号内按 queue_order 串行发布，保证顺序
    for sub in sub_tasks:
        try:
            await _publish_sub_task(sub.id, channels, account.account_name, ai_config, account_type=account.account_type)
        except Exception:
            logger.exception(
                "【定时发布】账号 %s（%s）发布子任务 %s 失败，继续下一个",
                account.id, account.account_name, sub.id,
            )


async def _load_auto_publish_config(account: Account) -> dict | None:
    """加载账号 owner 的自动发布 AI 配置，若未启用返回 None"""
    from app.services.publish_meta_service import _load_auto_publish_config as _load_cfg
    return await _load_cfg(account.owner_id)


async def _publish_sub_task(
    sub_task_id: uuid.UUID,
    channels: list[dict],
    account_name: str,
    ai_config: dict | None,
    *,
    account_type: str = "traffic",
) -> None:
    from app.services.video_publication_service import VideoPublicationService
    from app.schemas.video_publication import VideoPublicationCreate

    async with SessionLocal() as session:
        result = await session.execute(
            select(VideoSubTask)
            .where(VideoSubTask.id == sub_task_id)
            .options(selectinload(VideoSubTask.task))
        )
        sub = result.scalar_one_or_none()
        if sub is None:
            logger.warning("【定时发布】子任务 %s 不存在，跳过", sub_task_id)
            return
        if sub.status != "queued":
            logger.info("【定时发布】子任务 %s 状态为 %s（已不在队列），跳过", sub_task_id, sub.status)
            return
        if not sub.result_video_url:
            logger.warning("【定时发布】子任务 %s 无视频地址，跳过", sub_task_id)
            return

        task = sub.task
        fallback_title = (task.prompt or "")[:100] or "视频"
        publish_meta = sub.publish_meta or {}

    original_video_url = sub.result_video_url

    # ── 拼接 logo 视频（traffic / persona 各用不同 logo）────────────────────
    # 改为 if True 即可开启
    if False:
        try:
            from app.services.video_logo_service import concat_video_with_logo
            logger.info("【定时发布】子任务 %s（账号：%s, %s）开始拼接 logo", sub_task_id, account_name, account_type)
            publish_video_url = await concat_video_with_logo(original_video_url, account_type=account_type)
            logger.info("【定时发布】子任务 %s logo 拼接完成: %s", sub_task_id, publish_video_url[:100])
        except Exception:
            logger.exception("【定时发布】子任务 %s logo 拼接失败，使用原视频发布", sub_task_id)
            publish_video_url = original_video_url
    else:
        publish_video_url = original_video_url

    # ── 使用预生成的 publish_meta 标题（查询已保证 status==done）────────────
    title = publish_meta.get("title") or fallback_title
    description = publish_meta.get("description", "")
    hashtags = publish_meta.get("hashtags", [])
    logger.info("【定时发布】子任务 %s 使用预生成标题：%r", sub_task_id, title)

    # ── 发布 ──────────────────────────────────────────────────────────────────
    async with SessionLocal() as session:
        result = await session.execute(
            select(VideoSubTask)
            .where(VideoSubTask.id == sub_task_id)
            .options(selectinload(VideoSubTask.task))
        )
        sub = result.scalar_one_or_none()
        if sub is None or sub.status != "queued":
            return

        service = VideoPublicationService(session)
        logger.info(
            "【定时发布】子任务 %s（账号：%s）调用 create_publication，channels=%s，title=%r",
            sub_task_id, account_name, channels, title,
        )
        try:
            publication = await service.create_publication(VideoPublicationCreate(
                sub_task_id=sub.id,
                video_url=publish_video_url,
                original_video_url=original_video_url,
                video_type=account_type,
                title=title,
                description=description or None,
                tags=hashtags or None,
                channels=channels,
            ))
            sub.queue_order = None
            await session.commit()
            logger.info(
                "【定时发布】子任务 %s（账号：%s）已提交发布 → %s（标题：%r）",
                sub_task_id, account_name, publication.status, title,
            )
        except Exception as e:
            logger.error(
                "【定时发布】子任务 %s（账号：%s）发布失败：%s",
                sub_task_id, account_name, e,
            )
            raise


async def _build_channels(account_id: uuid.UUID) -> list[dict]:
    async with SessionLocal() as session:
        bindings = (await session.execute(
            select(AccountChannelReservation)
            .where(AccountChannelReservation.account_id == account_id)
            .where(AccountChannelReservation.status == "bound")
            .where(AccountChannelReservation.channel_id.is_not(None))
            .where(AccountChannelReservation.channel_status == "active")
            .order_by(AccountChannelReservation.created_at.asc())
        )).scalars().all()
    result = []
    for b in bindings:
        entry = {"platform": b.platform, "channel_id": b.channel_id, "channel_source": b.channel_source or b.source or "openapi"}
        result.append(entry)
    return result
