from __future__ import annotations

import hmac
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.schemas.external_account_query import (
    ExternalAccountListResponse,
    ExternalPlatform,
    ExternalPlatformVideosResponse,
)
from app.services.external_account_query_service import (
    list_external_account_platform_videos,
    list_external_accounts,
)

router = APIRouter(prefix="/open-api/accounts", tags=["open-api-account-query"])


def _verify_api_key(x_api_key: str | None) -> None:
    expected = settings.account_channel_api_key
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ACCOUNT_CHANNEL_API_KEY 未配置",
        )
    if not hmac.compare_digest(x_api_key or "", expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid api_key")


def _resolve_owner_id() -> uuid.UUID:
    raw = settings.account_channel_owner_id
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="服务端 ACCOUNT_CHANNEL_OWNER_ID 未配置",
        )
    try:
        return uuid.UUID(raw)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="服务端 ACCOUNT_CHANNEL_OWNER_ID 格式无效",
        ) from exc


@router.get("", response_model=ExternalAccountListResponse)
async def list_open_api_accounts(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    gender: str | None = Query(None, pattern="^(male|female|unisex)$"),
    platform: ExternalPlatform | None = Query(None),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    session: AsyncSession = Depends(get_db),
) -> ExternalAccountListResponse:
    _verify_api_key(x_api_key)
    owner_id = _resolve_owner_id()
    items, total = await list_external_accounts(
        session,
        owner_id=owner_id,
        page=page,
        page_size=page_size,
        gender=gender,
        platform=platform,
    )
    return ExternalAccountListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{account_id}/platforms/{platform}/videos", response_model=ExternalPlatformVideosResponse)
async def list_open_api_account_platform_videos(
    account_id: uuid.UUID,
    platform: ExternalPlatform,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    x_api_key: str | None = Header(None, alias="X-API-Key"),
    session: AsyncSession = Depends(get_db),
) -> ExternalPlatformVideosResponse:
    _verify_api_key(x_api_key)
    owner_id = _resolve_owner_id()
    channel, items, total = await list_external_account_platform_videos(
        session,
        owner_id=owner_id,
        account_id=account_id,
        platform=platform,
        page=page,
        page_size=page_size,
    )
    return ExternalPlatformVideosResponse(
        account_id=account_id,
        platform=platform,
        channel=channel,
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )
