import io
import re
import uuid
from datetime import date
from urllib.parse import quote
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import TokenData, get_current_user
from app.db.session import get_db
from app.schemas.video_publication import (
    VideoPublicationCreate,
    VideoPublicationDetailRead,
    VideoPublicationRead,
    VideoPublicationStatsListResponse,
    VideoPublicationStatsQuery,
    VideoPublicationStatusUpdate,
)
from app.services.video_publication_service import VideoPublicationService

router = APIRouter()
logger = __import__("logging").getLogger("app.video_publications")


def _parse_category_indices(raw: str | None) -> list[int] | None:
    if not raw:
        return None
    try:
        return [int(x) for x in raw.split(",") if x.strip() != ""] or None
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="category_indices 必须是逗号分隔的整数",
        ) from exc


@router.post("/video-publications", response_model=VideoPublicationRead)
async def create_publication(
    data: VideoPublicationCreate,
    db: AsyncSession = Depends(get_db),
):
    """创建视频发布任务"""
    service = VideoPublicationService(db)

    # 验证子任务存在
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.video_task import VideoSubTask

    result = await db.execute(
        select(VideoSubTask)
        .where(VideoSubTask.id == data.sub_task_id)
        .options(selectinload(VideoSubTask.task))
    )
    sub_task = result.scalar_one_or_none()

    if not sub_task:
        raise HTTPException(status_code=404, detail="子任务不存在")

    if not sub_task.selected:
        raise HTTPException(status_code=400, detail="只能发布已选中的视频")

    if sub_task.status not in ("queued", "pending_publish"):
        raise HTTPException(status_code=400, detail=f"视频状态不允许发布: {sub_task.status}")

    if not sub_task.result_video_url:
        raise HTTPException(status_code=400, detail="视频尚未生成完成")

    try:
        publication = await service.create_publication(data)
        return publication
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建发布任务失败: {str(e)}")


@router.get("/video-publications/stats", response_model=VideoPublicationStatsListResponse)
async def get_publication_stats(
    platform: str | None = Query(None, description="平台类型: tiktok/youtube/instagram"),
    account_id: uuid.UUID | None = Query(None, description="账号 ID"),
    date_from: date | None = Query(None, description="发布时间起始日期"),
    date_to: date | None = Query(None, description="发布时间结束日期"),
    keyword: str | None = Query(None, description="标题/账号/渠道/平台链接关键字"),
    category_indices: str | None = Query(None, description="视频分类（0-13），逗号分隔"),
    unclassified: bool = Query(False, description="只显示未分类视频"),
    promotion_code_filter: str | None = Query(None, description="商品码筛选: with/without"),
    sort_by: str = Query("published_at", description="排序字段"),
    sort_order: str = Query("desc", description="排序方向: asc/desc"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取数据统计页已发布视频列表。"""
    parsed_category_indices = _parse_category_indices(category_indices)
    query = VideoPublicationStatsQuery(
        platform=platform,
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
        keyword=keyword,
        category_indices=parsed_category_indices,
        unclassified=unclassified,
        promotion_code_filter=promotion_code_filter or None,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )
    owner_id = None if current_user.is_admin else current_user.user_id
    service = VideoPublicationService(db)
    items, total = await service.get_publication_stats_page(query, owner_id=owner_id)
    return VideoPublicationStatsListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/video-publications/stats/export")
async def export_publication_stats(
    platform: str | None = Query(None),
    account_id: uuid.UUID | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    keyword: str | None = Query(None),
    category_indices: str | None = Query(None),
    unclassified: bool = Query(False),
    promotion_code_filter: str | None = Query(None),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """导出数据统计 CSV，按博主×日期透视表格式。"""
    parsed_category_indices = _parse_category_indices(category_indices)
    query = VideoPublicationStatsQuery(
        platform=platform,
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
        keyword=keyword,
        category_indices=parsed_category_indices,
        unclassified=unclassified,
        promotion_code_filter=promotion_code_filter or None,
    )
    owner_id = None if current_user.is_admin else current_user.user_id
    service = VideoPublicationService(db)
    items = await service.get_publication_stats_all(query, owner_id=owner_id)

    # 加载 account 详情 + 关联 flags（关联Flag 列只展示形如 <xxx> 的 flag，其它博主留空）
    from sqlalchemy import select as _select
    from app.models.account import Account
    from app.models.flag import AccountFlag, Flag

    account_ids: set[uuid.UUID] = {item.account_id for item in items if item.account_id is not None}

    account_details: dict[uuid.UUID, Account] = {}
    flag_names_by_account: dict[uuid.UUID, list[str]] = {}
    if account_ids:
        acc_rows = (await db.execute(_select(Account).where(Account.id.in_(account_ids)))).scalars().all()
        account_details = {a.id: a for a in acc_rows}

        flag_rows = (await db.execute(
            _select(AccountFlag.account_id, Flag.name)
            .join(Flag, AccountFlag.flag_id == Flag.id)
            .where(AccountFlag.account_id.in_(account_ids))
            .order_by(AccountFlag.created_at.asc())
        )).all()
        for aid, name in flag_rows:
            flag_names_by_account.setdefault(aid, []).append(name or "")

    _bracket_re = re.compile(r"^<[^<>]+>$")

    # 收集所有出现的日期（列），升序
    date_set: set[str] = set()
    for item in items:
        dt = item.published_at or item.created_at
        if dt:
            date_set.add(dt.strftime("%Y-%m-%d"))
    dates = sorted(date_set, reverse=True)

    # 收集每个 account_id 绑定的平台（优先从 social_bindings 提取，拼完整主页 URL）
    _platform_base = {
        "youtube": "https://www.youtube.com/",
        "tiktok": "https://www.tiktok.com/",
        "instagram": "https://www.instagram.com/",
    }
    account_bindings: dict[uuid.UUID | None, list[tuple[str, str, str]]] = {}
    seen_ids: set[uuid.UUID | None] = set()
    for item in items:
        aid = item.account_id
        if aid in seen_ids:
            continue
        seen_ids.add(aid)
        # 优先从 account.social_bindings 提取，生成 (URL, 频道名称, 平台) 三元组
        pairs: list[tuple[str, str, str]] = []
        for binding in item.social_bindings or []:
            if not isinstance(binding, dict):
                continue
            p = str(binding.get("platform") or "").lower()
            username = str(binding.get("username") or "").strip()
            channel_name = str(binding.get("channel_name") or "").strip()
            if not p:
                continue
            base = _platform_base.get(p)
            if base and username:
                url = f"{base}{username}"
            elif base:
                url = base.rstrip("/")
            else:
                url = ""
            pairs.append((url, channel_name, p))
        # 兜底：从 metrics_channels 和 channels_status 补充平台名（无频道名）
        if not pairs:
            platforms_set: set[str] = set()
            for ch in item.metrics_channels:
                p = str(ch.platform or "").lower()
                if p:
                    platforms_set.add(p)
            for ch in item.channels_status or []:
                p = str(ch.platform or "").lower()
                if p:
                    platforms_set.add(p)
            pairs = [(_platform_base.get(p, p).rstrip("/"), "", p) for p in sorted(platforms_set)]
        account_bindings[aid] = pairs

    # 按账号名分组：{ name -> { account_type, ..., date -> { platform -> [(views, likes), ...] } } }
    _gender_map = {"male": "男", "female": "女", "unisex": "男女皆有"}
    _face_map = {"face": "控脸", "no_face": "不控脸"}
    _pc_map = {"with_code": "带码", "without_code": "不带码"}
    _type_map = {"persona": "人设号", "shared": "共享号", "exclusive": "独享号"}

    blogger_map: dict[str, dict] = {}
    for item in items:
        name = item.account_name or "未知账号"
        if name not in blogger_map:
            account_type = _type_map.get(item.account_type or "", "共享号")
            bindings = account_bindings.get(item.account_id, [])

            acc = account_details.get(item.account_id) if item.account_id else None
            gender = _gender_map.get(getattr(acc, "gender", "") or "", "")
            face = _face_map.get(getattr(acc, "face_mode", "") or "", "")
            product_code = _pc_map.get(getattr(acc, "product_code_mode", "") or "", "")

            cls_type = getattr(acc, "classification_type", None) if acc else None
            summary = (getattr(acc, "classification_summary", None) or {}) if acc else {}
            if cls_type == "single":
                core_type = "单核心"
                core_detail = summary.get("primary") or ""
            elif cls_type == "dual":
                core_type = "双核心"
                primary = summary.get("primary") or ""
                secondary = summary.get("secondary") or ""
                core_detail = f"{primary}+{secondary}" if (primary or secondary) else ""
            else:
                core_type = ""
                core_detail = ""

            matched_flag_names = [
                n for n in flag_names_by_account.get(item.account_id, [])
                if _bracket_re.match(n)
            ]
            flags_text = "\n".join(matched_flag_names)

            blogger_map[name] = {
                "account_type": account_type,
                "bindings": bindings,
                "gender": gender,
                "face": face,
                "product_code": product_code,
                "core_type": core_type,
                "core_detail": core_detail,
                "flags": flags_text,
                # dates[day][platform] = [(views, likes), ...]，按视频逐条记录
                "dates": {},
            }
        dt = item.published_at or item.created_at
        if not dt:
            continue
        day = dt.strftime("%Y-%m-%d")
        per_platform = blogger_map[name]["dates"].setdefault(day, {})

        def _stat(stats, *keys):
            if stats is None:
                return None
            for k in keys:
                v = getattr(stats, k, None) if not isinstance(stats, dict) else stats.get(k)
                if v is not None:
                    return v
            return None

        for ch in item.metrics_channels or []:
            p = str(ch.platform or "").lower()
            if not p:
                continue
            views = _stat(ch.stats, "views", "view_count") or 0
            likes = _stat(ch.stats, "likes", "like_count") or 0
            per_platform.setdefault(p, []).append((int(views), int(likes)))

    # 构建 XLSX：每个博主一行，绑定多频道时按频道展开多行，其他列合并单元格
    from openpyxl import Workbook
    from openpyxl.styles import Alignment

    wb = Workbook()
    ws = wb.active
    ws.title = "数据统计"

    headers = [
        "博主名称", "账号类型", "绑定平台", "频道名称",
        "博主性别", "是否控脸", "商品码类型", "核心类型", "具体核心类别", "关联Flag",
        *dates,
    ]
    ws.append(headers)

    wrap_align = Alignment(wrap_text=True, vertical="center")
    date_col_start = 11  # 第 11 列起为日期列
    date_col_end = date_col_start + len(dates) - 1
    # 「绑定平台」「频道名称」+ 日期列均按频道展开，不参与合并
    per_channel_cols = {3, 4} | set(range(date_col_start, date_col_end + 1)) if dates else {3, 4}
    total_cols = len(headers)

    current_row = 2  # 表头是第 1 行
    for name, info in blogger_map.items():
        bindings: list[tuple[str, str, str]] = info["bindings"]
        row_count = max(1, len(bindings))

        for i in range(row_count):
            url, ch_name, platform = bindings[i] if i < len(bindings) else ("", "", "")
            row_date_cells = [
                "\n".join(
                    f"▶{v} ♥{l}"
                    for v, l in info["dates"].get(day, {}).get(platform, [])
                )
                for day in dates
            ]
            ws.append([
                name, info["account_type"], url, ch_name,
                info["gender"], info["face"], info["product_code"],
                info["core_type"], info["core_detail"], info["flags"],
                *row_date_cells,
            ])

        # 多频道时合并非频道列（日期列保持每行独立）
        if row_count > 1:
            end_row = current_row + row_count - 1
            for col in range(1, total_cols + 1):
                if col in per_channel_cols:
                    continue
                ws.merge_cells(
                    start_row=current_row, end_row=end_row,
                    start_column=col, end_column=col,
                )

        # 单元格对齐 + 换行
        for r in range(current_row, current_row + row_count):
            for col in range(1, total_cols + 1):
                ws.cell(row=r, column=col).alignment = wrap_align

        current_row += row_count

    for col in range(1, total_cols + 1):
        ws.cell(row=1, column=col).alignment = Alignment(vertical="center")

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = "数据统计"
    if date_from:
        filename += f"_{date_from}"
    if date_to and date_to != date_from:
        filename += f"_{date_to}"
    filename += ".xlsx"

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


@router.post("/video-publications/sync-metrics")
async def sync_publication_metrics(
    background_tasks: BackgroundTasks,
    platform: str | None = Query(None),
    account_id: uuid.UUID | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """先查出待同步数量立即返回，后台执行指标同步"""
    from sqlalchemy import select, func
    from app.models.video_task import VideoSubTask, VideoTask
    from app.db.session import SessionLocal

    query = VideoPublicationStatsQuery(
        platform=platform,
        account_id=account_id,
        date_from=date_from,
        date_to=date_to,
    )
    owner_id = None if current_user.is_admin else current_user.user_id

    # 先查数量
    from datetime import date as date_type
    from app.models.video_publication import VideoPublication
    stmt = (
        select(func.count())
        .select_from(VideoPublication)
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
        from datetime import datetime, timezone
        stmt = stmt.where(
            VideoPublication.completed_at >= datetime.combine(query.date_from, datetime.min.time(), tzinfo=timezone.utc)
        )
    if query.date_to is not None:
        from datetime import datetime, timezone
        next_day = date_type.fromordinal(query.date_to.toordinal() + 1)
        stmt = stmt.where(
            VideoPublication.completed_at < datetime.combine(next_day, datetime.min.time(), tzinfo=timezone.utc)
        )
    total = (await db.execute(stmt)).scalar() or 0

    async def _run():
        try:
            async with SessionLocal() as bg_db:
                service = VideoPublicationService(bg_db)
                result = await service.sync_metrics_for_stats_page(query, owner_id=owner_id)
                logger.info("sync-metrics background done: %s", result)
        except Exception:
            logger.exception("sync-metrics background failed")

    background_tasks.add_task(_run)
    return {"total": total, "message": f"后台同步 {total} 条视频数据中"}


@router.post("/video-publications/sync-kol-clicks")
async def sync_kol_link_clicks(
    background_tasks: BackgroundTasks,
    platform: str | None = Query(None),
    account_id: uuid.UUID | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """按美东自然日后台重算 KOL Link 点击数。"""
    from sqlalchemy import select, func
    from app.db.session import SessionLocal
    from app.models.account import Account
    from app.models.video_publication import VideoPublication
    from app.models.video_task import VideoSubTask, VideoTask
    from app.services.publication_metrics_scheduler import collect_kol_link_clicks

    owner_id = None if current_user.is_admin else current_user.user_id

    stmt = (
        select(func.count())
        .select_from(VideoPublication)
        .join(VideoSubTask, VideoSubTask.id == VideoPublication.sub_task_id)
        .join(VideoTask, VideoTask.id == VideoSubTask.task_id)
        .join(Account, Account.id == VideoTask.account_id)
        .where(VideoPublication.status.in_(["completed", "partial"]))
        .where(VideoPublication.completed_at.isnot(None))
        .where(Account.kol_user_id.isnot(None))
    )
    if owner_id is not None:
        stmt = stmt.where(VideoTask.owner_id == owner_id)
    if account_id is not None:
        stmt = stmt.where(VideoTask.account_id == account_id)
    if date_from is not None:
        from datetime import datetime, timezone
        stmt = stmt.where(
            VideoPublication.completed_at >= datetime.combine(date_from, datetime.min.time(), tzinfo=timezone.utc)
        )
    if date_to is not None:
        from datetime import datetime, timezone
        next_day = date.fromordinal(date_to.toordinal() + 1)
        stmt = stmt.where(
            VideoPublication.completed_at < datetime.combine(next_day, datetime.min.time(), tzinfo=timezone.utc)
        )
    total = (await db.execute(stmt)).scalar() or 0

    async def _run():
        try:
            async with SessionLocal() as bg_db:
                result = await collect_kol_link_clicks(
                    bg_db,
                    owner_id=owner_id,
                    account_id=account_id,
                    date_from=date_from,
                    date_to=date_to,
                    platform=platform,
                    force=True,
                )
                logger.info("sync-kol-clicks background done: %s", result)
        except Exception:
            logger.exception("sync-kol-clicks background failed")

    background_tasks.add_task(_run)
    return {"total": total, "message": f"后台同步 {total} 条视频 Link 点击中"}


@router.get("/video-publications/{publication_id}", response_model=VideoPublicationDetailRead)
async def get_publication(
    publication_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """获取发布任务详情"""
    from sqlalchemy import select
    from app.models.video_publication import VideoPublication

    result = await db.execute(
        select(VideoPublication).where(VideoPublication.id == publication_id)
    )
    publication = result.scalar_one_or_none()

    if not publication:
        raise HTTPException(status_code=404, detail="发布任务不存在")

    return publication


@router.get("/video-sub-tasks/{sub_task_id}/publications", response_model=list[VideoPublicationRead])
async def get_sub_task_publications(
    sub_task_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """获取子任务的所有发布记录"""
    from sqlalchemy import select
    from app.models.video_task import VideoTask, VideoSubTask

    # 验证子任务存在
    result = await db.execute(
        select(VideoSubTask).where(VideoSubTask.id == sub_task_id)
    )
    sub_task = result.scalar_one_or_none()

    if not sub_task:
        raise HTTPException(status_code=404, detail="子任务不存在")

    service = VideoPublicationService(db)
    return await service.get_publications_by_sub_task(sub_task_id)


@router.post("/video-publications/{publication_id}/sync", response_model=VideoPublicationRead)
async def sync_publication_status(
    publication_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """从 Open API 同步发布任务状态"""
    from sqlalchemy import select
    from app.models.video_publication import VideoPublication

    result = await db.execute(
        select(VideoPublication).where(VideoPublication.id == publication_id)
    )
    publication = result.scalar_one_or_none()

    if not publication:
        raise HTTPException(status_code=404, detail="发布任务不存在")

    service = VideoPublicationService(db)

    try:
        return await service.sync_publication_status(publication_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"同步状态失败: {str(e)}")


@router.post("/video-publications/{publication_id}/retry", response_model=VideoPublicationRead)
async def retry_publication(
    publication_id: uuid.UUID,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """用上次的发布参数直接重新发布（sub_task 必须处于 publish_failed 状态）"""
    owner_id = None if current_user.is_admin else current_user.user_id
    service = VideoPublicationService(db)
    try:
        return await service.retry_publication(publication_id, owner_id)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重试发布失败: {str(e)}")


class _RetryChannelPayload(BaseModel):
    platform: str
    channel_id: str


@router.post("/video-publications/{publication_id}/retry-channel", response_model=VideoPublicationRead)
async def retry_publication_channel(
    publication_id: uuid.UUID,
    payload: _RetryChannelPayload,
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """重发当前 publication 中指定 (platform, channel_id) 的失败渠道。"""
    owner_id = None if current_user.is_admin else current_user.user_id
    service = VideoPublicationService(db)
    try:
        return await service.retry_publication_channel(
            publication_id, payload.platform, payload.channel_id, owner_id,
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"重发渠道失败: {str(e)}")


@router.post("/open-api/callback/publication")
async def handle_publication_callback(
    callback_data: VideoPublicationStatusUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    接收 Open API 发布任务回调

    注意：此接口不需要认证，但需要验证签名
    """
    # TODO: 验证签名
    import logging
    logger = logging.getLogger("app.video_publications")
    logger.info(
        "Received publication callback: task_id=%s external_id=%s status=%s total=%s completed=%s failed=%s",
        callback_data.task_id,
        callback_data.external_id,
        callback_data.status,
        callback_data.total_channels,
        callback_data.completed_channels,
        callback_data.failed_channels,
    )

    service = VideoPublicationService(db)

    publication = await service.handle_callback(callback_data.dict())

    if not publication:
        import logging
        logging.getLogger("app.video_publications").warning(
            "Callback received but no matching publication found, returning 200 to avoid retry: task_id=%s external_id=%s",
            callback_data.task_id, callback_data.external_id,
        )
        return {"message": "success", "data": None}

    return {"message": "success", "data": {"publication_id": str(publication.id)}}


@router.post("/video-publications/sync-account-snapshots")
async def sync_account_snapshots(
    background_tasks: BackgroundTasks,
    account_id: uuid.UUID | None = Query(None, description="指定账号 ID，不传则计算所有账号"),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """先查出待计算账号数量立即返回，后台执行 performance_snapshot 计算"""
    from sqlalchemy import select, func
    from app.models.account import Account
    from app.db.session import SessionLocal
    from app.services.publication_metrics_scheduler import sync_account_performance_snapshots

    stmt = select(func.count()).select_from(Account)
    if account_id is not None:
        stmt = stmt.where(Account.id == account_id)
    total = (await db.execute(stmt)).scalar() or 0

    async def _run():
        try:
            async with SessionLocal() as bg_db:
                result = await sync_account_performance_snapshots(bg_db, account_id=account_id)
                logger.info("sync-account-snapshots background done: %s", result)
        except Exception:
            logger.exception("sync-account-snapshots background failed")

    background_tasks.add_task(_run)
    return {"total": total, "message": f"后台同步 {total} 个博主数据中"}


@router.get("/channels")
async def fetch_channels_unified(
    platform: str = Query(..., description="平台类型: tiktok/youtube/instagram"),
    channel_source: str = Query(..., description="频道来源: openapi（内部）| ext_pub（外部）"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=200, description="每页数量，最大 200"),
    is_active: bool | None = Query(None, description="是否只获取启用的渠道（仅内部频道有效）"),
    account_id: uuid.UUID | None = Query(None, description="当前编辑中的账号 ID，用于保留它自己已绑定的频道"),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """统一频道查询接口。

    通过 channel_source 参数区分内部（openapi）和外部（ext_pub）频道。
    两侧均过滤当前用户已被其他账号占用的频道，返回归一化结构：
    { channel_id, channel_name, username, platform, channel_source, avatar_url }
    """
    if channel_source not in ("openapi", "ext_pub"):
        raise HTTPException(status_code=422, detail="channel_source 必须为 openapi 或 ext_pub")

    service = VideoPublicationService(db)
    usage_types = settings.open_api_channel_usage_types_list or None if channel_source == "openapi" else None

    logger.info(
        "channels unified request: platform=%s source=%s page=%s page_size=%s account_id=%s user_id=%s",
        platform, channel_source, page, page_size, account_id, current_user.user_id,
    )
    try:
        response = await service.fetch_channels_unified(
            platform=platform,
            channel_source=channel_source,
            owner_id=current_user.user_id,
            page=page,
            page_size=page_size,
            is_active=is_active,
            current_account_id=account_id,
            usage_types=usage_types,
        )
        data = response.get("data", {}) if isinstance(response, dict) else {}
        logger.info(
            "channels unified response: platform=%s source=%s total=%s returned=%s",
            platform, channel_source, data.get("total"), len(data.get("items") or []),
        )
        return response
    except (httpx.ConnectTimeout, httpx.ConnectError, httpx.TimeoutException):
        logger.warning("channels unified network fallback: platform=%s source=%s", platform, channel_source)
        return {"code": 0, "message": "success", "data": {"items": [], "total": 0, "page": page, "page_size": page_size}}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("channels unified failed: platform=%s source=%s", platform, channel_source)
        raise HTTPException(status_code=500, detail=f"获取频道列表失败: {str(e)}")


@router.get("/open-api/channels")
async def fetch_channels(
    platform: str = Query(..., description="平台类型: tiktok/youtube/instagram"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量，最大 100"),
    is_active: bool | None = Query(None, description="是否只获取启用的渠道"),
    account_id: uuid.UUID | None = Query(None, description="当前编辑中的账号 ID，用于保留它自己已绑定的频道"),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取 Open API 渠道列表（代理，兼容旧版）"""
    service = VideoPublicationService(db)
    try:
        usage_types = settings.open_api_channel_usage_types_list or None
        response = await service.fetch_channels_filtered(
            platform,
            owner_id=current_user.user_id,
            page=page,
            page_size=page_size,
            is_active=is_active,
            current_account_id=account_id,
            usage_types=usage_types,
        )
        return response
    except (httpx.ConnectTimeout, httpx.ConnectError, httpx.TimeoutException):
        return {"code": 0, "message": "success", "data": {"items": [], "total": 0, "page": page, "page_size": page_size}}
    except Exception as e:
        logger.exception("Open API channels proxy failed: platform=%s", platform)
        raise HTTPException(status_code=500, detail=f"获取渠道列表失败: {str(e)}")


@router.get("/ext-pub/platform-accounts")
async def fetch_ext_pub_platform_accounts(
    platform: str | None = Query(None, description="平台过滤：tiktok/youtube/instagram"),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取外部发布 API 的平台账号列表（代理，兼容旧版）"""
    service = VideoPublicationService(db)
    try:
        result = await service.ext_pub.fetch_platform_accounts(platform=platform)
        return result
    except (httpx.ConnectTimeout, httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError):
        logger.warning("ExtPubAPI platform-accounts proxy fallback: platform=%s", platform)
        return {"code": 200, "message": "Success", "data": {"items": [], "total": 0}}
    except Exception:
        logger.exception("ExtPubAPI platform-accounts proxy failed")
        return {"code": 200, "message": "Success", "data": {"items": [], "total": 0}}


@router.get("/open-api/upload/metrics")
async def get_upload_metrics(
    task_id: str | None = Query(None, description="Open API 任务 ID"),
    external_id: str | None = Query(None, description="外部系统 ID"),
    current_user: TokenData = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """查询上传任务各渠道视频指标（代理到 Open API）"""
    if not task_id and not external_id:
        raise HTTPException(status_code=400, detail="task_id 和 external_id 至少提供一个")

    service = VideoPublicationService(db)
    try:
        return await service.open_api.fetch_upload_metrics(task_id=task_id, external_id=external_id)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"Open API 返回错误: {e.response.text}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"查询指标失败: {str(e)}")


@router.post("/open-api/health-check")
async def open_api_health_check(
    db: AsyncSession = Depends(get_db),
):
    """检查 Open API 服务健康状态"""
    service = VideoPublicationService(db)

    try:
        return await service.open_api.health_check()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Open API 服务不可用: {str(e)}")
