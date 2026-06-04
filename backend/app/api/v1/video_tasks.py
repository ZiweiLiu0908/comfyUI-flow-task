from __future__ import annotations

import asyncio
import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenData, get_current_user, get_optional_user
from app.db.session import get_db
from app.models.video_ai_template import VideoAITemplate
from app.models.tag import Tag, VideoSourceTag
from app.models.video_source import VideoSource
from app.schemas.video_ai_template import VideoSourceSummary
from app.schemas.video_task import (
    OperatorStatItem,
    VideoSubTaskListPage,
    VideoSubTaskNoteUpdate,
    VideoSubTaskRead,
    VideoSubTaskStatusUpdate,
    VideoSubTaskWithTaskPage,
    VideoSubTaskWithTaskRead,
    VideoTaskCreate,
    VideoTaskDetailRead,
    VideoTaskListItem,
    VideoTaskListPage,
    VideoTaskNavRead,
    VideoTaskRead,
    VideoTaskStateRead,
)
from app.services.video_task_service import VideoTaskService

router = APIRouter(prefix="/video-tasks", tags=["video-tasks"])


async def _load_template_tags_map(
    session: AsyncSession,
    template_ids: list[uuid.UUID | None],
) -> dict[uuid.UUID, list]:
    from app.schemas.video_ai_template import TagRead

    valid_ids = [tpl_id for tpl_id in template_ids if tpl_id is not None]
    tags_map: dict[uuid.UUID, list[TagRead]] = {tpl_id: [] for tpl_id in valid_ids}
    if not valid_ids:
        return tags_map

    stmt = (
        select(VideoSourceTag.video_ai_template_id, Tag)
        .join(Tag, Tag.id == VideoSourceTag.tag_id)
        .where(VideoSourceTag.video_ai_template_id.in_(valid_ids))
        .order_by(Tag.name.asc())
    )
    for tpl_id, tag in (await session.execute(stmt)).all():
        if tpl_id in tags_map:
            tags_map[tpl_id].append(TagRead.model_validate(tag))
    return tags_map


def _get_creator_id(current_user: TokenData = Depends(get_current_user)) -> uuid.UUID:
    return current_user.user_id


def _get_query_owner_id(current_user: TokenData = Depends(get_current_user)) -> uuid.UUID | None:
    return None if current_user.is_admin else current_user.user_id


# ── Parent task endpoints ──────────────────────────────────────────────────────

@router.post("", status_code=status.HTTP_201_CREATED, response_model=VideoTaskDetailRead)
async def create_video_task(
    payload: VideoTaskCreate,
    creator_id: uuid.UUID = Depends(_get_creator_id),
    session: AsyncSession = Depends(get_db),
) -> Any:
    svc = VideoTaskService(db=session)
    task = await svc.create_task(
        account_id=payload.account_id,
        template_id=payload.template_id,
        final_prompt=payload.final_prompt,
        duration=payload.duration,
        shots=payload.shots,
        user_id=creator_id,
    )
    return task


def _resolve_owner_id(
    owner_id: uuid.UUID | None = Query(default=None, description="按所属用户筛选（外部API可传）"),
    current_user: TokenData | None = Depends(get_optional_user),
) -> uuid.UUID | None:
    """External API can pass owner_id; with token, non-admin overrides to own user_id."""
    if owner_id is not None:
        # External API call with explicit owner_id
        if current_user is not None and not current_user.is_admin:
            return current_user.user_id
        return owner_id
    if current_user is not None:
        return None if current_user.is_admin else current_user.user_id
    return None


@router.get("", response_model=VideoTaskListPage)
async def list_video_tasks(
    target_date: date | None = Query(default=None),
    account_id: uuid.UUID | None = Query(default=None),
    status: str | None = Query(default=None),
    tiktok_blogger_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=9999),
    owner_id: uuid.UUID | None = Depends(_resolve_owner_id),
    session: AsyncSession = Depends(get_db),
) -> Any:
    svc = VideoTaskService(db=session)
    enriched, total = await svc.get_tasks_with_names(
        target_date, owner_id, account_id, status, tiktok_blogger_id,
        page=page, page_size=page_size,
    )
    tags_map = await _load_template_tags_map(session, [item["task"].template_id for item in enriched])
    # 一次性批量签 GCS URL（外部 API 给其它团队调用，必须返回可播链）
    from app.utils.gcs_signing import serialize_sub_tasks
    all_subs = [s for item in enriched for s in item["sub_tasks"]]
    sub_reads = await serialize_sub_tasks(session, all_subs)
    sub_reads_by_id = {r.id: r for r in sub_reads}

    items = []
    for item in enriched:
        task = item["task"]
        data = VideoTaskListItem.model_validate({
            **VideoTaskRead.model_validate(task).model_dump(),
            "sub_tasks": [sub_reads_by_id[s.id] for s in item["sub_tasks"]],
            "sub_tasks_done": item["sub_tasks_done"],
            "account_name": item["account_name"],
            "template_title": item["template_title"],
            "tags": tags_map.get(task.template_id, []) if task.template_id else [],
            "original_video": None,
        })
        items.append(data)
    return VideoTaskListPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/download-latest-published")
async def download_latest_published_videos(
    account_ids: str | None = Query(default=None, description="逗号分隔的 account_id 列表，为空则全量"),
    owner_id: uuid.UUID | None = Depends(_get_query_owner_id),
    session: AsyncSession = Depends(get_db),
):
    """下载每个账号最新已发布的视频，含 caption/hashtag txt，打包成 ZIP 返回。"""
    from fastapi import HTTPException
    from fastapi.responses import StreamingResponse

    parsed_account_ids: list[uuid.UUID] | None = None
    if account_ids:
        try:
            parsed_account_ids = [uuid.UUID(a.strip()) for a in account_ids.split(",") if a.strip()]
        except ValueError:
            raise HTTPException(status_code=400, detail="account_ids 格式错误")

    svc = VideoTaskService(db=session)
    buf, filename = await svc.download_latest_published_videos(owner_id, account_ids=parsed_account_ids)
    if buf is None:
        raise HTTPException(status_code=404, detail="没有已发布的视频")
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/stats", response_model=dict[str, int])
async def get_video_task_stats(
    target_date: date | None = Query(default=None),
    tiktok_blogger_id: uuid.UUID | None = Query(default=None),
    owner_id: uuid.UUID | None = Depends(_get_query_owner_id),
    session: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    """Return count per status, optionally filtered by target_date and tiktok_blogger_id."""
    from sqlalchemy import func, select
    from app.models.video_task import VideoTask
    from app.models.video_ai_template import VideoAITemplate

    stmt = select(
        VideoTask.status,
        func.count(VideoTask.id).label("cnt"),
    ).group_by(VideoTask.status)
    if owner_id is not None:
        stmt = stmt.where(VideoTask.owner_id == owner_id)
    if target_date is not None:
        stmt = stmt.where(VideoTask.target_date == target_date)
    if tiktok_blogger_id is not None:
        stmt = stmt.join(VideoAITemplate, VideoTask.template_id == VideoAITemplate.id)
        stmt = stmt.where(VideoAITemplate.tiktok_blogger_id == tiktok_blogger_id)
    rows = (await session.execute(stmt)).all()
    result = {str(row[0]): row[1] for row in rows}

    # Extra virtual counter: tasks with updated prompt
    from sqlalchemy import func as _func
    prompt_stmt = select(_func.count(VideoTask.id)).where(VideoTask.is_prompt_updated == True)  # noqa: E712
    if owner_id is not None:
        prompt_stmt = prompt_stmt.where(VideoTask.owner_id == owner_id)
    if target_date is not None:
        prompt_stmt = prompt_stmt.where(VideoTask.target_date == target_date)
    if tiktok_blogger_id is not None:
        prompt_stmt = prompt_stmt.join(VideoAITemplate, VideoTask.template_id == VideoAITemplate.id)
        prompt_stmt = prompt_stmt.where(VideoAITemplate.tiktok_blogger_id == tiktok_blogger_id)
    result["prompt_updated"] = (await session.execute(prompt_stmt)).scalar_one()

    return result



# ── Batch operations by date ───────────────────────────────────────────────────

import logging
from app.db.session import SessionLocal

logger = logging.getLogger(__name__)

async def _bg_upload_tasks(target_date: date, owner_id: uuid.UUID | None):
    async with SessionLocal() as session:
        svc = VideoTaskService(db=session)
        try:
            gcs_url, task_count, subtask_count = await svc.upload_tasks(target_date, owner_id)
            logger.info(f"Background upload tasks completed for {target_date}: {task_count} tasks, {subtask_count} subtasks. GCS URL: {gcs_url}")
        except Exception as e:
            logger.error(f"Background upload tasks failed for {target_date}: {e}")

async def _bg_fetch_results(target_date: date, owner_id: uuid.UUID | None):
    async with SessionLocal() as session:
        svc = VideoTaskService(db=session)
        try:
            res = await svc.fetch_results(target_date, owner_id)
            logger.info(f"Background fetch results completed for {target_date}: {res}")
        except Exception as e:
            logger.error(f"Background fetch results failed for {target_date}: {e}")

@router.get("/daily/{target_date}/download-videos")
async def download_videos(
    target_date: date,
    owner_id: uuid.UUID | None = Depends(_get_query_owner_id),
    session: AsyncSession = Depends(get_db),
):
    """下载指定日期所有已选定视频，按账号分文件夹打包成 ZIP 返回。"""
    from fastapi import HTTPException
    from fastapi.responses import StreamingResponse

    svc = VideoTaskService(db=session)
    buf, filename = await svc.download_videos(target_date, owner_id)
    if buf is None:
        raise HTTPException(status_code=404, detail="该日期没有已发布的视频")
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/daily/{target_date}/upload", status_code=status.HTTP_200_OK)
async def upload_video_tasks(
    target_date: date,
    background_tasks: BackgroundTasks,
    owner_id: uuid.UUID | None = Depends(_get_query_owner_id),
) -> dict:
    background_tasks.add_task(_bg_upload_tasks, target_date, owner_id)
    return {
        "status": "success",
        "message": "后台上传任务已启动，请稍后刷新查看状态",
    }


@router.post("/daily/{target_date}/fetch-results", status_code=status.HTTP_200_OK)
async def fetch_video_task_results(
    target_date: date,
    background_tasks: BackgroundTasks,
    owner_id: uuid.UUID | None = Depends(_get_query_owner_id),
) -> dict:
    background_tasks.add_task(_bg_fetch_results, target_date, owner_id)
    return {
        "status": "success",
        "message": "后台获取结果任务已启动，请稍后刷新查看状态",
    }


# ── Sub-task endpoints ─────────────────────────────────────────────────────────

@router.get("/subtasks", response_model=VideoSubTaskListPage)
async def list_reviewing_subtasks(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    owner_id: uuid.UUID | None = Depends(_get_query_owner_id),
    session: AsyncSession = Depends(get_db),
) -> Any:
    """获取待决策（reviewing）状态的子任务分页列表"""
    svc = VideoTaskService(db=session)
    items, total = await svc.list_reviewing_subtasks(owner_id, page=page, page_size=page_size)
    from app.utils.gcs_signing import serialize_sub_tasks
    return VideoSubTaskListPage(
        items=await serialize_sub_tasks(session, items),
        total=total,
        page=page,
        page_size=page_size,
    )

@router.get("/subtasks/by-account", response_model=VideoSubTaskWithTaskPage)
async def list_subtasks_by_account(
    account_id: uuid.UUID = Query(...),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=200),
    owner_id: uuid.UUID | None = Depends(_get_query_owner_id),
    session: AsyncSession = Depends(get_db),
) -> Any:
    """按账号+子任务状态分页查询 sub_tasks，附带父任务摘要信息。供 AccountDetailView 各 tab 独立分页使用。"""
    from sqlalchemy import func, select
    from app.models.video_task import VideoSubTask, VideoTask
    from app.models.video_ai_template import VideoAITemplate
    from app.models.video_publication import VideoPublication
    from app.schemas.video_task import TaskSummaryForSub

    base = (
        select(VideoSubTask)
        .join(VideoTask, VideoSubTask.task_id == VideoTask.id)
        .where(VideoTask.account_id == account_id)
        .where(VideoSubTask.status != "abandoned")
    )
    if owner_id is not None:
        base = base.where(VideoTask.owner_id == owner_id)
    if status:
        base = base.where(VideoSubTask.status == status)

    # queued 按 queue_order 排序；published 按 video_publication.completed_at 倒序；
    # pending_publish 按权重分；其他按创建时间倒序
    if status == "queued":
        base = base.order_by(VideoSubTask.queue_order.asc().nulls_last())
    elif status == "pending_publish":
        base = base.order_by(VideoSubTask.weighted_total_score.desc().nulls_last())
    elif status == "published":
        base = base.outerjoin(
            VideoPublication, VideoPublication.sub_task_id == VideoSubTask.id
        ).order_by(
            VideoPublication.completed_at.desc().nulls_last(),
            VideoSubTask.created_at.desc(),
        )
    else:
        base = base.order_by(VideoSubTask.created_at.desc())

    total: int = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()

    rows = (await session.execute(base.offset((page - 1) * page_size).limit(page_size))).scalars().all()

    # Batch-load parent tasks
    task_ids = list({s.task_id for s in rows})
    task_map: dict[uuid.UUID, VideoTask] = {}
    if task_ids:
        tpl_map: dict[uuid.UUID, str] = {}
        tasks_rows = (await session.execute(select(VideoTask).where(VideoTask.id.in_(task_ids)))).scalars().all()
        tpl_ids = list({t.template_id for t in tasks_rows if t.template_id})
        if tpl_ids:
            for tpl_id, title in (await session.execute(
                select(VideoAITemplate.id, VideoAITemplate.title).where(VideoAITemplate.id.in_(tpl_ids))
            )).all():
                tpl_map[tpl_id] = title
        for t in tasks_rows:
            task_map[t.id] = t
            t._template_title = tpl_map.get(t.template_id)  # type: ignore[attr-defined]

    # 一次性批量签 GCS URL
    from app.utils.gcs_signing import serialize_sub_tasks
    sub_reads = await serialize_sub_tasks(session, rows)
    sub_reads_by_id = {r.id: r for r in sub_reads}

    items = []
    for sub in rows:
        task = task_map.get(sub.task_id)
        task_summary = TaskSummaryForSub(
            id=task.id,
            target_date=task.target_date,
            prompt=task.prompt,
            template_title=getattr(task, "_template_title", None),
        ) if task else None
        if task_summary is None:
            continue
        item = VideoSubTaskWithTaskRead(
            **sub_reads_by_id[sub.id].model_dump(),
            task=task_summary,
        )
        items.append(item)

    return VideoSubTaskWithTaskPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/subtasks/by-account/counts", response_model=dict[str, int])
async def count_subtasks_by_account(
    account_id: uuid.UUID = Query(...),
    owner_id: uuid.UUID | None = Depends(_get_query_owner_id),
    session: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    """返回指定账号各 sub_task status 的数量（排除 abandoned）。"""
    from sqlalchemy import func, select
    from app.models.video_task import VideoSubTask, VideoTask

    stmt = (
        select(VideoSubTask.status, func.count(VideoSubTask.id).label("cnt"))
        .join(VideoTask, VideoSubTask.task_id == VideoTask.id)
        .where(VideoTask.account_id == account_id)
        .where(VideoSubTask.status != "abandoned")
        .group_by(VideoSubTask.status)
    )
    if owner_id is not None:
        stmt = stmt.where(VideoTask.owner_id == owner_id)

    rows = (await session.execute(stmt)).all()
    return {row.status: row.cnt for row in rows}


@router.post("/daily/{target_date}/route-stashed", status_code=202)
async def batch_route_stashed(
    target_date: date,
    background_tasks: BackgroundTasks,
    owner_id: uuid.UUID | None = Depends(_get_query_owner_id),
) -> Any:
    """将指定日期所有暂存（stashed）的父任务按评分规则批量路由到队列或废弃（后台异步执行）"""
    from app.db.session import SessionLocal

    async def _run() -> None:
        async with SessionLocal() as bg_session:
            svc = VideoTaskService(db=bg_session)
            await svc.batch_route_stashed(target_date, owner_id)

    background_tasks.add_task(_run)
    return {"status": "accepted"}


@router.post("/daily/{target_date}/retry-templates", status_code=status.HTTP_202_ACCEPTED)
async def retry_daily_task_templates(
    target_date: date,
    task_status: str | None = Query(default=None, alias="status"),
    owner_id: uuid.UUID | None = Depends(_get_query_owner_id),
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """daily-tasks 页「一键重试」专用端点。

    **走 soft retry**：只从阶段 2.5 重挑 panel + 跑下游，不重抽帧/不重识别穿搭/不重生 lookbook；
    池子耗尽或模板无 lookbook 时自动 fallback 到 hard restart。

    本端点是 task 层 → 模板层的单向注入：
      1) 查 video_tasks 当天关联的所有模板（可选按 status 过滤，仅 pending / generating）
      2) 构造 abandon_map（模板失败 → 关联 task 标 abandoned）
      3) 构造 cta_map（任一关联 task 是 cta=True 即视为 True）
      4) 调 batch_soft_retry_templates 把这两个 map 注入流水线 enqueue

    AI 模板侧不会反查 task；cta / abandon 信息由本端点显式传入。
    """
    from app.models.video_task import VideoTask
    from app.services.video_ai_service import batch_soft_retry_templates

    if task_status is not None and task_status not in ("pending", "generating"):
        raise HTTPException(
            status_code=400,
            detail="status 仅支持 pending / generating，或不传以重试全部",
        )

    stmt = select(VideoTask.id, VideoTask.template_id, VideoTask.cta).where(
        VideoTask.target_date == target_date,
        VideoTask.template_id.is_not(None),
        VideoTask.ai_retry_done.is_not(True),  # 跳过已被 AI 模板处理完成的任务
    )
    if task_status:
        stmt = stmt.where(VideoTask.status == task_status)
    if owner_id is not None:
        stmt = stmt.where(VideoTask.owner_id == owner_id)
    rows = (await session.execute(stmt)).all()

    abandon_map: dict[str, list[str]] = {}
    cta_map: dict[str, bool] = {}
    for task_id, tpl_id, task_cta in rows:
        tpl_str = str(tpl_id)
        abandon_map.setdefault(tpl_str, []).append(str(task_id))
        if task_cta:
            cta_map[tpl_str] = True
        else:
            cta_map.setdefault(tpl_str, False)

    # 软重试：复用 lookbook + 重新挑下一个未用 panel + 跑下游；
    # 池子耗尽 / 无 lookbook 的模板会 fallback 到 hard restart
    asyncio.create_task(batch_soft_retry_templates(
        template_ids=list(abandon_map.keys()),
        abandon_task_ids_on_fail=abandon_map or None,
        cta_map=cta_map or None,
    ))
    return {"status": "accepted"}


@router.get("/operator-stats", response_model=list[OperatorStatItem])
async def get_operator_stats(
    target_date: date | None = Query(default=None),
    owner_id: uuid.UUID | None = Depends(_get_query_owner_id),
    session: AsyncSession = Depends(get_db),
) -> Any:
    """返回各审核人的处理数量和对应子任务列表"""
    svc = VideoTaskService(db=session)
    return await svc.get_operator_stats(owner_id, target_date)


@router.patch("/subtasks/{sub_task_id}/status", response_model=VideoSubTaskRead)
async def patch_sub_task_status(
    sub_task_id: uuid.UUID,
    payload: VideoSubTaskStatusUpdate,
    owner_id: uuid.UUID | None = Depends(_get_query_owner_id),
    session: AsyncSession = Depends(get_db),
) -> Any:
    svc = VideoTaskService(db=session)
    sub = await svc.patch_sub_task_status(
        sub_task_id=sub_task_id,
        owner_id=owner_id,
        new_status=payload.status,
        result_video_url=payload.result_video_url,
        selected=payload.selected,
    )
    from app.utils.gcs_signing import serialize_sub_task
    return await serialize_sub_task(session, sub)


@router.patch("/subtasks/{sub_task_id}/note", response_model=VideoSubTaskRead)
async def update_sub_task_note(
    sub_task_id: uuid.UUID,
    payload: VideoSubTaskNoteUpdate,
    owner_id: uuid.UUID | None = Query(default=None, description="按所属用户筛选（外部API可传）"),
    current_user: TokenData | None = Depends(get_optional_user),
    session: AsyncSession = Depends(get_db),
) -> Any:
    """审核人填写备注、穿帮信息和多维度评分，原子地将状态从 reviewing → stashed。
    有 token 时 operator 取登录用户名；无 token 时从请求体 operator 字段获取。
    owner_id 支持外部 API 传入筛选，规则同列表接口。
    """
    from fastapi import HTTPException as _HTTPException
    operator = current_user.username if current_user else payload.operator
    if not operator:
        raise _HTTPException(status_code=422, detail="无 token 时 operator 字段为必填")

    # Resolve owner_id: external API can pass explicitly; token non-admin overrides
    if owner_id is not None:
        if current_user is not None and not current_user.is_admin:
            owner_id = current_user.user_id
    else:
        owner_id = None if current_user is None else (None if current_user.is_admin else current_user.user_id)

    svc = VideoTaskService(db=session)
    sub = await svc.update_sub_task_note(
        sub_task_id,
        owner_id,
        operator=operator,
        target_status=payload.status,
        manual_note=payload.manual_note,
        has_ng=payload.has_ng,
        ng_timestamps=payload.ng_timestamps,
        dimension_scores=payload.dimension_scores,
    )
    from app.utils.gcs_signing import serialize_sub_task
    return await serialize_sub_task(session, sub)


@router.delete("/subtasks/{sub_task_id}", status_code=status.HTTP_200_OK)
async def delete_sub_task(
    sub_task_id: uuid.UUID,
    owner_id: uuid.UUID | None = Depends(_get_query_owner_id),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """删除待发布的子任务，若父任务无剩余有效子任务则一并删除"""
    svc = VideoTaskService(db=session)
    return await svc.delete_sub_task(sub_task_id, owner_id)


@router.post("/subtasks/{sub_task_id}/rollback", response_model=VideoSubTaskRead)
async def rollback_sub_task_status(
    sub_task_id: uuid.UUID,
    owner_id: uuid.UUID | None = Depends(_get_query_owner_id),
    session: AsyncSession = Depends(get_db),
) -> Any:
    svc = VideoTaskService(db=session)
    sub = await svc.rollback_sub_task_status(sub_task_id, owner_id)
    from app.utils.gcs_signing import serialize_sub_task
    return await serialize_sub_task(session, sub)


@router.post("/subtasks/{sub_task_id}/enqueue", response_model=VideoSubTaskRead)
async def enqueue_sub_task(
    sub_task_id: uuid.UUID,
    owner_id: uuid.UUID | None = Depends(_get_query_owner_id),
    session: AsyncSession = Depends(get_db),
) -> Any:
    """将子任务从 stashed 状态移到 queued 状态，进入发布队列"""
    svc = VideoTaskService(db=session)
    sub = await svc.enqueue_sub_task(sub_task_id, owner_id)
    from app.utils.gcs_signing import serialize_sub_task
    return await serialize_sub_task(session, sub)


@router.post("/subtasks/{sub_task_id}/dequeue", response_model=VideoSubTaskRead)
async def dequeue_sub_task(
    sub_task_id: uuid.UUID,
    owner_id: uuid.UUID | None = Depends(_get_query_owner_id),
    session: AsyncSession = Depends(get_db),
) -> Any:
    """将子任务从 queued 状态移回 stashed 状态"""
    svc = VideoTaskService(db=session)
    sub = await svc.dequeue_sub_task(sub_task_id, owner_id)
    from app.utils.gcs_signing import serialize_sub_task
    return await serialize_sub_task(session, sub)


@router.post("/subtasks/{sub_task_id}/regenerate-publish-meta", response_model=VideoSubTaskRead)
async def regenerate_publish_meta(
    sub_task_id: uuid.UUID,
    owner_id: uuid.UUID | None = Depends(_get_query_owner_id),
    session: AsyncSession = Depends(get_db),
) -> Any:
    """重新触发 AI 预生成发布标题（仅限 queued 状态，使用视频输入并失败兜底）"""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.video_task import VideoSubTask, VideoTask

    result = await session.execute(
        select(VideoSubTask)
        .where(VideoSubTask.id == sub_task_id)
        .options(selectinload(VideoSubTask.task))
    )
    sub = result.scalar_one_or_none()
    if sub is None:
        raise HTTPException(status_code=404, detail="子任务不存在")
    if owner_id is not None and sub.task.owner_id != owner_id:
        raise HTTPException(status_code=404, detail="子任务不存在")
    if sub.status != "queued":
        raise HTTPException(status_code=422, detail="只有队列中的子任务才能重新生成标题")

    # 重置为 pending，直接后台生成（不入队，优先执行）；保留已分配的商品口令，避免重生时浪费或更换口令
    existing_meta = sub.publish_meta if isinstance(sub.publish_meta, dict) else {}
    pending_meta = {"status": "pending"}
    if existing_meta.get("promotion_code"):
        pending_meta["promotion_code"] = existing_meta["promotion_code"]
    sub.publish_meta = pending_meta
    await session.commit()
    await session.refresh(sub)

    from app.services.publish_meta_service import _process_publish_meta
    asyncio.create_task(
        _process_publish_meta(
            sub.id,
            input_mode="video",
            fallback_to_default=True,
        )
    )

    from app.utils.gcs_signing import serialize_sub_task
    return await serialize_sub_task(session, sub)


@router.patch("/subtasks/queue-order", status_code=status.HTTP_200_OK)
async def update_queue_order(
    payload: list[dict],
    owner_id: uuid.UUID | None = Depends(_get_query_owner_id),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """批量更新发布队列顺序，payload: [{id: uuid, queue_order: int}]"""
    from fastapi import HTTPException
    from app.models.video_task import VideoSubTask
    from sqlalchemy import select

    for item in payload:
        sub_id = uuid.UUID(item["id"])
        order = int(item["queue_order"])
        q = select(VideoSubTask).where(VideoSubTask.id == sub_id)
        if owner_id is not None:
            from app.models.video_task import VideoTask
            from sqlalchemy.orm import selectinload
            q = q.options(selectinload(VideoSubTask.task))
        sub = (await session.execute(q)).scalar_one_or_none()
        if not sub:
            raise HTTPException(status_code=404, detail=f"子任务 {sub_id} 不存在")
        if owner_id is not None and sub.task.owner_id != owner_id:
            raise HTTPException(status_code=403, detail="无权操作")
        sub.queue_order = order

    await session.commit()
    return {"status": "ok"}


# ── Dynamic {task_id} routes — MUST be after all fixed-path routes ────────────

@router.get("/{task_id}", response_model=VideoTaskDetailRead)
async def get_video_task(
    task_id: uuid.UUID,
    owner_id: uuid.UUID | None = Depends(_get_query_owner_id),
    session: AsyncSession = Depends(get_db),
) -> Any:
    svc = VideoTaskService(db=session)
    item = await svc.get_task_detail(task_id, owner_id)
    data = VideoTaskDetailRead.model_validate(item["task"])
    data.account_name = item["account_name"]
    data.template_title = item["template_title"]
    if data.template_id:
        tags_map = await _load_template_tags_map(session, [data.template_id])
        data.tags = tags_map.get(data.template_id, [])
        tpl = await session.get(VideoAITemplate, data.template_id)
        if tpl and tpl.video_source_id:
            vs = await session.get(VideoSource, tpl.video_source_id)
            if vs:
                data.original_video = VideoSourceSummary.model_validate(vs)
    return data


@router.delete("/batch", status_code=status.HTTP_200_OK)
async def batch_delete_pending_generating(
    target_date: date = Query(..., description="目标日期，格式 YYYY-MM-DD"),
    task_status: str | None = Query(None, description="要删除的状态：pending 或 generating，不传则两者都删"),
    owner_id: uuid.UUID | None = Depends(_get_query_owner_id),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """删除指定日期下 pending / generating 状态的任务及其子任务。"""
    svc = VideoTaskService(db=session)
    deleted = await svc.batch_delete_pending_generating(target_date, owner_id, status=task_status)
    return {"status": "success", "deleted": deleted, "message": f"已删除 {deleted} 个任务"}


@router.delete("/{task_id}", status_code=status.HTTP_200_OK)
async def delete_video_task(
    task_id: uuid.UUID,
    owner_id: uuid.UUID | None = Depends(_get_query_owner_id),
    session: AsyncSession = Depends(get_db),
) -> dict:
    svc = VideoTaskService(db=session)
    await svc.delete_task(task_id, owner_id)
    return {"status": "success", "message": "删除成功"}


@router.get("/{task_id}/state", response_model=VideoTaskStateRead)
async def get_video_task_state(
    task_id: uuid.UUID,
    owner_id: uuid.UUID | None = Depends(_get_query_owner_id),
    session: AsyncSession = Depends(get_db),
) -> Any:
    """Lightweight endpoint for polling task and sub-task statuses."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from fastapi import HTTPException
    from app.models.video_task import VideoTask

    q = (
        select(VideoTask)
        .where(VideoTask.id == task_id)
        .options(selectinload(VideoTask.sub_tasks))
    )
    if owner_id is not None:
        q = q.where(VideoTask.owner_id == owner_id)
    task = (await session.execute(q)).scalar_one_or_none()
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

    return task


@router.get("/{task_id}/navigation", response_model=VideoTaskNavRead)
async def get_video_task_navigation(
    task_id: uuid.UUID,
    owner_id: uuid.UUID | None = Depends(_get_query_owner_id),
    session: AsyncSession = Depends(get_db),
) -> Any:
    """Return prev/next task and prev/next blogger task for navigation without full list fetches."""
    svc = VideoTaskService(db=session)
    raw = await svc.get_task_navigation(task_id, owner_id)

    def _task_item(t):
        if t is None:
            return None
        from app.schemas.video_task import TaskNavItem
        return TaskNavItem(id=t.id, status=t.status)

    def _blogger_item(row):
        if row is None:
            return None
        from app.schemas.video_task import TaskNavItem
        t, acc = row.VideoTask, row.Account
        return TaskNavItem(id=t.id, status=t.status, account_id=acc.id, account_name=acc.account_name)

    return VideoTaskNavRead(
        position=raw["position"],
        total=raw["total"],
        selected_count=raw["selected_count"],
        prev_task=_task_item(raw["prev_task"]),
        next_task=_task_item(raw["next_task"]),
        prev_blogger_task=_blogger_item(raw["prev_blogger_task"]),
        next_blogger_task=_blogger_item(raw["next_blogger_task"]),
    )
