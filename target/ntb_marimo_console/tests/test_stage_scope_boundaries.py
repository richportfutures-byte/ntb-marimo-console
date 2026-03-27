from __future__ import annotations

import unittest

from ntb_marimo_console.adapters.contracts import PipelineBackend
from ntb_marimo_console.ui.surfaces.audit_replay import render_audit_replay_panel
from ntb_marimo_console.ui.surfaces.decision_review import render_decision_review_panel
from ntb_marimo_console.viewmodels.models import PipelineTraceVM


class StageScopeBoundaryTests(unittest.TestCase):
    def test_pipeline_backend_exposes_frozen_methods_only(self) -> None:
        method_names = {
            name
            for name in dir(PipelineBackend)
            if not name.startswith("_") and callable(getattr(PipelineBackend, name, None))
        }
        self.assertIn("sweep_watchman", method_names)
        self.assertIn("run_pipeline", method_names)
        self.assertIn("summarize_pipeline_result", method_names)
        self.assertNotIn("run_pipeline_and_log", method_names)
        self.assertNotIn("sweep_watchman_and_log", method_names)
        self.assertNotIn("run_readiness_for_contract", method_names)

    def test_decision_review_is_stage_abcd_only(self) -> None:
        trace = PipelineTraceVM(
            contract="ES",
            termination_stage="risk_authorization",
            final_decision="TRADE_REDUCED",
            stage_a_status="READY",
            stage_b_outcome="ANALYSIS_COMPLETE",
            stage_c_outcome="SETUP_PROPOSED",
            stage_d_decision="REDUCED",
        )

        panel = render_decision_review_panel(trace)

        self.assertTrue(panel["has_result"])
        self.assertIn("stage_a_status", panel)
        self.assertIn("stage_b_outcome", panel)
        self.assertIn("stage_c_outcome", panel)
        self.assertIn("stage_d_decision", panel)
        self.assertNotIn("stage_e", panel)
        self.assertNotIn("audit_log", panel)

    def test_audit_replay_declares_no_live_stage_e_backend(self) -> None:
        panel = render_audit_replay_panel(trace=None)
        self.assertEqual(panel["mode"], "fixture_or_stub")
        self.assertFalse(panel["stage_e_live_backend"])


if __name__ == "__main__":
    unittest.main()
