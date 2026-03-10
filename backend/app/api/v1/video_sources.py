from __future__ import annotations

import asyncio
import io
import re
import uuid
import zipfile

import httpx
from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenData, get_current_user
from app.db.session import get_db
from sqlalchemy import select

from app.models.user import User
from app.schemas.video_source import (
    TagRead,
    VideoSourceCreate,
    VideoSourceListItem,
    VideoSourceListResponse,
    VideoSourceParseRequest,
    VideoSourceParseResult,
    VideoSourceRead,
    VideoSourceStatHistoryResponse,
    VideoSourceStatsResponse,
)
from app.services.video_source_service import (
    create_video_source,
    delete_video_source,
    get_stats_history,
    get_video_source_or_404,
    get_video_source_stats,
    list_video_sources,
    parse_video_url,
    trigger_download_and_upload,
)

router = APIRouter(prefix="/video-sources", tags=["video-sources"])


def _get_owner_id(current_user: TokenData = Depends(get_current_user)) -> uuid.UUID | None:
    """Query filter: admin→None (no filter), user→user_id"""
    return None if current_user.is_admin else current_user.user_id


def _get_creator_id(current_user: TokenData = Depends(get_current_user)) -> uuid.UUID:
    """Create records: always returns actual user_id"""
    return current_user.user_id


# /stats and /parse MUST be before /{vs_id} to avoid UUID matching them
@router.get("/stats", response_model=VideoSourceStatsResponse)
async def get_stats_endpoint(
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> VideoSourceStatsResponse:
    stats = await get_video_source_stats(session, owner_id)
    return VideoSourceStatsResponse(**stats)


@router.post("/parse", response_model=VideoSourceParseResult)
async def parse_video_endpoint(
    payload: VideoSourceParseRequest,
    creator_id: uuid.UUID = Depends(_get_creator_id),
    session: AsyncSession = Depends(get_db),
) -> VideoSourceParseResult:
    """Parse a video URL via yt-dlp without saving to database.
    If source_url already exists for this user, returns existing_id in response."""
    return await parse_video_url(payload.source_url, session=session, owner_id=creator_id)


@router.post("", response_model=VideoSourceRead, status_code=201)
async def create_video_source_endpoint(
    payload: VideoSourceCreate,
    creator_id: uuid.UUID = Depends(_get_creator_id),
    session: AsyncSession = Depends(get_db),
) -> VideoSourceRead:
    vs = await create_video_source(session, payload, creator_id)
    return VideoSourceRead.model_validate(vs)


@router.get("", response_model=VideoSourceListResponse)
async def list_video_sources_endpoint(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    platform: str | None = Query(None),
    blogger_name: str | None = Query(None),
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> VideoSourceListResponse:
    rows, total = await list_video_sources(
        session, page=page, page_size=page_size, owner_id=owner_id,
        platform=platform, blogger_name=blogger_name,
    )

    # 批量查询创建者用户名
    owner_ids = list({r.owner_id for r in rows if r.owner_id is not None})
    username_map: dict[uuid.UUID, str] = {}
    if owner_ids:
        users = (await session.execute(select(User).where(User.id.in_(owner_ids)))).scalars().all()
        for u in users:
            username_map[u.id] = u.display_name or u.username

    items = [
        VideoSourceListItem(
            **{k: getattr(r, k) for k in VideoSourceListItem.model_fields if k not in ("owner_username", "tags") and hasattr(r, k)},
            owner_username=username_map.get(r.owner_id) if r.owner_id else None,
            tags=[TagRead.model_validate(t) for t in (r.tags or [])],
        )
        for r in rows
    ]
    return VideoSourceListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/download-all-zip")
async def download_all_zip_endpoint(
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Download all videos with local_video_url as a single zip file."""
    # Fetch all video sources (up to 1000)
    rows, _ = await list_video_sources(session, page=1, page_size=1000, owner_id=owner_id)
    videos = [r for r in rows if r.local_video_url]

    async def generate_zip():
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
            async with httpx.AsyncClient(timeout=120.0) as client:
                for i, v in enumerate(videos, 1):
                    try:
                        resp = await client.get(v.local_video_url)
                        resp.raise_for_status()
                        safe_title = re.sub(r'[\\/*?:"<>|]', "_", v.video_title or v.blogger_name or "video")
                        filename = f"{i:03d}_{safe_title}.mp4"
                        zf.writestr(filename, resp.content)
                    except Exception:
                        pass
        buf.seek(0)
        yield buf.read()

    return StreamingResponse(
        generate_zip(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="videos.zip"'},
    )


@router.get("/{vs_id}", response_model=VideoSourceRead)
async def get_video_source_endpoint(
    vs_id: uuid.UUID,
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> VideoSourceRead:
    vs = await get_video_source_or_404(session, vs_id, owner_id)
    return VideoSourceRead.model_validate(vs)


@router.get("/{vs_id}/stats-history", response_model=VideoSourceStatHistoryResponse)
async def get_stats_history_endpoint(
    vs_id: uuid.UUID,
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> VideoSourceStatHistoryResponse:
    """Get historical stats for a video source."""
    items = await get_stats_history(session, vs_id, owner_id)
    return VideoSourceStatHistoryResponse(items=items)  # type: ignore[arg-type]


@router.post("/{vs_id}/download", response_model=VideoSourceRead)
async def download_video_source_endpoint(
    vs_id: uuid.UUID,
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> VideoSourceRead:
    """Trigger background download via yt-dlp and upload to permanent storage."""
    vs = await trigger_download_and_upload(session, vs_id, owner_id)
    return VideoSourceRead.model_validate(vs)


@router.delete("/{vs_id}")
async def delete_video_source_endpoint(
    vs_id: uuid.UUID,
    owner_id: uuid.UUID | None = Depends(_get_owner_id),
    session: AsyncSession = Depends(get_db),
) -> Response:
    await delete_video_source(session, vs_id, owner_id)
    return Response(status_code=204)
