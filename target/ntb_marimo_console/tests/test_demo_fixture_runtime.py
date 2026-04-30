from __future__ import annotations

import unittest
from datetime import datetime, timezone

from ntb_marimo_console.app import Phase1AppDependencies, build_phase1_app
from ntb_marimo_console.demo_fixture_runtime import (
    FixturePipelineBackend,
    build_phase1_dependencies,
    build_runtime_inputs_for_profile,
    default_fixtures_root,
)
from ntb_marimo_console.market_data.futures_quote_service import (
    FixtureFuturesQuoteProvider,
    FuturesQuote,
    FuturesQuoteService,
    NullFuturesQuoteProvider,
)
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
        self.assertEqual(surfaces["live_observables"]["market_data"]["status"], "Market data unavailable")
        self.assertEqual(surfaces["live_observables"]["market_data"]["bid"], "N/A")
        self.assertIn("Informational only.", surfaces["live_observables"]["market_data"]["disclaimer"])
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

    def test_fixture_market_data_display_does_not_change_workflow_or_runtime(self) -> None:
        profile = get_runtime_profile("fixture_es_demo")
        base_root = default_fixtures_root()
        artifacts_root = profile.resolve_artifact_root(base_root)
        inputs = build_runtime_inputs_for_profile(artifacts_root, profile=profile)
        baseline_dependencies = build_phase1_dependencies(artifacts_root, profile=profile)
        baseline_shell = build_phase1_app(
            backend=FixturePipelineBackend(artifacts_root, profile=profile),
            inputs=inputs,
            dependencies=baseline_dependencies,
        )

        fixture_service = FuturesQuoteService(
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
        fixture_dependencies = Phase1AppDependencies(
            premarket_store=baseline_dependencies.premarket_store,
            run_history_store=baseline_dependencies.run_history_store,
            audit_replay_store=baseline_dependencies.audit_replay_store,
            trigger_evaluator=baseline_dependencies.trigger_evaluator,
            market_data_service=fixture_service,
        )
        fixture_shell = build_phase1_app(
            backend=FixturePipelineBackend(artifacts_root, profile=profile),
            inputs=inputs,
            dependencies=fixture_dependencies,
        )

        self.assertEqual(
            fixture_shell["surfaces"]["query_action"],
            baseline_shell["surfaces"]["query_action"],
        )
        self.assertEqual(fixture_shell["workflow"], baseline_shell["workflow"])
        self.assertEqual(fixture_shell["runtime"], baseline_shell["runtime"])
        market_data = fixture_shell["surfaces"]["live_observables"]["market_data"]
        self.assertEqual(market_data["status"], "Fixture quote")
        self.assertEqual(market_data["bid"], "7175")
        self.assertEqual(market_data["ask"], "7175.5")
        self.assertEqual(market_data["last"], "7175.25")
        self.assertEqual(market_data["quote_time"], "2026-04-30T11:59:58+00:00")


if __name__ == "__main__":
    unittest.main()
