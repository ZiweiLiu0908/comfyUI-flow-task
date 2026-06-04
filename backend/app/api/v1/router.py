from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.v1 import account_channel_reservations, accounts, auth, candidates, external_supplement, face_library, flags, formal_backfill, open_api_account_query, persona_tagging, settings, tags, tiktok_bloggers, topics, uploads, video_ai_templates, video_sources, video_tasks, video_task_config, video_publications
from app.core.security import get_current_user

api_router = APIRouter(prefix="/api/v1")

# ── Public routes (no auth required) ──────────────────────────────────────────
api_router.include_router(auth.router)       # /auth/login is public
api_router.include_router(video_publications.router)  # Open API 代理（测试阶段无需认证）
api_router.include_router(account_channel_reservations.router)
api_router.include_router(open_api_account_query.router)
api_router.include_router(external_supplement.router)  # vendor 回调，X-API-Key 自校验

# ── Protected routes (Bearer token required) ──────────────────────────────────
_auth_dep = [Depends(get_current_user)]

api_router.include_router(settings.router, dependencies=_auth_dep)
api_router.include_router(video_sources.router, dependencies=_auth_dep)
api_router.include_router(video_ai_templates.router, dependencies=_auth_dep)
api_router.include_router(accounts.router, dependencies=_auth_dep)
# video_tasks: per-endpoint auth (some endpoints are public, some require token)
api_router.include_router(video_tasks.router)
api_router.include_router(video_task_config.router, dependencies=_auth_dep)
api_router.include_router(tags.router, dependencies=_auth_dep)
api_router.include_router(flags.router, dependencies=_auth_dep)
api_router.include_router(tiktok_bloggers.router, dependencies=_auth_dep)
api_router.include_router(topics.router, dependencies=_auth_dep)
api_router.include_router(candidates.router, dependencies=_auth_dep)
api_router.include_router(face_library.router, dependencies=_auth_dep)
api_router.include_router(uploads.router, dependencies=_auth_dep)
api_router.include_router(formal_backfill.router)  # 内部接 admin 校验
api_router.include_router(persona_tagging.router, dependencies=_auth_dep)
