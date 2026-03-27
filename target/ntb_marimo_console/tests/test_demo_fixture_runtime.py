from __future__ import annotations

import unittest

from ntb_marimo_console.runtime_modes import build_es_app_shell_for_mode


class DemoFixtureRuntimeSmokeTests(unittest.TestCase):
    def test_boots_fixture_backed_es_shell(self) -> None:
        shell = build_es_app_shell_for_mode(mode="fixture_demo")

        self.assertIn("surfaces", shell)
        surfaces = shell["surfaces"]
        self.assertIn("pre_market_brief", surfaces)
        self.assertIn("readiness_matrix", surfaces)
        self.assertIn("live_observables", surfaces)
        self.assertIn("trigger_table", surfaces)
        self.assertIn("query_action", surfaces)
        self.assertIn("decision_review", surfaces)
        self.assertIn("audit_replay", surfaces)
        self.assertIn("run_history", surfaces)
        self.assertEqual(surfaces["run_history"]["source"], "fixture_backed")
        self.assertIn("runtime", shell)
        self.assertEqual(shell["runtime"]["runtime_mode"], "fixture_demo")
        self.assertEqual(shell["runtime"]["profile_id"], "fixture_es_demo")
        self.assertEqual(shell["runtime"]["session_state"], "AUDIT_REPLAY_READY")

    def test_lockout_mode_keeps_query_disabled(self) -> None:
        shell = build_es_app_shell_for_mode(mode="fixture_demo", lockout=True)
        surfaces = shell["surfaces"]
        self.assertFalse(surfaces["query_action"]["query_enabled"])

    def test_fixture_demo_path_does_not_require_model_adapter(self) -> None:
        shell = build_es_app_shell_for_mode(mode="fixture_demo", model_adapter=None)
        self.assertEqual(shell["surfaces"]["run_history"]["source"], "fixture_backed")


if __name__ == "__main__":
    unittest.main()
