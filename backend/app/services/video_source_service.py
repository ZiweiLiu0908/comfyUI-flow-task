from __future__ import annotations

import asyncio
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone
from uuid import UUID
from urllib.parse import urlparse, urlunparse

import httpx
from fastapi import HTTPException, status
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.tag import Tag, video_source_tags
from app.models.video_source import VideoSource
from app.models.video_source_stat import VideoSourceStat
from app.schemas.video_source import VideoSourceCreate, VideoSourceParseResult

logger = logging.getLogger("app.video_source")


def _clean_url(url: str) -> str:
    """Remove query parameters and fragment from URL to get a clean URL for deduplication."""
    if not url:
        return url
    parsed = urlparse(url)
    # Reconstruct URL without query parameters and fragment
    clean = urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        None,  # Remove params
        None,  # Remove query
        None   # Remove fragment
    ))
    return clean


def _parse_yt_dlp_info(info: dict) -> dict:
    """Extract normalized fields from yt-dlp info dict."""
    platform = info.get("extractor_key", "").lower()
    if "youtube" in platform:
        platform = "youtube"
    elif "tiktok" in platform:
        platform = "tiktok"
    elif "instagram" in platform:
        platform = "instagram"
    else:
        platform = platform or None

    raw_date = info.get("upload_date")  # YYYYMMDD string
    publish_date: datetime | None = None
    if raw_date and len(str(raw_date)) == 8:
        try:
            publish_date = datetime.strptime(str(raw_date), "%Y%m%d").replace(tzinfo=timezone.utc)
        except ValueError:
            pass

    thumbnail_url = info.get("thumbnail") or None

    _exclude = {"url", "formats", "thumbnails", "automatic_captions", "subtitles"}
    extra = {k: v for k, v in info.items() if k not in _exclude}

    # Extract video metadata
    duration = info.get("duration")
    width = info.get("width")
    height = info.get("height")
    aspect_ratio = info.get("aspect_ratio")

    logger.info(
        "Extracted video metadata: duration=%s, width=%s, height=%s, aspect_ratio=%s",
        duration, width, height, aspect_ratio
    )

    return {
        "platform": platform,
        "blogger_name": info.get("uploader") or info.get("channel") or None,
        "video_title": info.get("title") or None,
        "video_desc": info.get("description") or None,
        "video_url": info.get("url") or None,
        "thumbnail_url": thumbnail_url,
        "view_count": info.get("view_count"),
        "like_count": info.get("like_count"),
        "favorite_count": info.get("save_count"),
        "comment_count": info.get("comment_count"),
        "share_count": info.get("share_count") or info.get("repost_count"),
        "publish_date": publish_date,
        "duration": duration,
        "width": width,
        "height": height,
        "aspect_ratio": aspect_ratio,
        "extra": extra,
    }


async def check_duplicate_url(
    session: AsyncSession,
    source_url: str,
    owner_id: UUID | None,
) -> VideoSource | None:
    """Return existing VideoSource if source_url already exists for this owner.
    Admin (owner_id=None) and regular users each have their own namespace."""
    stmt = select(VideoSource).where(VideoSource.source_url == source_url)
    stmt = stmt.where(VideoSource.owner_id == owner_id)
    return await session.scalar(stmt)


async def parse_video_url(
    url: str,
    session: AsyncSession | None = None,
    owner_id: UUID | None = None,
) -> VideoSourceParseResult:
    """Use yt-dlp (in a thread) to parse a video URL. Returns parsed info without saving.
    If session is provided, also checks for duplicates and sets existing_id."""
    def _run() -> dict:
        try:
            import yt_dlp  # type: ignore
        except ImportError:
            raise RuntimeError("yt-dlp is not installed")
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "format": "best",
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        return info or {}

    try:
        info = await asyncio.to_thread(_run)
    except Exception as exc:
        logger.warning("yt-dlp failed for %s: %s", url, exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无法解析视频链接: {exc}",
        ) from exc

    parsed = _parse_yt_dlp_info(info)
    # Get the original URL from parsed info or use the input URL
    original_url = info.get("original_url") or info.get("webpage_url") or url

    # Clean the URL by removing query parameters and fragment
    clean_url = _clean_url(original_url)

    logger.info(
        "Parsed video URL: input=%s, original_url=%s, clean_url=%s",
        url,
        original_url,
        clean_url
    )

    # Check for duplicates using the clean URL
    if session is not None:
        existing = await check_duplicate_url(session, clean_url, owner_id)
        if existing:
            return VideoSourceParseResult(source_url=clean_url, existing_id=existing.id)

    return VideoSourceParseResult(source_url=clean_url, **parsed)


async def create_video_source(
    session: AsyncSession,
    payload: VideoSourceCreate,
    owner_id: UUID | None = None,
) -> VideoSource:
    # Check for duplicates first (even with pre-parsed data)
    existing = await check_duplicate_url(session, payload.source_url, owner_id)
    if existing:
        logger.info("Video source already exists: %s", existing.id)
        # Return the existing video source instead of creating a new one
        return existing

    # If pre-parsed fields provided, skip yt-dlp
    if payload.video_title or payload.video_url or payload.blogger_name:
        logger.info(
            "Creating video source from pre-parsed payload: source_url=%s, duration=%s, width=%s, height=%s",
            payload.source_url, payload.duration, payload.width, payload.height
        )
        vs = VideoSource(
            owner_id=owner_id,
            source_url=payload.source_url,  # This should already be the original_url from parse
            platform=payload.platform,
            blogger_name=payload.blogger_name,
            video_title=payload.video_title,
            video_desc=payload.video_desc,
            video_url=payload.video_url,
            thumbnail_url=payload.thumbnail_url,
            view_count=payload.view_count,
            like_count=payload.like_count,
            favorite_count=payload.favorite_count,
            comment_count=payload.comment_count,
            share_count=payload.share_count,
            publish_date=payload.publish_date,
            duration=payload.duration,
            width=payload.width,
            height=payload.height,
            aspect_ratio=payload.aspect_ratio,
            extra=payload.extra,
            repeatable=payload.repeatable,
        )
    else:
        result = await parse_video_url(payload.source_url, session=session, owner_id=owner_id)
        vs = VideoSource(
            owner_id=owner_id,
            source_url=result.source_url,  # Use the parsed original_url
            platform=result.platform,
            blogger_name=result.blogger_name,
            video_title=result.video_title,
            video_desc=result.video_desc,
            video_url=result.video_url,
            thumbnail_url=result.thumbnail_url,
            view_count=result.view_count,
            like_count=result.like_count,
            favorite_count=result.favorite_count,
            comment_count=result.comment_count,
            share_count=result.share_count,
            publish_date=result.publish_date,
            duration=result.duration,
            width=result.width,
            height=result.height,
            aspect_ratio=result.aspect_ratio,
            extra=result.extra,
            repeatable=payload.repeatable,
        )

    session.add(vs)
    await session.flush()  # flush to get vs.id before associating tags

    # Associate tags via direct INSERT into junction table (avoids async lazy-load issue)
    if payload.tag_ids:
        for tag_id in payload.tag_ids:
            await session.execute(
                video_source_tags.insert().values(
                    video_source_id=vs.id,
                    tag_id=tag_id,
                )
            )

    await session.commit()
    await session.refresh(vs)

    logger.info(
        "Created video source: id=%s, duration=%s, width=%s, height=%s, aspect_ratio=%s, tags=%s",
        vs.id, vs.duration, vs.width, vs.height, vs.aspect_ratio,
        [str(t.id) for t in vs.tags],
    )

    return vs


async def list_video_sources(
    session: AsyncSession,
    *,
    page: int,
    page_size: int,
    owner_id: UUID | None = None,
    platform: str | None = None,
    blogger_name: str | None = None,
) -> tuple[list[VideoSource], int]:
    stmt = select(VideoSource).order_by(VideoSource.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    total_stmt = select(func.count(VideoSource.id))
    if owner_id is not None:
        stmt = stmt.where(VideoSource.owner_id == owner_id)
        total_stmt = total_stmt.where(VideoSource.owner_id == owner_id)
    if platform:
        stmt = stmt.where(VideoSource.platform == platform)
        total_stmt = total_stmt.where(VideoSource.platform == platform)
    if blogger_name:
        stmt = stmt.where(VideoSource.blogger_name.ilike(f"%{blogger_name}%"))
        total_stmt = total_stmt.where(VideoSource.blogger_name.ilike(f"%{blogger_name}%"))
    rows = (await session.execute(stmt)).scalars().all()
    total = int(await session.scalar(total_stmt) or 0)
    return list(rows), total


async def get_video_source_stats(
    session: AsyncSession,
    owner_id: UUID | None = None,
) -> dict:
    base = select(func.count(VideoSource.id))
    yt_stmt = select(func.count(VideoSource.id)).where(VideoSource.platform == "youtube")
    tk_stmt = select(func.count(VideoSource.id)).where(VideoSource.platform == "tiktok")
    week_ago = datetime.now(timezone.utc) - timedelta(days=7)
    recent_stmt = select(func.count(VideoSource.id)).where(VideoSource.created_at >= week_ago)

    if owner_id is not None:
        base = base.where(VideoSource.owner_id == owner_id)
        yt_stmt = yt_stmt.where(VideoSource.owner_id == owner_id)
        tk_stmt = tk_stmt.where(VideoSource.owner_id == owner_id)
        recent_stmt = recent_stmt.where(VideoSource.owner_id == owner_id)

    total = int(await session.scalar(base) or 0)
    youtube_count = int(await session.scalar(yt_stmt) or 0)
    tiktok_count = int(await session.scalar(tk_stmt) or 0)
    recent_count = int(await session.scalar(recent_stmt) or 0)

    return {
        "total": total,
        "youtube_count": youtube_count,
        "tiktok_count": tiktok_count,
        "recent_count": recent_count,
    }


async def get_video_source_or_404(
    session: AsyncSession,
    vs_id: UUID,
    owner_id: UUID | None = None,
) -> VideoSource:
    vs = await session.scalar(select(VideoSource).where(VideoSource.id == vs_id))
    if not vs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="视频源不存在")
    if owner_id is not None and vs.owner_id != owner_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="视频源不存在")
    return vs


async def delete_video_source(
    session: AsyncSession,
    vs_id: UUID,
    owner_id: UUID | None = None,
) -> None:
    await get_video_source_or_404(session, vs_id, owner_id)
    await session.execute(delete(VideoSource).where(VideoSource.id == vs_id))
    await session.commit()


async def _upload_video_file(file_path: str, filename: str) -> str:
    """Upload a local video file to the storage API. Returns the permanent URL. Retries up to 3 times."""
    last_exc: Exception | None = None
    for attempt in range(1, 4):
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                with open(file_path, "rb") as f:
                    response = await client.post(
                        settings.video_upload_api_url,
                        files={"file": (filename, f, "video/mp4")},
                        headers={"Accept": "*/*"},
                    )
            if response.status_code >= 400:
                raise RuntimeError(f"Upload API returned {response.status_code}: {response.text[:300]}")
            payload = response.json()
            url = payload.get("data", {}).get("url") if isinstance(payload.get("data"), dict) else None
            if not url:
                raise RuntimeError(f"Upload API response missing data.url: {payload}")
            return url
        except Exception as exc:
            last_exc = exc
            logger.warning("_upload_video_file failed (attempt %d/3): %s", attempt, exc)
            if attempt < 3:
                await asyncio.sleep(attempt)
    raise RuntimeError(f"Upload failed after 3 attempts: {last_exc}") from last_exc


async def _download_video_yt_dlp(source_url: str, out_path: str) -> str:
    """Download video to out_path using yt-dlp. Returns the actual output file path. Retries up to 3 times."""
    def _run() -> str:
        try:
            import yt_dlp  # type: ignore
        except ImportError:
            raise RuntimeError("yt-dlp is not installed")
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "outtmpl": out_path,
            "format": "best[ext=mp4]/best",
            "merge_output_format": "mp4",
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(source_url, download=True)
            # yt-dlp may append extension; get actual filename
            return ydl.prepare_filename(info)

    last_exc: Exception | None = None
    for attempt in range(1, 4):
        try:
            return await asyncio.to_thread(_run)
        except Exception as exc:
            last_exc = exc
            logger.warning("_download_video_yt_dlp failed (attempt %d/3): %s", attempt, exc)
            if attempt < 3:
                await asyncio.sleep(attempt)
    raise RuntimeError(f"Download failed after 3 attempts: {last_exc}") from last_exc


async def _do_download_and_upload(vs_id: UUID) -> None:
    """Background coroutine: download + upload, then persist result."""
    async with SessionLocal() as session:
        vs = await session.scalar(select(VideoSource).where(VideoSource.id == vs_id))
        if not vs:
            return

        # Determine filename from title or id
        safe_title = (vs.video_title or str(vs_id))[:60].replace("/", "_").replace("\\", "_")
        filename = f"{safe_title}.mp4"

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                out_template = os.path.join(tmpdir, "video")
                actual_path = await _download_video_yt_dlp(vs.source_url, out_template)
                # yt-dlp might produce e.g. /tmp/xxx/video.mp4 or /tmp/xxx/video
                if not os.path.exists(actual_path):
                    alt = out_template + ".mp4"
                    actual_path = alt if os.path.exists(alt) else actual_path

                permanent_url = await _upload_video_file(actual_path, filename)

            vs.local_video_url = permanent_url
            vs.download_status = "done"
            await session.commit()
            logger.info("Video %s downloaded and uploaded: %s", vs_id, permanent_url)
        except Exception as exc:
            logger.error("Video %s permanently failed: %s", vs_id, exc)
            vs.download_status = "failed"
            await session.commit()


async def trigger_download_and_upload(
    session: AsyncSession,
    vs_id: UUID,
    owner_id: UUID | None = None,
) -> VideoSource:
    """Mark status as 'downloading' and start background task. Returns updated record."""
    vs = await get_video_source_or_404(session, vs_id, owner_id)
    vs.download_status = "downloading"
    vs.local_video_url = None
    await session.commit()
    await session.refresh(vs)
    asyncio.create_task(_do_download_and_upload(vs_id))
    return vs


async def get_stats_history(
    session: AsyncSession,
    vs_id: UUID,
    owner_id: UUID | None = None,
) -> list[VideoSourceStat]:
    """Get historical stats for a video (ordered by collected_at asc)."""
    await get_video_source_or_404(session, vs_id, owner_id)
    stmt = (
        select(VideoSourceStat)
        .where(VideoSourceStat.video_source_id == vs_id)
        .order_by(VideoSourceStat.collected_at.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    return list(rows)
