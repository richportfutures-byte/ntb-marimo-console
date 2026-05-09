from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
AUTHORITY_ROOT = REPO_ROOT / "docs" / "authority"
FINAL_TARGET = ("ES", "NQ", "CL", "6E", "MGC")


def _read_authority_doc(name: str) -> str:
    return (AUTHORITY_ROOT / name).read_text(encoding="utf-8")


class AuthorityContractUniverseTests(unittest.TestCase):
    def test_phase_and_support_matrix_bind_final_target_universe(self) -> None:
        phase = _read_authority_doc("03_current_phase_scope_contract.md")
        support = _read_authority_doc("04_support_matrix.md")

        for contract in FINAL_TARGET:
            self.assertIn(f"`{contract}`", phase)
            self.assertIn(f"`{contract}`", support)

        self.assertIn("final target support universe", phase)
        self.assertIn("Final Target Universe", support)
        self.assertNotIn("ES + ZN + CL", phase)
        self.assertNotIn("Supported preserved profiles for this phase are ES, ZN, and CL only", support)

    def test_zn_and_gc_are_excluded_from_final_target_support(self) -> None:
        combined = "\n".join(
            _read_authority_doc(name)
            for name in (
                "03_current_phase_scope_contract.md",
                "04_support_matrix.md",
                "05_acceptance_matrix.md",
                "06_deferred_work_register.md",
                "07_current_state_baseline.md",
                "08_contradiction_detection_report.md",
            )
        )

        self.assertIn("`ZN` is excluded", combined)
        self.assertIn("`GC` is excluded", combined)
        self.assertNotRegex(combined, r"`ZN`\s*\|\s*Required final target")
        self.assertNotRegex(combined, r"`GC`\s*\|\s*Required final target")
        self.assertNotRegex(combined, r"`GC` is (a )?synonym")

    def test_mgc_is_gold_contract_without_gc_aliasing(self) -> None:
        support = _read_authority_doc("04_support_matrix.md")
        acceptance = _read_authority_doc("05_acceptance_matrix.md")

        self.assertIn("`MGC` is the gold contract for this application", support)
        self.assertIn("`GC` is not used as a synonym for `MGC`", acceptance)
        self.assertNotIn("`GC` is the gold contract", support)
        self.assertNotIn("`GC` is the gold contract", acceptance)

    def test_onboarding_targets_are_not_engine_missing_contracts(self) -> None:
        support = _read_authority_doc("04_support_matrix.md")
        baseline = _read_authority_doc("07_current_state_baseline.md")

        for contract in ("NQ", "6E", "MGC"):
            self.assertRegex(support, rf"\| {re.escape(contract)} \| Required final target")
            self.assertIn(f"`{contract}`", support)

        self.assertIn("`6E` and `MGC` are required onboarding targets", support)
        self.assertIn("engine-supported but not final app-profile-supported yet", baseline)
        self.assertIn("must not be described as engine-missing contracts", support)
        self.assertNotIn("engine-missing", baseline)

    def test_current_runtime_profiles_remain_factual_not_final_target_authority(self) -> None:
        baseline = _read_authority_doc("07_current_state_baseline.md")

        for profile_id in (
            "fixture_es_demo",
            "preserved_es_phase1",
            "preserved_zn_phase1",
            "preserved_cl_phase1",
            "preserved_nq_phase1",
        ):
            self.assertIn(f"`{profile_id}`", baseline)

        self.assertIn("current-state behavior does not make `ZN` final target support", baseline)


if __name__ == "__main__":
    unittest.main()
