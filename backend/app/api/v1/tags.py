from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import TokenData, get_current_user
from app.db.session import get_db
from app.models.tag import Tag
from app.schemas.video_source import TagCreate, TagRead

router = APIRouter(prefix="/tags", tags=["tags"])


def _owner_id(current_user: TokenData = Depends(get_current_user)) -> uuid.UUID | None:
    """Admin gets None (global scope), regular user gets their own id."""
    return None if current_user.is_admin else current_user.user_id


@router.get("", response_model=list[TagRead])
async def list_tags(
    owner_id: uuid.UUID | None = Depends(_owner_id),
    session: AsyncSession = Depends(get_db),
) -> list[TagRead]:
    """List tags visible to the current user."""
    stmt = select(Tag).order_by(Tag.created_at.asc())
    if owner_id is not None:
        stmt = stmt.where(Tag.owner_id == owner_id)
    rows = (await session.execute(stmt)).scalars().all()
    return [TagRead.model_validate(r) for r in rows]


@router.post("", response_model=TagRead, status_code=201)
async def create_tag(
    payload: TagCreate,
    current_user: TokenData = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> TagRead:
    tag = Tag(
        owner_id=current_user.user_id,
        name=payload.name,
        color=payload.color,
    )
    session.add(tag)
    await session.commit()
    await session.refresh(tag)
    return TagRead.model_validate(tag)


@router.delete("/{tag_id}", status_code=204)
async def delete_tag(
    tag_id: uuid.UUID,
    owner_id: uuid.UUID | None = Depends(_owner_id),
    session: AsyncSession = Depends(get_db),
) -> Response:
    stmt = select(Tag).where(Tag.id == tag_id)
    if owner_id is not None:
        stmt = stmt.where(Tag.owner_id == owner_id)
    tag = await session.scalar(stmt)
    if tag:
        await session.delete(tag)
        await session.commit()
    return Response(status_code=204)
