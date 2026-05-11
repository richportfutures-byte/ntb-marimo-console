from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from ntb_marimo_console.adapters.schwab_futures_market_data import (
    SchwabFuturesMarketDataResult,
    SchwabFuturesQuoteSnapshot,
)
from ntb_marimo_console.demo_fixture_runtime import (
    FixturePipelineBackend,
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
    build_app_shell_for_profile,
    build_es_app_shell_for_mode,
)
from ntb_marimo_console.runtime_profiles import RuntimeProfile, get_runtime_profile
from ntb_marimo_console.trigger_state import TriggerState, TriggerStateResult


def _query_ready_trigger_state_results(request: object) -> tuple[TriggerStateResult, ...]:
    """Stub producer output: real produced QUERY_READY TriggerStateResult for the request contract.

    Used only by demo tests that explicitly require a successful pipeline query path
    (narrative sidecar surfacing, missing-sidecar fail-safe behavior).
    """
    contract = getattr(request, "contract", "ES")
    return (
        TriggerStateResult(
            contract=contract,
            setup_id=f"{contract.lower()}_setup_1",
            trigger_id=f"{contract.lower()}_trigger_query_ready",
            state=TriggerState.QUERY_READY,
            distance_to_trigger_ticks=0.0,
            required_fields=("market.current_price",),
            missing_fields=(),
            invalid_reasons=(),
            blocking_reasons=(),
            last_updated=getattr(request, "last_updated", None) or "2026-03-25T09:35:00-04:00",
        ),
    )


TEST_MARKET_DATA_MAX_AGE_SECONDS = "3600"
DETERMINISTIC_FIXTURE_NOW = datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc)


def cl_fixture_profile() -> RuntimeProfile:
    return RuntimeProfile(
        profile_id="fixture_cl_contract_sidecar",
        runtime_mode="fixture_demo",
        contract="CL",
        session_date="2026-01-14",
        evaluation_timestamp_iso="2026-01-14T09:05:00-05:00",
        artifact_root_relative=Path("."),
        artifact_contract_dir="CL",
        readiness_trigger={"trigger_family": "price_level_touch", "price_level": 73.35},
    )


class FakeSchwabAdapter:
    def __init__(self, result: SchwabFuturesMarketDataResult) -> None:
        self.result = result
        self.requests: list[object] = []

    def fetch_once(self, request: object) -> SchwabFuturesMarketDataResult:
        self.requests.append(request)
        return self.result


class DemoFixtureRuntimeSmokeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._clock_patcher = patch(
            "ntb_marimo_console.market_data.futures_quote_service._utc_now",
            new=lambda: DETERMINISTIC_FIXTURE_NOW,
        )
        self._clock_patcher.start()
        self.addCleanup(self._clock_patcher.stop)

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
        gate = surfaces["query_action"]["pipeline_query_gate"]
        self.assertFalse(surfaces["query_action"]["query_enabled"])
        self.assertEqual(gate["trigger_state"], "TOUCHED")
        self.assertTrue(gate["trigger_state_from_real_producer"])
        self.assertEqual(shell["runtime"]["session_state"], "QUERY_ACTION_FAILED")

    def test_lockout_mode_keeps_query_disabled(self) -> None:
        shell = build_es_app_shell_for_mode(mode="fixture_demo", lockout=True)
        surfaces = shell["surfaces"]
        self.assertFalse(surfaces["query_action"]["query_enabled"])

    def test_fixture_demo_path_does_not_require_model_adapter(self) -> None:
        shell = build_es_app_shell_for_mode(mode="fixture_demo", model_adapter=None)
        self.assertEqual(shell["surfaces"]["run_history"]["source"], "fixture_backed")

    def test_fixture_sidecar_narrative_surfaces_through_replay_quality_path(self) -> None:
        with patch(
            "ntb_marimo_console.app.build_trigger_state_results",
            new=_query_ready_trigger_state_results,
        ):
            shell = build_es_app_shell_for_mode(mode="fixture_demo")
        decision = shell["surfaces"]["decision_review"]
        replay = decision["narrative_audit_replay"]

        self.assertTrue(decision["narrative_available"])
        self.assertTrue(decision["engine_reasoning"]["available"])
        self.assertEqual(decision["engine_reasoning"]["market_regime"], "choppy")
        self.assertEqual(decision["engine_reasoning"]["outcome"], "NO_TRADE")
        self.assertIn("Synthetic fixture/demo ES narrative", decision["engine_reasoning"]["structural_notes"])
        self.assertFalse(decision["trade_thesis"]["available"])
        self.assertEqual(replay["source"], "fixture")
        self.assertEqual(replay["replay_reference_status"], "available")
        self.assertEqual(replay["replay_reference_source"], "fixture_backed")
        self.assertTrue(replay["engine_narrative_available"])
        self.assertFalse(replay["trigger_transition_narrative_available"])
        self.assertEqual(replay["narrative_quality"]["status"], "WARN")
        self.assertTrue(replay["narrative_quality"]["source_reference_present"])
        self.assertTrue(replay["narrative_quality"]["replay_reference_present"])
        self.assertFalse(replay["narrative_quality"]["trigger_transition_narrative_present"])
        self.assertIn("trigger_transition_narrative_present", replay["narrative_quality"]["warnings"])

    def test_cl_fixture_sidecar_surfaces_contract_market_read_through_replay_path(self) -> None:
        with patch(
            "ntb_marimo_console.app.build_trigger_state_results",
            new=_query_ready_trigger_state_results,
        ):
            shell = build_app_shell_for_profile(
                profile=cl_fixture_profile(),
                query_action_requested=True,
            )
        decision = shell["surfaces"]["decision_review"]
        replay = decision["narrative_audit_replay"]

        self.assertEqual(shell["runtime"]["contract"], "CL")
        self.assertEqual(shell["runtime"]["runtime_mode"], "fixture_demo")
        self.assertEqual(shell["runtime"]["session_state"], "AUDIT_REPLAY_READY")
        self.assertTrue(decision["narrative_available"])
        self.assertTrue(decision["engine_reasoning"]["available"])
        self.assertEqual(decision["engine_reasoning"]["outcome"], "NO_TRADE")
        self.assertIn("Synthetic fixture/demo CL market read", decision["engine_reasoning"]["structural_notes"])
        self.assertIn("does not infer DOM", decision["engine_reasoning"]["structural_notes"])
        self.assertFalse(decision["trade_thesis"]["available"])
        self.assertEqual(replay["contract"], "CL")
        self.assertEqual(replay["final_decision"], "NO_TRADE")
        self.assertEqual(replay["replay_reference_status"], "available")
        self.assertEqual(replay["replay_reference_source"], "fixture_backed")
        self.assertTrue(replay["engine_narrative_available"])
        self.assertFalse(replay["trigger_transition_narrative_available"])
        self.assertEqual(replay["narrative_quality"]["status"], "WARN")
        self.assertFalse(replay["narrative_quality"]["unsupported_market_read_claim_detected"])
        self.assertFalse(replay["narrative_quality"]["unsupported_contract_language_detected"])
        self.assertFalse(replay["narrative_quality"]["trigger_transition_narrative_present"])
        self.assertIn("trigger_transition_narrative_present", replay["narrative_quality"]["warnings"])

    def test_missing_fixture_sidecar_remains_explicit_without_crashing(self) -> None:
        source_root = default_fixtures_root()
        profile = get_runtime_profile("fixture_es_demo")
        with tempfile.TemporaryDirectory() as temp_dir:
            fixture_root = Path(temp_dir) / "phase1"
            shutil.copytree(source_root, fixture_root)
            sidecar = fixture_root / "pipeline" / "ES" / "pipeline_result.no_trade.narrative.json"
            sidecar.unlink()

            with patch(
                "ntb_marimo_console.app.build_trigger_state_results",
                new=_query_ready_trigger_state_results,
            ):
                shell = build_es_app_shell_for_mode(mode="fixture_demo", fixtures_root=fixture_root)
            backend = FixturePipelineBackend(fixture_root, profile=profile)

            decision = shell["surfaces"]["decision_review"]
            replay = decision["narrative_audit_replay"]

            self.assertFalse(decision["narrative_available"])
            self.assertFalse(decision["engine_reasoning"]["available"])
            self.assertIn("did not surface narrative", decision["narrative_unavailable_message"].lower())
            self.assertFalse(replay["engine_narrative_available"])
            self.assertEqual(replay["narrative_quality"]["status"], "WARN")
            self.assertTrue(replay["narrative_quality"]["missing_narrative_detected"])
            self.assertIsNone(backend.narrate_pipeline_result({})["contract_analysis"])

    def test_fixture_sidecar_content_is_synthetic_safe_and_contract_scoped(self) -> None:
        fixture_root = default_fixtures_root()
        sidecars = sorted((fixture_root / "pipeline").glob("*/*.narrative.json"))
        sidecar_paths = {path.relative_to(fixture_root).as_posix() for path in sidecars}

        self.assertEqual(
            sidecar_paths,
            {
                "pipeline/6E/pipeline_result.no_trade.narrative.json",
                "pipeline/CL/pipeline_result.no_trade.narrative.json",
                "pipeline/ES/pipeline_result.no_trade.narrative.json",
                "pipeline/MGC/pipeline_result.no_trade.narrative.json",
                "pipeline/NQ/pipeline_result.no_trade.narrative.json",
            },
        )

        payloads = [json.loads(sidecar.read_text(encoding="utf-8")) for sidecar in sidecars]
        contracts = {payload["contract_analysis"]["contract"] for payload in payloads}
        self.assertEqual(contracts, {"6E", "CL", "ES", "MGC", "NQ"})

        for payload in payloads:
            rendered = json.dumps(payload, sort_keys=True).lower()
            contract = payload["contract_analysis"]["contract"]
            self.assertEqual(payload["contract_analysis"]["outcome"], "NO_TRADE")
            self.assertIsNone(payload["proposed_setup"])
            self.assertIn("synthetic fixture/demo", rendered)
            self.assertIn("execution remains manual", rendered)
            if contract != "ES":
                self.assertIn("preserved engine remains the decision authority", rendered)
            if contract == "6E":
                self.assertIn("numeric dxy", rendered)
                self.assertIn("session-sequence", rendered)
            if contract == "MGC":
                self.assertIn("numeric dxy", rendered)
                self.assertIn("yield-context", rendered)
                self.assertIn("fear-catalyst", rendered)
            for forbidden in (
                "account",
                "order",
                "fill",
                "p&l",
                "credential",
                "token",
                "http://",
                "https://",
                "wss://",
                "customer",
                "correl",
                "authorization",
                "zn",
                '"gc"',
            ):
                self.assertNotIn(forbidden, rendered)

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
        # Default fixture path produces TOUCHED, not QUERY_READY, so the R13 gate stays disabled.
        gate = shell["surfaces"]["query_action"]["pipeline_query_gate"]
        self.assertFalse(shell["surfaces"]["query_action"]["query_enabled"])
        self.assertEqual(gate["trigger_state"], "TOUCHED")
        self.assertIn("trigger_state_not_query_ready:TOUCHED", gate["disabled_reasons"])

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
        with patch(
            "ntb_marimo_console.app.build_trigger_state_results",
            new=_query_ready_trigger_state_results,
        ):
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
