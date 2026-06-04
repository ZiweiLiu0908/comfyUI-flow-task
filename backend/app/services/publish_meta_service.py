"""
publish_meta_service.py
=======================
负责在视频子任务进入发布队列时，异步预生成 AI 标题/描述/标签，
并将结果写入 video_sub_tasks.publish_meta。

publish_meta 字段格式：
{
    "status": "pending" | "generating" | "done" | "failed",
    "title": "...",
    "description": "...",
    "hashtags": ["tag1", "tag2"],
    "promotion_code": "12345678"  // 带商品码账号才有
}

队列设计：
- 全局 asyncio.Queue 串行接收任务，3 个 worker 并发消费
- enqueue_publish_meta_task() 将 sub_task_id 放入队列，同时把 publish_meta 写为 pending
- recover 时将 generating 状态的任务优先插入队列头部（通过优先队列实现）
"""
from __future__ import annotations

import asyncio
import json as _json
import logging
import uuid
from collections import deque
from typing import Any

from app.db.session import SessionLocal
from app.models.account import Account
from app.models.video_task import VideoSubTask, VideoTask
from app.services.ext_product_service import build_ext_products_from_shots
from app.services.promotion_code_service import promotion_code_distributor

logger = logging.getLogger("app.publish_meta_service")

# ── 全局队列与 worker ──────────────────────────────────────────────────────────
# 使用 deque 实现支持 appendleft（优先插入头部）的队列，配合 asyncio.Event 通知
_task_deque: deque[uuid.UUID] = deque()
_task_event: asyncio.Event | None = None   # 延迟初始化，须在 event loop 内创建
_WORKER_COUNT = 3
_workers: list[asyncio.Task] = []
_failed_retry_scheduler_task: asyncio.Task | None = None
_failed_retry_scheduler_stop_event: asyncio.Event | None = None
_FAILED_RETRY_POLL_INTERVAL_SECONDS = 600.0
_FAILED_RETRY_BATCH_SIZE = 20


def _get_event() -> asyncio.Event:
    global _task_event
    if _task_event is None:
        _task_event = asyncio.Event()
    return _task_event


async def _worker(worker_id: int) -> None:
    """持续从 _task_deque 取任务并执行，并发数由 worker 数量控制。"""
    event = _get_event()
    logger.info("【AI预生成标题】worker-%d 启动", worker_id)
    while True:
        # 等待有任务
        await event.wait()
        try:
            sub_task_id = _task_deque.popleft()
        except IndexError:
            # 被其他 worker 抢先取走了，清除 event 重新等待
            event.clear()
            continue
        # 队列还有任务则保持 event set
        if not _task_deque:
            event.clear()

        try:
            await _process_publish_meta(sub_task_id)
        except Exception:
            logger.exception("【AI预生成标题】worker-%d 处理子任务 %s 异常", worker_id, sub_task_id)


def enqueue_publish_meta_task(sub_task_id: uuid.UUID, *, priority: bool = False) -> None:
    """将 sub_task_id 加入生成队列。priority=True 时插入头部（用于 recover）。"""
    if priority:
        _task_deque.appendleft(sub_task_id)
    else:
        _task_deque.append(sub_task_id)
    _get_event().set()


async def start_publish_meta_workers() -> None:
    """在应用启动时调用，启动 _WORKER_COUNT 个后台 worker。"""
    global _workers
    _get_event()  # 确保在 event loop 内初始化
    _workers = [
        asyncio.create_task(_worker(i + 1), name=f"publish-meta-worker-{i + 1}")
        for i in range(_WORKER_COUNT)
    ]
    logger.info("【AI预生成标题】已启动 %d 个 worker", _WORKER_COUNT)


async def stop_publish_meta_workers() -> None:
    """在应用关闭时调用，取消所有 worker。"""
    for w in _workers:
        w.cancel()
    await asyncio.gather(*_workers, return_exceptions=True)
    _workers.clear()
    logger.info("【AI预生成标题】所有 worker 已停止")


def start_failed_publish_meta_retry_scheduler() -> None:
    """启动失败标题自动补偿调度器。"""
    global _failed_retry_scheduler_task, _failed_retry_scheduler_stop_event
    if _failed_retry_scheduler_task is not None and not _failed_retry_scheduler_task.done():
        return
    _failed_retry_scheduler_stop_event = asyncio.Event()
    _failed_retry_scheduler_task = asyncio.get_running_loop().create_task(
        _failed_retry_scheduler_loop(_failed_retry_scheduler_stop_event)
    )
    logger.info(
        "【AI标题失败补偿】调度器已启动，轮询间隔 %d 秒",
        int(_FAILED_RETRY_POLL_INTERVAL_SECONDS),
    )


async def stop_failed_publish_meta_retry_scheduler() -> None:
    """停止失败标题自动补偿调度器。"""
    global _failed_retry_scheduler_task, _failed_retry_scheduler_stop_event
    stop_event, worker = _failed_retry_scheduler_stop_event, _failed_retry_scheduler_task
    _failed_retry_scheduler_stop_event = None
    _failed_retry_scheduler_task = None
    if stop_event is not None:
        stop_event.set()
    if worker is None:
        return
    worker.cancel()
    try:
        await worker
    except asyncio.CancelledError:
        pass
    logger.info("【AI标题失败补偿】调度器已停止")


async def _failed_retry_scheduler_loop(stop_event: asyncio.Event) -> None:
    try:
        while not stop_event.is_set():
            try:
                await retry_failed_publish_meta_once()
            except Exception:
                logger.exception("【AI标题失败补偿】轮询异常")
            try:
                await asyncio.wait_for(
                    stop_event.wait(),
                    timeout=_FAILED_RETRY_POLL_INTERVAL_SECONDS,
                )
            except asyncio.TimeoutError:
                continue
    except asyncio.CancelledError:
        raise


async def retry_failed_publish_meta_once(limit: int = _FAILED_RETRY_BATCH_SIZE) -> dict[str, int]:
    """扫描标题生成失败的 queued 子任务，用视频输入补偿生成发布元数据。"""
    from sqlalchemy import select

    async with SessionLocal() as session:
        sub_task_ids = list((await session.execute(
            select(VideoSubTask.id)
            .where(VideoSubTask.status == "queued")
            .where(VideoSubTask.publish_meta["status"].as_string() == "failed")
            .order_by(VideoSubTask.updated_at.asc())
            .limit(limit)
        )).scalars().all())

    if not sub_task_ids:
        return {"total": 0, "processed": 0}

    logger.info("【AI标题失败补偿】发现 %d 条失败标题任务，开始按视频补偿", len(sub_task_ids))
    processed = 0
    for sub_task_id in sub_task_ids:
        try:
            await _process_publish_meta(
                sub_task_id,
                input_mode="video",
                fallback_to_default=True,
            )
            processed += 1
        except Exception:
            logger.exception("【AI标题失败补偿】处理子任务 %s 异常", sub_task_id)

    logger.info("【AI标题失败补偿】本轮完成：processed=%d total=%d", processed, len(sub_task_ids))
    return {"total": len(sub_task_ids), "processed": processed}


# ── 配置加载 ───────────────────────────────────────────────────────────────────

async def _load_auto_publish_config(owner_id: uuid.UUID | None) -> dict | None:
    """加载 owner 的自动发布 AI 配置，若未启用返回 None。"""
    from app.models.video_task_config import VideoTaskConfig
    from app.services.google_api import get_google_api_key

    if owner_id is None:
        return None

    async with SessionLocal() as session:
        cfg = await session.get(VideoTaskConfig, owner_id)
        if cfg is None:
            return None
        if not (cfg.auto_publish_prompt or "").strip():
            logger.warning("owner %s 未配置 AI 生成标题提示词", owner_id)
            return None

        api_key = get_google_api_key()
        if not api_key:
            logger.warning("owner %s 已启用 AI 生成标题，但 GOOGLE_API_KEY 未配置", owner_id)
            return None

        return {
            "model": cfg.auto_publish_model or "gemini-2.0-flash",
            "prompt": cfg.auto_publish_prompt,
        }


# ── AI 生成逻辑 ────────────────────────────────────────────────────────────────

_JSON_SUFFIX = """

Output strictly as JSON (no markdown, no explanation):
{"title": "...", "desc": "...", "hashtag": ["tag1", "tag2"]}"""

_PRODUCT_CODE_TITLE_PREFIX = "👆Outfit linked in bio"
# 旧版本曾以下面文案做拼接，保留常量供清洗脚本识别历史数据
_PRODUCT_CODE_TITLE_LEGACY_SUFFIX = "Get my exact look here 👀 👇"
_PRODUCT_CODE_TITLE_LEGACY_PREFIX = "👇 👀 Get my exact look here 👀 👇"
# description 第一段引流文案
_BIO_LINK_DESC_HEADER = "You can find this outfit through the link in my bio💗"
_DEFAULT_TITLES = [
    "How do you like this?",
    "What do you think of this look?",
    "A little moment worth sharing",
    "This one caught my eye",
]
_DEFAULT_DESCRIPTION = "What do you think? Tell me in the comments."
_DEFAULT_HASHTAGS = ["ootd", "style", "fashion", "outfitinspo"]
_VIDEO_INPUT_PROMPT = (
    "\n\nUse the attached video as the only content input. Analyze the visuals, scene, "
    "people, action, styling, on-screen text, and overall mood, then generate publish "
    "metadata for this video."
)


def _format_price_number(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value).strip()
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}".rstrip("0").rstrip(".")


def _format_product_price(price: Any) -> str:
    if isinstance(price, dict):
        extracted_value = price.get("extracted_value")
        currency = str(price.get("currency") or "").strip()
        if extracted_value is not None:
            amount = _format_price_number(extracted_value)
            if currency in {"$", "USD", "US$"}:
                return f"${amount}"
            return f"{currency}{amount}" if currency else amount
        value = str(price.get("value") or "").strip()
        if value:
            return value
        return ""
    if isinstance(price, (int, float)):
        return _format_price_number(price)
    text = str(price or "").strip()
    return text


def _fallback_brand_label(index: int) -> str:
    if 1 <= index <= 26:
        return f"Brand {chr(ord('A') + index - 1)}"
    return f"Brand {index}"


def _build_product_code_description(
    base_description: str,
    promotion_code: str,  # 保留入参兼容旧调用方；新版描述不再使用商品码文案
    ext_products: list[dict],
) -> str:
    del promotion_code  # noqa: F841 — 新版不再拼接「Search code X on Alvin's Club」引流
    lines: list[str] = [_BIO_LINK_DESC_HEADER]

    base = (base_description or "").strip()
    if base:
        lines.append(base)

    product_lines = []
    for index, product in enumerate(ext_products, start=1):
        if not isinstance(product, dict):
            continue
        # 内部商品无 source 字段，固定用 "Alvin's Club" 作为来源标签
        if product.get("is_internal"):
            label = "Alvin's Club"
        else:
            label = (
                product.get("source")
                or product.get("product_name")
                or product.get("title")
                or _fallback_brand_label(index)
            )
        price = _format_product_price(product.get("price")) or "price unavailable"
        product_lines.append(f"{label}: {price}")

    if product_lines:
        lines.append("\n".join(product_lines))
    return "\n\n".join(lines)


def _build_product_code_title(base_title: str) -> str:
    title = (base_title or "").strip()
    # 兼容历史脏数据：去掉旧版后缀 / 前缀，避免再次拼接造成重复
    if title.endswith(_PRODUCT_CODE_TITLE_LEGACY_SUFFIX):
        title = title[: -len(_PRODUCT_CODE_TITLE_LEGACY_SUFFIX)].rstrip()
    if title.startswith(_PRODUCT_CODE_TITLE_LEGACY_PREFIX):
        title = title[len(_PRODUCT_CODE_TITLE_LEGACY_PREFIX):].lstrip()
    if not title:
        return _PRODUCT_CODE_TITLE_PREFIX[:100]
    if title.startswith(_PRODUCT_CODE_TITLE_PREFIX):
        return title[:100]
    separator = " "
    max_base_length = max(0, 100 - len(separator) - len(_PRODUCT_CODE_TITLE_PREFIX))
    title_tail = title[:max_base_length].strip()
    return f"{_PRODUCT_CODE_TITLE_PREFIX}{separator}{title_tail}".strip()[:100]


def _build_default_publish_metadata(
    *,
    fallback_title: str,
    promotion_code: str | None = None,
    ext_products: list[dict] | None = None,
) -> tuple[str, str, list[str]]:
    base_title = (fallback_title or "").strip() or _DEFAULT_TITLES[0]
    title = base_title[:100]
    description = _DEFAULT_DESCRIPTION
    if promotion_code:
        title = _build_product_code_title(title)
        description = _build_product_code_description(
            description,
            promotion_code,
            ext_products or [],
        )
    return title, description, list(_DEFAULT_HASHTAGS)


async def _write_default_publish_meta(
    *,
    sub_task_id: uuid.UUID,
    fallback_title: str,
    product_code_mode: str,
    existing_promotion_code: str | None,
    ext_products: list[dict],
    fallback_reason: str,
) -> None:
    promotion_code = existing_promotion_code
    promotion_code_acquired = False
    if product_code_mode == "with_code" and not promotion_code:
        promotion_code = await promotion_code_distributor.acquire()
        promotion_code_acquired = True

    title, description, hashtags = _build_default_publish_metadata(
        fallback_title=fallback_title,
        promotion_code=promotion_code,
        ext_products=ext_products,
    )
    meta = {
        "status": "done",
        "title": title,
        "description": description,
        "hashtags": hashtags,
        "fallback": True,
        "fallback_reason": fallback_reason,
    }
    if promotion_code:
        meta["promotion_code"] = promotion_code
        meta["product_code_mode"] = product_code_mode
        meta["ext_products_count"] = len(ext_products)

    async with SessionLocal() as session:
        sub = await session.get(VideoSubTask, sub_task_id)
        if sub is None:
            if promotion_code_acquired:
                await promotion_code_distributor.discard(promotion_code)
            return
        sub.publish_meta = meta
        try:
            await session.commit()
        except Exception:
            if promotion_code_acquired:
                await promotion_code_distributor.discard(promotion_code)
            raise

    if promotion_code_acquired:
        await promotion_code_distributor.mark_committed(promotion_code)


async def generate_publish_metadata(
    video_prompt: str,
    ai_config: dict,
    fallback_title: str,
    promotion_code: str | None = None,
    ext_products: list[dict] | None = None,
    video_url: str | None = None,
) -> tuple[str, str, list[str]]:
    """
    根据视频描述文本或视频 URL 调用 Gemini API，生成 title/description/hashtags。
    返回 (title, description, hashtags)。失败时有限重试。
    """
    from app.services.ai_api import call_gemini_api

    system_prompt = (ai_config.get("prompt") or "").strip()
    prompt = f"{system_prompt}\n{video_prompt.strip()}{_JSON_SUFFIX}"

    FALLBACK_MODEL = "gemini-2.5-flash"
    PRIMARY_MAX = 3
    FALLBACK_MAX = 3
    retry_delay = 30.0

    models = [
        (ai_config["model"], PRIMARY_MAX),
        (FALLBACK_MODEL, FALLBACK_MAX),
    ]

    for model_name, max_attempts in models:
        attempt = 0
        while attempt < max_attempts:
            attempt += 1
            logger.info("【AI预生成标题】第%d次调用 Gemini API，模型: %s", attempt, model_name)
            try:
                raw = await call_gemini_api(
                    model_name=model_name,
                    prompt=prompt,
                    temperature=0.5,
                    video_url=video_url,
                )
                logger.info("【AI预生成标题】原始响应（第%d次）：%s", attempt, raw[:500])

                json_str = raw.strip()
                # 兼容模型输出 markdown 代码块
                import re as _re
                m = _re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", json_str)
                if m:
                    json_str = m.group(1)
                data = _json.loads(json_str)
                title = str(data.get("title", "") or "").strip()[:100]
                if not title:
                    raise ValueError("AI 返回的 JSON 缺少有效 title 字段")
                if promotion_code:
                    title = _build_product_code_title(title)
                desc = str(data.get("desc", "") or "")
                if promotion_code:
                    desc = _build_product_code_description(
                        desc,
                        promotion_code,
                        ext_products or [],
                    )
                hashtags = [str(t).strip().lstrip("#") for t in data.get("hashtag", []) if t]

                logger.info("【AI预生成标题】成功（第%d次，模型: %s） → %r", attempt, model_name, title)
                return title, desc, hashtags

            except Exception as e:
                exc_str = str(e)
                # 4xx 错误跳出当前模型直接换下一个
                is_4xx = any(code in exc_str for code in ["400", "401", "403", "404"])
                if is_4xx:
                    logger.warning("【AI预生成标题】模型 %s 4xx 错误，换模型重试：%s", model_name, exc_str[:300])
                    break
                if attempt >= max_attempts:
                    logger.warning("【AI预生成标题】模型 %s 已达最大重试次数 %d，换模型重试", model_name, max_attempts)
                    break
                logger.warning("【AI预生成标题】第%d次失败（模型: %s）：%s，%.0fs后重试", attempt, model_name, exc_str[:300], retry_delay)
                await asyncio.sleep(retry_delay)

    raise RuntimeError("AI 生成标题失败：主模型和备用模型均已耗尽重试次数")


async def _process_publish_meta(
    sub_task_id: uuid.UUID,
    *,
    input_mode: str = "prompt",
    fallback_to_default: bool = False,
) -> None:
    """worker 实际执行的处理逻辑：读取子任务 → 标记 generating → AI 生成 → 写回结果。"""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    # 1. 读取子任务信息
    async with SessionLocal() as session:
        row = await session.execute(
            select(VideoSubTask)
            .where(VideoSubTask.id == sub_task_id)
            .options(selectinload(VideoSubTask.task))
        )
        sub = row.scalar_one_or_none()
        if sub is None:
            return
        # 已被手动重新生成完成，跳过
        if (sub.publish_meta or {}).get("status") == "done":
            logger.info("【AI预生成标题】子任务 %s 已完成，跳过", sub_task_id)
            return

        video_prompt = (sub.task.prompt or "").strip()
        video_url: str | None = None
        if input_mode == "video":
            from app.utils.gcs_signing import ensure_sub_task_signed_url
            video_url = await ensure_sub_task_signed_url(session, sub)
            video_prompt = _VIDEO_INPUT_PROMPT
        owner_id = sub.task.owner_id
        fallback_title = (_DEFAULT_TITLES[0] if input_mode == "video" else video_prompt[:100]) or _DEFAULT_TITLES[0]
        ext_products = build_ext_products_from_shots(sub.task.shots)
        account: Account | None = None
        if sub.task.account_id:
            account = await session.get(Account, sub.task.account_id)
        product_code_mode = (account.product_code_mode if account else None) or "without_code"
        existing_meta = sub.publish_meta if isinstance(sub.publish_meta, dict) else {}
        existing_promotion_code = existing_meta.get("promotion_code")
        if not (
            isinstance(existing_promotion_code, str)
            and len(existing_promotion_code) == 8
            and existing_promotion_code.isdigit()
        ):
            existing_promotion_code = None

    if not video_prompt or (input_mode == "video" and not video_url):
        missing_reason = "result_video_url 为空" if input_mode == "video" else "task.prompt 为空"
        logger.info("【AI预生成标题】子任务 %s 的 %s，跳过", sub_task_id, missing_reason)
        if fallback_to_default:
            await _write_default_publish_meta(
                sub_task_id=sub_task_id,
                fallback_title=fallback_title,
                product_code_mode=product_code_mode,
                existing_promotion_code=existing_promotion_code,
                ext_products=ext_products,
                fallback_reason="missing_input",
            )
            return
        async with SessionLocal() as session:
            sub = await session.get(VideoSubTask, sub_task_id)
            if sub is not None:
                sub.publish_meta = {"status": "failed"}
                await session.commit()
        return

    # 2. 加载 AI 配置
    ai_config = await _load_auto_publish_config(owner_id)
    if ai_config is None:
        logger.info("【AI预生成标题】子任务 %s owner 未启用 AI 生成标题，跳过", sub_task_id)
        if fallback_to_default:
            await _write_default_publish_meta(
                sub_task_id=sub_task_id,
                fallback_title=fallback_title,
                product_code_mode=product_code_mode,
                existing_promotion_code=existing_promotion_code,
                ext_products=ext_products,
                fallback_reason="missing_ai_config",
            )
        return

    promotion_code: str | None = None
    promotion_code_acquired = False
    if product_code_mode == "with_code":
        if existing_promotion_code:
            promotion_code = existing_promotion_code
        else:
            promotion_code = await promotion_code_distributor.acquire()
            promotion_code_acquired = True

    # 3. 标记为 generating
    async with SessionLocal() as session:
        sub = await session.get(VideoSubTask, sub_task_id)
        if sub is None:
            if promotion_code_acquired:
                await promotion_code_distributor.discard(promotion_code)
            return
        generating_meta = {"status": "generating"}
        if promotion_code:
            generating_meta["promotion_code"] = promotion_code
            generating_meta["product_code_mode"] = product_code_mode
            generating_meta["ext_products_count"] = len(ext_products)
        sub.publish_meta = generating_meta
        try:
            await session.commit()
        except Exception:
            if promotion_code_acquired:
                await promotion_code_distributor.discard(promotion_code)
            raise

    if promotion_code_acquired:
        await promotion_code_distributor.mark_committed(promotion_code)

    logger.info(
        "【AI预生成标题】子任务 %s 开始生成标题，input_mode=%s prompt 前50字: %s",
        sub_task_id, input_mode, video_prompt[:50],
    )

    # 4. 调用 AI 生成
    try:
        title, description, hashtags = await generate_publish_metadata(
            video_prompt=video_prompt,
            ai_config=ai_config,
            fallback_title=fallback_title,
            promotion_code=promotion_code,
            ext_products=ext_products,
            video_url=video_url,
        )
        meta = {
            "status": "done",
            "title": title,
            "description": description,
            "hashtags": hashtags,
        }
        if promotion_code:
            meta["promotion_code"] = promotion_code
            meta["product_code_mode"] = product_code_mode
            meta["ext_products_count"] = len(ext_products)
    except Exception as e:
        logger.error("【AI预生成标题】子任务 %s 生成失败：%s", sub_task_id, e)
        meta = {"status": "failed"}
        if fallback_to_default:
            title, description, hashtags = _build_default_publish_metadata(
                fallback_title=fallback_title,
                promotion_code=promotion_code,
                ext_products=ext_products,
            )
            meta = {
                "status": "done",
                "title": title,
                "description": description,
                "hashtags": hashtags,
                "fallback": True,
                "fallback_reason": "ai_failed",
            }
        if promotion_code:
            meta["promotion_code"] = promotion_code
            meta["product_code_mode"] = product_code_mode
            meta["ext_products_count"] = len(ext_products)

    # 5. 写回 DB
    async with SessionLocal() as session:
        sub = await session.get(VideoSubTask, sub_task_id)
        if sub is None:
            return
        sub.publish_meta = meta
        await session.commit()

    logger.info("【AI预生成标题】子任务 %s 完成，状态: %s", sub_task_id, meta["status"])


# ── 启动恢复 ───────────────────────────────────────────────────────────────────

async def recover_stuck_publish_meta_on_startup() -> None:
    """
    启动时补跑未完成的标题生成任务：
    - generating 状态：插入队列头部（优先处理）
    - pending 状态：插入队列尾部
    """
    from sqlalchemy import select, or_

    async with SessionLocal() as session:
        # generating 优先
        generating_ids = (await session.execute(
            select(VideoSubTask.id).where(
                VideoSubTask.publish_meta["status"].as_string() == "generating",
                VideoSubTask.status == "queued",
            )
        )).scalars().all()

        pending_ids = (await session.execute(
            select(VideoSubTask.id).where(
                VideoSubTask.status == "queued",
                or_(
                    VideoSubTask.publish_meta.is_(None),
                    VideoSubTask.publish_meta["status"].as_string() == "pending",
                ),
            )
        )).scalars().all()

    if not generating_ids and not pending_ids:
        return

    logger.info(
        "【AI预生成标题】启动补跑：generating=%d，pending/null=%d",
        len(generating_ids), len(pending_ids),
    )

    # generating 插队列头部（逆序 appendleft 保持原顺序）
    for sub_task_id in reversed(generating_ids):
        enqueue_publish_meta_task(sub_task_id, priority=True)

    for sub_task_id in pending_ids:
        enqueue_publish_meta_task(sub_task_id)
