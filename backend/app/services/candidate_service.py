"""候选库搜索服务

核心流程：
1. 用关键词调 RapidAPI 搜索，翻页收集博主，直到 max_bloggers 个唯一博主
2. 并发获取博主粉丝数，按粉丝量从高到低排序
3. 依次对每个博主做 [关键词 + 博主名] 精搜，取前 max_videos_per_blogger 条，过滤 > max_duration_seconds 的视频
4. 过滤后该博主视频数 >= exclusive_threshold → 独享模板（删除已存的共享记录，停止搜索）
   过滤后该博主视频数 < exclusive_threshold → 共享模板（写入并继续下一个博主）
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete as sa_delete, or_, select, update as sa_update, text as sa_text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.candidate_video import CandidateVideo, CandidateVideoStatus
from app.utils import rapid_api
from app.utils.apify import TikTokFilter, DateRange, SortOrder
from app.utils.tiktok_search import search_by_keyword, search_by_profiles
from app.services.image_upload_service import image_upload_service
from app.services.pipeline_settings_service import get_or_create_pipeline_settings

logger = logging.getLogger(__name__)

# 并发控制
_CONCURRENCY_AI_REVIEW = 3    # AI 审核并发数
_CONCURRENCY_COVER_UPLOAD = 5 # 封面上传并发数


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _sync_account_template_tags_before_supplement(
    account_id: uuid.UUID,
    owner_id: uuid.UUID | None,
    context: str,
) -> None:
    from app.db.session import SessionLocal
    from app.services.account_template_tag_service import ensure_account_template_tags

    try:
        async with SessionLocal() as session:
            result = await ensure_account_template_tags(session, account_id, owner_id=owner_id)
            if result.newly_bound > 0:
                await session.commit()
            logger.info(
                "【%s】account_id=%s 既有模板补绑完成：new=%d matched=%d unused=%d used=%d",
                context,
                account_id,
                result.newly_bound,
                result.matched_templates,
                result.unused_templates,
                result.used_templates,
            )
    except Exception as exc:
        logger.warning("【%s】account_id=%s 既有模板补绑失败：%s", context, account_id, exc)


# ---------------------------------------------------------------------------
# 搜索配置（从 pipeline_settings 按用户读取）
# ---------------------------------------------------------------------------

class _SearchConfig:
    def __init__(self, row: Any | None) -> None:
        self.max_bloggers: int = row.candidate_max_bloggers if row else 20
        self.exclusive_threshold: int = row.candidate_exclusive_threshold if row else 10
        self.max_videos_per_blogger: int = row.candidate_max_videos_per_blogger if row else 100
        self.max_duration_seconds: int = row.candidate_max_duration_seconds if row else 30
        self.retry_delay: float = float(row.candidate_retry_delay_seconds) if row else 5.0
        self.min_play_count: int = row.candidate_min_play_count if row else 0
        self.publish_after_date: str | None = row.candidate_publish_after_date if row else None
        self.shared_top_n: int = row.candidate_shared_top_n if row else 50
        self.ai_review_enabled: bool = row.candidate_ai_review_enabled if row else False
        self.ai_review_model: str = row.candidate_ai_review_model if row else "gemini-3.1-pro-preview"
        self.ai_review_prompt: str = row.candidate_ai_review_prompt if row else ""


# ---------------------------------------------------------------------------
# 第一阶段：收集唯一博主
# ---------------------------------------------------------------------------

async def _collect_bloggers(
    keyword: str,
    max_bloggers: int,
    retry_delay: float,
    exclude_bloggers: set[str] | None = None,
) -> list[dict[str, Any]]:
    """
    用 Apify 关键词搜索，收集 max_bloggers 个唯一博主。
    结果不够时重新调用一次（每次结果不同），直到收够或连续两轮无新增为止。
    exclude_bloggers: 已在库中的博主 unique_id 集合，搜索时跳过。
    返回 list[{"unique_id", "nickname", "follower_count"}]，follower_count 可能为 None（待补全）。
    """
    seen: dict[str, dict[str, Any]] = {}  # unique_id -> blogger info
    excluded = exclude_bloggers or set()

    logger.info("【候选库】开始收集博主，keyword=%s，目标博主数=%d，排除已有博主数=%d",
                keyword, max_bloggers, len(excluded))

    round_num = 0

    while len(seen) < max_bloggers:
        round_num += 1
        prev_count = len(seen)

        videos = await search_by_keyword(
            keyword,
            results_per_page=max(200, max_bloggers * 10),
        )

        for v in videos:
            uid = v.author.name.lstrip("@")
            if uid in excluded or uid in seen:
                continue
            seen[uid] = {
                "unique_id": uid,
                "nickname": v.author.nick_name or uid,
                "follower_count": v.author.fans or None,
            }
            if len(seen) >= max_bloggers:
                break

        logger.info("【候选库】第%d轮 已收集 %d/%d 个博主", round_num, len(seen), max_bloggers)

        if len(seen) >= max_bloggers:
            break
        # 连续一轮无新增，停止
        if len(seen) == prev_count:
            logger.info("【候选库】连续一轮无新增，停止，共收集 %d 个博主", len(seen))
            break

    return list(seen.values())


# ---------------------------------------------------------------------------
# 第二阶段：补全粉丝数并排序
# ---------------------------------------------------------------------------

async def _enrich_and_sort_bloggers(
    bloggers: list[dict[str, Any]],
    retry_delay: float,
) -> list[dict[str, Any]]:
    """
    对粉丝数为 None 的博主调 get_user_info 补全，然后按粉丝数从高到低排序。
    get_user_info 内部已有无限重试，此处不做额外并发限制。
    """
    needs_enrich = [b for b in bloggers if b.get("follower_count") is None]

    logger.info("【候选库】需要补全粉丝数的博主数量=%d", len(needs_enrich))

    async def _fetch_one(blogger: dict[str, Any]) -> None:
        info = await rapid_api.get_user_info(blogger["unique_id"], retry_delay=retry_delay)
        blogger["follower_count"] = info["follower_count"]
        if not blogger["nickname"] or blogger["nickname"] == blogger["unique_id"]:
            blogger["nickname"] = info["nickname"]

    tasks = [asyncio.create_task(_fetch_one(b)) for b in needs_enrich]
    if tasks:
        await asyncio.gather(*tasks)

    # 按粉丝数从高到低排序
    bloggers.sort(key=lambda b: b.get("follower_count") or 0, reverse=True)
    logger.info("【候选库】博主排序完成，top3: %s", [f"{b['unique_id']}({b.get('follower_count',0)})" for b in bloggers[:3]])
    return bloggers


# ---------------------------------------------------------------------------
# 第三阶段：对单个博主精搜 + 过滤
# ---------------------------------------------------------------------------

async def _search_blogger_videos(
    keyword: str,
    blogger: dict[str, Any],
    cfg: _SearchConfig,
) -> list[dict[str, Any]]:
    """
    用 Apify profiles 直接搜博主视频，不够时重搜一次。
    过滤掉时长 > max_duration / 播放量 < min_play_count / 发布超过 max_publish_days 天的视频。
    返回满足条件的视频列表（格式兼容旧 rapid_api 字段）。
    """
    import calendar
    unique_id = blogger["unique_id"]

    # 计算发布时间截止 Unix 时间戳
    cutoff_ts = 0
    oldest_date: str | None = None
    if cfg.publish_after_date:
        try:
            from datetime import datetime as _dt
            d = _dt.strptime(cfg.publish_after_date, "%Y-%m-%d")
            cutoff_ts = int(calendar.timegm(d.timetuple()))
            oldest_date = cfg.publish_after_date
        except ValueError:
            pass

    logger.info("【候选库】开始精搜博主 %s，max_videos=%d，max_dur=%ds，min_play=%d，publish_after=%s",
                unique_id, cfg.max_videos_per_blogger, cfg.max_duration_seconds,
                cfg.min_play_count, cfg.publish_after_date or "不限")

    seen_urls: set[str] = set()
    collected: list[dict[str, Any]] = []
    round_num = 0

    while len(collected) < cfg.max_videos_per_blogger:
        round_num += 1
        prev_count = len(collected)

        videos = await search_by_profiles(
            profiles=[unique_id],
            results_per_page=30,
            oldest_date=oldest_date,
            filter_params=TikTokFilter(
                min_play=cfg.min_play_count if cfg.min_play_count > 0 else None,
                sort_by=SortOrder.play_count,
                sort_descending=True,
            ),
        )

        for v in videos:
            url = v.web_video_url
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            # 时长过滤
            if v.video_meta.duration > cfg.max_duration_seconds:
                continue
            # 发布日期过滤
            if cutoff_ts > 0 and v.create_time < cutoff_ts:
                continue
            collected.append({
                "unique_id":    unique_id,
                "nickname":     v.author.nick_name or unique_id,
                "video_url":    url,
                "video_id":     v.id,
                "duration":     v.video_meta.duration,
                "play_count":   v.play_count,
                "like_count":   v.digg_count,
                "cover_url":    v.video_meta.cover_url,
                "video_title":  v.text,
                "create_time":  v.create_time,
                "follower_count": v.author.fans or None,
            })
            if len(collected) >= cfg.max_videos_per_blogger:
                break

        logger.info("【候选库】博主 %s 第%d轮，合规视频数=%d", unique_id, round_num, len(collected))

        # 连续一轮无新增，停止
        if len(collected) == prev_count:
            break

    logger.info("【候选库】博主 %s 精搜完成，合规视频数=%d", unique_id, len(collected))
    return collected


# ---------------------------------------------------------------------------
# AI 审核（Gemini）
# ---------------------------------------------------------------------------

async def _download_and_upload_video(video_url: str) -> str:
    """下载 TikTok 视频并上传到 CDN，返回 CDN URL。tikwm → RapidAPI → Apify fallback。"""
    from app.utils.tiktok_download import download_and_upload
    return await download_and_upload(video_url)


async def _ai_review_single(
    video_url: str,
    prompt: str,
    model: str,
    retry_delay: float = 5.0,
) -> tuple[bool, str]:
    """
    调用 Gemini API 审核单条视频。
    返回 (passed, reason)。遇到网络错误时无限重试。
    """
    import json as _json
    from app.services.ai_api import call_gemini_api

    json_instructions = (
        "\n\n请必须以JSON格式输出审核结果，包含以下字段：\n"
        "- \"pass\": 布尔值（true 表示通过审核，false 表示不通过）\n"
        "- \"reason\": 字符串（简短说明原因，不超过50字）\n"
        "示例输出：\n"
        "{\"pass\": false, \"reason\": \"视频内容与关键词不相关\"}"
    )
    final_prompt = prompt + json_instructions

    # 下载视频并上传到 CDN，获取可供 Gemini 访问的 URL
    cdn_url = await _download_and_upload_video(video_url)

    max_attempts = 1
    for attempt in range(1, max_attempts + 1):
        try:
            logger.info("【候选库AI审核】attempt=%d/%d model=%s video=%s", attempt, max_attempts, model, cdn_url)
            text = await call_gemini_api(
                model_name=model,
                video_url=cdn_url,
                prompt=final_prompt,
            )
            logger.info("【候选库AI审核】原始响应: %s", text[:200])

            # 解析 JSON
            cleaned = text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            elif cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            cleaned = cleaned.strip()

            result = _json.loads(cleaned)
            passed = bool(result.get("pass", True))
            reason = str(result.get("reason", "") or "")
            logger.info("【候选库AI审核】结果: pass=%s reason=%s", passed, reason)
            return passed, reason

        except Exception as exc:
            if attempt >= max_attempts:
                logger.error("【候选库AI审核】已达最大重试次数 %d，放弃: %s", max_attempts, exc)
                raise
            logger.warning("【候选库AI审核】请求异常，%.0fs后重试 (%d/%d): %s", retry_delay, attempt, max_attempts, exc)
            await asyncio.sleep(retry_delay)


async def _ai_review_candidates(
    session: AsyncSession,
    keyword_id: uuid.UUID | None,
    owner_id: uuid.UUID | None,
    cfg: _SearchConfig,
) -> None:
    """对新入库的候选视频进行 AI 审核，不通过的从数据库删除。"""
    if not cfg.ai_review_enabled or not cfg.ai_review_prompt.strip():
        logger.info("【候选库AI审核】未启用或提示词为空，跳过")
        return

    from app.services.google_api import get_google_api_key
    api_key = get_google_api_key()
    if not api_key:
        logger.warning("【候选库AI审核】GOOGLE_API_KEY 未配置，跳过")
        return

    # 查询待审核的视频（本次关键词入库的，hidden 的跳过）
    q = select(CandidateVideo).where(
        CandidateVideo.video_url.isnot(None),
        CandidateVideo.hidden.is_not(True),
    )
    if keyword_id is not None:
        q = q.where(CandidateVideo.keyword_id == keyword_id)
    if owner_id is not None:
        q = q.where(CandidateVideo.owner_id == owner_id)

    rows = (await session.scalars(q)).all()
    if not rows:
        return

    logger.info("【候选库AI审核】开始审核 %d 条视频", len(rows))
    sem = asyncio.Semaphore(_CONCURRENCY_AI_REVIEW)
    to_delete: list[CandidateVideo] = []

    async def _review_one(row: CandidateVideo) -> None:
        async with sem:
            prompt = cfg.ai_review_prompt.replace("{keyword}", row.keyword_text or "")
            passed, reason = await _ai_review_single(
                video_url=row.video_url,
                prompt=prompt,
                model=cfg.ai_review_model,
            )
            if not passed:
                to_delete.append(row)
                logger.info("【候选库AI审核】视频 %s 未通过审核，将删除，reason=%s", row.video_id, reason)

    tasks = [asyncio.create_task(_review_one(r)) for r in rows]
    await asyncio.gather(*tasks)

    if to_delete:
        for row in to_delete:
            await session.delete(row)
        await session.commit()
        logger.info("【候选库AI审核】已删除 %d 条未通过视频", len(to_delete))
    else:
        logger.info("【候选库AI审核】全部通过")


# ---------------------------------------------------------------------------
# 封面图上传 CDN
# ---------------------------------------------------------------------------

async def _upload_covers_batch(videos: list[dict[str, Any]]) -> None:
    """批量上传封面到 CDN，直接在 video dict 中写入 cdn_cover_url 字段。入库前调用。"""
    to_upload = [v for v in videos if v.get("cover_url")]
    if not to_upload:
        return

    sem = asyncio.Semaphore(_CONCURRENCY_COVER_UPLOAD)

    async def _upload_one(v: dict[str, Any]) -> None:
        async with sem:
            for attempt in range(1, 4):
                try:
                    result = await image_upload_service.upload_from_url(
                        v["cover_url"],
                        filename=f"candidate_{v['video_id']}.jpg",
                    )
                    cdn_url = result.get("url")
                    if cdn_url:
                        v["cdn_cover_url"] = cdn_url
                        logger.debug("【候选库】封面上传成功 video_id=%s cdn_url=%s", v["video_id"], cdn_url)
                    break
                except Exception as exc:
                    if attempt < 3:
                        logger.warning("【候选库】封面上传失败 video_id=%s (第%d次，准备重试): %s", v["video_id"], attempt, exc)
                        await asyncio.sleep(2)
                    else:
                        logger.warning("【候选库】封面上传失败 video_id=%s (已重试3次，放弃): %s", v["video_id"], exc)

    tasks = [asyncio.create_task(_upload_one(v)) for v in to_upload]
    await asyncio.gather(*tasks)
    logger.info("【候选库】本批 %d 张封面上传完成", len(to_upload))


# ---------------------------------------------------------------------------
# 共享视频裁剪：按播放量保留前 N 条
# ---------------------------------------------------------------------------

async def _trim_shared_top_n(
    session: AsyncSession,
    keyword_id: uuid.UUID,
    owner_id: uuid.UUID | None,
    top_n: int,
) -> None:
    """保留该关键词下共享视频播放量最高的 top_n 条，删除其余记录。"""
    q = select(CandidateVideo).where(
        CandidateVideo.keyword_id == keyword_id,
        CandidateVideo.template_type == "shared",
    )
    if owner_id is not None:
        q = q.where(CandidateVideo.owner_id == owner_id)

    rows = list((await session.scalars(q)).all())
    if len(rows) <= top_n:
        return

    # 按 play_count 降序排序，NULL 视为 0
    rows.sort(key=lambda r: r.play_count or 0, reverse=True)
    to_delete = rows[top_n:]
    delete_ids = [r.id for r in to_delete]

    await session.execute(
        sa_delete(CandidateVideo).where(CandidateVideo.id.in_(delete_ids))
    )
    await session.commit()
    logger.info("【候选库】共享视频裁剪：保留前 %d 条，删除 %d 条", top_n, len(delete_ids))


# ---------------------------------------------------------------------------
# Vendor 集成：候选库使用 external_supplement_service 发请求 + 接收回调
# ---------------------------------------------------------------------------

async def submit_candidate_supplement_request(
    *,
    owner_id: uuid.UUID | None,
    bloggers: list[dict[str, Any]],   # [{"unique_id", "nickname", "follower_count", ...}]
    keyword_id: uuid.UUID | None,
    keyword_text: str,
    cfg: _SearchConfig,
) -> str:
    """将候选库博主列表打包，以 vendor supplement 请求的形式发出。

    每个博主虚拟为一个 account_id（UUID），映射关系存入 business_context.blogger_by_account_id，
    callback 时 on_vendor_callback 用它还原博主信息。

    返回 request_id（str）。
    """
    from app.core.config import settings
    from app.db.session import SessionLocal
    from app.models.candidate_video import CandidateVideo
    from app.models.external_supplement_request import ExternalSupplementRequest
    from app.models.video_source import VideoSource

    if not bloggers:
        raise ValueError("blogger 列表为空，无法发起 vendor 请求")

    # 为每个博主生成一个虚拟 account_id，并记录映射
    blogger_by_account_id: dict[str, dict[str, Any]] = {}
    items: list[dict] = []

    # 查询每个博主在候选库下已有的视频 URL（dedup 用）
    existing_by_blogger: dict[str, list[str]] = {}
    if keyword_id is not None:
        async with SessionLocal() as session:
            rows = (await session.execute(
                select(CandidateVideo.blogger_unique_id, CandidateVideo.video_url)
                .where(
                    CandidateVideo.keyword_id == keyword_id,
                    CandidateVideo.owner_id == owner_id,
                    CandidateVideo.video_url.is_not(None),
                )
            )).all()
            for uid, url in rows:
                if uid and url:
                    existing_by_blogger.setdefault(uid, []).append(url)

    for b in bloggers:
        virtual_account_id = str(uuid.uuid4())
        unique_id = b["unique_id"]
        blogger_by_account_id[virtual_account_id] = {
            "unique_id": unique_id,
            "nickname": b.get("nickname") or unique_id,
            "follower_count": b.get("follower_count"),
        }
        items.append({
            "account_id": virtual_account_id,
            "blogger": {
                "handle": unique_id,
                "profile_url": f"https://www.tiktok.com/@{unique_id}",
                "tiktok_blogger_id": "",
            },
            "existing_video_urls": existing_by_blogger.get(unique_id, []),
        })

    # 构造 business_context（callback 时还原博主信息 + keyword 上下文）
    business_context = {
        "source_domain": "candidate",
        "keyword_id": str(keyword_id) if keyword_id else None,
        "keyword_text": keyword_text,
        "blogger_by_account_id": blogger_by_account_id,
        "exclusive_threshold": cfg.exclusive_threshold,
        "shared_top_n": cfg.shared_top_n,
    }

    # 组装 vendor payload（不走 _build_outbound_payload，因为这里博主不来自 AccountBloggerBinding）
    import secrets as _secrets
    from app.core.config import settings as _settings

    if not (_settings.vendor_supplement_api_url and _settings.vendor_supplement_api_key):
        raise RuntimeError("VENDOR_SUPPLEMENT_API_URL / VENDOR_SUPPLEMENT_API_KEY 未配置")

    request_id = uuid.uuid4()
    callback_secret = f"ec_cb_{_secrets.token_urlsafe(24)}"
    callback_url = ((_settings.vendor_callback_public_base or "").rstrip("/")
                    + "/api/v1/external/supplement-callback")

    filters: dict = {}
    if cfg.max_duration_seconds:
        filters["max_duration_seconds"] = cfg.max_duration_seconds
    if cfg.min_play_count:
        filters["min_view_count"] = cfg.min_play_count
    if cfg.publish_after_date:
        filters["published_after"] = cfg.publish_after_date

    payload = {
        "request_id": str(request_id),
        "callback_url": callback_url,
        "callback_auth": {
            "header_name": "X-API-Key",
            "header_value": callback_secret,
        },
        "mode": "exclusive",   # 候选库让 vendor 按 exclusive 模式抓，独享/共享由我们在 callback 里判断
        "platform": "tiktok",
        "target_video_count": cfg.max_videos_per_blogger,
        "filters": filters,
        "items": items,
    }

    # 持久化请求记录
    async with SessionLocal() as session:
        row = ExternalSupplementRequest(
            request_id=request_id,
            owner_id=owner_id,
            mode="exclusive",
            target_video_count=cfg.max_videos_per_blogger,
            filters=filters,
            account_ids=[it["account_id"] for it in items],
            callback_secret=callback_secret,
            status="pending",
            vendor_request_payload=payload,
            business_context=business_context,
        )
        session.add(row)
        await session.commit()

    # 调 vendor
    import httpx as _httpx
    import json as _json

    url = _settings.vendor_supplement_api_url.rstrip("/") + "/supplement-requests"
    api_key = (_settings.vendor_supplement_api_key or "").strip()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    logger.info(
        "【候选库→vendor】发起请求 request_id=%s keyword=%s bloggers=%d",
        request_id, keyword_text, len(bloggers),
    )
    try:
        async with _httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
        try:
            vendor_body = resp.json()
        except Exception:
            vendor_body = resp.text
        logger.info(
            "【候选库→vendor】vendor 响应 request_id=%s http=%s body=%s",
            request_id, resp.status_code,
            (_json.dumps(vendor_body, ensure_ascii=False)[:500]
             if isinstance(vendor_body, (dict, list)) else str(vendor_body)[:500]),
        )
        if resp.status_code != 200:
            async with SessionLocal() as session:
                r = await session.get(ExternalSupplementRequest, row.id)
                if r is not None:
                    r.status = "failed"
                    r.vendor_response = {"http_status": resp.status_code, "body": vendor_body}
                    await session.commit()
            raise RuntimeError(f"vendor 返回非 200: {resp.status_code} {vendor_body}")
        async with SessionLocal() as session:
            r = await session.get(ExternalSupplementRequest, row.id)
            if r is not None:
                r.vendor_response = {"http_status": resp.status_code, "body": vendor_body}
                await session.commit()
    except Exception as exc:
        logger.error("【候选库→vendor】请求失败 request_id=%s: %s", request_id, exc)
        raise

    return str(request_id)


async def _mark_candidate_request_completed(
    session: AsyncSession,
    request_id: uuid.UUID,
    written_count: int,
) -> None:
    """候选库写入完成后，更新 videos_accepted 并把 request 推为 completed。

    候选库不走 mark_video_completed，需要在此统一推状态，
    确保下次 callback 进来时入口 early-return 生效。
    """
    from sqlalchemy import select as sa_select
    from app.models.external_supplement_request import ExternalSupplementRequest
    from datetime import datetime, timezone
    try:
        req = await session.scalar(
            sa_select(ExternalSupplementRequest)
            .where(ExternalSupplementRequest.request_id == request_id)
            .with_for_update()
        )
        if req is not None and req.status not in ("completed", "failed"):
            req.videos_accepted = int(req.videos_accepted or 0) + written_count
            req.status = "completed"
            req.completed_at = datetime.now(timezone.utc)
            await session.commit()
            logger.info(
                "【候选库callback】request_id=%s 已写入 %d 条，推为 completed",
                request_id, written_count,
            )
    except Exception as exc:
        logger.warning("【候选库callback】推 completed 失败 request_id=%s: %s", request_id, exc)


async def on_vendor_callback(
    *,
    to_process: list[dict],            # [{"account_id": uuid, "video": {...}}]
    mode: str,
    owner_id: uuid.UUID | None,
    request_id: uuid.UUID,
    business_context: dict,
) -> None:
    """候选库 vendor callback 处理器。

    从 business_context 还原博主信息和 keyword 上下文，
    将 vendor 返回的视频按博主分组后写入 candidate_videos，
    并执行独享/共享阈值判断（逻辑与原 _search_blogger_videos 阶段一致）。
    """
    keyword_id_str: str | None = business_context.get("keyword_id")
    keyword_id: uuid.UUID | None = uuid.UUID(keyword_id_str) if keyword_id_str else None
    keyword_text: str = business_context.get("keyword_text") or ""
    blogger_by_account_id: dict[str, dict[str, Any]] = business_context.get("blogger_by_account_id") or {}
    exclusive_threshold: int = int(business_context.get("exclusive_threshold") or 10)
    shared_top_n: int = int(business_context.get("shared_top_n") or 50)

    logger.info(
        "【候选库callback】开始处理 request_id=%s keyword=%s entries=%d",
        request_id, keyword_text, len(to_process),
    )

    # 按 account_id（→ blogger）分组视频
    videos_by_account: dict[str, list[dict]] = {}
    for entry in to_process:
        aid = str(entry["account_id"])
        videos_by_account.setdefault(aid, []).append(entry["video"])

    # 按粉丝数排序（还原 blogger 列表顺序，高粉丝优先）
    ordered_accounts = sorted(
        videos_by_account.keys(),
        key=lambda aid: (blogger_by_account_id.get(aid) or {}).get("follower_count") or 0,
        reverse=True,
    )

    shared_videos: list[dict[str, Any]] = []   # 暂存已写入的共享视频（独享触发时清除）
    now = _utcnow()

    def _extract_video_id(v: dict) -> str:
        """从 vendor callback video dict 提取 video_id。
        extra 字段可能为 None，source_url 末尾即为视频 ID。
        """
        extra = v.get("extra") or {}
        return extra.get("video_id") or (v.get("source_url") or "").rstrip("/").split("/")[-1]

    from app.db.session import SessionLocal
    async with SessionLocal() as session:
        for aid in ordered_accounts:
            blogger_info = blogger_by_account_id.get(aid) or {}
            unique_id = blogger_info.get("unique_id") or aid
            nickname = blogger_info.get("nickname") or unique_id
            follower_count = blogger_info.get("follower_count")
            videos = videos_by_account[aid]

            logger.info(
                "【候选库callback】博主=%s videos=%d threshold=%d",
                unique_id, len(videos), exclusive_threshold,
            )

            if len(videos) >= exclusive_threshold:
                # 独享：清除已写入的共享记录，写独享，停止
                if shared_videos:
                    await session.execute(
                        sa_delete(CandidateVideo).where(
                            CandidateVideo.keyword_id == keyword_id,
                            CandidateVideo.owner_id == owner_id,
                            CandidateVideo.template_type == "shared",
                        )
                    )
                    await session.flush()
                    logger.info("【候选库callback】已清除共享记录，写入独享 blogger=%s", unique_id)

                rows_to_insert = [
                    dict(
                        id=uuid.uuid4(),
                        owner_id=owner_id,
                        keyword_id=keyword_id,
                        keyword_text=keyword_text,
                        template_type="exclusive",
                        blogger_unique_id=unique_id,
                        blogger_nickname=nickname,
                        blogger_follower_count=follower_count,
                        video_id=_extract_video_id(v),
                        video_url=v.get("source_url"),
                        video_title=v.get("video_title"),
                        duration=v.get("duration"),
                        cover_url=v.get("thumbnail_url"),
                        play_count=v.get("view_count"),
                        like_count=v.get("like_count"),
                        created_at=now,
                    )
                    for v in videos
                ]
                await _upload_covers_batch(rows_to_insert)
                if rows_to_insert:
                    stmt = pg_insert(CandidateVideo).values(rows_to_insert).on_conflict_do_nothing(
                        index_elements=["keyword_id", "blogger_unique_id", "video_id"]
                    )
                    await session.execute(stmt)
                await session.commit()

                logger.info(
                    "【候选库callback】keyword=%s 结果=独享 blogger=%s videos=%d",
                    keyword_text, unique_id, len(videos),
                )
                await _mark_candidate_request_completed(session, request_id, len(rows_to_insert))
                return

            else:
                # 共享：写入，继续下一个博主
                rows_to_insert = [
                    dict(
                        id=uuid.uuid4(),
                        owner_id=owner_id,
                        keyword_id=keyword_id,
                        keyword_text=keyword_text,
                        template_type="shared",
                        blogger_unique_id=unique_id,
                        blogger_nickname=nickname,
                        blogger_follower_count=follower_count,
                        video_id=_extract_video_id(v),
                        video_url=v.get("source_url"),
                        video_title=v.get("video_title"),
                        duration=v.get("duration"),
                        cover_url=v.get("thumbnail_url"),
                        play_count=v.get("view_count"),
                        like_count=v.get("like_count"),
                        created_at=now,
                    )
                    for v in videos
                ]
                await _upload_covers_batch(rows_to_insert)
                if rows_to_insert:
                    stmt = pg_insert(CandidateVideo).values(rows_to_insert).on_conflict_do_nothing(
                        index_elements=["keyword_id", "blogger_unique_id", "video_id"]
                    )
                    await session.execute(stmt)
                shared_videos.extend(rows_to_insert)
                await session.commit()
                logger.info(
                    "【候选库callback】博主=%s 进入共享（%d < %d），继续",
                    unique_id, len(videos), exclusive_threshold,
                )

        # 全部博主处理完仍是共享：按播放量裁剪
        if shared_top_n > 0 and keyword_id is not None:
            await _trim_shared_top_n(session, keyword_id, owner_id, shared_top_n)

        total_shared = len(shared_videos)
        logger.info(
            "【候选库callback】keyword=%s 结果=共享 videos=%d",
            keyword_text, total_shared,
        )
        await _mark_candidate_request_completed(session, request_id, total_shared)


# ---------------------------------------------------------------------------
# 导入视频库
# ---------------------------------------------------------------------------

async def _get_or_create_tag(session: AsyncSession, name: str, owner_id: uuid.UUID | None) -> uuid.UUID:
    """按名称查找标签，不存在则创建，返回 tag.id。"""
    from app.models.tag import Tag
    tag = await session.scalar(
        select(Tag).where(Tag.name == name, Tag.owner_id == owner_id)
    )
    if tag is None:
        tag = Tag(owner_id=owner_id, name=name)
        session.add(tag)
        await session.flush()  # 获取 id，不提交事务
    return tag.id


async def _download_then_enqueue_template(
    vs_id: uuid.UUID,
    tpl_id: uuid.UUID,
    owner_id: uuid.UUID | None,
    blogger_name: str | None,
    keyword_text: str | None,
    template_type: str | None = None,
) -> None:
    """后台协程：等待视频下载完成后打标签并将模板入队。"""
    from app.db.session import SessionLocal
    from app.models.video_ai_template import VideoAITemplate
    from app.models.video_source import VideoSource
    from app.models.tag import VideoSourceTag
    from app.services.video_ai_service import enqueue_template

    # 轮询下载状态，直到 done
    while True:
        try:
            async with SessionLocal() as session:
                vs = await session.scalar(select(VideoSource).where(VideoSource.id == vs_id))
                if vs is None:
                    logger.warning("【候选库→模板】video_source %s 已被删除，取消入队", vs_id)
                    return
                if vs.download_status == "done":
                    break
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            raise

    logger.info("【候选库→模板】video_source %s 下载完成，开始打标签并入队 tpl_id=%s", vs_id, tpl_id)

    try:
        async with SessionLocal() as session:
            # ---- 打标签（共享=仅关键词，独享=关键词+博主名） ----
            if template_type == "exclusive":
                tag_name_parts = [p.strip() for p in [keyword_text, blogger_name] if p and p.strip()]
            else:
                tag_name_parts = [keyword_text.strip()] if keyword_text and keyword_text.strip() else []
            if tag_name_parts:
                combined_tag_name = " ".join(tag_name_parts)
                tid = await _get_or_create_tag(session, combined_tag_name, owner_id)
                # 视频打标签
                existing_vs_tag = await session.scalar(
                    select(VideoSourceTag).where(
                        VideoSourceTag.video_source_id == vs_id,
                        VideoSourceTag.tag_id == tid,
                    )
                )
                if existing_vs_tag is None:
                    session.add(VideoSourceTag(owner_id=owner_id, video_source_id=vs_id, tag_id=tid))
                # 模板打标签
                existing_tpl_tag = await session.scalar(
                    select(VideoSourceTag).where(
                        VideoSourceTag.video_ai_template_id == tpl_id,
                        VideoSourceTag.tag_id == tid,
                    )
                )
                if existing_tpl_tag is None:
                    session.add(VideoSourceTag(owner_id=owner_id, video_ai_template_id=tpl_id, tag_id=tid))

            await session.commit()

        await enqueue_template(str(tpl_id))
        logger.info("【候选库→模板】tpl_id=%s 已入队", tpl_id)
    except Exception as exc:
        logger.exception("【候选库→模板】tpl_id=%s 入队失败: %s", tpl_id, exc)


async def _import_to_video_library(
    session: AsyncSession,
    keyword_id: uuid.UUID | None,
    owner_id: uuid.UUID | None,
    single_candidate_id: uuid.UUID | None = None,
) -> None:
    """将候选视频导入视频库（video_sources），完全复用 parse → create → download → 生成模板 四步流程。"""
    from app.schemas.video_source import VideoSourceCreate
    from app.services.video_source_service import (
        create_video_source,
        parse_video_url,
        trigger_download_and_upload,
    )

    _MAX_IMPORT_ATTEMPTS = 3

    q = select(CandidateVideo).where(
        CandidateVideo.video_url.isnot(None),
        CandidateVideo.video_source_id.is_(None),
        CandidateVideo.import_attempts < _MAX_IMPORT_ATTEMPTS,
        CandidateVideo.hidden.is_not(True),
    )
    if keyword_id is not None:
        q = q.where(CandidateVideo.keyword_id == keyword_id)
    if owner_id is not None:
        q = q.where(CandidateVideo.owner_id == owner_id)
    if single_candidate_id is not None:
        q = q.where(CandidateVideo.id == single_candidate_id)

    rows = list((await session.scalars(q)).all())
    if not rows:
        return

    total = len(rows)
    imported = 0
    skipped = 0

    logger.info("【候选库→视频库】开始导入 %d 条候选视频", total)

    for idx, cv in enumerate(rows, 1):
        try:
            # Step 1: Parse — 调 tikwm/RapidAPI 获取完整信息
            result = await parse_video_url(cv.video_url, session=session, owner_id=owner_id)

            if result.existing_id is not None:
                # 已存在，关联并跳过
                cv.video_source_id = result.existing_id
                await session.commit()
                skipped += 1
                logger.debug("【候选库→视频库】[%d/%d] 已存在，跳过 video_url=%s", idx, total, cv.video_url)
                continue

            # Step 2: Create — 用 parse 结果预填创建
            payload = VideoSourceCreate(
                source_url=result.source_url,
                platform=result.platform,
                blogger_name=result.blogger_name,
                video_title=result.video_title,
                video_desc=result.video_desc,
                video_url=result.video_url,
                thumbnail_url=result.thumbnail_url,
                view_count=result.view_count,
                like_count=result.like_count,
                favorite_count=result.favorite_count,
                comment_count=result.comment_count,
                share_count=result.share_count,
                publish_date=result.publish_date,
                duration=result.duration,
                width=result.width,
                height=result.height,
                aspect_ratio=result.aspect_ratio,
                extra=result.extra,
            )
            is_new, vs = await create_video_source(session, payload, owner_id)

            # 关联 video_source_id
            cv.video_source_id = vs.id
            await session.commit()

            if is_new:
                # Step 3: Download — 后台下载+上传
                await trigger_download_and_upload(session, vs.id, owner_id)

                # Step 4: 预先创建模板记录（pending，不入队），持久化后重启可恢复
                from app.models.enums import VideoAIProcessStatus
                from app.models.video_ai_template import VideoAITemplate
                tpl = VideoAITemplate(
                    owner_id=owner_id,
                    title=(vs.video_title or vs.blogger_name or "新模板")[:200],
                    description="",
                    video_source_id=vs.id,
                    process_status=VideoAIProcessStatus.pending,
                )
                if getattr(vs, "tiktok_blogger_id", None) is not None:
                    tpl.tiktok_blogger_id = vs.tiktok_blogger_id
                session.add(tpl)
                await session.commit()
                await session.refresh(tpl)

                # 后台协程：等下载完成后打标签并入队
                asyncio.create_task(
                    _download_then_enqueue_template(
                        vs_id=vs.id,
                        tpl_id=tpl.id,
                        owner_id=owner_id,
                        blogger_name=vs.blogger_name,
                        keyword_text=cv.keyword_text,
                        template_type=cv.template_type,
                    )
                )
                imported += 1
                logger.info("【候选库→视频库】[%d/%d] 导入成功 video_url=%s vs_id=%s tpl_id=%s（等待下载后入队）", idx, total, cv.video_url, vs.id, tpl.id)
            else:
                skipped += 1
                logger.debug("【候选库→视频库】[%d/%d] 已存在（create去重），跳过 video_url=%s", idx, total, cv.video_url)

        except Exception as exc:
            await session.rollback()
            # 重新加载 cv（rollback 后 ORM 对象已 detached）
            cv = await session.get(CandidateVideo, cv.id)
            if cv is not None:
                cv.import_attempts = (cv.import_attempts or 0) + 1
                await session.commit()
                if cv.import_attempts >= _MAX_IMPORT_ATTEMPTS:
                    logger.warning("【候选库→视频库】[%d/%d] 导入失败已达 %d 次上限，放弃 video_url=%s: %s", idx, total, _MAX_IMPORT_ATTEMPTS, cv.video_url, exc)
                else:
                    logger.warning("【候选库→视频库】[%d/%d] 导入失败（第%d次） video_url=%s: %s", idx, total, cv.import_attempts, cv.video_url, exc)
            else:
                logger.warning("【候选库→视频库】[%d/%d] 导入失败且记录已不存在: %s", idx, total, exc)

    logger.info("【候选库→视频库】导入完成：共 %d 条，新导入 %d，跳过 %d", total, imported, skipped)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

async def run_candidate_search(
    session: AsyncSession,
    keyword_text: str,
    keyword_id: uuid.UUID | None,
    owner_id: uuid.UUID | None,
) -> dict[str, Any]:
    """
    触发候选库搜索（后台异步任务，由 API 路由通过 asyncio.create_task 调用）。

    返回搜索摘要 {"template_type": "shared"|"exclusive", "video_count": int}。
    """
    # 读取配置（按用户；admin owner_id=None 时使用默认值）
    if owner_id is not None:
        cfg_row = await get_or_create_pipeline_settings(session, owner_id=owner_id)
        cfg = _SearchConfig(cfg_row)
    else:
        cfg = _SearchConfig(None)

    logger.info("【候选库】启动搜索 keyword=%s keyword_id=%s owner_id=%s 配置=%s",
                keyword_text, keyword_id, owner_id,
                f"max_bloggers={cfg.max_bloggers} threshold={cfg.exclusive_threshold} max_videos={cfg.max_videos_per_blogger} max_dur={cfg.max_duration_seconds}s")

    # 查询该关键词下已存在的博主（去重用）
    existing_bloggers: set[str] = set()
    if keyword_id is not None:
        rows = await session.scalars(
            select(CandidateVideo.blogger_unique_id).where(
                CandidateVideo.keyword_id == keyword_id,
                CandidateVideo.owner_id == owner_id,
            ).distinct()
        )
        existing_bloggers = set(rows.all())
        if existing_bloggers:
            logger.info("【候选库】该关键词已有 %d 个博主记录，将跳过这些博主", len(existing_bloggers))

    # 第一阶段：收集博主（排除已处理过的）
    bloggers = await _collect_bloggers(
        keyword_text, cfg.max_bloggers, cfg.retry_delay,
        exclude_bloggers=existing_bloggers,
    )

    # 第二阶段：补全粉丝数并排序
    bloggers = await _enrich_and_sort_bloggers(bloggers, cfg.retry_delay)

    # 第三阶段：将所有博主打包发给 vendor，独享/共享判断在 callback 中处理
    if not bloggers:
        logger.info("【候选库】博主列表为空，搜索结束")
        return {"template_type": "shared", "video_count": 0}

    request_id = await submit_candidate_supplement_request(
        owner_id=owner_id,
        bloggers=bloggers,
        keyword_id=keyword_id,
        keyword_text=keyword_text,
        cfg=cfg,
    )
    logger.info(
        "【候选库】已发起 vendor 请求 request_id=%s，等待 callback 回填候选视频",
        request_id,
    )
    # 返回 pending 状态，实际写入由 on_vendor_callback 完成
    return {"template_type": "pending", "video_count": 0, "request_id": request_id}


# ---------------------------------------------------------------------------
# 查询 / 删除
# ---------------------------------------------------------------------------

async def list_candidate_videos(
    session: AsyncSession,
    owner_id: uuid.UUID | None,
    *,
    keyword_id: uuid.UUID | None = None,
    template_type: str | None = None,
    imported: bool | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """分页查询候选视频。imported=True 查已导入库；imported=False 查候选库（未导入）；None 查全部。"""
    q = select(CandidateVideo).where(CandidateVideo.hidden.is_not(True))

    if owner_id is not None:
        q = q.where(CandidateVideo.owner_id == owner_id)
    if keyword_id is not None:
        q = q.where(CandidateVideo.keyword_id == keyword_id)
    if template_type is not None:
        q = q.where(CandidateVideo.template_type == template_type)
    if imported is True:
        q = q.where(CandidateVideo.status == CandidateVideoStatus.imported)
    elif imported is False:
        q = q.where(CandidateVideo.status != CandidateVideoStatus.imported)
    if status is not None:
        try:
            q = q.where(CandidateVideo.status == CandidateVideoStatus(status))
        except ValueError:
            pass  # 忽略非法 status 值

    # 总数
    from sqlalchemy import func
    count_q = select(func.count()).select_from(q.subquery())
    total = (await session.scalar(count_q)) or 0

    # 分页
    offset = (page - 1) * page_size
    rows = (await session.scalars(q.order_by(CandidateVideo.created_at.desc()).offset(offset).limit(page_size))).all()

    return {"total": total, "items": rows, "page": page, "page_size": page_size}


async def delete_candidate_video(
    session: AsyncSession,
    video_id: uuid.UUID,
    owner_id: uuid.UUID | None,
) -> bool:
    """删除单条候选视频，非 admin 需校验 owner"""
    row = await session.get(CandidateVideo, video_id)
    if row is None:
        return False
    if owner_id is not None and row.owner_id != owner_id:
        return False
    await session.delete(row)
    await session.commit()
    return True


async def set_candidate_video_hidden(
    session: AsyncSession,
    video_id: uuid.UUID,
    owner_id: uuid.UUID | None,
    hidden: bool,
) -> bool:
    """设置候选视频的隐藏状态，非 admin 需校验 owner。返回是否操作成功。"""
    row = await session.get(CandidateVideo, video_id)
    if row is None:
        return False
    if owner_id is not None and row.owner_id != owner_id:
        return False
    row.hidden = hidden
    await session.commit()
    return True


async def recover_candidate_imports_on_startup() -> None:
    """启动时恢复中断的候选视频导入：将 status=importing 的视频重新触发导入。"""
    from app.db.session import SessionLocal

    async with SessionLocal() as session:
        result = await session.execute(
            select(CandidateVideo.id).where(
                CandidateVideo.status == CandidateVideoStatus.importing,
            )
        )
        ids = [row[0] for row in result.fetchall()]

    if not ids:
        logger.info("【导入恢复】无中断的导入任务")
        return

    logger.info("【导入恢复】发现 %d 条中断任务，重新入队", len(ids))
    for cid in ids:
        asyncio.create_task(_import_single_by_id(cid))


async def _import_single_by_id(candidate_id: uuid.UUID) -> None:
    """以独立 session 重新导入单条 status=importing 的候选视频。"""
    from app.db.session import SessionLocal

    async with SessionLocal() as session:
        try:
            await _import_to_video_library(session, keyword_id=None, owner_id=None, single_candidate_id=candidate_id)
        except Exception as exc:
            logger.exception("【导入恢复】重新导入失败 candidate_id=%s: %s", candidate_id, exc)


# ---------------------------------------------------------------------------
# 手动批量 AI 审核
# ---------------------------------------------------------------------------

async def ai_review_candidates_by_ids(
    session: AsyncSession,
    candidate_ids: list[str],
    owner_id: str | None,
) -> dict:
    """手动触发批量 AI 审核。

    只处理 status IN (pending, ai_failed) 的视频。
    下载视频 → 上传 CDN → 调 Gemini → 更新状态。
    返回 {"reviewed": N, "passed": N, "failed": N}
    """
    from app.services.pipeline_settings_service import get_or_create_pipeline_settings
    import uuid as _uuid

    owner_uuid = _uuid.UUID(owner_id) if owner_id else None

    # 读取配置
    # pipeline_settings 按 owner 读取；admin 无 owner 时用默认空 UUID 兜底
    _cfg_owner = owner_uuid or _uuid.UUID(int=0)
    pipeline_settings = await get_or_create_pipeline_settings(session, _cfg_owner)
    cfg = _SearchConfig(pipeline_settings)

    # 查询目标视频
    logger.info("AI审核请求: candidate_ids=%s, owner_uuid=%s", candidate_ids, owner_uuid)
    q = select(CandidateVideo).where(
        CandidateVideo.id.in_([_uuid.UUID(i) for i in candidate_ids]),
        CandidateVideo.status.in_([CandidateVideoStatus.pending, CandidateVideoStatus.ai_failed]),
        CandidateVideo.hidden.is_not(True),
    )
    if owner_uuid is not None:
        q = q.where(CandidateVideo.owner_id == owner_uuid)
    result = await session.execute(q)
    rows = result.scalars().all()
    logger.info("AI审核查到视频数: %d", len(rows))

    reviewed = 0
    passed = 0
    failed = 0

    for row in rows:
        # 原子锁定（顺序执行，避免共享 session 并发冲突）
        lock_result = await session.execute(
            sa_update(CandidateVideo)
            .where(
                CandidateVideo.id == row.id,
                CandidateVideo.status.in_([CandidateVideoStatus.pending, CandidateVideoStatus.ai_failed]),
            )
            .values(status=CandidateVideoStatus.ai_reviewing)
            .returning(CandidateVideo.id)
        )
        if not lock_result.scalar():
            continue  # 已被其他任务锁定，跳过
        await session.commit()

        try:
            ok, reason = await _ai_review_single(
                video_url=row.video_url,
                prompt=cfg.ai_review_prompt.replace("{keyword}", row.keyword_text or ""),
                model=cfg.ai_review_model,
                retry_delay=cfg.retry_delay,
            )
            if ok:
                await session.execute(
                    sa_update(CandidateVideo)
                    .where(CandidateVideo.id == row.id)
                    .values(status=CandidateVideoStatus.importing, ai_reviewed=True, ai_error=None)
                )
                await session.commit()
                try:
                    await _import_to_video_library(session, row.keyword_id, owner_uuid, single_candidate_id=row.id)
                    await session.execute(
                        sa_update(CandidateVideo)
                        .where(CandidateVideo.id == row.id)
                        .values(status=CandidateVideoStatus.imported)
                    )
                    await session.commit()
                except Exception as imp_exc:
                    logger.error("AI审核通过但导入失败 video_id=%s: %s", row.video_id, imp_exc)
                    await session.rollback()
                    await session.execute(
                        sa_update(CandidateVideo)
                        .where(CandidateVideo.id == row.id)
                        .values(status=CandidateVideoStatus.import_failed, ai_error=str(imp_exc))
                    )
                    await session.commit()
                passed += 1
            else:
                await session.execute(
                    sa_update(CandidateVideo)
                    .where(CandidateVideo.id == row.id)
                    .values(status=CandidateVideoStatus.ai_failed, ai_reviewed=True, ai_error=reason or None)
                )
                await session.commit()
                failed += 1
            reviewed += 1
        except Exception as exc:
            logger.error("AI审核失败 video_id=%s: %s", row.video_id, exc)
            await session.rollback()
            await session.execute(
                sa_update(CandidateVideo)
                .where(CandidateVideo.id == row.id)
                .values(status=CandidateVideoStatus.ai_failed, ai_reviewed=True, ai_error=str(exc))
            )
            await session.commit()
            reviewed += 1
            failed += 1

    return {"reviewed": reviewed, "passed": passed, "failed": failed}


# ---------------------------------------------------------------------------
# 手动批量导入
# ---------------------------------------------------------------------------

async def import_candidates_by_ids(
    session: AsyncSession,
    candidate_ids: list[str],
    owner_id: str | None,
) -> dict:
    """手动触发批量导入 ai_passed 的视频到视频库。

    返回 {"imported": N, "failed": N}
    """
    import uuid as _uuid

    owner_uuid = _uuid.UUID(owner_id) if owner_id else None

    # 查询目标视频（跳过 ai_failed / import_failed，其余状态均可导入）
    _skip = [CandidateVideoStatus.ai_failed, CandidateVideoStatus.import_failed, CandidateVideoStatus.imported]
    q = select(CandidateVideo).where(
        CandidateVideo.id.in_([_uuid.UUID(i) for i in candidate_ids]),
        CandidateVideo.status.not_in(_skip),
        CandidateVideo.hidden.is_not(True),
    )
    if owner_uuid is not None:
        q = q.where(CandidateVideo.owner_id == owner_uuid)
    result = await session.execute(q)
    rows = result.scalars().all()

    imported_count = 0
    failed_count = 0

    for row in rows:
        # 锁定状态
        lock_result = await session.execute(
            sa_update(CandidateVideo)
            .where(
                CandidateVideo.id == row.id,
                CandidateVideo.status.not_in(_skip),
            )
            .values(status=CandidateVideoStatus.importing)
            .returning(CandidateVideo.id)
        )
        if not lock_result.scalar():
            continue
        await session.commit()

        try:
            # 调用已有的单条导入逻辑（按 keyword_id + video_id 过滤到单条）
            await _import_to_video_library(session, row.keyword_id, owner_uuid, single_candidate_id=row.id)
            await session.execute(
                sa_update(CandidateVideo)
                .where(CandidateVideo.id == row.id)
                .values(status=CandidateVideoStatus.imported)
            )
            await session.commit()
            imported_count += 1
        except Exception as exc:
            logger.error("导入失败 video_id=%s: %s", row.video_id, exc)
            await session.rollback()
            await session.execute(
                sa_update(CandidateVideo)
                .where(CandidateVideo.id == row.id)
                .values(status=CandidateVideoStatus.import_failed, ai_error=str(exc))
            )
            await session.commit()
            failed_count += 1

    return {"imported": imported_count, "failed": failed_count}


# ---------------------------------------------------------------------------
# 全量 AI 审核（后台 worker，支持并发、重启恢复）
# ---------------------------------------------------------------------------

_BULK_REVIEW_SEM = asyncio.Semaphore(_CONCURRENCY_AI_REVIEW)  # 全局并发控制


async def _process_one_ai_review(candidate_id: uuid.UUID) -> None:
    """处理单条视频的 AI 审核 + 导入，使用独立 session。"""
    from app.db.session import SessionLocal
    from app.services.pipeline_settings_service import get_or_create_pipeline_settings

    async with _BULK_REVIEW_SEM:
        async with SessionLocal() as session:
            row = await session.get(CandidateVideo, candidate_id)
            if not row or row.status != CandidateVideoStatus.ai_reviewing:
                return  # 已被其他任务处理或状态已变
            if row.hidden:
                logger.info("【全量审核】跳过 hidden 视频 candidate_id=%s", candidate_id)
                await session.execute(
                    sa_update(CandidateVideo)
                    .where(CandidateVideo.id == candidate_id)
                    .values(status=CandidateVideoStatus.pending)
                )
                await session.commit()
                return

            # 读取配置（用 row.owner_id 或兜底）
            cfg_owner = row.owner_id or uuid.UUID(int=0)
            pipeline_settings = await get_or_create_pipeline_settings(session, cfg_owner)
            cfg = _SearchConfig(pipeline_settings)

            try:
                ok, reason = await _ai_review_single(
                    video_url=row.video_url,
                    prompt=cfg.ai_review_prompt.replace("{keyword}", row.keyword_text or ""),
                    model=cfg.ai_review_model,
                    retry_delay=cfg.retry_delay,
                )
            except Exception as exc:
                logger.error("【全量审核】审核失败 candidate_id=%s: %s", candidate_id, exc)
                await session.rollback()
                await session.execute(
                    sa_update(CandidateVideo)
                    .where(CandidateVideo.id == candidate_id)
                    .values(status=CandidateVideoStatus.ai_failed, ai_reviewed=True, ai_error=str(exc))
                )
                await session.commit()
                return

            if ok:
                await session.execute(
                    sa_update(CandidateVideo)
                    .where(CandidateVideo.id == candidate_id)
                    .values(status=CandidateVideoStatus.importing, ai_reviewed=True, ai_error=None)
                )
                await session.commit()
                try:
                    await _import_to_video_library(session, row.keyword_id, row.owner_id, single_candidate_id=candidate_id)
                    await session.execute(
                        sa_update(CandidateVideo)
                        .where(CandidateVideo.id == candidate_id)
                        .values(status=CandidateVideoStatus.imported)
                    )
                    await session.commit()
                    logger.info("【全量审核】导入成功 candidate_id=%s", candidate_id)
                except Exception as exc:
                    logger.error("【全量审核】审核通过但导入失败 candidate_id=%s: %s", candidate_id, exc)
                    await session.rollback()
                    await session.execute(
                        sa_update(CandidateVideo)
                        .where(CandidateVideo.id == candidate_id)
                        .values(status=CandidateVideoStatus.import_failed, ai_error=str(exc))
                    )
                    await session.commit()
            else:
                await session.execute(
                    sa_update(CandidateVideo)
                    .where(CandidateVideo.id == candidate_id)
                    .values(status=CandidateVideoStatus.ai_failed, ai_reviewed=True, ai_error=reason or None)
                )
                await session.commit()
                logger.info("【全量审核】审核拒绝 candidate_id=%s reason=%s", candidate_id, reason)


async def trigger_bulk_ai_review(
    template_type: str | None = None,
    owner_id: str | None = None,
) -> dict:
    """将所有 pending 的候选视频标记为 ai_reviewing 并启动后台并发处理。

    重启恢复：重启时调用 recover_stuck_ai_review_on_startup() 重新捡起 ai_reviewing 的视频。
    """
    from app.db.session import SessionLocal

    async with SessionLocal() as session:
        owner_uuid = uuid.UUID(owner_id) if owner_id else None

        # 批量原子锁定：pending → ai_reviewing（跳过 ai_failed）
        stmt = (
            sa_update(CandidateVideo)
            .where(
                CandidateVideo.status == CandidateVideoStatus.pending,
                CandidateVideo.video_url.isnot(None),
            )
        )
        if template_type:
            stmt = stmt.where(CandidateVideo.template_type == template_type)
        if owner_uuid:
            stmt = stmt.where(CandidateVideo.owner_id == owner_uuid)

        stmt = stmt.values(status=CandidateVideoStatus.ai_reviewing).returning(CandidateVideo.id)
        result = await session.execute(stmt)
        ids = [row[0] for row in result.fetchall()]
        await session.commit()

    logger.info("【全量审核】已标记 %d 条视频为 ai_reviewing，启动后台处理", len(ids))

    for cid in ids:
        asyncio.create_task(_process_one_ai_review(cid))

    return {"queued": len(ids)}


async def recover_stuck_ai_review_on_startup() -> None:
    """启动时恢复：将 status=ai_reviewing 的视频重新投入后台处理队列。"""
    from app.db.session import SessionLocal

    async with SessionLocal() as session:
        # hidden 的视频若卡在 ai_reviewing，退回 pending
        hidden_result = await session.execute(
            sa_update(CandidateVideo)
            .where(
                CandidateVideo.status == CandidateVideoStatus.ai_reviewing,
                CandidateVideo.hidden.is_(True),
            )
            .values(status=CandidateVideoStatus.pending)
            .returning(CandidateVideo.id)
        )
        hidden_reset = len(hidden_result.fetchall())
        if hidden_reset:
            await session.commit()
            logger.info("【全量审核】启动恢复：重置 %d 条 hidden 视频从 ai_reviewing → pending", hidden_reset)

        result = await session.execute(
            select(CandidateVideo.id).where(
                CandidateVideo.status == CandidateVideoStatus.ai_reviewing,
                CandidateVideo.video_url.isnot(None),
                CandidateVideo.hidden.is_not(True),
            )
        )
        ids = [row[0] for row in result.fetchall()]

    if not ids:
        logger.info("【全量审核】启动恢复：无中断的 AI 审核任务")
        return

    logger.info("【全量审核】启动恢复：发现 %d 条中断任务，重新入队", len(ids))
    for cid in ids:
        asyncio.create_task(_process_one_ai_review(cid))


# ---------------------------------------------------------------------------
# 补充模板（为 AI 博主账号搜索并导入新视频）
# ---------------------------------------------------------------------------

async def supplement_templates_for_account(
    account_id: uuid.UUID,
    owner_id: uuid.UUID | None,
    template_type: str,  # "shared" | "exclusive"
    max_new_videos: int = 10,
) -> dict[str, Any]:
    """
    为单个 AI 博主账号补充模板。

    流程：边搜索边导入，成功导入才计数，失败则继续搜索下一个，
    直到凑够 max_new_videos 个成功为止（或搜索耗尽）。
    若 pipeline_settings.candidate_ai_review_enabled=True，则每条视频在写库前先过 AI 审核。
    """
    await _sync_account_template_tags_before_supplement(account_id, owner_id, "补充模板")

    from app.db.session import SessionLocal
    from app.models.account_tag import AccountTag
    from app.models.account_blogger_binding import AccountBloggerBinding
    from app.models.tag import Tag
    from app.models.tiktok_blogger import TiktokBlogger
    from app.models.video_source import VideoSource
    from app.models.video_ai_template import VideoAITemplate
    from app.models.enums import VideoAIProcessStatus
    from app.schemas.video_source import VideoSourceCreate
    from app.services.video_source_service import (
        create_video_source,
        parse_video_url,
        trigger_download_and_upload,
        download_video_to_cdn,
    )
    from app.services.pipeline_settings_service import get_or_create_pipeline_settings

    # 读取 AI 审核配置
    _cfg_owner = owner_id or uuid.UUID(int=0)
    async with SessionLocal() as session:
        _pipeline_cfg = await get_or_create_pipeline_settings(session, _cfg_owner)
        _search_cfg = _SearchConfig(_pipeline_cfg)
    ai_review_enabled = _search_cfg.ai_review_enabled
    ai_review_model = _search_cfg.ai_review_model
    ai_review_prompt = _search_cfg.ai_review_prompt

    # shared 模式：通过绑定标签的名称作为关键词搜索
    # exclusive 模式：通过绑定的 tiktok 博主 handle 搜索该博主的视频
    if template_type == "exclusive":
        async with SessionLocal() as session:
            blogger_handle: str | None = await session.scalar(
                select(TiktokBlogger.blogger_handle)
                .join(AccountBloggerBinding, AccountBloggerBinding.tiktok_blogger_id == TiktokBlogger.id)
                .where(AccountBloggerBinding.account_id == account_id)
                .where(TiktokBlogger.blogger_handle.is_not(None))
                .order_by(AccountBloggerBinding.created_at.asc())
                .limit(1)
            )
            # 取账号绑定的标签名用于打标签（而非博主 handle）
            exclusive_tag_name: str | None = await session.scalar(
                select(Tag.name)
                .join(AccountTag, AccountTag.tag_id == Tag.id)
                .where(AccountTag.account_id == account_id)
                .order_by(AccountTag.created_at.asc())
                .limit(1)
            )
        if not blogger_handle:
            logger.warning("【补充模板】account_id=%s exclusive 模式但无绑定博主 handle，跳过", account_id)
            return {"account_id": str(account_id), "keyword": None, "imported": 0, "skipped": 0}
        search_keyword = blogger_handle
        logger.info("【补充模板】account_id=%s blogger_handle=%s template_type=exclusive 开始", account_id, blogger_handle)
    else:
        async with SessionLocal() as session:
            stmt = (
                select(Tag.name)
                .join(AccountTag, AccountTag.tag_id == Tag.id)
                .where(AccountTag.account_id == account_id)
                .order_by(AccountTag.created_at.asc())
                .limit(1)
            )
            tag_name: str | None = await session.scalar(stmt)
        if not tag_name:
            logger.warning("【补充模板】account_id=%s 无绑定标签，跳过", account_id)
            return {"account_id": str(account_id), "keyword": None, "imported": 0, "skipped": 0}
        search_keyword = tag_name
        exclusive_tag_name = None
        logger.info("【补充模板】account_id=%s keyword=%s template_type=shared 开始", account_id, tag_name)

    imported = 0
    skipped = 0
    rejected = 0
    seen_urls: set[str] = set()       # 跨轮去重（web_video_url）
    attempted_urls: set[str] = set()  # 已尝试过（无论成功失败）
    pending_urls: list[str] = []
    results_per_page = max_new_videos * 5
    round_num = 0

    while imported < max_new_videos:
        # 当前批候选耗尽时重新搜索
        if not pending_urls:
            round_num += 1
            prev_seen = len(seen_urls)

            try:
                if template_type == "exclusive":
                    videos = await search_by_profiles(
                        profiles=[search_keyword],
                        results_per_page=results_per_page,
                    )
                else:
                    videos = await search_by_keyword(
                        search_keyword,
                        results_per_page=results_per_page,
                    )
            except Exception as exc:
                logger.warning("【补充模板】搜索失败 keyword=%s round=%d: %s", search_keyword, round_num, exc)
                break

            # 内部过滤截止时间戳（publish_after_date → unix ts）
            import calendar as _cal
            from datetime import datetime as _dt
            _cutoff_ts = 0
            if _search_cfg.publish_after_date:
                try:
                    _d = _dt.strptime(_search_cfg.publish_after_date, "%Y-%m-%d")
                    _cutoff_ts = int(_cal.timegm(_d.timetuple()))
                except ValueError:
                    _cutoff_ts = 0

            # 过滤已见过 / 已尝试过的，并按 pipeline_settings 内部过滤条件筛选；不满足就跳过继续查找
            batch_urls = []
            filtered_count = 0
            for v in videos:
                url = v.web_video_url
                if not url or url in seen_urls or url in attempted_urls:
                    continue
                seen_urls.add(url)
                # 内部过滤：时长上限
                if _search_cfg.max_duration_seconds > 0 and v.video_meta.duration > _search_cfg.max_duration_seconds:
                    filtered_count += 1
                    continue
                # 内部过滤：最少播放量
                if _search_cfg.min_play_count > 0 and v.play_count < _search_cfg.min_play_count:
                    filtered_count += 1
                    continue
                # 内部过滤：发布日期下限
                if _cutoff_ts > 0 and v.create_time < _cutoff_ts:
                    filtered_count += 1
                    continue
                batch_urls.append(url)

            logger.info("【补充模板】第%d轮搜索 keyword=%s 新URL=%d条 内部过滤丢弃=%d条",
                        round_num, search_keyword, len(batch_urls), filtered_count)

            if not batch_urls:
                # 连续一轮无新 URL，停止
                if len(seen_urls) == prev_seen:
                    logger.info("【补充模板】连续一轮无新URL，停止 keyword=%s imported=%d", search_keyword, imported)
                    break
                continue

            # 批量过滤已在库内的
            async with SessionLocal() as session:
                existing_urls = set(
                    (await session.scalars(
                        select(VideoSource.source_url).where(
                            VideoSource.source_url.in_(batch_urls),
                            VideoSource.owner_id == owner_id,
                        )
                    )).all()
                )

            for url in batch_urls:
                if url not in existing_urls:
                    pending_urls.append(url)
                else:
                    skipped += 1

            if not pending_urls:
                continue

        # 取下一个候选
        video_url = pending_urls.pop(0)
        attempted_urls.add(video_url)

        try:
            # ── Step 1: 解析元数据 ─────────────────────────────────────────
            async with SessionLocal() as session:
                parse_result = await parse_video_url(video_url, session=session, owner_id=owner_id)
                if parse_result.existing_id is not None:
                    skipped += 1
                    continue

            # ── Step 2: AI 审核（若启用）───────────────────────────────────
            local_video_url: str | None = None
            if ai_review_enabled:
                try:
                    local_video_url = await download_video_to_cdn(
                        parse_result.source_url,
                        title=parse_result.video_title,
                    )
                except Exception as exc:
                    logger.warning("【补充模板】下载/上传CDN失败，跳过 %s: %s", video_url, exc)
                    skipped += 1
                    continue

                prompt = (ai_review_prompt or "").replace("{keyword}", search_keyword)
                ai_passed, ai_reason = await _ai_review_single(
                    video_url=local_video_url,
                    prompt=prompt,
                    model=ai_review_model,
                    retry_delay=_search_cfg.retry_delay,
                )
                if not ai_passed:
                    logger.info(
                        "【补充模板】AI审核未通过，丢弃 %s reason=%s",
                        video_url, ai_reason,
                    )
                    rejected += 1
                    continue

                logger.info("【补充模板】AI审核通过 %s", video_url)

            # ── Step 3: 写库 ───────────────────────────────────────────────
            async with SessionLocal() as session:
                payload = VideoSourceCreate(
                    source_url=parse_result.source_url,
                    platform=parse_result.platform,
                    blogger_name=parse_result.blogger_name,
                    video_title=parse_result.video_title,
                    video_desc=parse_result.video_desc,
                    video_url=parse_result.video_url,
                    thumbnail_url=parse_result.thumbnail_url,
                    view_count=parse_result.view_count,
                    like_count=parse_result.like_count,
                    favorite_count=parse_result.favorite_count,
                    comment_count=parse_result.comment_count,
                    share_count=parse_result.share_count,
                    publish_date=parse_result.publish_date,
                    duration=parse_result.duration,
                    width=parse_result.width,
                    height=parse_result.height,
                    aspect_ratio=parse_result.aspect_ratio,
                    extra=parse_result.extra,
                )
                is_new, vs = await create_video_source(session, payload, owner_id)

                if not is_new:
                    skipped += 1
                    continue

                if local_video_url:
                    # AI 审核时已下载好，直接写入，避免重复下载
                    from app.utils.video_upload import current_upload_backend
                    if current_upload_backend() == "gcs":
                        vs.local_gcs_video_url = local_video_url
                    else:
                        vs.local_video_url = local_video_url
                    vs.download_status = "done"
                else:
                    await trigger_download_and_upload(session, vs.id, owner_id)

                tpl = VideoAITemplate(
                    owner_id=owner_id,
                    title=(vs.video_title or vs.blogger_name or "新模板")[:200],
                    description="",
                    video_source_id=vs.id,
                    process_status=VideoAIProcessStatus.pending,
                )
                if getattr(vs, "tiktok_blogger_id", None) is not None:
                    tpl.tiktok_blogger_id = vs.tiktok_blogger_id
                session.add(tpl)
                await session.commit()
                await session.refresh(tpl)

                vs_id = vs.id
                tpl_id = tpl.id

            asyncio.create_task(
                _download_then_enqueue_template(
                    vs_id=vs_id,
                    tpl_id=tpl_id,
                    owner_id=owner_id,
                    blogger_name=None,
                    keyword_text=exclusive_tag_name if template_type == "exclusive" else search_keyword,
                    template_type=template_type,
                )
            )
            imported += 1
            logger.info("【补充模板】[%d/%d] 导入成功 video_url=%s", imported, max_new_videos, video_url)

        except Exception as exc:
            # 导入失败：记录日志，继续尝试下一个
            logger.warning("【补充模板】导入失败，继续搜索下一个 video_url=%s: %s", video_url, exc)

    logger.info(
        "【补充模板】account_id=%s keyword=%s 完成：导入=%d 跳过=%d AI拒绝=%d",
        account_id, search_keyword, imported, skipped, rejected,
    )
    return {"account_id": str(account_id), "keyword": search_keyword, "imported": imported, "skipped": skipped, "rejected": rejected}


async def supplement_templates_for_accounts(
    account_ids: list[uuid.UUID],
    owner_id: uuid.UUID | None,
    template_type: str,
    max_new_videos: int = 10,
) -> list[dict[str, Any]]:
    """为多个账号并发（串行）补充模板，返回每个账号的结果列表。"""
    results = []
    for account_id in account_ids:
        result = await supplement_templates_for_account(
            account_id=account_id,
            owner_id=owner_id,
            template_type=template_type,
            max_new_videos=max_new_videos,
        )
        results.append(result)
    return results


# ---------------------------------------------------------------------------
# 自动补充（按分类类型过滤）
# ---------------------------------------------------------------------------

async def _classify_video_for_auto_supplement(
    local_video_url: str,
    owner_id: uuid.UUID | None,
) -> str | None:
    """对视频调用 Gemini 分类，返回 category_key 字符串或 None（失败时）。

    自动补充的过滤口径是「小类必须命中账号 single primary / dual primary+secondary」，
    因此这里直接返回 key，让调用方与 classification_summary.primary_key / secondary_key 比对。
    """
    from app.services.ai_api import call_gemini_api
    from app.services.pipeline_settings_service import get_or_create_pipeline_settings
    from app.db.session import SessionLocal
    from app.services.video_classification_service import (
        _DEFAULT_PROMPT, _RESPONSE_SCHEMA, _parse_category_key,
    )

    async with SessionLocal() as session:
        cfg_owner = owner_id if owner_id is not None else uuid.UUID(int=0)
        try:
            cfg = await get_or_create_pipeline_settings(session, owner_id=cfg_owner)
        except Exception:
            cfg = None

    model_name = (cfg.video_classify_model if cfg else "") or "gemini-3.1-pro-preview"
    prompt = (cfg.video_classify_prompt if cfg else "") or _DEFAULT_PROMPT
    temperature = float(cfg.video_classify_temperature) if cfg else 0.7

    try:
        text = await call_gemini_api(
            model_name=model_name,
            prompt=prompt,
            temperature=temperature,
            video_url=local_video_url,
            response_schema=_RESPONSE_SCHEMA,
            timeout=180.0,
        )
        return _parse_category_key(text or "")
    except Exception as exc:
        logger.warning("【自动补充】分类失败 url=%s: %s", local_video_url, exc)
        return None


async def auto_supplement_for_account(
    account_id: uuid.UUID,
    owner_id: uuid.UUID | None,
    max_new_videos: int = 10,
) -> dict[str, Any]:
    """
    根据 AI 博主的分类类型（single/dual）自动补充模板。
    流程：搜索 → 解析元数据 → 下载上传 CDN → Gemini 分类
         → 类别匹配才写 video_source + 建模板；不匹配直接丢弃，零 DB 记录。
    - single: 只允许 Top1 大类；dual: 允许 Top1 + Top2 大类
    """
    await _sync_account_template_tags_before_supplement(account_id, owner_id, "自动补充")

    from app.db.session import SessionLocal
    from app.models.account import Account
    from app.models.account_blogger_binding import AccountBloggerBinding
    from app.models.account_tag import AccountTag
    from app.models.tag import Tag
    from app.models.tiktok_blogger import TiktokBlogger
    from app.models.video_source import VideoSource
    from app.models.video_ai_template import VideoAITemplate
    from app.models.enums import VideoAIProcessStatus
    from app.schemas.video_source import VideoSourceCreate
    from app.services.video_source_service import (
        create_video_source,
        parse_video_url,
        download_video_to_cdn,
    )

    async with SessionLocal() as session:
        account = await session.get(Account, account_id)
        if account is None:
            return {"account_id": str(account_id), "error": "账号不存在", "imported": 0, "skipped": 0, "filtered": 0}
        cls_type = account.classification_type
        summary = account.classification_summary or {}
        primary_key = summary.get("primary_key")
        secondary_key = summary.get("secondary_key")

    if cls_type not in ("single", "dual"):
        return {
            "account_id": str(account_id),
            "error": f"账号分类类型为 {cls_type or '未分类'}，自动补充仅支持单核心/双核心账号",
            "imported": 0, "skipped": 0, "filtered": 0,
        }

    # 用小类 key 严格匹配（single → 仅 primary；dual → primary + secondary）
    allowed_keys: list[str] = []
    if isinstance(primary_key, str) and primary_key:
        allowed_keys.append(primary_key)
    if cls_type == "dual" and isinstance(secondary_key, str) and secondary_key:
        allowed_keys.append(secondary_key)
    if not allowed_keys:
        return {"account_id": str(account_id), "error": "无法确定允许的视频小类", "imported": 0, "skipped": 0, "filtered": 0}

    async with SessionLocal() as session:
        blogger_handle: str | None = await session.scalar(
            select(TiktokBlogger.blogger_handle)
            .join(AccountBloggerBinding, AccountBloggerBinding.tiktok_blogger_id == TiktokBlogger.id)
            .where(AccountBloggerBinding.account_id == account_id)
            .where(TiktokBlogger.blogger_handle.is_not(None))
            .order_by(AccountBloggerBinding.created_at.asc())
            .limit(1)
        )
        tag_name: str | None = await session.scalar(
            select(Tag.name)
            .join(AccountTag, AccountTag.tag_id == Tag.id)
            .where(AccountTag.account_id == account_id)
            .order_by(AccountTag.created_at.asc())
            .limit(1)
        )

    if not blogger_handle:
        return {"account_id": str(account_id), "error": "无绑定博主 handle", "imported": 0, "skipped": 0, "filtered": 0}

    # 读取 AI 审核配置
    from app.services.pipeline_settings_service import get_or_create_pipeline_settings
    _cfg_owner = owner_id or uuid.UUID(int=0)
    async with SessionLocal() as session:
        _pipeline_cfg = await get_or_create_pipeline_settings(session, _cfg_owner)
        _search_cfg = _SearchConfig(_pipeline_cfg)
    ai_review_enabled = _search_cfg.ai_review_enabled
    ai_review_model = _search_cfg.ai_review_model
    ai_review_prompt = _search_cfg.ai_review_prompt

    logger.info(
        "【自动补充】account_id=%s cls_type=%s allowed_keys=%s blogger=%s ai_review=%s 开始",
        account_id, cls_type, allowed_keys, blogger_handle, ai_review_enabled,
    )

    imported = 0
    skipped = 0
    filtered = 0
    rejected = 0
    seen_urls: set[str] = set()
    attempted_urls: set[str] = set()
    pending_urls: list[str] = []
    results_per_page = max_new_videos * 8
    round_num = 0

    while imported < max_new_videos:
        if not pending_urls:
            round_num += 1
            prev_seen = len(seen_urls)
            try:
                videos = await search_by_profiles(profiles=[blogger_handle], results_per_page=results_per_page)
            except Exception as exc:
                logger.warning("【自动补充】搜索失败 blogger=%s round=%d: %s", blogger_handle, round_num, exc)
                break

            batch_urls = []
            for v in videos:
                url = v.web_video_url
                if not url or url in seen_urls or url in attempted_urls:
                    continue
                seen_urls.add(url)
                batch_urls.append(url)

            logger.info("【自动补充】第%d轮搜索 blogger=%s 新URL=%d条", round_num, blogger_handle, len(batch_urls))

            if not batch_urls:
                if len(seen_urls) == prev_seen:
                    logger.info("【自动补充】连续一轮无新URL，停止 blogger=%s imported=%d", blogger_handle, imported)
                    break
                continue

            async with SessionLocal() as session:
                existing_urls = set(
                    (await session.scalars(
                        select(VideoSource.source_url).where(
                            VideoSource.source_url.in_(batch_urls),
                            VideoSource.owner_id == owner_id,
                        )
                    )).all()
                )
            for url in batch_urls:
                if url not in existing_urls:
                    pending_urls.append(url)
                else:
                    skipped += 1

            if not pending_urls:
                continue

        video_url = pending_urls.pop(0)
        attempted_urls.add(video_url)

        try:
            # ── Step 1: 解析元数据（不写 DB）──────────────────────────────
            async with SessionLocal() as session:
                parse_result = await parse_video_url(video_url, session=session, owner_id=owner_id)
                if parse_result.existing_id is not None:
                    skipped += 1
                    continue

            # ── Step 2: 下载 + 上传 CDN，得到永久 URL ─────────────────────
            try:
                local_video_url = await download_video_to_cdn(
                    parse_result.source_url,
                    title=parse_result.video_title,
                )
            except Exception as exc:
                logger.warning("【自动补充】下载/上传失败，跳过 %s: %s", video_url, exc)
                skipped += 1
                continue

            # ── Step 3: AI 审核（若启用）先跑，比 Gemini 分类更便宜 ────────
            if ai_review_enabled:
                prompt = (ai_review_prompt or "").replace("{keyword}", tag_name or blogger_handle or "")
                ai_passed, ai_reason = await _ai_review_single(
                    video_url=local_video_url,
                    prompt=prompt,
                    model=ai_review_model,
                    retry_delay=_search_cfg.retry_delay,
                )
                if not ai_passed:
                    logger.info(
                        "【自动补充】AI审核未通过，丢弃 %s reason=%s",
                        video_url, ai_reason,
                    )
                    rejected += 1
                    continue
                logger.info("【自动补充】AI审核通过 %s", video_url)

            # ── Step 3.5: Gemini 分类（小类必须命中 allowed_keys）─────────
            category_key = await _classify_video_for_auto_supplement(local_video_url, owner_id)
            if category_key is None or category_key not in allowed_keys:
                logger.info(
                    "【自动补充】分类不匹配 key=%s allowed=%s，丢弃（不写库）%s",
                    category_key, allowed_keys, video_url,
                )
                filtered += 1
                continue

            # ── Step 4: 审核通过 + 分类通过 → 写 video_source（local_video_url 已就绪）
            async with SessionLocal() as session:
                payload = VideoSourceCreate(
                    source_url=parse_result.source_url,
                    platform=parse_result.platform,
                    blogger_name=parse_result.blogger_name,
                    video_title=parse_result.video_title,
                    video_desc=parse_result.video_desc,
                    video_url=parse_result.video_url,
                    thumbnail_url=parse_result.thumbnail_url,
                    view_count=parse_result.view_count,
                    like_count=parse_result.like_count,
                    favorite_count=parse_result.favorite_count,
                    comment_count=parse_result.comment_count,
                    share_count=parse_result.share_count,
                    publish_date=parse_result.publish_date,
                    duration=parse_result.duration,
                    width=parse_result.width,
                    height=parse_result.height,
                    aspect_ratio=parse_result.aspect_ratio,
                    extra=parse_result.extra,
                )
                is_new, vs = await create_video_source(session, payload, owner_id)
                if not is_new:
                    skipped += 1
                    continue
                # 直接写入已上传好的 URL，跳过重复下载
                from app.utils.video_upload import current_upload_backend
                if current_upload_backend() == "gcs":
                    vs.local_gcs_video_url = local_video_url
                else:
                    vs.local_video_url = local_video_url
                vs.download_status = "done"
                vs_id = vs.id
                tiktok_blogger_id = vs.tiktok_blogger_id

                tpl = VideoAITemplate(
                    owner_id=owner_id,
                    title=(parse_result.video_title or parse_result.blogger_name or "新模板")[:200],
                    description="",
                    video_source_id=vs_id,
                    process_status=VideoAIProcessStatus.pending,
                )
                if tiktok_blogger_id is not None:
                    tpl.tiktok_blogger_id = tiktok_blogger_id
                session.add(tpl)
                await session.commit()
                await session.refresh(tpl)
                tpl_id = tpl.id

            # ── Step 5: 打标签并入队 AI 处理 ──────────────────────────────
            asyncio.create_task(
                _download_then_enqueue_template(
                    vs_id=vs_id,
                    tpl_id=tpl_id,
                    owner_id=owner_id,
                    blogger_name=None,
                    keyword_text=tag_name or blogger_handle,
                    template_type="exclusive",
                )
            )
            imported += 1
            logger.info("【自动补充】[%d/%d] 分类=%s 导入成功 %s", imported, max_new_videos, major, video_url)

        except Exception as exc:
            logger.warning("【自动补充】处理失败，继续下一个 video_url=%s: %s", video_url, exc)

    logger.info(
        "【自动补充】account_id=%s 完成：导入=%d 跳过=%d 过滤=%d AI拒绝=%d",
        account_id, imported, skipped, filtered, rejected,
    )
    return {
        "account_id": str(account_id),
        "imported": imported,
        "skipped": skipped,
        "filtered": filtered,
        "rejected": rejected,
        "allowed_keys": allowed_keys,
    }


async def auto_supplement_for_accounts(
    account_ids: list[uuid.UUID],
    owner_id: uuid.UUID | None,
    max_new_videos: int = 10,
) -> list[dict[str, Any]]:
    """为多个账号串行执行自动补充。"""
    results = []
    for account_id in account_ids:
        result = await auto_supplement_for_account(
            account_id=account_id,
            owner_id=owner_id,
            max_new_videos=max_new_videos,
        )
        results.append(result)
    return results
