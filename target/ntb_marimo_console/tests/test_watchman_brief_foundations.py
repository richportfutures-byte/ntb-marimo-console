from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from ntb_marimo_console.adapters.trigger_specs import trigger_specs_from_brief
from ntb_marimo_console.contract_universe import final_target_contracts
from ntb_marimo_console.watchman_gate import validate_watchman_brief


FIXTURES_ROOT = Path("fixtures/golden/phase1")
BRIEF_PATHS = {
    "ES": FIXTURES_ROOT / "premarket" / "ES" / "2026-03-25" / "premarket_brief.ready.json",
    "NQ": FIXTURES_ROOT / "premarket" / "NQ" / "2026-01-14" / "premarket_brief.ready.json",
    "CL": FIXTURES_ROOT / "premarket" / "CL" / "2026-01-14" / "premarket_brief.ready.json",
    "6E": FIXTURES_ROOT / "premarket" / "6E" / "2026-01-14" / "premarket_brief.ready.json",
    "MGC": FIXTURES_ROOT / "premarket" / "MGC" / "2026-01-14" / "premarket_brief.ready.json",
}


class WatchmanBriefFoundationTests(unittest.TestCase):
    def test_final_target_briefs_are_schema_valid_live_thesis_foundations(self) -> None:
        self.assertEqual(tuple(BRIEF_PATHS), final_target_contracts())

        for contract, path in BRIEF_PATHS.items():
            with self.subTest(contract=contract):
                brief = _load_json(path)
                result = validate_watchman_brief(brief)

                self.assertEqual(result.status, "READY")
                self.assertEqual(brief["version"], "live_thesis_brief_v1")
                self.assertEqual(brief["contract"], contract)
                self.assertTrue(brief["structural_setups"])
                self.assertFalse(_brief_enables_authorization(brief))

    def test_every_setup_and_trigger_declares_required_fields_and_invalidators(self) -> None:
        for contract, path in BRIEF_PATHS.items():
            with self.subTest(contract=contract):
                brief = _load_json(path)
                for setup in brief["structural_setups"]:
                    self.assertTrue(setup["id"])
                    self.assertTrue(setup["required_live_fields"])
                    for trigger in setup["query_triggers"]:
                        self.assertTrue(trigger["id"])
                        self.assertTrue(trigger["description"])
                        self.assertEqual(trigger["required_live_fields"], trigger["fields_used"])
                        self.assertTrue(trigger["observable_conditions"])
                        self.assertTrue(
                            trigger.get("invalidators") or trigger.get("invalidator_policy"),
                            "Trigger must declare invalidators or an explicit policy.",
                        )

    def test_missing_required_source_context_fails_closed_even_when_raw_status_is_ready(self) -> None:
        brief = _load_json(BRIEF_PATHS["MGC"])
        broken = copy.deepcopy(brief)
        broken["status"] = "READY"
        broken["source_context"]["missing_required_context"] = ["cross_asset.dxy"]

        result = validate_watchman_brief(broken)

        self.assertEqual(result.status, "NEEDS_REVIEW")
        self.assertIn("required_source_context_available", result.failing_validators)
        self.assertFalse(result.pipeline_gate_open)

    def test_raw_brief_status_alone_does_not_authorize_validator_gate(self) -> None:
        brief = _load_json(BRIEF_PATHS["ES"])
        broken = copy.deepcopy(brief)
        broken["status"] = "READY"
        broken["structural_setups"][0]["query_triggers"][0].pop("required_live_fields")

        result = validate_watchman_brief(broken)

        self.assertEqual(result.status, "FAILED")
        self.assertIn("trigger_required_live_fields_present", result.failing_validators)
        self.assertFalse(result.pipeline_gate_open)

    def test_trigger_specs_use_required_live_fields_for_later_evaluation(self) -> None:
        brief = _load_json(BRIEF_PATHS["NQ"])

        specs = trigger_specs_from_brief(brief)

        self.assertEqual(len(specs), 1)
        self.assertEqual(specs[0].id, "nq_trigger_es_relative_breakout")
        self.assertIn("cross_asset.relative_strength_vs_es", specs[0].required_live_field_paths)

    def test_contract_specific_live_thesis_requirements_are_present(self) -> None:
        es = _encoded(BRIEF_PATHS["ES"])
        nq = _encoded(BRIEF_PATHS["NQ"])
        cl = _encoded(BRIEF_PATHS["CL"])
        sixe = _encoded(BRIEF_PATHS["6E"])
        mgc = _encoded(BRIEF_PATHS["MGC"])

        self.assertIn("breadth", es)
        self.assertIn("relative_strength_vs_es", nq)
        self.assertIn("absolute nq price action is not sufficient", nq)
        self.assertIn("eia_lockout_active", cl)
        self.assertIn("headline", cl)
        self.assertIn("cross_asset.dxy", sixe)
        self.assertIn("textual dxy", sixe)
        self.assertIn("micro gold", mgc)
        self.assertIn("cash_10y_yield", mgc)
        self.assertIn("fear_catalyst_state", mgc)
        self.assertIn("gc is excluded", mgc)

    def test_excluded_contract_briefs_fail_closed_if_presented_to_validator(self) -> None:
        for contract in ("ZN", "GC"):
            with self.subTest(contract=contract):
                result = validate_watchman_brief(
                    {
                        "contract": contract,
                        "session_date": "2026-01-14",
                        "status": "READY",
                        "version": "live_thesis_brief_v1",
                        "structural_setups": [],
                    }
                )

                self.assertEqual(result.status, "FAILED")
                self.assertIn("brief_contract_supported", result.failing_validators)


def _load_json(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError(f"Expected object JSON at {path}")
    return payload


def _encoded(path: Path) -> str:
    return json.dumps(_load_json(path), sort_keys=True).lower()


def _brief_enables_authorization(brief: dict[str, object]) -> bool:
    encoded = json.dumps(brief, sort_keys=True).lower()
    return "pipeline_query_authorized" in encoded or "trade_authorized" in encoded


if __name__ == "__main__":
    unittest.main()
