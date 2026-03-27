from __future__ import annotations

import unittest
from types import SimpleNamespace

from ntb_marimo_console.viewmodels.mappers import (
    premarket_brief_vm_from_brief,
    readiness_card_vm_from_context,
)
from ntb_marimo_console.viewmodels.models import PreMarketBriefVM, ReadinessCardVM


class ViewModelBoundaryEnforcementTests(unittest.TestCase):
    def test_engine_context_projects_to_readiness_vm_only(self) -> None:
        context = SimpleNamespace(
            contract="ES",
            event_risk_state="clear",
            vwap_posture_state="price_above_vwap",
            value_location_state="inside_value",
            level_proximity_state="clear_of_structure",
            hard_lockout_flags=[],
            awareness_flags=["awareness"],
            missing_inputs=[],
            extra_engine_only_field={"internal": True},
        )

        vm = readiness_card_vm_from_context(context)

        self.assertIsInstance(vm, ReadinessCardVM)
        self.assertFalse(hasattr(vm, "extra_engine_only_field"))

    def test_premarket_mapping_does_not_leak_full_engine_model(self) -> None:
        brief = {
            "contract": "ES",
            "session_date": "2026-03-25",
            "status": "READY",
            "structural_setups": [
                {
                    "summary": "Setup summary",
                    "warnings": ["warning"],
                    "fields_used": ["market.current_price"],
                    "engine_internal_payload": {"raw": "data"},
                }
            ],
        }

        vm = premarket_brief_vm_from_brief(brief)

        self.assertIsInstance(vm, PreMarketBriefVM)
        self.assertEqual(vm.setup_summaries, ("Setup summary",))
        self.assertFalse(hasattr(vm, "engine_internal_payload"))


if __name__ == "__main__":
    unittest.main()
