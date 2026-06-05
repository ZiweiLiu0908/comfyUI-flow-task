"""Template supplement scheduler.

Runs per owner on Beijing-time cron. Each scheduled account is submitted one
round at a time; vendor callback completion can trigger the second round.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from croniter import croniter
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.external_supplement_request import ExternalSupplementRequest
from app.models.pipeline_setting import PipelineSetting
from app.models.template_supplement_run import TemplateSupplementRun
from app.services.account_scope_service import normalize_schedule_scope, resolve_schedule_scope_accounts
from app.services.template_supplement_service import (
    build_account_top_up_plan,
    resolve_supplement_mode_for_account,
    should_start_another_round,
)


logger = logging.getLogger("app.template_supplement_scheduler")

_TZ = ZoneInfo("Asia/Shanghai")
_POLL_INTERVAL_SECONDS = 60
_DEFAULT_CRON = "0 10 * * *"

_scheduler_task: asyncio.Task | None = None
_scheduler_stop_event: asyncio.Event | None = None
_fired: dict[str, str] = {}


def start_template_supplement_scheduler() -> None:
    global _scheduler_task, _scheduler_stop_event
    if _scheduler_task is not None and not _scheduler_task.done():
        return
    _scheduler_stop_event = asyncio.Event()
    _scheduler_task = asyncio.get_running_loop().create_task(_start_scheduler_with_prefill(_scheduler_stop_event))
    logger.info("【模板补充调度器】已启动")


async def stop_template_supplement_scheduler() -> None:
    global _scheduler_task, _scheduler_stop_event
    stop_event, worker = _scheduler_stop_event, _scheduler_task
    _scheduler_stop_event = None
    _scheduler_task = None
    if stop_event:
        stop_event.set()
    if worker:
        worker.cancel()
        try:
            await worker
        except asyncio.CancelledError:
            pass
    logger.info("【模板补充调度器】已停止")


async def _start_scheduler_with_prefill(stop_event: asyncio.Event) -> None:
    await _prefill_fired()
    await _scheduler_loop(stop_event)


async def _prefill_fired() -> None:
    try:
        now_local = datetime.now(timezone.utc).astimezone(_TZ)
        async with SessionLocal() as session:
            settings_list = list((await session.execute(
                select(PipelineSetting).where(PipelineSetting.template_supplement_schedule_enabled.is_(True))
            )).scalars().all())
        for ps in settings_list:
            cron_expr = (ps.template_supplement_schedule_cron or _DEFAULT_CRON).strip()
            if not croniter.is_valid(cron_expr):
                continue
            prev_fire_local: datetime = croniter(cron_expr, now_local, ret_type=datetime).get_prev(datetime)
            _fired[str(ps.owner_id)] = prev_fire_local.strftime("%Y-%m-%d %H:%M")
        logger.info("【模板补充调度器】预填 _fired 完成，共 %d 条", len(_fired))
    except Exception:
        logger.exception("【模板补充调度器】预填 _fired 失败")


async def _scheduler_loop(stop_event: asyncio.Event) -> None:
    try:
        while not stop_event.is_set():
            try:
                await _run_once()
            except Exception:
                logger.exception("【模板补充调度器】轮询异常")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=_POLL_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                continue
    except asyncio.CancelledError:
        raise


async def _run_once() -> None:
    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone(_TZ)
    async with SessionLocal() as session:
        settings_list = list((await session.execute(
            select(PipelineSetting).where(PipelineSetting.template_supplement_schedule_enabled.is_(True))
        )).scalars().all())
    for ps in settings_list:
        try:
            await _process_owner(ps, now_utc=now_utc, now_local=now_local)
        except Exception:
            logger.exception("【模板补充调度器】处理用户 %s 异常", ps.owner_id)


async def _process_owner(ps: PipelineSetting, *, now_utc: datetime, now_local: datetime) -> None:
    cron_expr = (ps.template_supplement_schedule_cron or _DEFAULT_CRON).strip()
    if not croniter.is_valid(cron_expr):
        logger.warning("【模板补充调度器】用户 %s cron 无效：%s", ps.owner_id, cron_expr)
        return

    prev_fire_local: datetime = croniter(cron_expr, now_local, ret_type=datetime).get_prev(datetime)
    prev_fire_key = prev_fire_local.strftime("%Y-%m-%d %H:%M")
    prev_fire_utc = prev_fire_local.astimezone(timezone.utc)
    seconds_since_fire = (now_utc - prev_fire_utc).total_seconds()
    if seconds_since_fire < 0 or seconds_since_fire >= _POLL_INTERVAL_SECONDS * 1.5:
        return

    owner_key = str(ps.owner_id)
    if _fired.get(owner_key) == prev_fire_key or ps.template_supplement_last_trigger_key == prev_fire_key:
        return
    _fired[owner_key] = prev_fire_key

    async with SessionLocal() as session:
        row = await session.get(PipelineSetting, ps.owner_id)
        if row is not None:
            row.template_supplement_last_trigger_key = prev_fire_key
            await session.commit()

    logger.info("【模板补充调度器】触发用户 %s trigger=%s", ps.owner_id, prev_fire_key)
    await run_scheduled_template_supplement_for_owner(
        owner_id=ps.owner_id,
        trigger_key=prev_fire_key,
        target_unused_template_count=max(int(ps.template_supplement_target_unused_count or 10), 1),
        filters=ps.template_supplement_filters or {},
        max_rounds=max(int(ps.template_supplement_max_rounds or 2), 1),
        scope_mode=ps.template_supplement_scope_mode or "filtered",
        scope_account_ids=ps.template_supplement_scope_account_ids or [],
        scope_filters=ps.template_supplement_scope_filters or {},
    )


async def run_scheduled_template_supplement_for_owner(
    *,
    owner_id: uuid.UUID,
    trigger_key: str,
    target_unused_template_count: int,
    filters: dict,
    max_rounds: int,
    scope_mode: str | None = None,
    scope_account_ids: list | None = None,
    scope_filters: dict | None = None,
) -> None:
    scope = normalize_schedule_scope(
        scope_mode=scope_mode,
        account_ids=scope_account_ids,
        filters=scope_filters,
    )
    async with SessionLocal() as session:
        accounts = await resolve_schedule_scope_accounts(
            session,
            owner_id=owner_id,
            scope_mode=scope["mode"],
            account_ids=scope["account_ids"],
            filters=scope["filters"],
            require_channel_bound=False,
        )

    for account in accounts:
        mode = resolve_supplement_mode_for_account(account)
        run_id = await _create_scheduled_run(
            owner_id=owner_id,
            trigger_key=trigger_key,
            account_id=account.id,
            mode=mode,
            target_unused_template_count=target_unused_template_count,
            filters=filters,
            max_rounds=max_rounds,
            scope=scope,
            resolved_account_count=len(accounts),
        )
        asyncio.create_task(_start_round_for_run(run_id, round_index=1))


async def _create_scheduled_run(
    *,
    owner_id: uuid.UUID,
    trigger_key: str,
    account_id: uuid.UUID,
    mode: str,
    target_unused_template_count: int,
    filters: dict,
    max_rounds: int,
    scope: dict,
    resolved_account_count: int,
) -> uuid.UUID:
    async with SessionLocal() as session:
        plan = await build_account_top_up_plan(
            session,
            account_id=account_id,
            owner_id=owner_id,
            mode=mode,
            target_unused_template_count=target_unused_template_count,
            filters=filters,
        )
        run = TemplateSupplementRun(
            owner_id=owner_id,
            trigger_key=trigger_key,
            account_id=account_id,
            mode=mode,
            status="skipped" if plan.skip_reason else ("completed" if plan.need_count <= 0 else "running"),
            target_unused_template_count=target_unused_template_count,
            initial_unused_template_count=plan.current_unused_template_count,
            current_unused_template_count=plan.current_unused_template_count,
            requested_video_count=0,
            completed_rounds=0,
            max_rounds=max_rounds,
            filters=filters or {},
            scope_mode=scope["mode"],
            scope_account_ids_snapshot=scope["account_ids"],
            scope_filters_snapshot=scope["filters"],
            resolved_account_count=resolved_account_count,
            skip_reason=plan.skip_reason or ("已达目标" if plan.need_count <= 0 else None),
        )
        session.add(run)
        await session.commit()
        return run.id


async def _start_round_for_run(run_id: uuid.UUID, *, round_index: int) -> None:
    async with SessionLocal() as session:
        run = await session.get(TemplateSupplementRun, run_id)
        if run is None or run.status != "running":
            return
        plan = await build_account_top_up_plan(
            session,
            account_id=run.account_id,
            owner_id=run.owner_id,
            mode=run.mode,
            target_unused_template_count=run.target_unused_template_count,
            filters=run.filters or {},
        )
        run.current_unused_template_count = plan.current_unused_template_count
        if plan.skip_reason:
            run.status = "skipped"
            run.skip_reason = plan.skip_reason
            await session.commit()
            return
        if plan.need_count <= 0:
            run.status = "completed"
            run.skip_reason = "已达目标"
            await session.commit()
            return
        await session.commit()

    try:
        from app.services.external_supplement_service import submit_supplement_request

        result = await submit_supplement_request(
            owner_id=run.owner_id,
            account_ids=[run.account_id],
            mode=run.mode,
            target_video_count=plan.need_count,
            filters=run.filters or {},
            business_context={
                "source_domain": "ai_blogger",
                "template_supplement_schedule_run_id": str(run.id),
                "round_index": round_index,
                "max_rounds": run.max_rounds,
                "target_unused_template_count": run.target_unused_template_count,
                "account_id": str(run.account_id),
            },
            item_context_by_account={
                str(run.account_id): {
                    "target_unused_template_count": run.target_unused_template_count,
                    "initial_unused_template_count": run.initial_unused_template_count,
                    "current_unused_template_count": plan.current_unused_template_count,
                    "requested_video_count": plan.need_count,
                    "round_index": round_index,
                    "schedule_run_id": str(run.id),
                }
            },
        )
        request_id = uuid.UUID(str(result["request_id"]))
        async with SessionLocal() as session:
            current_run = await session.get(TemplateSupplementRun, run_id)
            if current_run is not None:
                current_run.last_request_id = request_id
                current_run.requested_video_count = int(current_run.requested_video_count or 0) + plan.need_count
                current_run.completed_rounds = max(int(current_run.completed_rounds or 0), round_index)
                await session.commit()
    except Exception as exc:
        logger.exception("【模板补充调度器】提交 round 失败 run=%s", run_id)
        async with SessionLocal() as session:
            current_run = await session.get(TemplateSupplementRun, run_id)
            if current_run is not None:
                current_run.status = "failed"
                current_run.skip_reason = str(exc)
                await session.commit()


async def maybe_continue_scheduled_request(request_id: uuid.UUID) -> None:
    async with SessionLocal() as session:
        req = await session.scalar(
            select(ExternalSupplementRequest)
            .where(ExternalSupplementRequest.request_id == request_id)
        )
        if req is None or req.status not in {"completed", "failed"}:
            return
        ctx = req.business_context or {}
        run_id_raw = ctx.get("template_supplement_schedule_run_id")
        if not run_id_raw:
            return
        run = await session.get(TemplateSupplementRun, uuid.UUID(str(run_id_raw)))
        if run is None or run.last_request_id != request_id or run.status != "running":
            return
        plan = await build_account_top_up_plan(
            session,
            account_id=run.account_id,
            owner_id=run.owner_id,
            mode=run.mode,
            target_unused_template_count=run.target_unused_template_count,
            filters=run.filters or {},
        )
        run.current_unused_template_count = plan.current_unused_template_count
        completed_rounds = max(int(run.completed_rounds or 0), int(ctx.get("round_index") or 1))
        run.completed_rounds = completed_rounds
        if plan.skip_reason:
            run.status = "skipped"
            run.skip_reason = plan.skip_reason
            await session.commit()
            return
        if plan.need_count <= 0:
            run.status = "completed"
            run.skip_reason = "已达目标"
            await session.commit()
            return
        if not should_start_another_round(
            completed_rounds=completed_rounds,
            current_unused_count=plan.current_unused_template_count,
            target_unused_count=run.target_unused_template_count,
            max_rounds=run.max_rounds,
        ):
            run.status = "stopped"
            run.skip_reason = "达到最大轮次，仍未补足"
            await session.commit()
            return
        next_round = completed_rounds + 1
        await session.commit()

    await _start_round_for_run(uuid.UUID(str(run_id_raw)), round_index=next_round)
