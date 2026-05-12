from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ninjatradebuilder.logging_record import RunHistoryRecord, append_log_record

from ntb_marimo_console.adapters.stage_e_log import resolve_stage_e_log_path
from ntb_marimo_console.adapters.contracts import PipelineQueryRequest, WatchmanSweepRequest
from ntb_marimo_console.adapters.preserved_engine_backend import PreservedEngineBackend
from ntb_marimo_console.demo_fixture_runtime import FixturePipelineBackend
from ntb_marimo_console.preserved_fixture_artifacts import write_preserved_fixture_artifacts
from ntb_marimo_console.runtime_modes import (
    PreservedModeInitializationError,
    RuntimeDataUnavailableError,
    build_app_shell_for_profile_id,
    build_backend_for_mode,
)
from ntb_marimo_console.runtime_profiles import get_runtime_profile

from tests._query_ready_producer import query_ready_trigger_state_results


FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "golden" / "phase1"


class _ValidModelAdapter:
    def generate_structured(self, request: object) -> dict[str, object]:
        return {"ok": True}


class _ReadyPreservedBackend:
    run_pipeline_calls = 0

    def __init__(self, *, model_adapter: object) -> None:
        self._model_adapter = model_adapter
        self._last_contract = "ES"

    def sweep_watchman(self, request: WatchmanSweepRequest) -> dict[str, SimpleNamespace]:
        contracts = tuple(request.packet_bundle.get("contracts", {}).keys()) or ("ES",)
        return {
            contract: SimpleNamespace(
                contract=contract,
                event_risk_state="clear",
                vwap_posture_state="price_above_vwap",
                value_location_state="inside_value",
                level_proximity_state="clear_of_structure",
                hard_lockout_flags=[],
                awareness_flags=[],
                missing_inputs=[],
            )
            for contract in contracts
        }

    def run_pipeline(self, request: PipelineQueryRequest) -> object:
        _ReadyPreservedBackend.run_pipeline_calls += 1
        self._last_contract = request.contract
        append_log_record(
            RunHistoryRecord(
                run_id=f"test-{request.contract.lower()}",
                logged_at=datetime.now(tz=timezone.utc),
                contract=request.contract,
                evaluation_timestamp_iso=request.evaluation_timestamp_iso or "2026-03-25T13:35:00Z",
                run_type="full_pipeline",
                trigger_family=str((request.readiness_trigger or {}).get("trigger_family", "price_level_touch")),
                watchman_status="ready",
                watchman_hard_lockouts=[],
                watchman_awareness_flags=[],
                watchman_missing_inputs=[],
                vwap_posture="price_above_vwap",
                value_location="inside_value",
                level_proximity="clear_of_structure",
                event_risk="clear",
                trigger_state="trigger_true",
                final_decision="NO_TRADE",
                termination_stage="contract_market_read",
                sufficiency_gate_status="READY",
                contract_analysis_outcome="NO_TRADE",
                proposed_setup_outcome=None,
                risk_authorization_decision=None,
                notes="runtime_modes_preserved test log",
            ),
            resolve_stage_e_log_path(request.contract),
        )
        return {"ok": True, "contract": request.contract}

    def summarize_pipeline_result(self, result: object) -> dict[str, object]:
        return {
            "contract": self._last_contract,
            "termination_stage": "contract_market_read",
            "final_decision": "NO_TRADE",
            "sufficiency_gate_status": "READY",
            "contract_analysis_outcome": "NO_TRADE",
            "proposed_setup_outcome": None,
            "risk_authorization_decision": None,
        }

    def narrate_pipeline_result(self, result: object) -> dict[str, object]:
        return {
            "contract_analysis": None,
            "proposed_setup": None,
            "risk_authorization": None,
        }


class _BrokenPreservedBackend:
    def __init__(self, *, model_adapter: object) -> None:
        raise RuntimeError("boom")


class _NonLoggingPreservedBackend(_ReadyPreservedBackend):
    def run_pipeline(self, request: PipelineQueryRequest) -> object:
        _ReadyPreservedBackend.run_pipeline_calls += 1
        self._last_contract = request.contract
        return {"ok": True, "contract": request.contract}


class RuntimeModesPreservedTests(unittest.TestCase):
    @staticmethod
    def _build_valid_preserved_artifact_root(root: Path, *, profile_id: str) -> Path:
        source_root = FIXTURES_ROOT
        artifact_root = root / "phase1"
        shutil.copytree(source_root, artifact_root)
        write_preserved_fixture_artifacts(
            artifact_root,
            profile=get_runtime_profile(profile_id),
        )
        return artifact_root

    def test_fixture_mode_returns_fixture_backend(self) -> None:
        backend = build_backend_for_mode(
            mode="fixture_demo",
            fixtures_root=FIXTURES_ROOT,
        )
        self.assertIsInstance(backend, FixturePipelineBackend)

    def test_preserved_mode_requires_model_adapter(self) -> None:
        with self.assertRaises(PreservedModeInitializationError):
            build_backend_for_mode(
                mode="preserved_engine",
                fixtures_root=FIXTURES_ROOT,
                model_adapter=None,
            )

    def test_preserved_mode_rejects_invalid_adapter_shape(self) -> None:
        with self.assertRaises(PreservedModeInitializationError):
            build_backend_for_mode(
                mode="preserved_engine",
                fixtures_root=FIXTURES_ROOT,
                model_adapter=object(),
            )

    def test_preserved_mode_init_failure_is_fail_closed_no_fallback(self) -> None:
        with patch(
            "ntb_marimo_console.runtime_modes.PreservedEngineBackend",
            _BrokenPreservedBackend,
        ):
            with self.assertRaises(PreservedModeInitializationError):
                build_backend_for_mode(
                    mode="preserved_engine",
                    fixtures_root=FIXTURES_ROOT,
                    model_adapter=_ValidModelAdapter(),
                )

    def test_supported_preserved_profile_reaches_ready_state(self) -> None:
        _ReadyPreservedBackend.run_pipeline_calls = 0
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_root = self._build_valid_preserved_artifact_root(
                Path(temp_dir),
                profile_id="preserved_es_phase1",
            )
            with patch.dict(os.environ, {"NTB_STAGE_E_LOG_ROOT": str(Path(temp_dir) / ".stage_e")}):
                with patch(
                    "ntb_marimo_console.runtime_modes.PreservedEngineBackend",
                    _ReadyPreservedBackend,
                ), patch(
                    "ntb_marimo_console.app.build_trigger_state_results",
                    new=query_ready_trigger_state_results,
                ):
                    shell = build_app_shell_for_profile_id(
                        profile_id="preserved_es_phase1",
                        fixtures_root=artifact_root,
                        model_adapter=_ValidModelAdapter(),
                    )

        surfaces = shell["surfaces"]
        self.assertEqual(surfaces["session_header"]["contract"], "ES")
        self.assertEqual(surfaces["run_history"]["source"], "stage_e_jsonl")
        self.assertTrue(surfaces["query_action"]["query_enabled"])
        self.assertTrue(surfaces["decision_review"]["has_result"])
        self.assertTrue(surfaces["audit_replay"]["stage_e_live_backend"])
        self.assertEqual(surfaces["audit_replay"]["source"], "stage_e_jsonl")
        self.assertEqual(shell["runtime"]["runtime_mode"], "preserved_engine")
        self.assertEqual(shell["runtime"]["profile_id"], "preserved_es_phase1")
        self.assertEqual(_ReadyPreservedBackend.run_pipeline_calls, 1)

    def test_second_supported_preserved_profile_reaches_ready_state(self) -> None:
        _ReadyPreservedBackend.run_pipeline_calls = 0
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_root = self._build_valid_preserved_artifact_root(
                Path(temp_dir),
                profile_id="preserved_nq_phase1",
            )
            with patch.dict(os.environ, {"NTB_STAGE_E_LOG_ROOT": str(Path(temp_dir) / ".stage_e")}):
                with patch(
                    "ntb_marimo_console.runtime_modes.PreservedEngineBackend",
                    _ReadyPreservedBackend,
                ), patch(
                    "ntb_marimo_console.app.build_trigger_state_results",
                    new=query_ready_trigger_state_results,
                ):
                    shell = build_app_shell_for_profile_id(
                        profile_id="preserved_nq_phase1",
                        fixtures_root=artifact_root,
                        model_adapter=_ValidModelAdapter(),
                    )

        surfaces = shell["surfaces"]
        self.assertEqual(surfaces["session_header"]["contract"], "NQ")
        self.assertEqual(surfaces["run_history"]["source"], "stage_e_jsonl")
        self.assertTrue(surfaces["query_action"]["query_enabled"])
        self.assertTrue(surfaces["decision_review"]["has_result"])
        self.assertTrue(surfaces["audit_replay"]["stage_e_live_backend"])
        self.assertEqual(surfaces["audit_replay"]["source"], "stage_e_jsonl")
        self.assertEqual(shell["runtime"]["runtime_mode"], "preserved_engine")
        self.assertEqual(shell["runtime"]["profile_id"], "preserved_nq_phase1")
        self.assertEqual(_ReadyPreservedBackend.run_pipeline_calls, 1)

        cockpit = shell["r14_cockpit"]
        identity = cockpit["identity"]
        runtime = cockpit["runtime_status"]
        premarket = cockpit["premarket"]
        trigger = cockpit["triggers"][0]
        query = cockpit["query_readiness"]
        last_result = cockpit["last_pipeline_result"]
        replay = cockpit["replay_availability"]
        operator_states = {
            state["category"]: state
            for state in cockpit["operator_states"]
        }

        self.assertEqual(identity["contract"], "NQ")
        self.assertEqual(identity["current_profile"], "preserved_nq_phase1")
        self.assertEqual(identity["contract_support_status"], "final_supported")
        self.assertEqual(identity["runtime_profile_status"], "available")

        self.assertEqual(runtime["provider_status"], "fixture")
        self.assertEqual(runtime["stream_status"], "fixture")
        self.assertEqual(runtime["quote_freshness"], "fresh")
        self.assertEqual(runtime["bar_freshness"], "fresh")
        self.assertEqual(runtime["event_lockout_state"], "inactive")

        self.assertEqual(premarket["premarket_brief_status"], "READY")
        self.assertIn("cross_asset.relative_strength_vs_es", premarket["required_fields"])
        self.assertIn(
            "Absolute NQ price action is not sufficient when ES-relative confirmation is required.",
            premarket["warnings"],
        )
        self.assertIn(
            "Missing NQ or ES anchors must keep the read model blocked.",
            premarket["warnings"],
        )
        self.assertIn(
            "Do not treat NQ as ready if ES-relative strength is unavailable or below threshold.",
            premarket["warnings"],
        )
        self.assertEqual(
            {
                field["field"]: field["status"]
                for field in premarket["unavailable_fields"]
            },
            {
                "cross_asset.index_cash_tone": "unavailable_not_inferred",
            },
        )
        self.assertEqual(
            {
                invalidator["invalidator_id"]: invalidator["action"]
                for invalidator in premarket["invalidators"]
            },
            {
                "nq_relative_strength_failure": "block_query_ready_read_model",
                "nq_completed_bar_confirmation_missing": "block_query_ready_read_model",
            },
        )

        self.assertEqual(trigger["setup_id"], "nq_setup_1")
        self.assertEqual(trigger["trigger_state"], "QUERY_READY")
        self.assertEqual(trigger["query_ready_provenance"], "real_trigger_state_result")
        self.assertEqual(trigger["distance_to_trigger_ticks"], 0.0)
        self.assertEqual(trigger["blocking_reasons"], [])

        self.assertTrue(query["query_ready"])
        self.assertTrue(query["manual_query_allowed"])
        self.assertTrue(query["trigger_state_from_real_producer"])
        self.assertEqual(query["pipeline_gate_state"], "ENABLED")
        self.assertEqual(
            query["query_ready_provenance"],
            "real_trigger_state_result_and_pipeline_gate",
        )
        self.assertIn("bars_fresh_and_available", query["enabled_reasons"])
        self.assertIn("trigger_state_query_ready", query["enabled_reasons"])
        self.assertIn("event_lockout_inactive", query["enabled_reasons"])

        self.assertEqual(last_result["final_decision"], "NO_TRADE")
        self.assertEqual(last_result["no_trade_summary"], "Preserved engine returned NO_TRADE.")
        self.assertIsNone(last_result["approved_summary"])
        self.assertIsNone(last_result["rejected_summary"])

        self.assertTrue(replay["audit_replay_available"])
        self.assertEqual(replay["audit_replay_status"], "available")
        self.assertEqual(replay["replay_statement"], "No synthetic replay is labeled as real evidence.")

        self.assertEqual(operator_states["fixture_mode"]["state"], "fixture_mode")
        self.assertEqual(operator_states["query_ready"]["state"], "query_ready")
        self.assertEqual(operator_states["query_ready"]["source"], "query_readiness")

    def test_third_supported_preserved_profile_reaches_ready_state(self) -> None:
        _ReadyPreservedBackend.run_pipeline_calls = 0
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_root = self._build_valid_preserved_artifact_root(
                Path(temp_dir),
                profile_id="preserved_cl_phase1",
            )
            with patch.dict(os.environ, {"NTB_STAGE_E_LOG_ROOT": str(Path(temp_dir) / ".stage_e")}):
                with patch(
                    "ntb_marimo_console.runtime_modes.PreservedEngineBackend",
                    _ReadyPreservedBackend,
                ), patch(
                    "ntb_marimo_console.app.build_trigger_state_results",
                    new=query_ready_trigger_state_results,
                ):
                    shell = build_app_shell_for_profile_id(
                        profile_id="preserved_cl_phase1",
                        fixtures_root=artifact_root,
                        model_adapter=_ValidModelAdapter(),
                    )

        surfaces = shell["surfaces"]
        self.assertEqual(surfaces["session_header"]["contract"], "CL")
        self.assertEqual(surfaces["run_history"]["source"], "stage_e_jsonl")
        self.assertTrue(surfaces["query_action"]["query_enabled"])
        self.assertTrue(surfaces["decision_review"]["has_result"])
        self.assertTrue(surfaces["audit_replay"]["stage_e_live_backend"])
        self.assertEqual(surfaces["audit_replay"]["source"], "stage_e_jsonl")
        self.assertEqual(shell["runtime"]["runtime_mode"], "preserved_engine")
        self.assertEqual(shell["runtime"]["profile_id"], "preserved_cl_phase1")
        self.assertEqual(_ReadyPreservedBackend.run_pipeline_calls, 1)

        cockpit = shell["r14_cockpit"]
        identity = cockpit["identity"]
        runtime = cockpit["runtime_status"]
        premarket = cockpit["premarket"]
        trigger = cockpit["triggers"][0]
        query = cockpit["query_readiness"]
        last_result = cockpit["last_pipeline_result"]
        replay = cockpit["replay_availability"]
        operator_states = {
            state["category"]: state
            for state in cockpit["operator_states"]
        }

        self.assertEqual(identity["contract"], "CL")
        self.assertEqual(identity["current_profile"], "preserved_cl_phase1")
        self.assertEqual(identity["contract_support_status"], "final_supported")
        self.assertEqual(identity["runtime_profile_status"], "available")

        self.assertEqual(runtime["provider_status"], "fixture")
        self.assertEqual(runtime["stream_status"], "fixture")
        self.assertEqual(runtime["quote_freshness"], "fresh")
        self.assertEqual(runtime["bar_freshness"], "fresh")
        self.assertEqual(runtime["event_lockout_state"], "inactive")

        self.assertEqual(premarket["premarket_brief_status"], "READY")
        self.assertIn("volatility_context.current_volume_vs_average", premarket["required_fields"])
        self.assertIn("macro_context.eia_lockout_active", premarket["required_fields"])
        self.assertEqual(
            {
                field["field"]: field["status"]
                for field in premarket["unavailable_fields"]
            },
            {
                "dom": "unavailable_not_inferred",
                "sweep": "unavailable_not_inferred",
            },
        )
        self.assertIn("If the EIA lockout activates, keep the query blocked.", premarket["warnings"])
        self.assertIn(
            "Reduce trust in the read model around headline spikes; do not infer sweep or DOM evidence from quote or bar data.",
            premarket["warnings"],
        )
        self.assertEqual(
            {
                invalidator["invalidator_id"]
                for invalidator in premarket["invalidators"]
            },
            {
                "cl_eia_lockout_active",
                "cl_volume_or_delta_failure",
            },
        )

        self.assertEqual(trigger["trigger_state"], "QUERY_READY")
        self.assertEqual(trigger["query_ready_provenance"], "real_trigger_state_result")
        self.assertEqual(trigger["missing_fields"], [])
        self.assertEqual(trigger["blocking_reasons"], [])

        self.assertTrue(query["query_ready"])
        self.assertTrue(query["manual_query_allowed"])
        self.assertTrue(query["trigger_state_from_real_producer"])
        self.assertEqual(query["query_ready_provenance"], "real_trigger_state_result_and_pipeline_gate")
        self.assertIn("event_lockout_inactive", query["enabled_reasons"])
        self.assertIn("bars_fresh_and_available", query["enabled_reasons"])
        self.assertEqual(query["disabled_reasons"], [])

        self.assertEqual(last_result["status"], "completed")
        self.assertEqual(last_result["final_decision"], "NO_TRADE")
        self.assertEqual(last_result["no_trade_summary"], "Preserved engine returned NO_TRADE.")
        self.assertNotIn("alternate", json.dumps(last_result, sort_keys=True).lower())

        self.assertTrue(replay["audit_replay_available"])
        self.assertEqual(replay["run_history_status"], "available")
        self.assertEqual(replay["replay_statement"], "No synthetic replay is labeled as real evidence.")

        self.assertIn("fixture_mode", operator_states)
        self.assertIn("query_ready", operator_states)
        self.assertEqual(cockpit["blocking_reasons"], [])

    def test_fourth_supported_preserved_profile_reaches_ready_state(self) -> None:
        _ReadyPreservedBackend.run_pipeline_calls = 0
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_root = self._build_valid_preserved_artifact_root(
                Path(temp_dir),
                profile_id="preserved_6e_phase1",
            )
            with patch.dict(os.environ, {"NTB_STAGE_E_LOG_ROOT": str(Path(temp_dir) / ".stage_e")}):
                with patch(
                    "ntb_marimo_console.runtime_modes.PreservedEngineBackend",
                    _ReadyPreservedBackend,
                ), patch(
                    "ntb_marimo_console.app.build_trigger_state_results",
                    new=query_ready_trigger_state_results,
                ):
                    shell = build_app_shell_for_profile_id(
                        profile_id="preserved_6e_phase1",
                        fixtures_root=artifact_root,
                        model_adapter=_ValidModelAdapter(),
                    )

        surfaces = shell["surfaces"]
        self.assertEqual(surfaces["session_header"]["contract"], "6E")
        self.assertEqual(surfaces["run_history"]["source"], "stage_e_jsonl")
        self.assertTrue(surfaces["query_action"]["query_enabled"])
        self.assertTrue(surfaces["decision_review"]["has_result"])
        self.assertTrue(surfaces["audit_replay"]["stage_e_live_backend"])
        self.assertEqual(surfaces["audit_replay"]["source"], "stage_e_jsonl")
        self.assertEqual(shell["runtime"]["runtime_mode"], "preserved_engine")
        self.assertEqual(shell["runtime"]["profile_id"], "preserved_6e_phase1")
        self.assertEqual(_ReadyPreservedBackend.run_pipeline_calls, 1)

        cockpit = shell["r14_cockpit"]
        identity = cockpit["identity"]
        runtime = cockpit["runtime_status"]
        premarket = cockpit["premarket"]
        trigger = cockpit["triggers"][0]
        query = cockpit["query_readiness"]
        last_result = cockpit["last_pipeline_result"]
        replay = cockpit["replay_availability"]
        operator_states = {
            state["category"]: state
            for state in cockpit["operator_states"]
        }

        self.assertEqual(identity["contract"], "6E")
        self.assertEqual(identity["current_profile"], "preserved_6e_phase1")
        self.assertEqual(identity["contract_support_status"], "final_supported")
        self.assertEqual(identity["runtime_profile_status"], "available")

        self.assertEqual(runtime["provider_status"], "fixture")
        self.assertEqual(runtime["stream_status"], "fixture")
        self.assertEqual(runtime["quote_freshness"], "fresh")
        self.assertEqual(runtime["bar_freshness"], "fresh")
        self.assertEqual(runtime["event_lockout_state"], "inactive")

        self.assertEqual(premarket["premarket_brief_status"], "READY")
        self.assertIn("cross_asset.dxy", premarket["required_fields"])
        self.assertIn("session_sequence.asia_complete", premarket["required_fields"])
        self.assertIn("session_sequence.london_complete", premarket["required_fields"])
        self.assertIn("session_sequence.ny_pending", premarket["required_fields"])
        self.assertIn(
            "Textual dollar context is not sufficient when DXY is required.",
            premarket["warnings"],
        )
        self.assertIn(
            "Absolute 6E price action is not sufficient without numeric DXY and explicit session sequence confirmation.",
            premarket["warnings"],
        )
        self.assertIn(
            "Thin liquidity after London close must keep the read model blocked or locked out when active.",
            premarket["warnings"],
        )
        self.assertEqual(
            {
                field["field"]: field["status"]
                for field in premarket["unavailable_fields"]
            },
            {
                "dxy_textual_context": "unavailable_not_inferred",
            },
        )
        self.assertEqual(
            {
                invalidator["invalidator_id"]: invalidator["action"]
                for invalidator in premarket["invalidators"]
            },
            {
                "sixe_numeric_dxy_failure": "block_query_ready_read_model",
                "sixe_session_sequence_incomplete": "block_query_ready_read_model",
            },
        )

        self.assertEqual(trigger["trigger_state"], "QUERY_READY")
        self.assertEqual(trigger["query_ready_provenance"], "real_trigger_state_result")
        self.assertEqual(trigger["distance_to_trigger_ticks"], 0.0)
        self.assertEqual(trigger["missing_fields"], [])
        self.assertEqual(trigger["blocking_reasons"], [])

        self.assertTrue(query["query_ready"])
        self.assertTrue(query["manual_query_allowed"])
        self.assertTrue(query["trigger_state_from_real_producer"])
        self.assertEqual(query["pipeline_gate_state"], "ENABLED")
        self.assertEqual(query["query_ready_provenance"], "real_trigger_state_result_and_pipeline_gate")
        self.assertIn("bars_fresh_and_available", query["enabled_reasons"])
        self.assertIn("trigger_state_query_ready", query["enabled_reasons"])
        self.assertIn("event_lockout_inactive", query["enabled_reasons"])
        self.assertEqual(query["disabled_reasons"], [])

        self.assertEqual(last_result["status"], "completed")
        self.assertEqual(last_result["final_decision"], "NO_TRADE")
        self.assertEqual(last_result["no_trade_summary"], "Preserved engine returned NO_TRADE.")
        self.assertIsNone(last_result["approved_summary"])
        self.assertIsNone(last_result["rejected_summary"])
        self.assertNotIn("alternate", json.dumps(last_result, sort_keys=True).lower())

        self.assertTrue(replay["audit_replay_available"])
        self.assertEqual(replay["run_history_status"], "available")
        self.assertEqual(replay["replay_statement"], "No synthetic replay is labeled as real evidence.")

        self.assertEqual(operator_states["fixture_mode"]["state"], "fixture_mode")
        self.assertEqual(operator_states["query_ready"]["state"], "query_ready")
        self.assertEqual(operator_states["query_ready"]["source"], "query_readiness")
        self.assertEqual(cockpit["blocking_reasons"], [])

    def test_preserved_profile_fails_closed_when_stage_e_record_is_missing(self) -> None:
        _ReadyPreservedBackend.run_pipeline_calls = 0
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_root = self._build_valid_preserved_artifact_root(
                Path(temp_dir),
                profile_id="preserved_es_phase1",
            )
            with patch.dict(os.environ, {"NTB_STAGE_E_LOG_ROOT": str(Path(temp_dir) / ".stage_e")}):
                with patch(
                    "ntb_marimo_console.runtime_modes.PreservedEngineBackend",
                    _NonLoggingPreservedBackend,
                ), patch(
                    "ntb_marimo_console.app.build_trigger_state_results",
                    new=query_ready_trigger_state_results,
                ):
                    shell = build_app_shell_for_profile_id(
                        profile_id="preserved_es_phase1",
                        fixtures_root=artifact_root,
                        model_adapter=_ValidModelAdapter(),
                    )

        # Real produced QUERY_READY allows the gate to admit the query; the test
        # then exercises the Stage E missing failure mode after pipeline execution.
        self.assertEqual(shell["runtime"]["session_state"], "ERROR")
        self.assertFalse(shell["surfaces"]["audit_replay"]["ready"])
        self.assertIn("no persisted Stage E record", shell["surfaces"]["query_action"]["failure_message"])

    def test_preserved_profile_missing_upstream_artifacts_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            with self.assertRaises(RuntimeDataUnavailableError):
                build_app_shell_for_profile_id(
                    profile_id="preserved_es_phase1",
                    fixtures_root=root,
                    model_adapter=_ValidModelAdapter(),
                )

    def test_preserved_profile_rejects_legacy_fixture_packet_shapes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_root = FIXTURES_ROOT
            artifact_root = Path(temp_dir) / "phase1"
            shutil.copytree(source_root, artifact_root)
            legacy_bundle = {
                "session_date": "2026-03-25",
                "packets": {"ES": {"contract": "ES", "timestamp": "2026-03-25T09:35:00-04:00"}},
                "extensions": {"ES": {}},
                "challenge_state": {"account_balance": 100000.0},
            }
            legacy_query = {
                "market_packet": {"contract": "ES", "timestamp": "2026-03-25T09:35:00-04:00"}
            }
            (artifact_root / "pipeline" / "ES" / "packet_bundle.watchman.json").write_text(
                json.dumps(legacy_bundle, indent=2),
                encoding="utf-8",
            )
            (artifact_root / "pipeline" / "ES" / "historical_packet.query.json").write_text(
                json.dumps(legacy_query, indent=2),
                encoding="utf-8",
            )

            with self.assertRaises(RuntimeDataUnavailableError):
                build_app_shell_for_profile_id(
                    profile_id="preserved_es_phase1",
                    fixtures_root=artifact_root,
                    model_adapter=_ValidModelAdapter(),
                )


class PreservedEngineBackendRoutingTests(unittest.TestCase):
    def test_routing_uses_allowed_facade_methods_only(self) -> None:
        calls: list[str] = []

        def sweep_watchman(packet_bundle: dict[str, object], readiness_trigger: dict[str, object]) -> dict[str, SimpleNamespace]:
            calls.append("sweep_watchman")
            return {
                "ES": SimpleNamespace(
                    contract="ES",
                    hard_lockout_flags=[],
                    awareness_flags=[],
                    missing_inputs=[],
                )
            }

        def run_pipeline(
            packet: dict[str, object],
            contract: str,
            *,
            model_adapter: object,
            evaluation_timestamp_iso: str | None = None,
        ) -> object:
            calls.append("run_pipeline")
            self.assertTrue(callable(getattr(model_adapter, "generate_structured", None)))
            return {"ok": True}

        def summarize_pipeline_result(result: object) -> dict[str, object]:
            calls.append("summarize_pipeline_result")
            return {
                "contract": "ES",
                "termination_stage": "contract_market_read",
                "final_decision": "NO_TRADE",
                "sufficiency_gate_status": "READY",
                "contract_analysis_outcome": "NO_TRADE",
                "proposed_setup_outcome": None,
                "risk_authorization_decision": None,
            }

        fake_facade = types.SimpleNamespace(
            sweep_watchman=sweep_watchman,
            run_pipeline=run_pipeline,
            summarize_pipeline_result=summarize_pipeline_result,
        )
        fake_module = types.SimpleNamespace(execution_facade=fake_facade)

        previous = sys.modules.get("ninjatradebuilder")
        sys.modules["ninjatradebuilder"] = fake_module
        try:
            backend = PreservedEngineBackend(model_adapter=_ValidModelAdapter())
            contexts = backend.sweep_watchman(
                WatchmanSweepRequest(
                    packet_bundle={"packets": {}},
                    readiness_trigger={"trigger_family": "price_level_touch"},
                )
            )
            result = backend.run_pipeline(
                PipelineQueryRequest(contract="ES", packet={"market_packet": {"contract": "ES"}})
            )
            summary = backend.summarize_pipeline_result(result)
        finally:
            if previous is None:
                del sys.modules["ninjatradebuilder"]
            else:
                sys.modules["ninjatradebuilder"] = previous

        self.assertIn("ES", contexts)
        self.assertEqual(summary["final_decision"], "NO_TRADE")
        self.assertEqual(calls, ["sweep_watchman", "run_pipeline", "summarize_pipeline_result"])


if __name__ == "__main__":
    unittest.main()
