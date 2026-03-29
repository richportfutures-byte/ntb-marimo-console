from __future__ import annotations

import unittest

from ntb_marimo_console.profile_operations import (
    build_profile_operations_snapshot,
    evaluate_profile_switch,
)


class ProfileOperationsTests(unittest.TestCase):
    def test_supported_profile_visibility_reports_demo_and_preserved_profiles(self) -> None:
        snapshot = build_profile_operations_snapshot(current_profile_id="preserved_es_phase1")

        supported = {profile.profile_id: profile for profile in snapshot.supported_profiles}
        self.assertEqual(
            tuple(supported),
            (
                "fixture_es_demo",
                "preserved_cl_phase1",
                "preserved_es_phase1",
                "preserved_zn_phase1",
            ),
        )
        self.assertEqual(supported["fixture_es_demo"].profile_kind, "Demo")
        self.assertEqual(supported["preserved_cl_phase1"].profile_kind, "Preserved")
        self.assertTrue(supported["preserved_es_phase1"].active)

    def test_blocked_candidate_visibility_reports_reason_labels(self) -> None:
        snapshot = build_profile_operations_snapshot()

        blocked = {
            candidate.contract: candidate
            for candidate in snapshot.candidate_profiles
            if candidate.status == "blocked"
        }
        self.assertEqual(
            set(blocked),
            {"NQ", "6E", "MGC"},
        )
        self.assertEqual(blocked["NQ"].reason_category, "blocked_unsupported_query_observable_contract")
        self.assertEqual(blocked["6E"].reason_label, "Missing numeric cross-asset source")

    def test_supported_profile_switch_evaluation_is_selectable(self) -> None:
        evaluation = evaluate_profile_switch(
            "preserved_zn_phase1",
            current_profile_id="preserved_es_phase1",
        )

        self.assertEqual(evaluation.status, "supported")
        self.assertIn("supported and selectable", evaluation.summary)

    def test_blocked_candidate_profile_switch_fails_closed(self) -> None:
        evaluation = evaluate_profile_switch(
            "preserved_nq_phase1",
            current_profile_id="preserved_es_phase1",
        )

        self.assertEqual(evaluation.status, "blocked")
        self.assertIn("not currently supported", evaluation.summary)
        self.assertIn("Unsupported query observable contract", evaluation.summary)

    def test_unknown_profile_switch_fails_closed(self) -> None:
        evaluation = evaluate_profile_switch(
            "unsupported_profile",
            current_profile_id="preserved_es_phase1",
        )

        self.assertEqual(evaluation.status, "unsupported")
        self.assertIn("supported profile registry", evaluation.summary)


if __name__ == "__main__":
    unittest.main()
