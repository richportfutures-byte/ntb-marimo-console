from __future__ import annotations

import unittest

from ntb_marimo_console.ui.app_shell import AppShellPayload, build_app_shell
from ntb_marimo_console.viewmodels.models import (
    LiveObservableVM,
    PipelineTraceVM,
    PreMarketBriefVM,
    ReadinessCardVM,
    RunHistoryRowVM,
    SessionHeaderVM,
    TriggerStatusVM,
)


class AppShellStructureTests(unittest.TestCase):
    def test_app_shell_contains_frozen_surfaces(self) -> None:
        payload = AppShellPayload(
            session_header=SessionHeaderVM(contract="ES", session_date="2026-03-25"),
            premarket_brief=PreMarketBriefVM(
                contract="ES",
                session_date="2026-03-25",
                status="READY",
                setup_summaries=("setup",),
                warnings=("warn",),
            ),
            live_observable=LiveObservableVM(
                contract="ES",
                timestamp_et="2026-03-25T09:35:00-04:00",
                snapshot={"market": {"current_price": 5600.0}},
            ),
            readiness_cards=(
                ReadinessCardVM(
                    contract="ES",
                    status="ready",
                    event_risk="clear",
                    vwap_posture="price_above_vwap",
                    value_location="inside_value",
                    level_proximity="clear_of_structure",
                    hard_lockouts=(),
                    awareness_items=(),
                    missing_context=(),
                ),
            ),
            trigger_rows=(
                TriggerStatusVM(
                    trigger_id="t",
                    is_valid=True,
                    is_true=False,
                    missing_fields=(),
                    invalid_reasons=(),
                ),
            ),
            pipeline_trace=PipelineTraceVM(
                contract="ES",
                termination_stage="contract_market_read",
                final_decision="NO_TRADE",
                stage_a_status="READY",
                stage_b_outcome="NO_TRADE",
                stage_c_outcome=None,
                stage_d_decision=None,
            ),
            run_history_rows=(
                RunHistoryRowVM(
                    run_id="r1",
                    logged_at="2026-03-25T09:35:00-04:00",
                    contract="ES",
                    run_type="pipeline",
                    final_decision="NO_TRADE",
                    notes="n",
                ),
            ),
        )

        app = build_app_shell(payload)

        self.assertIn("surfaces", app)
        names = set(app["surfaces"].keys())
        self.assertEqual(
            names,
            {
                "session_header",
                "pre_market_brief",
                "readiness_matrix",
                "trigger_table",
                "live_observables",
                "query_action",
                "decision_review",
                "audit_replay",
                "run_history",
            },
        )
        market_data = app["surfaces"]["live_observables"]["market_data"]
        self.assertEqual(market_data["status"], "Market data unavailable")
        self.assertEqual(market_data["bid"], "N/A")
        self.assertEqual(market_data["ask"], "N/A")
        self.assertEqual(market_data["last"], "N/A")
        self.assertEqual(market_data["quote_time"], "unknown")


if __name__ == "__main__":
    unittest.main()
