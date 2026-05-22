from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account


BLOCKED_ACCOUNT_STATUSES = {"disabled", "shadowban"}
BLOCKED_ACCOUNT_STATUS_LABELS = {
    "disabled": "已禁用",
    "shadowban": "Shadowban",
}


def is_account_operation_blocked(account: Account | None) -> bool:
    return bool(account and account.platform_binding_status in BLOCKED_ACCOUNT_STATUSES)


async def filter_operable_account_ids(
    session: AsyncSession,
    account_ids: list[uuid.UUID],
    *,
    owner_id: uuid.UUID | None = None,
) -> tuple[list[uuid.UUID], dict[str, int]]:
    if not account_ids:
        return [], {}

    stmt = select(Account.id, Account.platform_binding_status).where(Account.id.in_(account_ids))
    if owner_id is not None:
        stmt = stmt.where(Account.owner_id == owner_id)
    rows = (await session.execute(stmt)).all()
    status_by_id = {account_id: status for account_id, status in rows}

    operable_ids: list[uuid.UUID] = []
    skip_reasons: dict[str, int] = {}
    for account_id in account_ids:
        status = status_by_id.get(account_id)
        if status in BLOCKED_ACCOUNT_STATUSES:
            skip_reasons[status] = skip_reasons.get(status, 0) + 1
            continue
        operable_ids.append(account_id)

    return operable_ids, skip_reasons
