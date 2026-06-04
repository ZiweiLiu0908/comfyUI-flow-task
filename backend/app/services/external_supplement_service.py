"""「补充模板」外包给 vendor 的服务层。

对应文档：docs/external_supplement_api.md

两条主路径：
  1. submit_supplement_request(...)  我们 → vendor
  2. handle_supplement_callback(...) vendor → 我们

callback 入库流程：
  - 校验 request_id + X-API-Key
  - 对每条 video：
    a. source_url 去重 → 已存在则 duplicated +1
    b. 写 video_sources（local_video_url 先暂存原 gs:// URI，download_status="downloading"）
    c. 写 video_ai_template(pending) + 绑定账号 tag
    d. 异步任务：gs:// → 本地 tmp → 上传我们 CDN → 更新 local_video_url + download_status=done
       → 触发 AI pipeline（auto 模式由 pipeline 跑分类阶段后过滤）
"""
from __future__ import annotations

import asyncio
import logging
import os
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.external_supplement_request import ExternalSupplementRequest
from app.models.external_supplement_request_item import ExternalSupplementRequestItem

logger = logging.getLogger("app.external_supplement_service")


# ── outbound: 我们 → vendor ────────────────────────────────────────────────────

def _vendor_configured() -> bool:
    return bool(settings.vendor_supplement_api_url and settings.vendor_supplement_api_key)


def _build_callback_url() -> str:
    base = (settings.vendor_callback_public_base or "").rstrip("/")
    if not base:
        raise RuntimeError("VENDOR_CALLBACK_PUBLIC_BASE 未配置，无法构造 callback_url")
    return f"{base}/api/v1/external/supplement-callback"


async def _build_outbound_payload(
    *,
    session: AsyncSession,
    request_id: uuid.UUID,
    callback_secret: str,
    owner_id: uuid.UUID | None,
    mode: str,
    target_video_count: int,
    filters: dict,
    account_ids: list[uuid.UUID],
) -> dict:
    """根据 account_ids 反查绑定博主 + 已有视频，组装 outbound payload。"""
    from app.models.account_blogger_binding import AccountBloggerBinding
    from app.models.tiktok_blogger import TiktokBlogger
    from app.models.video_source import VideoSource
    from app.models.video_task import VideoTask

    # 1. 拉每个账号绑定的第一个博主（与原 candidate_service 口径一致）
    binding_rows = (await session.execute(
        select(
            AccountBloggerBinding.account_id,
            TiktokBlogger.id,
            TiktokBlogger.blogger_handle,
            TiktokBlogger.blogger_id,
        )
        .join(TiktokBlogger, TiktokBlogger.id == AccountBloggerBinding.tiktok_blogger_id)
        .where(AccountBloggerBinding.account_id.in_(account_ids))
        .where(TiktokBlogger.blogger_handle.is_not(None))
        .order_by(AccountBloggerBinding.created_at.asc())
    )).all()

    blogger_by_account: dict[uuid.UUID, tuple[uuid.UUID, str, str | None]] = {}
    for aid, tb_id, handle, tb_external_id in binding_rows:
        if aid in blogger_by_account:
            continue  # 只取第一个
        blogger_by_account[aid] = (tb_id, handle, tb_external_id)

    # 2. 已有视频：按 tiktok_blogger_id 反查 video_sources
    tb_ids = [v[0] for v in blogger_by_account.values()]
    existing_by_blogger: dict[uuid.UUID, list[str]] = {tid: [] for tid in tb_ids}
    if tb_ids:
        vs_rows = (await session.execute(
            select(VideoSource.tiktok_blogger_id, VideoSource.source_url)
            .where(VideoSource.tiktok_blogger_id.in_(tb_ids))
            .where(VideoSource.source_url.is_not(None))
        )).all()
        for tb_id, src in vs_rows:
            if tb_id is not None and src:
                existing_by_blogger.setdefault(tb_id, []).append(src)

    # 3. 组装 items
    items: list[dict] = []
    skipped: list[str] = []
    for aid in account_ids:
        bound = blogger_by_account.get(aid)
        if bound is None:
            skipped.append(str(aid))
            continue
        tb_id, handle, tb_external_id = bound
        items.append({
            "account_id": str(aid),
            "blogger": {
                "handle": handle,
                "profile_url": f"https://www.tiktok.com/@{handle}",
                "tiktok_blogger_id": tb_external_id or "",
            },
            "existing_video_urls": existing_by_blogger.get(tb_id, []),
        })
    if skipped:
        logger.warning(
            "external_supplement: %d 账号没有绑定博主 / handle 缺失，跳过：%s",
            len(skipped), skipped[:10],
        )

    payload: dict = {
        "request_id": str(request_id),
        "callback_url": _build_callback_url(),
        "callback_auth": {
            "header_name": "X-API-Key",
            "header_value": callback_secret,
        },
        "mode": mode,
        "platform": "tiktok",
        "target_video_count": target_video_count,
        "filters": filters or {},
        "items": items,
        "_skipped_account_ids": skipped,
    }
    return payload


async def submit_supplement_request(
    *,
    owner_id: uuid.UUID | None,
    account_ids: list[uuid.UUID],
    mode: str,                        # "exclusive" | "auto"
    target_video_count: int,
    filters: dict | None = None,
    business_context: dict | None = None,
) -> dict:
    """构造 outbound payload → POST 给 vendor → 写一条 external_supplement_requests。

    返回 vendor 响应 + 我们生成的 request_id（便于 UI 显示）。

    business_context: 调用方写入的业务元数据，不传给 vendor，仅用于 callback 时的 dispatch。
      示例（候选库）：{"source_domain": "candidate", "keyword_id": "...", "keyword_text": "..."}
      示例（AI博主）：{"source_domain": "ai_blogger"}
      若未传入，默认补充 source_domain="ai_blogger" 以兼容存量逻辑。
    """
    if mode not in ("exclusive", "auto"):
        raise ValueError(f"mode 必须是 exclusive 或 auto，收到: {mode}")
    if not _vendor_configured():
        raise RuntimeError("VENDOR_SUPPLEMENT_API_URL / VENDOR_SUPPLEMENT_API_KEY 未配置")

    # 补充默认 source_domain，确保 callback dispatch 始终有据可查
    ctx = dict(business_context or {})
    ctx.setdefault("source_domain", "ai_blogger")

    request_id = uuid.uuid4()
    callback_secret = f"ec_cb_{secrets.token_urlsafe(24)}"

    async with SessionLocal() as session:
        payload = await _build_outbound_payload(
            session=session,
            request_id=request_id,
            callback_secret=callback_secret,
            owner_id=owner_id,
            mode=mode,
            target_video_count=target_video_count,
            filters=filters or {},
            account_ids=account_ids,
        )

        if not payload["items"]:
            raise ValueError("所有账号都没有绑定博主，无法发起补充请求")

        # 持久化（先写一行，状态 pending；vendor 调用失败也能记录到）
        skipped_account_ids = list(payload.pop("_skipped_account_ids", []))
        row = ExternalSupplementRequest(
            request_id=request_id,
            owner_id=owner_id,
            mode=mode,
            target_video_count=target_video_count,
            filters=filters or {},
            account_ids=[str(aid) for aid in account_ids],
            callback_secret=callback_secret,
            status="pending",
            vendor_request_payload=payload,
            business_context=ctx,
        )
        session.add(row)
        from app.services.supplement_status_service import create_request_items
        await create_request_items(
            session,
            request_id=request_id,
            owner_id=owner_id,
            mode=mode,
            target_video_count=target_video_count,
            payload_items=payload["items"],
            skipped_account_ids=skipped_account_ids,
        )
        await session.commit()

    # 调 vendor
    url = settings.vendor_supplement_api_url.rstrip("/") + "/supplement-requests"
    api_key = (settings.vendor_supplement_api_key or "").strip()
    if not api_key:
        raise RuntimeError("VENDOR_SUPPLEMENT_API_KEY 未配置")
    try:
        api_key.encode("ascii")
    except UnicodeEncodeError:
        raise RuntimeError(
            "VENDOR_SUPPLEMENT_API_KEY 含非 ASCII 字符，请检查 .env 是否误把注释/占位符当成 key"
        )
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    import json as _json
    bloggers_preview = [
        {
            "account_id": it["account_id"],
            "blogger": it["blogger"]["handle"],
            "existing_videos": len(it.get("existing_video_urls") or []),
        }
        for it in payload["items"]
    ]
    logger.info(
        "[ext_supp][outbound] → vendor: request_id=%s mode=%s url=%s target=%d filters=%s items=%d",
        request_id, mode, url, target_video_count,
        payload.get("filters") or {}, len(payload["items"]),
    )
    logger.info(
        "[ext_supp][outbound] payload.items=%s",
        _json.dumps(bloggers_preview, ensure_ascii=False),
    )
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
        vendor_body: Any = None
        try:
            vendor_body = resp.json()
        except Exception:
            vendor_body = resp.text
        logger.info(
            "[ext_supp][outbound] ← vendor: request_id=%s http=%s body=%s",
            request_id, resp.status_code,
            (_json.dumps(vendor_body, ensure_ascii=False)[:1000]
             if isinstance(vendor_body, (dict, list))
             else str(vendor_body)[:1000]),
        )
    except Exception as exc:
        logger.error("[ext_supp][outbound] POST failed request_id=%s: %s", request_id, exc)
        async with SessionLocal() as session:
            r = await session.get(ExternalSupplementRequest, row.id)
            if r is not None:
                r.status = "failed"
                r.vendor_response = {"error": str(exc)}
                from app.services.supplement_status_service import mark_request_failed
                await mark_request_failed(
                    session,
                    request_id=request_id,
                    error_message=str(exc),
                )
                await session.commit()
        raise

    # 落 vendor response
    async with SessionLocal() as session:
        r = await session.get(ExternalSupplementRequest, row.id)
        if r is not None:
            r.vendor_response = {"http_status": resp.status_code, "body": vendor_body}
            if resp.status_code != 200 or (
                isinstance(vendor_body, dict) and vendor_body.get("status") == "rejected"
            ):
                r.status = "failed"
                from app.services.supplement_status_service import mark_request_failed
                await mark_request_failed(
                    session,
                    request_id=request_id,
                    error_message=f"vendor 返回失败: {vendor_body}",
                )
            await session.commit()

    return {
        "request_id": str(request_id),
        "vendor_http_status": resp.status_code,
        "vendor_response": vendor_body,
        "submitted_items": len(payload["items"]),
        "skipped_accounts": len(account_ids) - len(payload["items"]),
    }


# ── inbound: vendor → 我们 ─────────────────────────────────────────────────────

async def fetch_request_by_id(
    session: AsyncSession, request_id: uuid.UUID,
) -> ExternalSupplementRequest | None:
    return await session.scalar(
        select(ExternalSupplementRequest).where(
            ExternalSupplementRequest.request_id == request_id,
        )
    )


async def handle_supplement_callback(
    *,
    request_id: uuid.UUID,
    mode: str,
    final: bool,
    items: list,  # list[CallbackItem]
    header_secret: str,
) -> dict:
    """处理 vendor 的回调：校验 → dedup → 调度异步处理（AI 审核 + auto 分类 + 写库 + enqueue）。

    与原 candidate_service.supplement_templates_for_account 行为一致，只是
    「搜索 + 下载」环节被外包给 vendor。
    """
    from app.models.video_source import VideoSource

    async with SessionLocal() as session:
        req = await fetch_request_by_id(session, request_id)
        if req is None:
            logger.warning("supplement-callback 404: request_id=%s", request_id)
            return {
                "request_id": str(request_id),
                "accepted": 0,
                "duplicated": 0,
                "rejected": 0,
                "message": "request_id not found",
                "http_status": 404,
            }
        if req.callback_secret != header_secret:
            logger.warning(
                "supplement-callback 401: request_id=%s 密钥不匹配",
                request_id,
            )
            return {
                "request_id": str(request_id),
                "accepted": 0,
                "duplicated": 0,
                "rejected": 0,
                "message": "invalid X-API-Key",
                "http_status": 401,
            }

        owner_id = req.owner_id
        request_account_ids = {str(aid) for aid in (req.account_ids or [])}

        # 鉴权通过后立刻持久化原始 callback payload，方便排查问题
        # 与后续业务处理解耦：无论下游逻辑走到哪，原始数据都已落库
        import json as _json
        _raw_log_entry = {
            "received_at": datetime.now(timezone.utc).isoformat(),
            "mode": mode,
            "final": final,
            "items": [
                {
                    "account_id": str(it.account_id),
                    "status": it.status,
                    "error": it.error,
                    "videos": [v.model_dump(mode="json") for v in it.videos],
                }
                for it in items
            ],
        }
        try:
            async with SessionLocal() as _log_session:
                await _log_session.execute(
                    sa_text(
                        "UPDATE external_supplement_requests "
                        "SET callbacks_log = cast(callbacks_log as jsonb) || cast(:entry as jsonb) "
                        "WHERE request_id = cast(:rid as uuid)"
                    ),
                    {
                        "entry": _json.dumps([_raw_log_entry], ensure_ascii=False),
                        "rid": str(request_id),
                    },
                )
                await _log_session.commit()
        except Exception as _log_exc:
            logger.warning("[ext_supp][callback] callbacks_log 写入失败（不影响主流程）: %s", _log_exc)

        # 已达到 target 数量则直接跳过，不走任何业务逻辑
        # 用 videos_accepted（已调度入 pipeline 的数量）判断，不依赖异步 pipeline 的结果
        #
        # ⚠️ req.target_video_count 是单个账号的 target（如 100），
        # 整个 request 的总 target 是各 item.target_video_count 之和。
        # 必须对比「所有 item 的 target 合计」，否则多账号场景下总 accepted 超过
        # 单账号 target 就会被错误截断。
        _items_for_target = (await session.execute(
            select(ExternalSupplementRequestItem.target_video_count)
            .where(ExternalSupplementRequestItem.request_id == request_id)
            .where(ExternalSupplementRequestItem.status != "skipped")
        )).scalars().all()
        total_target_count = sum(int(t or 0) for t in _items_for_target)
        already_accepted = int(req.videos_accepted or 0)
        if total_target_count > 0 and already_accepted >= total_target_count:
            logger.info(
                "[ext_supp][callback] total target already reached (%d/%d across %d items), skip all processing: request_id=%s",
                already_accepted, total_target_count, len(_items_for_target), request_id,
            )
            req.callbacks_received = (req.callbacks_received or 0) + 1
            if req.status not in ("completed", "failed"):
                req.status = "completed"
                req.completed_at = datetime.now(timezone.utc)
            await session.commit()
            return {
                "request_id": str(request_id),
                "accepted": 0,
                "duplicated": 0,
                "rejected": 0,
                "message": "target already reached",
                "http_status": 200,
            }

        import json as _json
        total_videos = sum(len(it.videos) for it in items)
        logger.info(
            "[ext_supp][callback] ← vendor: request_id=%s mode=%s final=%s items=%d videos=%d",
            request_id, mode, final, len(items), total_videos,
        )
        callback_preview = [
            {
                "account_id": str(it.account_id),
                "status": it.status,
                "videos": len(it.videos),
                "video_urls": [v.source_url for v in it.videos][:5],
                "error": it.error,
            }
            for it in items
        ]
        logger.info(
            "[ext_supp][callback] payload.items=%s",
            _json.dumps(callback_preview, ensure_ascii=False)[:2000],
        )

        scheduled = 0       # 进入异步 pipeline 的数量
        duplicated = 0
        rejected = 0
        to_process: list[dict] = []  # 每条记录的所有必要字段
        progress_by_account: dict[uuid.UUID, dict[str, Any]] = {}

        for it in items:
            account_id = it.account_id
            progress_by_account.setdefault(
                account_id,
                {"scheduled": 0, "duplicated": 0, "rejected": 0, "error": it.error},
            )
            if str(account_id) not in request_account_ids:
                logger.warning(
                    "supplement-callback: account_id %s 不在本 request %s 范围内，跳过",
                    account_id, request_id,
                )
                rejected += len(it.videos)
                progress_by_account[account_id]["rejected"] += len(it.videos)
                continue

            for v in it.videos:
                if not v.source_url or not v.local_video_url:
                    rejected += 1
                    progress_by_account[account_id]["rejected"] += 1
                    continue
                # 同步快速 dedup
                existing = await session.scalar(
                    select(VideoSource.id).where(VideoSource.source_url == v.source_url)
                )
                if existing is not None:
                    duplicated += 1
                    progress_by_account[account_id]["duplicated"] += 1
                    continue
                to_process.append({
                    "account_id": account_id,
                    "video": v.model_dump(),  # 全部字段，async 阶段需要
                })
                scheduled += 1
                progress_by_account[account_id]["scheduled"] += 1

        if final:
            for aid in request_account_ids:
                account_uuid = uuid.UUID(str(aid))
                # setdefault：只对本次 callback items 里完全没有出现的账号补一条
                # final 信号到达时通知这些账号关闭 processing，不写 error（之前的回调已正常处理）
                progress_by_account.setdefault(
                    account_uuid,
                    {
                        "scheduled": 0,
                        "duplicated": 0,
                        "rejected": 0,
                        "error": None,   # 不覆盖之前已经正常处理过账号的状态
                    },
                )

        req.callbacks_received = (req.callbacks_received or 0) + 1
        req.videos_accepted = (req.videos_accepted or 0) + scheduled
        req.videos_duplicated = (req.videos_duplicated or 0) + duplicated
        req.videos_rejected = (req.videos_rejected or 0) + rejected
        if final:
            req.completed_at = datetime.now(timezone.utc)
            # 不在这里强制 completed，由 refresh_request_rollup 根据 item 汇总决定

        # 其余标量字段通过 ORM 写入
        from app.services.supplement_status_service import mark_callback_seen
        for aid, counters in progress_by_account.items():
            await mark_callback_seen(
                session,
                request_id=request_id,
                account_id=aid,
                scheduled_count=int(counters.get("scheduled") or 0),
                duplicated_count=int(counters.get("duplicated") or 0),
                rejected_count=int(counters.get("rejected") or 0),
                final_received=final,
                error_message=counters.get("error"),
                _req=req,
            )
        await session.commit()

    logger.info(
        "[ext_supp][callback] processed: request_id=%s scheduled=%d duplicated=%d rejected=%d (cumulative: cb=%s accepted=%s dup=%s rej=%s)",
        request_id, scheduled, duplicated, rejected,
        req.callbacks_received, req.videos_accepted, req.videos_duplicated, req.videos_rejected,
    )

    # 按 source_domain 分发给对应业务域处理
    business_context = req.business_context or {}
    source_domain = business_context.get("source_domain", "ai_blogger")

    logger.info(
        "[ext_supp][callback] dispatch: request_id=%s source_domain=%s entries=%d",
        request_id, source_domain, len(to_process),
    )

    if source_domain == "candidate":
        # 候选库：整批交给 candidate_service 统一处理（内含共享/独享判断）
        from app.services.candidate_service import on_vendor_callback as _candidate_on_vendor_callback
        asyncio.create_task(
            _candidate_on_vendor_callback(
                to_process=to_process,
                mode=mode,
                owner_id=owner_id,
                request_id=request_id,
                business_context=business_context,
            )
        )
    else:
        # AI博主补充（默认）：每条 video 单独跑 AI 审核 + 分类过滤 + 写库 + enqueue
        for entry in to_process:
            asyncio.create_task(
                _post_callback_pipeline(
                    account_id=entry["account_id"],
                    video=entry["video"],
                    owner_id=owner_id,
                    mode=mode,
                    request_id=request_id,
                )
            )

    return {
        "request_id": str(request_id),
        "accepted": scheduled,    # 实际通过审核 / 分类后才入库；这里返回的是已调度数
        "duplicated": duplicated,
        "rejected": rejected,
        "message": "ok",
        "http_status": 200,
    }


async def _append_rejected_video(
    request_id: uuid.UUID,
    entry: dict,
) -> None:
    """把一条未通过的视频追加到对应 request 的 rejected_videos 列表。

    用 SELECT ... FOR UPDATE 串行化并发回调对 JSON 列的修改。
    """
    async with SessionLocal() as session:
        async with session.begin():
            req = (await session.execute(
                select(ExternalSupplementRequest)
                .where(ExternalSupplementRequest.request_id == request_id)
                .with_for_update()
            )).scalar_one_or_none()
            if req is None:
                logger.warning("[ext_supp] append_rejected: request %s 不存在", request_id)
                return
            current = list(req.rejected_videos or [])
            current.append(entry)
            req.rejected_videos = current
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(req, "rejected_videos")
            req.videos_rejected = (req.videos_rejected or 0) + 1
            # handle_supplement_callback 在调度时已把这条计入 videos_accepted（=已调度），
            # 现在终因 AI 审核 / 分类未过被丢弃，回退该计数以保持总和一致
            if (req.videos_accepted or 0) > 0:
                req.videos_accepted = req.videos_accepted - 1


async def _mark_callback_video_failed(
    *,
    request_id: uuid.UUID,
    account_id: uuid.UUID,
    reason: str,
    rejected: bool = False,
) -> None:
    from app.services.supplement_status_service import mark_video_failed

    async with SessionLocal() as session:
        await mark_video_failed(
            session,
            request_id=request_id,
            account_id=account_id,
            reason=reason,
            rejected=rejected,
        )
        await session.commit()


def _rejected_entry(video: dict, account_id: uuid.UUID, **extras) -> dict:
    """组装 rejected_videos 列表里的一条记录。"""
    return {
        "account_id": str(account_id),
        "source_url": str(video.get("source_url") or ""),
        "local_video_url": str(video.get("local_video_url") or ""),
        "blogger_name": video.get("blogger_name"),
        "video_title": video.get("video_title"),
        "thumbnail_url": video.get("thumbnail_url"),
        "rejected_at": datetime.now(timezone.utc).isoformat(),
        **extras,
    }


def _normalize_category_keys(raw: Any) -> list[str]:
    from app.services.video_classification_service import _VALID_KEYS_SET
    if not isinstance(raw, list):
        return []
    values: list[str] = []
    for item in raw:
        key = str(item).strip() if item else ""
        if key in _VALID_KEYS_SET and key not in values:
            values.append(key)
    return values


async def _post_callback_pipeline(
    *,
    account_id: uuid.UUID,
    video: dict,
    owner_id: uuid.UUID | None,
    mode: str,
    request_id: uuid.UUID,
) -> None:
    """单条视频的后处理：

      1. 把 gs:// 下载到本地 tmp
      2. 上传到我们的存储（GCS 或 CDN，由 video_upload_backend 决定）→ 拿 permanent URL
      3. AI 审核（如 pipeline_settings.candidate_ai_review_enabled）— 不通过则丢弃
      4. mode=auto：调 Gemini 分类，对账号 single/dual 大类不匹配则丢弃
      5. 通过的：写 video_sources + video_ai_template(pending) + 绑定 tag
      6. 触发 AI pipeline（enqueue_template）
    """
    from app.models.account import Account
    from app.models.account_blogger_binding import AccountBloggerBinding
    from app.models.account_tag import AccountTag
    from app.models.enums import VideoAIProcessStatus
    from app.models.tag import Tag, VideoSourceTag
    from app.models.tiktok_blogger import TiktokBlogger
    from app.models.video_ai_template import VideoAITemplate
    from app.models.video_source import VideoSource
    from app.services.candidate_service import (
        _ai_review_single,
        _classify_video_for_auto_supplement,
        _SearchConfig,
    )
    from app.services.pipeline_settings_service import get_or_create_pipeline_settings
    from app.services.video_source_service import _compress_video_if_needed
    from app.utils.gcs_download import download_gs_to_local
    from app.utils.tmp_storage import disk_tempdir, ensure_free_space
    from app.utils.video_upload import upload_video_file

    source_url = str(video.get("source_url") or "")
    source_uri = str(video.get("local_video_url") or "")
    if not source_url or not source_uri:
        logger.warning("[ext_supp] 缺少 source_url 或 local_video_url，跳过")
        await _mark_callback_video_failed(
            request_id=request_id,
            account_id=account_id,
            reason="缺少 source_url 或 local_video_url",
        )
        return

    # 反查账号信息（绑定博主 + 第一个 tag + 分类配置）
    async with SessionLocal() as session:
        req = await fetch_request_by_id(session, request_id)
        request_filters = req.filters if req is not None and isinstance(req.filters, dict) else {}
        account = await session.get(Account, account_id)
        if account is None:
            logger.warning("[ext_supp] account_id %s 不存在，跳过", account_id)
            await _mark_callback_video_failed(
                request_id=request_id,
                account_id=account_id,
                reason="账号不存在",
            )
            return
        tiktok_blogger_id = await session.scalar(
            select(AccountBloggerBinding.tiktok_blogger_id)
            .where(AccountBloggerBinding.account_id == account_id)
            .order_by(AccountBloggerBinding.created_at.asc())
            .limit(1)
        )
        first_tag_id = await session.scalar(
            select(AccountTag.tag_id)
            .where(AccountTag.account_id == account_id)
            .order_by(AccountTag.created_at.asc())
            .limit(1)
        )
        # 用绑定博主 handle 作为 AI 审核 prompt 的 {keyword}
        blogger_handle: str | None = None
        if tiktok_blogger_id is not None:
            blogger_handle = await session.scalar(
                select(TiktokBlogger.blogger_handle)
                .where(TiktokBlogger.id == tiktok_blogger_id)
            )
        # pipeline 配置（AI 审核 / 分类）
        cfg_owner = owner_id if owner_id is not None else uuid.UUID(int=0)
        try:
            pipeline_cfg = await get_or_create_pipeline_settings(session, owner_id=cfg_owner)
        except Exception:
            pipeline_cfg = None

    search_cfg = _SearchConfig(pipeline_cfg) if pipeline_cfg else None
    ai_review_enabled = bool(search_cfg.ai_review_enabled) if search_cfg else False
    ai_review_model = search_cfg.ai_review_model if search_cfg else ""
    ai_review_prompt = search_cfg.ai_review_prompt if search_cfg else ""
    retry_delay = search_cfg.retry_delay if search_cfg else 30.0

    # auto 模式：解出允许的小类 key（single → primary_key；dual → primary + secondary）
    allowed_keys: list[str] = []
    if mode == "auto":
        cls_type = account.classification_type
        summary = account.classification_summary or {}
        primary_key = summary.get("primary_key")
        secondary_key = summary.get("secondary_key")
        if cls_type not in ("single", "dual"):
            logger.info(
                "[ext_supp] auto 模式但账号 %s 分类=%s，跳过",
                account_id, cls_type,
            )
            await _mark_callback_video_failed(
                request_id=request_id,
                account_id=account_id,
                reason=f"账号分类类型为 {cls_type or '未分类'}，自动补充仅支持单核心/双核心账号",
                rejected=True,
            )
            return
        if isinstance(primary_key, str) and primary_key:
            allowed_keys.append(primary_key)
        if cls_type == "dual" and isinstance(secondary_key, str) and secondary_key:
            allowed_keys.append(secondary_key)
        if not allowed_keys:
            logger.info("[ext_supp] auto 模式但 account %s 无法确定允许小类，跳过", account_id)
            await _mark_callback_video_failed(
                request_id=request_id,
                account_id=account_id,
                reason="无法确定允许的视频小类",
                rejected=True,
            )
            return
    exclusive_filter_keys = (
        _normalize_category_keys(request_filters.get("category_keys"))
        if mode == "exclusive"
        else []
    )

    try:
        ensure_free_space(min_bytes=500 * 1024 * 1024, label="external_supplement")
    except Exception as exc:
        logger.warning("[ext_supp] 磁盘空间预检失败: %s", exc)

    # 1. 下载 + 上传我们的 storage
    title_for_filename = (
        video.get("video_title") or video.get("blogger_name") or "video"
    )[:60].replace("/", "_").replace("\\", "_")
    filename = f"{title_for_filename}.mp4"

    try:
        with disk_tempdir(prefix="ext_supp_") as tmpdir:
            local_path = os.path.join(tmpdir, "video")
            if source_uri.startswith("gs://"):
                actual_path = await download_gs_to_local(source_uri, local_path)
            else:
                # 退化：vendor 返了 https URL
                actual_path = local_path + ".mp4"
                async with httpx.AsyncClient(timeout=600.0, follow_redirects=True) as client:
                    async with client.stream("GET", source_uri) as resp:
                        resp.raise_for_status()
                        with open(actual_path, "wb") as f:
                            async for chunk in resp.aiter_bytes(chunk_size=1024 * 256):
                                f.write(chunk)

            actual_path = await _compress_video_if_needed(actual_path, tmpdir)
            permanent_url = await upload_video_file(actual_path, filename)
            from app.utils.video_upload import current_upload_backend
            upload_backend = current_upload_backend()
    except Exception as exc:
        logger.exception("[ext_supp] 下载/上传失败 source_url=%s: %s", source_url, exc)
        await _mark_callback_video_failed(
            request_id=request_id,
            account_id=account_id,
            reason=f"下载/上传失败: {exc}",
        )
        return

    logger.info("[ext_supp] uploaded (%s) → %s (source_url=%s)", upload_backend, permanent_url, source_url)

    # 2. AI 审核（如启用）
    if ai_review_enabled:
        keyword = blogger_handle or video.get("blogger_name") or ""
        prompt = (ai_review_prompt or "").replace("{keyword}", str(keyword))
        try:
            passed, reason = await _ai_review_single(
                video_url=permanent_url,
                prompt=prompt,
                model=ai_review_model,
                retry_delay=retry_delay,
            )
        except Exception as exc:
            logger.warning("[ext_supp] AI 审核异常，按未通过处理 source_url=%s: %s", source_url, exc)
            passed, reason = False, str(exc)
        if not passed:
            logger.info(
                "[ext_supp] AI 审核未通过，丢弃 source_url=%s reason=%s",
                source_url, reason,
            )
            await _append_rejected_video(request_id, _rejected_entry(
                video, account_id,
                reason_type="ai_review",
                reason=reason,
            ))
            await _mark_callback_video_failed(
                request_id=request_id,
                account_id=account_id,
                reason=str(reason or "AI 审核未通过"),
                rejected=True,
            )
            return
        logger.info("[ext_supp] AI 审核通过 source_url=%s", source_url)

    # 3. 分类过滤：auto 使用账号 single/dual 小类；exclusive 可使用手选小类。
    classify_allowed_keys = allowed_keys if mode == "auto" else exclusive_filter_keys
    if classify_allowed_keys:
        try:
            category_key = await _classify_video_for_auto_supplement(permanent_url, owner_id)
        except Exception as exc:
            logger.warning("[ext_supp] 分类异常 source_url=%s: %s", source_url, exc)
            category_key = None
        if category_key is None:
            logger.info("[ext_supp] 分类失败，丢弃 source_url=%s mode=%s", source_url, mode)
            await _append_rejected_video(request_id, _rejected_entry(
                video, account_id,
                reason_type="classify_failed",
                reason="Gemini 分类未返回结果",
                allowed_keys=classify_allowed_keys,
            ))
            await _mark_callback_video_failed(
                request_id=request_id,
                account_id=account_id,
                reason="Gemini 分类未返回结果",
                rejected=True,
            )
            return
        # classify_allowed_keys 是大类 key（"beauty"/"method"/...），
        # category_key 是细分类 key（"beauty_showcase"/...），需先转成大类再比对
        from app.services.video_classification_service import CATEGORY_MAJOR
        category_major = CATEGORY_MAJOR.get(category_key, category_key)
        if category_major not in classify_allowed_keys:
            logger.info(
                "[ext_supp] 分类 key=%s major=%s ∉ 允许 %s，丢弃 source_url=%s mode=%s",
                category_key, category_major, classify_allowed_keys, source_url, mode,
            )
            await _append_rejected_video(request_id, _rejected_entry(
                video, account_id,
                reason_type="classify_unmatched",
                reason=f"分类 key={category_key}(major={category_major}) 不在允许大类 {classify_allowed_keys}",
                category_key=category_key,
                allowed_keys=classify_allowed_keys,
            ))
            await _mark_callback_video_failed(
                request_id=request_id,
                account_id=account_id,
                reason=f"分类 key={category_key}(major={category_major}) 不在允许大类 {classify_allowed_keys}",
                rejected=True,
            )
            return
        logger.info("[ext_supp] 分类匹配 key=%s major=%s source_url=%s mode=%s", category_key, category_major, source_url, mode)

    # 4. 写库（写 video_sources + template + 绑 tag）
    try:
        async with SessionLocal() as session:
            # 写入前再做一次 dedup（并发回调可能在同时间内被 schedule）
            existing = await session.scalar(
                select(VideoSource.id).where(VideoSource.source_url == source_url)
            )
            if existing is not None:
                logger.info("[ext_supp] 写入前再校验：已有 source_url=%s，跳过", source_url)
                from app.services.supplement_status_service import mark_video_failed
                await mark_video_failed(
                    session,
                    request_id=request_id,
                    account_id=account_id,
                    reason="视频已存在",
                )
                await session.commit()
                return

            vs = VideoSource(
                owner_id=owner_id,
                platform="tiktok",
                source_url=source_url,
                blogger_name=video.get("blogger_name"),
                video_title=video.get("video_title"),
                video_desc=video.get("video_desc"),
                thumbnail_url=video.get("thumbnail_url"),
                view_count=video.get("view_count"),
                like_count=video.get("like_count"),
                favorite_count=video.get("favorite_count"),
                comment_count=video.get("comment_count"),
                share_count=video.get("share_count"),
                publish_date=video.get("publish_date"),
                duration=video.get("duration"),
                width=video.get("width"),
                height=video.get("height"),
                aspect_ratio=video.get("aspect_ratio"),
                extra=video.get("extra"),
                local_video_url=permanent_url if upload_backend != "gcs" else None,
                local_gcs_video_url=permanent_url if upload_backend == "gcs" else None,
                download_status="done",
                tiktok_blogger_id=tiktok_blogger_id,
            )
            session.add(vs)
            await session.flush()

            tpl = VideoAITemplate(
                owner_id=owner_id,
                title=(vs.video_title or vs.blogger_name or "新模板")[:200],
                description="",
                video_source_id=vs.id,
                process_status=VideoAIProcessStatus.pending,
            )
            if tiktok_blogger_id is not None:
                tpl.tiktok_blogger_id = tiktok_blogger_id
            session.add(tpl)
            await session.flush()

            if first_tag_id is not None:
                session.add(VideoSourceTag(
                    video_source_id=vs.id,
                    tag_id=first_tag_id,
                    video_ai_template_id=tpl.id,
                ))
            from app.services.account_template_tag_service import ensure_account_template_tags
            await ensure_account_template_tags(session, account_id, owner_id=owner_id)
            await session.commit()
            vs_id = vs.id
            tpl_id = tpl.id

        # 5. enqueue
        from app.services.video_ai_service import enqueue_template
        await enqueue_template(str(tpl_id))
        async with SessionLocal() as session:
            from app.services.supplement_status_service import mark_video_completed
            await mark_video_completed(
                session,
                request_id=request_id,
                account_id=account_id,
            )
            await session.commit()
        logger.info("[ext_supp] enqueued template tpl_id=%s vs_id=%s", tpl_id, vs_id)

    except Exception as exc:
        logger.exception("[ext_supp] 写库/触发 pipeline 失败 source_url=%s: %s", source_url, exc)
        await _mark_callback_video_failed(
            request_id=request_id,
            account_id=account_id,
            reason=f"写库/触发 pipeline 失败: {exc}",
        )
