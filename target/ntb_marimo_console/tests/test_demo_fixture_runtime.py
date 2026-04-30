from __future__ import annotations

import unittest
from pathlib import Path

from ntb_marimo_console.adapters.schwab_futures_market_data import (
    SchwabFuturesMarketDataResult,
    SchwabFuturesQuoteSnapshot,
)
from ntb_marimo_console.demo_fixture_runtime import (
    build_phase1_dependencies,
    default_fixtures_root,
)
from ntb_marimo_console.market_data.config import resolve_futures_quote_service_config
from ntb_marimo_console.market_data.futures_quote_service import (
    FuturesQuote,
    NullFuturesQuoteProvider,
)
from ntb_marimo_console.runtime_modes import (
    assemble_runtime_for_profile,
    build_app_shell_from_assembly,
    build_es_app_shell_for_mode,
)
from ntb_marimo_console.runtime_profiles import get_runtime_profile


TEST_MARKET_DATA_MAX_AGE_SECONDS = "3600"


class FakeSchwabAdapter:
    def __init__(self, result: SchwabFuturesMarketDataResult) -> None:
        self.result = result
        self.requests: list[object] = []

    def fetch_once(self, request: object) -> SchwabFuturesMarketDataResult:
        self.requests.append(request)
        return self.result


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
        market_data_config = resolve_futures_quote_service_config(
            {
                "NTB_MARKET_DATA_PROVIDER": "fixture",
                "NTB_MARKET_DATA_SYMBOL": "ES",
                "NTB_MARKET_DATA_MAX_QUOTE_AGE_SECONDS": TEST_MARKET_DATA_MAX_AGE_SECONDS,
            },
            target_root=Path(__file__).resolve().parents[1],
        )
        baseline_shell = build_es_app_shell_for_mode(mode="fixture_demo")
        fixture_shell = build_es_app_shell_for_mode(
            mode="fixture_demo",
            market_data_config=market_data_config,
            market_data_fixture_quote=FuturesQuote(
                symbol="ES",
                bid_price=7175,
                ask_price=7175.5,
                last_price=7175.25,
                bid_size=19,
                ask_size=14,
                received_at="2026-04-30T11:59:58+00:00",
            ),
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

    def test_runtime_assembly_passes_fixture_market_data_config_and_injection_through_composition(self) -> None:
        profile = get_runtime_profile("fixture_es_demo")
        market_data_config = resolve_futures_quote_service_config(
            {
                "NTB_MARKET_DATA_PROVIDER": "fixture",
                "NTB_MARKET_DATA_SYMBOL": "ES",
                "NTB_MARKET_DATA_MAX_QUOTE_AGE_SECONDS": TEST_MARKET_DATA_MAX_AGE_SECONDS,
            },
            target_root=Path(__file__).resolve().parents[1],
        )

        assembly = assemble_runtime_for_profile(
            profile=profile,
            market_data_config=market_data_config,
            market_data_fixture_quote=FuturesQuote(
                symbol="ES",
                bid_price=7175,
                ask_price=7175.5,
                last_price=7175.25,
                bid_size=19,
                ask_size=14,
                received_at="2026-04-30T11:59:58+00:00",
            ),
        )
        shell = build_app_shell_from_assembly(assembly)

        self.assertIsNotNone(assembly.dependencies.market_data_service)
        result = assembly.dependencies.market_data_service.get_quote("ES")
        self.assertEqual(result.status, "connected")
        self.assertEqual(result.provider_name, "fixture")
        self.assertEqual(shell["surfaces"]["live_observables"]["market_data"]["status"], "Fixture quote")

    def test_fixture_market_data_config_without_explicit_quote_stays_unavailable(self) -> None:
        market_data_config = resolve_futures_quote_service_config(
            {
                "NTB_MARKET_DATA_PROVIDER": "fixture",
                "NTB_MARKET_DATA_SYMBOL": "ES",
                "NTB_MARKET_DATA_MAX_QUOTE_AGE_SECONDS": TEST_MARKET_DATA_MAX_AGE_SECONDS,
            },
            target_root=Path(__file__).resolve().parents[1],
        )

        shell = build_es_app_shell_for_mode(
            mode="fixture_demo",
            market_data_config=market_data_config,
        )

        market_data = shell["surfaces"]["live_observables"]["market_data"]
        self.assertEqual(market_data["status"], "Market data unavailable")
        self.assertEqual(market_data["bid"], "N/A")
        self.assertTrue(shell["surfaces"]["query_action"]["query_enabled"])

    def test_schwab_market_data_config_remains_blocked_and_unavailable(self) -> None:
        market_data_config = resolve_futures_quote_service_config(
            {
                "NTB_MARKET_DATA_PROVIDER": "schwab",
                "NTB_MARKET_DATA_SYMBOL": "ES",
                "NTB_MARKET_DATA_MAX_QUOTE_AGE_SECONDS": TEST_MARKET_DATA_MAX_AGE_SECONDS,
            },
            target_root=Path(__file__).resolve().parents[1],
        )

        dependencies = build_phase1_dependencies(
            default_fixtures_root(),
            market_data_config=market_data_config,
        )
        provider = getattr(dependencies.market_data_service, "_provider", None)
        result = dependencies.market_data_service.get_quote("ES")

        self.assertIsInstance(provider, NullFuturesQuoteProvider)
        self.assertEqual(result.status, "disabled")

    def test_schwab_market_data_display_uses_explicit_prebuilt_adapter_only(self) -> None:
        market_data_config = resolve_futures_quote_service_config(
            {
                "NTB_MARKET_DATA_PROVIDER": "schwab",
                "NTB_MARKET_DATA_SYMBOL": "ES",
                "NTB_MARKET_DATA_MAX_QUOTE_AGE_SECONDS": TEST_MARKET_DATA_MAX_AGE_SECONDS,
            },
            target_root=Path(__file__).resolve().parents[1],
        )
        baseline_shell = build_es_app_shell_for_mode(mode="fixture_demo")
        adapter = FakeSchwabAdapter(
            SchwabFuturesMarketDataResult(
                status="success",
                symbol="ES",
                field_ids=(0, 1, 2, 3, 4, 5),
                streamer_socket_host="streamer-api.schwab.com",
                login_response_code=0,
                subscription_response_code=0,
                market_data_received=True,
                last_quote_snapshot=SchwabFuturesQuoteSnapshot(
                    raw_fields=((0, "ES"), (1, 7175), (2, 7175.5), (3, 7175.25), (4, 19), (5, 14)),
                    symbol="ES",
                    bid_price=7175,
                    ask_price=7175.5,
                    last_price=7175.25,
                    bid_size=19,
                    ask_size=14,
                ),
                received_at="2026-04-30T11:59:58+00:00",
                failure_reason=None,
            )
        )

        schwab_shell = build_es_app_shell_for_mode(
            mode="fixture_demo",
            market_data_config=market_data_config,
            market_data_schwab_adapter=adapter,
        )

        self.assertEqual(schwab_shell["surfaces"]["query_action"], baseline_shell["surfaces"]["query_action"])
        self.assertEqual(schwab_shell["workflow"], baseline_shell["workflow"])
        self.assertEqual(schwab_shell["runtime"], baseline_shell["runtime"])
        market_data = schwab_shell["surfaces"]["live_observables"]["market_data"]
        self.assertEqual(market_data["status"], "Schwab quote")
        self.assertEqual(market_data["bid"], "7175")
        self.assertEqual(market_data["ask"], "7175.5")
        self.assertEqual(market_data["last"], "7175.25")
        self.assertEqual(market_data["quote_time"], "2026-04-30T11:59:58+00:00")
        self.assertEqual(len(adapter.requests), 1)

    def test_runtime_assembly_accepts_explicit_schwab_adapter_factory(self) -> None:
        profile = get_runtime_profile("fixture_es_demo")
        market_data_config = resolve_futures_quote_service_config(
            {
                "NTB_MARKET_DATA_PROVIDER": "schwab",
                "NTB_MARKET_DATA_SYMBOL": "ES",
                "NTB_MARKET_DATA_MAX_QUOTE_AGE_SECONDS": TEST_MARKET_DATA_MAX_AGE_SECONDS,
            },
            target_root=Path(__file__).resolve().parents[1],
        )
        seen_configs: list[object] = []
        adapter = FakeSchwabAdapter(
            SchwabFuturesMarketDataResult(
                status="success",
                symbol="ES",
                field_ids=(0, 1, 2, 3, 4, 5),
                streamer_socket_host="streamer-api.schwab.com",
                login_response_code=0,
                subscription_response_code=0,
                market_data_received=True,
                last_quote_snapshot=SchwabFuturesQuoteSnapshot(
                    raw_fields=((0, "ES"), (1, 7175), (2, 7175.5), (3, 7175.25), (4, 19), (5, 14)),
                    symbol="ES",
                    bid_price=7175,
                    ask_price=7175.5,
                    last_price=7175.25,
                    bid_size=19,
                    ask_size=14,
                ),
                received_at="2026-04-30T11:59:58+00:00",
                failure_reason=None,
            )
        )

        assembly = assemble_runtime_for_profile(
            profile=profile,
            market_data_config=market_data_config,
            market_data_schwab_adapter_factory=lambda cfg: seen_configs.append(cfg) or adapter,
        )
        shell = build_app_shell_from_assembly(assembly)

        self.assertTrue(seen_configs)
        self.assertEqual(seen_configs[0].provider, "schwab")
        self.assertEqual(
            shell["surfaces"]["live_observables"]["market_data"]["status"],
            "Schwab quote",
        )
        self.assertEqual(shell["runtime"]["session_state"], "AUDIT_REPLAY_READY")
        self.assertEqual(len(adapter.requests), 1)

    def test_runtime_market_data_paths_do_not_import_probe_logic(self) -> None:
        source_root = Path(__file__).resolve().parents[1] / "src" / "ntb_marimo_console"
        runtime_modes_source = (source_root / "runtime_modes.py").read_text(encoding="utf-8")
        demo_runtime_source = (source_root / "demo_fixture_runtime.py").read_text(encoding="utf-8")

        self.assertNotIn("probe_schwab_futures_market_data_adapter", runtime_modes_source)
        self.assertNotIn("probe_schwab_futures_market_data_adapter", demo_runtime_source)
        self.assertNotIn(".env", runtime_modes_source)
        self.assertNotIn(".env", demo_runtime_source)


if __name__ == "__main__":
    unittest.main()
