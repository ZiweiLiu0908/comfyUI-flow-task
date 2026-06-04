from __future__ import annotations

import logging
import time
import uuid

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import AppError
from app.core.logging import setup_logging
from app.db.init_db import init_db
from app.services.video_ai_service import start_video_ai_queue_processor, stop_video_ai_queue_processor, recover_stuck_templates_on_startup
from app.services.ai_account_service import start_ai_account_queue_processor, stop_ai_account_queue_processor, recover_stuck_accounts_on_startup
from app.services.video_publication_service import start_video_publication_poller, stop_video_publication_poller
from app.services.publication_metrics_scheduler import start_publication_metrics_scheduler, stop_publication_metrics_scheduler
from app.services.video_stats_collector import stop_video_stats_collector
from app.services.account_publish_scheduler import start_account_publish_scheduler, stop_account_publish_scheduler
from app.services.candidate_scheduler_service import start_candidate_scheduler, stop_candidate_scheduler
from app.services.template_supplement_scheduler_service import (
    start_template_supplement_scheduler,
    stop_template_supplement_scheduler,
)
from app.services.scheduled_generation_scheduler_service import (
    start_scheduled_generation_scheduler,
    stop_scheduled_generation_scheduler,
)
from app.services.lark_notify_scheduler import start_lark_notify_scheduler, stop_lark_notify_scheduler
from app.services.channel_status_poller import start_channel_status_poller, stop_channel_status_poller
from app.services.channel_name_sync_scheduler import start_channel_name_sync_scheduler, stop_channel_name_sync_scheduler
from app.services.account_tier_scheduler import start_account_tier_scheduler, stop_account_tier_scheduler
from app.services.promotion_code_service import start_promotion_code_distributor, stop_promotion_code_distributor
from app.services.topic_service import recover_stuck_keyword_gen_on_startup
from app.services.video_source_service import recover_stuck_downloads_on_startup
from app.services.candidate_service import recover_candidate_imports_on_startup, recover_stuck_ai_review_on_startup
from app.services.video_classification_service import (
    recover_classification_on_startup,
    start_classification_queue_processor,
    stop_classification_queue_processor,
)
from app.services.publish_meta_service import (
    recover_stuck_publish_meta_on_startup,
    start_failed_publish_meta_retry_scheduler,
    start_publish_meta_workers,
    stop_failed_publish_meta_retry_scheduler,
    stop_publish_meta_workers,
)
from app.services.persona_tagging_queue_service import (
    start_persona_tagging_workers,
    stop_persona_tagging_workers,
    recover_stuck_tagging_on_startup,
)

setup_logging(settings.log_level, settings.log_dir)
logger = logging.getLogger("app")

app = FastAPI(title="Task Manager API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Request-ID"],
)

@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    request_id = uuid.uuid4().hex[:8]
    start = time.perf_counter()
    path_with_query = request.url.path
    if request.url.query:
        path_with_query = f"{path_with_query}?{request.url.query}"

    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - start) * 1000
        logger.exception(
            "[%s] %s %s -> 500 (%.2fms)",
            request_id,
            request.method,
            path_with_query,
            duration_ms,
        )
        raise

    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "[%s] %s %s -> %s (%.2fms)",
        request_id,
        request.method,
        path_with_query,
        response.status_code,
        duration_ms,
    )
    response.headers["X-Request-ID"] = request_id
    # 允许任意来源通过 iframe 嵌入本站
    response.headers["X-Frame-Options"] = "ALLOWALL"
    response.headers["Content-Security-Policy"] = "frame-ancestors *"
    return response


@app.on_event("startup")
async def startup_event() -> None:
    if len(settings.auth_secret) < 32:
        raise RuntimeError("AUTH_SECRET must be at least 32 characters long. Set it via environment variable.")
    logger.info("Starting API with env=%s db=%s", settings.app_env, settings.database_url)
    if settings.auto_create_tables:
        await init_db()
    # 清理上次进程被强杀残留的 .tmp/ 子目录（>1h），避免磁盘越占越大
    from app.utils.tmp_storage import cleanup_stale_tmp
    try:
        cleanup_stale_tmp(max_age_seconds=3600)
    except Exception as exc:
        logger.warning("cleanup_stale_tmp on startup failed: %s", exc)
    await start_promotion_code_distributor()
    start_video_ai_queue_processor()
    start_ai_account_queue_processor()
    await recover_stuck_accounts_on_startup()
    start_video_publication_poller()
    start_publication_metrics_scheduler()
    # start_video_stats_collector()  # 暂停：每日统计定时任务
    start_account_publish_scheduler()
    start_candidate_scheduler()
    start_template_supplement_scheduler()
    start_scheduled_generation_scheduler()
    start_lark_notify_scheduler()
    start_channel_status_poller()
    start_channel_name_sync_scheduler()
    start_account_tier_scheduler()
    await recover_stuck_keyword_gen_on_startup()
    await recover_stuck_templates_on_startup()
    await recover_stuck_downloads_on_startup()
    await recover_candidate_imports_on_startup()
    await recover_stuck_ai_review_on_startup()
    start_classification_queue_processor()
    await recover_classification_on_startup()
    await start_publish_meta_workers()
    await recover_stuck_publish_meta_on_startup()
    start_failed_publish_meta_retry_scheduler()
    start_persona_tagging_workers()
    await recover_stuck_tagging_on_startup()


@app.on_event("shutdown")
async def shutdown_event() -> None:
    await stop_video_ai_queue_processor()
    await stop_ai_account_queue_processor()
    await stop_video_publication_poller()
    await stop_publication_metrics_scheduler()
    await stop_video_stats_collector()
    await stop_promotion_code_distributor()
    await stop_account_publish_scheduler()
    await stop_candidate_scheduler()
    await stop_template_supplement_scheduler()
    await stop_scheduled_generation_scheduler()
    await stop_failed_publish_meta_retry_scheduler()
    await stop_publish_meta_workers()
    await stop_lark_notify_scheduler()
    await stop_channel_status_poller()
    await stop_channel_name_sync_scheduler()
    await stop_account_tier_scheduler()
    await stop_classification_queue_processor()
    await stop_persona_tagging_workers()


@app.get("/health")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


app.include_router(api_router)
