import asyncio
import json
import logging
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, date, timezone
from typing import Any

import httpx
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer, selectinload

from app.core.config import settings
from app.models.account import Account
from app.models.account_channel_reservation import AccountChannelReservation
from app.models.video_ai_template import VideoAITemplate
from app.models.video_classification import VideoClassification
from app.models.video_publication import VideoPublication
from app.models.video_task import VideoSubTask, VideoTask
from app.schemas.video_publication import (
    VideoPublicationCreate,
    VideoPublicationStatsListItem,
    VideoPublicationStatsQuery,
)
from app.services.ext_product_service import build_ext_products_from_shots
from app.services.open_api_signing import (
    generate_signature as _shared_generate_signature,
    sign_params as _shared_sign_params,
    value_to_sign_str as _shared_value_to_sign_str,
)
from app.services.promotion_code_service import promotion_code_distributor

logger = logging.getLogger("app.video_publication_service")


def _classification_label(classification: VideoClassification | None) -> str | None:
    if classification is None or not classification.category_key:
        return None
    from app.services.video_classification_service import CATEGORY_LABELS

    return CATEGORY_LABELS.get(classification.category_key)


# ── 后台轮询器 ──────────────────────────────────────────────────────────────────
_POLL_INTERVAL_SECONDS = 600.0
_poller_task: asyncio.Task | None = None
_poller_stop_event: asyncio.Event | None = None

# 同步视频指标限流参数
_SYNC_METRICS_RATE_LIMIT_SEC = 1   # 每条请求间隔（秒）
_SYNC_METRICS_RETRY_DELAY_SEC = 10  # 失败后重试等待（秒）
_SYNC_METRICS_RETRIES = 3           # 最大重试次数


def _mask_sensitive_for_log(value: Any) -> Any:
    if isinstance(value, dict):
        masked: dict = {}
        for key, item in value.items():
            key_text = str(key).lower()
            if key_text in {"signature", "client_secret", "api_key", "x-api-key"}:
                masked[key] = "***"
            else:
                masked[key] = _mask_sensitive_for_log(item)
        return masked
    if isinstance(value, list):
        return [_mask_sensitive_for_log(item) for item in value]
    return value


def _payload_for_log(payload: dict) -> str:
    try:
        return json.dumps(_mask_sensitive_for_log(payload), ensure_ascii=False, default=str)
    except Exception:
        return str(_mask_sensitive_for_log(payload))


def start_video_publication_poller() -> None:
    global _poller_task, _poller_stop_event
    if _poller_task is not None and not _poller_task.done():
        return
    _poller_stop_event = asyncio.Event()
    _poller_task = asyncio.get_running_loop().create_task(
        _poller_loop(_poller_stop_event)
    )
    logger.info("Video publication poller started")


async def stop_video_publication_poller() -> None:
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
    logger.info("Video publication poller stopped")


async def _poller_loop(stop_event: asyncio.Event) -> None:
    try:
        while not stop_event.is_set():
            try:
                await _poll_once()
            except Exception:
                logger.exception("Publication poll run failed")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=_POLL_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                pass
    except asyncio.CancelledError:
        pass


async def _poll_once() -> None:
    """查询所有进行中的 publication，逐一调用 Open API 同步状态。"""
    from app.db.session import SessionLocal

    async with SessionLocal() as db:
        result = await db.execute(
            select(VideoPublication).where(
                VideoPublication.status.in_(["pending", "processing", "uploading", "partial"])
            )
        )
        pub_ids: list[uuid.UUID] = [p.id for p in result.scalars().all()]

    if not pub_ids:
        return

    logger.debug("Polling %d in-progress publications", len(pub_ids))

    from app.db.session import SessionLocal

    for pub_id in pub_ids:
        try:
            async with SessionLocal() as db:
                service = VideoPublicationService(db)
                await service.sync_publication_status(pub_id)
        except ValueError as e:
            logger.error("Skipping publication %s: %s", pub_id, e)
        except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError) as e:
            logger.error("【发布同步】publication %s 连接超时", pub_id)
        except Exception:
            logger.exception("Failed to sync publication %s", pub_id)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _build_open_api_request_payload(
    data: "VideoPublicationCreate",
    channels: list[dict],
    promotion_code: str | None,
    ext_products: list[dict],
    account_tier: str | None,
    kol_user_id: str | None,
    callback_url: str | None,
) -> dict:
    """构造发到 Open API 的完整请求体。

    返回结构与实际 HTTP body 一致（嵌套 ``ext_info``、含 ``callback_url`` /
    ``video_tags.env``）。``channels`` 字段保留调用方传入的完整 dict（含
    ``channel_source`` 等本地路由元数据），实际 HTTP 发送时由 adapter 裁成
    ``[{"platform", "channel_id"}]``。签名相关字段（``client_id`` / ``timestamp`` /
    ``signature``）由 ``OpenAPIClient`` 发送时再追加。

    这份 payload 既用于实际发送，也用于持久化到 ``video_publications.request_payload``
    作为审计 / retry 依据。
    """
    env = (account_tier or "test").lower()
    if env not in {"test", "dev", "prod"}:
        env = "test"
    ext_info: dict = {
        "promotion_code": promotion_code,
        "ext_products": ext_products,
        "video_tags": {"env": [env]},
    }
    if kol_user_id:
        ext_info["kol_user_id"] = kol_user_id
    payload: dict = {
        "video_url": data.video_url,
        "original_video_url": data.original_video_url or data.video_url,
        "video_type": data.video_type or "traffic",
        "title": data.title,
        "description": data.description,
        "tags": data.tags or [],
        "ext_info": ext_info,
        "channels": channels,
        "external_id": str(data.sub_task_id),
    }
    if callback_url:
        payload["callback_url"] = callback_url
    return payload


def _payload_ext_field(payload: dict, key: str):
    """从 request_payload 里取 ``promotion_code`` / ``ext_products`` / ``kol_user_id``。

    新格式（本次重构后）：嵌套在 ``ext_info`` 下；
    老格式（DB 中历史行）：平铺在顶层。
    """
    ext_info = payload.get("ext_info") if isinstance(payload.get("ext_info"), dict) else None
    if ext_info is not None and key in ext_info:
        return ext_info[key]
    return payload.get(key)


class OpenAPIClient:
    """Open API 客户端"""

    def __init__(
        self,
        base_url: str | None = None,
        client_id: str | None = None,
        client_secret: str | None = None,
        publish_base_url: str | None = None,
    ):
        self.base_url = base_url or getattr(settings, "open_api_base_url", "http://192.168.199.28:8080")
        # 发布视频 + 轮询发布状态走独立 base_url；未配置时回退到主 base_url
        _publish = publish_base_url or getattr(settings, "publish_api_base_url", "")
        self.publish_base_url = (_publish.rstrip("/") if _publish else self.base_url)
        self.client_id = client_id or getattr(settings, "open_api_client_id", "default_client")
        self.client_secret = client_secret or getattr(
            settings, "open_api_client_secret", ""
        )
        self.timeout = 30.0

    @staticmethod
    def _value_to_sign_str(v) -> str:
        return _shared_value_to_sign_str(v)

    def _generate_signature(self, params: dict, timestamp: int) -> str:
        return _shared_generate_signature(params, self.client_secret, timestamp)

    def _sign_params(self, params: dict) -> dict:
        return _shared_sign_params(params, self.client_id, self.client_secret)

    async def fetch_channels(
        self, platform: str, page: int = 1, page_size: int = 20, is_active: bool | None = None,
        usage_types: list[str] | None = None,
    ) -> dict:
        """获取渠道列表"""
        params = {"platform": platform, "page": page, "page_size": page_size}
        if is_active is not None:
            params["is_active"] = is_active
        if usage_types:
            params["usage_type"] = ",".join(usage_types)

        signed_params = self._sign_params(params)
        logged_params = dict(signed_params)
        if "signature" in logged_params:
            sig = str(logged_params["signature"])
            logged_params["signature"] = f"{sig[:8]}...{sig[-6:]}" if len(sig) > 14 else "***"
        logger.info(
            "Open API fetch_channels outbound request: base_url=%s params=%s",
            self.base_url,
            logged_params,
        )

        # trust_env=False 禁用系统代理；渠道列表是 UI 辅助接口，超时缩短到 5s
        async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
            response = await client.get(
                f"{self.base_url}/open-api/v1/channels",
                params=signed_params,
            )
            response.raise_for_status()
            result = response.json()
            data = result.get("data", {}) if isinstance(result, dict) else {}
            logger.info(
                "Open API fetch_channels outbound response: status=%s code=%s total=%s items=%s message=%s",
                response.status_code,
                result.get("code") if isinstance(result, dict) else None,
                data.get("total"),
                len(data.get("items") or []),
                result.get("message") if isinstance(result, dict) else None,
            )
            return result

    async def create_upload_task(self, payload: dict) -> dict:
        """创建视频上传任务"""
        signed_payload = self._sign_params(payload)

        # trust_env=False 禁用系统代理
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            response = await client.post(
                f"{self.publish_base_url}/open-api/v1/upload/task",
                json=signed_payload,
            )
            response.raise_for_status()
            return response.json()

    async def fetch_upload_status(self, task_id: str | None = None, external_id: str | None = None) -> dict:
        """查询上传任务状态。

        优先访问 publish_base_url；若与 base_url 不同且请求失败（网络异常 / 非 2xx），
        自动回退到 base_url 再试一次。
        """
        params = {}
        if task_id:
            params["task_id"] = task_id
        if external_id:
            params["external_id"] = external_id

        signed_params = self._sign_params(params)
        candidates = [self.publish_base_url]
        if self.base_url and self.base_url != self.publish_base_url:
            candidates.append(self.base_url)

        last_exc: Exception | None = None
        for idx, base in enumerate(candidates):
            try:
                # trust_env=False 禁用系统代理
                async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
                    response = await client.get(
                        f"{base}/open-api/v1/upload/status",
                        params=signed_params,
                    )
                    response.raise_for_status()
                    return response.json()
            except Exception as exc:
                last_exc = exc
                if idx < len(candidates) - 1:
                    logger.warning(
                        "fetch_upload_status via %s failed (%s)，回退到 %s 重试",
                        base,
                        exc,
                        candidates[idx + 1],
                    )
                    continue
                raise
        # 理论上不会走到这里
        assert last_exc is not None
        raise last_exc

    async def fetch_upload_metrics(self, task_id: str | None = None, external_id: str | None = None) -> dict:
        """查询上传任务各渠道视频指标（base_url 使用 publish_api_base_url"""
        params = {}
        if task_id:
            params["task_id"] = task_id
        if external_id:
            params["external_id"] = external_id

        signed_params = self._sign_params(params)

        metrics_base = getattr(settings, "publish_api_base_url", "").rstrip("/") or self.base_url
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            response = await client.get(
                f"{metrics_base}/open-api/v1/upload/metrics",
                params=signed_params,
            )
            response.raise_for_status()
            return response.json()

    async def health_check(self) -> dict:
        """健康检查"""
        # trust_env=False 禁用系统代理
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            response = await client.get(f"{self.base_url}/open-api/v1/health")
            response.raise_for_status()
            return response.json()


class ExtPubAPIClient:
    """外部发布 API 客户端（独立维护的第三方频道发布服务）"""

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
    ):
        self.base_url = (base_url or getattr(settings, "ext_pub_api_base_url", "http://34.21.25.209:8000")).rstrip("/")
        self.api_key = api_key or getattr(settings, "ext_pub_api_key", "")
        self.timeout = 30.0

    def _headers(self) -> dict:
        return {"X-API-Key": self.api_key, "Content-Type": "application/json"}

    async def fetch_platform_accounts(self, platform: str | None = None, page: int = 1, page_size: int = 100) -> dict:
        """获取平台账号列表（即外部频道列表），可按 platform 过滤"""
        params: dict = {"page": page, "page_size": page_size}
        if platform:
            params["platform"] = platform
        async with httpx.AsyncClient(timeout=10.0, trust_env=False) as client:
            logger.info(
                "ExtPubAPI platform-accounts request: url=%s params=%s",
                f"{self.base_url}/api/platform-accounts",
                params,
            )
            response = await client.get(
                f"{self.base_url}/api/platform-accounts",
                params=params,
                headers=self._headers(),
            )
            response.raise_for_status()
            result = response.json()
            data = result.get("data") if isinstance(result, dict) else {}
            items = data.get("items") if isinstance(data, dict) else []
            platform_counts: dict[str, int] = {}
            if isinstance(items, list):
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    item_platform = str(item.get("platform_type") or "")
                    platform_counts[item_platform] = platform_counts.get(item_platform, 0) + 1
            logger.info(
                "ExtPubAPI platform-accounts response: requested_platform=%s status_code=%s total=%s returned_items=%s platform_counts=%s",
                platform,
                response.status_code,
                data.get("total") if isinstance(data, dict) else None,
                len(items) if isinstance(items, list) else None,
                platform_counts,
            )
            return result

    async def create_post(self, payload: dict) -> dict:
        """创建发布任务"""
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            response = await client.post(
                f"{self.base_url}/api/posts",
                json=payload,
                headers=self._headers(),
            )
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError:
                logger.warning(
                    "ExtPubAPI create_post failed: status=%s body=%s payload=%s",
                    response.status_code,
                    response.text[:1000],
                    _payload_for_log(payload),
                )
                raise
            return response.json()

    async def fetch_post_detail(self, business_id: str) -> dict:
        """查询发布任务详情（用于轮询状态）"""
        async with httpx.AsyncClient(timeout=self.timeout, trust_env=False) as client:
            response = await client.get(
                f"{self.base_url}/api/posts/detail",
                params={"business_id": business_id},
                headers=self._headers(),
            )
            response.raise_for_status()
            return response.json()


# ── 发布适配器 ──────────────────────────────────────────────────────────────────

# ── 频道级状态工具 ──────────────────────────────────────────────────────────────

# 每条 channel_status 的 _source 字段值
_SOURCE_OPENAPI = "openapi"
_SOURCE_EXT_PUB = "ext_pub"

# 下游限流：100 req/min。进程级 lock + 最小间隔 0.6s 保证：
#   1. 同一时刻只有一个 publish HTTP 请求在飞
#   2. 即使每个请求秒级返回，QPS 上限也是 ~1.67/s = 100/min
# 注意：asyncio.Lock 只在单进程内生效；多 worker 部署需要 Redis / DB 锁。
_PUBLISH_HTTP_LOCK = asyncio.Lock()
_PUBLISH_MIN_INTERVAL_SEC = 0.6
_last_publish_call_at: float = 0.0


class _PublishSlot:
    """``async with _PublishSlot():`` 拿到一个发布 HTTP 槽位：

    入口阻塞直到拿到全局锁，再保证距离上次发布间隔 ≥ _PUBLISH_MIN_INTERVAL_SEC。
    退出时记录"本次开始时间"作为下次的基准。
    """

    async def __aenter__(self) -> "_PublishSlot":
        global _last_publish_call_at
        import time as _time
        await _PUBLISH_HTTP_LOCK.acquire()
        elapsed = _time.monotonic() - _last_publish_call_at
        if elapsed < _PUBLISH_MIN_INTERVAL_SEC:
            wait = _PUBLISH_MIN_INTERVAL_SEC - elapsed
            logger.debug("[publish-slot] pacing: sleep %.2fs", wait)
            await asyncio.sleep(wait)
        _last_publish_call_at = _time.monotonic()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        _PUBLISH_HTTP_LOCK.release()

# 终态集合
_TERMINAL_STATUSES = {"completed", "published", "failed"}
_SUCCESS_STATUSES = {"completed", "published"}
_FAILED_STATUSES = {"failed"}


def _compute_publication_status(channels_status: list[dict]) -> str:
    """根据全部平台频道级状态列表计算汇总发布状态。

    规则：
    - 全部为终态且全成功 → completed
    - 全部为终态且全失败 → failed
    - 全部为终态有成有败 → partial
    - 有任何非终态 → processing
    - 空列表 → pending
    """
    if not channels_status:
        return "pending"

    statuses = [c.get("status", "") for c in channels_status]
    all_terminal = all(s in _TERMINAL_STATUSES for s in statuses)

    if not all_terminal:
        return "processing"

    success = sum(1 for s in statuses if s in _SUCCESS_STATUSES)
    failed = sum(1 for s in statuses if s in _FAILED_STATUSES)

    if success > 0 and failed == 0:
        return "completed"
    if failed > 0 and success == 0:
        return "failed"
    return "partial"


def _finalize_ext_pub_channel_statuses(channels_status: list[dict]) -> tuple[list[dict], bool]:
    """将 ext_pub 侧频道视为提交即完成，不再依赖后续轮询。"""
    finalized: list[dict] = []
    changed = False
    completed_at = utcnow().isoformat()

    for channel in channels_status:
        if channel.get("_source") != _SOURCE_EXT_PUB:
            finalized.append(channel)
            continue

        if channel.get("status") in _FAILED_STATUSES:
            finalized.append(channel)
            continue

        updated = dict(channel)
        if updated.get("status") != "completed":
            updated["status"] = "completed"
            changed = True
        if not updated.get("uploaded_at"):
            updated["uploaded_at"] = completed_at
            changed = True
        if updated.get("error_message") is not None:
            updated["error_message"] = None
            changed = True
        finalized.append(updated)

    return finalized, changed


# YouTube 返回账号被封禁时的错误标识。命中后把对应 reservation 标为 disabled，
# 后续 reserve / bind / 发布流程都会跳过该频道。
_SUSPENDED_ERROR_TOKENS = (
    "authenticatedUserAccountSuspended",
    "accountSuspended",
)


def _channel_indicates_account_suspended(channel: dict) -> bool:
    if (channel.get("status") or "") not in _FAILED_STATUSES:
        return False
    msg = str(channel.get("error_message") or "")
    return any(tok in msg for tok in _SUSPENDED_ERROR_TOKENS)


async def _disable_suspended_channel_reservations(
    db: AsyncSession,
    sub_task_id: uuid.UUID,
    channels_status: list[dict],
) -> int:
    """扫描 channels_status，把命中"账号被封禁"错误的 channel 对应的
    AccountChannelReservation 标记为 disabled。返回被禁用的 reservation 数。
    任何子步骤失败都吞掉、不影响外层主流程；仅记日志。
    """
    targets = [
        (c.get("platform"), c.get("channel_id"))
        for c in (channels_status or [])
        if _channel_indicates_account_suspended(c)
    ]
    if not targets:
        return 0
    try:
        row = (await db.execute(
            select(VideoTask.account_id)
            .join(VideoSubTask, VideoSubTask.task_id == VideoTask.id)
            .where(VideoSubTask.id == sub_task_id)
        )).first()
    except Exception:
        logger.exception("disable_suspended_reservations: 查找 account_id 失败 sub_task=%s", sub_task_id)
        return 0
    if row is None or row[0] is None:
        return 0
    account_id = row[0]
    disabled = 0
    for platform, channel_id in targets:
        if not platform or not channel_id:
            continue
        try:
            reservation = await db.scalar(
                select(AccountChannelReservation)
                .where(AccountChannelReservation.account_id == account_id)
                .where(AccountChannelReservation.platform == platform)
                .where(AccountChannelReservation.channel_id == channel_id)
                .where(AccountChannelReservation.channel_status != "disabled")
            )
        except Exception:
            logger.exception(
                "disable_suspended_reservations: 查询 reservation 失败 account=%s platform=%s channel=%s",
                account_id, platform, channel_id,
            )
            continue
        if reservation is None:
            continue
        reservation.channel_status = "disabled"
        disabled += 1
        logger.warning(
            "Channel reservation marked disabled (account suspended): "
            "account_id=%s platform=%s channel_id=%s reservation_id=%s",
            account_id, platform, channel_id, reservation.id,
        )
    return disabled


async def _apply_publication_status_to_sub_task(
    db: AsyncSession,
    *,
    sub_task_id: uuid.UUID,
    publication_status: str,
) -> None:
    from app.models.video_task import VideoSubTask, VideoTask
    from app.services.video_task_service import _compute_parent_status

    target_status: str | None = None
    if publication_status in ("completed", "partial"):
        target_status = "published"
    elif publication_status == "failed":
        target_status = "publish_failed"
    elif publication_status in ("pending", "processing", "uploading"):
        target_status = "publishing"

    if target_status is None:
        return

    result = await db.execute(
        select(VideoSubTask)
        .where(VideoSubTask.id == sub_task_id)
        .options(selectinload(VideoSubTask.task).selectinload(VideoTask.sub_tasks))
    )
    sub_task = result.scalar_one_or_none()
    if sub_task is None:
        return

    if target_status == "publishing":
        if sub_task.status in ("queued", "pending_publish", "publish_failed"):
            sub_task.status = "publishing"
            sub_task.task.status = "publishing"
        return

    if sub_task.status in ("queued", "pending_publish", "publish_failed", "publishing"):
        sub_task.status = target_status
        sub_task.task.status = _compute_parent_status(sub_task.task.sub_tasks)


class PublishAdapter(ABC):
    """发布适配器抽象基类。

    适配器只负责与单侧外部 API 通信，不直接读写 VideoPublication：
    - submit()    → 调用外部 API 提交发布，返回该侧的初始频道状态列表
    - sync_status() → 轮询外部 API，返回该侧最新频道状态列表（覆盖对应 _source 条目）
    """

    @abstractmethod
    async def submit(
        self,
        data: "VideoPublicationCreate",
        channels: list[dict],
        promotion_code: str | None,
        ext_products: list[dict],
    ) -> tuple[str | None, list[dict]]:
        """提交发布，返回 (task_id_or_none, channel_status_list)。

        channel_status_list 每条格式：
        {
          "platform": str,
          "channel_id": str,
          "channel_name": str,
          "status": "pending"|"uploading"|"completed"|"failed",
          "platform_video_id": str|None,
          "platform_video_url": str|None,
          "error_message": str|None,
          "uploaded_at": str|None,
          "_source": "openapi"|"ext_pub",   # 内部标记，用于区分来源
        }
        """

    @abstractmethod
    async def sync_status(
        self,
        publication: "VideoPublication",
    ) -> list[dict]:
        """轮询外部 API，返回该侧最新频道状态列表（格式同 submit）。
        若无更新或不适用，返回空列表。
        """


class OpenAPIAdapter(PublishAdapter):
    """通过内部 Open API 发布的适配器。"""

    def __init__(self, client: OpenAPIClient):
        self.client = client

    async def submit(
        self,
        data: "VideoPublicationCreate",
        channels: list[dict],
        promotion_code: str | None,
        ext_products: list[dict],
        account_tier: str | None = None,
        kol_user_id: str | None = None,
    ) -> tuple[str | None, list[dict]]:
        callback_url = data.callback_url or settings.open_api_callback_url or None
        api_payload = _build_open_api_request_payload(
            data, channels, promotion_code, ext_products,
            account_tier=account_tier,
            kol_user_id=kol_user_id,
            callback_url=callback_url,
        )
        # 实际发送时把 channels 裁成 platform + channel_id（Open API 规范），
        # request_payload 里仍保留完整 dict 含 channel_source 供 retry/audit
        api_payload["channels"] = [{"platform": c["platform"], "channel_id": c["channel_id"]} for c in channels]

        logger.info(
            "OpenAPIAdapter.submit payload: sub_task_id=%s payload=%s",
            data.sub_task_id,
            _payload_for_log(api_payload),
        )
        # 进程级串行 + 节流，避免触发下游 100 req/min 限流
        async with _PublishSlot():
            response = await self.client.create_upload_task(api_payload)
        if response.get("code") != 0:
            raise ValueError(response.get("message", "Open API 返回错误"))

        response_data = response.get("data", {})
        task_id: str | None = response_data.get("task_id")

        # 将 Open API 返回的 channels 列表规范化，补 _source 标记
        raw_channels: list[dict] = response_data.get("channels") or []
        if raw_channels:
            channel_statuses = [
                {**ch, "_source": _SOURCE_OPENAPI} for ch in raw_channels
            ]
        else:
            # Open API 没返回 channels 时，用请求的 channels 构造 pending 条目
            channel_statuses = [
                {
                    "platform": c["platform"],
                    "channel_id": c["channel_id"],
                    "channel_name": c.get("channel_name", ""),
                    "status": "pending",
                    "platform_video_id": None,
                    "platform_video_url": None,
                    "error_message": None,
                    "uploaded_at": None,
                    "_source": _SOURCE_OPENAPI,
                }
                for c in channels
            ]

        logger.info(
            "OpenAPIAdapter.submit: task_id=%s channels=%s",
            task_id, channel_statuses,
        )
        return task_id, channel_statuses

    async def sync_status(self, publication: "VideoPublication") -> list[dict]:
        """调用 Open API 查询状态，返回 openapi 侧最新频道状态列表。"""
        payload = publication.request_payload or {}
        task_id = publication.open_api_task_id
        if not task_id:
            logger.debug("OpenAPIAdapter.sync_status: publication %s 无 open_api_task_id，跳过", publication.id)
            return []

        response = await self.client.fetch_upload_status(
            task_id=task_id,
            external_id=publication.external_id,
        )
        if response.get("code") != 0:
            raise ValueError(response.get("message", "Open API 返回错误"))

        response_data = response.get("data", {})
        raw_channels: list[dict] = response_data.get("channels") or []
        result = [{**ch, "_source": _SOURCE_OPENAPI} for ch in raw_channels]
        logger.info(
            "OpenAPIAdapter.sync_status: publication=%s task_id=%s channels=%s",
            publication.id, task_id, result,
        )
        return result


class ExtPubAdapter(PublishAdapter):
    """通过外部发布 API（POST /api/posts）发布的适配器。"""

    # 外部 API 的 publish.status → 内部 channel status 映射
    _CHANNEL_STATUS_MAP = {
        "pending":    "pending",
        "completed":  "completed",
        "published":  "completed",   # 历史兼容值
        "failed":     "failed",
    }

    def __init__(self, client: ExtPubAPIClient):
        self.client = client

    @staticmethod
    def _statuses_from_post_data(post_data: dict, fallback_channels: list[dict]) -> list[dict]:
        publishes = post_data.get("publishes") if isinstance(post_data, dict) else None
        if isinstance(publishes, list) and publishes:
            return [
                {
                    "platform": p.get("platform_type", ""),
                    "channel_id": p.get("platform_account_id") or p.get("id") or "",
                    "channel_name": p.get("nickname") or p.get("username") or "",
                    "status": ExtPubAdapter._CHANNEL_STATUS_MAP.get(p.get("status", ""), p.get("status", "pending")),
                    "platform_video_id": p.get("external_post_id"),
                    "platform_video_url": None,
                    "error_message": p.get("failed_reason"),
                    "uploaded_at": p.get("published_at"),
                    "_source": _SOURCE_EXT_PUB,
                }
                for p in publishes
            ]

        return [
            {
                "platform": c.get("platform", ""),
                "channel_id": c["channel_id"],
                "channel_name": c.get("channel_name", ""),
                "status": "pending",
                "platform_video_id": None,
                "platform_video_url": None,
                "error_message": None,
                "uploaded_at": None,
                "_source": _SOURCE_EXT_PUB,
            }
            for c in fallback_channels
        ]

    async def submit(
        self,
        data: "VideoPublicationCreate",
        channels: list[dict],
        promotion_code: str | None,
        ext_products: list[dict],
    ) -> tuple[str | None, list[dict]]:
        api_payload: dict = {
            "post_type": "video",
            "title": data.title,
            "content": data.description or "",
            "tags": data.tags or [],
            "promotion_code": promotion_code,
            "ext_products": ext_products,
            "video_url": data.video_url,
            "business_id": str(data.sub_task_id),
            "accounts": [{"id": c["channel_id"]} for c in channels],
        }
        logger.info(
            "ExtPubAdapter.submit: sub_task_id=%s payload=%s",
            data.sub_task_id, _payload_for_log(api_payload),
        )

        # 进程级串行 + 节流，避免触发下游 100 req/min 限流（含 400 fallback 的两次调用）
        async with _PublishSlot():
            try:
                response = await self.client.create_post(api_payload)
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code != 400:
                    raise
                logger.info(
                    "ExtPubAdapter.submit: create_post 400, probing existing business_id=%s",
                    api_payload["business_id"],
                )
                try:
                    response = await self.client.fetch_post_detail(api_payload["business_id"])
                    logger.info("ExtPubAdapter.submit: found existing post for business_id=%s", api_payload["business_id"])
                except Exception:
                    raise exc
        logger.info("ExtPubAdapter.submit response: %s", response)

        response_data = response if isinstance(response, dict) else {}
        # 外部 API 返回 {code, message, data: {id, ...}}
        post_data = response_data.get("data") or {}
        task_id: str | None = str(post_data.get("id")) if post_data.get("id") else None

        channel_statuses = self._statuses_from_post_data(post_data, channels)
        channel_statuses, _ = _finalize_ext_pub_channel_statuses(channel_statuses)

        logger.info(
            "ExtPubAdapter.submit: task_id=%s channels=%s",
            task_id, channel_statuses,
        )
        return task_id, channel_statuses

    async def sync_status(self, publication: "VideoPublication") -> list[dict]:
        """通过 GET /api/posts/detail?business_id= 轮询外部发布状态。"""
        business_id = publication.external_id
        if not business_id:
            logger.warning("ExtPubAdapter.sync_status: publication %s 缺少 external_id，跳过", publication.id)
            return []

        try:
            response = await self.client.fetch_post_detail(business_id)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                logger.warning("ExtPubAdapter.sync_status: business_id=%s 在外部 API 中不存在", business_id)
                return []
            raise

        detail = response.get("data") if isinstance(response, dict) else None
        if not detail:
            logger.warning("ExtPubAdapter.sync_status: 外部 API 返回空 data, business_id=%s", business_id)
            return []

        publishes: list[dict] = detail.get("publishes") or []
        result = [
            {
                "platform": p.get("platform_type", ""),
                "channel_id": p.get("platform_account_id", ""),
                "channel_name": p.get("nickname") or p.get("username") or "",
                "status": self._CHANNEL_STATUS_MAP.get(p.get("status", ""), p.get("status", "pending")),
                "platform_video_id": p.get("external_post_id"),
                "platform_video_url": None,
                "error_message": p.get("failed_reason"),
                "uploaded_at": p.get("published_at"),
                "_source": _SOURCE_EXT_PUB,
            }
            for p in publishes
        ]
        logger.info(
            "ExtPubAdapter.sync_status: publication=%s business_id=%s channels=%s",
            publication.id, business_id, result,
        )
        return result


def _merge_channel_statuses(
    existing: list[dict],
    updated: list[dict],
    source: str,  # 保留参数以兼容历史调用方，函数内部不再使用
) -> list[dict]:
    """合并 updated 频道状态到 existing：按 (platform, channel_id) 替换同名条目。

    历史实现是按 `_source` 整批替换——「openapi 侧 callback 视为完整覆盖」。
    但单渠道重试会产生新的 openapi task_id，后续 callback / sync_status
    只覆盖那个新 task 涉及的 channel，旧实现会把同 source 但其他 task
    发布过的成功 channel 一并清掉，导致历史成功数据丢失。

    新规则：existing 中未出现在 updated 里的条目原样保留；
    出现在 updated 里的条目用 updated 的版本替换。
    """
    del source  # noqa: F841 — kept for backward compat
    updated_keys = {
        (str(c.get("platform", "")), str(c.get("channel_id", "")))
        for c in updated
    }
    result = [
        c for c in existing
        if (str(c.get("platform", "")), str(c.get("channel_id", ""))) not in updated_keys
    ]
    result.extend(updated)
    return result


class VideoPublicationService:
    """视频发布服务"""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.open_api = OpenAPIClient()
        self.ext_pub = ExtPubAPIClient()
        self._openapi_adapter = OpenAPIAdapter(self.open_api)
        self._ext_pub_adapter = ExtPubAdapter(self.ext_pub)

    async def _load_publication_context_for_sub_task(self, sub_task_id: uuid.UUID) -> dict:
        result = await self.db.execute(
            select(VideoSubTask)
            .where(VideoSubTask.id == sub_task_id)
            .options(selectinload(VideoSubTask.task))
        )
        sub_task = result.scalar_one_or_none()
        if sub_task is None or sub_task.task is None:
            return {
                "ext_products": [],
                "promotion_code": None,
                "product_code_mode": None,
                "account_tier": None,
                "kol_user_id": None,
            }
        product_code_mode: str | None = None
        account_tier: str | None = None
        kol_user_id: str | None = None
        if sub_task.task.account_id:
            row = (await self.db.execute(
                select(Account.product_code_mode, Account.account_tier, Account.kol_user_id)
                .where(Account.id == sub_task.task.account_id)
            )).first()
            if row is not None:
                product_code_mode = row[0]
                account_tier = row[1]
                kol_user_id = row[2]
        publish_meta = sub_task.publish_meta if isinstance(sub_task.publish_meta, dict) else {}
        promotion_code = publish_meta.get("promotion_code")
        if not (
            isinstance(promotion_code, str)
            and len(promotion_code) == 8
            and promotion_code.isdigit()
        ):
            promotion_code = None
        return {
            "ext_products": build_ext_products_from_shots(sub_task.task.shots),
            "promotion_code": promotion_code,
            "product_code_mode": product_code_mode,
            "account_tier": account_tier,
            "kol_user_id": kol_user_id,
        }

    async def create_publication(self, data: VideoPublicationCreate) -> VideoPublication:
        """创建发布任务。

        channels 中每条可携带 channel_source 字段：
          - "openapi"（默认）：走原 Open API 发布
          - "ext_pub"：走外部发布 API（POST /api/posts），提交成功即视为完成

        同一账号每个平台只能绑定一种来源，但同一次发布可以混合（如
        YouTube 走内部、TikTok 走外部）。两侧并发提交，合并频道级状态
        后写入一条 VideoPublication 记录。
        """
        ext_channels = [c for c in data.channels if c.get("channel_source") == "ext_pub"]
        openapi_channels = [c for c in data.channels if c.get("channel_source") != "ext_pub"]
        if not data.channels:
            raise ValueError("至少需要一个发布渠道")

        publication_context = await self._load_publication_context_for_sub_task(data.sub_task_id)
        ext_products = publication_context["ext_products"]
        product_code_mode = (publication_context.get("product_code_mode") or "without_code")
        account_tier = publication_context.get("account_tier") or "test"
        kol_user_id: str | None = publication_context.get("kol_user_id") or None
        logger.info(
            "create_publication: sub_task_id=%s openapi_channels=%s ext_channels=%s ext_products=%d pre_generated_promotion_code=%s product_code_mode=%s",
            data.sub_task_id,
            openapi_channels,
            ext_channels,
            len(ext_products),
            bool(publication_context["promotion_code"]),
            product_code_mode,
        )
        # 仅当账号配置为「有商品码」时使用 / 分配 promotion_code；
        # 「无商品码」账号即使 publish_meta 残留 code 也不再使用，避免历史脏数据传染。
        if product_code_mode == "with_code":
            if publication_context["promotion_code"]:
                promotion_code: str | None = publication_context["promotion_code"]
                promotion_code_acquired_for_publication = False
            else:
                promotion_code = await promotion_code_distributor.acquire()
                promotion_code_acquired_for_publication = True
        else:
            promotion_code = None
            promotion_code_acquired_for_publication = False
        publication_committed = False

        # GCS 视频链发出去之前续签，给外部平台留足 7 天拉取窗口
        from app.utils.gcs_signing import refresh_publish_data_urls
        refresh_publish_data_urls(data)

        # 记录完整请求负载（用于 audit / 重试）：结构与发到 Open API 的实际 body 一致，
        # 仅 channels 保留含 channel_source 的完整 dict 以便 retry 路由识别
        callback_url_for_payload = data.callback_url or settings.open_api_callback_url or None
        request_payload: dict = _build_open_api_request_payload(
            data, data.channels, promotion_code, ext_products,
            account_tier=account_tier,
            kol_user_id=kol_user_id,
            callback_url=callback_url_for_payload,
        )
        # 标记哪些来源被使用，供 sync_status 判断是否需要调用对应 adapter
        request_payload["_has_openapi"] = bool(openapi_channels)
        request_payload["_has_ext_pub"] = bool(ext_channels)
        logger.info(
            "create_publication request_payload: sub_task_id=%s payload=%s",
            data.sub_task_id,
            _payload_for_log(request_payload),
        )

        # 并发向两侧提交
        open_api_task_id: str | None = None
        all_channel_statuses: list[dict] = []
        errors: list[str] = []

        submit_tasks = []
        if openapi_channels:
            submit_tasks.append(("openapi", self._openapi_adapter.submit(
                data,
                openapi_channels,
                promotion_code,
                ext_products,
                account_tier=account_tier,
                kol_user_id=kol_user_id,
            )))
        if ext_channels:
            submit_tasks.append(("ext_pub", self._ext_pub_adapter.submit(
                data,
                ext_channels,
                promotion_code,
                ext_products,
            )))

        try:
            results = await asyncio.gather(
                *[t for _, t in submit_tasks],
                return_exceptions=True,
            )
        except BaseException:
            if promotion_code_acquired_for_publication:
                await promotion_code_distributor.discard(promotion_code)
            raise

        for (source, _), result in zip(submit_tasks, results):
            if isinstance(result, Exception):
                logger.error("create_publication %s side failed: %s", source, result)
                errors.append(f"{source}: {result}")
                # 将该侧频道标记为 failed
                failed_channels = ext_channels if source == "ext_pub" else openapi_channels
                all_channel_statuses.extend([
                    {
                        "platform": c.get("platform", ""),
                        "channel_id": c["channel_id"],
                        "channel_name": c.get("channel_name", ""),
                        "status": "failed",
                        "platform_video_id": None,
                        "platform_video_url": None,
                        "error_message": str(result),
                        "uploaded_at": None,
                        "_source": _SOURCE_EXT_PUB if source == "ext_pub" else _SOURCE_OPENAPI,
                    }
                    for c in failed_channels
                ])
            else:
                task_id, channel_statuses = result
                if source == "openapi" and task_id:
                    open_api_task_id = task_id
                all_channel_statuses.extend(channel_statuses)

        overall_status = _compute_publication_status(all_channel_statuses)
        error_message = "; ".join(errors) if errors else None

        publication = VideoPublication(
            sub_task_id=data.sub_task_id,
            open_api_task_id=open_api_task_id,
            external_id=str(data.sub_task_id),
            status=overall_status,
            request_payload=request_payload,
            promotion_code=promotion_code,
            ext_products=ext_products,
            response_data=None,
            total_channels=len(all_channel_statuses),
            completed_channels=sum(1 for c in all_channel_statuses if c.get("status") in _SUCCESS_STATUSES),
            failed_channels=sum(1 for c in all_channel_statuses if c.get("status") in _FAILED_STATUSES),
            channels_status=all_channel_statuses or None,
            error_message=error_message,
        )
        if overall_status in ("completed", "partial", "failed"):
            publication.completed_at = utcnow()

        try:
            self.db.add(publication)
            # 检测 YouTube 账号被封禁的 channel，标记对应 reservation 为 disabled
            await _disable_suspended_channel_reservations(
                self.db, data.sub_task_id, all_channel_statuses,
            )
            await _apply_publication_status_to_sub_task(
                self.db,
                sub_task_id=data.sub_task_id,
                publication_status=overall_status,
            )
            await self.db.commit()
            publication_committed = True
            await promotion_code_distributor.mark_committed(promotion_code)
            await self.db.refresh(publication)
        except BaseException:
            if publication_committed:
                await promotion_code_distributor.mark_committed(promotion_code)
            else:
                await self.db.rollback()
                if promotion_code_acquired_for_publication:
                    await promotion_code_distributor.discard(promotion_code)
            raise

        logger.info(
            "create_publication done: sub_task_id=%s publication_id=%s status=%s",
            data.sub_task_id, publication.id, overall_status,
        )

        # 若两侧全部提交失败则向上抛出，让调用方感知
        if errors and len(errors) == len(submit_tasks):
            raise RuntimeError(f"所有发布渠道提交失败: {error_message}")

        return publication

    async def retry_publication(self, publication_id: uuid.UUID, owner_id: uuid.UUID | None) -> VideoPublication:
        """用上次的 request_payload 直接重新发布，sub_task 必须处于 publish_failed 状态。"""
        from app.models.video_task import VideoSubTask, VideoTask

        pub = await self.get_publication(publication_id)
        if pub is None:
            raise HTTPException(status_code=404, detail="发布记录不存在")

        # 权限校验
        result = await self.db.execute(
            select(VideoSubTask)
            .where(VideoSubTask.id == pub.sub_task_id)
            .options(selectinload(VideoSubTask.task))
        )
        sub_task = result.scalar_one_or_none()
        if sub_task is None:
            raise HTTPException(status_code=404, detail="子任务不存在")
        if owner_id is not None and sub_task.task.owner_id != owner_id:
            raise HTTPException(status_code=403, detail="无权操作")

        if sub_task.status != "publish_failed":
            raise HTTPException(status_code=422, detail=f"只有发布失败的任务才能重试，当前状态: {sub_task.status}")

        payload = pub.request_payload
        if not payload:
            raise HTTPException(status_code=422, detail="发布记录缺少原始请求参数，无法重试")

        # 重新读 channel 绑定：原 request_payload 里的 channel_id 可能因为换绑失效，
        # 仅以「原 publication 涉及哪些 platform」作为重试范围，每个 platform 的
        # channel_id / channel_source / channel_name 从 account_channel_reservations
        # 实时获取。
        account_id_for_retry = sub_task.task.account_id if sub_task.task else None
        if account_id_for_retry is None:
            raise HTTPException(status_code=422, detail="子任务关联的账号缺失，无法重试")

        original_platforms = list({
            str(c.get("platform", ""))
            for c in (payload.get("channels") or [])
            if isinstance(c, dict) and c.get("platform")
        })
        if not original_platforms:
            raise HTTPException(status_code=422, detail="发布记录缺少 platform 信息，无法重试")

        reservations = (await self.db.execute(
            select(AccountChannelReservation)
            .where(AccountChannelReservation.account_id == account_id_for_retry)
            .where(AccountChannelReservation.platform.in_(original_platforms))
            .where(AccountChannelReservation.status == "bound")
        )).scalars().all()
        reservation_by_platform = {r.platform: r for r in reservations if r.channel_id}

        retry_channels: list[dict] = []
        missing_platforms: list[str] = []
        for plat in original_platforms:
            res = reservation_by_platform.get(plat)
            if res is None:
                missing_platforms.append(plat)
                continue
            retry_channels.append({
                "platform": plat,
                "channel_id": res.channel_id,
                "channel_name": res.channel_name or "",
                "channel_source": res.channel_source or "openapi",
            })
        if missing_platforms:
            raise HTTPException(
                status_code=422,
                detail=f"账号当前未绑定以下平台或绑定渠道缺失，无法重试: {', '.join(missing_platforms)}",
            )
        if not retry_channels:
            raise HTTPException(status_code=422, detail="发布记录缺少发布渠道，无法重试")

        data = VideoPublicationCreate(
            sub_task_id=pub.sub_task_id,
            video_url=payload.get("video_url", ""),
            original_video_url=payload.get("original_video_url"),
            video_type=payload.get("video_type"),
            title=payload.get("title", ""),
            description=payload.get("description"),
            tags=payload.get("tags"),
            channels=retry_channels,
        )
        # GCS 视频链发出去之前续签
        from app.utils.gcs_signing import refresh_publish_data_urls
        refresh_publish_data_urls(data)
        ext_channels = [c for c in data.channels if c.get("channel_source") == "ext_pub"]
        openapi_channels = [c for c in data.channels if c.get("channel_source") != "ext_pub"]

        ext_products = _payload_ext_field(payload, "ext_products")
        if not isinstance(ext_products, list):
            ext_products = pub.ext_products if isinstance(pub.ext_products, list) else []

        # 重试时使用账号当前的 account_tier（晋级后立即生效）+ kol_user_id（事后回填的会被取到）
        retry_account_tier: str = "test"
        retry_kol_user_id: str | None = None
        if sub_task.task and sub_task.task.account_id:
            row = (await self.db.execute(
                select(Account.account_tier, Account.kol_user_id)
                .where(Account.id == sub_task.task.account_id)
            )).first()
            if row is not None:
                if row[0]:
                    retry_account_tier = row[0]
                retry_kol_user_id = row[1] or None

        payload_promotion_code = _payload_ext_field(payload, "promotion_code")
        if (
            isinstance(payload_promotion_code, str)
            and len(payload_promotion_code) == 8
            and payload_promotion_code.isdigit()
        ):
            promotion_code: str | None = payload_promotion_code
        else:
            promotion_code = pub.promotion_code
        if not (
            isinstance(promotion_code, str)
            and len(promotion_code) == 8
            and promotion_code.isdigit()
        ):
            # 「无商品码」账号原本就没有 promotion_code，重试时也保持 None
            promotion_code = None

        # 重新构造完整 request_payload（与发到 Open API 的 body 同构）
        callback_url_for_payload = data.callback_url or settings.open_api_callback_url or None
        request_payload: dict = _build_open_api_request_payload(
            data, retry_channels, promotion_code, ext_products,
            account_tier=retry_account_tier,
            kol_user_id=retry_kol_user_id,
            callback_url=callback_url_for_payload,
        )
        request_payload["_has_openapi"] = bool(openapi_channels)
        request_payload["_has_ext_pub"] = bool(ext_channels)

        logger.info(
            "retry_publication request_payload: publication_id=%s sub_task_id=%s payload=%s",
            pub.id,
            data.sub_task_id,
            _payload_for_log(request_payload),
        )

        open_api_task_id: str | None = None
        all_channel_statuses: list[dict] = []
        errors: list[str] = []

        submit_tasks = []
        if openapi_channels:
            submit_tasks.append(("openapi", self._openapi_adapter.submit(
                data,
                openapi_channels,
                promotion_code,
                ext_products,
                account_tier=retry_account_tier,
                kol_user_id=retry_kol_user_id,
            )))
        if ext_channels:
            submit_tasks.append(("ext_pub", self._ext_pub_adapter.submit(
                data,
                ext_channels,
                promotion_code,
                ext_products,
            )))

        results = await asyncio.gather(
            *[t for _, t in submit_tasks],
            return_exceptions=True,
        )

        for (source, _), result in zip(submit_tasks, results):
            if isinstance(result, Exception):
                logger.error("retry_publication %s side failed: %s", source, result)
                errors.append(f"{source}: {result}")
                failed_channels = ext_channels if source == "ext_pub" else openapi_channels
                all_channel_statuses.extend([
                    {
                        "platform": c.get("platform", ""),
                        "channel_id": c["channel_id"],
                        "channel_name": c.get("channel_name", ""),
                        "status": "failed",
                        "platform_video_id": None,
                        "platform_video_url": None,
                        "error_message": str(result),
                        "uploaded_at": None,
                        "_source": _SOURCE_EXT_PUB if source == "ext_pub" else _SOURCE_OPENAPI,
                    }
                    for c in failed_channels
                ])
            else:
                task_id, channel_statuses = result
                if source == "openapi" and task_id:
                    open_api_task_id = task_id
                all_channel_statuses.extend(channel_statuses)

        overall_status = _compute_publication_status(all_channel_statuses)
        error_message = "; ".join(errors) if errors else None

        pub.open_api_task_id = open_api_task_id
        pub.external_id = str(pub.sub_task_id)
        pub.status = overall_status
        pub.request_payload = request_payload
        pub.promotion_code = promotion_code
        pub.ext_products = ext_products
        pub.response_data = None
        pub.channels_status = all_channel_statuses or None
        pub.metrics_snapshot = None
        pub.total_channels = len(all_channel_statuses)
        pub.completed_channels = sum(1 for c in all_channel_statuses if c.get("status") in _SUCCESS_STATUSES)
        pub.failed_channels = sum(1 for c in all_channel_statuses if c.get("status") in _FAILED_STATUSES)
        pub.callback_received = False
        pub.callback_received_at = None
        pub.error_message = error_message
        pub.completed_at = utcnow() if overall_status in ("completed", "partial", "failed") else None

        # 检测 YouTube 账号被封禁的 channel，标记对应 reservation 为 disabled
        await _disable_suspended_channel_reservations(
            self.db, pub.sub_task_id, all_channel_statuses,
        )

        await _apply_publication_status_to_sub_task(
            self.db,
            sub_task_id=pub.sub_task_id,
            publication_status=overall_status,
        )
        await self.db.commit()
        await self.db.refresh(pub)

        logger.info(
            "retry_publication done: publication_id=%s sub_task_id=%s status=%s",
            pub.id,
            pub.sub_task_id,
            overall_status,
        )

        if errors and len(errors) == len(submit_tasks):
            raise RuntimeError(f"所有发布渠道提交失败: {error_message}")

        return pub

    async def retry_publication_channel(
        self,
        publication_id: uuid.UUID,
        platform: str,
        channel_id: str,
        owner_id: uuid.UUID | None,
    ) -> VideoPublication:
        """只重发当前 publication 中指定 (platform, channel_id) 的失败渠道。

        其他渠道（包括已成功和其他失败渠道）结果原样保留，便于用户在「查看数据」
        弹窗内逐个手动重发失败平台。
        """
        from app.models.video_task import VideoSubTask

        pub = await self.get_publication(publication_id)
        if pub is None:
            raise HTTPException(status_code=404, detail="发布记录不存在")

        result = await self.db.execute(
            select(VideoSubTask)
            .where(VideoSubTask.id == pub.sub_task_id)
            .options(selectinload(VideoSubTask.task))
        )
        sub_task = result.scalar_one_or_none()
        if sub_task is None:
            raise HTTPException(status_code=404, detail="子任务不存在")
        if owner_id is not None and sub_task.task.owner_id != owner_id:
            raise HTTPException(status_code=403, detail="无权操作")

        target_platform = str(platform or "")
        target_channel_id = str(channel_id or "")
        if not target_platform or not target_channel_id:
            raise HTTPException(status_code=422, detail="platform 和 channel_id 不能为空")

        existing_statuses: list[dict] = list(pub.channels_status or [])
        target_key = (target_platform, target_channel_id)
        failed_entries = [
            c for c in existing_statuses
            if c.get("status") in _FAILED_STATUSES
            and (str(c.get("platform", "")), str(c.get("channel_id", ""))) == target_key
        ]
        if not failed_entries:
            raise HTTPException(
                status_code=422,
                detail=f"指定渠道 {target_platform}/{target_channel_id} 当前不是失败状态，无需重发",
            )

        payload = pub.request_payload or {}

        # 关键：重试用的 channel_id / channel_source / channel_name 不复用 request_payload
        # 里的旧数据，而是从 account_channel_reservations 实时读取当前绑定。
        # 原因：原发布失败后用户可能换绑了同一平台的另一个 channel，旧 channel_id 已失效。
        account_id_for_retry = sub_task.task.account_id if sub_task.task else None
        if account_id_for_retry is None:
            raise HTTPException(status_code=422, detail="子任务关联的账号缺失，无法重发")

        reservation = (await self.db.execute(
            select(AccountChannelReservation)
            .where(AccountChannelReservation.account_id == account_id_for_retry)
            .where(AccountChannelReservation.platform == target_platform)
            .where(AccountChannelReservation.status == "bound")
        )).scalar_one_or_none()
        if reservation is None or not reservation.channel_id:
            raise HTTPException(
                status_code=422,
                detail=f"账号当前未绑定 {target_platform} 平台或绑定的 channel 缺失，无法重发",
            )

        retry_channel = {
            "platform": target_platform,
            "channel_id": reservation.channel_id,
            "channel_name": reservation.channel_name or "",
            "channel_source": reservation.channel_source or "openapi",
        }
        retry_channels: list[dict] = [retry_channel]

        ext_channels = [c for c in retry_channels if c.get("channel_source") == "ext_pub"]
        openapi_channels = [c for c in retry_channels if c.get("channel_source") != "ext_pub"]

        # 重试时使用账号当前 tier + kol_user_id
        retry_account_tier: str = "test"
        retry_kol_user_id: str | None = None
        if sub_task.task and sub_task.task.account_id:
            row = (await self.db.execute(
                select(Account.account_tier, Account.kol_user_id)
                .where(Account.id == sub_task.task.account_id)
            )).first()
            if row is not None:
                if row[0]:
                    retry_account_tier = row[0]
                retry_kol_user_id = row[1] or None

        payload_promotion_code = _payload_ext_field(payload, "promotion_code")
        if (
            isinstance(payload_promotion_code, str)
            and len(payload_promotion_code) == 8
            and payload_promotion_code.isdigit()
        ):
            promotion_code: str | None = payload_promotion_code
        else:
            promotion_code = pub.promotion_code
        if not (
            isinstance(promotion_code, str)
            and len(promotion_code) == 8
            and promotion_code.isdigit()
        ):
            promotion_code = None

        ext_products = _payload_ext_field(payload, "ext_products")
        if not isinstance(ext_products, list):
            ext_products = pub.ext_products if isinstance(pub.ext_products, list) else []

        data = VideoPublicationCreate(
            sub_task_id=pub.sub_task_id,
            video_url=payload.get("video_url", ""),
            original_video_url=payload.get("original_video_url"),
            video_type=payload.get("video_type"),
            title=payload.get("title", ""),
            description=payload.get("description"),
            tags=payload.get("tags"),
            channels=retry_channels,
        )
        # GCS 视频链发出去之前续签
        from app.utils.gcs_signing import refresh_publish_data_urls
        refresh_publish_data_urls(data)

        logger.info(
            "retry_publication_channel start: publication_id=%s sub_task_id=%s "
            "platform=%s channel_id=%s source=%s",
            pub.id,
            pub.sub_task_id,
            target_platform,
            target_channel_id,
            "ext_pub" if ext_channels else "openapi",
        )

        submit_tasks: list[tuple[str, Any]] = []
        if openapi_channels:
            submit_tasks.append(("openapi", self._openapi_adapter.submit(
                data, openapi_channels, promotion_code, ext_products,
                account_tier=retry_account_tier,
                kol_user_id=retry_kol_user_id,
            )))
        if ext_channels:
            submit_tasks.append(("ext_pub", self._ext_pub_adapter.submit(
                data, ext_channels, promotion_code, ext_products,
            )))

        results = await asyncio.gather(
            *[t for _, t in submit_tasks],
            return_exceptions=True,
        )

        new_open_api_task_id: str | None = None
        new_statuses: list[dict] = []
        errors: list[str] = []
        for (source, _), result in zip(submit_tasks, results):
            if isinstance(result, Exception):
                logger.error("retry_publication_channel %s side failed: %s", source, result)
                errors.append(f"{source}: {result}")
                failed_for_source = ext_channels if source == "ext_pub" else openapi_channels
                new_statuses.extend([
                    {
                        "platform": c.get("platform", ""),
                        "channel_id": c["channel_id"],
                        "channel_name": c.get("channel_name", ""),
                        "status": "failed",
                        "platform_video_id": None,
                        "platform_video_url": None,
                        "error_message": str(result),
                        "uploaded_at": None,
                        "_source": _SOURCE_EXT_PUB if source == "ext_pub" else _SOURCE_OPENAPI,
                    }
                    for c in failed_for_source
                ])
            else:
                task_id, channel_statuses = result
                if source == "openapi" and task_id:
                    new_open_api_task_id = task_id
                new_statuses.extend(channel_statuses)

        # 合并：删除 existing 中目标 platform 的所有旧条目（一个账号 / 平台只
        # 对应一条 channel，channel_id 可能因换绑发生变化），再追加新提交结果。
        merged: list[dict] = [
            c for c in existing_statuses
            if str(c.get("platform", "")) != target_platform
        ]
        merged.extend(new_statuses)

        overall_status = _compute_publication_status(merged)
        # 单渠道重试场景特殊处理：若新提交的渠道处于非终态，但其他渠道里仍有
        # 成功条目，则强制 publication.status 维持为 "partial"，避免被打回
        # "processing"。否则 sub_task 会被 _apply_publication_status_to_sub_task
        # 错误地切到 publishing，导致整条发布从「已发布」tab 里消失。
        # 等回调（或下次 sync_status）把新渠道刷成终态时，再走正常的
        # completed/partial/failed 计算。
        if overall_status == "processing" and any(
            c.get("status") in _SUCCESS_STATUSES for c in merged
        ):
            overall_status = "partial"

        error_message = "; ".join(errors) if errors else None

        # 同步 request_payload：保留其他平台原始 channels 信息；用最新绑定覆盖
        # 目标 platform 那条 channel，以便后续再次重试 / sync 使用最新 channel_id。
        existing_payload_channels = [
            c for c in (payload.get("channels") or [])
            if isinstance(c, dict) and str(c.get("platform", "")) != target_platform
        ]
        updated_payload = dict(payload)
        updated_payload["channels"] = existing_payload_channels + [retry_channel]
        # 把 promotion_code / ext_products / kol_user_id 写回嵌套的 ext_info（与 Open API body 结构一致）
        existing_ext_info = updated_payload.get("ext_info") if isinstance(updated_payload.get("ext_info"), dict) else {}
        merged_ext_info = dict(existing_ext_info)
        merged_ext_info["promotion_code"] = promotion_code
        merged_ext_info["ext_products"] = ext_products
        if retry_kol_user_id:
            merged_ext_info["kol_user_id"] = retry_kol_user_id
        elif "kol_user_id" in merged_ext_info and not retry_kol_user_id:
            # 账号上 kol_user_id 已被清空，audit 字段同步清掉避免误导
            merged_ext_info.pop("kol_user_id", None)
        # video_tags.env 用最新的 retry_account_tier 刷新
        env_for_tags = (retry_account_tier or "test").lower()
        if env_for_tags not in {"test", "dev", "prod"}:
            env_for_tags = "test"
        merged_ext_info["video_tags"] = {"env": [env_for_tags]}
        updated_payload["ext_info"] = merged_ext_info
        # 清掉老格式平铺字段（如果是历史行）：避免新旧两份不一致
        for legacy_key in ("promotion_code", "ext_products", "kol_user_id"):
            updated_payload.pop(legacy_key, None)
        updated_payload["_has_openapi"] = bool(openapi_channels) or payload.get("_has_openapi", False)
        updated_payload["_has_ext_pub"] = bool(ext_channels) or payload.get("_has_ext_pub", False)

        if new_open_api_task_id:
            pub.open_api_task_id = new_open_api_task_id
        pub.status = overall_status
        pub.request_payload = updated_payload
        pub.promotion_code = promotion_code
        pub.ext_products = ext_products
        pub.channels_status = merged or None
        pub.total_channels = len(merged)
        pub.completed_channels = sum(1 for c in merged if c.get("status") in _SUCCESS_STATUSES)
        pub.failed_channels = sum(1 for c in merged if c.get("status") in _FAILED_STATUSES)
        pub.error_message = error_message
        if overall_status in ("completed", "partial", "failed"):
            pub.completed_at = utcnow()
        # 若仍有非终态条目（如重新提交后变 pending/uploading），等待回调更新 completed_at
        else:
            pub.completed_at = None

        # 检测 YouTube 账号被封禁的 channel，标记对应 reservation 为 disabled
        await _disable_suspended_channel_reservations(
            self.db, pub.sub_task_id, merged,
        )

        await _apply_publication_status_to_sub_task(
            self.db,
            sub_task_id=pub.sub_task_id,
            publication_status=overall_status,
        )
        await self.db.commit()
        await self.db.refresh(pub)

        logger.info(
            "retry_publication_channel done: publication_id=%s sub_task_id=%s "
            "platform=%s channel_id=%s status=%s completed=%s failed=%s",
            pub.id, pub.sub_task_id,
            target_platform, target_channel_id,
            overall_status, pub.completed_channels, pub.failed_channels,
        )

        if errors and len(errors) == len(submit_tasks):
            raise RuntimeError(f"渠道重发提交失败: {error_message}")

        return pub

    async def get_publication(self, publication_id: uuid.UUID) -> VideoPublication | None:
        """获取发布任务"""
        from sqlalchemy import select

        result = await self.db.execute(
            select(VideoPublication).where(VideoPublication.id == publication_id)
        )
        return result.scalar_one_or_none()

    async def get_publications_by_sub_task(self, sub_task_id: uuid.UUID) -> list[VideoPublication]:
        """获取子任务的所有发布记录"""
        from sqlalchemy import select

        result = await self.db.execute(
            select(VideoPublication)
            .where(VideoPublication.sub_task_id == sub_task_id)
            .order_by(VideoPublication.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_publication_stats_page(
        self,
        query: VideoPublicationStatsQuery,
        owner_id: uuid.UUID | None = None,
    ) -> tuple[list[VideoPublicationStatsListItem], int]:
        """获取数据统计页所需的已发布视频列表。

        快速路径：当没有 platform / keyword 过滤且排序字段可下推 SQL 时，使用 SQL
        分页 + COUNT，仅加载当页数据；否则走回退路径（与历史一致：捞全量后在
        Python 里过滤+排序+切片）。
        """
        from app.models.video_task import VideoSubTask, VideoTask

        platform = (query.platform or "").strip().lower()
        keyword = (query.keyword or "").strip().lower()
        sql_sort_clauses = self._stats_sql_order_clauses(query.sort_by, query.sort_order)
        can_use_fast_path = not platform and not keyword and sql_sort_clauses is not None

        base_stmt = self._stats_base_select().where(
            VideoPublication.status.in_(["completed", "partial"])
        )
        base_stmt = self._apply_stats_sql_filters(base_stmt, query, owner_id)

        if can_use_fast_path:
            count_stmt = (
                select(func.count(VideoPublication.id.distinct()))
                .select_from(VideoPublication)
                .join(VideoSubTask, VideoSubTask.id == VideoPublication.sub_task_id)
                .join(VideoTask, VideoTask.id == VideoSubTask.task_id)
                .outerjoin(Account, Account.id == VideoTask.account_id)
                .outerjoin(VideoAITemplate, VideoAITemplate.id == VideoTask.template_id)
                .outerjoin(
                    VideoClassification,
                    VideoClassification.video_source_id == VideoAITemplate.video_source_id,
                )
                .where(VideoPublication.status.in_(["completed", "partial"]))
            )
            count_stmt = self._apply_stats_sql_filters(count_stmt, query, owner_id)
            total = int(await self.db.scalar(count_stmt) or 0)

            page_stmt = (
                base_stmt.order_by(*sql_sort_clauses)
                .offset(max(0, (query.page - 1) * query.page_size))
                .limit(query.page_size)
            )
            rows = (await self.db.execute(page_stmt)).all()
            items = await self._stats_rows_to_items(rows)
            return items, total

        # 回退路径：post-filter（platform / keyword / 复杂排序）
        rows = (await self.db.execute(
            base_stmt.order_by(
                VideoPublication.completed_at.desc().nullslast(),
                VideoPublication.created_at.desc(),
            )
        )).all()
        items = await self._stats_rows_to_items(rows)

        if platform:
            items = [item for item in items if self._matches_platform(item, platform)]
        if keyword:
            items = [item for item in items if self._matches_keyword(item, keyword)]

        items = self._sort_stats_items(items, query.sort_by, query.sort_order)
        total = len(items)
        start = (query.page - 1) * query.page_size
        end = start + query.page_size
        return items[start:end], total

    async def get_publication_stats_all(
        self,
        query: VideoPublicationStatsQuery,
        owner_id: uuid.UUID | None = None,
    ) -> list[VideoPublicationStatsListItem]:
        """返回全量数据（不分页），用于导出。"""
        stmt = (
            self._stats_base_select()
            .where(VideoPublication.status.in_(["completed", "partial"]))
            .order_by(
                VideoPublication.completed_at.asc().nullslast(),
                VideoPublication.created_at.asc(),
            )
        )
        stmt = self._apply_stats_sql_filters(stmt, query, owner_id)

        rows = (await self.db.execute(stmt)).all()
        items = await self._stats_rows_to_items(rows)

        platform = (query.platform or "").strip().lower()
        if platform:
            items = [item for item in items if self._matches_platform(item, platform)]

        keyword = (query.keyword or "").strip().lower()
        if keyword:
            items = [item for item in items if self._matches_keyword(item, keyword)]

        return items

    @staticmethod
    def _stats_base_select():
        """基础 select 语句：返回 (publication, sub_task, task, account, classification)。

        VideoAITemplate 仅参与 JOIN（不在 select 中），它的大 JSON 列不会被加载。
        VideoPublication.response_data 通过 defer 跳过加载（仅 list 视图不需要）。
        """
        from app.models.video_task import VideoSubTask, VideoTask

        return (
            select(VideoPublication, VideoSubTask, VideoTask, Account, VideoClassification)
            .options(defer(VideoPublication.response_data))
            .join(VideoSubTask, VideoSubTask.id == VideoPublication.sub_task_id)
            .join(VideoTask, VideoTask.id == VideoSubTask.task_id)
            .outerjoin(Account, Account.id == VideoTask.account_id)
            .outerjoin(VideoAITemplate, VideoAITemplate.id == VideoTask.template_id)
            .outerjoin(
                VideoClassification,
                VideoClassification.video_source_id == VideoAITemplate.video_source_id,
            )
        )

    @staticmethod
    def _apply_stats_sql_filters(stmt, query: VideoPublicationStatsQuery, owner_id):
        from app.models.video_task import VideoTask

        if owner_id is not None:
            stmt = stmt.where(VideoTask.owner_id == owner_id)
        if query.account_id is not None:
            stmt = stmt.where(VideoTask.account_id == query.account_id)
        if query.date_from is not None:
            stmt = stmt.where(
                VideoPublication.completed_at
                >= datetime.combine(query.date_from, datetime.min.time(), tzinfo=timezone.utc)
            )
        if query.date_to is not None:
            next_day = date.fromordinal(query.date_to.toordinal() + 1)
            stmt = stmt.where(
                VideoPublication.completed_at
                < datetime.combine(next_day, datetime.min.time(), tzinfo=timezone.utc)
            )
        if query.unclassified:
            stmt = stmt.where(VideoClassification.id.is_(None))
        elif query.category_indices:
            stmt = stmt.where(VideoClassification.category_key.in_(query.category_indices))
        if query.promotion_code_filter == "with":
            stmt = stmt.where(VideoPublication.promotion_code.is_not(None))
        elif query.promotion_code_filter == "without":
            stmt = stmt.where(VideoPublication.promotion_code.is_(None))
        return stmt

    @staticmethod
    def _stats_sql_order_clauses(sort_by: str | None, sort_order: str | None):
        """返回可下推 SQL 的 ORDER BY 子句；不可下推则返回 None。"""
        desc = str(sort_order or "desc").lower() != "asc"
        key = (sort_by or "published_at").lower()
        if key in ("", "published_at"):
            primary = VideoPublication.completed_at
            secondary = VideoPublication.created_at
            return (
                primary.desc().nullslast() if desc else primary.asc().nullslast(),
                secondary.desc() if desc else secondary.asc(),
            )
        if key == "account_name":
            col = Account.account_name
            return (col.desc().nullslast() if desc else col.asc().nullslast(),)
        if key == "kol_link_clicks":
            col = VideoPublication.kol_link_clicks
            return (
                col.desc().nullslast() if desc else col.asc().nullslast(),
                VideoPublication.completed_at.desc().nullslast(),
            )
        # title 在 request_payload JSON 中、metric 类排序需聚合 metrics_snapshot；都不下推
        return None

    async def _stats_rows_to_items(self, rows) -> list[VideoPublicationStatsListItem]:
        bindings_by_account = await self._load_social_bindings_by_account([
            account.id for _, _, _, account, _ in rows if account is not None
        ])
        return [
            self._build_stats_item(
                publication,
                sub_task,
                task,
                account,
                bindings_by_account.get(account.id, []) if account is not None else [],
                classification=classification,
            )
            for publication, sub_task, task, account, classification in rows
        ]

    def _build_stats_item(
        self,
        publication: VideoPublication,
        sub_task: Any,
        task: Any,
        account: Account | None,
        social_bindings: list[dict],
        *,
        classification: VideoClassification | None = None,
    ) -> VideoPublicationStatsListItem:
        request_payload = publication.request_payload or {}
        metrics_snapshot = publication.metrics_snapshot if isinstance(publication.metrics_snapshot, dict) else None
        metrics_channels = []
        if metrics_snapshot:
            raw_channels = metrics_snapshot.get("channels") or []
            if isinstance(raw_channels, list):
                metrics_channels = [channel for channel in raw_channels if isinstance(channel, dict)]

        total_views = 0
        total_likes = 0
        total_comments = 0
        total_shares = 0
        view_percentage_values: list[float] = []

        for channel in metrics_channels:
            stats = channel.get("stats") or {}
            platform = str(channel.get("platform") or "").lower()
            total_views += self._to_int(stats.get("views") if platform == "youtube" else stats.get("view_count"))
            total_likes += self._to_int(stats.get("likes") if platform == "youtube" else stats.get("like_count"))
            total_comments += self._to_int(stats.get("comments") if platform == "youtube" else stats.get("comment_count"))
            total_shares += self._to_int(stats.get("shares") if platform == "youtube" else stats.get("share_count"))

            avg_view_percentage = self._to_float(stats.get("average_view_percentage"))
            if avg_view_percentage is not None:
                view_percentage_values.append(avg_view_percentage)

        video_click_rate = None
        if publication.kol_link_clicks is not None and total_views > 0:
            video_click_rate = publication.kol_link_clicks / total_views * 100

        return VideoPublicationStatsListItem(
            id=publication.id,
            sub_task_id=publication.sub_task_id,
            task_id=getattr(task, "id", None),
            account_id=getattr(task, "account_id", None),
            account_name=getattr(account, "account_name", None),
            account_type=getattr(account, "account_type", None),
            social_bindings=social_bindings,
            status=publication.status,
            video_url=getattr(sub_task, "result_video_url", None),
            published_at=publication.completed_at,
            title=request_payload.get("title"),
            description=request_payload.get("description"),
            promotion_code=publication.promotion_code or _payload_ext_field(request_payload, "promotion_code"),
            ext_products=publication.ext_products or _payload_ext_field(request_payload, "ext_products"),
            channels_status=publication.channels_status,
            metrics_snapshot=metrics_snapshot,
            metrics_channels=metrics_channels,
            total_views=total_views,
            total_likes=total_likes,
            total_comments=total_comments,
            total_shares=total_shares,
            avg_view_percentage=(sum(view_percentage_values) / len(view_percentage_values)) if view_percentage_values else None,
            kol_link_clicks=publication.kol_link_clicks,
            video_click_rate=video_click_rate,
            category_key=getattr(classification, "category_key", None),
            category_label=_classification_label(classification),
            major_category=getattr(classification, "major_category", None),
            created_at=publication.created_at,
            updated_at=publication.updated_at,
        )

    async def _load_social_bindings_by_account(
        self,
        account_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, list[dict]]:
        unique_ids = list({aid for aid in account_ids if aid is not None})
        if not unique_ids:
            return {}
        stmt = (
            select(AccountChannelReservation)
            .where(AccountChannelReservation.account_id.in_(unique_ids))
            .where(AccountChannelReservation.status == "bound")
            .order_by(AccountChannelReservation.created_at.asc())
        )
        result: dict[uuid.UUID, list[dict]] = {aid: [] for aid in unique_ids}
        for row in (await self.db.execute(stmt)).scalars().all():
            binding = dict(row.channel_info or {})
            binding.update({
                "platform": row.platform,
                "channel_source": row.channel_source or row.source or "openapi",
                "channel_id": row.channel_id or "",
                "channel_name": row.channel_name or "",
                "username": row.username or "",
            })
            if row.avatar_url:
                binding["avatar_url"] = row.avatar_url
            result.setdefault(row.account_id, []).append(binding)
        return result

    @staticmethod
    def _to_int(value: Any) -> int:
        try:
            if value is None or value == "":
                return 0
            return int(float(value))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _to_float(value: Any) -> float | None:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _sort_stats_items(
        items: list[VideoPublicationStatsListItem],
        sort_by: str,
        sort_order: str,
    ) -> list[VideoPublicationStatsListItem]:
        reverse = str(sort_order or "desc").lower() != "asc"
        key_name = str(sort_by or "published_at").lower()

        def key(item: VideoPublicationStatsListItem):
            if key_name == "title":
                return (item.title or "").lower()
            if key_name == "account_name":
                return (item.account_name or "").lower()
            if key_name == "total_views":
                return item.total_views
            if key_name == "total_likes":
                return item.total_likes
            if key_name == "total_comments":
                return item.total_comments
            if key_name == "total_shares":
                return item.total_shares
            if key_name == "avg_view_percentage":
                return item.avg_view_percentage if item.avg_view_percentage is not None else -1
            if key_name == "kol_link_clicks":
                return item.kol_link_clicks if item.kol_link_clicks is not None else -1
            if key_name == "video_click_rate":
                return item.video_click_rate if item.video_click_rate is not None else -1
            return item.published_at or item.created_at or datetime.min.replace(tzinfo=timezone.utc)

        return sorted(items, key=key, reverse=reverse)

    @staticmethod
    def _matches_platform(item: VideoPublicationStatsListItem, platform: str) -> bool:
        for channel in item.metrics_channels:
            if str(channel.platform or "").lower() == platform:
                return True
        for channel in item.channels_status or []:
            if str(channel.platform or "").lower() == platform:
                return True
        return False

    @staticmethod
    def _matches_keyword(item: VideoPublicationStatsListItem, keyword: str) -> bool:
        haystacks = [
            item.title or "",
            item.account_name or "",
        ]
        for channel in item.metrics_channels:
            haystacks.append(str(channel.channel_name or ""))
            haystacks.append(str(channel.platform_video_url or ""))
        for channel in item.channels_status or []:
            haystacks.append(channel.channel_name or "")
            haystacks.append(channel.platform_video_url or "")
        return any(keyword in value.lower() for value in haystacks if value)

    async def sync_publication_status(self, publication_id: uuid.UUID) -> VideoPublication:
        """同步频道级状态，ext_pub 侧视为提交即完成，仅轮询 openapi 侧。"""
        publication = await self.get_publication(publication_id)
        if not publication:
            raise ValueError("发布任务不存在")

        payload = publication.request_payload or {}

        # ext_pub 侧不再轮询；新老数据都只用 openapi 标记或 task_id 判断是否有活动发布侧。
        if "_has_openapi" in payload or "_has_ext_pub" in payload:
            has_openapi = payload.get("_has_openapi", False)
        else:
            has_openapi = bool(publication.open_api_task_id)

        existing_statuses: list[dict] = publication.channels_status or []
        merged, ext_finalized = _finalize_ext_pub_channel_statuses(existing_statuses)

        sync_tasks = []
        if has_openapi:
            sync_tasks.append(("openapi", self._openapi_adapter.sync_status(publication)))

        if not sync_tasks:
            logger.debug(
                "sync_publication_status: publication %s 无 openapi 活跃适配器%s",
                publication_id,
                "，仅应用 ext_pub 自动完成" if ext_finalized else "，跳过轮询",
            )

        else:
            results = await asyncio.gather(
                *[t for _, t in sync_tasks],
                return_exceptions=True,
            )

            for (source, _), result in zip(sync_tasks, results):
                if isinstance(result, Exception):
                    logger.error("sync_publication_status %s side failed for %s: %s", source, publication_id, result)
                    continue
                updated_channels: list[dict] = result
                if updated_channels:
                    merged = _merge_channel_statuses(merged, updated_channels, source)

        # 重新计算汇总状态
        new_status = _compute_publication_status(merged)
        publication.status = new_status
        publication.channels_status = merged or None
        publication.total_channels = len(merged)
        publication.completed_channels = sum(1 for c in merged if c.get("status") in _SUCCESS_STATUSES)
        publication.failed_channels = sum(1 for c in merged if c.get("status") in _FAILED_STATUSES)

        if new_status in ("completed", "partial", "failed") and not publication.completed_at:
            publication.completed_at = utcnow()

        # 同步检测 YouTube 账号被封禁的 channel，标记对应 reservation 为 disabled
        await _disable_suspended_channel_reservations(
            self.db, publication.sub_task_id, merged,
        )

        # 根据终态联动更新子任务状态
        await _apply_publication_status_to_sub_task(
            self.db,
            sub_task_id=publication.sub_task_id,
            publication_status=new_status,
        )

        await self.db.commit()
        await self.db.refresh(publication)
        return publication

    async def sync_metrics_for_stats_page(
        self,
        query: VideoPublicationStatsQuery,
        owner_id: uuid.UUID | None = None,
    ) -> dict:
        """批量同步数据统计页中已完成发布记录的指标快照。
        按当前筛选条件捞出所有 completed 记录，逐一调用 Open API metrics，
        将结果写入 metrics_snapshot 字段。
        返回 {"synced": n, "failed": n} 统计。
        """
        from app.models.video_task import VideoSubTask, VideoTask
        from datetime import date

        stmt = (
            select(VideoPublication)
            .join(VideoSubTask, VideoSubTask.id == VideoPublication.sub_task_id)
            .join(VideoTask, VideoTask.id == VideoSubTask.task_id)
            .where(VideoPublication.status.in_(["completed", "partial"]))
            .where(VideoPublication.open_api_task_id.isnot(None))
        )
        if owner_id is not None:
            stmt = stmt.where(VideoTask.owner_id == owner_id)
        if query.account_id is not None:
            stmt = stmt.where(VideoTask.account_id == query.account_id)
        if query.date_from is not None:
            stmt = stmt.where(
                VideoPublication.completed_at >= datetime.combine(query.date_from, datetime.min.time(), tzinfo=timezone.utc)
            )
        if query.date_to is not None:
            next_day = date.fromordinal(query.date_to.toordinal() + 1)
            stmt = stmt.where(
                VideoPublication.completed_at < datetime.combine(next_day, datetime.min.time(), tzinfo=timezone.utc)
            )

        publications = list((await self.db.execute(stmt)).scalars().all())

        # platform / keyword 是 post-filter（列表页一致逻辑），用 get_publication_stats_all
        # 拿到匹配的 publication id 集合，再过滤 publications，保证同步范围和列表页完全一致。
        platform = (query.platform or "").strip()
        keyword = (query.keyword or "").strip()
        if platform or keyword:
            matched_items = await self.get_publication_stats_all(query, owner_id=owner_id)
            matched_ids = {item.id for item in matched_items}
            publications = [pub for pub in publications if pub.id in matched_ids]

        synced = 0
        failed = 0
        for pub in publications:
            # 跳过纯 ext_pub 发布（无 openapi 侧），不调 Open API metrics 接口
            payload = pub.request_payload or {}
            if payload.get("_has_ext_pub") and not payload.get("_has_openapi"):
                logger.debug("sync_metrics: skip ext_pub-only publication %s", pub.id)
                continue

            await asyncio.sleep(_SYNC_METRICS_RATE_LIMIT_SEC)
            for attempt in range(_SYNC_METRICS_RETRIES + 1):
                try:
                    response = await self.open_api.fetch_upload_metrics(
                        task_id=pub.open_api_task_id,
                        external_id=pub.external_id,
                    )
                    logger.debug(
                        "sync_metrics: publication=%s task_id=%s external_id=%s response=%s",
                        pub.id, pub.open_api_task_id, pub.external_id, response,
                    )
                    if response.get("code") != 0:
                        raise RuntimeError(f"API code={response.get('code')} msg={response.get('message')}")
                    data = response.get("data") or {}
                    snapshot = {
                        "status": data.get("status"),
                        "total_channels": data.get("total_channels", 0),
                        "completed_channels": data.get("completed_channels", 0),
                        "failed_channels": data.get("failed_channels", 0),
                        "synced_at": utcnow().isoformat(),
                        "channels": data.get("channels") or [],
                    }
                    pub.metrics_snapshot = snapshot
                    synced += 1
                    break
                except (httpx.ConnectTimeout, httpx.ReadTimeout, httpx.ConnectError) as exc:
                    if attempt < _SYNC_METRICS_RETRIES:
                        logger.warning("sync_metrics: timeout for publication %s, %ds 后重试: %s", pub.id, _SYNC_METRICS_RETRY_DELAY_SEC, exc)
                        await asyncio.sleep(_SYNC_METRICS_RETRY_DELAY_SEC)
                    else:
                        logger.warning("sync_metrics: timeout for publication %s, 放弃: %s", pub.id, exc)
                        failed += 1
                except Exception as exc:
                    if attempt < _SYNC_METRICS_RETRIES:
                        logger.warning("sync_metrics: error for publication %s, %ds 后重试: %s", pub.id, _SYNC_METRICS_RETRY_DELAY_SEC, exc)
                        await asyncio.sleep(_SYNC_METRICS_RETRY_DELAY_SEC)
                    else:
                        logger.exception("sync_metrics: error for publication %s, 放弃", pub.id)
                        failed += 1

        if synced:
            await self.db.commit()

        return {"synced": synced, "failed": failed, "total": len(publications)}

    async def handle_callback(self, callback_data: dict) -> VideoPublication | None:
        """处理 Open API 回调"""
        task_id = callback_data.get("task_id")
        external_id = callback_data.get("external_id")

        logger.info(
            "handle_callback: looking up publication by task_id=%s OR external_id=%s",
            task_id, external_id,
        )

        # 查找对应的发布任务：优先同时匹配 open_api_task_id 和 external_id（AND），
        # 若未找到则单独用 open_api_task_id 回退（external_id 可能重复，不单独作为回退）
        from sqlalchemy import select

        publication = None
        if task_id and external_id:
            result = await self.db.execute(
                select(VideoPublication).where(
                    (VideoPublication.open_api_task_id == task_id) &
                    (VideoPublication.external_id == external_id)
                )
            )
            publication = result.scalar_one_or_none()

        if publication is None and task_id:
            result = await self.db.execute(
                select(VideoPublication).where(VideoPublication.open_api_task_id == task_id)
            )
            publication = result.scalar_one_or_none()

        if not publication:
            # 打印所有 publication 记录帮助排查
            all_pubs = (await self.db.execute(select(VideoPublication))).scalars().all()
            logger.warning(
                "handle_callback: no publication found. Total publications in DB: %d. "
                "task_ids=%s, external_ids=%s",
                len(all_pubs),
                [p.open_api_task_id for p in all_pubs],
                [p.external_id for p in all_pubs],
            )
            return None

        # 更新 publication 状态——只合并 openapi 侧频道状态
        callback_channels_raw = callback_data.get("channels") or []
        callback_channels = [{**ch, "_source": _SOURCE_OPENAPI} for ch in callback_channels_raw]
        merged = _merge_channel_statuses(
            publication.channels_status or [], callback_channels, _SOURCE_OPENAPI,
        )

        computed_status = _compute_publication_status(merged)
        publication.status = computed_status
        publication.total_channels = len(merged)
        publication.completed_channels = sum(1 for c in merged if c.get("status") in _SUCCESS_STATUSES)
        publication.failed_channels = sum(1 for c in merged if c.get("status") in _FAILED_STATUSES)
        publication.channels_status = merged or None
        publication.callback_received = True
        publication.callback_received_at = utcnow()

        if callback_data.get("completed_at"):
            from datetime import datetime
            completed_at = callback_data["completed_at"]
            if isinstance(completed_at, datetime):
                publication.completed_at = completed_at
            else:
                publication.completed_at = datetime.fromisoformat(str(completed_at).replace("Z", "+00:00"))

        logger.info(
            "handle_callback: updating publication %s openapi channels=%d → computed_status=%s",
            publication.id, len(callback_channels), computed_status,
        )

        # 检测 YouTube 账号被封禁的 channel，标记对应 reservation 为 disabled
        await _disable_suspended_channel_reservations(
            self.db, publication.sub_task_id, merged,
        )

        await _apply_publication_status_to_sub_task(
            self.db,
            sub_task_id=publication.sub_task_id,
            publication_status=computed_status,
        )

        await self.db.commit()
        await self.db.refresh(publication)

        return publication

    async def fetch_channels(
        self,
        platform: str,
        page: int = 1,
        page_size: int = 20,
        is_active: bool | None = None,
        usage_types: list[str] | None = None,
    ) -> dict:
        """获取渠道列表（代理到 Open API）"""
        return await self.open_api.fetch_channels(platform, page=page, page_size=page_size, is_active=is_active, usage_types=usage_types)

    async def fetch_channels_filtered(
        self,
        platform: str,
        owner_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        is_active: bool | None = None,
        current_account_id: uuid.UUID | None = None,
        usage_types: list[str] | None = None,
    ) -> dict:
        """过滤掉当前用户下已被其他账号绑定过的渠道，并对过滤后的结果重新分页。"""
        excluded_channel_ids = await self._load_excluded_channel_ids(
            owner_id=owner_id,
            platform=platform,
            current_account_id=current_account_id,
        )
        logger.info(
            "Open API fetch_channels filtered request: platform=%s owner_id=%s page=%s page_size=%s current_account_id=%s excluded=%s",
            platform,
            owner_id,
            page,
            page_size,
            current_account_id,
            len(excluded_channel_ids),
        )
        if not excluded_channel_ids:
            return await self.fetch_channels(platform, page=page, page_size=page_size, is_active=is_active, usage_types=usage_types)

        upstream_page = 1
        upstream_page_size = max(page_size, 100)
        upstream_total = 0
        filtered_items: list[dict[str, Any]] = []

        while True:
            response = await self.open_api.fetch_channels(
                platform,
                page=upstream_page,
                page_size=upstream_page_size,
                is_active=is_active,
                usage_types=usage_types,
            )
            data = response.get("data", {}) if isinstance(response, dict) else {}
            raw_items = data.get("items") or []
            upstream_total = max(upstream_total, int(data.get("total") or 0))
            filtered_items.extend(
                item
                for item in raw_items
                if str(item.get("channel_id") or "").strip() not in excluded_channel_ids
            )
            if len(raw_items) < upstream_page_size:
                break
            if upstream_total and upstream_page * upstream_page_size >= upstream_total:
                break
            upstream_page += 1

        start = max(page - 1, 0) * page_size
        end = start + page_size
        page_items = filtered_items[start:end]
        logger.info(
            "Open API fetch_channels filtered response: platform=%s owner_id=%s upstream_total=%s filtered_total=%s page=%s page_size=%s returned=%s",
            platform,
            owner_id,
            upstream_total,
            len(filtered_items),
            page,
            page_size,
            len(page_items),
        )
        return {
            "code": 0,
            "message": "success",
            "data": {
                "items": page_items,
                "total": len(filtered_items),
                "page": page,
                "page_size": page_size,
            },
        }

    async def _load_excluded_channel_ids(
        self,
        owner_id: uuid.UUID,
        platform: str,
        current_account_id: uuid.UUID | None = None,
        channel_source: str | None = None,
    ) -> set[str]:
        """返回当前用户下（排除 current_account_id）已绑定的 channel_id 集合。

        channel_source: 若传入则只统计该来源（openapi / ext_pub），
                        None 表示统计所有来源。
        """
        stmt = (
            select(AccountChannelReservation.channel_id)
            .join(Account, Account.id == AccountChannelReservation.account_id)
            .where(Account.owner_id == owner_id)
            .where(AccountChannelReservation.platform == platform)
            .where(AccountChannelReservation.status == "bound")
        )
        if current_account_id is not None:
            stmt = stmt.where(Account.id != current_account_id)
        if channel_source is not None:
            stmt = stmt.where(AccountChannelReservation.channel_source == channel_source)
        rows = (await self.db.execute(stmt)).scalars().all()
        return {str(channel_id).strip() for channel_id in rows if str(channel_id or "").strip()}

    # ── 统一频道查询 ──────────────────────────────────────────────────────────────

    @staticmethod
    def _normalize_openapi_channel(item: dict) -> dict:
        """将 Open API 渠道条目归一化为统一格式。"""
        return {
            "channel_id": str(item.get("channel_id") or ""),
            "channel_name": str(item.get("channel_name") or ""),
            "username": str(item.get("username") or ""),
            "platform": str(item.get("platform") or ""),
            "channel_source": _SOURCE_OPENAPI,
            # 内部额外字段，前端可选用
            "avatar_url": item.get("avatar_url"),
        }

    @staticmethod
    def _normalize_ext_pub_channel(item: dict) -> dict:
        """将外部发布 API 平台账号条目归一化为统一格式。"""
        return {
            "channel_id": str(item.get("id") or ""),
            "channel_name": str(item.get("nickname") or item.get("username") or ""),
            "username": str(item.get("username") or ""),
            "platform": str(item.get("platform_type") or ""),
            "channel_source": _SOURCE_EXT_PUB,
            "avatar_url": None,
        }

    async def fetch_channels_unified(
        self,
        platform: str,
        channel_source: str,               # "openapi" | "ext_pub"
        owner_id: uuid.UUID,
        page: int = 1,
        page_size: int = 50,
        is_active: bool | None = None,
        current_account_id: uuid.UUID | None = None,
        usage_types: list[str] | None = None,
    ) -> dict:
        """统一频道查询入口，按 channel_source 路由到对应上游，过滤已占用频道，返回归一化结果。

        统一返回格式（data.items 每条）：
        {
          "channel_id": str,
          "channel_name": str,
          "username": str,
          "platform": str,
          "channel_source": "openapi" | "ext_pub",
          "avatar_url": str | null,
        }
        """
        excluded = await self._load_excluded_channel_ids(
            owner_id=owner_id,
            platform=platform,
            current_account_id=current_account_id,
            channel_source=channel_source,
        )
        logger.info(
            "fetch_channels_unified: platform=%s source=%s page=%s page_size=%s excluded=%d",
            platform, channel_source, page, page_size, len(excluded),
        )

        if channel_source == _SOURCE_EXT_PUB:
            return await self._fetch_ext_pub_channels_unified(
                platform=platform,
                page=page,
                page_size=page_size,
                excluded=excluded,
            )
        else:
            return await self._fetch_openapi_channels_unified(
                platform=platform,
                page=page,
                page_size=page_size,
                is_active=is_active,
                usage_types=usage_types,
                excluded=excluded,
            )

    async def _fetch_openapi_channels_unified(
        self,
        platform: str,
        page: int,
        page_size: int,
        is_active: bool | None,
        usage_types: list[str] | None,
        excluded: set[str],
    ) -> dict:
        if not excluded:
            response = await self.open_api.fetch_channels(
                platform, page=page, page_size=page_size,
                is_active=is_active, usage_types=usage_types,
            )
            data = response.get("data", {}) if isinstance(response, dict) else {}
            raw_items = data.get("items") or []
            items = [self._normalize_openapi_channel(i) for i in raw_items]
            return {"code": 0, "message": "success", "data": {
                "items": items, "total": int(data.get("total") or 0),
                "page": page, "page_size": page_size,
            }}

        # 有排除列表时，拉全量过滤后重新分页（与原 fetch_channels_filtered 逻辑一致）
        upstream_page = 1
        upstream_page_size = max(page_size, 100)
        upstream_total = 0
        filtered: list[dict] = []

        while True:
            response = await self.open_api.fetch_channels(
                platform, page=upstream_page, page_size=upstream_page_size,
                is_active=is_active, usage_types=usage_types,
            )
            data = response.get("data", {}) if isinstance(response, dict) else {}
            raw_items = data.get("items") or []
            upstream_total = max(upstream_total, int(data.get("total") or 0))
            for item in raw_items:
                if str(item.get("channel_id") or "").strip() not in excluded:
                    filtered.append(self._normalize_openapi_channel(item))
            if len(raw_items) < upstream_page_size:
                break
            if upstream_total and upstream_page * upstream_page_size >= upstream_total:
                break
            upstream_page += 1

        start = max(page - 1, 0) * page_size
        return {"code": 0, "message": "success", "data": {
            "items": filtered[start: start + page_size],
            "total": len(filtered),
            "page": page,
            "page_size": page_size,
        }}

    async def _fetch_ext_pub_channels_unified(
        self,
        platform: str,
        page: int,
        page_size: int,
        excluded: set[str],
    ) -> dict:
        """拉取外部发布 API 的平台账号，过滤已占用，归一化后分页返回。

        外部 API 默认 page_size=20，这里循环翻页拉取全量数据后在本地分页。
        """
        _upstream_page_size = 100
        upstream_page = 1
        all_raw: list[dict] = []

        try:
            while True:
                response = await self.ext_pub.fetch_platform_accounts(
                    platform=platform,
                    page=upstream_page,
                    page_size=_upstream_page_size,
                )
                data = response.get("data") if isinstance(response, dict) else {}
                items: list[dict] = (data.get("items") if isinstance(data, dict) else None) or []
                all_raw.extend(items)
                total = int(data.get("total") or 0) if isinstance(data, dict) else 0
                if len(items) < _upstream_page_size or (total and upstream_page * _upstream_page_size >= total):
                    break
                upstream_page += 1
        except Exception:
            logger.exception("fetch_ext_pub_channels_unified: upstream error")
            return {"code": 0, "message": "success", "data": {"items": [], "total": 0, "page": page, "page_size": page_size}}

        filtered = [
            self._normalize_ext_pub_channel(item)
            for item in all_raw
            if isinstance(item, dict) and str(item.get("id") or "").strip() not in excluded
        ]

        start = max(page - 1, 0) * page_size
        return {"code": 0, "message": "success", "data": {
            "items": filtered[start: start + page_size],
            "total": len(filtered),
            "page": page,
            "page_size": page_size,
        }}
