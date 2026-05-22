from __future__ import annotations

import os
import tempfile
import unittest
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models  # noqa: F401
from app.db.base import Base
from app.models.account import Account
from app.models.account_channel_reservation import AccountChannelReservation
from app.models.pipeline_setting import PipelineSetting
from app.models.video_publication import VideoPublication
from app.models.video_task import VideoSubTask, VideoTask
from app.services.account_operation_guard import filter_operable_account_ids
from app.services.account_service import list_accounts, recompute_account_platform_binding_status
from app.services.account_shadowban_scheduler import run_shadowban_evaluation
from app.services.video_task_service import VideoTaskService


class ListAccountsPlatformBindingStatusTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        fd, self.db_path = tempfile.mkstemp(suffix=".sqlite3")
        os.close(fd)
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{self.db_path}")
        self.session_factory = async_sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self) -> None:
        await self.engine.dispose()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    async def test_disabled_filter_requires_all_bound_platforms_to_be_disabled(self) -> None:
        owner_id = uuid.uuid4()
        disabled_account = Account(account_name="all-disabled", owner_id=owner_id)
        mixed_account = Account(account_name="mixed-active-disabled", owner_id=owner_id)
        active_bound_account = Account(account_name="active-only", owner_id=owner_id)
        confirmed_account = Account(account_name="confirmed-tiktok", owner_id=owner_id)
        unbound_account = Account(account_name="unbound", owner_id=owner_id)

        async with self.session_factory() as session:
            session.add_all([
                disabled_account,
                mixed_account,
                active_bound_account,
                confirmed_account,
                unbound_account,
            ])
            await session.flush()
            session.add_all([
                AccountChannelReservation(
                    account_id=disabled_account.id,
                    platform="youtube",
                    status="bound",
                    channel_status="disabled",
                ),
                AccountChannelReservation(
                    account_id=disabled_account.id,
                    platform="tiktok",
                    status="bound",
                    channel_status="disabled",
                ),
                AccountChannelReservation(
                    account_id=mixed_account.id,
                    platform="youtube",
                    status="bound",
                    channel_status="disabled",
                ),
                AccountChannelReservation(
                    account_id=mixed_account.id,
                    platform="instagram",
                    status="bound",
                    channel_status="active",
                ),
                AccountChannelReservation(
                    account_id=active_bound_account.id,
                    platform="youtube",
                    status="bound",
                    channel_status="active",
                ),
                AccountChannelReservation(
                    account_id=confirmed_account.id,
                    platform="tiktok",
                    status="confirmed",
                    channel_status="active",
                ),
            ])
            for account in [
                disabled_account,
                mixed_account,
                active_bound_account,
                confirmed_account,
                unbound_account,
            ]:
                await recompute_account_platform_binding_status(session, account.id)
            await session.commit()

        async with self.session_factory() as session:
            disabled_rows, disabled_total = await list_accounts(
                session,
                page=1,
                page_size=20,
                owner_id=owner_id,
                platform_binding_status="disabled",
            )
            bound_rows, bound_total = await list_accounts(
                session,
                page=1,
                page_size=20,
                owner_id=owner_id,
                platform_binding_status="bound",
            )

        self.assertEqual(disabled_total, 1)
        self.assertEqual([row.account_name for row in disabled_rows], ["all-disabled"])
        self.assertEqual(bound_total, 2)
        self.assertCountEqual(
            [row.account_name for row in bound_rows],
            ["mixed-active-disabled", "active-only"],
        )

    async def test_recompute_does_not_change_shadowban_status(self) -> None:
        owner_id = uuid.uuid4()
        account = Account(
            account_name="already-shadowban",
            owner_id=owner_id,
            platform_binding_status="shadowban",
        )

        async with self.session_factory() as session:
            session.add(account)
            await session.flush()
            session.add(
                AccountChannelReservation(
                    account_id=account.id,
                    platform="youtube",
                    status="bound",
                    channel_status="active",
                )
            )
            await recompute_account_platform_binding_status(session, account.id)
            await session.commit()

        async with self.session_factory() as session:
            saved = await session.get(Account, account.id)
        self.assertEqual(saved.platform_binding_status, "shadowban")

    async def test_shadowban_evaluation_uses_latest_n_publications_with_view_data(self) -> None:
        owner_id = uuid.uuid4()
        shadowban_account = Account(account_name="shadowban-target", owner_id=owner_id)
        healthy_account = Account(account_name="healthy", owner_id=owner_id)
        insufficient_account = Account(account_name="insufficient-data", owner_id=owner_id)
        already_shadowban = Account(
            account_name="already-shadowban",
            owner_id=owner_id,
            platform_binding_status="shadowban",
        )

        async with self.session_factory() as session:
            session.add(PipelineSetting(
                owner_id=owner_id,
                shadowban_video_sample_count=3,
                shadowban_view_threshold=100,
            ))
            session.add_all([shadowban_account, healthy_account, insufficient_account, already_shadowban])
            await session.flush()

            now = datetime.now(timezone.utc)

            async def add_publication(account: Account, idx: int, views: int | None) -> None:
                task = VideoTask(
                    owner_id=owner_id,
                    account_id=account.id,
                    target_date=date.today(),
                    prompt="test",
                    duration="10",
                )
                sub = VideoSubTask(task=task, sub_index=idx, status="published")
                metrics_snapshot = None
                if views is not None:
                    metrics_snapshot = {
                        "channels": [{
                            "platform": "youtube",
                            "stats": {"views": views},
                        }]
                    }
                pub = VideoPublication(
                    sub_task=sub,
                    status="completed",
                    completed_at=now - timedelta(minutes=idx),
                    metrics_snapshot=metrics_snapshot,
                )
                session.add_all([task, sub, pub])

            for i, views in enumerate([None, 100, 80, 0, 1000], start=1):
                await add_publication(shadowban_account, i, views)
            for i, views in enumerate([100, 80, 101], start=10):
                await add_publication(healthy_account, i, views)
            for i, views in enumerate([None, 50, 80], start=20):
                await add_publication(insufficient_account, i, views)
            for i, views in enumerate([999, 999, 999], start=30):
                await add_publication(already_shadowban, i, views)

            await session.commit()

        async with self.session_factory() as session:
            result = await run_shadowban_evaluation(session)
            await session.commit()

        async with self.session_factory() as session:
            rows = (
                await session.execute(
                    select(Account.account_name, Account.platform_binding_status)
                    .where(Account.owner_id == owner_id)
                )
            ).all()

        self.assertEqual(result["updated"], 1)
        self.assertEqual(dict(rows), {
            "shadowban-target": "shadowban",
            "healthy": "unbound",
            "insufficient-data": "unbound",
            "already-shadowban": "shadowban",
        })

    async def test_operable_account_filter_skips_disabled_and_shadowban_accounts(self) -> None:
        owner_id = uuid.uuid4()
        allowed = Account(account_name="allowed", owner_id=owner_id, platform_binding_status="bound")
        disabled = Account(account_name="disabled", owner_id=owner_id, platform_binding_status="disabled")
        shadowban = Account(account_name="shadowban", owner_id=owner_id, platform_binding_status="shadowban")
        missing_id = uuid.uuid4()

        async with self.session_factory() as session:
            session.add_all([allowed, disabled, shadowban])
            await session.commit()

        async with self.session_factory() as session:
            operable_ids, skip_reasons = await filter_operable_account_ids(
                session,
                [disabled.id, allowed.id, shadowban.id, missing_id],
                owner_id=owner_id,
            )

        self.assertEqual(operable_ids, [allowed.id, missing_id])
        self.assertEqual(skip_reasons, {"disabled": 1, "shadowban": 1})

    async def test_video_task_creation_rejects_disabled_and_shadowban_accounts(self) -> None:
        owner_id = uuid.uuid4()
        disabled = Account(account_name="disabled", owner_id=owner_id, platform_binding_status="disabled")
        shadowban = Account(account_name="shadowban", owner_id=owner_id, platform_binding_status="shadowban")

        async with self.session_factory() as session:
            session.add_all([disabled, shadowban])
            await session.commit()

        async with self.session_factory() as session:
            service = VideoTaskService(session)
            for account in [disabled, shadowban]:
                with self.assertRaisesRegex(Exception, "账号状态不可操作"):
                    await service.create_task(
                        account_id=account.id,
                        template_id=uuid.uuid4(),
                        final_prompt="test",
                        duration="10s",
                        shots=[],
                        user_id=owner_id,
                    )

            total = await session.scalar(select(func.count(VideoTask.id)))
        self.assertEqual(total, 0)


if __name__ == "__main__":
    unittest.main()
