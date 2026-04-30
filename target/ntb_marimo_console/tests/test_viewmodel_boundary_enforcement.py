from __future__ import annotations

import unittest
from datetime import datetime, timezone
from types import SimpleNamespace

from ntb_marimo_console.market_data.futures_quote_service import (
    FixtureFuturesQuoteProvider,
    FuturesQuote,
    FuturesQuoteService,
)
from ntb_marimo_console.viewmodels.mappers import (
    live_observable_vm_from_snapshot,
    premarket_brief_vm_from_brief,
    readiness_card_vm_from_context,
)
from ntb_marimo_console.viewmodels.models import LiveObservableVM, PreMarketBriefVM, ReadinessCardVM


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

    def test_live_observable_market_data_projection_is_safe_and_read_only(self) -> None:
        service = FuturesQuoteService(
            FixtureFuturesQuoteProvider(
                FuturesQuote(
                    symbol="ES",
                    bid_price=7175,
                    ask_price=7175.5,
                    last_price=7175.25,
                    bid_size=19,
                    ask_size=14,
                    received_at="2026-04-30T11:59:58+00:00",
                )
            ),
            clock=lambda: datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc),
        )

        vm = live_observable_vm_from_snapshot(
            {
                "contract": "ES",
                "timestamp_et": "2026-03-25T09:35:00-04:00",
                "market": {"current_price": 5600.0},
            },
            market_data_service=service,
            market_data_symbol="ES",
        )

        self.assertIsInstance(vm, LiveObservableVM)
        self.assertEqual(vm.market_data.status, "Fixture quote")
        self.assertEqual(vm.market_data.bid, "7175")
        self.assertEqual(vm.market_data.ask, "7175.5")
        self.assertEqual(vm.market_data.last, "7175.25")
        self.assertFalse(hasattr(vm.market_data, "provider_name"))
        self.assertFalse(hasattr(vm.market_data, "failure_reason"))
        self.assertFalse(hasattr(vm.market_data, "quote_age_seconds"))


if __name__ == "__main__":
    unittest.main()
