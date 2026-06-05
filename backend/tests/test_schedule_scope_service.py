from __future__ import annotations

import unittest


class ScheduleScopeServiceTest(unittest.TestCase):
    def _service(self):
        try:
            from app.services import account_scope_service as svc
        except ImportError as exc:
            self.fail(f"account_scope_service is missing: {exc}")
        return svc

    def test_selected_scope_uses_selected_ids_only(self):
        svc = self._service()

        scope = svc.normalize_schedule_scope(
            scope_mode="selected",
            account_ids=["7e5c7234-0e8c-4cb1-a3d3-0f1e87f359a1"],
            filters={"search": "Lauren", "gender": "female"},
        )

        self.assertEqual(scope["mode"], "selected")
        self.assertEqual(scope["account_ids"], ["7e5c7234-0e8c-4cb1-a3d3-0f1e87f359a1"])
        self.assertEqual(scope["filters"], {})

    def test_filtered_scope_uses_filter_snapshot(self):
        svc = self._service()

        scope = svc.normalize_schedule_scope(
            scope_mode="filtered",
            account_ids=["7e5c7234-0e8c-4cb1-a3d3-0f1e87f359a1"],
            filters={"search": "Lauren", "category_keys": ["beauty"]},
        )

        self.assertEqual(scope["mode"], "filtered")
        self.assertEqual(scope["account_ids"], [])
        self.assertEqual(scope["filters"], {"search": "Lauren", "category_keys": ["beauty"]})

    def test_legacy_scope_defaults_to_filtered_all_accounts(self):
        svc = self._service()

        scope = svc.normalize_schedule_scope(scope_mode=None, account_ids=None, filters=None)

        self.assertEqual(scope["mode"], "filtered")
        self.assertEqual(scope["account_ids"], [])
        self.assertEqual(scope["filters"], {})


if __name__ == "__main__":
    unittest.main()
