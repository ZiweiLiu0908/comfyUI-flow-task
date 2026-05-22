import asyncio
import io
import json
import logging
import os
import tempfile
import uuid
from datetime import date, timedelta
from typing import Any

import httpx
from fastapi import HTTPException, status
from google.cloud import storage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.models.video_ai_template import VideoAITemplate
from app.models.account import Account

from app.models.video_task import VideoSubTask, VideoTask
from app.models.video_task_config import VideoTaskConfig
from app.services.account_operation_guard import BLOCKED_ACCOUNT_STATUS_LABELS, is_account_operation_blocked
from app.services.ext_product_service import enrich_shots_with_ext_products

logger = logging.getLogger(__name__)



VALID_STATUSES = {"pending", "generating", "reviewing", "stashed", "decision_rejected", "queued", "pending_publish", "publishing", "published", "publish_failed", "abandoned"}

JOB = "jimeng/jobs"
CLI_JOBS = "jimeng/cli-jobs"

SUBTASK_COUNT = 3


def build_prompt_with_image_refs(base_prompt: str | None, shots_count: int, has_face: bool) -> str:
    """在 prompt 最前面拼接造型/人物参考说明，按 has_face 与造型图数量动态生成。

    has_face=True 时假设 shots[0] 是人物图，剩余为造型图：
      "人物参考: @图片1\n造型参考: @图片2,@图片3\n\n<原 prompt>"
    has_face=False 时所有 shots 都是造型图：
      "造型参考: @图片1,@图片2,@图片3\n\n<原 prompt>"
    无造型图（outfit_count<=0）时不拼接前缀，原 prompt 不变。
    """
    outfit_count = max(0, shots_count - (1 if has_face else 0))
    if outfit_count <= 0:
        return base_prompt or ""
    lines: list[str] = []
    if has_face:
        lines.append("人物参考: @图片1")
        outfit_refs = ",".join(f"@图片{i}" for i in range(2, outfit_count + 2))
        lines.append(f"造型参考: {outfit_refs}")
    else:
        outfit_refs = ",".join(f"@图片{i}" for i in range(1, outfit_count + 1))
        lines.append(f"造型参考: {outfit_refs}")
    return "\n".join(lines) + "\n\n" + (base_prompt or "")

SUB_TASK_TRANSITIONS: dict[str, set[str]] = {
    "pending":           {"generating"},
    "generating":        {"reviewing", "abandoned"},
    "reviewing":         {"stashed", "decision_rejected", "abandoned"},
    "stashed":           {"queued", "pending_publish", "abandoned"},
    "decision_rejected": set(),
    "queued":            {"publishing", "stashed"},
    "pending_publish":   {"queued", "stashed"},
    "publishing":        {"published", "publish_failed"},
    "publish_failed":    {"stashed", "pending_publish"},
    "published":         set(),
    "abandoned":         set(),
}

PREV_STATUS: dict[str, str] = {
    "generating":        "pending",
    "reviewing":         "generating",
    "stashed":           "reviewing",
    "queued":            "stashed",
    "publishing":        "queued",
    "publish_failed":    "publishing",
    "published":         "publishing",
}


def _compute_parent_status(sub_tasks: list[VideoSubTask]) -> str:
    if any(st.selected and st.status == "published" for st in sub_tasks):
        return "published"
    active = [st for st in sub_tasks if st.status not in ("abandoned", "decision_rejected")]
    statuses = {st.status for st in active}
    if not statuses:
        # 所有子任务都是 abandoned/decision_rejected；只有全部 decision_rejected 才返回 decision_rejected
        if all(st.status == "decision_rejected" for st in sub_tasks):
            return "decision_rejected"
        return "abandoned"
    if "publishing" in statuses:
        return "publishing"
    if "publish_failed" in statuses:
        return "publish_failed"
    if "queued" in statuses:
        return "queued"
    # Only return "stashed" when ALL active sub-tasks are stashed
    if "stashed" in statuses and all(st.status == "stashed" for st in active):
        return "stashed"
    if "reviewing" in statuses:
        return "reviewing"
    if "generating" in statuses:
        return "generating"
    return "pending"


def _extract_image_urls(shots: list | None) -> list[str]:
    if not shots:
        return []
    urls = []
    for shot in shots:
        if isinstance(shot, dict):
            url = shot.get("image_url") or shot.get("url") or ""
            if url:
                urls.append(url)
    return urls




class VideoTaskService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.bucket_name = settings.gcs_bucket_name
        self._storage_client = None
        self._bucket = None

    @property
    def bucket(self):
        if self._bucket is None:
            try:
                self._storage_client = storage.Client(project=settings.gcs_project_id)
                self._bucket = self._storage_client.bucket(self.bucket_name)
            except Exception as e:
                logger.warning(f"Could not initialize GCS client: {e}")
        return self._bucket

    async def create_task(
        self,
        account_id: uuid.UUID,
        template_id: uuid.UUID,
        final_prompt: str,
        duration: str,
        shots: list | None,
        user_id: uuid.UUID,
        target_date: date | None = None,
        subtask_count: int = SUBTASK_COUNT,
    ) -> VideoTask:
        if target_date is None:
            target_date = date.today() + timedelta(days=1)

        normalized_shots = list(shots) if isinstance(shots, list) else []
        account = await self.db.get(Account, account_id)
        if is_account_operation_blocked(account):
            label = BLOCKED_ACCOUNT_STATUS_LABELS.get(account.platform_binding_status, account.platform_binding_status)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"账号状态不可操作：{label}",
            )
        account_photo_url = account.photo_url if account else None
        if account_photo_url and (not account or account.face_mode != "no_face"):
            photo_shot = {
                "image_url": account_photo_url,
                "description": "",
            }
            if not normalized_shots or normalized_shots[0].get("image_url") != account_photo_url:
                normalized_shots = [photo_shot, *normalized_shots]
        normalized_shots = enrich_shots_with_ext_products(normalized_shots)

        has_face = (account.face_mode != "no_face") if account else True
        # 商品码账号 → 走「有CTA」一套提示词；无商品码 → 走「无CTA」（默认）
        cta = bool(account and account.product_code_mode == "with_code")

        composed_prompt = build_prompt_with_image_refs(final_prompt, len(normalized_shots), has_face)

        task = VideoTask(
            owner_id=user_id,
            account_id=account_id,
            template_id=template_id,
            target_date=target_date,
            status="pending",
            prompt=composed_prompt,
            duration=duration,
            shots=normalized_shots,
            has_face=has_face,
            cta=cta,
        )
        self.db.add(task)
        await self.db.flush()  # get task.id before creating sub-tasks

        # 标记模板为已使用
        tpl = await self.db.get(VideoAITemplate, template_id)
        if tpl and not tpl.is_used:
            tpl.is_used = True

        for i in range(1, subtask_count + 1):
            sub = VideoSubTask(
                task_id=task.id,
                sub_index=i,
                status="pending",
            )
            self.db.add(sub)

        await self.db.commit()
        await self.db.refresh(task)

        # Reload with sub_tasks
        result = await self.db.execute(
            select(VideoTask)
            .where(VideoTask.id == task.id)
            .options(selectinload(VideoTask.sub_tasks))
        )
        return result.scalar_one()

    async def get_tasks(
        self,
        target_date: date | None,
        owner_id: uuid.UUID | None,
        account_id: uuid.UUID | None = None,
        status_filter: str | None = None,
        tiktok_blogger_id: uuid.UUID | None = None,
        page: int | None = None,
        page_size: int | None = None,
    ) -> tuple[list[VideoTask], int]:
        from sqlalchemy import func

        base_q = select(VideoTask).order_by(VideoTask.created_at.desc())
        if target_date is not None:
            base_q = base_q.where(VideoTask.target_date == target_date)
        if owner_id is not None:
            base_q = base_q.where(VideoTask.owner_id == owner_id)
        if account_id is not None:
            base_q = base_q.where(VideoTask.account_id == account_id)
        if status_filter == "prompt_updated":
            base_q = base_q.where(VideoTask.is_prompt_updated == True)  # noqa: E712
        elif status_filter:
            base_q = base_q.where(VideoTask.status == status_filter)
        if tiktok_blogger_id is not None:
            base_q = base_q.join(VideoAITemplate, VideoTask.template_id == VideoAITemplate.id)
            base_q = base_q.where(VideoAITemplate.tiktok_blogger_id == tiktok_blogger_id)

        # Count total
        count_q = select(func.count()).select_from(base_q.subquery())
        total: int = (await self.db.execute(count_q)).scalar_one()

        # Paginate — no sub_tasks eager load for list view
        q = base_q
        if page is not None and page_size is not None:
            q = q.offset((page - 1) * page_size).limit(page_size)
        result = await self.db.execute(q)
        return list(result.scalars().all()), total

    async def get_task_detail(self, task_id: uuid.UUID, owner_id: uuid.UUID | None) -> dict:
        q = (
            select(VideoTask)
            .where(VideoTask.id == task_id)
            .options(selectinload(VideoTask.sub_tasks))
        )
        if owner_id is not None:
            q = q.where(VideoTask.owner_id == owner_id)
        task = (await self.db.execute(q)).scalar_one_or_none()
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")

        account_name: str | None = None
        template_title: str | None = None

        if task.account_id:
            acc = await self.db.get(Account, task.account_id)
            account_name = acc.account_name if acc else None

        if task.template_id:
            tpl = await self.db.get(VideoAITemplate, task.template_id)
            template_title = tpl.title if tpl else None

        return {"task": task, "account_name": account_name, "template_title": template_title}

    async def get_task_navigation(self, task_id: uuid.UUID, owner_id: uuid.UUID | None) -> dict:
        from sqlalchemy import func

        task = await self.db.get(VideoTask, task_id)
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
        if owner_id is not None and task.owner_id != owner_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权访问")

        account = await self.db.get(Account, task.account_id) if task.account_id else None

        # Navigation only shows tasks in 'reviewing' (待决策) status
        NAV_STATUS = "reviewing"

        def _base_task_q():
            q = select(VideoTask).where(
                VideoTask.status == NAV_STATUS,
                VideoTask.target_date == date.today(),
            )
            if owner_id is not None:
                q = q.where(VideoTask.owner_id == owner_id)
            return q

        # Position: count reviewing tasks for same account with created_at > current (DESC order)
        pos_q = select(func.count(VideoTask.id)).where(
            VideoTask.account_id == task.account_id,
            VideoTask.status == NAV_STATUS,
            VideoTask.created_at > task.created_at,
        )
        if owner_id is not None:
            pos_q = pos_q.where(VideoTask.owner_id == owner_id)
        position: int = (await self.db.execute(pos_q)).scalar() or 0

        # Total reviewing tasks for this account
        total_q = select(func.count(VideoTask.id)).where(
            VideoTask.account_id == task.account_id,
            VideoTask.status == NAV_STATUS,
        )
        if owner_id is not None:
            total_q = total_q.where(VideoTask.owner_id == owner_id)
        total: int = (await self.db.execute(total_q)).scalar() or 0

        # Selected count (stashed / queued / publishing / published)
        SELECTED_STATUSES = ("stashed", "queued", "publishing", "published")
        sel_q = select(func.count(VideoTask.id)).where(
            VideoTask.account_id == task.account_id,
            VideoTask.status.in_(SELECTED_STATUSES),
        )
        if owner_id is not None:
            sel_q = sel_q.where(VideoTask.owner_id == owner_id)
        selected_count: int = (await self.db.execute(sel_q)).scalar() or 0

        # Prev task (lower index = newer = created_at > current), only reviewing
        prev_q = (
            _base_task_q()
            .where(VideoTask.account_id == task.account_id, VideoTask.created_at > task.created_at)
            .order_by(VideoTask.created_at.asc())
            .limit(1)
        )
        prev_task = (await self.db.execute(prev_q)).scalar_one_or_none()

        # Next task (higher index = older = created_at < current), only reviewing
        next_q = (
            _base_task_q()
            .where(VideoTask.account_id == task.account_id, VideoTask.created_at < task.created_at)
            .order_by(VideoTask.created_at.desc())
            .limit(1)
        )
        next_task = (await self.db.execute(next_q)).scalar_one_or_none()

        # Prev/next blogger task: only reviewing status
        prev_blogger_row = None
        next_blogger_row = None
        if account:
            prev_blogger_q = (
                select(VideoTask, Account)
                .join(Account, Account.id == VideoTask.account_id)
                .where(Account.created_at > account.created_at)
                .where(VideoTask.status == NAV_STATUS)
                .where(VideoTask.target_date == date.today())
                .order_by(Account.created_at.asc(), VideoTask.created_at.asc())
                .limit(1)
            )
            if owner_id is not None:
                prev_blogger_q = prev_blogger_q.where(VideoTask.owner_id == owner_id)
            prev_blogger_row = (await self.db.execute(prev_blogger_q)).first()

            next_blogger_q = (
                select(VideoTask, Account)
                .join(Account, Account.id == VideoTask.account_id)
                .where(Account.created_at < account.created_at)
                .where(VideoTask.status == NAV_STATUS)
                .where(VideoTask.target_date == date.today())
                .order_by(Account.created_at.desc(), VideoTask.created_at.desc())
                .limit(1)
            )
            if owner_id is not None:
                next_blogger_q = next_blogger_q.where(VideoTask.owner_id == owner_id)
            next_blogger_row = (await self.db.execute(next_blogger_q)).first()

        return {
            "position": position,
            "total": total,
            "selected_count": selected_count,
            "prev_task": prev_task,
            "next_task": next_task,
            "prev_blogger_task": prev_blogger_row,
            "next_blogger_task": next_blogger_row,
            "account": account,
        }

    async def batch_delete_pending_generating(
        self, target_date: date, owner_id: uuid.UUID | None, status: str | None = None
    ) -> int:
        """删除指定日期下 pending / generating 状态的任务（及其级联子任务）。
        status 为 None 时删除两种状态，否则只删指定状态。返回删除数量。"""
        allowed = {"pending", "generating"}
        statuses = [status] if status in allowed else list(allowed)
        q = (
            select(VideoTask)
            .where(VideoTask.target_date == target_date)
            .where(VideoTask.status.in_(statuses))
        )
        if owner_id is not None:
            q = q.where(VideoTask.owner_id == owner_id)
        tasks = (await self.db.execute(q)).scalars().all()
        for task in tasks:
            await self.db.delete(task)
        await self.db.commit()
        return len(tasks)

    async def delete_task(self, task_id: uuid.UUID, owner_id: uuid.UUID | None) -> bool:
        q = select(VideoTask).where(VideoTask.id == task_id)
        if owner_id is not None:
            q = q.where(VideoTask.owner_id == owner_id)
        task = (await self.db.execute(q)).scalar_one_or_none()
        if not task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在")
        if task.target_date < date.today():
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="不允许删除今日之前的任务")
        if task.status not in ("pending", "generating"):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="只能删除 pending 或 generating 状态的任务")
        await self.db.delete(task)
        await self.db.commit()
        return True

    async def delete_sub_task(self, sub_task_id: uuid.UUID, owner_id: uuid.UUID | None) -> dict:
        """删除待发布的 sub_task，若父 task 无剩余有效 sub_task 则一并删除 task"""
        q = (
            select(VideoSubTask)
            .where(VideoSubTask.id == sub_task_id)
            .options(selectinload(VideoSubTask.task).selectinload(VideoTask.sub_tasks))
        )
        sub_task = (await self.db.execute(q)).scalar_one_or_none()
        if not sub_task:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="子任务不存在")

        task = sub_task.task
        if owner_id is not None and task.owner_id != owner_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权操作")

        if sub_task.status != "stashed":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"只能删除暂存状态的子任务，当前状态: {sub_task.status}",
            )

        await self.db.delete(sub_task)

        # 若父任务除本 sub_task 外无其他非 abandoned sub_task，则删除父任务
        remaining = [st for st in task.sub_tasks if st.id != sub_task_id and st.status != "abandoned"]
        if not remaining:
            await self.db.delete(task)
            await self.db.commit()
            return {"deleted_task": True}

        # 否则重新计算父任务状态
        # 先 flush 使 sub_task 从 task.sub_tasks 中移除，再重算
        await self.db.flush()
        updated_subs = [st for st in task.sub_tasks if st.id != sub_task_id]
        task.status = _compute_parent_status(updated_subs) if updated_subs else "pending"
        await self.db.commit()
        return {"deleted_task": False}

    async def upload_tasks(self, target_date: date, owner_id: uuid.UUID | None) -> tuple[str, int, int]:
        """
        Upload all pending tasks for the date to GCS.
        Each sub-task gets one entry in the payload using its UUID as video_id.
        Returns (gcs_url, task_count, subtask_count).
        """
        # 必须 eager load sub_tasks，否则访问 task.sub_tasks 触发懒加载导致 greenlet 错误
        q = (
            select(VideoTask)
            .where(VideoTask.target_date == target_date)
            .where(VideoTask.status == "pending")
            .options(selectinload(VideoTask.sub_tasks))
            .order_by(VideoTask.created_at.desc())
        )
        if owner_id is not None:
            q = q.where(VideoTask.owner_id == owner_id)
        tasks = list((await self.db.execute(q)).scalars().all())
        if not tasks:
            raise ValueError(f"No pending tasks found for {target_date}")

        if not self.bucket:
            raise RuntimeError("GCS bucket not initialized")

        payload = []
        for task in tasks:
            image_urls = _extract_image_urls(task.shots)
            prompt_text = (task.prompt.replace("\n", " ").replace("\r", "").strip() if task.prompt else "")[:1990]
            for sub in task.sub_tasks:
                sub_prompt = f"video_id: {sub.id}\n{prompt_text}"
                payload.append({
                    "prompt": sub_prompt,
                    "image_urls": image_urls,
                    "duration": task.duration,
                    "video_id": str(sub.id),
                    "has_face": task.has_face,
                })
                sub.status = "generating"
            task.status = "generating"

        date_str = target_date.strftime("%Y-%m-%d")
        # object_key = f"jimeng/jobs/{date_str}.json"
        object_key = f"{CLI_JOBS}/{date_str}.json"
        json_data = json.dumps(payload, ensure_ascii=False, indent=2)

        blob = self.bucket.blob(object_key)
        await asyncio.to_thread(blob.upload_from_string, json_data, content_type="application/json")
        logger.info(f"Uploaded {len(payload)} sub-task entries to gs://{self.bucket_name}/{object_key}")

        await self.db.commit()
        gcs_url = f"gs://{self.bucket_name}/{object_key}"
        return gcs_url, len(tasks), len(payload)

    async def _upload_gcs_video_to_cdn(self, blob: Any, filename: str) -> str:
        """把一个 GCS blob 下载到本地，再走 upload_video_file 统一上传入口。

        函数名沿用历史，实际目标由 VIDEO_UPLOAD_BACKEND 决定。
        """
        from app.utils.tmp_storage import disk_namedtempfile
        from app.utils.video_upload import upload_video_file

        with disk_namedtempfile(suffix=".mp4", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            await asyncio.to_thread(blob.download_to_filename, tmp_path)
            return await upload_video_file(tmp_path, filename)
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    async def fetch_results(self, target_date: date, owner_id: uuid.UUID | None) -> dict:
        """
        Read result videos from GCS for the given date using each sub-task's UUID as the path key.
        GCS path: jimeng/results/{YYYY-MM-DD}/{sub_task.id}/video.mp4
        Scans all tasks for the date and processes any sub-task with status=generating.
        Uploads are processed concurrently. Successfully uploaded videos are then enqueued
        into the background AI scoring queue.
        """
        # 必须 eager load sub_tasks，否则访问 task.sub_tasks 触发懒加载导致 greenlet 错误
        q = (
            select(VideoTask)
            .where(VideoTask.target_date == target_date)
            .options(selectinload(VideoTask.sub_tasks))
            .order_by(VideoTask.created_at.desc())
        )
        if owner_id is not None:
            q = q.where(VideoTask.owner_id == owner_id)
        tasks = list((await self.db.execute(q)).scalars().all())
        valid_tasks = [t for t in tasks if any(s.status == "generating" for s in t.sub_tasks)]
        if not valid_tasks:
            return {"updated": 0, "skipped": 0, "errors": [], "message": f"当天没有 generating 状态的子任务"}

        if not self.bucket:
            raise RuntimeError("GCS bucket not initialized")

        date_str = target_date.strftime("%Y-%m-%d")
        updated = 0
        skipped = 0
        errors = []

        # 1. Gather all generating subtasks
        target_subs = []
        for task in valid_tasks:
            for sub in task.sub_tasks:
                if sub.status == "generating":
                    target_subs.append((task, sub))
                else:
                    skipped += 1

        # 2. Concurrently check GCS and upload to CDN
        async def _process_upload(task, sub):
            object_key = f"jimeng/results/{date_str}/{sub.id}/video.mp4"
            blob = self.bucket.blob(object_key)
            if not await asyncio.to_thread(blob.exists):
                return task, sub, None, f"{sub.id}/video.mp4 not found in GCS"
            try:
                filename = f"{date_str}_{sub.id}.mp4"
                cdn_url = await self._upload_gcs_video_to_cdn(blob, filename)
                return task, sub, cdn_url, None
            except Exception as exc:
                return task, sub, None, f"{sub.id}: upload failed - {exc}"

        logger.info("Starting concurrent uploads for %d subtasks", len(target_subs))
        upload_coros = [_process_upload(t, s) for t, s in target_subs]
        upload_results = await asyncio.gather(*upload_coros)

        # 3. Process upload results and save DB
        #    If video not found or upload failed → abandon the subtask immediately
        successfully_uploaded = []
        for task, sub, cdn_url, error_msg in upload_results:
            if not cdn_url:
                errors.append(error_msg)
                logger.info("Sub-task %s not video: %s", sub.id, error_msg)
            else:
                sub.result_video_url = cdn_url
                sub.status = "reviewing"
                logger.info("Sub-task %s uploaded, moved to reviewing", sub.id)
            updated += 1

        # Recompute parent statuses and commit
        for task in valid_tasks:
            task.status = _compute_parent_status(task.sub_tasks)
        await self.db.commit()

        return {"updated": updated, "skipped": skipped, "errors": errors}

    async def patch_sub_task_status(
        self,
        sub_task_id: uuid.UUID,
        owner_id: uuid.UUID | None,
        new_status: str,
        result_video_url: str | None = None,
        selected: bool | None = None,
    ) -> VideoSubTask:
        if new_status not in VALID_STATUSES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"无效状态: {new_status}")

        # Load sub-task with its parent task (and all siblings)
        q = (
            select(VideoSubTask)
            .where(VideoSubTask.id == sub_task_id)
            .options(selectinload(VideoSubTask.task).selectinload(VideoTask.sub_tasks))
        )
        sub = (await self.db.execute(q)).scalar_one_or_none()
        if not sub:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="子任务不存在")
        if owner_id is not None and sub.task.owner_id != owner_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="子任务不存在")

        allowed = SUB_TASK_TRANSITIONS.get(sub.status, set())
        if new_status not in allowed:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"不允许从 {sub.status} 切换到 {new_status}",
            )

        sub.status = new_status
        if result_video_url is not None:
            sub.result_video_url = result_video_url

        # When moving to stashed with selected=True, abandon the other sub-tasks
        if new_status == "stashed" and selected:
            sub.selected = True
            for sibling in sub.task.sub_tasks:
                if sibling.id != sub.id and sibling.status not in ("published", "abandoned", "decision_rejected"):
                    sibling.status = "abandoned"

        sub.task.status = _compute_parent_status(sub.task.sub_tasks)
        await self.db.commit()
        await self.db.refresh(sub)
        return sub

    # Dimension weights for multi-dimension scoring
    DIMENSION_WEIGHTS = {
        "audio_visual": 20,        # 声画与听觉
        "character_realism": 30,   # 人物与全身拟真
        "performance_narrative": 15, # 表演与叙事
        "editing_transition": 12,  # 剪辑与转场
        "camera_composition": 12,  # 镜头与构图
        "visual_environment": 11,  # 画面与环境
    }

    async def update_sub_task_note(
        self,
        sub_task_id: uuid.UUID,
        owner_id: uuid.UUID | None,
        operator: str,
        target_status: str = "stashed",
        manual_note: str | None = None,
        has_ng: bool | None = None,
        ng_timestamps: list | None = None,
        dimension_scores: dict | None = None,
    ) -> VideoSubTask:
        q = select(VideoSubTask).where(VideoSubTask.id == sub_task_id).options(
            selectinload(VideoSubTask.task).selectinload(VideoTask.sub_tasks)
        )
        sub = (await self.db.execute(q)).scalar_one_or_none()
        if not sub:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="子任务不存在")
        if owner_id is not None and sub.task.owner_id != owner_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="子任务不存在")

        # Status lock: only reviewing sub-tasks can be processed
        if sub.status != "reviewing":
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"视频已被处理（当前状态：{sub.status}），请刷新后重试",
            )

        sub.operator = operator

        if manual_note is not None:
            sub.manual_note = manual_note

        if has_ng is not None:
            sub.has_ng = has_ng

        if ng_timestamps is not None:
            sub.ng_timestamps = ng_timestamps

        if dimension_scores is not None:
            sub.dimension_scores = dimension_scores

        # Recompute weighted total score from dimension_scores
        if sub.dimension_scores:
            total = 0.0
            for dim, weight in self.DIMENSION_WEIGHTS.items():
                score = sub.dimension_scores.get(dim)
                if score is not None:
                    total += (score / 5) * weight
            sub.weighted_total_score = round(total, 1)

        # Transition: reviewing → stashed / decision_rejected
        if target_status not in ("stashed", "decision_rejected"):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"不支持的目标状态: {target_status}")
        sub.status = target_status
        sub.task.status = _compute_parent_status(sub.task.sub_tasks)

        await self.db.commit()
        await self.db.refresh(sub)
        return sub

    async def rollback_sub_task_status(
        self,
        sub_task_id: uuid.UUID,
        owner_id: uuid.UUID | None,
    ) -> VideoSubTask:
        q = (
            select(VideoSubTask)
            .where(VideoSubTask.id == sub_task_id)
            .options(selectinload(VideoSubTask.task).selectinload(VideoTask.sub_tasks))
        )
        sub = (await self.db.execute(q)).scalar_one_or_none()
        if not sub:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="子任务不存在")
        if owner_id is not None and sub.task.owner_id != owner_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="子任务不存在")

        prev = PREV_STATUS.get(sub.status)
        if not prev:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"状态 {sub.status} 无法回退",
            )

        was_stashed = sub.status == "stashed"
        sub.status = prev
        sub.selected = False

        # 从 stashed 撤回时，将所有被废弃的兄弟子任务一并恢复到 reviewing
        if was_stashed:
            for sibling in sub.task.sub_tasks:
                if sibling.id != sub.id and sibling.status == "abandoned":
                    sibling.status = "reviewing"
                    sibling.selected = False

        sub.task.status = _compute_parent_status(sub.task.sub_tasks)
        await self.db.commit()
        await self.db.refresh(sub)
        return sub

    async def enqueue_sub_task(
        self,
        sub_task_id: uuid.UUID,
        owner_id: uuid.UUID | None,
    ) -> VideoSubTask:
        """将子任务从 stashed 状态移到 queued 状态，进入发布队列"""
        q = (
            select(VideoSubTask)
            .where(VideoSubTask.id == sub_task_id)
            .options(selectinload(VideoSubTask.task).selectinload(VideoTask.sub_tasks))
        )
        sub = (await self.db.execute(q)).scalar_one_or_none()
        if not sub:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="子任务不存在")
        if owner_id is not None and sub.task.owner_id != owner_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="子任务不存在")

        if sub.status not in ("stashed", "pending_publish"):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"只有暂存/待发布状态的子任务才能进入队列",
            )

        sub.status = "queued"
        # 如果没有设置 queue_order，设置为当前时间戳，确保排在最后
        if sub.queue_order is None:
            # 获取当前最大的 queue_order
            from sqlalchemy import func
            max_order = await self.db.execute(
                select(func.max(VideoSubTask.queue_order)).where(VideoSubTask.status == "queued")
            )
            max_order_val = max_order.scalar()
            sub.queue_order = (max_order_val or 0) + 1

        sub.publish_meta = {"status": "pending"}
        sub.task.status = _compute_parent_status(sub.task.sub_tasks)
        await self.db.commit()
        await self.db.refresh(sub)

        # 加入 AI 标题生成队列
        from app.services.publish_meta_service import enqueue_publish_meta_task
        enqueue_publish_meta_task(sub.id)

        return sub

    async def dequeue_sub_task(
        self,
        sub_task_id: uuid.UUID,
        owner_id: uuid.UUID | None,
    ) -> VideoSubTask:
        """将子任务从 queued 状态移回 stashed 状态"""
        q = (
            select(VideoSubTask)
            .where(VideoSubTask.id == sub_task_id)
            .options(selectinload(VideoSubTask.task).selectinload(VideoTask.sub_tasks))
        )
        sub = (await self.db.execute(q)).scalar_one_or_none()
        if not sub:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="子任务不存在")
        if owner_id is not None and sub.task.owner_id != owner_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="子任务不存在")

        if sub.status != "queued":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"只有 queued 状态的子任务才能移出队列",
            )

        sub.status = "stashed"
        sub.queue_order = None  # 清除排序

        sub.task.status = _compute_parent_status(sub.task.sub_tasks)
        await self.db.commit()
        await self.db.refresh(sub)
        return sub

    async def get_tasks_with_names(
        self,
        target_date: date | None,
        owner_id: uuid.UUID | None,
        account_id: uuid.UUID | None = None,
        status_filter: str | None = None,
        tiktok_blogger_id: uuid.UUID | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict], int]:
        """Returns (enriched task list, total count). Supports pagination."""
        from sqlalchemy import func, case

        tasks, total = await self.get_tasks(
            target_date, owner_id, account_id, status_filter, tiktok_blogger_id,
            page=page, page_size=page_size,
        )

        if not tasks:
            return [], total

        task_ids = [t.id for t in tasks]

        # Batch-fetch account and template names
        account_ids = {t.account_id for t in tasks if t.account_id}
        template_ids = {t.template_id for t in tasks if t.template_id}

        account_map: dict[uuid.UUID, str] = {}
        template_map: dict[uuid.UUID, str] = {}

        if account_ids:
            rows = await self.db.execute(
                select(Account.id, Account.account_name).where(Account.id.in_(account_ids))
            )
            account_map = {r.id: r.account_name for r in rows}

        if template_ids:
            rows = await self.db.execute(
                select(VideoAITemplate.id, VideoAITemplate.title).where(VideoAITemplate.id.in_(template_ids))
            )
            template_map = {r.id: r.title for r in rows}

        # Batch-fetch all sub_tasks in one query
        sub_rows = await self.db.execute(
            select(VideoSubTask)
            .where(VideoSubTask.task_id.in_(task_ids))
            .order_by(VideoSubTask.created_at.asc())
        )
        all_subs = sub_rows.scalars().all()
        sub_map: dict[uuid.UUID, list[VideoSubTask]] = {tid: [] for tid in task_ids}
        for sub in all_subs:
            sub_map[sub.task_id].append(sub)

        result = []
        for task in tasks:
            subs = sub_map.get(task.id, [])
            item = {
                "task": task,
                "account_name": account_map.get(task.account_id) if task.account_id else None,
                "template_title": template_map.get(task.template_id) if task.template_id else None,
                "sub_tasks_done": sum(1 for s in subs if s.result_video_url),
                "sub_tasks": subs,
            }
            result.append(item)
        return result, total

    async def evaluate_and_route_stashed(
        self,
        sub_task_id: uuid.UUID,
        owner_id: uuid.UUID | None,
    ) -> VideoSubTask:
        """
        Evaluate a stashed sub-task and route it based on score and has_ng.
        - has_ng=True → abandoned
        - weighted_total_score >= score_threshold_high → queued
        - weighted_total_score < score_threshold_low → abandoned
        - between → random(pool_ratio) → queued or abandoned
        Called automatically after a sub-task is moved to stashed.
        """
        import random

        q = (
            select(VideoSubTask)
            .where(VideoSubTask.id == sub_task_id)
            .options(selectinload(VideoSubTask.task).selectinload(VideoTask.sub_tasks))
        )
        sub = (await self.db.execute(q)).scalar_one_or_none()
        if not sub:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="子任务不存在")

        config = await self.db.get(VideoTaskConfig, sub.task.owner_id)
        threshold_high = config.score_threshold_high if config else 60.0
        threshold_low = config.score_threshold_low if config else 20.0
        pool_ratio = config.pool_ratio if config else 0.75

        if sub.has_ng:
            sub.status = "abandoned"
            logger.info("Sub-task %s has_ng=True → abandoned", sub.id)
        else:
            score = sub.weighted_total_score or 0.0
            if score >= threshold_high:
                sub.status = "queued"
                logger.info("Sub-task %s score=%.1f >= %.1f → queued", sub.id, score, threshold_high)
            elif score < threshold_low:
                sub.status = "abandoned"
                logger.info("Sub-task %s score=%.1f < %.1f → abandoned", sub.id, score, threshold_low)
            else:
                if random.random() < pool_ratio:
                    sub.status = "queued"
                    logger.info("Sub-task %s score=%.1f in middle range → queued (pool_ratio=%.2f)", sub.id, score, pool_ratio)
                else:
                    sub.status = "abandoned"
                    logger.info("Sub-task %s score=%.1f in middle range → abandoned (pool_ratio=%.2f)", sub.id, score, pool_ratio)

        if sub.status == "queued" and sub.queue_order is None:
            from sqlalchemy import func
            max_order = await self.db.execute(
                select(func.max(VideoSubTask.queue_order)).where(VideoSubTask.status == "queued")
            )
            max_order_val = max_order.scalar()
            sub.queue_order = (max_order_val or 0) + 1

        if sub.status == "queued":
            sub.publish_meta = {"status": "pending"}

        sub.task.status = _compute_parent_status(sub.task.sub_tasks)
        await self.db.commit()
        await self.db.refresh(sub)

        if sub.status == "queued":
            from app.services.publish_meta_service import enqueue_publish_meta_task
            enqueue_publish_meta_task(sub.id)

        return sub

    async def list_reviewing_subtasks(
        self,
        owner_id: uuid.UUID | None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[VideoSubTask], int]:
        """Return paginated list of sub-tasks in 'reviewing' status."""
        from sqlalchemy import func

        base_q = (
            select(VideoSubTask)
            .join(VideoTask, VideoTask.id == VideoSubTask.task_id)
            .where(VideoSubTask.status == "reviewing")
            .options(selectinload(VideoSubTask.task))
            .order_by(VideoSubTask.created_at.asc())
        )
        if owner_id is not None:
            base_q = base_q.where(VideoTask.owner_id == owner_id)

        count_q = select(func.count()).select_from(base_q.subquery())
        total: int = (await self.db.execute(count_q)).scalar_one()

        q = base_q.offset((page - 1) * page_size).limit(page_size)
        items = list((await self.db.execute(q)).scalars().all())
        return items, total

    async def batch_route_stashed(
        self,
        target_date: date,
        owner_id: uuid.UUID | None,
    ) -> dict:
        """
        3-step batch routing for all stashed parent tasks on the target date:

        1. From each task, pick the highest-scoring stashed sub-task (no NG).
           Collect all winners across tasks, rank by score, take top N% → queued.
        2. From the remaining winners, discard those with score < discard_below.
        3. From those still remaining, take top Y% → queued.
        All others (including NG sub-tasks and non-winners) → abandoned.
        """
        import math
        from sqlalchemy import func

        # Load parent tasks in "stashed" status for the target date
        task_q = (
            select(VideoTask)
            .where(VideoTask.status == "stashed")
            .where(VideoTask.target_date == target_date)
            .options(selectinload(VideoTask.sub_tasks))
        )
        if owner_id is not None:
            task_q = task_q.where(VideoTask.owner_id == owner_id)

        tasks = list((await self.db.execute(task_q)).scalars().all())
        if not tasks:
            return {"queued": 0, "abandoned": 0, "total": 0}

        # Fetch config
        sample_owner_id = tasks[0].owner_id
        config = await self.db.get(VideoTaskConfig, sample_owner_id)
        top_pct = (config.top_percent if config else None) or 30.0
        discard_below = (config.discard_below if config else None) or 40.0
        select_pct = (config.select_percent if config else None) or 50.0

        # Get current max queue_order
        max_order_res = await self.db.execute(
            select(func.max(VideoSubTask.queue_order)).where(VideoSubTask.status == "queued")
        )
        next_order = (max_order_res.scalar() or 0) + 1

        # Step 0: From each task, pick the best eligible sub-task (no NG, highest score)
        candidates = []  # list of (sub_task, parent_task)
        for task in tasks:
            stashed_subs = [st for st in task.sub_tasks if st.status == "stashed"]
            if not stashed_subs:
                continue
            eligible = [st for st in stashed_subs if not st.has_ng]
            eligible.sort(key=lambda st: st.weighted_total_score or 0.0, reverse=True)
            if eligible:
                candidates.append((eligible[0], task))

        total_candidates = len(candidates)
        if total_candidates == 0:
            # No eligible sub-tasks — abandon everything
            counts = {"queued": 0, "abandoned": 0}
            for task in tasks:
                for st in task.sub_tasks:
                    if st.status == "stashed":
                        st.status = "abandoned"
                        counts["abandoned"] += 1
                task.status = _compute_parent_status(task.sub_tasks)
            await self.db.commit()
            return {"queued": 0, "abandoned": counts["abandoned"], "total": counts["abandoned"]}

        # Sort all candidates by score descending
        candidates.sort(key=lambda pair: pair[0].weighted_total_score or 0.0, reverse=True)

        # Step 1: Pick top N% → queued
        top_n = max(1, math.ceil(total_candidates * top_pct / 100.0))
        step1_queued = candidates[:top_n]
        remaining = candidates[top_n:]

        # Step 2: Discard those with score < discard_below
        step2_kept = [p for p in remaining if (p[0].weighted_total_score or 0.0) >= discard_below]

        # Step 3: From those kept, pick top Y% → queued
        step3_n = max(1, math.ceil(len(step2_kept) * select_pct / 100.0)) if step2_kept else 0
        step3_queued = step2_kept[:step3_n]
        step3_abandoned = step2_kept[step3_n:]

        # All sub-tasks not selected as the best → abandoned
        queued_subs = {p[0].id for p in step1_queued + step3_queued}
        abandoned_subs = {p[0].id for p in remaining}  # all remaining from step1 that weren't in step3

        newly_queued_ids: list = []
        counts = {"queued": 0, "abandoned": 0}
        for task in tasks:
            for st in task.sub_tasks:
                if st.status != "stashed":
                    continue
                if st.id in queued_subs:
                    st.status = "queued"
                    st.selected = True   # 进入候选池即视为人工选中，否则 publish 链路会判 selected=False 报错
                    st.publish_meta = {"status": "pending"}
                    if st.queue_order is None:
                        st.queue_order = next_order
                        next_order += 1
                    newly_queued_ids.append(st.id)
                    counts["queued"] += 1
                else:
                    st.status = "abandoned"
                    counts["abandoned"] += 1
            task.status = _compute_parent_status(task.sub_tasks)

        await self.db.commit()

        from app.services.publish_meta_service import enqueue_publish_meta_task
        for sid in newly_queued_ids:
            enqueue_publish_meta_task(sid)
        return {"queued": counts["queued"], "abandoned": counts["abandoned"], "total": counts["queued"] + counts["abandoned"]}

    async def get_operator_stats(
        self,
        owner_id: uuid.UUID | None,
        target_date: date | None = None,
    ) -> list[dict]:
        """Return per-operator count and sub-task list."""
        from sqlalchemy import func

        base_q = (
            select(VideoSubTask)
            .join(VideoTask, VideoTask.id == VideoSubTask.task_id)
            .where(VideoSubTask.operator.isnot(None))
            .order_by(VideoSubTask.updated_at.desc())
        )
        if owner_id is not None:
            base_q = base_q.where(VideoTask.owner_id == owner_id)
        if target_date is not None:
            base_q = base_q.where(VideoTask.target_date == target_date)

        subs = list((await self.db.execute(base_q)).scalars().all())

        # Group by operator
        groups: dict[str, list] = {}
        for sub in subs:
            groups.setdefault(sub.operator, []).append(sub)

        return [
            {"operator": op, "count": len(items), "sub_tasks": items}
            for op, items in sorted(groups.items(), key=lambda x: -len(x[1]))
        ]

    # ── Download videos ────────────────────────────────────────────────────────

    async def download_videos(
        self,
        target_date: date,
        owner_id: uuid.UUID | None,
    ) -> tuple["io.BytesIO", str] | tuple[None, None]:
        """
        下载指定日期当天发布成功的视频，按账号分文件夹打包成 ZIP 返回。
        文件夹名：account_name
        文件名：account_id_account_name_发布时间.mp4（VideoPublication.completed_at）
        """
        import io
        import re
        import zipfile
        from sqlalchemy import func, cast, Date
        from app.models.video_publication import VideoPublication

        stmt = (
            select(VideoTask, VideoSubTask, VideoPublication, Account)
            .join(VideoSubTask, VideoSubTask.task_id == VideoTask.id)
            .join(VideoPublication, VideoPublication.sub_task_id == VideoSubTask.id)
            .join(Account, Account.id == VideoTask.account_id)
            .where(VideoPublication.status == "completed")
            .where(VideoSubTask.result_video_url.isnot(None))
            .where(cast(VideoPublication.completed_at, Date) == target_date)
        )
        if owner_id is not None:
            stmt = stmt.where(VideoTask.owner_id == owner_id)

        rows = (await self.db.execute(stmt)).all()
        if not rows:
            return None, None

        def sanitize(name: str) -> str:
            return re.sub(r'[\\/:*?"<>|]', '_', name).strip()

        date_str = target_date.strftime("%Y%m%d")
        root = f"videos_{date_str}"
        zip_filename = f"videos_{date_str}.zip"

        buf = io.BytesIO()
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for task, sub_task, publication, account in rows:
                    folder = sanitize(account.account_name)
                    pub_time = publication.completed_at or publication.updated_at or task.created_at
                    pub_str = pub_time.strftime("%Y%m%d_%H%M%S")
                    filename = f"{account.id}_{sanitize(account.account_name)}_{pub_str}.mp4"
                    arc_path = f"{root}/{folder}/{filename}"
                    try:
                        resp = await client.get(sub_task.result_video_url)
                        resp.raise_for_status()
                        zf.writestr(arc_path, resp.content)
                        logger.info("Packed video %s → %s", sub_task.result_video_url, arc_path)
                    except Exception as exc:
                        logger.warning(
                            "Skip video for task %s (account %s): %s",
                            task.id, account.account_name, exc,
                        )

        buf.seek(0)
        return buf, zip_filename

    async def download_latest_published_videos(
        self,
        owner_id: uuid.UUID | None,
        account_ids: list[uuid.UUID] | None = None,
    ) -> tuple["io.BytesIO", str] | tuple[None, None]:
        """
        下载每个账号最新已发布的视频，同时打包对应的 caption/hashtag txt。
        文件夹名：account_name
        文件名：account_id_account_name_发布时间.mp4 / .txt
        txt 内容：标题 + 描述 + 标签（来自 VideoPublication.request_payload，若无则留空）
        以 VideoSubTask.status == 'published' 为主，LEFT JOIN VideoPublication 取 caption。
        """
        import io
        import re
        import zipfile
        from sqlalchemy import outerjoin
        from app.models.video_publication import VideoPublication

        # 以 VideoSubTask.status='published' 为准，LEFT JOIN VideoPublication 取 caption
        stmt = (
            select(VideoTask, VideoSubTask, VideoPublication, Account)
            .join(VideoSubTask, VideoSubTask.task_id == VideoTask.id)
            .outerjoin(VideoPublication, VideoPublication.sub_task_id == VideoSubTask.id)
            .join(Account, Account.id == VideoTask.account_id)
            .where(VideoSubTask.status == "published")
            .where(VideoSubTask.result_video_url.isnot(None))
            .order_by(VideoSubTask.updated_at.desc())
        )
        if owner_id is not None:
            stmt = stmt.where(VideoTask.owner_id == owner_id)
        if account_ids:
            stmt = stmt.where(VideoTask.account_id.in_(account_ids))

        rows = (await self.db.execute(stmt)).all()
        if not rows:
            return None, None

        # 每个账号只保留最新一条（已按 updated_at DESC 排序）
        seen_accounts: set[uuid.UUID] = set()
        latest_rows = []
        for row in rows:
            task, sub_task, publication, account = row
            if account.id not in seen_accounts:
                seen_accounts.add(account.id)
                latest_rows.append(row)

        def sanitize(name: str) -> str:
            return re.sub(r'[\\/:*?"<>|]', '_', name).strip()

        def build_caption_txt(payload: dict | None) -> str:
            if not payload:
                return ""
            lines = []
            if payload.get("title"):
                lines.append(f"标题：{payload['title']}")
            if payload.get("description"):
                lines.append(f"描述：{payload['description']}")
            tags = payload.get("tags") or []
            if tags:
                lines.append(f"标签：{' '.join(f'#{t}' if not t.startswith('#') else t for t in tags)}")
            return "\n".join(lines)

        root = "videos_latest"
        zip_filename = "videos_latest.zip"

        buf = io.BytesIO()
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for task, sub_task, publication, account in latest_rows:
                    folder = sanitize(account.account_name)
                    pub_time = sub_task.updated_at or task.created_at
                    pub_str = pub_time.strftime("%Y%m%d_%H%M%S")
                    base_name = f"{account.id}_{sanitize(account.account_name)}_{pub_str}"
                    video_path = f"{root}/{folder}/{base_name}.mp4"
                    txt_path = f"{root}/{folder}/{base_name}_caption.txt"
                    try:
                        resp = await client.get(sub_task.result_video_url)
                        resp.raise_for_status()
                        zf.writestr(video_path, resp.content)
                        caption_text = build_caption_txt(publication.request_payload)
                        zf.writestr(txt_path, caption_text.encode("utf-8"))
                        logger.info("Packed latest video for account %s → %s", account.account_name, video_path)
                    except Exception as exc:
                        logger.warning(
                            "Skip latest video for account %s: %s",
                            account.account_name, exc,
                        )

        buf.seek(0)
        return buf, zip_filename
