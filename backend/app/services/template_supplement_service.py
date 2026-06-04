from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Any, Iterable

from sqlalchemy import exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.account_blogger_binding import AccountBloggerBinding
from app.models.account_tag import AccountTag
from app.models.tag import VideoSourceTag
from app.models.video_ai_template import VideoAITemplate
from app.models.video_classification import VideoClassification
from app.models.video_source import VideoSource


_CATEGORY_MAJOR: dict[str, str] = {
    "beauty_static_pose": "beauty",
    "beauty_light_action": "beauty",
    "beauty_dance": "beauty",
    "beauty_lipsync": "beauty",
    "beauty_drama_light": "beauty",
    "method_single_silent": "method",
    "method_multi_look": "method",
    "method_multi_build": "method",
    "method_base_replace": "method",
    "method_multiway": "method",
    "method_before_after": "method",
    "method_compare": "method",
    "method_voice_formula": "method",
    "method_voice_steps": "method",
    "method_voice_diagnose": "method",
    "method_voice_compare": "method",
    "method_voice_case": "method",
    "method_voice_standard": "method",
    "method_voice_system": "method",
    "shopping_brand": "shopping",
    "shopping_single_item": "shopping",
    "shopping_dupe": "shopping",
    "shopping_scene": "shopping",
    "shopping_list": "shopping",
    "shopping_compare": "shopping",
    "lifestyle": "lifestyle",
    "drama": "drama",
    "unclassifiable": "unclassifiable",
}
_VALID_CATEGORY_KEYS = frozenset(_CATEGORY_MAJOR)


@dataclass(frozen=True)
class AccountTopUpPlan:
    account_id: uuid.UUID
    mode: str
    target_unused_template_count: int
    current_unused_template_count: int
    need_count: int
    skip_reason: str | None = None


def compute_supplement_gap(current_unused_count: int | None, target_unused_count: int | None) -> int:
    current = max(int(current_unused_count or 0), 0)
    target = max(int(target_unused_count or 0), 0)
    return max(target - current, 0)


def resolve_supplement_mode_for_account(account: Any) -> str:
    return "auto" if getattr(account, "classification_type", None) in {"single", "dual"} else "exclusive"


def should_start_another_round(
    *,
    completed_rounds: int,
    current_unused_count: int,
    target_unused_count: int,
    max_rounds: int,
) -> bool:
    if int(completed_rounds or 0) >= max(int(max_rounds or 0), 1):
        return False
    return compute_supplement_gap(current_unused_count, target_unused_count) > 0


def normalize_category_keys(raw: Any) -> list[str]:
    if not raw:
        return []
    if not isinstance(raw, list):
        raw = [raw]
    values: list[str] = []
    for item in raw:
        key = str(item).strip() if item else ""
        if key in _VALID_CATEGORY_KEYS and key not in values:
            values.append(key)
    return values


def category_major(category_key: str | None) -> str | None:
    if not category_key:
        return None
    return _CATEGORY_MAJOR.get(category_key, category_key)


def account_allowed_major_keys(account: Any) -> list[str]:
    cls_type = getattr(account, "classification_type", None)
    summary = getattr(account, "classification_summary", None) or {}
    if cls_type not in {"single", "dual"}:
        return []
    keys = []
    primary = summary.get("primary_key")
    secondary = summary.get("secondary_key")
    if primary:
        keys.append(str(primary))
    if cls_type == "dual" and secondary:
        keys.append(str(secondary))
    return list(dict.fromkeys(keys))


def should_bind_template_to_account(
    account: Any,
    *,
    mode: str,
    category_key: str | None,
    filter_category_keys: Iterable[str] | None = None,
) -> bool:
    if mode == "auto":
        major = category_major(category_key)
        return bool(major and major in account_allowed_major_keys(account))

    selected = set(normalize_category_keys(list(filter_category_keys or [])))
    if not selected:
        return True
    if not category_key:
        return False
    return category_key in selected or (category_major(category_key) in selected)


def filter_accounts_for_template_binding(
    accounts: Iterable[Any],
    *,
    mode: str,
    category_key: str | None,
    filter_category_keys: Iterable[str] | None,
) -> list[Any]:
    return [
        account
        for account in accounts
        if should_bind_template_to_account(
            account,
            mode=mode,
            category_key=category_key,
            filter_category_keys=filter_category_keys,
        )
    ]


def filters_category_keys(filters: dict | None) -> list[str]:
    return normalize_category_keys((filters or {}).get("category_keys"))


def _coerce_publish_after(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min, tzinfo=timezone.utc)
    if isinstance(value, str) and value.strip():
        try:
            parsed = date.fromisoformat(value.strip())
        except ValueError:
            return None
        return datetime.combine(parsed, time.min, tzinfo=timezone.utc)
    return None


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


async def account_has_bound_blogger(session: AsyncSession, account_id: uuid.UUID) -> bool:
    return bool(await session.scalar(
        select(AccountBloggerBinding.id)
        .where(AccountBloggerBinding.account_id == account_id)
        .limit(1)
    ))


async def count_account_unused_templates(
    session: AsyncSession,
    *,
    account: Account,
    owner_id: uuid.UUID | None,
    mode: str,
    filters: dict | None = None,
) -> int:
    tag_ids = list((await session.execute(
        select(AccountTag.tag_id).where(AccountTag.account_id == account.id)
    )).scalars().all())
    if not tag_ids:
        return 0

    stmt = (
        select(VideoAITemplate.id, VideoAITemplate.video_source_id)
        .join(VideoSource, VideoSource.id == VideoAITemplate.video_source_id)
        .where(
            exists().where(
                VideoSourceTag.video_ai_template_id == VideoAITemplate.id,
                VideoSourceTag.tag_id.in_(tag_ids),
            )
        )
        .where(or_(VideoAITemplate.is_used.is_(False), VideoAITemplate.repeatable.is_(True)))
    )
    if owner_id is not None:
        stmt = stmt.where(VideoAITemplate.owner_id == owner_id)

    min_views = _positive_int((filters or {}).get("min_view_count"))
    if min_views is not None:
        stmt = stmt.where(VideoSource.view_count >= min_views)
    published_after = _coerce_publish_after((filters or {}).get("published_after"))
    if published_after is not None:
        stmt = stmt.where(VideoSource.publish_date >= published_after)
    max_duration = _positive_int((filters or {}).get("max_duration_seconds"))
    if max_duration is not None:
        stmt = stmt.where(VideoSource.duration <= max_duration)

    rows = list((await session.execute(stmt)).all())
    if not rows:
        return 0

    video_source_ids = [row.video_source_id for row in rows if row.video_source_id]
    allowed_major_keys: list[str] = []
    allowed_category_keys: list[str] = []
    if mode == "auto":
        allowed_major_keys = account_allowed_major_keys(account)
        if not allowed_major_keys:
            return 0
    else:
        allowed_category_keys = filters_category_keys(filters)

    if allowed_major_keys or allowed_category_keys:
        matched_vs_ids = await _matched_video_source_ids(
            session,
            video_source_ids=video_source_ids,
            allowed_major_keys=allowed_major_keys,
            allowed_category_keys=allowed_category_keys,
        )
        return sum(1 for row in rows if row.video_source_id in matched_vs_ids)

    return len({row.id for row in rows})


async def _matched_video_source_ids(
    session: AsyncSession,
    *,
    video_source_ids: list[uuid.UUID],
    allowed_major_keys: list[str],
    allowed_category_keys: list[str],
) -> set[uuid.UUID]:
    if not video_source_ids:
        return set()
    clauses = []
    if allowed_major_keys:
        clauses.append(VideoClassification.major_category.in_(allowed_major_keys))
    if allowed_category_keys:
        clauses.append(VideoClassification.category_key.in_(allowed_category_keys))
        clauses.append(VideoClassification.major_category.in_(allowed_category_keys))
    if not clauses:
        return set(video_source_ids)
    return set((await session.execute(
        select(VideoClassification.video_source_id)
        .where(VideoClassification.video_source_id.in_(video_source_ids))
        .where(VideoClassification.status == "success")
        .where(or_(*clauses))
    )).scalars().all())


async def build_account_top_up_plan(
    session: AsyncSession,
    *,
    account_id: uuid.UUID,
    owner_id: uuid.UUID | None,
    mode: str,
    target_unused_template_count: int,
    filters: dict | None = None,
    sync_first: bool = True,
) -> AccountTopUpPlan:
    account = await session.get(Account, account_id)
    if account is None:
        return AccountTopUpPlan(account_id, mode, target_unused_template_count, 0, 0, "账号不存在")
    if not await account_has_bound_blogger(session, account_id):
        return AccountTopUpPlan(account_id, mode, target_unused_template_count, 0, 0, "无绑定博主")
    if mode == "auto" and resolve_supplement_mode_for_account(account) != "auto":
        return AccountTopUpPlan(account_id, mode, target_unused_template_count, 0, 0, "非单核心/双核心")

    if sync_first:
        from app.services.account_template_tag_service import ensure_account_template_tags

        await ensure_account_template_tags(
            session,
            account_id,
            owner_id=owner_id,
            bind_mode=mode,
            category_keys=filters_category_keys(filters),
        )

    current = await count_account_unused_templates(
        session,
        account=account,
        owner_id=owner_id,
        mode=mode,
        filters=filters,
    )
    need = compute_supplement_gap(current, target_unused_template_count)
    return AccountTopUpPlan(account_id, mode, target_unused_template_count, current, need)


async def bind_template_to_matching_accounts(
    session: AsyncSession,
    *,
    template_id: uuid.UUID,
    video_source_id: uuid.UUID,
    owner_id: uuid.UUID | None,
    source_account_id: uuid.UUID,
    mode: str,
    category_key: str | None,
    filter_category_keys: Iterable[str] | None = None,
) -> dict[str, int]:
    video_source = await session.get(VideoSource, video_source_id)
    if video_source is None:
        return {"matched_accounts": 0, "inserted_bindings": 0, "bound_account_ids": []}

    if video_source.tiktok_blogger_id is not None:
        account_stmt = (
            select(Account)
            .join(AccountBloggerBinding, AccountBloggerBinding.account_id == Account.id)
            .where(AccountBloggerBinding.tiktok_blogger_id == video_source.tiktok_blogger_id)
        )
        if owner_id is not None:
            account_stmt = account_stmt.where(Account.owner_id == owner_id)
        accounts = list((await session.execute(account_stmt)).scalars().all())
    else:
        account = await session.get(Account, source_account_id)
        accounts = [account] if account is not None else []

    eligible_accounts = filter_accounts_for_template_binding(
        accounts,
        mode=mode,
        category_key=category_key,
        filter_category_keys=filter_category_keys,
    )
    if not eligible_accounts:
        return {"matched_accounts": 0, "inserted_bindings": 0, "bound_account_ids": []}

    account_ids = [account.id for account in eligible_accounts]
    tag_rows = list((await session.execute(
        select(AccountTag.account_id, AccountTag.tag_id)
        .where(AccountTag.account_id.in_(account_ids))
    )).all())
    if not tag_rows:
        return {
            "matched_accounts": len(eligible_accounts),
            "inserted_bindings": 0,
            "bound_account_ids": [str(account.id) for account in eligible_accounts],
        }

    tag_ids = list({row.tag_id for row in tag_rows})
    existing_tag_ids = set((await session.execute(
        select(VideoSourceTag.tag_id)
        .where(VideoSourceTag.video_ai_template_id == template_id)
        .where(VideoSourceTag.tag_id.in_(tag_ids))
    )).scalars().all())

    inserted = 0
    for row in tag_rows:
        if row.tag_id in existing_tag_ids:
            continue
        session.add(VideoSourceTag(
            owner_id=owner_id,
            video_source_id=video_source_id,
            video_ai_template_id=template_id,
            tag_id=row.tag_id,
        ))
        existing_tag_ids.add(row.tag_id)
        inserted += 1
    return {
        "matched_accounts": len(eligible_accounts),
        "inserted_bindings": inserted,
        "bound_account_ids": [str(account.id) for account in eligible_accounts],
    }
