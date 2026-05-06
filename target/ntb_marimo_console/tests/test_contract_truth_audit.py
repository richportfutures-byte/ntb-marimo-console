from __future__ import annotations

import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
AUDIT_PATH = REPO_ROOT / "docs" / "authority" / "contract_truth_audit.md"


class ContractTruthAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.audit = AUDIT_PATH.read_text(encoding="utf-8")

    def test_audit_document_exists(self) -> None:
        self.assertTrue(AUDIT_PATH.exists())

    def test_final_targets_are_listed(self) -> None:
        for contract in ("ES", "NQ", "CL", "6E", "MGC"):
            self.assertIn(f"| {contract} | Final target", self.audit)

    def test_zn_and_gc_are_excluded(self) -> None:
        self.assertIn("| ZN | Excluded/historical |", self.audit)
        self.assertIn("| GC | Excluded |", self.audit)
        self.assertIn("`ZN` and `GC` are excluded from final target support", self.audit)

    def test_gc_has_no_engine_prompt_runtime_or_live_support(self) -> None:
        self.assertIn(
            "| GC | Excluded | No | No | No | No | Keep excluded; no engine schema literal, prompt, runtime profile, or live gating |",
            self.audit,
        )
        self.assertIn(
            "`GC` is not present as an engine schema literal, Stage A/B prompt, system-spec target, runtime profile, or current app/live-gating target.",
            self.audit,
        )

    def test_mgc_is_final_target_and_not_gc(self) -> None:
        self.assertIn("| MGC | Final target; not `GC` | Yes | Yes | No | No |", self.audit)
        self.assertIn("`GC` must not be added or conflated with `MGC`", self.audit)

    def test_onboarding_targets_require_onboarding_not_engine_creation(self) -> None:
        self.assertIn("| NQ | Final target | Yes | Yes | No | No | Onboard profile and ES-relative live gating |", self.audit)
        self.assertIn("| 6E | Final target | Yes | Yes | No | No | Onboard profile and DXY/session gating |", self.audit)
        self.assertIn("| MGC | Final target; not `GC` | Yes | Yes | No | No | Onboard profile and DXY/yield gating |", self.audit)
        self.assertIn("They require onboarding rather than engine creation", self.audit)

    def test_es_and_cl_have_runtime_profiles_and_need_live_upgrades(self) -> None:
        self.assertIn("| ES | Final target | Yes | Yes | Yes: `fixture_es_demo`, `preserved_es_phase1` | Partial | Live upgrade |", self.audit)
        self.assertIn("| CL | Final target | Yes | Yes | Yes: `preserved_cl_phase1` | Partial | Live upgrade |", self.audit)

    def test_zn_exists_today_but_is_historical_excluded(self) -> None:
        self.assertIn(
            "| ZN | Excluded/historical | Yes | Yes | Yes today: `preserved_zn_phase1` | Partial/historical |",
            self.audit,
        )
        self.assertIn("`ZN` exists today", self.audit)
        self.assertIn("historical/excluded", self.audit)


if __name__ == "__main__":
    unittest.main()
