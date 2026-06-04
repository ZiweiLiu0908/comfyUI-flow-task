from __future__ import annotations

import unittest
from types import SimpleNamespace


class TemplateSupplementServiceRulesTest(unittest.TestCase):
    def _service(self):
        try:
            from app.services import template_supplement_service as svc
        except ImportError as exc:
            self.fail(f"template_supplement_service is missing: {exc}")
        return svc

    def test_compute_supplement_gap_tops_up_to_target(self):
        svc = self._service()

        self.assertEqual(svc.compute_supplement_gap(1, 10), 9)
        self.assertEqual(svc.compute_supplement_gap(2, 10), 8)
        self.assertEqual(svc.compute_supplement_gap(10, 10), 0)
        self.assertEqual(svc.compute_supplement_gap(12, 10), 0)

    def test_single_and_dual_accounts_route_to_auto_only(self):
        svc = self._service()

        self.assertEqual(svc.resolve_supplement_mode_for_account(SimpleNamespace(classification_type="single")), "auto")
        self.assertEqual(svc.resolve_supplement_mode_for_account(SimpleNamespace(classification_type="dual")), "auto")
        self.assertEqual(svc.resolve_supplement_mode_for_account(SimpleNamespace(classification_type="chaos")), "exclusive")
        self.assertEqual(svc.resolve_supplement_mode_for_account(SimpleNamespace(classification_type=None)), "exclusive")

    def test_auto_binding_requires_category_match(self):
        svc = self._service()
        account = SimpleNamespace(
            classification_type="single",
            classification_summary={"primary_key": "beauty"},
        )

        self.assertTrue(svc.should_bind_template_to_account(account, mode="auto", category_key="beauty_static_pose"))
        self.assertFalse(svc.should_bind_template_to_account(account, mode="auto", category_key="shopping_single_item"))
        self.assertFalse(svc.should_bind_template_to_account(account, mode="auto", category_key=None))

    def test_filters_accounts_for_reusable_template_bindings(self):
        svc = self._service()
        accounts = [
            SimpleNamespace(id="beauty-auto", classification_type="single", classification_summary={"primary_key": "beauty"}),
            SimpleNamespace(id="method-auto", classification_type="dual", classification_summary={"primary_key": "method", "secondary_key": "shopping"}),
            SimpleNamespace(id="persona", classification_type="chaos", classification_summary={}),
        ]

        auto_matches = svc.filter_accounts_for_template_binding(
            accounts,
            mode="auto",
            category_key="beauty_static_pose",
            filter_category_keys=[],
        )
        self.assertEqual([a.id for a in auto_matches], ["beauty-auto"])

        persona_matches = svc.filter_accounts_for_template_binding(
            accounts,
            mode="exclusive",
            category_key="beauty_static_pose",
            filter_category_keys=["beauty_static_pose"],
        )
        self.assertEqual([a.id for a in persona_matches], ["beauty-auto", "method-auto", "persona"])

        filtered_out = svc.filter_accounts_for_template_binding(
            accounts,
            mode="exclusive",
            category_key="shopping_single_item",
            filter_category_keys=["beauty_static_pose"],
        )
        self.assertEqual(filtered_out, [])

    def test_second_round_is_the_last_retry(self):
        svc = self._service()

        self.assertTrue(svc.should_start_another_round(completed_rounds=1, current_unused_count=5, target_unused_count=10, max_rounds=2))
        self.assertFalse(svc.should_start_another_round(completed_rounds=2, current_unused_count=5, target_unused_count=10, max_rounds=2))
        self.assertFalse(svc.should_start_another_round(completed_rounds=1, current_unused_count=10, target_unused_count=10, max_rounds=2))


if __name__ == "__main__":
    unittest.main()
