from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.account_channel_reservation import AccountChannelReservation
from app.models.video_publication import VideoPublication
from app.models.video_task import VideoSubTask, VideoTask
from app.schemas.external_account_query import (
    ExternalAccountChannelRead,
    ExternalAccountListItem,
    ExternalPlatformVideoItem,
    ExternalVideoMetrics,
)
from app.utils.gcs_signing import ensure_sub_tasks_signed_urls


def _channel_read(row: AccountChannelReservation) -> ExternalAccountChannelRead:
    return ExternalAccountChannelRead(
        platform=row.platform,
        channel_status=row.channel_status,
        channel_source=row.channel_source or row.source or "openapi",
        channel_id=row.channel_id,
        channel_name=row.channel_name,
        username=row.username,
        avatar_url=row.avatar_url,
        kol_long_link=row.kol_long_link,
        kol_short_link=row.kol_short_link,
        bound_at=row.bound_at,
    )


def _to_int(value: Any) -> int:
    if value is None or value == "":
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _published_at(publication: VideoPublication) -> datetime | None:
    return publication.completed_at or publication.created_at


def _matches_channel(raw: dict, reservation: AccountChannelReservation) -> bool:
    platform = str(raw.get("platform") or "").lower()
    if platform != reservation.platform.lower():
        return False
    raw_channel_id = str(
        raw.get("channel_id")
        or raw.get("real_channel_id")
        or raw.get("platform_account_id")
        or raw.get("id")
        or ""
    ).strip()
    expected_channel_id = str(reservation.channel_id or "").strip()
    if raw_channel_id and expected_channel_id and raw_channel_id != expected_channel_id:
        return False
    return True


def _extract_channels(value: Any) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _find_platform_channel(publication: VideoPublication, reservation: AccountChannelReservation) -> dict | None:
    snapshot = publication.metrics_snapshot if isinstance(publication.metrics_snapshot, dict) else {}
    metric_channels = _extract_channels(snapshot.get("channels"))
    for channel in metric_channels:
        if _matches_channel(channel, reservation):
            return channel

    status_channels = _extract_channels(publication.channels_status)
    for channel in status_channels:
        if _matches_channel(channel, reservation):
            return channel
    return None


def _metric_value(stats: dict, platform: str, youtube_key: str, default_key: str) -> int:
    if platform == "youtube":
        return _to_int(stats.get(youtube_key) if stats.get(youtube_key) is not None else stats.get(default_key))
    return _to_int(stats.get(default_key) if stats.get(default_key) is not None else stats.get(youtube_key))


def _build_video_item(
    publication: VideoPublication,
    sub_task: VideoSubTask,
    task: VideoTask,
    channel: dict,
    video_url: str | None,
) -> ExternalPlatformVideoItem:
    request_payload = publication.request_payload if isinstance(publication.request_payload, dict) else {}
    platform = str(channel.get("platform") or "").lower()
    stats = channel.get("stats") if isinstance(channel.get("stats"), dict) else {}
    video_info = channel.get("video_info") if isinstance(channel.get("video_info"), dict) else {}

    return ExternalPlatformVideoItem(
        publication_id=publication.id,
        task_id=task.id,
        sub_task_id=sub_task.id,
        status=publication.status,
        title=request_payload.get("title"),
        description=request_payload.get("description"),
        video_url=video_url,
        platform_video_id=channel.get("platform_video_id"),
        platform_video_url=channel.get("platform_video_url"),
        thumbnail_url=video_info.get("thumbnail_url") or channel.get("thumbnail_url"),
        published_at=video_info.get("published_at") or channel.get("uploaded_at") or _published_at(publication),
        promotion_code=publication.promotion_code,
        metrics=ExternalVideoMetrics(
            views=_metric_value(stats, platform, "views", "view_count"),
            likes=_metric_value(stats, platform, "likes", "like_count"),
            comments=_metric_value(stats, platform, "comments", "comment_count"),
            shares=_metric_value(stats, platform, "shares", "share_count"),
        ),
    )


async def list_external_accounts(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    page: int,
    page_size: int,
    gender: str | None = None,
    platform: str | None = None,
) -> tuple[list[ExternalAccountListItem], int]:
    platform = platform.lower() if platform else None

    bound_exists = (
        exists()
        .where(AccountChannelReservation.account_id == Account.id)
        .where(AccountChannelReservation.status == "bound")
    )
    if platform:
        bound_exists = bound_exists.where(AccountChannelReservation.platform == platform)

    stmt = (
        select(Account)
        .where(Account.owner_id == owner_id)
        .where(Account.hidden.is_(False))
        .where(bound_exists)
        .order_by(Account.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    total_stmt = (
        select(func.count(Account.id))
        .where(Account.owner_id == owner_id)
        .where(Account.hidden.is_(False))
        .where(bound_exists)
    )
    if gender:
        stmt = stmt.where(Account.gender == gender)
        total_stmt = total_stmt.where(Account.gender == gender)

    accounts = list((await session.execute(stmt)).scalars().all())
    total = int(await session.scalar(total_stmt) or 0)
    if not accounts:
        return [], total

    account_ids = [account.id for account in accounts]
    reservation_stmt = (
        select(AccountChannelReservation)
        .where(AccountChannelReservation.account_id.in_(account_ids))
        .where(AccountChannelReservation.status == "bound")
        .order_by(AccountChannelReservation.created_at.asc())
    )
    if platform:
        reservation_stmt = reservation_stmt.where(AccountChannelReservation.platform == platform)
    reservations = list((await session.execute(reservation_stmt)).scalars().all())

    reservations_by_account: dict[uuid.UUID, list[ExternalAccountChannelRead]] = {aid: [] for aid in account_ids}
    for reservation in reservations:
        reservations_by_account.setdefault(reservation.account_id, []).append(_channel_read(reservation))

    return [
        ExternalAccountListItem(
            account_id=account.id,
            account_name=account.account_name,
            account_handle=account.account_handle,
            account_signature=account.account_signature,
            gender=account.gender,
            account_type=account.account_type,
            account_tier=account.account_tier,
            avatar_url=account.avatar_url,
            photo_url=account.photo_url,
            hashtags=account.hashtags,
            created_at=account.created_at,
            updated_at=account.updated_at,
            platforms=reservations_by_account.get(account.id, []),
        )
        for account in accounts
    ], total


async def list_external_account_platform_videos(
    session: AsyncSession,
    *,
    owner_id: uuid.UUID,
    account_id: uuid.UUID,
    platform: str,
    page: int,
    page_size: int,
) -> tuple[ExternalAccountChannelRead, list[ExternalPlatformVideoItem], int]:
    platform = platform.lower()

    account = await session.scalar(
        select(Account)
        .where(Account.id == account_id)
        .where(Account.owner_id == owner_id)
        .where(Account.hidden.is_(False))
    )
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号或平台绑定不存在")

    reservation = await session.scalar(
        select(AccountChannelReservation)
        .where(AccountChannelReservation.account_id == account_id)
        .where(AccountChannelReservation.platform == platform)
        .where(AccountChannelReservation.status == "bound")
    )
    if reservation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="账号或平台绑定不存在")

    rows = (
        await session.execute(
            select(VideoPublication, VideoSubTask, VideoTask)
            .join(VideoSubTask, VideoSubTask.id == VideoPublication.sub_task_id)
            .join(VideoTask, VideoTask.id == VideoSubTask.task_id)
            .where(VideoTask.account_id == account_id)
            .where(VideoTask.owner_id == owner_id)
            .where(VideoPublication.status.in_(["completed", "partial"]))
            .order_by(
                VideoPublication.completed_at.desc().nullslast(),
                VideoPublication.created_at.desc(),
            )
        )
    ).all()

    matched: list[tuple[VideoPublication, VideoSubTask, VideoTask, dict]] = []
    for publication, sub_task, task in rows:
        channel = _find_platform_channel(publication, reservation)
        if channel is not None:
            matched.append((publication, sub_task, task, channel))

    total = len(matched)
    start = (page - 1) * page_size
    page_rows = matched[start:start + page_size]

    sub_tasks = [sub_task for _, sub_task, _, _ in page_rows]
    url_map = await ensure_sub_tasks_signed_urls(session, sub_tasks) if sub_tasks else {}

    items = [
        _build_video_item(
            publication,
            sub_task,
            task,
            channel,
            url_map.get(sub_task.id, sub_task.result_video_url),
        )
        for publication, sub_task, task, channel in page_rows
    ]
    return _channel_read(reservation), items, total
