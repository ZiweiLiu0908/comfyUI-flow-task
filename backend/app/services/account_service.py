from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import Float, Integer, cast, delete, func, literal_column, nullslast, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.account_channel_reservation import AccountChannelReservation
from app.models.flag import AccountFlag
from app.schemas.account import AccountCreate, AccountPatch, BulkUpdateAccountAttributesBody

# Sortable columns backed by performance_snapshot JSON keys
_SNAPSHOT_SORT_FIELDS = {
    "avg_views": "performance_snapshot->>'avg_views'",
    "avg_like_rate": "performance_snapshot->>'avg_like_rate'",
    "latest_video_published_at": "performance_snapshot->>'latest_video_published_at'",
    "followers_count": "performance_snapshot->>'followers_count'",
    "total_views": "performance_snapshot->>'total_views'",
}

# Sortable columns on the Account table itself
_TABLE_SORT_FIELDS = {
    "created_at": Account.created_at,
}


async def recompute_account_platform_binding_status(
    session: AsyncSession,
    account_id: UUID,
) -> str | None:
    await session.flush()
    account = await session.get(Account, account_id)
    if account is None:
        return None
    if account.platform_binding_status == "shadowban":
        return "shadowban"

    rows = (
        await session.execute(
            select(AccountChannelReservation.status, AccountChannelReservation.channel_status)
            .where(AccountChannelReservation.account_id == account_id)
        )
    ).all()

    if not rows:
        new_status = "unbound"
    else:
        bound_rows = [row for row in rows if row[0] == "bound"]
        if bound_rows:
            all_bound_disabled = all((channel_status or "active") == "disabled" for _, channel_status in bound_rows)
            new_status = "disabled" if all_bound_disabled else "bound"
        elif any(status in ("confirmed", "reserved") for status, _ in rows):
            new_status = "confirmed"
        else:
            new_status = "unbound"

    account.platform_binding_status = new_status
    return new_status


async def create_account(
    session: AsyncSession,
    payload: AccountCreate,
    owner_id: UUID | None = None,
    *,
    defer_kol_provision: bool = False,
) -> Account:
    """创建账号；默认在 commit 后同步等待 KOL 创建。

    AI 自动生成路径下 nickname/avatar/signature 还没填充完，需要传
    ``defer_kol_provision=True``，由 ai_account_service 在生成完成节点自行调用
    ``provision_kol_for_account``。
    """
    account = Account(
        owner_id=owner_id,
        account_name=payload.account_name,
        account_type=payload.account_type,
        product_code_mode=payload.product_code_mode,
        face_mode=payload.face_mode,
        gender=payload.gender,
        account_tier=payload.account_tier,
        style_description=payload.style_description,
        model_appearance=payload.model_appearance,
        avatar_url=payload.avatar_url,
        photo_url=payload.photo_url,
        hashtags=payload.hashtags if payload.hashtags else None,
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)
    if not defer_kol_provision:
        # 同步等待 KOL 创建；失败只更新 kol_provision_status，不抛回（service 内已吞掉异常）
        from app.services.kol_service import provision_kol_for_account
        await provision_kol_for_account(account.id)
        await session.refresh(account)
    return account


async def list_accounts(
    session: AsyncSession,
    *,
    page: int,
    page_size: int,
    owner_id: UUID | None = None,
    flag_id: UUID | None = None,
    search: str | None = None,
    sort_by: str | None = None,
    sort_order: str | None = None,
    gender: str | None = None,
    account_type: str | None = None,
    face_mode: str | None = None,
    product_code_mode: str | None = None,
    account_tier: str | None = None,
    platform_binding_status: str | None = None,
    classification_type: str | None = None,
    category_indices: list[int] | None = None,
) -> tuple[list[Account], int]:
    # ── Determine sort order ──────────────────────────────────────────────────
    order_desc = (sort_order or "desc").lower() == "desc"

    if sort_by and sort_by in _SNAPSHOT_SORT_FIELDS:
        json_expr = _SNAPSHOT_SORT_FIELDS[sort_by]
        # Extract the raw JSON text value via a literal column expression
        raw_col = text(json_expr)
        if sort_by in ("avg_views", "avg_like_rate", "followers_count", "total_views"):
            # Cast to float so numeric ordering works correctly
            typed_col = func.cast(func.nullif(raw_col, ""), Float)
        else:
            # Date strings in ISO format sort correctly as text
            typed_col = func.nullif(raw_col, "")
        order_clause = nullslast(typed_col.desc() if order_desc else typed_col.asc())
    elif sort_by and sort_by in _TABLE_SORT_FIELDS:
        col = _TABLE_SORT_FIELDS[sort_by]
        order_clause = col.desc() if order_desc else col.asc()
    else:
        order_clause = Account.created_at.desc()

    stmt = select(Account).order_by(order_clause).offset((page - 1) * page_size).limit(page_size)
    total_stmt = select(func.count(Account.id))

    # ── Filters ───────────────────────────────────────────────────────────────
    if owner_id is not None:
        stmt = stmt.where(Account.owner_id == owner_id)
        total_stmt = total_stmt.where(Account.owner_id == owner_id)
    if flag_id is not None:
        flag_subq = select(AccountFlag.account_id).where(AccountFlag.flag_id == flag_id)
        stmt = stmt.where(Account.id.in_(flag_subq))
        total_stmt = total_stmt.where(Account.id.in_(flag_subq))
    if search:
        pattern = f"%{search}%"
        stmt = stmt.where(Account.account_name.ilike(pattern))
        total_stmt = total_stmt.where(Account.account_name.ilike(pattern))
    if gender:
        stmt = stmt.where(Account.gender == gender)
        total_stmt = total_stmt.where(Account.gender == gender)
    if account_type:
        stmt = stmt.where(Account.account_type == account_type)
        total_stmt = total_stmt.where(Account.account_type == account_type)
    if face_mode:
        stmt = stmt.where(Account.face_mode == face_mode)
        total_stmt = total_stmt.where(Account.face_mode == face_mode)
    if product_code_mode:
        stmt = stmt.where(Account.product_code_mode == product_code_mode)
        total_stmt = total_stmt.where(Account.product_code_mode == product_code_mode)
    if account_tier:
        stmt = stmt.where(Account.account_tier == account_tier)
        total_stmt = total_stmt.where(Account.account_tier == account_tier)
    if platform_binding_status:
        stmt = stmt.where(Account.platform_binding_status == platform_binding_status)
        total_stmt = total_stmt.where(Account.platform_binding_status == platform_binding_status)
    if classification_type:
        if classification_type == "unclassified":
            stmt = stmt.where(Account.classification_type.is_(None))
            total_stmt = total_stmt.where(Account.classification_type.is_(None))
        else:
            stmt = stmt.where(Account.classification_type == classification_type)
            total_stmt = total_stmt.where(Account.classification_type == classification_type)

    if category_indices and classification_type in ("single", "dual"):
        primary_idx = cast(literal_column("classification_summary->>'primary_index'"), Integer)
        secondary_idx = cast(literal_column("classification_summary->>'secondary_index'"), Integer)
        if classification_type == "single":
            stmt = stmt.where(primary_idx.in_(category_indices))
            total_stmt = total_stmt.where(primary_idx.in_(category_indices))
        else:  # dual: each selected index must match primary or secondary
            for idx in category_indices:
                cond = or_(primary_idx == idx, secondary_idx == idx)
                stmt = stmt.where(cond)
                total_stmt = total_stmt.where(cond)

    rows = (await session.execute(stmt)).scalars().all()
    total = int(await session.scalar(total_stmt) or 0)
    return list(rows), total


async def get_account_or_404(
    session: AsyncSession,
    account_id: UUID,
    owner_id: UUID | None = None,
) -> Account:
    account = await session.scalar(select(Account).where(Account.id == account_id))
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")
    if owner_id is not None and account.owner_id != owner_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")
    return account


async def patch_account(
    session: AsyncSession,
    account: Account,
    payload: AccountPatch,
) -> Account:
    if payload.account_name is not None:
        account.account_name = payload.account_name
    if payload.account_handle is not None:
        account.account_handle = payload.account_handle
    if payload.account_signature is not None:
        account.account_signature = payload.account_signature
    if payload.account_type is not None:
        account.account_type = payload.account_type
    if payload.product_code_mode is not None:
        account.product_code_mode = payload.product_code_mode
    if payload.face_mode is not None:
        account.face_mode = payload.face_mode
    if payload.gender is not None:
        account.gender = payload.gender
    if payload.account_tier is not None:
        account.account_tier = payload.account_tier
    if payload.style_description is not None:
        account.style_description = payload.style_description
    if payload.model_appearance is not None:
        account.model_appearance = payload.model_appearance
    if payload.avatar_url is not None:
        account.avatar_url = payload.avatar_url
    if payload.photo_url is not None:
        account.photo_url = payload.photo_url
    if payload.hashtags is not None:
        account.hashtags = payload.hashtags if payload.hashtags else None
    await session.commit()
    await session.refresh(account)
    return account


async def bulk_update_account_attributes(
    session: AsyncSession,
    payload: BulkUpdateAccountAttributesBody,
    owner_id: UUID | None = None,
) -> list[Account]:
    updates = payload.model_dump(exclude={"account_ids"}, exclude_none=True)
    if not updates:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请至少选择一个要修改的字段",
        )

    # Deduplicate while keeping the client order stable for the response.
    account_ids = list(dict.fromkeys(payload.account_ids))
    stmt = select(Account).where(Account.id.in_(account_ids))
    if owner_id is not None:
        stmt = stmt.where(Account.owner_id == owner_id)

    accounts = list((await session.execute(stmt)).scalars().all())
    if not accounts:
        return []
    account_order = {account_id: index for index, account_id in enumerate(account_ids)}
    accounts.sort(key=lambda account: account_order.get(account.id, len(account_order)))

    for account in accounts:
        for field, value in updates.items():
            setattr(account, field, value)

    await session.commit()
    for account in accounts:
        await session.refresh(account)
    return accounts


# ── 最近 N 条子任务成功率 ─────────────────────────────────────────────────────

_SUB_TASK_SUCCESS_NUMER_STATUSES: tuple[str, ...] = ("stashed", "queued", "published")
_SUB_TASK_SUCCESS_DENOM_STATUSES: tuple[str, ...] = (
    "stashed", "reviewing", "decision_rejected", "queued", "published",
)


async def compute_sub_task_success_rate(
    session: AsyncSession,
    account_id: UUID,
    *,
    sample_size: int = 20,
) -> tuple[int, int, int]:
    """计算账号最近 N 条 sub_task 的成功率。

    公式：成功率 = (暂存 + 队列中 + 已发布) / (暂存 + 待决策 + 决策未通过 + 队列中 + 已发布)

    返回 (numer, denom, sample) —— numer/denom 用于算比例；sample 是
    实际拉到的子任务总数（包含分母外的状态，便于调用方了解样本规模）。
    """
    from app.models.video_task import VideoSubTask, VideoTask

    stmt = (
        select(VideoSubTask.status)
        .join(VideoTask, VideoTask.id == VideoSubTask.task_id)
        .where(VideoTask.account_id == account_id)
        .order_by(VideoSubTask.created_at.desc())
        .limit(sample_size)
    )
    statuses = list((await session.execute(stmt)).scalars().all())
    numer = sum(1 for s in statuses if s in _SUB_TASK_SUCCESS_NUMER_STATUSES)
    denom = sum(1 for s in statuses if s in _SUB_TASK_SUCCESS_DENOM_STATUSES)
    return numer, denom, len(statuses)


async def batch_compute_sub_task_success_rate(
    session: AsyncSession,
    account_ids: list[UUID],
    *,
    sample_size: int = 20,
) -> dict[UUID, tuple[int, int, int]]:
    """批量版本：返回 {account_id: (numer, denom, sample)}。

    每个账号独立按 created_at desc 取最近 N 条；用 row_number over partition 一次
    捞完所有候选行，再在 Python 端聚合。
    """
    from sqlalchemy import func as sa_func
    from app.models.video_task import VideoSubTask, VideoTask

    if not account_ids:
        return {}

    rn = sa_func.row_number().over(
        partition_by=VideoTask.account_id,
        order_by=VideoSubTask.created_at.desc(),
    ).label("rn")
    subq = (
        select(
            VideoTask.account_id.label("aid"),
            VideoSubTask.status.label("status"),
            rn,
        )
        .join(VideoSubTask, VideoSubTask.task_id == VideoTask.id)
        .where(VideoTask.account_id.in_(account_ids))
        .subquery()
    )
    rows = (await session.execute(
        select(subq.c.aid, subq.c.status).where(subq.c.rn <= sample_size)
    )).all()

    out: dict[UUID, tuple[int, int, int]] = {aid: (0, 0, 0) for aid in account_ids}
    counters: dict[UUID, list[int]] = {aid: [0, 0, 0] for aid in account_ids}  # [numer, denom, sample]
    for aid, status_val in rows:
        if aid is None:
            continue
        bucket = counters.setdefault(aid, [0, 0, 0])
        bucket[2] += 1
        if status_val in _SUB_TASK_SUCCESS_NUMER_STATUSES:
            bucket[0] += 1
        if status_val in _SUB_TASK_SUCCESS_DENOM_STATUSES:
            bucket[1] += 1
    for aid, (n, d, s) in counters.items():
        out[aid] = (n, d, s)
    return out


async def delete_account(
    session: AsyncSession,
    account_id: UUID,
    owner_id: UUID | None = None,
) -> None:
    await get_account_or_404(session, account_id, owner_id)
    await session.execute(delete(Account).where(Account.id == account_id))
    await session.commit()
