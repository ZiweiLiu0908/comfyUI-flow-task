from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.external_supplement_request import ExternalSupplementRequest
from app.models.external_supplement_request_item import ExternalSupplementRequestItem


TERMINAL_STATUSES = {"completed", "failed", "skipped"}


def resolve_item_status(
    *,
    target_count: int,
    completed_count: int,
    processing_count: int,
    final_received: bool,
    force_failed: bool = False,
) -> str:
    """推算单个 item 的状态。

    设计原则：
    - completed_count >= target_count → completed（达到目标数）
    - final 已收到 且 processing 已清零 → 所有异步任务都已结案
        - 有任何视频成功入库 → completed（AI 审核/分类过滤掉部分是正常业务行为）
        - 一条都没入库 → failed
    - 其余情况 → running（仍在处理中）
    """
    if force_failed:
        return "failed"
    if completed_count >= target_count > 0:
        return "completed"
    if final_received and processing_count <= 0:
        # 所有异步任务已结案：有任何成功入库视为正常完成
        return "completed" if completed_count > 0 else "failed"
    return "running"


def item_status_payload(item: ExternalSupplementRequestItem) -> dict[str, Any]:
    target = int(item.target_video_count or 0)
    completed = int(item.completed_count or 0)
    target_unused = item.target_unused_template_count
    current_unused = item.current_unused_template_count
    return {
        "request_id": str(item.request_id),
        "account_id": str(item.account_id),
        "mode": item.mode,
        "status": item.status,
        "target_count": target,
        "completed_count": completed,
        "remaining_count": max(target - completed, 0),
        "target_unused_template_count": int(target_unused) if target_unused is not None else target,
        "initial_unused_template_count": (
            int(item.initial_unused_template_count)
            if item.initial_unused_template_count is not None
            else None
        ),
        "current_unused_template_count": int(current_unused) if current_unused is not None else None,
        "requested_video_count": (
            int(item.requested_video_count)
            if item.requested_video_count is not None
            else target
        ),
        "round_index": int(item.round_index or 1),
        "schedule_run_id": str(item.schedule_run_id) if item.schedule_run_id else None,
        "failed_count": int(item.failed_count or 0),
        "rejected_count": int(item.rejected_count or 0),
        "duplicated_count": int(item.duplicated_count or 0),
        "processing_count": int(item.processing_count or 0),
        "error_message": item.error_message,
        "updated_at": item.updated_at,
    }


async def create_request_items(
    session: AsyncSession,
    *,
    request_id: uuid.UUID,
    owner_id: uuid.UUID | None,
    mode: str,
    target_video_count: int,
    payload_items: list[dict],
    skipped_account_ids: list[str],
    item_context_by_account: dict[str, dict[str, Any]] | None = None,
) -> None:
    item_context_by_account = item_context_by_account or {}
    for item in payload_items:
        account_id = uuid.UUID(str(item["account_id"]))
        blogger = item.get("blogger") or {}
        ctx = item_context_by_account.get(str(account_id), {})
        session.add(ExternalSupplementRequestItem(
            request_id=request_id,
            owner_id=owner_id,
            account_id=account_id,
            mode=mode,
            blogger_handle=blogger.get("handle"),
            target_video_count=target_video_count,
            target_unused_template_count=ctx.get("target_unused_template_count"),
            initial_unused_template_count=ctx.get("initial_unused_template_count"),
            current_unused_template_count=ctx.get("current_unused_template_count"),
            requested_video_count=ctx.get("requested_video_count", target_video_count),
            round_index=int(ctx.get("round_index") or 1),
            schedule_run_id=(
                uuid.UUID(str(ctx["schedule_run_id"]))
                if ctx.get("schedule_run_id")
                else None
            ),
            status="running",
        ))
    for aid in skipped_account_ids:
        ctx = item_context_by_account.get(str(aid), {})
        session.add(ExternalSupplementRequestItem(
            request_id=request_id,
            owner_id=owner_id,
            account_id=uuid.UUID(str(aid)),
            mode=mode,
            target_video_count=target_video_count,
            target_unused_template_count=ctx.get("target_unused_template_count"),
            initial_unused_template_count=ctx.get("initial_unused_template_count"),
            current_unused_template_count=ctx.get("current_unused_template_count"),
            requested_video_count=ctx.get("requested_video_count", target_video_count),
            round_index=int(ctx.get("round_index") or 1),
            schedule_run_id=(
                uuid.UUID(str(ctx["schedule_run_id"]))
                if ctx.get("schedule_run_id")
                else None
            ),
            status="skipped",
            error_message="无绑定博主 handle",
            final_received=True,
        ))


async def mark_callback_seen(
    session: AsyncSession,
    *,
    request_id: uuid.UUID,
    account_id: uuid.UUID,
    scheduled_count: int,
    duplicated_count: int,
    rejected_count: int,
    final_received: bool,
    error_message: str | None = None,
    _req: ExternalSupplementRequest | None = None,
) -> None:
    item = await _get_item_for_update(session, request_id, account_id)
    if item is None:
        return
    item.processing_count = max(0, int(item.processing_count or 0) + scheduled_count)
    item.duplicated_count = int(item.duplicated_count or 0) + duplicated_count
    item.rejected_count = int(item.rejected_count or 0) + rejected_count
    item.failed_count = int(item.failed_count or 0) + rejected_count
    item.final_received = bool(item.final_received or final_received)
    if error_message:
        item.error_message = error_message
    if item.status not in TERMINAL_STATUSES:
        item.status = resolve_item_status(
            target_count=int(item.target_video_count or 0),
            completed_count=int(item.completed_count or 0),
            processing_count=int(item.processing_count or 0),
            final_received=bool(item.final_received),
        )
    await refresh_request_rollup(session, request_id, _req=_req)


async def mark_video_completed(
    session: AsyncSession,
    *,
    request_id: uuid.UUID,
    account_id: uuid.UUID,
    current_unused_template_count: int | None = None,
) -> None:
    item = await _get_item_for_update(session, request_id, account_id)
    if item is None:
        return
    item.completed_count = int(item.completed_count or 0) + 1
    item.processing_count = max(0, int(item.processing_count or 0) - 1)
    if current_unused_template_count is not None:
        item.current_unused_template_count = int(current_unused_template_count)
    item.status = resolve_item_status(
        target_count=int(item.target_video_count or 0),
        completed_count=int(item.completed_count or 0),
        processing_count=int(item.processing_count or 0),
        final_received=bool(item.final_received),
    )
    await refresh_request_rollup(session, request_id)


async def mark_video_failed(
    session: AsyncSession,
    *,
    request_id: uuid.UUID,
    account_id: uuid.UUID,
    reason: str,
    rejected: bool = False,
    decrement_processing: bool = True,
    current_unused_template_count: int | None = None,
) -> None:
    item = await _get_item_for_update(session, request_id, account_id)
    if item is None:
        return
    item.failed_count = int(item.failed_count or 0) + 1
    if rejected:
        item.rejected_count = int(item.rejected_count or 0) + 1
    if decrement_processing:
        item.processing_count = max(0, int(item.processing_count or 0) - 1)
    if current_unused_template_count is not None:
        item.current_unused_template_count = int(current_unused_template_count)
    item.error_message = reason
    item.status = resolve_item_status(
        target_count=int(item.target_video_count or 0),
        completed_count=int(item.completed_count or 0),
        processing_count=int(item.processing_count or 0),
        final_received=bool(item.final_received),
    )
    await refresh_request_rollup(session, request_id)


async def mark_request_failed(
    session: AsyncSession,
    *,
    request_id: uuid.UUID,
    error_message: str,
) -> None:
    items = (await session.execute(
        select(ExternalSupplementRequestItem)
        .where(ExternalSupplementRequestItem.request_id == request_id)
        .with_for_update()
    )).scalars().all()
    for item in items:
        if item.status not in ("completed", "skipped"):
            item.status = "failed"
            item.error_message = error_message
            item.final_received = True
    await refresh_request_rollup(session, request_id, force_failed=True, error_message=error_message)


async def latest_statuses_for_accounts(
    session: AsyncSession,
    *,
    account_ids: list[uuid.UUID],
    owner_id: uuid.UUID | None,
) -> dict[uuid.UUID, dict[str, Any]]:
    if not account_ids:
        return {}
    stmt = (
        select(ExternalSupplementRequestItem)
        .where(ExternalSupplementRequestItem.account_id.in_(account_ids))
        .order_by(
            ExternalSupplementRequestItem.account_id.asc(),
            ExternalSupplementRequestItem.updated_at.desc(),
        )
    )
    if owner_id is not None:
        stmt = stmt.where(ExternalSupplementRequestItem.owner_id == owner_id)
    rows = (await session.execute(stmt)).scalars().all()
    result: dict[uuid.UUID, dict[str, Any]] = {}
    for item in rows:
        if item.account_id in result:
            continue
        if item.status == "skipped":
            continue
        result[item.account_id] = item_status_payload(item)
    return result


async def refresh_request_rollup(
    session: AsyncSession,
    request_id: uuid.UUID,
    *,
    force_failed: bool = False,
    error_message: str | None = None,
    _req: ExternalSupplementRequest | None = None,
) -> None:
    # 优先复用调用方已持有的 req 对象，避免 SELECT FOR UPDATE 在同一 session
    # 内重新 load 覆盖调用方尚未 commit 的字段修改（如 callbacks_log）
    if _req is not None:
        req = _req
    else:
        req = await session.scalar(
            select(ExternalSupplementRequest)
            .where(ExternalSupplementRequest.request_id == request_id)
            .with_for_update()
        )
    if req is None:
        return
    items = (await session.execute(
        select(ExternalSupplementRequestItem)
        .where(ExternalSupplementRequestItem.request_id == request_id)
    )).scalars().all()
    active_items = [i for i in items if i.status != "skipped"]
    completed = sum(int(i.completed_count or 0) for i in active_items)
    processing = sum(int(i.processing_count or 0) for i in active_items)
    expected = sum(int(i.target_video_count or 0) for i in active_items)
    if force_failed:
        req.status = "failed"
        req.vendor_response = {**(req.vendor_response or {}), "progress_error": error_message}
        return
    if active_items and all(i.status == "completed" for i in active_items):
        req.status = "completed"
    elif active_items and all(i.status in TERMINAL_STATUSES for i in active_items):
        # 所有 item 都已结案：只要有任何一条视频成功入库，整体视为 completed
        # （部分 item failed 是因为 AI 审核/分类全部未通过，属于正常业务损耗）
        req.status = "completed" if completed > 0 else "failed"
    elif processing > 0 or any(i.status == "running" for i in active_items):
        req.status = "partial"


async def _get_item_for_update(
    session: AsyncSession,
    request_id: uuid.UUID,
    account_id: uuid.UUID,
) -> ExternalSupplementRequestItem | None:
    return await session.scalar(
        select(ExternalSupplementRequestItem)
        .where(ExternalSupplementRequestItem.request_id == request_id)
        .where(ExternalSupplementRequestItem.account_id == account_id)
        .with_for_update()
    )
