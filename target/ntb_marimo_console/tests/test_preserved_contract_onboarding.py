from __future__ import annotations

import copy
import unittest
from dataclasses import replace

from ntb_marimo_console.preserved_contract_onboarding import (
    build_candidate_profile_template,
    build_contract_eligibility_snapshot,
    render_contract_eligibility_report,
    render_profile_template_checklist,
    select_single_new_preserved_contract,
    validate_profile_template,
)


class PreservedContractOnboardingTests(unittest.TestCase):
    def test_supported_profiles_appear_in_audit_snapshot(self) -> None:
        snapshot = build_contract_eligibility_snapshot()
        supported_ids = {result.profile_id for result in snapshot.supported_now}

        self.assertEqual(
            supported_ids,
            {
                "preserved_6e_phase1",
                "preserved_es_phase1",
                "preserved_mgc_phase1",
                "preserved_nq_phase1",
                "preserved_zn_phase1",
                "preserved_cl_phase1",
            },
        )

    def test_no_blocked_candidates_remain_after_mgc_profile_foundation(self) -> None:
        snapshot = build_contract_eligibility_snapshot()

        self.assertEqual(snapshot.blocked, ())
        self.assertEqual(snapshot.viable_to_onboard_now, ())

        report = render_contract_eligibility_report(snapshot)
        self.assertIn("Supported Now:", report)
        self.assertIn("Blocked:\n- none", report)
        self.assertIn("Final Target Contracts: ES, NQ, CL, 6E, MGC", report)
        self.assertIn("Excluded Final Target Contracts: ZN, GC", report)
        self.assertIn("ZN -> preserved_zn_phase1: legacy_historical", report)
        self.assertIn("NQ -> preserved_nq_phase1: final_target | supported_profile", report)
        self.assertIn("6E -> preserved_6e_phase1: final_target | supported_profile", report)
        self.assertIn("MGC -> preserved_mgc_phase1: final_target | supported_profile", report)

    def test_profile_template_checklist_is_readable_and_complete(self) -> None:
        template = validate_profile_template(build_candidate_profile_template("CL"))
        checklist = render_profile_template_checklist(template)

        self.assertIn("Profile Template: preserved_cl_phase1", checklist)
        self.assertIn("pre-market packet", checklist)
        self.assertIn("macro_context.eia_lockout_active", checklist)

    def test_invalid_profile_template_fails_closed(self) -> None:
        template = build_candidate_profile_template("CL")
        broken_brief = copy.deepcopy(template.premarket_brief)
        broken_brief["structural_setups"][0]["query_triggers"][0]["fields_used"] = [
            "market.current_price",
            "market.cumulative_delta",
        ]

        with self.assertRaisesRegex(RuntimeError, "trigger fields"):
            validate_profile_template(replace(template, premarket_brief=broken_brief))

    def test_select_single_new_contract_picks_cl_when_only_cl_is_viable(self) -> None:
        selected = select_single_new_preserved_contract(supported_contracts={"ES", "ZN", "NQ", "6E", "MGC"})

        self.assertIsNotNone(selected)
        self.assertEqual(selected.contract, "CL")
        self.assertEqual(selected.profile_id, "preserved_cl_phase1")

    def test_select_single_new_contract_fails_closed_when_only_blocked_candidates_remain(self) -> None:
        selected = select_single_new_preserved_contract(supported_contracts={"ES", "ZN", "CL", "NQ", "6E", "MGC"})

        self.assertIsNone(selected)

    def test_select_single_new_contract_can_pick_mgc_before_r10_onboarding(self) -> None:
        selected = select_single_new_preserved_contract(supported_contracts={"ES", "ZN", "CL", "NQ", "6E"})

        self.assertIsNotNone(selected)
        self.assertEqual(selected.contract, "MGC")
        self.assertEqual(selected.profile_id, "preserved_mgc_phase1")


if __name__ == "__main__":
    unittest.main()
