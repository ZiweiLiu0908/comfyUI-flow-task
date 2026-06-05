from __future__ import annotations

import tempfile
import unittest
import uuid
import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")
os.environ.setdefault("AUTH_SECRET", "test-auth-secret")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_template_reuse_tracking.sqlite3")


class TemplateReuseTrackingSQLiteTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmpdir.name) / "template_reuse.sqlite3"
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
        self.Session = async_sessionmaker(bind=self.engine, expire_on_commit=False)

        from app.db.base import Base
        import app.models  # noqa: F401

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self):
        await self.engine.dispose()
        self.tmpdir.cleanup()

    async def _seed_account_and_template(self, session, *, is_used: bool = False):
        from app.models.account import Account
        from app.models.video_ai_template import VideoAITemplate

        owner_id = uuid.uuid4()
        account = Account(
            id=uuid.uuid4(),
            owner_id=owner_id,
            account_name="Reuse Test Account",
            face_mode="no_face",
            product_code_mode="without_code",
        )
        template = VideoAITemplate(
            id=uuid.uuid4(),
            owner_id=owner_id,
            title="Reusable Template",
            prompt_description="outfit prompt",
            extracted_shots=[],
            is_used=is_used,
        )
        session.add_all([account, template])
        await session.commit()
        return owner_id, account, template

    async def test_first_use_records_history_without_reuse_marker(self):
        from app.models.template_usage_history import TemplateUsageHistory
        from app.services.video_task_service import VideoTaskService

        async with self.Session() as session:
            owner_id, account, template = await self._seed_account_and_template(session, is_used=False)
            task = await VideoTaskService(session).create_task(
                account_id=account.id,
                template_id=template.id,
                final_prompt="prompt",
                duration="10s",
                shots=[],
                user_id=owner_id,
                subtask_count=1,
            )

            self.assertFalse(task.is_reused_template)
            self.assertIsNone(task.template_reuse_reason)
            self.assertEqual(task.template_usage_index, 1)
            self.assertIsNotNone(task.template_used_at)

            histories = list((await session.execute(
                select(TemplateUsageHistory).where(TemplateUsageHistory.template_id == template.id)
            )).scalars().all())
            self.assertEqual(len(histories), 1)
            self.assertEqual(histories[0].usage_index, 1)
            self.assertIsNone(histories[0].reuse_reason)

    async def test_manual_used_template_defaults_to_inventory_fallback_reuse(self):
        from app.models.template_usage_history import TemplateUsageHistory
        from app.services.video_task_service import VideoTaskService

        async with self.Session() as session:
            owner_id, account, template = await self._seed_account_and_template(session, is_used=True)
            first = await VideoTaskService(session).create_task(
                account_id=account.id,
                template_id=template.id,
                final_prompt="first",
                duration="10s",
                shots=[],
                user_id=owner_id,
                subtask_count=1,
            )
            second = await VideoTaskService(session).create_task(
                account_id=account.id,
                template_id=template.id,
                final_prompt="second",
                duration="10s",
                shots=[],
                user_id=owner_id,
                subtask_count=1,
            )

            self.assertTrue(first.is_reused_template)
            self.assertEqual(first.template_reuse_reason, "inventory_fallback_reuse")
            self.assertEqual(first.template_usage_index, 1)
            self.assertTrue(second.is_reused_template)
            self.assertEqual(second.template_reuse_reason, "inventory_fallback_reuse")
            self.assertEqual(second.template_usage_index, 2)

            histories = list((await session.execute(
                select(TemplateUsageHistory)
                .where(TemplateUsageHistory.template_id == template.id)
                .order_by(TemplateUsageHistory.usage_index.asc())
            )).scalars().all())
            self.assertEqual([h.reuse_reason for h in histories], ["inventory_fallback_reuse", "inventory_fallback_reuse"])

    async def test_explicit_high_performance_reuse_reason_is_preserved(self):
        from app.services.video_task_service import VideoTaskService

        async with self.Session() as session:
            owner_id, account, template = await self._seed_account_and_template(session, is_used=True)
            task = await VideoTaskService(session).create_task(
                account_id=account.id,
                template_id=template.id,
                final_prompt="prompt",
                duration="10s",
                shots=[],
                user_id=owner_id,
                subtask_count=1,
                template_reuse_reason="high_performance_reuse",
                template_usage_source="scheduled",
                template_usage_source_step="high_performance_republish",
            )

            self.assertTrue(task.is_reused_template)
            self.assertEqual(task.template_reuse_reason, "high_performance_reuse")
            self.assertEqual(task.template_usage_source, "scheduled")
            self.assertEqual(task.template_usage_source_step, "high_performance_republish")

    async def test_queue_lists_high_performance_reuse_first(self):
        from app.api.v1.video_tasks import list_subtasks_by_account
        from app.models.video_task import VideoSubTask
        from app.services.video_task_service import VideoTaskService

        async with self.Session() as session:
            owner_id, account, template = await self._seed_account_and_template(session, is_used=True)
            normal = await VideoTaskService(session).create_task(
                account_id=account.id,
                template_id=template.id,
                final_prompt="normal",
                duration="10s",
                shots=[],
                user_id=owner_id,
                subtask_count=1,
            )
            hot = await VideoTaskService(session).create_task(
                account_id=account.id,
                template_id=template.id,
                final_prompt="hot",
                duration="10s",
                shots=[],
                user_id=owner_id,
                subtask_count=1,
                template_reuse_reason="high_performance_reuse",
                template_usage_source="scheduled",
                template_usage_source_step="high_performance_republish",
            )

            normal_sub = (await session.execute(select(VideoSubTask).where(VideoSubTask.task_id == normal.id))).scalar_one()
            hot_sub = (await session.execute(select(VideoSubTask).where(VideoSubTask.task_id == hot.id))).scalar_one()
            normal.status = hot.status = "queued"
            normal_sub.status = hot_sub.status = "queued"
            normal_sub.queue_order = 1
            hot_sub.queue_order = 99
            normal_sub.publish_meta = hot_sub.publish_meta = {"status": "done", "title": "ready"}
            await session.commit()

            page = await list_subtasks_by_account(
                account_id=account.id,
                status="queued",
                page=1,
                page_size=20,
                owner_id=owner_id,
                session=session,
            )

            self.assertEqual(page.items[0].task.id, hot.id)
            self.assertEqual(page.items[0].task.template_reuse_reason, "high_performance_reuse")
            self.assertEqual(page.items[1].task.template_reuse_reason, "inventory_fallback_reuse")


if __name__ == "__main__":
    unittest.main()
