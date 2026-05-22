from __future__ import annotations

import asyncio
import hmac
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.models.account import Account
from app.models.account_channel_reservation import AccountChannelReservation
from app.services.channel_status_poller import (
    query_channel_authorization,
    refresh_reservation_channel_status,
)
from app.services.account_service import recompute_account_platform_binding_status
from app.services.kol_service import build_long_link, encode_short_link
from app.schemas.account import (
    ExternalBindOpenAPIChannelBody,
    ExternalBindOpenAPIChannelResponse,
    ExternalAIAccountCandidateItem,
    ExternalChannelReservationRead,
    ExternalConfirmChannelReservationBody,
    ExternalConfirmChannelReservationResponse,
    ExternalLinkInfoItem,
    ExternalReserveAIAccountsBody,
    ExternalReserveAIAccountsResponse,
    ExternalReleaseChannelReservationBody,
)

LINK_INFO_NAME = "Outfit details below ⬇️"

router = APIRouter(prefix="/open-api/accounts", tags=["open-api-account-channels"])
logger = logging.getLogger("app.account_channel_reservations")


def _mask_api_key(value: str | None) -> str:
    if not value:
        return ""
    if len(value) <= 6:
        return "***"
    return f"{value[:4]}***{value[-2:]}"


def _resolve_owner_id(body_owner_id: uuid.UUID | None) -> uuid.UUID:
    if body_owner_id is not None:
        return body_owner_id
    default = settings.account_channel_owner_id
    if not default:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="owner_id 未传且服务端未配置 ACCOUNT_CHANNEL_OWNER_ID",
        )
    try:
        return uuid.UUID(default)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="服务端 ACCOUNT_CHANNEL_OWNER_ID 格式无效",
        )


def _verify_api_key(body_api_key: str = "", header_api_key: str | None = None) -> None:
    expected = settings.account_channel_api_key
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ACCOUNT_CHANNEL_API_KEY 未配置",
        )
    supplied = header_api_key or body_api_key or ""
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid api_key")


async def _build_kol_links_for_account(
    account: Account, platform: str,
) -> tuple[str | None, str | None]:
    """为 (account, platform) 生成 (long_link, short_link)。

    没有 ``kol_user_id`` 或短链 API 失败时返回 (None, None)；不抛异常。
    """
    if not account.kol_user_id:
        return None, None
    long_link = build_long_link(account.kol_user_id, platform)
    try:
        encoded = await encode_short_link(long_link)
    except Exception:
        logger.exception(
            "reserve_ai_accounts short link encode failed: account=%s platform=%s",
            account.id, platform,
        )
        return long_link, None
    return long_link, encoded.get("short") or None


def _channel_binding_payload(body: ExternalBindOpenAPIChannelBody) -> dict:
    return {
        "platform": body.platform,
        "channel_source": body.channel_source or "openapi",
        "channel_id": body.channel_id,
        "channel_name": body.channel_name,
        "username": body.username,
    }


def _apply_channel_binding(
    reservation: AccountChannelReservation,
    binding: dict,
    *,
    now: datetime,
) -> None:
    source = str(binding.get("channel_source") or binding.get("source") or reservation.source or "openapi")
    reservation.status = "bound"
    reservation.source = source
    reservation.channel_source = source
    reservation.channel_id = str(binding.get("channel_id") or "") or None
    reservation.channel_name = str(binding.get("channel_name") or "") or None
    reservation.username = str(binding.get("username") or "") or None
    reservation.avatar_url = str(binding.get("avatar_url") or "") or None
    reservation.channel_info = None
    reservation.confirmed_at = reservation.confirmed_at or now
    reservation.bound_at = now


@router.post("/channel-reservations", response_model=ExternalReserveAIAccountsResponse, status_code=201)
async def reserve_ai_accounts_for_channel_openapi(
    body: ExternalReserveAIAccountsBody,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    session: AsyncSession = Depends(get_db),
) -> ExternalReserveAIAccountsResponse:
    """外部团队按 owner、性别、平台查询可用 AI 博主，并立即 confirm 占用，避免并发重复领取。"""
    logger.info(
        "reserve_ai_accounts request: owner_id=%s gender=%s platform=%s count=%s source=%s "
        "api_key_header=%s api_key_body=%s",
        body.owner_id,
        body.gender,
        body.platform,
        body.count,
        body.source,
        _mask_api_key(x_api_key),
        _mask_api_key(body.api_key),
    )
    _verify_api_key(body.api_key, x_api_key)
    owner_id = _resolve_owner_id(body.owner_id)

    platform = body.platform.lower()
    # FOR UPDATE SKIP LOCKED: 并发请求各自锁定不重叠的行，保证 count 准确
    stmt = (
        select(Account)
        .where(Account.owner_id == owner_id)
        .where(Account.gender == body.gender)
        .where(Account.ai_generation_status == "completed")
        .where(
            ~exists()
            .where(AccountChannelReservation.account_id == Account.id)
            .where(AccountChannelReservation.platform == platform)
        )
        .order_by(Account.created_at.asc())
        .limit(body.count)
        .with_for_update(skip_locked=True)
    )

    now = datetime.now(timezone.utc)
    items: list[ExternalAIAccountCandidateItem] = []
    confirmed_count = 0

    accounts = (await session.execute(stmt)).scalars().all()

    # 并发跑 build_long_link + encode_short_link（每条账号一对长/短链）
    link_pairs: list[tuple[str | None, str | None]] = []
    if accounts:
        link_pairs = list(await asyncio.gather(
            *(_build_kol_links_for_account(account, platform) for account in accounts)
        ))

    for account, (long_link, short_link) in zip(accounts, link_pairs, strict=True):
        reservation = AccountChannelReservation(
            account_id=account.id,
            platform=platform,
            status="confirmed",
            source=body.source,
            channel_source=body.source,
            kol_long_link=long_link,
            kol_short_link=short_link,
            reserved_at=now,
            confirmed_at=now,
        )
        session.add(reservation)
        confirmed_count += 1
        link_info = (
            [ExternalLinkInfoItem(name=LINK_INFO_NAME, link=short_link)]
            if short_link
            else None
        )
        items.append(
            ExternalAIAccountCandidateItem(
                account_id=account.id,
                platform=body.platform,
                account_name=account.account_name,
                account_handle=account.account_handle,
                account_signature=account.account_signature,
                hashtags=account.hashtags,
                avatar_url=account.avatar_url,
                confirmed=True,
                link_info=link_info,
            )
        )

    try:
        for account in accounts:
            await recompute_account_platform_binding_status(session, account.id)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="部分账号已被其他请求占用，请稍后重试",
        )
    response = ExternalReserveAIAccountsResponse(
        items=items,
        requested_count=body.count,
        returned_count=len(items),
        confirmed_count=confirmed_count,
    )
    logger.info(
        "reserve_ai_accounts response summary: owner_id=%s platform=%s requested=%s returned=%s confirmed=%s account_ids=%s",
        owner_id,
        platform,
        body.count,
        len(items),
        confirmed_count,
        [str(it.account_id) for it in items],
    )
    logger.info(
        "reserve_ai_accounts response body: %s",
        response.model_dump(mode="json"),
    )
    return response


@router.post("/channel-reservations/confirm", response_model=ExternalConfirmChannelReservationResponse)
async def confirm_channel_reservation_openapi(
    body: ExternalConfirmChannelReservationBody,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
) -> ExternalConfirmChannelReservationResponse:
    """占用已由 reserve 接口完成，此接口直接返回成功（兼容旧调用方）。"""
    _verify_api_key(body.api_key, x_api_key)
    owner_id = _resolve_owner_id(body.owner_id)
    return ExternalConfirmChannelReservationResponse(
        status="confirmed",
        owner_id=owner_id,
        account_id=body.account_id,
        platform=body.platform,
    )


@router.post("/{account_id}/channel-bindings", response_model=ExternalBindOpenAPIChannelResponse)
async def bind_openapi_channel_openapi(
    account_id: uuid.UUID,
    body: ExternalBindOpenAPIChannelBody,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    session: AsyncSession = Depends(get_db),
) -> ExternalBindOpenAPIChannelResponse:
    """外部团队绑定频道信息到 AI 博主。

    若该账号该平台已绑定（status='bound'），直接返回当前绑定信息，不修改任何字段、
    不报错；调用方需要重绑请先调 release 释放。
    """
    _verify_api_key(body.api_key, x_api_key)
    owner_id = _resolve_owner_id(body.owner_id)

    account = await session.scalar(
        select(Account)
        .where(Account.id == account_id)
        .where(Account.owner_id == owner_id)
    )
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")

    platform = body.platform.lower()

    # 优先以 Open API authorization 接口返回的 channel 信息为准：调用方传 username
    # 时往往不知道平台真实的 channel_id（如 TikTok 的 users.id、Instagram 的 account_id），
    # Open API 会根据 username/handle 反查并返回规范化的 {platform, channel_id, channel_name}。
    # 没有 username 时回退用 body.channel_id 做查询键。
    binding_payload = _channel_binding_payload(body)
    lookup_key = (body.username or body.channel_id or "").strip()
    if lookup_key:
        try:
            auth_result = await query_channel_authorization(platform, lookup_key)
        except Exception as exc:
            logger.warning(
                "bind_openapi_channel_openapi: authorization 查询失败 account_id=%s platform=%s lookup=%s err=%s",
                account_id, platform, lookup_key, exc,
            )
            auth_result = None
        auth_channel = (auth_result or {}).get("channel") if auth_result else None
        if isinstance(auth_channel, dict):
            if auth_channel.get("channel_id"):
                binding_payload["channel_id"] = str(auth_channel["channel_id"])
            if auth_channel.get("channel_name"):
                binding_payload["channel_name"] = str(auth_channel["channel_name"])
            logger.info(
                "bind_openapi_channel_openapi: 使用 authorization 返回的 channel 信息 "
                "account_id=%s platform=%s channel_id=%s channel_name=%s",
                account_id, platform,
                binding_payload.get("channel_id"),
                binding_payload.get("channel_name"),
            )

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
            source=body.channel_source or "openapi",
            channel_source=body.channel_source or "openapi",
            reserved_at=now,
            confirmed_at=now,
        )
        session.add(reservation)
        _apply_channel_binding(reservation, binding_payload, now=now)
        await refresh_reservation_channel_status(reservation)
        await recompute_account_platform_binding_status(session, account_id)
        await session.commit()
    elif reservation.status != "bound":
        # 旧 reservation 但尚未 bound（reserved/confirmed），允许覆盖完成绑定
        _apply_channel_binding(reservation, binding_payload, now=now)
        await refresh_reservation_channel_status(reservation)
        await recompute_account_platform_binding_status(session, account_id)
        await session.commit()
    # 已 bound：保持原值，直接返回当前数据

    rows = (
        await session.execute(
            select(AccountChannelReservation)
            .where(AccountChannelReservation.account_id == account_id)
            .order_by(AccountChannelReservation.created_at.asc())
        )
    ).scalars().all()
    return ExternalBindOpenAPIChannelResponse(
        account_id=account.id,
        account_name=account.account_name,
        account_handle=account.account_handle,
        account_signature=account.account_signature,
        gender=account.gender,
        account_type=account.account_type,
        channel_reservations=[ExternalChannelReservationRead.model_validate(row) for row in rows],
    )


@router.post("/channel-reservations/release", status_code=200)
async def release_channel_reservation_openapi(
    body: ExternalReleaseChannelReservationBody,
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """解绑并删除 AI 博主的平台频道占用记录，解绑后该博主可重新被领取绑定。"""
    _verify_api_key(body.api_key, x_api_key)
    owner_id = _resolve_owner_id(body.owner_id)

    account = await session.scalar(
        select(Account)
        .where(Account.id == body.account_id)
        .where(Account.owner_id == owner_id)
    )
    if not account:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号不存在")

    platform = body.platform.lower()
    reservation = await session.scalar(
        select(AccountChannelReservation)
        .where(AccountChannelReservation.account_id == body.account_id)
        .where(AccountChannelReservation.platform == platform)
    )
    if not reservation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到该平台的绑定记录")

    await session.delete(reservation)
    await session.flush()
    await recompute_account_platform_binding_status(session, body.account_id)
    await session.commit()
    return {"account_id": str(body.account_id), "platform": body.platform, "released": True}
