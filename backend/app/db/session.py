from __future__ import annotations

import json
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings


def _json_serializer(obj):
    return json.dumps(obj, ensure_ascii=False)


def _engine_options() -> dict:
    options = {
        "future": True,
        "pool_pre_ping": True,
        "json_serializer": _json_serializer,
    }
    if settings.database_url.startswith("sqlite"):
        return options
    options.update({
        # 多个 scheduler + 10 个 video_ai pipeline + HTTP + 后台任务 + 偶发慢查询，
        # 老配置 20+20=40 连接 30s 超时容易打满。pool_recycle 防止 PG 端 idle 超时
        # 拿到死连接，pool_timeout 适度延长容忍突发。
        "pool_size": 40,
        "max_overflow": 40,
        "pool_timeout": 60,
        "pool_recycle": 1800,
    })
    return options


engine = create_async_engine(
    settings.database_url,
    **_engine_options(),
)
SessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
