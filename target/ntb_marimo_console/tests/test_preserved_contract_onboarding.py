from __future__ import annotations

import copy
import unittest
from dataclasses import replace

from ntb_marimo_console.preserved_contract_onboarding import (
    BLOCKED_MISSING_NUMERIC_CROSS_ASSET_SOURCE,
    BLOCKED_UNSUPPORTED_QUERY_OBSERVABLE_CONTRACT,
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
            {"preserved_es_phase1", "preserved_zn_phase1", "preserved_cl_phase1"},
        )

    def test_blocked_candidates_are_reported_with_reason_categories(self) -> None:
        snapshot = build_contract_eligibility_snapshot()
        blocked = {result.contract: result.reason_category for result in snapshot.blocked}

        self.assertEqual(blocked["NQ"], BLOCKED_UNSUPPORTED_QUERY_OBSERVABLE_CONTRACT)
        self.assertEqual(blocked["6E"], BLOCKED_MISSING_NUMERIC_CROSS_ASSET_SOURCE)
        self.assertEqual(blocked["MGC"], BLOCKED_MISSING_NUMERIC_CROSS_ASSET_SOURCE)

        report = render_contract_eligibility_report(snapshot)
        self.assertIn("Supported Now:", report)
        self.assertIn("Blocked:", report)
        self.assertIn("NQ -> preserved_nq_phase1", report)

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

    def test_select_single_new_contract_picks_cl_when_only_es_and_zn_are_supported(self) -> None:
        selected = select_single_new_preserved_contract(supported_contracts={"ES", "ZN"})

        self.assertIsNotNone(selected)
        self.assertEqual(selected.contract, "CL")
        self.assertEqual(selected.profile_id, "preserved_cl_phase1")

    def test_select_single_new_contract_fails_closed_when_only_blocked_candidates_remain(self) -> None:
        selected = select_single_new_preserved_contract(supported_contracts={"ES", "ZN", "CL"})

        self.assertIsNone(selected)


if __name__ == "__main__":
    unittest.main()
