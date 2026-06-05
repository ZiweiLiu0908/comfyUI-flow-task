from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from typing import Any, Iterable
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import and_, exists, select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class CategoryRuleMatch:
    major_category: str
    min_views: int
    repeat_count: int


@dataclass(frozen=True)
class UsedTemplateScore:
    score_views: int
    latest_published_at: Any | None
    scored_published_at: Any | None


@dataclass(frozen=True)
class ScheduledGenerationResult:
    owner_id: UUID
    trigger_key: str
    target_date: Any
    account_count: int
    total_created_tasks: int
    step_one_created_tasks: int
    unused_template_created_tasks: int
    used_template_created_tasks: int
    shortfall_count: int


def _to_int(value: Any) -> int:
    try:
        if value is None or value == "":
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def total_publication_views(metrics_snapshot: dict | None) -> int:
    if not isinstance(metrics_snapshot, dict):
        return 0
    total = 0
    for channel in metrics_snapshot.get("channels") or []:
        if not isinstance(channel, dict):
            continue
        stats = channel.get("stats") or {}
        if not isinstance(stats, dict):
            continue
        platform = str(channel.get("platform") or "").lower()
        key = "views" if platform == "youtube" else "view_count"
        total += _to_int(stats.get(key))
    return total


def compute_planned_video_count(*, repeat_count: int | None, subtask_count: int | None) -> int:
    repeat = max(_to_int(repeat_count), 0)
    subtasks = max(_to_int(subtask_count), 0)
    return repeat * subtasks


def compute_publish_inventory_gap(
    *,
    target_unpublished_count: int | None,
    current_unpublished_count: int | None,
    planned_step_one_video_count: int | None,
) -> int:
    target = max(_to_int(target_unpublished_count), 0)
    current = max(_to_int(current_unpublished_count), 0)
    planned = max(_to_int(planned_step_one_video_count), 0)
    return max(target - current - planned, 0)


def _published_sort_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    return value


def score_used_template_from_publications(publications: Iterable[Any]) -> UsedTemplateScore:
    rows = sorted(
        list(publications or []),
        key=lambda item: _published_sort_value(getattr(item, "published_at", None)),
        reverse=True,
    )
    latest_published_at = getattr(rows[0], "published_at", None) if rows else None
    for row in rows:
        views = _to_int(getattr(row, "total_views", 0))
        if views > 0:
            return UsedTemplateScore(
                score_views=views,
                latest_published_at=latest_published_at,
                scored_published_at=getattr(row, "published_at", None),
            )
    return UsedTemplateScore(
        score_views=0,
        latest_published_at=latest_published_at,
        scored_published_at=None,
    )


def match_category_rule(
    major_category: str | None,
    total_views: int | None,
    category_rules: dict | None,
) -> CategoryRuleMatch | None:
    if not major_category or not isinstance(category_rules, dict):
        return None
    rule = category_rules.get(str(major_category))
    if not isinstance(rule, dict) or not rule.get("enabled"):
        return None
    min_views = max(_to_int(rule.get("min_views")), 0)
    repeat_count = max(_to_int(rule.get("repeat_count")), 0)
    if repeat_count <= 0:
        return None
    if _to_int(total_views) <= min_views:
        return None
    return CategoryRuleMatch(
        major_category=str(major_category),
        min_views=min_views,
        repeat_count=repeat_count,
    )


def _as_positive_int(value: Any, default: int) -> int:
    parsed = _to_int(value)
    return parsed if parsed > 0 else default


def _as_local_datetime(value: datetime) -> datetime:
    tz = ZoneInfo("Asia/Shanghai")
    if value.tzinfo is None:
        return value.replace(tzinfo=tz)
    return value.astimezone(tz)


def _target_day_utc_range(now_local: datetime, lookback_days: int) -> tuple[Any, datetime, datetime]:
    local = _as_local_datetime(now_local)
    target_day = local.date() - timedelta(days=max(int(lookback_days or 0), 0))
    tz = local.tzinfo or ZoneInfo("Asia/Shanghai")
    start_local = datetime.combine(target_day, time.min, tzinfo=tz)
    end_local = start_local + timedelta(days=1)
    return target_day, start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc)


async def count_publishable_inventory(session: AsyncSession, account_id: UUID) -> int:
    from sqlalchemy import func

    from app.models.video_task import VideoSubTask, VideoTask

    return int(await session.scalar(
        select(func.count(VideoSubTask.id))
        .join(VideoTask, VideoTask.id == VideoSubTask.task_id)
        .where(VideoTask.account_id == account_id)
        .where(VideoSubTask.status == "queued")
        .where(VideoSubTask.result_video_url.is_not(None))
        .where(VideoSubTask.publish_meta["status"].as_string() == "done")
    ) or 0)


async def _load_bound_accounts(session: AsyncSession, owner_id: UUID) -> list[Any]:
    from app.models.account import Account
    from app.models.account_blogger_binding import AccountBloggerBinding
    from app.models.account_channel_reservation import AccountChannelReservation

    rows = await session.execute(
        select(Account)
        .where(Account.owner_id == owner_id)
        .where(
            exists().where(
                AccountChannelReservation.account_id == Account.id,
                AccountChannelReservation.status == "bound",
            )
        )
        .where(
            exists().where(
                AccountBloggerBinding.account_id == Account.id,
            )
        )
        .order_by(Account.created_at.asc())
    )
    return list(rows.scalars().all())


def _account_allowed_majors(account: Any) -> list[str]:
    cls_type = getattr(account, "classification_type", None)
    summary = getattr(account, "classification_summary", None) or {}
    if cls_type not in {"single", "dual"}:
        return []
    values = []
    primary = summary.get("primary_key")
    secondary = summary.get("secondary_key")
    if primary:
        values.append(str(primary))
    if cls_type == "dual" and secondary:
        values.append(str(secondary))
    return list(dict.fromkeys(values))


async def _account_tag_ids(session: AsyncSession, account_id: UUID) -> list[UUID]:
    from app.models.account_tag import AccountTag

    return list((await session.execute(
        select(AccountTag.tag_id).where(AccountTag.account_id == account_id)
    )).scalars().all())


def _template_duration(template: Any, video_source: Any | None) -> str:
    seconds = _to_int(getattr(video_source, "duration", 0))
    seconds = min(seconds, 15) if seconds > 0 else 0
    return f"{seconds}s" if seconds else "0s"


def _template_shots(template: Any) -> list:
    return [
        {key: value for key, value in shot.items() if key != "image_base64"}
        for shot in (getattr(template, "extracted_shots", None) or [])
        if isinstance(shot, dict)
    ]


async def _create_task_from_template(
    session: AsyncSession,
    *,
    owner_id: UUID,
    account_id: UUID,
    template: Any,
    video_source: Any | None,
    subtask_count: int,
    template_reuse_reason: str | None = None,
    template_usage_source_step: str | None = None,
) -> UUID:
    from app.services.video_task_service import VideoTaskService

    svc = VideoTaskService(db=session)
    task = await svc.create_task(
        account_id=account_id,
        template_id=template.id,
        final_prompt=getattr(template, "prompt_description", None) or "",
        duration=_template_duration(template, video_source),
        shots=_template_shots(template),
        user_id=owner_id,
        subtask_count=max(int(subtask_count or 1), 1),
        template_reuse_reason=template_reuse_reason,
        template_usage_source="scheduled",
        template_usage_source_step=template_usage_source_step,
    )
    return task.id


async def _load_video_source_map(session: AsyncSession, templates: Iterable[Any]) -> dict[UUID, Any]:
    from app.models.video_source import VideoSource

    ids = list({tpl.video_source_id for tpl in templates if getattr(tpl, "video_source_id", None)})
    if not ids:
        return {}
    rows = list((await session.execute(
        select(VideoSource).where(VideoSource.id.in_(ids))
    )).scalars().all())
    return {row.id: row for row in rows}


async def _template_matches_account_classification(
    session: AsyncSession,
    *,
    account: Any,
    template: Any,
) -> bool:
    from app.models.video_classification import VideoClassification

    allowed = _account_allowed_majors(account)
    if not allowed:
        return True
    if not getattr(template, "video_source_id", None):
        return False
    return bool(await session.scalar(
        select(VideoClassification.id)
        .where(VideoClassification.video_source_id == template.video_source_id)
        .where(VideoClassification.status == "success")
        .where(VideoClassification.major_category.in_(allowed))
        .limit(1)
    ))


async def _load_unused_templates(
    session: AsyncSession,
    *,
    account: Any,
    owner_id: UUID,
    limit: int,
    months: int,
    exclude_template_ids: set[UUID],
    now_utc: datetime,
) -> list[tuple[Any, Any | None]]:
    from app.models.tag import VideoSourceTag
    from app.models.video_ai_template import VideoAITemplate
    from app.models.video_source import VideoSource

    tag_ids = await _account_tag_ids(session, account.id)
    if not tag_ids or limit <= 0:
        return []
    cutoff = now_utc - timedelta(days=max(int(months or 1), 1) * 31)
    rows = list((await session.execute(
        select(VideoAITemplate, VideoSource)
        .join(VideoSource, VideoSource.id == VideoAITemplate.video_source_id)
        .where(VideoAITemplate.owner_id == owner_id)
        .where(VideoAITemplate.is_used.is_(False))
        .where(VideoAITemplate.id.not_in(exclude_template_ids))
        .where(VideoSource.publish_date.is_not(None))
        .where(VideoSource.publish_date >= cutoff)
        .where(
            exists().where(
                VideoSourceTag.video_ai_template_id == VideoAITemplate.id,
                VideoSourceTag.tag_id.in_(tag_ids),
            )
        )
        .order_by(VideoSource.view_count.desc().nullslast(), VideoAITemplate.created_at.desc())
    )).all())
    matched: list[tuple[Any, Any | None]] = []
    for template, source in rows:
        if await _template_matches_account_classification(session, account=account, template=template):
            matched.append((template, source))
        if len(matched) >= limit:
            break
    return matched


async def _template_has_recent_publication(
    session: AsyncSession,
    *,
    account_id: UUID,
    template_id: UUID,
    cutoff: datetime,
) -> bool:
    from app.models.video_publication import VideoPublication
    from app.models.video_task import VideoSubTask, VideoTask

    return bool(await session.scalar(
        select(VideoPublication.id)
        .join(VideoSubTask, VideoSubTask.id == VideoPublication.sub_task_id)
        .join(VideoTask, VideoTask.id == VideoSubTask.task_id)
        .where(VideoTask.account_id == account_id)
        .where(VideoTask.template_id == template_id)
        .where(VideoPublication.status.in_(["completed", "partial"]))
        .where(VideoPublication.completed_at.is_not(None))
        .where(VideoPublication.completed_at >= cutoff)
        .limit(1)
    ))


async def _score_used_template(
    session: AsyncSession,
    *,
    account_id: UUID,
    template_id: UUID,
) -> UsedTemplateScore:
    from types import SimpleNamespace

    from app.models.video_publication import VideoPublication
    from app.models.video_task import VideoSubTask, VideoTask

    rows = list((await session.execute(
        select(VideoPublication)
        .join(VideoSubTask, VideoSubTask.id == VideoPublication.sub_task_id)
        .join(VideoTask, VideoTask.id == VideoSubTask.task_id)
        .where(VideoTask.account_id == account_id)
        .where(VideoTask.template_id == template_id)
        .where(VideoPublication.status.in_(["completed", "partial"]))
        .where(VideoPublication.completed_at.is_not(None))
        .order_by(VideoPublication.completed_at.desc())
    )).scalars().all())
    return score_used_template_from_publications([
        SimpleNamespace(
            published_at=row.completed_at,
            total_views=total_publication_views(row.metrics_snapshot),
        )
        for row in rows
    ])


async def _load_used_templates(
    session: AsyncSession,
    *,
    account: Any,
    owner_id: UUID,
    limit: int,
    cooldown_days: int,
    exclude_template_ids: set[UUID],
    now_utc: datetime,
) -> list[tuple[Any, Any | None]]:
    from app.models.tag import VideoSourceTag
    from app.models.video_ai_template import VideoAITemplate
    from app.models.video_source import VideoSource
    from app.models.video_task import VideoTask

    tag_ids = await _account_tag_ids(session, account.id)
    if not tag_ids or limit <= 0:
        return []

    rows = list((await session.execute(
        select(VideoAITemplate)
        .where(VideoAITemplate.owner_id == owner_id)
        .where(VideoAITemplate.is_used.is_(True))
        .where(VideoAITemplate.id.not_in(exclude_template_ids))
        .where(
            exists().where(
                VideoTask.account_id == account.id,
                VideoTask.template_id == VideoAITemplate.id,
            )
        )
        .where(
            exists().where(
                VideoSourceTag.video_ai_template_id == VideoAITemplate.id,
                VideoSourceTag.tag_id.in_(tag_ids),
            )
        )
    )).scalars().all())

    cutoff = now_utc - timedelta(days=max(int(cooldown_days or 1), 1))
    scored: list[tuple[Any, UsedTemplateScore]] = []
    for template in rows:
        if await _template_has_recent_publication(
            session,
            account_id=account.id,
            template_id=template.id,
            cutoff=cutoff,
        ):
            continue
        if not await _template_matches_account_classification(session, account=account, template=template):
            continue
        scored.append((template, await _score_used_template(session, account_id=account.id, template_id=template.id)))

    scored.sort(
        key=lambda item: (
            item[1].score_views,
            _published_sort_value(item[1].latest_published_at) if item[1].latest_published_at is not None else datetime.min,
        ),
        reverse=True,
    )
    selected = [template for template, _score in scored[:limit]]
    vs_map = await _load_video_source_map(session, selected)
    return [(template, vs_map.get(template.video_source_id)) for template in selected]


async def _step_one_republish(
    session: AsyncSession,
    *,
    owner_id: UUID,
    target_start_utc: datetime,
    target_end_utc: datetime,
    category_rules: dict,
    subtask_count: int,
    run_id: UUID | None = None,
) -> tuple[int, dict[UUID, int], dict[UUID, set[UUID]]]:
    from app.models.scheduled_generation_run import ScheduledGenerationRunItem
    from app.models.account_blogger_binding import AccountBloggerBinding
    from app.models.account_channel_reservation import AccountChannelReservation
    from app.models.video_ai_template import VideoAITemplate
    from app.models.video_classification import VideoClassification
    from app.models.video_publication import VideoPublication
    from app.models.video_task import VideoSubTask, VideoTask

    rows = list((await session.execute(
        select(VideoPublication, VideoTask.account_id, VideoAITemplate, VideoClassification.major_category)
        .join(VideoSubTask, VideoSubTask.id == VideoPublication.sub_task_id)
        .join(VideoTask, VideoTask.id == VideoSubTask.task_id)
        .join(VideoAITemplate, VideoAITemplate.id == VideoTask.template_id)
        .join(VideoClassification, VideoClassification.video_source_id == VideoAITemplate.video_source_id)
        .where(VideoTask.owner_id == owner_id)
        .where(VideoTask.account_id.is_not(None))
        .where(VideoPublication.status.in_(["completed", "partial"]))
        .where(VideoPublication.completed_at.is_not(None))
        .where(VideoPublication.completed_at >= target_start_utc)
        .where(VideoPublication.completed_at < target_end_utc)
        .where(VideoClassification.status == "success")
        .where(
            exists().where(
                AccountChannelReservation.account_id == VideoTask.account_id,
                AccountChannelReservation.status == "bound",
            )
        )
        .where(
            exists().where(
                AccountBloggerBinding.account_id == VideoTask.account_id,
            )
        )
    )).all())

    created_tasks = 0
    planned_videos_by_account: dict[UUID, int] = {}
    selected_template_ids_by_account: dict[UUID, set[UUID]] = {}
    vs_map = await _load_video_source_map(session, [row[2] for row in rows])

    for publication, account_id, template, major_category in rows:
        views = total_publication_views(publication.metrics_snapshot)
        match = match_category_rule(major_category, views, category_rules)
        if match is None:
            continue
        created_task_ids: list[str] = []
        for _ in range(match.repeat_count):
            task_id = await _create_task_from_template(
                session,
                owner_id=owner_id,
                account_id=account_id,
                template=template,
                video_source=vs_map.get(template.video_source_id),
                subtask_count=subtask_count,
                template_reuse_reason="high_performance_reuse",
                template_usage_source_step="high_performance_republish",
            )
            created_task_ids.append(str(task_id))
            created_tasks += 1
        if run_id is not None:
            session.add(ScheduledGenerationRunItem(
                run_id=run_id,
                owner_id=owner_id,
                account_id=account_id,
                source_step="high_performance_republish",
                template_id=template.id,
                publication_id=publication.id,
                major_category=major_category,
                total_views=views,
                threshold_views=match.min_views,
                repeat_count=match.repeat_count,
                subtask_count=subtask_count,
                created_task_ids=created_task_ids,
            ))
        planned_videos_by_account[account_id] = planned_videos_by_account.get(account_id, 0) + compute_planned_video_count(
            repeat_count=match.repeat_count,
            subtask_count=subtask_count,
        )
        selected_template_ids_by_account.setdefault(account_id, set()).add(template.id)

    return created_tasks, planned_videos_by_account, selected_template_ids_by_account


async def execute_scheduled_generation_for_owner(
    session: AsyncSession,
    *,
    owner_id: UUID,
    trigger_key: str,
    now_local: datetime,
    config: dict,
) -> ScheduledGenerationResult:
    from app.models.scheduled_generation_run import ScheduledGenerationRun, ScheduledGenerationRunItem

    lookback_days = _as_positive_int(config.get("lookback_days"), 2)
    target_unpublished = _as_positive_int(config.get("target_unpublished_count"), 5)
    subtask_count = _as_positive_int(config.get("subtask_count"), 1)
    unused_months = _as_positive_int(config.get("unused_template_months"), 3)
    cooldown_days = _as_positive_int(config.get("used_template_cooldown_days"), 30)
    category_rules = config.get("category_rules") or {}
    target_day, target_start_utc, target_end_utc = _target_day_utc_range(now_local, lookback_days)
    now_utc = _as_local_datetime(now_local).astimezone(timezone.utc)

    run = ScheduledGenerationRun(
        owner_id=owner_id,
        trigger_key=trigger_key,
        target_date=target_day,
        status="running",
        config_snapshot={
            "lookback_days": lookback_days,
            "target_unpublished_count": target_unpublished,
            "subtask_count": subtask_count,
            "unused_template_months": unused_months,
            "used_template_cooldown_days": cooldown_days,
            "category_rules": category_rules,
        },
    )
    session.add(run)
    await session.flush()

    try:
        accounts = await _load_bound_accounts(session, owner_id)
        step_one_created, planned_by_account, step_one_template_ids_by_account = await _step_one_republish(
            session,
            owner_id=owner_id,
            target_start_utc=target_start_utc,
            target_end_utc=target_end_utc,
            category_rules=category_rules,
            subtask_count=subtask_count,
            run_id=run.id,
        )

        unused_created = 0
        used_created = 0
        shortfall = 0

        for account in accounts:
            selected_template_ids = set(step_one_template_ids_by_account.get(account.id, set()))
            current_inventory = await count_publishable_inventory(session, account.id)
            need_videos = compute_publish_inventory_gap(
                target_unpublished_count=target_unpublished,
                current_unpublished_count=current_inventory,
                planned_step_one_video_count=planned_by_account.get(account.id, 0),
            )
            need_tasks = max((need_videos + subtask_count - 1) // subtask_count, 0)
            unused_templates = await _load_unused_templates(
                session,
                account=account,
                owner_id=owner_id,
                limit=need_tasks,
                months=unused_months,
                exclude_template_ids=selected_template_ids,
                now_utc=now_utc,
            )
            for template, source in unused_templates:
                task_id = await _create_task_from_template(
                    session,
                    owner_id=owner_id,
                    account_id=account.id,
                    template=template,
                    video_source=source,
                    subtask_count=subtask_count,
                    template_usage_source_step="unused_template_top_up",
                )
                session.add(ScheduledGenerationRunItem(
                    run_id=run.id,
                    owner_id=owner_id,
                    account_id=account.id,
                    source_step="unused_template_top_up",
                    template_id=template.id,
                    total_views=getattr(source, "view_count", None) if source is not None else None,
                    subtask_count=subtask_count,
                    created_task_ids=[str(task_id)],
                ))
                selected_template_ids.add(template.id)
                unused_created += 1

            remaining_tasks = max(need_tasks - len(unused_templates), 0)
            used_templates = await _load_used_templates(
                session,
                account=account,
                owner_id=owner_id,
                limit=remaining_tasks,
                cooldown_days=cooldown_days,
                exclude_template_ids=selected_template_ids,
                now_utc=now_utc,
            )
            for template, source in used_templates:
                task_id = await _create_task_from_template(
                    session,
                    owner_id=owner_id,
                    account_id=account.id,
                    template=template,
                    video_source=source,
                    subtask_count=subtask_count,
                    template_reuse_reason="inventory_fallback_reuse",
                    template_usage_source_step="used_template_top_up",
                )
                session.add(ScheduledGenerationRunItem(
                    run_id=run.id,
                    owner_id=owner_id,
                    account_id=account.id,
                    source_step="used_template_top_up",
                    template_id=template.id,
                    total_views=getattr(source, "view_count", None) if source is not None else None,
                    subtask_count=subtask_count,
                    created_task_ids=[str(task_id)],
                ))
                selected_template_ids.add(template.id)
                used_created += 1

            missing_tasks = max(remaining_tasks - len(used_templates), 0)
            if missing_tasks > 0:
                missing_videos = missing_tasks * subtask_count
                session.add(ScheduledGenerationRunItem(
                    run_id=run.id,
                    owner_id=owner_id,
                    account_id=account.id,
                    source_step="shortfall",
                    subtask_count=subtask_count,
                    skip_reason=f"缺少 {missing_videos} 条未发布视频库存",
                ))
                shortfall += missing_videos

        total_created = step_one_created + unused_created + used_created
        run.status = "completed"
        run.account_count = len(accounts)
        run.total_created_tasks = total_created
        run.step_one_created_tasks = step_one_created
        run.unused_template_created_tasks = unused_created
        run.used_template_created_tasks = used_created
        run.shortfall_count = shortfall
        await session.commit()

        return ScheduledGenerationResult(
            owner_id=owner_id,
            trigger_key=trigger_key,
            target_date=target_day,
            account_count=len(accounts),
            total_created_tasks=total_created,
            step_one_created_tasks=step_one_created,
            unused_template_created_tasks=unused_created,
            used_template_created_tasks=used_created,
            shortfall_count=shortfall,
        )
    except Exception as exc:
        run.status = "failed"
        run.error_message = str(exc)
        await session.commit()
        raise
