from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account


@dataclass(frozen=True)
class AccountTemplateTagSyncResult:
    account_id: uuid.UUID
    owner_id: uuid.UUID | None
    source_templates: int
    already_bound: int
    newly_bound: int
    matched_templates: int
    unused_templates: int
    used_templates: int
    tag_count: int
    blogger_count: int

    def model_dump(self) -> dict:
        data = asdict(self)
        data["account_id"] = str(self.account_id)
        data["owner_id"] = str(self.owner_id) if self.owner_id else None
        return data


_SYNC_STATS_SQL = text(
    """
    WITH scope_templates AS (
      SELECT DISTINCT tpl.id AS template_id
      FROM video_ai_templates tpl
      JOIN video_sources vs ON vs.id = tpl.video_source_id
      JOIN account_tiktok_bloggers abb ON abb.tiktok_blogger_id = vs.tiktok_blogger_id
      WHERE abb.account_id = CAST(:account_id AS uuid)
        AND (
          CAST(:owner_id AS uuid) IS NULL
          OR COALESCE(tpl.owner_id, vs.owner_id) = CAST(:owner_id AS uuid)
        )
    ),
    account_tag_scope AS (
      SELECT DISTINCT tag_id
      FROM account_tags
      WHERE account_id = CAST(:account_id AS uuid)
    )
    SELECT
      (SELECT COUNT(*) FROM scope_templates) AS source_templates,
      (SELECT COUNT(*) FROM account_tag_scope) AS tag_count,
      (
        SELECT COUNT(*)
        FROM account_tiktok_bloggers
        WHERE account_id = CAST(:account_id AS uuid)
      ) AS blogger_count,
      (
        SELECT COUNT(*)
        FROM scope_templates st
        JOIN video_source_tags vst ON vst.video_ai_template_id = st.template_id
        JOIN account_tag_scope ats ON ats.tag_id = vst.tag_id
      ) AS existing_bindings
    """
)


_INSERT_MISSING_SQL = text(
    """
    INSERT INTO video_source_tags
      (id, owner_id, video_source_id, video_ai_template_id, tag_id, created_at)
    SELECT
      gen_random_uuid(),
      COALESCE(tpl.owner_id, vs.owner_id),
      tpl.video_source_id,
      tpl.id,
      at.tag_id,
      now()
    FROM video_ai_templates tpl
    JOIN video_sources vs ON vs.id = tpl.video_source_id
    JOIN account_tiktok_bloggers abb ON abb.tiktok_blogger_id = vs.tiktok_blogger_id
    JOIN account_tags at ON at.account_id = abb.account_id
    WHERE abb.account_id = CAST(:account_id AS uuid)
      AND (
        CAST(:owner_id AS uuid) IS NULL
        OR COALESCE(tpl.owner_id, vs.owner_id) = CAST(:owner_id AS uuid)
      )
      AND (
        :binding_filter_mode = 'none'
        OR (
          :binding_filter_mode = 'auto'
          AND EXISTS (
            SELECT 1
            FROM video_classifications vc
            WHERE vc.video_source_id = tpl.video_source_id
              AND vc.status = 'success'
              AND vc.major_category = ANY(CAST(:allowed_major_keys AS text[]))
          )
        )
        OR (
          :binding_filter_mode = 'category'
          AND EXISTS (
            SELECT 1
            FROM video_classifications vc
            WHERE vc.video_source_id = tpl.video_source_id
              AND vc.status = 'success'
              AND (
                vc.category_key = ANY(CAST(:category_keys AS text[]))
                OR vc.major_category = ANY(CAST(:category_keys AS text[]))
              )
          )
        )
      )
      AND NOT EXISTS (
        SELECT 1
        FROM video_source_tags vst
        WHERE vst.video_ai_template_id = tpl.id
          AND vst.tag_id = at.tag_id
      )
    RETURNING id
    """
)


_POOL_COUNTS_SQL = text(
    """
    WITH account_tag_scope AS (
      SELECT DISTINCT tag_id
      FROM account_tags
      WHERE account_id = CAST(:account_id AS uuid)
    ),
    tagged_templates AS (
      SELECT DISTINCT tpl.id, tpl.video_source_id, tpl.is_used, tpl.repeatable
      FROM video_ai_templates tpl
      JOIN video_source_tags vst ON vst.video_ai_template_id = tpl.id
      JOIN account_tag_scope ats ON ats.tag_id = vst.tag_id
      WHERE (
        CAST(:owner_id AS uuid) IS NULL
        OR tpl.owner_id = CAST(:owner_id AS uuid)
      )
    ),
    matched_templates AS (
      SELECT tt.*
      FROM tagged_templates tt
      WHERE (
        :use_classification_filter = false
        OR EXISTS (
          SELECT 1
          FROM video_classifications vc
          WHERE vc.video_source_id = tt.video_source_id
            AND vc.status = 'success'
            AND (
              vc.category_index = ANY(CAST(:allowed_indices AS integer[]))
              OR vc.major_category = ANY(CAST(:allowed_major_keys AS text[]))
            )
        )
      )
      AND (
        :use_category_filter = false
        OR EXISTS (
          SELECT 1
          FROM video_classifications vc
          WHERE vc.video_source_id = tt.video_source_id
            AND vc.status = 'success'
            AND (
              vc.category_key = ANY(CAST(:category_keys AS text[]))
              OR vc.major_category = ANY(CAST(:category_keys AS text[]))
            )
        )
      )
    )
    SELECT
      COUNT(*) AS matched_templates,
      COUNT(*) FILTER (WHERE (NOT is_used) OR repeatable) AS unused_templates,
      COUNT(*) FILTER (WHERE is_used) AS used_templates
    FROM matched_templates
    """
)


def _classification_filters(account: Account) -> tuple[list[int], list[str]]:
    cls_type = account.classification_type
    summary = account.classification_summary or {}
    if cls_type not in {"single", "dual"}:
        return [], []

    index_keys = ["primary_index"]
    major_keys = ["primary_key"]
    if cls_type == "dual":
        index_keys.append("secondary_index")
        major_keys.append("secondary_key")

    allowed_indices: list[int] = []
    for key in index_keys:
        value = summary.get(key)
        if value is not None:
            allowed_indices.append(int(value))

    allowed_major_keys = [
        str(summary[key])
        for key in major_keys
        if summary.get(key)
    ]
    return allowed_indices, allowed_major_keys


async def ensure_account_template_tags(
    session: AsyncSession,
    account_id: uuid.UUID,
    owner_id: uuid.UUID | None = None,
    *,
    bind_mode: str = "default",
    category_keys: list[str] | None = None,
) -> AccountTemplateTagSyncResult:
    account = await session.get(Account, account_id)
    if account is None:
        raise ValueError("account not found")

    effective_owner_id = owner_id if owner_id is not None else account.owner_id
    allowed_indices, allowed_major_keys = _classification_filters(account)
    normalized_category_keys = list(dict.fromkeys(category_keys or []))
    if bind_mode == "auto":
        binding_filter_mode = "auto"
    elif normalized_category_keys:
        binding_filter_mode = "category"
    else:
        binding_filter_mode = "none"
    params = {
        "account_id": account_id,
        "owner_id": effective_owner_id,
        "binding_filter_mode": binding_filter_mode,
        "allowed_major_keys": allowed_major_keys,
        "category_keys": normalized_category_keys,
    }
    before = (await session.execute(_SYNC_STATS_SQL, params)).first()

    inserted = (await session.execute(_INSERT_MISSING_SQL, params)).all()

    pool = (await session.execute(_POOL_COUNTS_SQL, {
        **params,
        "use_classification_filter": bool(allowed_indices or allowed_major_keys),
        "allowed_indices": allowed_indices,
        "allowed_major_keys": allowed_major_keys,
        "use_category_filter": bool(normalized_category_keys),
    })).first()

    return AccountTemplateTagSyncResult(
        account_id=account_id,
        owner_id=effective_owner_id,
        source_templates=int(getattr(before, "source_templates", 0) or 0),
        already_bound=int(getattr(before, "existing_bindings", 0) or 0),
        newly_bound=len(inserted),
        matched_templates=int(getattr(pool, "matched_templates", 0) or 0),
        unused_templates=int(getattr(pool, "unused_templates", 0) or 0),
        used_templates=int(getattr(pool, "used_templates", 0) or 0),
        tag_count=int(getattr(before, "tag_count", 0) or 0),
        blogger_count=int(getattr(before, "blogger_count", 0) or 0),
    )
