from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.account_blogger_binding import AccountBloggerBinding
from app.models.account_channel_reservation import AccountChannelReservation
from app.services.account_service import list_accounts


_FILTER_KEYS = {
    "gender",
    "account_type",
    "face_mode",
    "product_code_mode",
    "account_tier",
    "platform_binding_status",
    "classification_type",
    "category_keys",
    "flag_id",
    "search",
}


def _uuid_strings(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    if not isinstance(values, list):
        return result
    for value in values:
        try:
            parsed = str(UUID(str(value)))
        except (TypeError, ValueError):
            continue
        if parsed not in seen:
            result.append(parsed)
            seen.add(parsed)
    return result


def _clean_filters(filters: Any) -> dict[str, Any]:
    if not isinstance(filters, dict):
        return {}
    cleaned: dict[str, Any] = {}
    for key in _FILTER_KEYS:
        value = filters.get(key)
        if value in (None, "", []):
            continue
        if key == "category_keys":
            values = [str(item) for item in value if item] if isinstance(value, list) else []
            if values:
                cleaned[key] = values
        elif key == "flag_id":
            try:
                cleaned[key] = str(UUID(str(value)))
            except (TypeError, ValueError):
                continue
        else:
            cleaned[key] = value
    return cleaned


def normalize_schedule_scope(
    *,
    scope_mode: str | None,
    account_ids: Any,
    filters: Any,
) -> dict[str, Any]:
    ids = _uuid_strings(account_ids)
    if scope_mode == "selected" and ids:
        return {"mode": "selected", "account_ids": ids, "filters": {}}
    return {"mode": "filtered", "account_ids": [], "filters": _clean_filters(filters)}


async def resolve_schedule_scope_accounts(
    session: AsyncSession,
    *,
    owner_id: UUID | None,
    scope_mode: str | None,
    account_ids: Any,
    filters: Any,
    require_channel_bound: bool,
) -> list[Account]:
    scope = normalize_schedule_scope(scope_mode=scope_mode, account_ids=account_ids, filters=filters)
    if scope["mode"] == "selected":
        ids = [UUID(value) for value in scope["account_ids"]]
        rows = list((await session.execute(
            select(Account).where(Account.id.in_(ids))
        )).scalars().all())
        by_id = {account.id: account for account in rows}
        accounts = [by_id[account_id] for account_id in ids if account_id in by_id]
    else:
        f = scope["filters"]
        flag_id = UUID(f["flag_id"]) if f.get("flag_id") else None
        accounts, _ = await list_accounts(
            session,
            page=None,
            page_size=None,
            owner_id=owner_id,
            gender=f.get("gender"),
            account_type=f.get("account_type"),
            face_mode=f.get("face_mode"),
            product_code_mode=f.get("product_code_mode"),
            account_tier=f.get("account_tier"),
            platform_binding_status=f.get("platform_binding_status"),
            classification_type=f.get("classification_type"),
            category_keys=f.get("category_keys"),
            flag_id=flag_id,
            search=f.get("search"),
        )

    if not accounts:
        return []

    scoped_ids = [account.id for account in accounts]
    stmt = (
        select(Account)
        .where(Account.id.in_(scoped_ids))
        .where(exists().where(AccountBloggerBinding.account_id == Account.id))
    )
    if owner_id is not None:
        stmt = stmt.where(Account.owner_id == owner_id)
    if require_channel_bound:
        stmt = stmt.where(
            exists().where(
                AccountChannelReservation.account_id == Account.id,
                AccountChannelReservation.status == "bound",
            )
        )
    eligible = list((await session.execute(stmt)).scalars().all())
    eligible_by_id = {account.id: account for account in eligible}
    return [eligible_by_id[account.id] for account in accounts if account.id in eligible_by_id]
