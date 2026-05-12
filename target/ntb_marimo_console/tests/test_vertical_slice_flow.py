from __future__ import annotations

import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ntb_marimo_console.app import build_phase1_app
from ntb_marimo_console.adapters.contracts import (
    OperatorRuntimeInputs,
    PipelineBackend,
    PipelineQueryRequest,
    PipelineSummary,
    RuntimeSelection,
    SessionTarget,
    WatchmanSweepRequest,
)
from ntb_marimo_console.demo_fixture_runtime import build_es_runtime_inputs, build_phase1_dependencies

from tests._query_ready_producer import query_ready_trigger_state_results as _query_ready_trigger_state_results


class _FakeBackend(PipelineBackend):
    def __init__(self, *, lockout: bool, summary: PipelineSummary) -> None:
        self.lockout = lockout
        self.summary = summary
        self.calls: list[str] = []

    def sweep_watchman(
        self,
        request: WatchmanSweepRequest,
    ) -> dict[str, SimpleNamespace]:
        self.calls.append("sweep_watchman")
        return {
            "ES": SimpleNamespace(
                contract="ES",
                event_risk_state="lockout_active" if self.lockout else "clear",
                vwap_posture_state="price_above_vwap",
                value_location_state="inside_value",
                level_proximity_state="clear_of_structure",
                hard_lockout_flags=["event_lockout"] if self.lockout else [],
                awareness_flags=[],
                missing_inputs=[],
            )
        }

    def run_pipeline(self, request: PipelineQueryRequest) -> object:
        self.calls.append("run_pipeline")
        return {"ok": True}

    def summarize_pipeline_result(self, result: object) -> PipelineSummary:
        self.calls.append("summarize_pipeline_result")
        return self.summary

    def narrate_pipeline_result(self, result: object) -> dict[str, object]:
        self.calls.append("narrate_pipeline_result")
        return {
            "contract_analysis": None,
            "proposed_setup": None,
            "risk_authorization": None,
        }


class _MissingWatchmanBackend(_FakeBackend):
    def sweep_watchman(
        self,
        request: WatchmanSweepRequest,
    ) -> dict[str, SimpleNamespace]:
        self.calls.append("sweep_watchman")
        return {}


class _FailingPipelineBackend(_FakeBackend):
    def run_pipeline(self, request: PipelineQueryRequest) -> object:
        self.calls.append("run_pipeline")
        raise RuntimeError("pipeline exploded")


class VerticalSliceFlowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixtures_root = Path("fixtures/golden/phase1")
        self.dependencies = build_phase1_dependencies(self.fixtures_root)
        self.true_snapshot = self._load_json(
            self.fixtures_root / "observables" / "ES" / "trigger_true.json"
        )
        self.false_snapshot = self._load_json(
            self.fixtures_root / "observables" / "ES" / "trigger_false.json"
        )
        self.summary_no_trade = self._load_json(
            self.fixtures_root / "pipeline" / "ES" / "pipeline_result.no_trade.json"
        )
        self.base_inputs = build_es_runtime_inputs(self.fixtures_root)

    def test_es_happy_path_executes_pipeline_and_renders_stage_trace(self) -> None:
        backend = _FakeBackend(lockout=False, summary=self.summary_no_trade)
        with patch(
            "ntb_marimo_console.app.build_trigger_state_results",
            new=_query_ready_trigger_state_results,
        ):
            app = build_phase1_app(backend=backend, inputs=self.base_inputs, dependencies=self.dependencies)

        surfaces = app["surfaces"]
        self.assertTrue(surfaces["query_action"]["query_enabled"])
        self.assertEqual(surfaces["query_action"]["pipeline_query_gate"]["trigger_state"], "QUERY_READY")
        self.assertTrue(surfaces["query_action"]["pipeline_query_gate"]["trigger_state_from_real_producer"])
        self.assertTrue(surfaces["decision_review"]["has_result"])
        self.assertTrue(surfaces["decision_review"]["ready"])
        self.assertEqual(surfaces["decision_review"]["final_decision"], "NO_TRADE")
        self.assertIn("audit_replay", surfaces)
        self.assertFalse(surfaces["audit_replay"]["stage_e_live_backend"])
        self.assertTrue(surfaces["audit_replay"]["ready"])
        self.assertEqual(app["runtime"]["session_state"], "AUDIT_REPLAY_READY")
        self.assertIn("STARTUP_READY", app["runtime"]["state_history"])
        self.assertIn("QUERY_ACTION_REQUESTED", app["runtime"]["state_history"])
        self.assertIn("QUERY_ACTION_COMPLETED", app["runtime"]["state_history"])
        self.assertIn("DECISION_REVIEW_READY", app["runtime"]["state_history"])
        self.assertEqual(
            backend.calls,
            [
                "sweep_watchman",
                "run_pipeline",
                "summarize_pipeline_result",
                "narrate_pipeline_result",
            ],
        )

    def test_ready_path_without_query_request_stays_live_query_eligible(self) -> None:
        backend = _FakeBackend(lockout=False, summary=self.summary_no_trade)
        with patch(
            "ntb_marimo_console.app.build_trigger_state_results",
            new=_query_ready_trigger_state_results,
        ):
            app = build_phase1_app(
                backend=backend,
                inputs=self.base_inputs,
                dependencies=self.dependencies,
                query_action_requested=False,
            )

        surfaces = app["surfaces"]
        self.assertTrue(surfaces["query_action"]["query_enabled"])
        self.assertTrue(surfaces["query_action"]["action_available"])
        self.assertEqual(surfaces["query_action"]["query_action_status"], "AVAILABLE")
        self.assertFalse(surfaces["decision_review"]["ready"])
        self.assertFalse(surfaces["audit_replay"]["ready"])
        self.assertEqual(app["runtime"]["session_state"], "LIVE_QUERY_ELIGIBLE")
        self.assertEqual(backend.calls, ["sweep_watchman"])

    def test_lockout_path_disables_query_and_skips_pipeline(self) -> None:
        backend = _FakeBackend(lockout=True, summary=self.summary_no_trade)
        app = build_phase1_app(
            backend=backend,
            inputs=self.base_inputs,
            dependencies=self.dependencies,
            query_action_requested=False,
        )

        surfaces = app["surfaces"]
        self.assertFalse(surfaces["query_action"]["query_enabled"])
        self.assertEqual(surfaces["query_action"]["query_action_status"], "BLOCKED")
        self.assertFalse(surfaces["decision_review"]["has_result"])
        self.assertFalse(surfaces["decision_review"]["ready"])
        self.assertFalse(surfaces["audit_replay"]["ready"])
        self.assertEqual(app["runtime"]["session_state"], "LIVE_QUERY_BLOCKED")
        self.assertIn("LIVE_QUERY_BLOCKED", app["runtime"]["state_history"])
        self.assertEqual(backend.calls, ["sweep_watchman"])

    def test_default_fixture_path_fails_closed_because_real_trigger_state_is_not_query_ready(self) -> None:
        """Default fixture inputs produce TOUCHED, not QUERY_READY; the R13 gate must stay disabled."""

        backend = _FakeBackend(lockout=False, summary=self.summary_no_trade)
        app = build_phase1_app(
            backend=backend,
            inputs=self.base_inputs,
            dependencies=self.dependencies,
            query_action_requested=False,
        )

        surfaces = app["surfaces"]
        gate = surfaces["query_action"]["pipeline_query_gate"]
        self.assertFalse(surfaces["query_action"]["query_enabled"])
        self.assertEqual(gate["trigger_state"], "TOUCHED")
        self.assertTrue(gate["trigger_state_from_real_producer"])
        self.assertIn("trigger_state_not_query_ready:TOUCHED", gate["disabled_reasons"])
        self.assertEqual(backend.calls, ["sweep_watchman"])

    def test_missing_watchman_context_fails_closed(self) -> None:
        backend = _MissingWatchmanBackend(lockout=False, summary=self.summary_no_trade)

        with self.assertRaises(ValueError):
            build_phase1_app(backend=backend, inputs=self.base_inputs, dependencies=self.dependencies)

    def test_query_action_failure_is_explicit_and_fail_closed(self) -> None:
        backend = _FailingPipelineBackend(lockout=False, summary=self.summary_no_trade)

        with patch(
            "ntb_marimo_console.app.build_trigger_state_results",
            new=_query_ready_trigger_state_results,
        ):
            app = build_phase1_app(
                backend=backend,
                inputs=self.base_inputs,
                dependencies=self.dependencies,
                query_action_requested=True,
            )

        surfaces = app["surfaces"]
        self.assertEqual(surfaces["query_action"]["query_action_status"], "FAILED")
        self.assertIn("pipeline exploded", surfaces["query_action"]["failure_message"])
        self.assertFalse(surfaces["decision_review"]["ready"])
        self.assertFalse(surfaces["audit_replay"]["ready"])
        self.assertEqual(app["runtime"]["session_state"], "QUERY_ACTION_FAILED")
        self.assertIn("QUERY_ACTION_REQUESTED", app["runtime"]["state_history"])
        self.assertIn("QUERY_ACTION_FAILED", app["runtime"]["state_history"])

    def test_payload_contract_rejects_query_contract_mismatch(self) -> None:
        backend = _FakeBackend(lockout=False, summary=self.summary_no_trade)
        inputs = OperatorRuntimeInputs(
            selection=RuntimeSelection(
                mode="fixture_demo",
                profile_id="fixture_es_demo",
                session=SessionTarget(contract="ES", session_date="2026-03-25"),
            ),
            premarket=WatchmanSweepRequest(
                packet_bundle={"shared": {}, "contracts": {"ES": {}}},
                readiness_trigger={"trigger_family": "price_level_touch", "price_level": 1.0},
            ),
            live_snapshot=self.false_snapshot,
            pipeline_query=PipelineQueryRequest(
                contract="NQ",
                packet=self._load_json(self.fixtures_root / "pipeline" / "ES" / "historical_packet.query.json"),
            ),
        )

        with self.assertRaises(ValueError):
            build_phase1_app(backend=backend, inputs=inputs, dependencies=self.dependencies)

    def test_payload_contract_rejects_snapshot_contract_mismatch(self) -> None:
        backend = _FakeBackend(lockout=False, summary=self.summary_no_trade)
        bad_snapshot = dict(self.true_snapshot)
        bad_snapshot["contract"] = "NQ"
        inputs = OperatorRuntimeInputs(
            selection=self.base_inputs.selection,
            premarket=self.base_inputs.premarket,
            live_snapshot=bad_snapshot,
            pipeline_query=self.base_inputs.pipeline_query,
        )

        with self.assertRaises(ValueError):
            build_phase1_app(backend=backend, inputs=inputs, dependencies=self.dependencies)

    def test_premarket_artifacts_must_match_selected_session_date(self) -> None:
        backend = _FakeBackend(lockout=False, summary=self.summary_no_trade)
        inputs = OperatorRuntimeInputs(
            selection=RuntimeSelection(
                mode="fixture_demo",
                profile_id="fixture_es_demo",
                session=SessionTarget(contract="ES", session_date="2026-03-26"),
            ),
            premarket=self.base_inputs.premarket,
            live_snapshot=self.base_inputs.live_snapshot,
            pipeline_query=self.base_inputs.pipeline_query,
        )

        with self.assertRaises(ValueError):
            build_phase1_app(backend=backend, inputs=inputs, dependencies=self.dependencies)

    @staticmethod
    def _load_json(path: Path) -> dict[str, object]:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise ValueError(f"Expected object JSON at {path}")
        return data


if __name__ == "__main__":
    unittest.main()
