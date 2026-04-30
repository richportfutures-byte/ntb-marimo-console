from __future__ import annotations

import unittest

from ntb_marimo_console.demo_fixture_runtime import build_phase1_dependencies, default_fixtures_root
from ntb_marimo_console.market_data.futures_quote_service import NullFuturesQuoteProvider
from ntb_marimo_console.runtime_modes import assemble_runtime_for_profile, build_es_app_shell_for_mode
from ntb_marimo_console.runtime_profiles import get_runtime_profile


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

    def test_fixture_dependency_construction_includes_noop_market_data_service(self) -> None:
        dependencies = build_phase1_dependencies(default_fixtures_root())

        self.assertIsNotNone(dependencies.market_data_service)
        provider = getattr(dependencies.market_data_service, "_provider", None)
        self.assertIsInstance(provider, NullFuturesQuoteProvider)
        result = dependencies.market_data_service.get_quote("/ESM26")
        self.assertEqual(result.status, "disabled")
        self.assertEqual(result.provider_name, "disabled")

    def test_runtime_assembly_carries_market_data_service_without_changing_shell(self) -> None:
        profile = get_runtime_profile("fixture_es_demo")

        assembly = assemble_runtime_for_profile(profile=profile)
        shell = build_es_app_shell_for_mode(mode="fixture_demo")

        self.assertIsNotNone(assembly.dependencies.market_data_service)
        provider = getattr(assembly.dependencies.market_data_service, "_provider", None)
        self.assertIsInstance(provider, NullFuturesQuoteProvider)
        self.assertIn("surfaces", shell)
        self.assertIn("runtime", shell)
        self.assertEqual(shell["runtime"]["runtime_mode"], "fixture_demo")
        self.assertEqual(shell["runtime"]["profile_id"], "fixture_es_demo")


if __name__ == "__main__":
    unittest.main()
