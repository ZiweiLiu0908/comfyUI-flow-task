from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone, date
from pathlib import Path
from typing import Any

from sqlalchemy import select
from google.cloud import bigquery
from google.auth import load_credentials_from_dict

from app.core.config import settings
from app.models.account_channel_reservation import AccountChannelReservation
from app.models.video_publication import VideoPublication
from app.models.video_task import VideoSubTask, VideoTask

logger = logging.getLogger("app.publication_click_metrics")

CLICK_METRICS_EVENT_NAME = "v_thirdapp_open"
CLICK_METRICS_COMPLETED = "completed"
CLICK_METRICS_FAILED = "failed"


def collect_tracking_links(bindings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, tuple[str, ...]]] = set()
    for binding in bindings:
        platform = str(binding.get("platform") or "").lower()
        short_link = str(binding.get("kol_short_link") or "").strip()
        long_link = str(binding.get("kol_long_link") or "").strip()
        query_links: list[str] = []
        for link in (short_link, long_link):
            if link and link not in query_links:
                query_links.append(link)
        if not platform or not query_links:
            continue
        dedup_key = (platform, tuple(query_links))
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        items.append(
            {
                "platform": platform,
                "short_link": short_link or None,
                "long_link": long_link or None,
                "query_links": query_links,
            }
        )
    return items


def is_click_metrics_due(
    snapshot: dict[str, Any] | None,
    completed_at: datetime | None,
    now: datetime,
) -> bool:
    if completed_at is None:
        return False
    if completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=timezone.utc)
    if now < completed_at + timedelta(hours=24):
        return False
    if isinstance(snapshot, dict) and snapshot.get("status") == CLICK_METRICS_COMPLETED:
        return False
    return True


def build_click_metrics_snapshot(
    *,
    completed_at: datetime,
    tracking_links: list[dict[str, Any]],
    clicks_by_link: dict[str, int],
    views_24h_snapshot: int | None,
    synced_at: datetime,
    status: str = CLICK_METRICS_COMPLETED,
    error_message: str | None = None,
) -> dict[str, Any]:
    per_link_rows: list[dict[str, Any]] = []
    total_clicks = 0
    for item in tracking_links:
        query_links = list(item.get("query_links") or [])
        per_link_clicks = 0
        link_counts: list[dict[str, Any]] = []
        for link in query_links:
            count = int(clicks_by_link.get(link, 0) or 0)
            per_link_clicks += count
            link_counts.append({"link": link, "clicks": count})
        total_clicks += per_link_clicks
        per_link_rows.append(
            {
                "platform": item.get("platform"),
                "short_link": item.get("short_link"),
                "long_link": item.get("long_link"),
                "query_links": query_links,
                "query_link_counts": link_counts,
                "clicks": per_link_clicks,
            }
        )

    ctr_24h = None
    if views_24h_snapshot is not None and views_24h_snapshot > 0:
        ctr_24h = round(total_clicks / views_24h_snapshot * 100, 2)

    return {
        "status": status,
        "window_start_at": completed_at.isoformat(),
        "window_end_at": (completed_at + timedelta(hours=24)).isoformat(),
        "synced_at": synced_at.isoformat(),
        "views_24h_snapshot": views_24h_snapshot,
        "total_clicks_24h": total_clicks,
        "ctr_24h": ctr_24h,
        "links": per_link_rows,
        "error_message": error_message or None,
    }


class PublicationClickMetricsService:
    def __init__(
        self,
        db,
        *,
        bigquery_client: bigquery.Client | None = None,
        open_api_client: Any | None = None,
    ) -> None:
        self.db = db
        self._bigquery_client = bigquery_client
        if open_api_client is None:
            from app.services.video_publication_service import OpenAPIClient

            open_api_client = OpenAPIClient()
        self.open_api = open_api_client

    async def sync_due_click_metrics(
        self,
        *,
        owner_id: Any | None = None,
        query: Any | None = None,
        now: datetime | None = None,
    ) -> dict[str, int]:
        now = now or datetime.now(timezone.utc)
        stmt = (
            select(VideoPublication, VideoTask.account_id)
            .join(VideoSubTask, VideoSubTask.id == VideoPublication.sub_task_id)
            .join(VideoTask, VideoTask.id == VideoSubTask.task_id)
            .where(VideoPublication.status.in_(["completed", "partial"]))
            .where(VideoPublication.completed_at.is_not(None))
        )
        if owner_id is not None:
            stmt = stmt.where(VideoTask.owner_id == owner_id)
        if query is not None and getattr(query, "account_id", None) is not None:
            stmt = stmt.where(VideoTask.account_id == query.account_id)
        if query is not None and getattr(query, "date_from", None) is not None:
            stmt = stmt.where(
                VideoPublication.completed_at
                >= datetime.combine(query.date_from, datetime.min.time(), tzinfo=timezone.utc)
            )
        if query is not None and getattr(query, "date_to", None) is not None:
            next_day = date.fromordinal(query.date_to.toordinal() + 1)
            stmt = stmt.where(
                VideoPublication.completed_at
                < datetime.combine(next_day, datetime.min.time(), tzinfo=timezone.utc)
            )

        rows = list((await self.db.execute(stmt)).all())
        synced = 0
        failed = 0
        eligible = 0
        for publication, account_id in rows:
            if query is not None and getattr(query, "platform", None):
                wanted = str(query.platform or "").lower()
                if wanted and wanted not in self._extract_publication_platforms(publication):
                    continue
            if not is_click_metrics_due(publication.click_metrics_24h_snapshot, publication.completed_at, now):
                continue
            eligible += 1
            try:
                await self.sync_publication_click_metrics(publication, account_id=account_id, now=now)
                synced += 1
            except Exception as exc:
                failed += 1
                logger.exception("sync_publication_click_metrics failed: publication_id=%s", publication.id)
                publication.click_metrics_24h_snapshot = build_click_metrics_snapshot(
                    completed_at=publication.completed_at,
                    tracking_links=[],
                    clicks_by_link={},
                    views_24h_snapshot=None,
                    synced_at=now,
                    status=CLICK_METRICS_FAILED,
                    error_message=str(exc)[:1000],
                )
        if synced or failed:
            await self.db.commit()
        return {"eligible": eligible, "synced": synced, "failed": failed}

    async def sync_publication_click_metrics(
        self,
        publication: VideoPublication,
        *,
        account_id: Any | None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if publication.completed_at is None:
            raise ValueError("publication.completed_at is required")
        if account_id is None:
            raise ValueError("publication.account_id is required for click metrics")

        now = now or datetime.now(timezone.utc)
        completed_at = publication.completed_at
        if completed_at.tzinfo is None:
            completed_at = completed_at.replace(tzinfo=timezone.utc)
        window_start = completed_at
        window_end = completed_at + timedelta(hours=24)

        tracking_links = await self._load_tracking_links(account_id, self._extract_publication_platforms(publication))
        if not tracking_links:
            raise ValueError("no tracking links found for publication")

        query_links = [link for item in tracking_links for link in item.get("query_links") or []]
        clicks_by_link = await self._count_clicks_by_link(query_links, window_start, window_end)
        views_24h_snapshot = await self._fetch_views_24h_snapshot(publication)

        snapshot = build_click_metrics_snapshot(
            completed_at=completed_at,
            tracking_links=tracking_links,
            clicks_by_link=clicks_by_link,
            views_24h_snapshot=views_24h_snapshot,
            synced_at=now,
        )
        publication.click_metrics_24h_snapshot = snapshot
        return snapshot

    async def _load_tracking_links(self, account_id: Any, platforms: set[str]) -> list[dict[str, Any]]:
        if not platforms:
            return []
        stmt = (
            select(AccountChannelReservation)
            .where(AccountChannelReservation.account_id == account_id)
            .where(AccountChannelReservation.platform.in_(sorted(platforms)))
            .where(AccountChannelReservation.status == "bound")
        )
        rows = list((await self.db.execute(stmt)).scalars().all())
        bindings = [
            {
                "platform": row.platform,
                "kol_short_link": row.kol_short_link,
                "kol_long_link": row.kol_long_link,
            }
            for row in rows
        ]
        return collect_tracking_links(bindings)

    def _extract_publication_platforms(self, publication: VideoPublication) -> set[str]:
        platforms: set[str] = set()
        for channel in publication.channels_status or []:
            platform = str(channel.get("platform") or "").lower()
            if platform:
                platforms.add(platform)
        if not platforms:
            payload = publication.request_payload or {}
            for channel in payload.get("channels") or []:
                if not isinstance(channel, dict):
                    continue
                platform = str(channel.get("platform") or "").lower()
                if platform:
                    platforms.add(platform)
        return platforms

    async def _count_clicks_by_link(
        self,
        query_links: list[str],
        window_start: datetime,
        window_end: datetime,
    ) -> dict[str, int]:
        unique_links = list(dict.fromkeys(link for link in query_links if link))
        if not unique_links:
            return {}
        client = self._get_bigquery_client()
        return await asyncio.to_thread(
            self._run_bigquery_click_count,
            client,
            unique_links,
            window_start,
            window_end,
        )

    def _run_bigquery_click_count(
        self,
        client: bigquery.Client,
        query_links: list[str],
        window_start: datetime,
        window_end: datetime,
    ) -> dict[str, int]:
        table = f"{settings.bigquery_project_id}.decom.dwd_event_log"
        sql = f"""
        SELECT
          JSON_VALUE(args, '$.current_url') AS link,
          COUNT(*) AS clicks
        FROM `{table}`
        WHERE DATE(logAt_timestamp) BETWEEN DATE(@window_start) AND DATE(TIMESTAMP_SUB(@window_end, INTERVAL 1 SECOND))
          AND logAt_timestamp >= @window_start
          AND logAt_timestamp < @window_end
          AND event_name = @event_name
          AND JSON_VALUE(args, '$.sf') != ''
          AND JSON_VALUE(args, '$.current_url') IN UNNEST(@links)
        GROUP BY link
        """
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ArrayQueryParameter("links", "STRING", query_links),
                bigquery.ScalarQueryParameter("window_start", "TIMESTAMP", window_start),
                bigquery.ScalarQueryParameter("window_end", "TIMESTAMP", window_end),
                bigquery.ScalarQueryParameter("event_name", "STRING", CLICK_METRICS_EVENT_NAME),
            ]
        )
        rows = client.query(sql, job_config=job_config).result()
        return {str(row.link): int(row.clicks or 0) for row in rows}

    async def _fetch_views_24h_snapshot(self, publication: VideoPublication) -> int | None:
        payload = publication.request_payload or {}
        if payload.get("_has_ext_pub") and not payload.get("_has_openapi"):
            return None
        if not publication.open_api_task_id:
            return None
        response = await self.open_api.fetch_upload_metrics(
            task_id=publication.open_api_task_id,
            external_id=publication.external_id,
        )
        if response.get("code") not in (0, "0", None):
            raise RuntimeError(f"metrics api code={response.get('code')} msg={response.get('message')}")
        data = response.get("data") or {}
        return self._extract_total_views_from_channels(data.get("channels") or [])

    @staticmethod
    def _extract_total_views_from_channels(channels: list[dict[str, Any]]) -> int | None:
        total_views = 0
        has_value = False
        for channel in channels:
            if not isinstance(channel, dict):
                continue
            stats = channel.get("stats") or {}
            platform = str(channel.get("platform") or "").lower()
            raw_value = stats.get("views") if platform == "youtube" else stats.get("view_count")
            try:
                if raw_value is None or raw_value == "":
                    continue
                total_views += int(float(raw_value))
                has_value = True
            except (TypeError, ValueError):
                continue
        return total_views if has_value else None

    def _get_bigquery_client(self) -> bigquery.Client:
        if self._bigquery_client is not None:
            return self._bigquery_client

        adc_path = Path.home() / ".config/gcloud/application_default_credentials.json"
        if adc_path.exists() and not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON"):
            credentials = json.loads(adc_path.read_text(encoding="utf-8"))
            credentials.pop("quota_project_id", None)
            os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"] = json.dumps(credentials)

        if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS_JSON"):
            info = json.loads(os.environ["GOOGLE_APPLICATION_CREDENTIALS_JSON"])
            credentials, _ = load_credentials_from_dict(
                info,
                scopes=["https://www.googleapis.com/auth/cloud-platform"],
            )
            self._bigquery_client = bigquery.Client(
                project=settings.bigquery_project_id,
                credentials=credentials,
            )
        else:
            self._bigquery_client = bigquery.Client(project=settings.bigquery_project_id)
        return self._bigquery_client
