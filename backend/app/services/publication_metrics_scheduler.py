"""
Publication metrics scheduler
==============================
每天北京时间 11:30 — 同步最近一个月已发布视频的指标快照（completed + partial）
每天北京时间 12:30 — 根据 video_publications 数据聚合计算每个 Account 的 performance_snapshot
每天北京时间 13:30 — 收集 completed_at ≥24h 且 kol_link_clicks 为空的发布记录的 KOL Link 点击数
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import pytz

from app.db.session import SessionLocal

logger = logging.getLogger("app.publication_metrics_scheduler")

_TZ = pytz.timezone("Asia/Shanghai")
_EASTERN_TZ = pytz.timezone("America/New_York")

# 每日定时任务触发时间（北京时间，24小时制；HH, MM）
_TRIGGER_SYNC_METRICS = (11, 30)        # 同步视频指标快照
_TRIGGER_SYNC_ACCOUNT_SNAPSHOT = (12, 30)  # 计算账号 performance_snapshot（指标同步后1小时）
_TRIGGER_COLLECT_KOL_CLICKS = (13, 30)  # 收集发布后 24h KOL Link 点击数

_scheduler_task: asyncio.Task | None = None
_scheduler_stop_event: asyncio.Event | None = None

# 上次执行时间记录，key: "sync_metrics" | "sync_account_snapshot"
_last_run: dict[str, str] = {}


def start_publication_metrics_scheduler() -> None:
    global _scheduler_task, _scheduler_stop_event
    if _scheduler_task is not None and not _scheduler_task.done():
        return
    _scheduler_stop_event = asyncio.Event()
    _scheduler_task = asyncio.get_running_loop().create_task(
        _scheduler_loop(_scheduler_stop_event)
    )
    logger.info("【指标同步调度器】已启动")


async def stop_publication_metrics_scheduler() -> None:
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
    logger.info("【指标同步调度器】已停止")


async def _scheduler_loop(stop_event: asyncio.Event) -> None:
    try:
        while not stop_event.is_set():
            try:
                await _check_and_run()
            except Exception:
                logger.exception("【指标同步调度器】轮询异常")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=60.0)
            except asyncio.TimeoutError:
                pass
    except asyncio.CancelledError:
        pass


def _today_key(job: str) -> str:
    """返回今日北京时间日期字符串作为去重 key"""
    return f"{job}:{datetime.now(_TZ).strftime('%Y-%m-%d')}"


def _is_in_window(now_bj: datetime, target: tuple[int, int], window_min: int = 2) -> bool:
    """now_bj 的 (hour, minute) 是否落在 [target, target+window_min) 内。"""
    now_minutes = now_bj.hour * 60 + now_bj.minute
    target_minutes = target[0] * 60 + target[1]
    return 0 <= (now_minutes - target_minutes) < window_min


async def _check_and_run() -> None:
    now_bj = datetime.now(_TZ)

    # 每天 11:30 同步指标
    if _is_in_window(now_bj, _TRIGGER_SYNC_METRICS):
        key = _today_key("sync_metrics")
        if _last_run.get("sync_metrics") != key:
            _last_run["sync_metrics"] = key
            logger.info("【指标同步调度器】触发每日指标同步（北京时间 %s）", now_bj.strftime("%H:%M"))
            asyncio.get_running_loop().create_task(_run_sync_metrics())

    # 每天 12:30 计算账号快照
    if _is_in_window(now_bj, _TRIGGER_SYNC_ACCOUNT_SNAPSHOT):
        key = _today_key("sync_account_snapshot")
        if _last_run.get("sync_account_snapshot") != key:
            _last_run["sync_account_snapshot"] = key
            logger.info("【指标同步调度器】触发账号快照计算（北京时间 %s）", now_bj.strftime("%H:%M"))
            asyncio.get_running_loop().create_task(_run_sync_account_snapshots())

    # 每天 13:30 收集发布后 24h KOL Link 点击数
    if _is_in_window(now_bj, _TRIGGER_COLLECT_KOL_CLICKS):
        key = _today_key("collect_kol_clicks")
        if _last_run.get("collect_kol_clicks") != key:
            _last_run["collect_kol_clicks"] = key
            logger.info("【指标同步调度器】触发 KOL Link 点击数收集（北京时间 %s）", now_bj.strftime("%H:%M"))
            asyncio.get_running_loop().create_task(_run_collect_kol_clicks())


async def _run_sync_metrics() -> None:
    """同步最近一个月 completed + partial 发布记录的 metrics_snapshot"""
    try:
        async with SessionLocal() as db:
            from app.services.video_publication_service import VideoPublicationService
            from app.schemas.video_publication import VideoPublicationStatsQuery
            from datetime import date

            one_month_ago = (datetime.now(timezone.utc) - timedelta(days=30)).date()
            today = datetime.now(timezone.utc).date()

            query = VideoPublicationStatsQuery(
                date_from=one_month_ago,
                date_to=today,
            )
            service = VideoPublicationService(db)
            result = await service.sync_metrics_for_stats_page(query, owner_id=None)
            logger.info(
                "【指标同步调度器】每日指标同步完成：synced=%d failed=%d total=%d",
                result["synced"], result["failed"], result["total"],
            )
    except Exception:
        logger.exception("【指标同步调度器】每日指标同步异常")


async def _run_sync_account_snapshots() -> None:
    """根据 video_publications 聚合计算所有账号的 performance_snapshot"""
    try:
        async with SessionLocal() as db:
            await sync_account_performance_snapshots(db)
    except Exception:
        logger.exception("【指标同步调度器】账号快照计算异常")


def _fetch_youtube_subscribers(channel_name: str) -> int | None:
    """用 yt-dlp 获取 YouTube 频道订阅数。在线程中调用（阻塞）。"""
    try:
        import yt_dlp  # type: ignore
    except ImportError:
        logger.warning("yt-dlp 未安装，无法获取 YouTube 订阅数")
        return None

    # username 可能带 @ 前缀，统一处理
    url = f"https://www.youtube.com/{channel_name}"
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        # 不用 extract_flat，需要完整频道元数据才能拿到 channel_follower_count
        "playlist_items": "0",
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False) or {}
        count = info.get("channel_follower_count")
        if count is not None:
            logger.info("【yt-dlp】YouTube @%s 订阅数=%s", channel_name, count)
            return int(count)
        logger.warning("【yt-dlp】YouTube @%s 未返回 channel_follower_count，字段: %s", channel_name, list(info.keys()))
        return None
    except Exception as exc:
        logger.warning("【yt-dlp】获取 YouTube @%s 订阅数失败: %s", channel_name, exc)
        return None


async def _fetch_tiktok_followers(channel_name: str) -> int | None:
    """用 RapidAPI 获取 TikTok 粉丝数（单次调用，失败返回 None）。"""
    import httpx
    from app.core.config import settings

    api_key = getattr(settings, "rapidapi_key", None)
    if not api_key:
        logger.warning("【RapidAPI】未配置 rapidapi_key，跳过 TikTok 粉丝数获取")
        return None

    url = "https://tiktok-api23.p.rapidapi.com/api/user/info"
    headers = {
        "x-rapidapi-host": "tiktok-api23.p.rapidapi.com",
        "x-rapidapi-key": api_key,
    }
    try:
        async with httpx.AsyncClient(timeout=15.0, trust_env=False) as client:
            unique_id = channel_name.lstrip("@")
            resp = await client.get(url, params={"uniqueId": unique_id}, headers=headers)
        resp.raise_for_status()
        payload = resp.json()
        user_info = payload.get("userInfo") or {}
        stats_v2 = user_info.get("statsV2") or {}
        stats = user_info.get("stats") or {}
        raw = stats_v2.get("followerCount") or stats.get("followerCount") or 0
        count = int(raw)
        logger.info("【RapidAPI】TikTok @%s 粉丝数=%d", channel_name, count)
        return count
    except Exception as exc:
        logger.warning("【RapidAPI】获取 TikTok @%s 粉丝数失败: %s", channel_name, exc)
        return None


async def sync_account_performance_snapshots(db, account_id=None) -> dict:
    """
    遍历 Account，统计其关联的 video_publications（completed + partial）里的指标：
    - total_views, total_likes, avg_views, avg_like_rate
    - video_count（有 metrics 数据的视频数）
    - latest_video_published_at, first_content_date
    - followers_count（YouTube 频道订阅数，via yt-dlp）
    写入 account.performance_snapshot。
    account_id: 若传入则只计算该账号，否则计算所有账号。
    """
    from sqlalchemy import select
    from app.models.account import Account
    from app.models.account_channel_reservation import AccountChannelReservation
    from app.models.video_publication import VideoPublication
    from app.models.video_task import VideoSubTask, VideoTask

    stmt = select(Account)
    if account_id is not None:
        stmt = stmt.where(Account.id == account_id)
    result = await db.execute(stmt)
    accounts = list(result.scalars().all())

    updated = 0
    for account in accounts:
        try:
            # 查该账号下所有 completed / partial 的发布记录
            stmt = (
                select(VideoPublication)
                .join(VideoSubTask, VideoSubTask.id == VideoPublication.sub_task_id)
                .join(VideoTask, VideoTask.id == VideoSubTask.task_id)
                .where(VideoTask.account_id == account.id)
                .where(VideoPublication.status.in_(["completed", "partial"]))
                .where(VideoPublication.metrics_snapshot.isnot(None))
            )
            pubs = list((await db.execute(stmt)).scalars().all())

            # 从频道绑定表遍历各平台获取粉丝数（各平台累加）
            followers_count: int | None = None
            bindings = (await db.execute(
                select(AccountChannelReservation)
                .where(AccountChannelReservation.account_id == account.id)
                .where(AccountChannelReservation.status == "bound")
            )).scalars().all()
            loop = asyncio.get_running_loop()
            for binding in bindings:
                platform = binding.platform or ""
                ch_name = binding.username or binding.channel_name or ""
                if not ch_name:
                    continue
                if platform == "youtube":
                    count = await loop.run_in_executor(None, _fetch_youtube_subscribers, ch_name)
                elif platform == "tiktok":
                    count = await _fetch_tiktok_followers(ch_name)
                else:
                    continue
                if count is not None:
                    followers_count = (followers_count or 0) + count

            if not pubs:
                # 即使没有发布记录，如果拿到了订阅数也保存
                if followers_count is not None:
                    existing = account.performance_snapshot or {}
                    if isinstance(existing, dict):
                        existing["followers_count"] = followers_count
                        existing["synced_at"] = datetime.now(timezone.utc).isoformat()
                        account.performance_snapshot = existing
                        updated += 1
                continue

            total_views = 0
            total_likes = 0
            total_kol_link_clicks = 0
            like_rate_values: list[float] = []
            click_rate_values: list[float] = []
            published_dates: list[datetime] = []
            video_count = 0

            for pub in pubs:
                snapshot = pub.metrics_snapshot
                if not isinstance(snapshot, dict):
                    continue
                channels = snapshot.get("channels") or []
                if not channels:
                    continue

                pub_views = 0
                pub_likes = 0
                has_data = False

                for ch in channels:
                    if not isinstance(ch, dict):
                        continue
                    stats = ch.get("stats") or {}
                    platform = str(ch.get("platform") or "").lower()

                    views = _to_int(stats.get("views") if platform == "youtube" else stats.get("view_count"))
                    likes = _to_int(stats.get("likes") if platform == "youtube" else stats.get("like_count"))
                    if views > 0 or likes > 0:
                        has_data = True
                    pub_views += views
                    pub_likes += likes

                if not has_data:
                    continue

                video_count += 1
                total_views += pub_views
                total_likes += pub_likes

                if pub_views > 0 and pub_likes >= 0:
                    like_rate_values.append(pub_likes / pub_views * 100)

                # kol_link_clicks 是 account 维度的，所有平台共用同一个 kol_user_id
                if pub.kol_link_clicks is not None:
                    total_kol_link_clicks += pub.kol_link_clicks
                    if pub_views > 0:
                        click_rate_values.append(pub.kol_link_clicks / pub_views * 100)

                if pub.completed_at:
                    published_dates.append(pub.completed_at)

            if video_count == 0:
                continue

            avg_views = round(total_views / video_count, 1) if video_count else None
            avg_like_rate = round(sum(like_rate_values) / len(like_rate_values), 2) if like_rate_values else None
            avg_video_click_rate = round(sum(click_rate_values) / len(click_rate_values), 4) if click_rate_values else None
            latest = max(published_dates) if published_dates else None
            first = min(published_dates) if published_dates else None

            account.performance_snapshot = {
                "synced_at": datetime.now(timezone.utc).isoformat(),
                "followers_count": followers_count,
                "video_count": video_count,
                "total_views": total_views,
                "total_likes": total_likes,
                "avg_views": avg_views,
                "avg_like_rate": avg_like_rate,
                "total_kol_link_clicks": total_kol_link_clicks if total_kol_link_clicks > 0 else None,
                "avg_video_click_rate": avg_video_click_rate,
                "latest_video_published_at": latest.isoformat() if latest else None,
                "first_content_date": first.isoformat() if first else None,
            }
            updated += 1

        except Exception:
            logger.exception("【指标同步调度器】计算账号快照失败: account_id=%s", account.id)

    if updated:
        await db.commit()

    logger.info("【指标同步调度器】账号快照计算完成：updated=%d / total=%d", updated, len(accounts))
    return {"updated": updated, "total": len(accounts)}


def _to_int(value) -> int:
    try:
        if value is None or value == "":
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


async def _run_collect_kol_clicks() -> None:
    """收集 completed_at ≥ 24h 且 kol_link_clicks 为 NULL 的发布记录的 KOL Link 点击数"""
    try:
        async with SessionLocal() as db:
            result = await collect_kol_link_clicks(db)
            logger.info(
                "【指标同步调度器】KOL Link 点击数收集完成：updated=%d skipped=%d failed=%d total=%d",
                result["updated"], result["skipped"], result["failed"], result["total"],
            )
    except Exception:
        logger.exception("【指标同步调度器】KOL Link 点击数收集异常")


async def collect_kol_link_clicks(
    db,
    *,
    publication_id=None,
    owner_id=None,
    account_id=None,
    date_from=None,
    date_to=None,
    platform=None,
    force: bool = False,
) -> dict:
    """
    扫描发布记录，按 completed_at 对应的美东自然日查询 BigQuery KOL Link 点击数并写回。

    口径：如果视频发布于 America/New_York 的某一天，即使是 23:59，
    也统计该美东自然日 00:00:00-23:59:59 的点击量。

    默认定时任务口径：只采集上一完整美东自然日且 kol_link_clicks IS NULL 的发布记录。
    publication_id: 若传入则只处理该条记录（用于手动触发单条补采）。
    force: 为 True 时会重算并覆盖已有 kol_link_clicks。
    """
    from datetime import date as date_type
    from sqlalchemy import select
    from app.models.account import Account
    from app.models.video_publication import VideoPublication
    from app.models.video_task import VideoSubTask, VideoTask
    from app.services.ext.bigquery_service.kol_analytics import get_kol_clicks_on_eastern_day

    stmt = (
        select(VideoPublication, Account.kol_user_id)
        .join(VideoSubTask, VideoSubTask.id == VideoPublication.sub_task_id)
        .join(VideoTask, VideoTask.id == VideoSubTask.task_id)
        .join(Account, Account.id == VideoTask.account_id)
        .where(VideoPublication.status.in_(["completed", "partial"]))
        .where(VideoPublication.completed_at.isnot(None))
        .where(Account.kol_user_id.isnot(None))
    )
    if not force:
        target_eastern_day = (datetime.now(_EASTERN_TZ) - timedelta(days=1)).date()
        eastern_start = _EASTERN_TZ.localize(
            datetime.combine(target_eastern_day, datetime.min.time())
        ).astimezone(timezone.utc)
        eastern_end = eastern_start + timedelta(days=1)
        stmt = stmt.where(VideoPublication.kol_link_clicks.is_(None))
        stmt = stmt.where(VideoPublication.completed_at >= eastern_start)
        stmt = stmt.where(VideoPublication.completed_at < eastern_end)
    if publication_id is not None:
        stmt = stmt.where(VideoPublication.id == publication_id)
    if owner_id is not None:
        stmt = stmt.where(VideoTask.owner_id == owner_id)
    if account_id is not None:
        stmt = stmt.where(VideoTask.account_id == account_id)
    if date_from is not None:
        stmt = stmt.where(
            VideoPublication.completed_at
            >= datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc)
        )
    if date_to is not None:
        next_day = date_type.fromordinal(date_to.toordinal() + 1)
        stmt = stmt.where(
            VideoPublication.completed_at
            < datetime.combine(next_day, datetime.min.time(), tzinfo=timezone.utc)
        )
    rows = (await db.execute(stmt)).all()
    if platform:
        platform_lower = str(platform).lower()
        def _has_platform(pub) -> bool:
            status_channels = pub.channels_status or []
            if any(
                isinstance(ch, dict) and str(ch.get("platform") or "").lower() == platform_lower
                for ch in status_channels
            ):
                return True
            snapshot = pub.metrics_snapshot if isinstance(pub.metrics_snapshot, dict) else {}
            metric_channels = snapshot.get("channels") or []
            return any(
                isinstance(ch, dict) and str(ch.get("platform") or "").lower() == platform_lower
                for ch in metric_channels
            )

        rows = [
            (pub, kol_user_id)
            for pub, kol_user_id in rows
            if _has_platform(pub)
        ]

    updated = skipped = failed = 0
    loop = asyncio.get_running_loop()

    for pub, kol_user_id in rows:
        if not kol_user_id:
            skipped += 1
            continue
        try:
            completed_at = pub.completed_at
            if completed_at.tzinfo is None:
                completed_at = completed_at.replace(tzinfo=timezone.utc)
            eastern_day: date_type = completed_at.astimezone(_EASTERN_TZ).date()
            clicks = await loop.run_in_executor(
                None,
                get_kol_clicks_on_eastern_day,
                kol_user_id,
                eastern_day,
            )
            pub.kol_link_clicks = clicks
            updated += 1
            logger.info(
                "【KOL点击收集】publication_id=%s kol_user_id=%s eastern_day=%s clicks=%d",
                pub.id, kol_user_id, eastern_day, clicks,
            )
        except Exception:
            logger.exception(
                "【KOL点击收集】BigQuery 查询失败: publication_id=%s kol_user_id=%s",
                pub.id, kol_user_id,
            )
            failed += 1

    if updated:
        await db.commit()

    return {"updated": updated, "skipped": skipped, "failed": failed, "total": len(rows)}
