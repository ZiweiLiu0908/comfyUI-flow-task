from __future__ import annotations

import os
import json
import tempfile
import unittest
import uuid
from datetime import date
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")
os.environ.setdefault("AUTH_SECRET", "test-auth-secret")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_scheduled_generation_rule_tiers.sqlite3")


def tier_rules() -> dict:
    return {
        "beauty": {
            "enabled": True,
            "tiers": [
                {"label": "小爆", "min_views": 5000, "max_views": 10000, "repeat_count": 3},
                {"label": "中爆", "min_views": 10000, "max_views": 100000, "repeat_count": 5},
                {"label": "大爆", "min_views": 100000, "max_views": 500000, "repeat_count": 10},
                {"label": "超级爆", "min_views": 500000, "max_views": None, "repeat_count": 15},
            ],
            "reuse_note": "保持原有 prompt，换音乐、衣服",
        }
    }


class ScheduledGenerationTierRuleTest(unittest.TestCase):
    def test_tier_boundaries_match_expected_bucket(self):
        from app.services.scheduled_generation_service import match_category_rule

        self.assertIsNone(match_category_rule("beauty", 4999, tier_rules()))
        self.assertEqual(match_category_rule("beauty", 5000, tier_rules()).rule_label, "小爆")
        self.assertEqual(match_category_rule("beauty", 10000, tier_rules()).rule_label, "中爆")
        self.assertEqual(match_category_rule("beauty", 100000, tier_rules()).rule_label, "大爆")
        self.assertEqual(match_category_rule("beauty", 500000, tier_rules()).rule_label, "超级爆")

    def test_legacy_min_views_rule_still_matches(self):
        from app.services.scheduled_generation_service import match_category_rule

        rules = {"beauty": {"enabled": True, "min_views": 5000, "repeat_count": 3}}
        self.assertIsNone(match_category_rule("beauty", 5000, rules))
        match = match_category_rule("beauty", 5001, rules)
        self.assertEqual(match.min_views, 5000)
        self.assertEqual(match.repeat_count, 3)

    def test_overlapping_tiers_use_highest_min_views(self):
        from app.services.scheduled_generation_service import match_category_rule

        rules = {
            "beauty": {
                "enabled": True,
                "tiers": [
                    {"label": "low", "min_views": 5000, "max_views": 20000, "repeat_count": 3},
                    {"label": "higher", "min_views": 10000, "max_views": 30000, "repeat_count": 7},
                ],
            }
        }

        match = match_category_rule("beauty", 12000, rules)
        self.assertEqual(match.rule_label, "higher")
        self.assertEqual(match.repeat_count, 7)


class ScheduledGenerationTierSQLiteE2ETest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmpdir.name) / "scheduled_generation_tiers.sqlite3"
        self.engine = create_async_engine(f"sqlite+aiosqlite:///{db_path}", future=True)
        self.Session = async_sessionmaker(bind=self.engine, expire_on_commit=False)

        from app.db.base import Base
        import app.models  # noqa: F401

        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self):
        await self.engine.dispose()
        self.tmpdir.cleanup()

    async def test_frontend_payload_persists_to_db_and_matches_backend_tier(self):
        from app.models.pipeline_setting import PipelineSetting
        from app.models.scheduled_generation_run import ScheduledGenerationRun, ScheduledGenerationRunItem
        from app.services.scheduled_generation_service import match_category_rule

        frontend_payload = tier_rules()
        owner_id = uuid.uuid4()

        async with self.Session() as session:
            row = PipelineSetting(
                owner_id=owner_id,
                scheduled_generation_enabled=True,
                scheduled_generation_category_rules=frontend_payload,
            )
            session.add(row)
            await session.commit()

            raw = await session.scalar(text("select scheduled_generation_category_rules from pipeline_settings limit 1"))
            raw_payload = json.loads(raw) if isinstance(raw, str) else raw
            self.assertEqual(raw_payload["beauty"]["tiers"][1]["label"], "中爆")

            saved = await session.scalar(select(PipelineSetting).where(PipelineSetting.owner_id == owner_id))
            self.assertEqual(saved.scheduled_generation_category_rules["beauty"]["tiers"][1]["label"], "中爆")
            match = match_category_rule("beauty", 12000, saved.scheduled_generation_category_rules)
            self.assertEqual(match.rule_label, "中爆")
            self.assertEqual(match.min_views, 10000)
            self.assertEqual(match.max_views, 100000)
            self.assertEqual(match.repeat_count, 5)

            run = ScheduledGenerationRun(
                owner_id=owner_id,
                trigger_key="2026-06-05 10:00",
                target_date=date(2026, 6, 3),
                config_snapshot={"category_rules": frontend_payload},
            )
            session.add(run)
            await session.flush()
            session.add(ScheduledGenerationRunItem(
                run_id=run.id,
                owner_id=owner_id,
                source_step="high_performance_republish",
                major_category="beauty",
                total_views=12000,
                threshold_views=match.min_views,
                matched_rule_label=match.rule_label,
                threshold_min_views=match.min_views,
                threshold_max_views=match.max_views,
                matched_rule_snapshot=match.rule_snapshot,
                repeat_count=match.repeat_count,
            ))
            await session.commit()

            item = await session.scalar(select(ScheduledGenerationRunItem))
            self.assertEqual(item.matched_rule_label, "中爆")
            self.assertEqual(item.threshold_min_views, 10000)
            self.assertEqual(item.threshold_max_views, 100000)
            self.assertEqual(item.matched_rule_snapshot["repeat_count"], 5)


if __name__ == "__main__":
    unittest.main()
