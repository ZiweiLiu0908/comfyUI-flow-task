from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import date, datetime, timezone


from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, exists, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenData, get_current_user
from app.db.session import SessionLocal
from app.db.session import get_db
from app.models.account import Account
from app.models.account_blogger_binding import AccountBloggerBinding
from app.models.account_channel_reservation import AccountChannelReservation
from app.models.account_tag import AccountTag
from app.models.flag import AccountFlag, Flag
from app.models.tag import Tag
from app.models.tag import VideoSourceTag
from app.models.tiktok_blogger import TiktokBlogger
from app.models.video_source import VideoSource
from app.models.video_task import VideoSubTask, VideoTask
from app.models.video_publication import VideoPublication
from app.schemas.account import (
    AccountCreate, AccountListResponse, AccountPatch, AccountRead,
    BoundBloggerRead, BoundFlagRead, BoundTagRead, ScheduledPublishConfig,
    AIGenerateBody, AIGenerateStatusResponse, BindTagBody, BulkGenerateAIAccountsResponse,
    BulkResumeAIAccountsResponse, ResumeAIGenerationBody, SelectPhotoCandidateBody,
    BulkGenerateNameHandleBody, BulkGenerateNameHandleResponse,
    AccountChannelReservationRead, BindOpenAPIChannelBody, ConfirmChannelReservationsBody,
    ConfirmChannelReservationsResponse, ReserveAIAccountsBody, ReserveAIAccountsResponse,
    BulkUpdateAccountAttributesBody, BulkUpdateAccountAttributesResponse,
    SupplementStatusRead, ChannelAnalyticsResponse,
)
from app.schemas.tiktok_blogger import TiktokBloggerRead
from app.services.account_service import (
    create_account,
    delete_account,
    get_account_or_404,
    list_accounts,
    bulk_update_account_attributes,
    patch_account,
)
from app.services.channel_status_poller import refresh_reservation_channel_status

router = APIRouter(prefix="/accounts", tags=["accounts"])
logger = logging.getLogger("app.accounts")


async def _ensure_template_tags_for_account(
    session: AsyncSession,
    account_id: uuid.UUID,
    owner_id: uuid.UUID | None,
) -> dict:
    from app.services.account_template_tag_service import ensure_account_template_tags

    result = await ensure_account_template_tags(session, account_id, owner_id=owner_id)
    return result.model_dump()


def _get_owner_id(current_user: TokenData = Depends(get_current_user)) -> uuid.UUID | None:
    """For queries: admin sees all (None = no filter), regular user sees own only."""
    return None if current_user.is_admin else current_user.user_id


def _get_creator_id(current_user: TokenData = Depends(get_current_user)) -> uuid.UUID:
    """For writes: always bind to the actual user, even if admin."""
    return current_user.user_id


class PlatformStatItem(BaseModel):
    platform: str
    bound: int
    confirmed: int
    no_stock: int   # 已绑定但无有效库存（队列中无 publish_meta.status=done 的 subtask）
    unbound: int


class PlatformStatsResponse(BaseModel):
    platforms: list[PlatformStatItem]


@router.get("/platform-stats", response_model=PlatformStatsResponse)
async def get_platform_stats(
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> PlatformStatsResponse:
    """按平台统计账号绑定状态数量。"""
    PLATFORMS = ["tiktok", "youtube", "instagram"]

    # 总账号数（用于计算未绑定 = 总数 - 有该平台 reservation 的数）
    total_stmt = select(func.count(Account.id))
    if owner_id is not None:
        total_stmt = total_stmt.where(Account.owner_id == owner_id)
    total_accounts: int = (await session.scalar(total_stmt)) or 0

    # 有效库存子查询：account_id 存在 queued 且 publish_meta.status=done 的 subtask
    has_stock_subq = (
        select(VideoTask.account_id)
        .join(VideoSubTask, VideoSubTask.task_id == VideoTask.id)
        .where(
            VideoSubTask.status == "queued",
            VideoSubTask.publish_meta.op("->>")(  # type: ignore[attr-defined]
                "status"
            ) == "done",
        )
        .where(VideoTask.account_id.is_not(None))
    )

    items: list[PlatformStatItem] = []
    for platform in PLATFORMS:
        # 统计各 reservation 状态
        res_stmt = (
            select(
                AccountChannelReservation.status,
                AccountChannelReservation.channel_status,
                func.count(AccountChannelReservation.id),
            )
            .join(Account, Account.id == AccountChannelReservation.account_id)
            .where(AccountChannelReservation.platform == platform)
            .group_by(
                AccountChannelReservation.status,
                AccountChannelReservation.channel_status,
            )
        )
        if owner_id is not None:
            res_stmt = res_stmt.where(Account.owner_id == owner_id)

        rows = (await session.execute(res_stmt)).all()

        bound = 0
        confirmed = 0
        has_reservation = 0

        for res_status, _ch_status, cnt in rows:
            has_reservation += cnt
            if res_status == "bound":
                bound += cnt
            elif res_status == "confirmed":
                confirmed += cnt

        # 已绑定中，有有效库存的账号数
        stock_stmt = (
            select(func.count(func.distinct(AccountChannelReservation.account_id)))
            .join(Account, Account.id == AccountChannelReservation.account_id)
            .where(
                AccountChannelReservation.platform == platform,
                AccountChannelReservation.status == "bound",
                AccountChannelReservation.account_id.in_(has_stock_subq),
            )
        )
        if owner_id is not None:
            stock_stmt = stock_stmt.where(Account.owner_id == owner_id)
        bound_with_stock: int = (await session.scalar(stock_stmt)) or 0

        no_stock = max(bound - bound_with_stock, 0)
        unbound = max(total_accounts - has_reservation, 0)

        items.append(PlatformStatItem(
            platform=platform,
            bound=bound,
            confirmed=confirmed,
            no_stock=no_stock,
            unbound=unbound,
        ))

    return PlatformStatsResponse(platforms=items)


class BindBloggerBody(BaseModel):
    tiktok_blogger_id: uuid.UUID


async def _load_bound_bloggers(session: AsyncSession, account_id: uuid.UUID) -> list[BoundBloggerRead]:
    stmt = (
        select(TiktokBlogger)
        .join(AccountBloggerBinding, AccountBloggerBinding.tiktok_blogger_id == TiktokBlogger.id)
        .where(AccountBloggerBinding.account_id == account_id)
        .order_by(AccountBloggerBinding.created_at.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [BoundBloggerRead.model_validate(b) for b in rows]


async def _load_bound_flags(session: AsyncSession, account_id: uuid.UUID) -> list[BoundFlagRead]:
    stmt = (
        select(Flag)
        .join(AccountFlag, AccountFlag.flag_id == Flag.id)
        .where(AccountFlag.account_id == account_id)
        .order_by(AccountFlag.created_at.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [BoundFlagRead.model_validate(f) for f in rows]


async def _load_bound_tags(session: AsyncSession, account_id: uuid.UUID) -> list[BoundTagRead]:
    stmt = (
        select(Tag)
        .join(AccountTag, AccountTag.tag_id == Tag.id)
        .where(AccountTag.account_id == account_id)
        .order_by(AccountTag.created_at.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [BoundTagRead.model_validate(t) for t in rows]


async def _load_channel_reservations(
    session: AsyncSession,
    account_id: uuid.UUID,
) -> list[AccountChannelReservationRead]:
    stmt = (
        select(AccountChannelReservation)
        .where(AccountChannelReservation.account_id == account_id)
        .order_by(AccountChannelReservation.created_at.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [AccountChannelReservationRead.model_validate(r) for r in rows]


def _channel_binding_payload(body: BindOpenAPIChannelBody) -> dict:
    data = body.model_dump(exclude_none=True)
    extra = data.pop("extra", None) or {}
    data.update(extra)
    data["platform"] = body.platform
    data["source"] = body.source or "openapi"
    return data


def _reservation_to_binding(reservation: AccountChannelReservation | AccountChannelReservationRead) -> dict:
    base = {
        "platform": reservation.platform,
        "channel_source": reservation.channel_source or reservation.source or "openapi",
        "channel_id": reservation.channel_id or "",
        "channel_name": reservation.channel_name or "",
        "username": reservation.username or "",
    }
    avatar_url = getattr(reservation, "avatar_url", None)
    if avatar_url:
        base["avatar_url"] = avatar_url
    return base


def _apply_channel_binding(
    reservation: AccountChannelReservation,
    binding: dict,
    *,
    now: datetime,
) -> None:
    platform = str(binding.get("platform") or reservation.platform or "").lower()
    source = str(binding.get("channel_source") or binding.get("source") or reservation.source or "openapi")
    reservation.platform = platform
    reservation.status = "bound"
    reservation.source = source
    reservation.channel_source = source
    reservation.channel_id = str(binding.get("channel_id") or "") or None
    reservation.channel_name = str(binding.get("channel_name") or "") or None
    reservation.username = str(binding.get("username") or "") or None
    reservation.avatar_url = str(binding.get("avatar_url") or "") or None
    reservation.channel_info = {**binding, "platform": platform, "channel_source": source}
    reservation.confirmed_at = reservation.confirmed_at or now
    reservation.bound_at = now


async def _sync_channel_reservations_from_bindings(
    session: AsyncSession,
    account: Account,
    bindings: list[dict] | None,
) -> None:
    """把接口传入的频道绑定写入结构化频道表。"""
    supported_platforms = {"youtube", "tiktok", "instagram"}
    desired: dict[str, dict] = {}
    for binding in bindings or []:
        if not isinstance(binding, dict):
            continue
        platform = str(binding.get("platform") or "").lower()
        if platform in supported_platforms:
            desired[platform] = {**binding, "platform": platform}

    rows = (await session.execute(
        select(AccountChannelReservation)
        .where(AccountChannelReservation.account_id == account.id)
        .where(AccountChannelReservation.platform.in_(supported_platforms))
    )).scalars().all()
    existing_by_platform = {r.platform: r for r in rows}
    now = datetime.now(timezone.utc)

    for platform, binding in desired.items():
        reservation = existing_by_platform.get(platform)
        if reservation is None:
            reservation = AccountChannelReservation(
                account_id=account.id,
                platform=platform,
                reserved_at=now,
                confirmed_at=now,
            )
            session.add(reservation)
        elif reservation.status == "bound":
            # bound 记录受保护，跳过修改
            continue
        _apply_channel_binding(reservation, binding, now=now)
        await refresh_reservation_channel_status(reservation)

    for platform, reservation in existing_by_platform.items():
        if platform not in desired and reservation.status == "bound" and reservation.confirmed_at is None:
            await session.delete(reservation)

    await session.commit()


def _account_read(
    account,
    bloggers: list[BoundBloggerRead],
    tags: list[BoundTagRead] | None = None,
    flags: list[BoundFlagRead] | None = None,
    pending_publish_count: int = 0,
    channel_reservations: list[AccountChannelReservationRead] | None = None,
    linked_video_count: int = 0,
    unused_template_count: int = 0,
    used_template_count: int = 0,
    sub_task_success: tuple[int, int, int] = (0, 0, 0),
    supplement_status: dict | None = None,
) -> AccountRead:
    data = AccountRead.model_validate(account)
    data.tiktok_bloggers = bloggers
    data.bound_tags = tags or []
    data.bound_flags = flags or []
    data.pending_publish_count = pending_publish_count
    data.linked_video_count = linked_video_count
    data.unused_template_count = unused_template_count
    data.used_template_count = used_template_count
    numer, denom, sample = sub_task_success
    data.sub_task_success_numer = numer
    data.sub_task_success_denom = denom
    data.sub_task_success_sample = sample
    data.sub_task_success_rate = (numer / denom) if denom > 0 else None
    data.channel_reservations = channel_reservations or []
    data.supplement_status = SupplementStatusRead(**supplement_status) if supplement_status else None
    data.social_bindings = None
    return data


def _ai_generation_response(account_id: uuid.UUID, state: dict, account) -> AIGenerateStatusResponse:
    return AIGenerateStatusResponse(
        account_id=str(account_id),
        status=state.get("status", account.ai_generation_status or "idle"),
        error_message=state.get("error_message", account.ai_generation_error or ""),
        all_video_count=state.get("all_video_count", 0),
        analysis_sample_size=state.get("analysis_sample_size", 10),
        analysis_video_ids=state.get("analysis_video_ids", []) or [],
        analysis_items=state.get("analysis_items", []) or [],
        generated_name=state.get("generated_name", ""),
        generated_handle=state.get("generated_handle", account.account_handle or ""),
        generated_signature=state.get("generated_signature", account.account_signature or ""),
        generated_gender=state.get("generated_gender", account.gender or ""),
        generated_avatar_url=state.get("generated_avatar_url", account.avatar_url or ""),
        generated_photo_url=state.get("generated_photo_url", account.photo_url or ""),
        photo_candidate_count=state.get("photo_candidate_count", 0),
        photo_candidates=state.get("photo_candidates", []) or [],
        selected_photo_candidate_id=state.get("selected_photo_candidate_id"),
        combined_description=state.get("combined_description", ""),
    )


@router.post("", response_model=AccountRead, status_code=201)
async def create_account_endpoint(
    payload: AccountCreate,
    creator_id: uuid.UUID = Depends(_get_creator_id),
    session: AsyncSession = Depends(get_db),
) -> AccountRead:
    account = await create_account(
        session, payload, creator_id,
        defer_kol_provision=payload.defer_kol_provision,
    )
    if payload.social_bindings is not None:
        await _sync_channel_reservations_from_bindings(session, account, payload.social_bindings)
    reservations = await _load_channel_reservations(session, account.id)
    return _account_read(account, [], [], channel_reservations=reservations)


@router.get("", response_model=AccountListResponse)
async def list_accounts_endpoint(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=9999),
    flag_id: uuid.UUID | None = Query(None),
    search: str | None = Query(None),
    sort_by: str | None = Query(None),
    sort_order: str | None = Query(None),
    gender: str | None = Query(None),
    account_type: str | None = Query(None),
    face_mode: str | None = Query(None),
    product_code_mode: str | None = Query(None),
    account_tier: str | None = Query(None),
    platform_binding_status: str | None = Query(None),
    classification_type: str | None = Query(None),
    category_keys: str | None = Query(None),
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> AccountListResponse:
    parsed_category_keys: list[str] | None = None
    if category_keys:
        parsed_category_keys = [x.strip() for x in category_keys.split(",") if x.strip()]
    items, total = await list_accounts(
        session,
        page=page,
        page_size=page_size,
        owner_id=owner_id,
        flag_id=flag_id,
        search=search or None,
        sort_by=sort_by or None,
        sort_order=sort_order or None,
        gender=gender or None,
        account_type=account_type or None,
        face_mode=face_mode or None,
        product_code_mode=product_code_mode or None,
        account_tier=account_tier or None,
        platform_binding_status=platform_binding_status or None,
        classification_type=classification_type or None,
        category_keys=parsed_category_keys or None,
    )
    # Batch-load bound bloggers, tags, flags for all accounts.
    account_ids = [a.id for a in items]
    blogger_map: dict[uuid.UUID, list[BoundBloggerRead]] = {aid: [] for aid in account_ids}
    tag_map: dict[uuid.UUID, list[BoundTagRead]] = {aid: [] for aid in account_ids}
    flag_map: dict[uuid.UUID, list[BoundFlagRead]] = {aid: [] for aid in account_ids}
    reservation_map: dict[uuid.UUID, list[AccountChannelReservationRead]] = {aid: [] for aid in account_ids}
    pending_publish_map: dict[uuid.UUID, int] = {aid: 0 for aid in account_ids}
    video_count_map: dict[uuid.UUID, int] = {aid: 0 for aid in account_ids}
    supplement_status_map: dict[uuid.UUID, dict] = {}
    if account_ids:
        from app.services.supplement_status_service import latest_statuses_for_accounts
        supplement_status_map = await latest_statuses_for_accounts(
            session,
            account_ids=account_ids,
            owner_id=owner_id,
        )

        blogger_stmt = (
            select(AccountBloggerBinding.account_id, TiktokBlogger)
            .join(TiktokBlogger, AccountBloggerBinding.tiktok_blogger_id == TiktokBlogger.id)
            .where(AccountBloggerBinding.account_id.in_(account_ids))
            .order_by(AccountBloggerBinding.created_at.asc())
        )
        for aid, blogger in (await session.execute(blogger_stmt)).all():
            blogger_map[aid].append(BoundBloggerRead.model_validate(blogger))

        tag_stmt = (
            select(AccountTag.account_id, Tag)
            .join(Tag, AccountTag.tag_id == Tag.id)
            .where(AccountTag.account_id.in_(account_ids))
            .order_by(AccountTag.created_at.asc())
        )
        for aid, tag in (await session.execute(tag_stmt)).all():
            tag_map[aid].append(BoundTagRead.model_validate(tag))

        flag_stmt = (
            select(AccountFlag.account_id, Flag)
            .join(Flag, AccountFlag.flag_id == Flag.id)
            .where(AccountFlag.account_id.in_(account_ids))
            .order_by(AccountFlag.created_at.asc())
        )
        for aid, flag in (await session.execute(flag_stmt)).all():
            flag_map[aid].append(BoundFlagRead.model_validate(flag))

        reservation_stmt = (
            select(AccountChannelReservation)
            .where(AccountChannelReservation.account_id.in_(account_ids))
            .order_by(AccountChannelReservation.created_at.asc())
        )
        for reservation in (await session.execute(reservation_stmt)).scalars().all():
            reservation_map[reservation.account_id].append(AccountChannelReservationRead.model_validate(reservation))

        pending_publish_stmt = (
            select(VideoTask.account_id, func.count(VideoSubTask.id))
            .join(VideoSubTask, VideoSubTask.task_id == VideoTask.id)
            .where(
                VideoTask.account_id.in_(account_ids),
                VideoSubTask.status == "queued",
            )
            .group_by(VideoTask.account_id)
        )
        for aid, count in (await session.execute(pending_publish_stmt)).all():
            if aid is not None:
                pending_publish_map[aid] = int(count or 0)

        video_count_stmt = (
            select(AccountBloggerBinding.account_id, func.count(VideoSource.id))
            .join(VideoSource, VideoSource.tiktok_blogger_id == AccountBloggerBinding.tiktok_blogger_id)
            .where(AccountBloggerBinding.account_id.in_(account_ids))
            .group_by(AccountBloggerBinding.account_id)
        )
        for aid, count in (await session.execute(video_count_stmt)).all():
            if aid is not None:
                video_count_map[aid] = int(count or 0)

    # 模板池：复用「一键生成」过滤逻辑，分别统计未使用/已使用
    template_counts: dict[uuid.UUID, tuple[int, int]] = {}
    for a in items:
        template_counts[a.id] = await _count_account_templates(
            session, account=a, owner_id=owner_id,
        )

    # 最近 N 条子任务的成功率，N 从 pipeline_settings 读（owner 维度），缺省 10
    from app.models.pipeline_setting import PipelineSetting
    from app.services.account_service import batch_compute_sub_task_success_rate
    success_sample_size = 10
    if owner_id is not None:
        ps_row = await session.scalar(
            select(PipelineSetting).where(PipelineSetting.owner_id == owner_id)
        )
        if ps_row is not None and ps_row.sub_task_success_sample_size > 0:
            success_sample_size = int(ps_row.sub_task_success_sample_size)
    success_rate_map = await batch_compute_sub_task_success_rate(
        session, account_ids, sample_size=success_sample_size,
    )

    rich_items = [
        _account_read(
            a,
            blogger_map[a.id],
            tag_map[a.id],
            flag_map[a.id],
            pending_publish_map[a.id],
            reservation_map[a.id],
            linked_video_count=video_count_map.get(a.id, 0),
            unused_template_count=template_counts[a.id][0],
            used_template_count=template_counts[a.id][1],
            sub_task_success=success_rate_map.get(a.id, (0, 0, 0)),
            supplement_status=supplement_status_map.get(a.id),
        )
        for a in items
    ]
    return AccountListResponse(
        items=rich_items,  # type: ignore[arg-type]
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/bulk-update-attributes", response_model=BulkUpdateAccountAttributesResponse)
async def bulk_update_account_attributes_endpoint(
    body: BulkUpdateAccountAttributesBody,
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> BulkUpdateAccountAttributesResponse:
    """批量修改账号基础属性：独享号/人脸/性别/商品码。"""
    accounts = await bulk_update_account_attributes(session, body, owner_id)
    requested_count = len(set(body.account_ids))
    updated_ids = [account.id for account in accounts]
    status_text = "updated" if updated_ids else "no_accounts"
    logger.info(
        "bulk_update_account_attributes status=%s requested=%s updated=%s fields=%s",
        status_text,
        requested_count,
        len(updated_ids),
        body.model_dump(exclude={"account_ids"}, exclude_none=True),
    )
    return BulkUpdateAccountAttributesResponse(
        status=status_text,
        requested_count=requested_count,
        updated_count=len(updated_ids),
        account_ids=updated_ids,
    )


class TierEvaluationChange(BaseModel):
    account_id: uuid.UUID
    account_name: str
    current_tier: str
    target_tier: str
    reason: dict


class TierEvaluationPreviewResponse(BaseModel):
    changes: list[TierEvaluationChange]
    summary: dict  # {promote_to_dev, demote_to_test, total}


class TierEvaluationApplyBody(BaseModel):
    changes: list[TierEvaluationChange]


class TierEvaluationApplyResponse(BaseModel):
    promoted: int = 0   # test → dev
    demoted: int = 0    # dev → test
    skipped: int = 0


@router.post("/tier-evaluation/preview", response_model=TierEvaluationPreviewResponse)
async def preview_tier_evaluation(
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> TierEvaluationPreviewResponse:
    """根据当前 pipeline_settings 中的判定规则，预览会发生 tier 变更的 test/dev 账号列表。

    不修改任何数据。仅评估当前用户名下账号（admin 会评估所有 owner_id IS NULL 的账号）。
    prod 账号不参与，不会被列出。
    """
    from app.services.account_tier_scheduler import compute_tier_changes
    raw = await compute_tier_changes(session, owner_id)
    changes = [TierEvaluationChange(**c) for c in raw]
    promote = sum(1 for c in changes if c.target_tier == "dev")
    demote = sum(1 for c in changes if c.target_tier == "test")
    return TierEvaluationPreviewResponse(
        changes=changes,
        summary={
            "promote_to_dev": promote,
            "demote_to_test": demote,
            "total": len(changes),
        },
    )


@router.post("/tier-evaluation/apply", response_model=TierEvaluationApplyResponse)
async def apply_tier_evaluation(
    body: TierEvaluationApplyBody,
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> TierEvaluationApplyResponse:
    """按 preview 给出的列表实际应用 tier 变更。

    安全校验：
    - 只允许 target_tier ∈ {test, dev}（prod 永不被改）
    - 账号 owner_id 必须等于当前用户（admin 不限）
    - 账号当前 tier 必须仍等于 current_tier，否则跳过（避免覆盖其他人的修改）
    """
    from app.services.account_tier_scheduler import apply_tier_changes
    changes_dict = [c.model_dump() for c in body.changes]
    res = await apply_tier_changes(session, owner_id, changes_dict)
    logger.info(
        "tier_evaluation apply: owner=%s promoted=%d demoted=%d skipped=%d",
        owner_id, res["promoted"], res["demoted"], res["skipped"],
    )
    return TierEvaluationApplyResponse(**res)


@router.post("/channel-reservations", response_model=ReserveAIAccountsResponse, status_code=201)
async def reserve_ai_accounts_for_channel(
    body: ReserveAIAccountsBody,
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> ReserveAIAccountsResponse:
    """按性别和平台领取 AI 博主，并立即占用该平台名额。"""
    platform = body.platform.lower()
    reserved_accounts: list[Account] = []
    reservations: list[AccountChannelReservation] = []
    seen_account_ids: set[uuid.UUID] = set()
    batch_size = max(body.count * 5, 50)
    while len(reserved_accounts) < body.count:
        stmt = (
            select(Account)
            .where(Account.gender == body.gender)
            .where(
                ~exists()
                .where(AccountChannelReservation.account_id == Account.id)
                .where(AccountChannelReservation.platform == platform)
            )
            .order_by(Account.created_at.asc())
            .limit(batch_size)
        )
        if owner_id is not None:
            stmt = stmt.where(Account.owner_id == owner_id)
        if seen_account_ids:
            stmt = stmt.where(Account.id.not_in(list(seen_account_ids)))
        candidates = (await session.execute(stmt)).scalars().all()
        if not candidates:
            break
        for account in candidates:
            seen_account_ids.add(account.id)
            if len(reserved_accounts) >= body.count:
                break
            reservation = AccountChannelReservation(
                account_id=account.id,
                platform=platform,
                status="reserved",
                source=body.source or "openapi",
                channel_source=body.source or "openapi",
                reserved_at=datetime.now(timezone.utc),
            )
            session.add(reservation)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                continue
            await session.refresh(reservation)
            reserved_accounts.append(account)
            reservations.append(reservation)

    items: list[AccountRead] = []
    for account, reservation in zip(reserved_accounts, reservations, strict=False):
        bloggers = await _load_bound_bloggers(session, account.id)
        tags = await _load_bound_tags(session, account.id)
        flags = await _load_bound_flags(session, account.id)
        items.append(
            _account_read(
                account,
                bloggers,
                tags,
                flags,
                channel_reservations=[AccountChannelReservationRead.model_validate(reservation)],
            )
        )

    return ReserveAIAccountsResponse(
        items=items,
        requested_count=body.count,
        reserved_count=len(items),
        reservation_ids=[r.id for r in reservations],
    )


@router.post("/channel-reservations/confirm", response_model=ConfirmChannelReservationsResponse)
async def confirm_channel_reservations(
    body: ConfirmChannelReservationsBody,
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> ConfirmChannelReservationsResponse:
    """确认外部调用方确实占用了这些 AI 博主的平台频道。"""
    stmt = select(AccountChannelReservation).join(Account, Account.id == AccountChannelReservation.account_id)
    if body.reservation_ids:
        stmt = stmt.where(AccountChannelReservation.id.in_(body.reservation_ids))
    else:
        if not body.account_ids or not body.platform:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="reservation_ids 或 account_ids + platform 必须提供一组",
            )
        stmt = stmt.where(AccountChannelReservation.account_id.in_(body.account_ids))
        stmt = stmt.where(AccountChannelReservation.platform == body.platform)
    if owner_id is not None:
        stmt = stmt.where(Account.owner_id == owner_id)

    rows = (await session.execute(stmt)).scalars().all()
    now = datetime.now(timezone.utc)
    confirmed_ids: list[uuid.UUID] = []
    for reservation in rows:
        if reservation.status != "bound":
            reservation.status = "confirmed"
            reservation.confirmed_at = reservation.confirmed_at or now
        confirmed_ids.append(reservation.id)
    await session.commit()
    return ConfirmChannelReservationsResponse(
        status="confirmed",
        confirmed_count=len(confirmed_ids),
        reservation_ids=confirmed_ids,
    )


@router.post("/{account_id}/channel-bindings", response_model=AccountRead)
async def bind_openapi_channel(
    account_id: uuid.UUID,
    body: BindOpenAPIChannelBody,
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> AccountRead:
    """保存 OpenAPI 回传的平台频道信息。"""
    account = await get_account_or_404(session, account_id, owner_id)
    platform = body.platform.lower()
    binding = _channel_binding_payload(body)

    reservation = await session.scalar(
        select(AccountChannelReservation)
        .where(AccountChannelReservation.account_id == account_id)
        .where(AccountChannelReservation.platform == platform)
    )
    now = datetime.now(timezone.utc)
    if reservation is None:
        reservation = AccountChannelReservation(
            account_id=account_id,
            platform=platform,
            source=body.source or "openapi",
            channel_source=body.source or "openapi",
            reserved_at=now,
            confirmed_at=now,
        )
        session.add(reservation)
    elif reservation.status == "bound":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"该账号 {platform} 平台已绑定，不可修改；请先调用 release 释放",
        )
    _apply_channel_binding(reservation, binding, now=now)
    await refresh_reservation_channel_status(reservation)

    await session.commit()
    await session.refresh(account)
    bloggers = await _load_bound_bloggers(session, account_id)
    tags = await _load_bound_tags(session, account_id)
    flags = await _load_bound_flags(session, account_id)
    reservations = await _load_channel_reservations(session, account_id)
    return _account_read(account, bloggers, tags, flags, channel_reservations=reservations)


@router.get("/{account_id}", response_model=AccountRead)
async def get_account_endpoint(
    account_id: uuid.UUID,
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> AccountRead:
    account = await get_account_or_404(session, account_id, owner_id)
    bloggers = await _load_bound_bloggers(session, account_id)
    tags = await _load_bound_tags(session, account_id)
    flags = await _load_bound_flags(session, account_id)
    reservations = await _load_channel_reservations(session, account_id)
    return _account_read(account, bloggers, tags, flags, channel_reservations=reservations)


@router.patch("/{account_id}", response_model=AccountRead)
async def patch_account_endpoint(
    account_id: uuid.UUID,
    payload: AccountPatch,
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> AccountRead:
    account = await get_account_or_404(session, account_id, owner_id)
    account = await patch_account(session, account, payload)
    if payload.social_bindings is not None:
        await _sync_channel_reservations_from_bindings(session, account, payload.social_bindings)
    bloggers = await _load_bound_bloggers(session, account_id)
    tags = await _load_bound_tags(session, account_id)
    flags = await _load_bound_flags(session, account_id)
    reservations = await _load_channel_reservations(session, account_id)
    return _account_read(account, bloggers, tags, flags, channel_reservations=reservations)


@router.delete("/{account_id}/channel-reservations/{reservation_id}")
async def delete_channel_reservation(
    account_id: uuid.UUID,
    reservation_id: uuid.UUID,
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """删除一条频道绑定（channel_reservation）。仅允许删除 bound 状态的记录。"""
    await get_account_or_404(session, account_id, owner_id)
    reservation = await session.scalar(
        select(AccountChannelReservation)
        .where(AccountChannelReservation.id == reservation_id)
        .where(AccountChannelReservation.account_id == account_id)
    )
    if reservation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="频道绑定不存在")
    if reservation.status != "bound":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="只能删除已绑定（bound）状态的频道",
        )
    await session.delete(reservation)
    await session.commit()
    return Response(status_code=204)


@router.delete("/{account_id}")
async def delete_account_endpoint(
    account_id: uuid.UUID,
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> Response:
    await delete_account(session, account_id, owner_id)
    return Response(status_code=204)


# ── 定时发布配置 ────────────────────────────────────────────────────────────────

@router.put("/{account_id}/scheduled-publish", response_model=AccountRead)
async def update_scheduled_publish(
    account_id: uuid.UUID,
    payload: ScheduledPublishConfig,
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> AccountRead:
    """更新 AI 博主账号的定时发布配置"""
    account = await get_account_or_404(session, account_id, owner_id)
    account.publish_enabled = payload.publish_enabled
    account.publish_cron = payload.publish_cron
    account.publish_window_minutes = payload.publish_window_minutes
    account.publish_count = payload.publish_count
    await session.commit()
    await session.refresh(account)
    bloggers = await _load_bound_bloggers(session, account_id)
    tags = await _load_bound_tags(session, account_id)
    flags = await _load_bound_flags(session, account_id)
    reservations = await _load_channel_reservations(session, account_id)
    return _account_read(account, bloggers, tags, flags, channel_reservations=reservations)


class BulkScheduledPublishFilters(BaseModel):
    gender: str | None = None
    account_type: str | None = None
    face_mode: str | None = None
    product_code_mode: str | None = None
    account_tier: str | None = None
    platform_binding_status: str | None = None
    classification_type: str | None = None
    category_keys: list[str] | None = None
    flag_id: uuid.UUID | None = None
    search: str | None = None


class BulkScheduledPublishBody(BaseModel):
    account_ids: list[uuid.UUID] = Field(default_factory=list)
    filters: BulkScheduledPublishFilters | None = None  # account_ids 为空时用此条件查全量
    config: ScheduledPublishConfig


@router.post("/bulk-update-scheduled-publish", status_code=200)
async def bulk_update_scheduled_publish(
    body: BulkScheduledPublishBody,
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """批量更新 AI 博主定时发布配置。account_ids 为空时用 filters 查全量。"""
    account_ids = list(body.account_ids)
    if not account_ids:
        if body.filters:
            f = body.filters
            all_accounts, _ = await list_accounts(
                session,
                page=None,
                page_size=None,
                owner_id=owner_id,
                gender=f.gender,
                account_type=f.account_type,
                face_mode=f.face_mode,
                product_code_mode=f.product_code_mode,
                account_tier=f.account_tier,
                platform_binding_status=f.platform_binding_status,
                classification_type=f.classification_type,
                category_keys=f.category_keys,
                flag_id=f.flag_id,
                search=f.search,
            )
            account_ids = [a.id for a in all_accounts]
        if not account_ids:
            return {"status": "ok", "updated": 0}

    stmt = select(Account).where(Account.id.in_(account_ids))
    if owner_id is not None:
        stmt = stmt.where(Account.owner_id == owner_id)
    accounts = list((await session.execute(stmt)).scalars().all())

    for account in accounts:
        account.publish_enabled = body.config.publish_enabled
        account.publish_cron = body.config.publish_cron
        account.publish_window_minutes = body.config.publish_window_minutes
        account.publish_count = body.config.publish_count

    await session.commit()
    return {"status": "ok", "updated_count": len(accounts)}


# ── 账号-博主绑定 ─────────────────────────────────────────────────────────────

@router.get("/{account_id}/bloggers", response_model=list[TiktokBloggerRead])
async def list_account_bloggers(
    account_id: uuid.UUID,
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> list[TiktokBloggerRead]:
    """获取账号已绑定的TikTok博主列表。"""
    await get_account_or_404(session, account_id, owner_id)
    stmt = (
        select(TiktokBlogger)
        .join(AccountBloggerBinding, AccountBloggerBinding.tiktok_blogger_id == TiktokBlogger.id)
        .where(AccountBloggerBinding.account_id == account_id)
        .order_by(AccountBloggerBinding.created_at.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return [
        TiktokBloggerRead(
            **{k: getattr(b, k) for k in TiktokBloggerRead.model_fields if k != "video_count" and hasattr(b, k)},
            video_count=0,
        )
        for b in rows
    ]


@router.post("/{account_id}/bloggers", status_code=201)
async def bind_blogger_to_account(
    account_id: uuid.UUID,
    body: BindBloggerBody,
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """绑定TikTok博主到账号。"""
    await get_account_or_404(session, account_id, owner_id)

    blogger = await session.get(TiktokBlogger, body.tiktok_blogger_id)
    if not blogger:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="博主不存在")

    existing = await session.scalar(
        select(AccountBloggerBinding)
        .where(AccountBloggerBinding.account_id == account_id)
        .where(AccountBloggerBinding.tiktok_blogger_id == body.tiktok_blogger_id)
    )
    if existing:
        sync_result = await _ensure_template_tags_for_account(session, account_id, owner_id)
        if sync_result.get("newly_bound", 0) > 0:
            await session.commit()
        return {"status": "already_bound", "template_tag_sync": sync_result}

    binding = AccountBloggerBinding(
        account_id=account_id,
        tiktok_blogger_id=body.tiktok_blogger_id,
        created_at=datetime.now(timezone.utc),
    )
    session.add(binding)
    await session.flush()
    sync_result = await _ensure_template_tags_for_account(session, account_id, owner_id)
    await session.commit()
    return {"status": "bound", "template_tag_sync": sync_result}


@router.delete("/{account_id}/bloggers/{blogger_id}")
async def unbind_blogger_from_account(
    account_id: uuid.UUID,
    blogger_id: uuid.UUID,
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """解绑TikTok博主与账号的关联。"""
    await get_account_or_404(session, account_id, owner_id)
    binding = await session.scalar(
        select(AccountBloggerBinding)
        .where(AccountBloggerBinding.account_id == account_id)
        .where(AccountBloggerBinding.tiktok_blogger_id == blogger_id)
    )
    if binding:
        await session.delete(binding)
        await session.commit()
    return Response(status_code=204)


# ── AI 生成 ──────────────────────────────────────────────────────────────────

@router.post("/{account_id}/ai-generate", status_code=202)
async def trigger_ai_generation(
    account_id: uuid.UUID,
    body: AIGenerateBody,
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """触发 AI 生成博主照片候选、头像和账号资料。"""
    from app.services.ai_account_service import enqueue_ai_account_generation

    await get_account_or_404(session, account_id, owner_id)

    # 先将标签绑定到账号
    tag_ids_str = [str(tid) for tid in body.tag_ids]
    for tag_id in body.tag_ids:
        tag = await session.get(Tag, tag_id)
        if not tag:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"标签 {tag_id} 不存在")
        existing = await session.scalar(
            select(AccountTag)
            .where(AccountTag.account_id == account_id)
            .where(AccountTag.tag_id == tag_id)
        )
        if not existing:
            session.add(AccountTag(account_id=account_id, tag_id=tag_id))

    # 自动绑定 TikTok 博主：从每个标签关联的视频里找 tiktok_blogger_id，
    # 与批量一键生成 (bulk_generate_ai_bloggers) 保持一致。
    # 已绑定的不重复添加（幂等）。
    for tag_id in body.tag_ids:
        blogger_id_row = (
            await session.execute(
                select(VideoSource.tiktok_blogger_id)
                .join(VideoSourceTag, VideoSourceTag.video_source_id == VideoSource.id)
                .where(VideoSourceTag.tag_id == tag_id)
                .where(VideoSource.tiktok_blogger_id.is_not(None))
                .limit(1)
            )
        ).first()
        if not blogger_id_row:
            continue
        tiktok_blogger_id = blogger_id_row[0]
        already_bound = await session.scalar(
            select(AccountBloggerBinding)
            .where(AccountBloggerBinding.account_id == account_id)
            .where(AccountBloggerBinding.tiktok_blogger_id == tiktok_blogger_id)
        )
        if not already_bound:
            session.add(AccountBloggerBinding(
                account_id=account_id,
                tiktok_blogger_id=tiktok_blogger_id,
            ))

    await session.flush()
    sync_result = await _ensure_template_tags_for_account(session, account_id, owner_id)
    await session.commit()

    await enqueue_ai_account_generation(str(account_id), tag_ids_str)
    return {"status": "queued", "template_tag_sync": sync_result}


@router.get("/{account_id}/ai-generate/status", response_model=AIGenerateStatusResponse)
async def get_ai_generation_status(
    account_id: uuid.UUID,
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> AIGenerateStatusResponse:
    """查询 AI 生成状态。"""
    from app.services.ai_account_service import get_ai_account_state

    account = await get_account_or_404(session, account_id, owner_id)

    state = get_ai_account_state(str(account_id))
    if not state:
        state = account.ai_generation_state or {}
    return _ai_generation_response(account_id, state, account)


@router.post("/{account_id}/ai-generate/resume", status_code=202)
async def resume_ai_generation(
    account_id: uuid.UUID,
    body: ResumeAIGenerationBody | None = None,
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """断点续跑：从上次失败/暂停的阶段继续。"""
    from app.services.ai_account_service import resume_ai_account_generation
    await get_account_or_404(session, account_id, owner_id)
    status_value = await resume_ai_account_generation(
        str(account_id),
        from_stage=(body.from_stage if body else "current"),
    )
    return {"status": status_value}


@router.post("/{account_id}/ai-generate/restart", status_code=202)
async def restart_ai_generation(
    account_id: uuid.UUID,
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """从头重试：清空所有已完成阶段，重新执行完整流程。"""
    from app.services.ai_account_service import restart_ai_account_generation
    await get_account_or_404(session, account_id, owner_id)
    await restart_ai_account_generation(str(account_id))
    return {"status": "restarting"}


@router.post("/{account_id}/ai-generate/select-photo", response_model=AIGenerateStatusResponse)
async def select_ai_generation_photo(
    account_id: uuid.UUID,
    body: SelectPhotoCandidateBody,
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> AIGenerateStatusResponse:
    from app.services.ai_account_service import select_ai_account_photo_candidate

    account = await get_account_or_404(session, account_id, owner_id)
    try:
        state = await select_ai_account_photo_candidate(str(account_id), body.candidate_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    refreshed_account = await get_account_or_404(session, account_id, owner_id)
    return _ai_generation_response(account_id, state, refreshed_account)


class BulkRestartAIBody(BaseModel):
    account_ids: list[str]


@router.post("/bulk-resume-ai-generation", response_model=BulkResumeAIAccountsResponse, status_code=202)
async def bulk_resume_ai_generation(
    body: ResumeAIGenerationBody,
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> BulkResumeAIAccountsResponse:
    from app.services.ai_account_service import resume_ai_account_generation

    owner_id = current_user.user_id

    stmt = select(Account.id).where(Account.owner_id == owner_id)

    # 指定账号列表时限定范围
    if body.account_ids:
        stmt = stmt.where(Account.id.in_(body.account_ids))

    # stage 筛选逻辑始终生效
    if body.from_stage == "current":
        stmt = (
            stmt
            .where(Account.ai_generation_status != "completed")
            .where(Account.ai_generation_status != "awaiting_photo_selection")
        )
    else:
        stmt = stmt.where(
            or_(
                Account.ai_generation_status != "idle",
                Account.ai_generation_state.is_not(None),
                Account.photo_url.is_not(None),
                Account.avatar_url.is_not(None),
            )
        )

    stmt = stmt.order_by(Account.created_at.desc())
    account_ids = [str(aid) for aid in (await session.execute(stmt)).scalars().all()]
    if not account_ids:
        return BulkResumeAIAccountsResponse(status="no_accounts", from_stage=body.from_stage)

    resumed_count = 0
    skipped_count = 0
    for aid_str in account_ids:
        try:
            result = await resume_ai_account_generation(aid_str, from_stage=body.from_stage)
            if result in {"resuming", "already_running"}:
                resumed_count += 1
            else:
                skipped_count += 1
        except Exception as exc:
            skipped_count += 1
            logger.error("Failed to bulk resume account %s from stage %s: %s", aid_str, body.from_stage, exc)

    return BulkResumeAIAccountsResponse(
        status="resumed",
        resumed_count=resumed_count,
        skipped_count=skipped_count,
        from_stage=body.from_stage,
    )


@router.post("/bulk-generate-ai-bloggers", response_model=BulkGenerateAIAccountsResponse, status_code=202)
async def bulk_generate_ai_bloggers(
    creator_id: uuid.UUID = Depends(_get_creator_id),
    session: AsyncSession = Depends(get_db),
) -> BulkGenerateAIAccountsResponse:
    """为还没有绑定 AI 博主账号的标签批量创建账号并入队生成。"""
    from app.services.ai_account_service import enqueue_ai_account_generation

    tags_stmt = (
        select(Tag)
        .where(Tag.owner_id == creator_id)
        .where(
            exists(
                select(VideoSourceTag.id)
                .where(VideoSourceTag.tag_id == Tag.id)
                .where(VideoSourceTag.owner_id == creator_id)
                .where(VideoSourceTag.video_source_id.is_not(None))
            )
        )
        .where(
            ~exists(
                select(AccountTag.id)
                .join(Account, Account.id == AccountTag.account_id)
                .where(AccountTag.tag_id == Tag.id)
                .where(Account.owner_id == creator_id)
            )
        )
        .order_by(Tag.created_at.asc())
    )
    tags = (await session.execute(tags_stmt)).scalars().all()
    if not tags:
        return BulkGenerateAIAccountsResponse(status="no_tags")

    created_accounts: list[Account] = []
    created_tag_ids: list[str] = []
    bound_blogger_ids: list = []
    for tag in tags:
        account = Account(
            owner_id=creator_id,
            account_name=f"AI博主生成中 · {tag.name}",
            ai_generation_status="idle",
        )
        session.add(account)
        await session.flush()
        session.add(AccountTag(account_id=account.id, tag_id=tag.id))

        # 通过 tag → video_source_tags → video_sources 找到 tiktok_blogger_id 并绑定
        from app.models.video_source import VideoSource as _VS
        blogger_id_row = (
            await session.execute(
                select(_VS.tiktok_blogger_id)
                .join(VideoSourceTag, VideoSourceTag.video_source_id == _VS.id)
                .where(VideoSourceTag.tag_id == tag.id)
                .where(VideoSourceTag.video_source_id.is_not(None))
                .where(_VS.tiktok_blogger_id.is_not(None))
                .limit(1)
            )
        ).first()
        if blogger_id_row:
            session.add(AccountBloggerBinding(
                account_id=account.id,
                tiktok_blogger_id=blogger_id_row[0],
            ))
            bound_blogger_ids.append(blogger_id_row[0])

        created_accounts.append(account)
        created_tag_ids.append(str(tag.id))

    await session.flush()
    for account in created_accounts:
        await _ensure_template_tags_for_account(session, account.id, creator_id)

    await session.commit()

    for account, tag_id in zip(created_accounts, created_tag_ids, strict=False):
        await enqueue_ai_account_generation(str(account.id), [tag_id])

    # 异步触发绑定博主的人设打标（不阻塞当前请求）
    _blogger_ids_to_tag = list({str(bid) for bid in bound_blogger_ids})
    if _blogger_ids_to_tag:
        import asyncio as _asyncio
        import uuid as _uuid

        async def _trigger_tagging() -> None:
            from app.db.session import SessionLocal as _SessionLocal
            from app.services.persona_tagging_queue_service import enqueue_blogger_tagging
            import logging as _logging
            _log = _logging.getLogger("app.accounts")
            async with _SessionLocal() as _db:
                for _bid_str in _blogger_ids_to_tag:
                    try:
                        await enqueue_blogger_tagging(_uuid.UUID(_bid_str), _db)
                    except Exception as _e:
                        _log.warning(
                            "Failed to enqueue persona tagging for blogger %s: %s", _bid_str, _e
                        )
                await _db.commit()

        _asyncio.create_task(_trigger_tagging())

    return BulkGenerateAIAccountsResponse(
        status="queued",
        created_count=len(created_accounts),
        skipped_count=0,
        queued_count=len(created_accounts),
        created_account_ids=[str(account.id) for account in created_accounts],
        skipped_tag_ids=[],
    )


@router.post("/bulk-persona-tagging", status_code=202)
async def bulk_persona_tagging(
    body: dict,
    creator_id: uuid.UUID = Depends(_get_creator_id),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """
    为已勾选的 AI 博主（或全部）触发绑定 TikTok 博主的人设打标。
    body: { account_ids?: string[], force?: bool }
    force=true 时强制重跑，清除已有打标结果。
    """
    from app.services.persona_tagging_queue_service import enqueue_blogger_tagging
    from app.models.persona_tagging import BloggerTaggingResult, VideoTaggingResult
    from app.models.video_source import VideoSource as _VS

    account_ids = body.get("account_ids") or []
    force = bool(body.get("force", False))

    # 查这批账号绑定的所有 TikTok 博主（去重）
    stmt = (
        select(AccountBloggerBinding.tiktok_blogger_id)
        .join(Account, Account.id == AccountBloggerBinding.account_id)
        .where(Account.owner_id == creator_id)
    )
    if account_ids:
        stmt = stmt.where(AccountBloggerBinding.account_id.in_([uuid.UUID(i) for i in account_ids]))
    blogger_ids = (await session.execute(stmt.distinct())).scalars().all()

    if not blogger_ids:
        return {"queued": 0, "message": "没有找到绑定的 TikTok 博主"}

    if force:
        # 清除这批博主的所有视频打标结果和博主聚合结果
        now_dt = __import__('datetime').datetime.now(__import__('datetime').timezone.utc)
        for bid in blogger_ids:
            # 查博主旗下视频
            from app.services.persona_tagging_service import get_blogger_videos as _gbv
            videos = await _gbv(session, bid)
            video_ids = [uuid.UUID(v["video_id"]) for v in videos]
            if video_ids:
                vt_rows = (await session.execute(
                    select(VideoTaggingResult).where(VideoTaggingResult.video_id.in_(video_ids))
                )).scalars().all()
                for vt in vt_rows:
                    vt.status = "pending"
                    vt.result_code = None
                    vt.result_message = "re-queued"
                    vt.error_code = None
                    vt.error_message = None
                    vt.video_description_unit = None
                    vt.personal_tags = None
                    vt.style_vector = None
                    vt.style_signature = None
                    vt.raw_outputs = None
                    vt.worker_id = None
                    vt.lock_until = None
                    vt.started_at = None
                    vt.finished_at = None
                    vt.updated_at = now_dt
                vs_rows = (await session.execute(
                    select(_VS).where(_VS.id.in_(video_ids))
                )).scalars().all()
                for vs in vs_rows:
                    vs.personal_tags = None
                    vs.style_vector = None
                    vs.tagging_status = "pending"
                    vs.updated_at = now_dt
            # 清空博主聚合结果
            from app.models.tiktok_blogger import TiktokBlogger as _TB
            tb = (await session.execute(select(_TB).where(_TB.id == bid))).scalar_one_or_none()
            if tb:
                tb.persona_tags = None
                tb.style_vector = None
                tb.style_signature = None
                tb.one_sentence_summary = None
                tb.tagging_status = "pending"
                tb.updated_at = now_dt
            # 清空博主任务聚合结果
            bt = (await session.execute(
                select(BloggerTaggingResult).where(BloggerTaggingResult.tiktok_blogger_id == bid)
            )).scalar_one_or_none()
            if bt:
                bt.account_personal_tags = None
                bt.account_style_vector = None
                bt.account_style_signature = None
                bt.account_one_sentence_summary = None
                bt.aggregated_social_identity = None
                bt.aggregated_occasion = None
                bt.raw_outputs = None
                bt.status = "pending"
                bt.result_code = 0
                bt.result_message = "re-queued"
                bt.error_code = None
                bt.error_message = None
                bt.worker_id = None
                bt.lock_until = None
                bt.next_retry_at = None
                bt.started_at = None
                bt.finished_at = None
                bt.updated_at = now_dt
        await session.commit()

    queued = 0
    for blogger_id in blogger_ids:
        task = await enqueue_blogger_tagging(blogger_id, session)
        if task is not None:
            queued += 1

    await session.commit()
    return {"queued": queued, "message": f"已为 {queued} 个博主入队人设打标"}


@router.post("/bulk-restart-ai-generation", status_code=202)
async def bulk_restart_ai_generation(
    body: BulkRestartAIBody,
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """批量重启失败的 AI 生成任务。"""
    from app.services.ai_account_service import restart_ai_account_generation

    if not body.account_ids:
        return {"status": "no_accounts"}

    # 验证权限并获取账号
    await get_account_or_404(session, uuid.UUID(body.account_ids[0]), owner_id)

    # 批量重启
    for aid_str in body.account_ids:
        try:
            aid = uuid.UUID(aid_str)
            acc = await session.get(Account, aid)
            if acc and acc.owner_id == owner_id:
                await restart_ai_account_generation(aid_str)
        except Exception as e:
            logger.error("Failed to restart account %s: %s", aid_str, e)

    return {"status": "restarted", "count": len(body.account_ids)}


@router.post("/bulk-generate-name-handle", response_model=BulkGenerateNameHandleResponse, status_code=202)
async def bulk_generate_name_handle(
    body: BulkGenerateNameHandleBody,
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> BulkGenerateNameHandleResponse:
    """批量为账号 AI 生成名称/Handle/签名。"""
    from app.services.name_handle_service import enqueue_name_handle_generation

    owner_id = current_user.user_id
    stmt = select(Account.id).where(Account.owner_id == owner_id)
    if body.account_ids:
        stmt = stmt.where(Account.id.in_(body.account_ids))

    account_ids = [str(aid) for aid in (await session.execute(stmt)).scalars().all()]
    if not account_ids:
        return BulkGenerateNameHandleResponse(status="no_accounts", queued_count=0)

    queued_count = await enqueue_name_handle_generation(account_ids)
    return BulkGenerateNameHandleResponse(status="queued", queued_count=queued_count)


# ── 账号-标签绑定 ──────────────────────────────────────────────────────────────

@router.get("/{account_id}/tags", response_model=list[BoundTagRead])
async def list_account_tags(
    account_id: uuid.UUID,
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> list[BoundTagRead]:
    """获取账号已绑定的标签列表。"""
    await get_account_or_404(session, account_id, owner_id)
    return await _load_bound_tags(session, account_id)


@router.post("/{account_id}/kol/retry", response_model=AccountRead)
async def retry_kol_provision(
    account_id: uuid.UUID,
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> AccountRead:
    """重试 KOL 创建（仅当当前 status 不是 success 时允许）。

    同步调 ``provision_kol_for_account``，成功后写入 ``kol_user_id`` 和
    ``kol_provision_status='success'``；失败则把错误写到 ``kol_provision_error``。
    """
    from app.services.kol_service import provision_kol_for_account

    account = await get_account_or_404(session, account_id, owner_id)

    # 若 AI 自动生成尚未完成，名称/头像/签名可能仍是占位符，不允许重试
    ai_status = account.ai_generation_status or "idle"
    if ai_status == "running":
        raise HTTPException(
            status_code=409,
            detail="AI 博主生成仍在进行中，请等待生成完成后再重试 KOL 创建",
        )
    if ai_status == "idle" and (account.account_name or "").startswith("AI博主生成中"):
        raise HTTPException(
            status_code=409,
            detail="AI 博主尚未生成完成（名称仍为占位符），KOL 创建将在生成完成后自动触发",
        )

    if account.kol_user_id:
        # 已有 kol_user_id 直接校正状态返回（兼容历史脏数据）
        if account.kol_provision_status != "success":
            account.kol_provision_status = "success"
            account.kol_provision_error = None
            await session.commit()
            await session.refresh(account)
    else:
        if account.kol_provision_status == "success":
            raise HTTPException(status_code=409, detail="KOL 已成功创建，无需重试")
        # 切回 pending，前端立刻看到"KOL 生成中"
        account.kol_provision_status = "pending"
        account.kol_provision_error = None
        await session.commit()

        # provision_kol_for_account 自带 session + try/except，不抛回
        await provision_kol_for_account(account_id)

        await session.refresh(account)

    bloggers = await _load_bound_bloggers(session, account_id)
    tags = await _load_bound_tags(session, account_id)
    flags = await _load_bound_flags(session, account_id)
    reservations = await _load_channel_reservations(session, account_id)
    return _account_read(account, bloggers, tags, flags, channel_reservations=reservations)


@router.post("/{account_id}/tags", status_code=201)
async def bind_tag_to_account(
    account_id: uuid.UUID,
    body: BindTagBody,
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """绑定标签到账号。"""
    await get_account_or_404(session, account_id, owner_id)
    tag = await session.get(Tag, body.tag_id)
    if not tag:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="标签不存在")
    existing = await session.scalar(
        select(AccountTag)
        .where(AccountTag.account_id == account_id)
        .where(AccountTag.tag_id == body.tag_id)
    )
    if existing:
        sync_result = await _ensure_template_tags_for_account(session, account_id, owner_id)
        if sync_result.get("newly_bound", 0) > 0:
            await session.commit()
        return {"status": "already_bound", "template_tag_sync": sync_result}
    session.add(AccountTag(account_id=account_id, tag_id=body.tag_id))
    await session.flush()
    sync_result = await _ensure_template_tags_for_account(session, account_id, owner_id)
    await session.commit()
    return {"status": "bound", "template_tag_sync": sync_result}


@router.post("/{account_id}/sync-template-tags")
async def sync_account_template_tags(
    account_id: uuid.UUID,
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """把绑定博主下已有模板补绑到当前账号 tag。"""
    await get_account_or_404(session, account_id, owner_id)
    try:
        result = await _ensure_template_tags_for_account(session, account_id, owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    await session.commit()
    return {"status": "ok", **result}


@router.delete("/{account_id}/tags/{tag_id}")
async def unbind_tag_from_account(
    account_id: uuid.UUID,
    tag_id: uuid.UUID,
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """解绑标签与账号的关联。"""
    await get_account_or_404(session, account_id, owner_id)
    binding = await session.scalar(
        select(AccountTag)
        .where(AccountTag.account_id == account_id)
        .where(AccountTag.tag_id == tag_id)
    )
    if binding:
        await session.delete(binding)
        await session.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# 补充模板
# ---------------------------------------------------------------------------

class SupplementFiltersBody(BaseModel):
    """补充模板过滤条件（缺省 = 不限）。"""
    min_view_count: int | None = None
    published_after: date | None = None
    max_duration_seconds: int | None = None
    category_keys: list[str] | None = None

    def normalized_category_keys(self) -> list[str]:
        from app.services.video_classification_service import _VALID_KEYS_SET
        if not self.category_keys:
            return []
        values: list[str] = []
        for key in self.category_keys:
            if key not in _VALID_KEYS_SET:
                raise ValueError(f"无效 category_key: {key}")
            if key not in values:
                values.append(key)
        return values


class SupplementTemplatesBody(BaseModel):
    account_ids: list[uuid.UUID] = Field(default_factory=list)
    account_list_filters: AccountListFilters | None = None  # account_ids 为空时后端自查全量
    template_type: str = "shared"  # "shared" | "exclusive"
    # 新版字段 + 兼容旧前端
    target_unused_template_count: int | None = None
    target_video_count: int | None = None
    max_new_videos: int | None = None
    filters: SupplementFiltersBody | None = None


# ---------------------------------------------------------------------------
# 一键生成视频任务
# ---------------------------------------------------------------------------

class AccountListFilters(BaseModel):
    """前端筛选条件，供无 account_ids 时后端自查全量。"""
    gender: str | None = None
    account_type: str | None = None
    face_mode: str | None = None
    product_code_mode: str | None = None
    account_tier: str | None = None
    platform_binding_status: str | None = None
    classification_type: str | None = None
    category_keys: list[str] | None = None
    flag_id: uuid.UUID | None = None
    search: str | None = None


class BulkGenerateVideoTasksBody(BaseModel):
    account_ids: list[uuid.UUID] = Field(default_factory=list)
    filters: AccountListFilters | None = None  # account_ids 为空时用此条件查全量
    mode: str = "unused"         # "unused" | "used"
    fill_mode: str = "count"     # "count" = 每号补 limit 个；"target_total" = 每号补到 limit 个 queued 任务
    limit: int = 0               # 数量值（fill_mode=count 时是新增数；target_total 时是目标 queued 总数）
    subtask_count: int = 3       # 每个任务创建的子任务数量


_BULK_VIDEO_TASK_SKIP_REASON_LABELS = {
    "account_missing": "账号不存在",
    "classification_unavailable": "分类结果不可用",
    "no_tags": "未绑定标签",
    "no_tag_matching_templates": "账号标签下没有模板",
    "no_used_templates": "当前模式无已使用模板",
    "only_used_nonrepeatable_templates": "未用过模式下仅有已使用且不可重复模板",
    "no_templates_for_mode": "当前模式无可生成模板",
    "no_classification_match": "分类不匹配",
    "already_satisfied": "已达目标 queued 数量，无需补充",
}


def _bulk_skip_reason_label(reason: str) -> str:
    return _BULK_VIDEO_TASK_SKIP_REASON_LABELS.get(reason, reason)


def _account_allowed_classification_filters(account: Account) -> tuple[list[int], list[str]]:
    cls_type = account.classification_type
    summary = account.classification_summary or {}
    if cls_type not in {"single", "dual"}:
        return [], []

    index_keys = ["primary_index"]
    major_keys = ["primary_key"]
    if cls_type == "dual":
        index_keys.append("secondary_index")
        major_keys.append("secondary_key")

    allowed_indices: list[int] = []
    for key in index_keys:
        value = summary.get(key)
        if value is not None:
            allowed_indices.append(int(value))

    allowed_major_keys = [
        str(summary[key])
        for key in major_keys
        if summary.get(key)
    ]
    return allowed_indices, allowed_major_keys


async def _matched_classified_video_source_ids(
    session: AsyncSession,
    *,
    video_source_ids: list[uuid.UUID],
    allowed_indices: list[int],
    allowed_major_keys: list[str],
) -> set[uuid.UUID]:
    from app.models.video_classification import VideoClassification

    if not video_source_ids or (not allowed_indices and not allowed_major_keys):
        return set()

    match_clauses = []
    if allowed_indices:
        match_clauses.append(VideoClassification.category_index.in_(allowed_indices))
    if allowed_major_keys:
        match_clauses.append(VideoClassification.major_category.in_(allowed_major_keys))

    rows = (await session.execute(
        select(VideoClassification.video_source_id)
        .where(VideoClassification.video_source_id.in_(video_source_ids))
        .where(VideoClassification.status == "success")
        .where(or_(*match_clauses))
    )).scalars().all()
    return set(rows)


async def _load_bulk_video_task_templates(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    owner_id: uuid.UUID | None,
    use_used: bool,
    with_reason: bool = False,
):
    from app.models.video_ai_template import VideoAITemplate

    account = await session.get(Account, account_id)

    if account is None:
        return ([], "account_missing") if with_reason else []

    # single / dual 走分类硬过滤，兼容旧小类 category_index 与新版大类 major_category
    allowed_indices, allowed_major_keys = _account_allowed_classification_filters(account)

    # ── 按标签查模板池 ────────────────────────────────────────────────────────
    tagged_tpls: list[VideoAITemplate] = []
    tag_stmt = select(AccountTag.tag_id).where(AccountTag.account_id == account_id)
    tag_ids = list((await session.execute(tag_stmt)).scalars().all())
    if not tag_ids:
        return ([], "no_tags") if with_reason else []

    for tid in tag_ids:
        tpl_stmt = (
            select(VideoAITemplate)
            .where(
                exists().where(
                    VideoSourceTag.video_ai_template_id == VideoAITemplate.id,
                    VideoSourceTag.tag_id == tid,
                )
            )
            .order_by(VideoAITemplate.created_at.desc())
        )
        if owner_id is not None:
            tpl_stmt = tpl_stmt.where(VideoAITemplate.owner_id == owner_id)

        rows = (await session.execute(tpl_stmt)).scalars().all()
        tagged_tpls.extend(rows)

    seen: set[uuid.UUID] = set()
    unique_tagged_tpls = []
    for tpl in tagged_tpls:
        if tpl.id in seen:
            continue
        seen.add(tpl.id)
        unique_tagged_tpls.append(tpl)

    if not unique_tagged_tpls:
        return ([], "no_tag_matching_templates") if with_reason else []

    # 不再按 process_status 过滤 fail 模板：fail 状态的模板也允许进候选池
    # （由调用方在 enqueue 时自行处理可能的不完整 shots / prompt_description）

    if use_used:
        unique_tpls = [tpl for tpl in unique_tagged_tpls if tpl.is_used]
        mode_skip_reason = "no_used_templates"
    else:
        unique_tpls = [
            tpl for tpl in unique_tagged_tpls
            if (not tpl.is_used) or tpl.repeatable
        ]
        mode_skip_reason = "only_used_nonrepeatable_templates"

    if not unique_tpls:
        return ([], mode_skip_reason) if with_reason else []

    # 单核心 / 双核心账号：只允许使用与账号 primary/secondary 分类匹配的模板
    if allowed_indices or allowed_major_keys:
        vs_ids = list({tpl.video_source_id for tpl in unique_tpls if tpl.video_source_id})
        matched_vs_ids = await _matched_classified_video_source_ids(
            session,
            video_source_ids=vs_ids,
            allowed_indices=allowed_indices,
            allowed_major_keys=allowed_major_keys,
        )
        unique_tpls = [tpl for tpl in unique_tpls if tpl.video_source_id in matched_vs_ids]
        if not unique_tpls:
            return ([], "no_classification_match") if with_reason else []

    if with_reason:
        return unique_tpls, None
    return unique_tpls


async def _count_queued_tasks(session: AsyncSession, account_id: uuid.UUID) -> int:
    """统计该账号当前 status='queued' 的 video_tasks 数。供 fill_mode='target_total' 使用。"""
    from app.models.video_task import VideoTask
    from sqlalchemy import func as sa_func
    return int(await session.scalar(
        select(sa_func.count(VideoTask.id))
        .where(VideoTask.account_id == account_id)
        .where(VideoTask.status == "queued")
    ) or 0)


async def _count_account_templates(
    session: AsyncSession,
    *,
    account: Account,
    owner_id: uuid.UUID | None,
) -> tuple[int, int]:
    """复用「一键生成」的过滤逻辑，返回 (unused_count, used_count)。
    - unused：not is_used 或 repeatable
    - used：is_used
    已排除不在账号 single/dual 分类下的模板；不再按 process_status 过滤
    （fail 模板也计入；与「一键生成」候选池口径一致）。
    """
    from app.models.video_ai_template import VideoAITemplate

    allowed_indices, allowed_major_keys = _account_allowed_classification_filters(account)

    tag_ids = list((await session.execute(
        select(AccountTag.tag_id).where(AccountTag.account_id == account.id)
    )).scalars().all())
    if not tag_ids:
        return (0, 0)

    tpl_stmt = (
        select(VideoAITemplate)
        .where(
            exists().where(
                VideoSourceTag.video_ai_template_id == VideoAITemplate.id,
                VideoSourceTag.tag_id.in_(tag_ids),
            )
        )
    )
    if owner_id is not None:
        tpl_stmt = tpl_stmt.where(VideoAITemplate.owner_id == owner_id)
    tpls = list((await session.execute(tpl_stmt)).scalars().all())

    if allowed_indices or allowed_major_keys:
        vs_ids = list({t.video_source_id for t in tpls if t.video_source_id})
        matched_vs_ids = await _matched_classified_video_source_ids(
            session,
            video_source_ids=vs_ids,
            allowed_indices=allowed_indices,
            allowed_major_keys=allowed_major_keys,
        )
        tpls = [t for t in tpls if t.video_source_id in matched_vs_ids]

    used_count = sum(1 for t in tpls if t.is_used)
    unused_count = sum(1 for t in tpls if (not t.is_used) or t.repeatable)
    return (unused_count, used_count)


async def _load_vs_map(session: AsyncSession, vs_ids: list[uuid.UUID]) -> dict:
    from app.models.video_source import VideoSource
    if not vs_ids:
        return {}
    rows = (await session.execute(select(VideoSource).where(VideoSource.id.in_(vs_ids)))).scalars().all()
    return {vs.id: vs for vs in rows}


def _sort_tpls_by_view_count(tpls: list, vs_map: dict) -> list:
    """按对应 VideoSource.view_count 降序，None 视为 0；缺 video_source 排到最后。"""
    def _key(t):
        if not t.video_source_id:
            return 0
        vs = vs_map.get(t.video_source_id)
        return -(vs.view_count or 0) if vs else 0
    return sorted(tpls, key=_key)


async def _resolve_account_pool(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    owner_id: uuid.UUID | None,
    use_used: bool,
    fill_mode: str,
    limit: int,
    with_reason: bool = False,
):
    """
    统一在 planning + background 两条链路调用：
    返回 (items_to_use: list, vs_map: dict, skip_reason: str|None)
    items_to_use 是按 view_count 降序、按需求量截取后的最终模板列表。
    """
    unique_tpls, skip_reason = await _load_bulk_video_task_templates(
        session,
        account_id=account_id,
        owner_id=owner_id,
        use_used=use_used,
        with_reason=True,
    )
    if not unique_tpls:
        return [], {}, skip_reason

    vs_ids = list({t.video_source_id for t in unique_tpls if t.video_source_id})
    vs_map = await _load_vs_map(session, vs_ids)
    sorted_tpls = _sort_tpls_by_view_count(unique_tpls, vs_map)

    if fill_mode == "target_total":
        current = await _count_queued_tasks(session, account_id)
        need = max(0, int(limit) - current)
        if need == 0:
            return [], vs_map, "already_satisfied"
    else:  # count
        need = int(limit) if limit and limit > 0 else len(sorted_tpls)

    items_to_use = sorted_tpls[:need]
    return items_to_use, vs_map, None


async def _run_bulk_generate_video_tasks(
    *,
    account_ids: list[uuid.UUID],
    owner_id: uuid.UUID | None,
    user_id: uuid.UUID,
    mode: str,
    fill_mode: str,
    limit: int,
    subtask_count: int,
) -> None:
    from app.services.video_task_service import VideoTaskService

    use_used = mode == "used"
    total_created = 0
    total_failed = 0
    total_skipped = 0

    async with SessionLocal() as session:
        svc = VideoTaskService(db=session)

        for account_id in account_ids:
            try:
                items_to_use, vs_map, _skip_reason = await _resolve_account_pool(
                    session,
                    account_id=account_id,
                    owner_id=owner_id,
                    use_used=use_used,
                    fill_mode=fill_mode,
                    limit=limit,
                )
                if not items_to_use:
                    total_skipped += 1
                    continue

                for tpl in items_to_use:
                    try:
                        dur_s = 0
                        if tpl.video_source_id and tpl.video_source_id in vs_map:
                            dur_s = vs_map[tpl.video_source_id].duration or 0
                        dur_s = min(int(dur_s), 15)
                        duration = f"{dur_s}s" if dur_s else "0s"

                        shots = [
                            {k: v for k, v in s.items() if k != "image_base64"}
                            for s in (tpl.extracted_shots or [])
                        ]
                        await svc.create_task(
                            account_id=account_id,
                            template_id=tpl.id,
                            final_prompt=tpl.prompt_description or "",
                            duration=duration,
                            shots=shots,
                            user_id=user_id,
                            subtask_count=subtask_count,
                        )
                        total_created += 1
                    except Exception:
                        total_failed += 1
            except Exception:
                total_skipped += 1

    logger.info(
        "bulk_generate_video_tasks done: created=%s failed=%s skipped=%s mode=%s fill_mode=%s limit=%s accounts=%s",
        total_created,
        total_failed,
        total_skipped,
        mode,
        fill_mode,
        limit,
        len(account_ids),
    )


@router.post("/bulk-generate-video-tasks", status_code=202)
async def bulk_generate_video_tasks(
    body: BulkGenerateVideoTasksBody,
    current_user: TokenData = Depends(get_current_user),
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """
    为指定账号批量创建视频生成任务。

    - mode=unused / used：取未使用 / 已使用的模板（搭配 repeatable 规则）
    - fill_mode=count：每账号最多创建 limit 个；limit=0 → 无限（全部模板）
    - fill_mode=target_total：每账号补到 limit 个 status='queued' 任务；够了就跳过
    - 模板按对应 video_source.view_count 从高到低排序后取需求量
    - chaos / insufficient / 未分类账号不再被分类硬阻断；仅按标签交集出候选
    - single / dual 仍按小类(category_key)硬过滤
    先计算预计创建的任务数并立即返回，真正创建过程放到后台执行。
    """
    # 无 account_ids 时用 filters 查全量
    account_ids = list(body.account_ids)
    if not account_ids:
        if body.filters:
            f = body.filters
            all_accounts, _ = await list_accounts(
                session,
                page=None,
                page_size=None,
                owner_id=owner_id,
                gender=f.gender,
                account_type=f.account_type,
                face_mode=f.face_mode,
                product_code_mode=f.product_code_mode,
                account_tier=f.account_tier,
                platform_binding_status=f.platform_binding_status,
                classification_type=f.classification_type,
                category_keys=f.category_keys,
                flag_id=f.flag_id,
                search=f.search,
            )
            account_ids = [a.id for a in all_accounts]
        if not account_ids:
            return {"status": "no_accounts", "planned": 0, "skipped_accounts": 0, "account_count": 0}
    if body.fill_mode not in ("count", "target_total"):
        raise HTTPException(status_code=422, detail="fill_mode 必须是 'count' 或 'target_total'")
    if body.fill_mode == "target_total" and body.limit <= 0:
        raise HTTPException(status_code=422, detail="fill_mode=target_total 时 limit 必须 > 0")

    use_used = body.mode == "used"
    total_planned = 0
    total_skipped = 0
    skip_reasons: dict[str, int] = {}

    for account_id in account_ids:
        try:
            items_to_use, _vs_map, skip_reason = await _resolve_account_pool(
                session,
                account_id=account_id,
                owner_id=owner_id,
                use_used=use_used,
                fill_mode=body.fill_mode,
                limit=body.limit,
                with_reason=True,
            )
            if not items_to_use:
                total_skipped += 1
                if skip_reason:
                    skip_reasons[skip_reason] = skip_reasons.get(skip_reason, 0) + 1
                continue
            total_planned += len(items_to_use)
        except Exception as exc:
            logger.warning("bulk_generate_video_tasks planning failed account=%s: %s", account_id, exc)
            total_skipped += 1
            skip_reasons["error"] = skip_reasons.get("error", 0) + 1

    skip_summary = "，".join(
        f"{_bulk_skip_reason_label(reason)} {count} 个"
        for reason, count in sorted(skip_reasons.items())
    )
    skipped_text = ""
    if total_skipped > 0:
        skipped_text = f"，{total_skipped} 个账号没有符合条件的模板"
        if skip_summary:
            skipped_text += f"（{skip_summary}）"

    asyncio.create_task(
        _run_bulk_generate_video_tasks(
            account_ids=account_ids,
            owner_id=owner_id,
            user_id=current_user.user_id,
            mode=body.mode,
            fill_mode=body.fill_mode,
            limit=body.limit,
            subtask_count=body.subtask_count,
        )
    )

    return {
        "status": "queued",
        "planned": total_planned,
        "skipped_accounts": total_skipped,
        "skip_reasons": skip_reasons,
        "account_count": len(account_ids),
        "message": f"后台已启动，预计创建 {total_planned} 个生成任务{skipped_text}",
    }


async def _resolve_account_ids(
    body_account_ids: list[uuid.UUID],
    body_account_list_filters: AccountListFilters | None,
    session: AsyncSession,
    owner_id: uuid.UUID | None,
) -> list[uuid.UUID]:
    """account_ids 非空直接返回；为空时用 account_list_filters 查全量。"""
    if body_account_ids:
        return list(body_account_ids)
    if body_account_list_filters:
        f = body_account_list_filters
        accounts, _ = await list_accounts(
            session,
            page=None,
            page_size=None,
            owner_id=owner_id,
            gender=f.gender,
            account_type=f.account_type,
            face_mode=f.face_mode,
            product_code_mode=f.product_code_mode,
            account_tier=f.account_tier,
            platform_binding_status=f.platform_binding_status,
            classification_type=f.classification_type,
            category_keys=f.category_keys,
            flag_id=f.flag_id,
            search=f.search,
        )
        return [a.id for a in accounts]
    return []


def _resolve_target_unused_count(body: SupplementTemplatesBody | "AutoSupplementBody") -> int:
    """target_unused_template_count 优先；兼容旧 target_video_count / max_new_videos。"""
    n = (
        getattr(body, "target_unused_template_count", None)
        or getattr(body, "target_video_count", None)
        or getattr(body, "max_new_videos", None)
    )
    return int(n) if n and int(n) > 0 else 10


@router.post("/supplement-templates", status_code=200)
async def supplement_templates(
    body: SupplementTemplatesBody,
    creator_id: uuid.UUID = Depends(_get_creator_id),
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
):
    """
    为指定账号批量补充模板（后台异步执行，立即返回）。

    - `template_type=exclusive`：走 vendor outbound（StyleDNA），由 callback 入库；vendor 未配/失败直接报错，不 fallback
    - `template_type=shared`：走内部 candidate_service（按 tag 关键词搜索）
    """
    from app.services.candidate_service import supplement_templates_for_accounts
    from app.services.external_supplement_service import (
        submit_supplement_request, _vendor_configured,
    )
    import asyncio as _asyncio

    account_ids = await _resolve_account_ids(
        body.account_ids, body.account_list_filters, session, owner_id
    )
    if not account_ids:
        return {"message": "无账号，跳过", "count": 0}

    template_type = body.template_type if body.template_type in ("shared", "exclusive") else "shared"
    target_count = _resolve_target_unused_count(body)
    effective_owner = owner_id if owner_id is not None else creator_id
    filters_dict = body.filters.model_dump(mode="json", exclude_none=True) if body.filters else {}
    if body.filters and body.filters.category_keys is not None:
        try:
            category_keys = body.filters.normalized_category_keys()
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if category_keys:
            filters_dict["category_keys"] = category_keys
        else:
            filters_dict.pop("category_keys", None)

    from app.services.template_supplement_service import build_account_top_up_plan

    plans = []
    for account_id in account_ids:
        plan = await build_account_top_up_plan(
            session,
            account_id=account_id,
            owner_id=effective_owner,
            mode="exclusive" if template_type == "exclusive" else "shared",
            target_unused_template_count=target_count,
            filters=filters_dict,
        )
        plans.append(plan)
    await session.commit()
    need_plans = [p for p in plans if p.need_count > 0 and not p.skip_reason]
    skipped_accounts = len(plans) - len(need_plans)
    if not need_plans:
        return {
            "message": f"所有账号都已达到目标未使用模板数或不可补充，跳过 {skipped_accounts} 个",
            "count": 0,
            "skipped_accounts": skipped_accounts,
        }

    # exclusive 模式：只走 vendor，失败/未配置直接报错
    if template_type == "exclusive":
        if not _vendor_configured():
            raise HTTPException(status_code=503, detail="vendor 未配置（VENDOR_SUPPLEMENT_API_URL / API_KEY）")
        grouped: dict[int, list[uuid.UUID]] = {}
        for plan in need_plans:
            grouped.setdefault(plan.need_count, []).append(plan.account_id)
        request_ids: list[str] = []
        submitted_items = 0
        try:
            for need_count, grouped_account_ids in grouped.items():
                context_by_account = {
                    str(plan.account_id): {
                        "target_unused_template_count": target_count,
                        "initial_unused_template_count": plan.current_unused_template_count,
                        "current_unused_template_count": plan.current_unused_template_count,
                        "requested_video_count": need_count,
                        "round_index": 1,
                    }
                    for plan in need_plans
                    if plan.need_count == need_count
                }
                result = await submit_supplement_request(
                    owner_id=effective_owner,
                    account_ids=grouped_account_ids,
                    mode="exclusive",
                    target_video_count=need_count,
                    filters=filters_dict,
                    item_context_by_account=context_by_account,
                )
                request_ids.append(result["request_id"])
                submitted_items += result["submitted_items"]
        except Exception as exc:
            logger.error("vendor outbound 失败: %s", exc)
            raise HTTPException(status_code=502, detail=f"vendor outbound 失败: {exc}")
        return {
            "message": f"已按目标未使用模板数为 {submitted_items} 个账号补充模板，跳过 {skipped_accounts} 个",
            "count": submitted_items,
            "skipped_accounts": skipped_accounts,
            "request_ids": request_ids,
        }

    # shared 模式：内部 candidate_service
    async def _run_shared_top_up() -> None:
        for plan in need_plans:
            await supplement_templates_for_accounts(
                account_ids=[plan.account_id],
                owner_id=effective_owner,
                template_type=template_type,
                max_new_videos=plan.need_count,
            )

    _asyncio.create_task(_run_shared_top_up())
    return {
        "message": f"已按目标未使用模板数为 {len(need_plans)} 个账号启动共享补充，跳过 {skipped_accounts} 个",
        "count": len(need_plans),
        "skipped_accounts": skipped_accounts,
    }


class AutoSupplementBody(BaseModel):
    account_ids: list[uuid.UUID] = Field(default_factory=list)
    account_list_filters: AccountListFilters | None = None  # account_ids 为空时后端自查全量
    target_unused_template_count: int | None = None
    target_video_count: int | None = None
    max_new_videos: int | None = None
    filters: SupplementFiltersBody | None = None


@router.post("/auto-supplement-templates", status_code=200)
async def auto_supplement_templates(
    body: AutoSupplementBody,
    creator_id: uuid.UUID = Depends(_get_creator_id),
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
):
    """
    根据 AI 博主分类类型自动补充匹配视频模板。
    只走 vendor outbound；vendor 未配置 / 失败直接报错，不 fallback。
    """
    from app.services.external_supplement_service import (
        submit_supplement_request, _vendor_configured,
    )

    account_ids = await _resolve_account_ids(
        body.account_ids, body.account_list_filters, session, owner_id
    )
    if not account_ids:
        return {"message": "无账号，跳过", "count": 0}

    target_count = _resolve_target_unused_count(body)
    effective_owner = owner_id if owner_id is not None else creator_id
    filters_dict = body.filters.model_dump(mode="json", exclude_none=True) if body.filters else {}
    from app.services.template_supplement_service import build_account_top_up_plan
    plans = []
    for account_id in account_ids:
        plan = await build_account_top_up_plan(
            session,
            account_id=account_id,
            owner_id=effective_owner,
            mode="auto",
            target_unused_template_count=target_count,
            filters=filters_dict,
        )
        plans.append(plan)
    await session.commit()
    need_plans = [p for p in plans if p.need_count > 0 and not p.skip_reason]
    skipped_accounts = len(plans) - len(need_plans)
    if not need_plans:
        return {
            "message": f"所有账号都已达到目标未使用模板数或不可自动补充，跳过 {skipped_accounts} 个",
            "count": 0,
            "skipped_accounts": skipped_accounts,
        }

    if not _vendor_configured():
        raise HTTPException(status_code=503, detail="vendor 未配置（VENDOR_SUPPLEMENT_API_URL / API_KEY）")
    grouped: dict[int, list[uuid.UUID]] = {}
    for plan in need_plans:
        grouped.setdefault(plan.need_count, []).append(plan.account_id)
    request_ids: list[str] = []
    submitted_items = 0
    try:
        for need_count, grouped_account_ids in grouped.items():
            context_by_account = {
                str(plan.account_id): {
                    "target_unused_template_count": target_count,
                    "initial_unused_template_count": plan.current_unused_template_count,
                    "current_unused_template_count": plan.current_unused_template_count,
                    "requested_video_count": need_count,
                    "round_index": 1,
                }
                for plan in need_plans
                if plan.need_count == need_count
            }
            result = await submit_supplement_request(
                owner_id=effective_owner,
                account_ids=grouped_account_ids,
                mode="auto",
                target_video_count=need_count,
                filters=filters_dict,
                item_context_by_account=context_by_account,
            )
            request_ids.append(result["request_id"])
            submitted_items += result["submitted_items"]
    except Exception as exc:
        logger.error("vendor outbound 失败: %s", exc)
        raise HTTPException(status_code=502, detail=f"vendor outbound 失败: {exc}")
    return {
        "message": f"已按目标未使用模板数为 {submitted_items} 个账号自动补充，跳过 {skipped_accounts} 个",
        "count": submitted_items,
        "skipped_accounts": skipped_accounts,
        "request_ids": request_ids,
    }


# ---------------------------------------------------------------------------
# 标签搜索（Hashtag Search）
# ---------------------------------------------------------------------------

class BulkSearchHashtagsBody(BaseModel):
    account_ids: list[uuid.UUID] | None = None  # None = 当前用户全部账号
    mode: str = "replace"                        # "replace" | "merge"


@router.post("/bulk-search-hashtags", status_code=202)
async def bulk_search_hashtags(
    body: BulkSearchHashtagsBody,
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """
    批量标签搜索并绑定（后台异步执行）：
    1. 找到所选账号绑定的 TikTok 博主
    2. 用 Apify 抓取每个博主最热门视频（top_n 由配置决定，默认 100）
    3. 提取 hashtag 去重
    4. AI 过滤（需在 AI博主配置中填写提示词）
    5. 将结果写入各账号的 hashtags 字段（mode=replace 覆盖 / mode=merge 追加）
    """
    import asyncio as _asyncio
    from app.services.hashtag_search_service import search_and_bind_hashtags_for_accounts

    owner_id = current_user.user_id

    # 确定账号范围
    stmt = select(Account.id).where(Account.owner_id == owner_id)
    if body.account_ids:
        stmt = stmt.where(Account.id.in_(body.account_ids))
    account_ids = [str(aid) for aid in (await session.execute(stmt)).scalars().all()]

    if not account_ids:
        raise HTTPException(status_code=400, detail="没有找到符合条件的账号")

    _asyncio.create_task(
        search_and_bind_hashtags_for_accounts(
            account_ids=account_ids,
            owner_id=str(owner_id),
            mode=body.mode,
        )
    )
    return {"status": "queued", "account_count": len(account_ids)}


class BulkBindHashtagsBody(BaseModel):
    account_ids: list[uuid.UUID] | None = None  # None = 当前用户全部账号
    hashtags: list[str]                          # 要绑定的 hashtag 列表（不含 #）
    mode: str = "replace"                        # "replace" | "merge"


@router.post("/bulk-bind-hashtags", status_code=200)
async def bulk_bind_hashtags(
    body: BulkBindHashtagsBody,
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """
    将 hashtag 列表批量绑定到指定账号。
    mode=replace：直接覆盖账号的 hashtags 字段。
    mode=merge：与现有 hashtags 合并去重。
    """
    owner_id = current_user.user_id

    stmt = select(Account).where(Account.owner_id == owner_id)
    if body.account_ids:
        stmt = stmt.where(Account.id.in_(body.account_ids))
    accounts = (await session.execute(stmt)).scalars().all()

    if not accounts:
        return {"updated_count": 0, "message": "没有找到符合条件的账号"}

    clean_tags = [t.strip().lstrip("#") for t in body.hashtags if t.strip()]

    for acc in accounts:
        if body.mode == "merge" and acc.hashtags:
            existing = list(acc.hashtags)
            existing_lower = {t.lower() for t in existing}
            merged = existing + [t for t in clean_tags if t.lower() not in existing_lower]
            acc.hashtags = merged
        else:
            acc.hashtags = clean_tags

    await session.commit()
    return {"updated_count": len(accounts), "message": f"已为 {len(accounts)} 个账号绑定 {len(clean_tags)} 个标签"}


class ExportVideoUrlsBody(BaseModel):
    account_ids: list[uuid.UUID] | None = None  # None = 全部


@router.post("/export-video-urls")
async def export_video_urls(
    body: ExportVideoUrlsBody = ExportVideoUrlsBody(),
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """导出 AI 博主关联的 TikTok 博主原视频 local_video_url，生成合并单元格 Excel。"""
    import io
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from app.models.video_source import VideoSource

    owner_id = current_user.user_id

    # 查所有目标账号
    stmt = select(Account).where(Account.owner_id == owner_id)
    if body.account_ids:
        stmt = stmt.where(Account.id.in_(body.account_ids))
    stmt = stmt.order_by(Account.created_at.asc())
    accounts = (await session.execute(stmt)).scalars().all()

    # 对每个账号查绑定的 TiktokBlogger，再查 VideoSource
    rows: list[tuple[Account, TiktokBlogger | None, str]] = []  # (account, blogger, local_video_url)
    for acc in accounts:
        bloggers_stmt = (
            select(TiktokBlogger)
            .join(AccountBloggerBinding, AccountBloggerBinding.tiktok_blogger_id == TiktokBlogger.id)
            .where(AccountBloggerBinding.account_id == acc.id)
        )
        bloggers = (await session.execute(bloggers_stmt)).scalars().all()

        if not bloggers:
            rows.append((acc, None, ""))
            continue

        for blogger in bloggers:
            vs_stmt = (
                select(VideoSource.local_video_url, VideoSource.local_gcs_video_url)
                .where(VideoSource.tiktok_blogger_id == blogger.id)
                .where(
                    or_(
                        and_(VideoSource.local_video_url.is_not(None), VideoSource.local_video_url != ""),
                        and_(VideoSource.local_gcs_video_url.is_not(None), VideoSource.local_gcs_video_url != ""),
                    )
                )
                .order_by(VideoSource.created_at.asc())
            )
            url_pairs = (await session.execute(vs_stmt)).all()
            if url_pairs:
                for cdn_url, gcs_url in url_pairs:
                    rows.append((acc, blogger, cdn_url or gcs_url or ""))
            else:
                rows.append((acc, blogger, ""))

    # 生成 Excel
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "AI博主视频导出"

    header_fill = PatternFill("solid", fgColor="4F46E5")
    header_font = Font(bold=True, color="FFFFFF")
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    wrap = Alignment(vertical="top", wrap_text=True)

    headers = ["AI博主名称", "性别", "TikTok博主", "原视频URL"]
    ws.append(headers)
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center

    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 10
    ws.column_dimensions["C"].width = 22
    ws.column_dimensions["D"].width = 80
    ws.row_dimensions[1].height = 22

    # 写数据并合并单元格
    data_row = 2
    # 按 account 分组计算行范围
    from itertools import groupby
    acc_grouped: list[tuple[Account, list[tuple[Account, TiktokBlogger | None, str]]]] = []
    for acc_obj, group in groupby(rows, key=lambda r: r[0].id):
        group_rows = list(group)
        acc_grouped.append((group_rows[0][0], group_rows))

    for acc, group in acc_grouped:
        start_row = data_row
        for _, blogger, url in group:
            ws.cell(row=data_row, column=1, value=acc.account_name).alignment = center
            ws.cell(row=data_row, column=2, value=acc.gender).alignment = center
            ws.cell(row=data_row, column=3, value=blogger.blogger_name if blogger else "").alignment = center
            ws.cell(row=data_row, column=4, value=url).alignment = wrap
            data_row += 1

        end_row = data_row - 1
        if end_row > start_row:
            ws.merge_cells(f"A{start_row}:A{end_row}")
            ws.merge_cells(f"B{start_row}:B{end_row}")

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    return Response(
        content=buf.read(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=ai_blogger_videos.xlsx"},
    )


# ---------------------------------------------------------------------------
# 视频分类（按 AI 博主）
# ---------------------------------------------------------------------------


class ClassifyVideosRequest(BaseModel):
    force: bool = False


@router.post("/{account_id}/classify-videos", status_code=202)
async def trigger_account_classification(
    account_id: uuid.UUID,
    body: ClassifyVideosRequest = ClassifyVideosRequest(),
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
) -> dict:
    from app.services.video_classification_service import enqueue_account_classification

    try:
        result = await enqueue_account_classification(account_id, owner_id, force=body.force)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"status": "queued", **result}


@router.post("/{account_id}/classify-videos/retry-failed", status_code=202)
async def retry_account_classification_failed(
    account_id: uuid.UUID,
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
) -> dict:
    from app.services.video_classification_service import retry_failed_classifications

    try:
        result = await retry_failed_classifications(account_id, owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return {"status": "queued", **result}


@router.get("/{account_id}/classification")
async def get_account_classification(
    account_id: uuid.UUID,
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
) -> dict:
    from app.services.video_classification_service import (
        CATEGORY_LABELS,
        CATEGORY_MAJOR,
        MAJOR_LABELS,
        get_account_classification_view,
    )

    try:
        view = await get_account_classification_view(account_id, owner_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return {
        **view,
        "categories": [
            {"index": idx, "label": label, "major": CATEGORY_MAJOR[idx]}
            for idx, label in CATEGORY_LABELS.items()
        ],
        "major_labels": MAJOR_LABELS,
    }


class BatchClassifyRequest(BaseModel):
    ids: list[uuid.UUID] = Field(default_factory=list)
    account_list_filters: AccountListFilters | None = None  # ids 为空时后端自查全量
    force: bool = False


@router.post("/batch-classify-videos", status_code=202)
async def batch_classify_videos(
    body: BatchClassifyRequest,
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> dict:
    from app.services.video_classification_service import enqueue_account_classification

    account_ids = await _resolve_account_ids(
        body.ids, body.account_list_filters, session, owner_id
    )
    if not account_ids:
        return {"status": "queued", "total_queued": 0, "results": []}

    results: list[dict] = []
    for account_id in account_ids:
        try:
            r = await enqueue_account_classification(account_id, owner_id, force=body.force)
            results.append({"account_id": str(account_id), **r})
        except ValueError:
            results.append({"account_id": str(account_id), "queued": 0, "skipped": 0, "error": "not_found"})
    total_queued = sum(r.get("queued", 0) for r in results)
    return {"status": "queued", "total_queued": total_queued, "results": results}


@router.get("/{account_id}/channel-analytics", response_model=ChannelAnalyticsResponse)
async def get_channel_analytics(
    account_id: uuid.UUID,
    platform: str = Query(..., description="youtube / tiktok / instagram"),
    start_date: date = Query(..., description="YYYY-MM-DD"),
    end_date: date = Query(..., description="YYYY-MM-DD"),
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> ChannelAnalyticsResponse:
    """返回指定账号、平台的频道数据分析（views 趋势 + Link 点击趋势）。"""
    import asyncio
    from app.services.ext.bigquery_service.kol_analytics import (
        get_channel_daily_views,
        get_kol_daily_clicks,
    )

    account = await get_account_or_404(session, account_id, owner_id)

    reservation = await session.scalar(
        select(AccountChannelReservation)
        .where(AccountChannelReservation.account_id == account_id)
        .where(AccountChannelReservation.platform == platform.lower())
    )
    if not reservation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"该账号未绑定 {platform} 平台",
        )

    channel_id = reservation.channel_id
    kol_user_id = account.kol_user_id

    # 并发查询两个 BigQuery 数据源（同步阻塞函数放到线程池）
    loop = asyncio.get_running_loop()

    async def _fetch_daily_views():
        if not channel_id:
            return []
        return await loop.run_in_executor(
            None,
            get_channel_daily_views,
            channel_id,
            platform.lower(),
            start_date,
            end_date,
        )

    async def _fetch_daily_clicks():
        if not kol_user_id:
            return []
        return await loop.run_in_executor(
            None,
            get_kol_daily_clicks,
            kol_user_id,
            start_date,
            end_date,
        )

    # 从本地 DB 查询该 channel 下已发布视频的总 views
    # 路径：video_publications.completed_at IS NOT NULL
    #        → video_sub_tasks.task_id → video_tasks.account_id == account_id
    #        + metrics_snapshot.channels[].{platform, channel_id, stats.view_count/views}
    async def _fetch_total_video_views() -> int:
        if not channel_id:
            return 0
        target_platform = platform.lower()
        target_channel_id = channel_id

        pubs = (await session.execute(
            select(VideoPublication)
            .join(VideoSubTask, VideoSubTask.id == VideoPublication.sub_task_id)
            .join(VideoTask, VideoTask.id == VideoSubTask.task_id)
            .where(VideoTask.account_id == account_id)
            .where(VideoPublication.completed_at.isnot(None))
            .where(VideoPublication.metrics_snapshot.isnot(None))
        )).scalars().all()

        total = 0
        for pub in pubs:
            snapshot = pub.metrics_snapshot
            if not isinstance(snapshot, dict):
                continue
            for ch in (snapshot.get("channels") or []):
                if not isinstance(ch, dict):
                    continue
                if str(ch.get("platform") or "").lower() != target_platform:
                    continue
                if str(ch.get("channel_id") or "") != target_channel_id:
                    continue
                stats = ch.get("stats") or {}
                v = stats.get("views") if target_platform == "youtube" else stats.get("view_count")
                total += int(v or 0)
        return total

    daily_views, daily_clicks, total_video_views = await asyncio.gather(
        _fetch_daily_views(),
        _fetch_daily_clicks(),
        _fetch_total_video_views(),
    )

    total_link_clicks = sum(p["daily_clicks"] for p in daily_clicks)

    return ChannelAnalyticsResponse(
        platform=platform.lower(),
        channel_id=channel_id,
        kol_user_id=kol_user_id,
        daily_views=daily_views,
        daily_clicks=daily_clicks,
        total_link_clicks=total_link_clicks,
        total_video_views=total_video_views,
    )
