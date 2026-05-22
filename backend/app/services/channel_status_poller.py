"""
Channel status poller
=====================
每小时自动触发一次，对所有 source=openapi、status=bound 的
AccountChannelReservation 记录，调用 GET /open-api/v1/channels/authorization
检查授权状态：
  - DISABLED → 将 channel_status 改为 "disabled"
  - ACTIVE    → 将 channel_status 恢复为 "active"
  - 其他/空状态 → 按 "disabled" 处理
  - 请求失败  → 跳过，打印警告日志

也可通过 run_channel_status_check() 在任意时刻手动触发一次。
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import httpx
from croniter import croniter
from sqlalchemy import select

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.account_channel_reservation import AccountChannelReservation
from app.services.account_service import recompute_account_platform_binding_status

logger = logging.getLogger("app.channel_status_poller")

_CRON_EXPR = "0 * * * *"   # 北京时间每小时整点
_POLL_INTERVAL_SECONDS = 60  # 每分钟检查一次是否到了触发时间
_REQUEST_TIMEOUT = 10.0
_REQUEST_RATE_LIMIT_SEC = 0.4
_TZ = ZoneInfo("Asia/Shanghai")

_poller_task: asyncio.Task | None = None
_poller_stop_event: asyncio.Event | None = None

# 上次触发的 cron key（"YYYY-MM-DD HH:MM"），用于去重
_last_fire_key: str | None = None

# 手动触发时使用的锁，防止手动与自动并发
_run_lock = asyncio.Lock()


ProgressCallback = Callable[[dict], Awaitable[None]]
DisconnectChecker = Callable[[], Awaitable[bool]]


def start_channel_status_poller() -> None:
    global _poller_task, _poller_stop_event
    if _poller_task is not None and not _poller_task.done():
        return
    _poller_stop_event = asyncio.Event()
    _poller_task = asyncio.get_running_loop().create_task(
        _poller_loop(_poller_stop_event)
    )
    logger.info("【频道状态轮询】已启动，触发规则：北京时间 %s", _CRON_EXPR)


async def stop_channel_status_poller() -> None:
    global _poller_task, _poller_stop_event
    stop_event, worker = _poller_stop_event, _poller_task
    _poller_stop_event = None
    _poller_task = None
    if stop_event is not None:
        stop_event.set()
    if worker is None:
        return
    worker.cancel()
    try:
        await worker
    except asyncio.CancelledError:
        pass
    logger.info("【频道状态轮询】已停止")


async def run_channel_status_check(
    progress_callback: ProgressCallback | None = None,
    should_stop: DisconnectChecker | None = None,
) -> dict:
    """手动触发一次完整检查，返回 {"checked": N, "changed": N}。"""
    async with _run_lock:
        return await _run_once(progress_callback=progress_callback, should_stop=should_stop)


async def _poller_loop(stop_event: asyncio.Event) -> None:
    global _last_fire_key
    # 启动时预填 _last_fire_key，防止重启后立即重复触发
    now_local = datetime.now(timezone.utc).astimezone(_TZ)
    cron = croniter(_CRON_EXPR, now_local)
    prev_local: datetime = cron.get_prev(datetime)
    _last_fire_key = prev_local.strftime("%Y-%m-%d %H:%M")
    logger.debug("【频道状态轮询】预填触发点 %s，启动后不会重复执行", _last_fire_key)

    try:
        while not stop_event.is_set():
            try:
                await _check_and_maybe_fire()
            except Exception:
                logger.exception("【频道状态轮询】调度异常")
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

    # 距上次触发点不超过 _POLL_INTERVAL_SECONDS * 1.5 才算命中
    seconds_since = (now_local - prev_local).total_seconds()
    if seconds_since < 0 or seconds_since >= _POLL_INTERVAL_SECONDS * 1.5:
        return

    if fire_key == _last_fire_key:
        return  # 本触发点已执行过

    _last_fire_key = fire_key
    logger.info("【频道状态轮询】命中触发点 %s（北京时间），开始检查", fire_key)
    async with _run_lock:
        await _run_once()


async def _emit_progress(progress_callback: ProgressCallback | None, payload: dict) -> None:
    if progress_callback is not None:
        await progress_callback(payload)


def _authorization_status_to_channel_status(status_val: str) -> str | None:
    if status_val == "ACTIVE":
        return "active"
    return "disabled"


async def query_channel_authorization(
    platform: str,
    channel_id: str,
    *,
    client: httpx.AsyncClient | None = None,
    base_url: str | None = None,
) -> dict:
    """查询单个频道授权状态，返回与 _check_one 一致的结构。

    新版 Open API 在 data 下额外返回 `channel: {platform, channel_id, channel_name}`
    供调用方矫正 channel_id / channel_name；本函数将其原样透传在 `channel` 字段。
    """
    if not channel_id:
        return {
            "result": "not_found",
            "new_status": None,
            "authorization_status": None,
            "channel": None,
        }

    base_url = (base_url or settings.open_api_base_url).rstrip("/")
    owns_client = client is None
    client_obj = client or httpx.AsyncClient(timeout=_REQUEST_TIMEOUT)

    try:
        resp = await client_obj.get(
            f"{base_url}/open-api/v1/channels/authorization",
            params={"platform": platform, "channel_id": channel_id},
        )
        resp.raise_for_status()
        data = resp.json()
        data_obj = data.get("data") or {}
        status_val: str = data_obj.get("status", "")
        channel_obj = data_obj.get("channel") if isinstance(data_obj.get("channel"), dict) else None
    except Exception as exc:
        logger.warning(
            "【频道状态轮询】查询 %s(%s) 失败: %s",
            platform,
            channel_id,
            exc,
        )
        return {
            "result": "request_failed",
            "new_status": None,
            "authorization_status": None,
            "channel": None,
        }
    finally:
        if owns_client:
            await client_obj.aclose()

    new_status = _authorization_status_to_channel_status(status_val)
    return {
        "result": "resolved",
        "new_status": new_status,
        "authorization_status": status_val or None,
        "channel": channel_obj,
    }


async def refresh_reservation_channel_status(
    reservation: AccountChannelReservation,
    *,
    client: httpx.AsyncClient | None = None,
    base_url: str | None = None,
) -> str | None:
    """绑定后立刻同步一次频道状态；仅对 openapi 来源生效。"""
    source = str(reservation.channel_source or reservation.source or "openapi")
    if source != "openapi" or not reservation.channel_id:
        return None

    result = await query_channel_authorization(
        reservation.platform,
        reservation.channel_id,
        client=client,
        base_url=base_url,
    )
    if result["new_status"] is not None:
        reservation.channel_status = result["new_status"]
        return result["new_status"]
    return None


async def _run_once(
    *,
    progress_callback: ProgressCallback | None = None,
    should_stop: DisconnectChecker | None = None,
) -> dict:
    async with SessionLocal() as session:
        result = await session.execute(
            select(AccountChannelReservation).where(
                AccountChannelReservation.source == "openapi",
                AccountChannelReservation.status == "bound",
                AccountChannelReservation.channel_id.isnot(None),
            )
        )
        reservations = list(result.scalars().all())

    total = len(reservations)
    processed = 0
    checked = 0
    changed = 0
    aborted = False

    await _emit_progress(progress_callback, {
        "event": "started",
        "total": total,
        "message": "开始检查频道授权状态",
    })

    if not reservations:
        logger.info("【频道状态轮询】无绑定频道，跳过")
        result = {"checked": 0, "changed": 0, "total": 0, "aborted": False}
        await _emit_progress(progress_callback, {
            "event": "completed",
            **result,
            "message": "暂无绑定频道，无需检查",
        })
        return result

    logger.info("【频道状态轮询】开始检查 %d 条绑定频道", total)

    base_url = settings.open_api_base_url.rstrip("/")

    async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
        for index, r in enumerate(reservations):
            if should_stop is not None and await should_stop():
                aborted = True
                logger.info(
                    "【频道状态轮询】客户端已断开，提前结束，已处理 %d/%d 条",
                    processed,
                    total,
                )
                break

            previous_status = r.channel_status
            check_result = await _check_one(client, base_url, r)
            new_status = check_result["new_status"]
            result_type = check_result["result"]
            current_status = previous_status

            if new_status is not None and new_status != previous_status:
                async with SessionLocal() as session:
                    obj = await session.get(AccountChannelReservation, r.id)
                    if obj is not None:
                        obj.channel_status = new_status
                        await recompute_account_platform_binding_status(session, obj.account_id)
                        await session.commit()
                        current_status = new_status
                        logger.info(
                            "【频道状态轮询】%s(%s) channel_status: %s → %s",
                            r.platform,
                            r.channel_id,
                            previous_status,
                            new_status,
                        )
                        changed += 1
                        result_type = "updated"
                    else:
                        result_type = "request_failed"
            elif new_status is not None:
                result_type = "unchanged"

            processed = index + 1
            checked = processed

            if result_type == "updated":
                message = f"{r.platform}({r.channel_id}) 状态已更新为 {current_status}"
            elif result_type == "unchanged":
                message = f"{r.platform}({r.channel_id}) 状态正常，保持 {current_status}"
            elif result_type == "not_found":
                message = f"{r.platform}({r.channel_id}) 未查到授权状态，保持 {current_status}"
            else:
                message = f"{r.platform}({r.channel_id}) 查询失败，保持 {current_status}"

            await _emit_progress(progress_callback, {
                "event": "progress",
                "index": processed,
                "total": total,
                "changed": changed,
                "platform": r.platform,
                "channel_name": r.channel_name,
                "channel_id": r.channel_id,
                "previous_status": previous_status,
                "current_status": current_status,
                "authorization_status": check_result["authorization_status"],
                "result": result_type,
                "message": message,
            })

            # authorization 接口限流：串行调用，请求间隔至少 0.4 秒
            if index < len(reservations) - 1 and not aborted:
                await asyncio.sleep(_REQUEST_RATE_LIMIT_SEC)

    logger.info("【频道状态轮询】本轮完成，共检查 %d 条，更新 %d 条", checked, changed)
    result = {"checked": checked, "changed": changed, "total": total, "aborted": aborted}
    await _emit_progress(progress_callback, {
        "event": "completed" if not aborted else "aborted",
        **result,
        "message": (
            f"已检查 {checked} / {total} 个频道，{changed} 个状态已更新"
            if total
            else "暂无绑定频道，无需检查"
        ),
    })
    return result


async def _check_one(
    client: httpx.AsyncClient,
    base_url: str,
    r: AccountChannelReservation,
) -> dict:
    return await query_channel_authorization(
        r.platform,
        r.channel_id or "",
        client=client,
        base_url=base_url,
    )
