from __future__ import annotations

import asyncio
import logging

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.publication_click_metrics_service import PublicationClickMetricsService

logger = logging.getLogger("app.publication_click_metrics_scheduler")

_scheduler_task: asyncio.Task | None = None
_scheduler_stop_event: asyncio.Event | None = None


def start_publication_click_metrics_scheduler() -> None:
    global _scheduler_task, _scheduler_stop_event
    if _scheduler_task is not None and not _scheduler_task.done():
        return
    _scheduler_stop_event = asyncio.Event()
    _scheduler_task = asyncio.get_running_loop().create_task(_scheduler_loop(_scheduler_stop_event))
    logger.info("【24h点击快照调度器】已启动")


async def stop_publication_click_metrics_scheduler() -> None:
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
    logger.info("【24h点击快照调度器】已停止")


async def _scheduler_loop(stop_event: asyncio.Event) -> None:
    interval = max(60, int(settings.publication_click_metrics_poll_interval_sec))
    try:
        while not stop_event.is_set():
            try:
                async with SessionLocal() as db:
                    service = PublicationClickMetricsService(db)
                    result = await service.sync_due_click_metrics()
                    if result["eligible"] > 0:
                        logger.info("【24h点击快照调度器】本轮完成: %s", result)
            except Exception:
                logger.exception("【24h点击快照调度器】轮询异常")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass
    except asyncio.CancelledError:
        pass
