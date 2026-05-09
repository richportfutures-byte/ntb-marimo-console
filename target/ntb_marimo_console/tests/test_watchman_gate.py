from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ntb_marimo_console.app import Phase1AppDependencies, build_phase1_app
from ntb_marimo_console.adapters.contracts import (
    AuditReplayRecord,
    PipelineBackend,
    PipelineQueryRequest,
    PipelineSummary,
    PreMarketArtifacts,
    SessionTarget,
    WatchmanSweepRequest,
)
from ntb_marimo_console.demo_fixture_runtime import build_es_runtime_inputs, build_phase1_dependencies
from ntb_marimo_console.launch_config import build_startup_artifacts_from_env
from ntb_marimo_console.watchman_gate import (
    build_watchman_gate_markdown,
    build_watchman_gate_payload,
    validate_watchman_brief,
    watchman_gate_requires_stop,
)


class _StaticPreMarketStore:
    def __init__(self, *, packet: dict[str, object], brief: dict[str, object]) -> None:
        self._artifacts = PreMarketArtifacts(packet=packet, brief=brief)

    def load(self, session: SessionTarget) -> PreMarketArtifacts:
        return self._artifacts


class _StaticRunHistoryStore:
    def list_rows(self, session: SessionTarget) -> list[dict[str, object]]:
        return [
            {
                "run_id": "fixture-row",
                "logged_at": "2026-03-25T09:35:00-04:00",
                "contract": session.contract,
                "run_type": "pipeline",
                "final_decision": "NO_TRADE",
                "termination_stage": "contract_market_read",
                "stage_d_decision": None,
                "notes": "fixture row",
            }
        ]


class _StaticAuditReplayStore:
    def load_replay(self, session: SessionTarget) -> AuditReplayRecord:
        return {
            "source": "fixture_backed",
            "stage_e_live_backend": False,
            "replay_available": True,
            "last_run_id": "fixture-row",
            "last_final_decision": "NO_TRADE",
        }


class _ReadyWatchmanBackend(PipelineBackend):
    def sweep_watchman(
        self,
        request: WatchmanSweepRequest,
    ) -> dict[str, SimpleNamespace]:
        return {
            "ES": SimpleNamespace(
                contract="ES",
                event_risk_state="clear",
                vwap_posture_state="price_above_vwap",
                value_location_state="inside_value",
                level_proximity_state="clear_of_structure",
                hard_lockout_flags=[],
                awareness_flags=[],
                missing_inputs=[],
            )
        }

    def run_pipeline(self, request: PipelineQueryRequest) -> object:
        return {"ok": True}

    def summarize_pipeline_result(self, result: object) -> PipelineSummary:
        return {
            "contract": "ES",
            "termination_stage": "contract_market_read",
            "final_decision": "NO_TRADE",
            "sufficiency_gate_status": "READY",
            "contract_analysis_outcome": "NO_TRADE",
            "proposed_setup_outcome": None,
            "risk_authorization_decision": None,
        }


class WatchmanGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.fixtures_root = Path("fixtures/golden/phase1")
        self.inputs = build_es_runtime_inputs(self.fixtures_root)
        packet = self._load_json(
            self.fixtures_root / "premarket" / "ES" / "2026-03-25" / "premarket_packet.json"
        )
        brief = self._load_json(
            self.fixtures_root / "premarket" / "ES" / "2026-03-25" / "premarket_brief.ready.json"
        )
        brief["structural_setups"][0].pop("description", None)
        brief["status"] = "READY"
        fixture_dependencies = build_phase1_dependencies(self.fixtures_root)
        self.dependencies = Phase1AppDependencies(
            premarket_store=_StaticPreMarketStore(packet=packet, brief=brief),
            run_history_store=_StaticRunHistoryStore(),
            audit_replay_store=_StaticAuditReplayStore(),
            trigger_evaluator=fixture_dependencies.trigger_evaluator,
        )

    def test_missing_narrative_substance_returns_needs_review(self) -> None:
        brief = self.dependencies.premarket_store.load(self.inputs.selection.session).brief
        result = validate_watchman_brief(brief)

        self.assertEqual(result.status, "NEEDS_REVIEW")
        self.assertIn("narrative_substance_present", result.failing_validators)
        self.assertFalse(result.pipeline_gate_open)

    def test_manual_ready_status_cannot_bypass_validator_gate(self) -> None:
        shell = build_phase1_app(
            backend=_ReadyWatchmanBackend(),
            inputs=self.inputs,
            dependencies=self.dependencies,
            query_action_requested=False,
        )

        self.assertEqual(shell["watchman_gate"]["validator_status"], "NEEDS_REVIEW")
        self.assertFalse(shell["watchman_gate"]["pipeline_gate_open"])
        self.assertFalse(shell["surfaces"]["query_action"]["query_enabled"])
        self.assertEqual(shell["workflow"]["query_action_status"], "BLOCKED")
        self.assertEqual(shell["runtime"]["session_state"], "LIVE_QUERY_BLOCKED")

    def test_gate_stop_reads_validator_output_only(self) -> None:
        shell = build_phase1_app(
            backend=_ReadyWatchmanBackend(),
            inputs=self.inputs,
            dependencies=self.dependencies,
            query_action_requested=False,
        )

        shell["surfaces"]["pre_market_brief"]["status"] = "READY"
        self.assertTrue(watchman_gate_requires_stop(shell))

        gate_markdown = build_watchman_gate_markdown(shell["watchman_gate"])
        self.assertIn("Validator Status: `NEEDS_REVIEW`", gate_markdown)
        self.assertIn("narrative_substance_present", gate_markdown)

    def test_startup_path_carries_watchman_gate_into_shell(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_root = Path(temp_dir) / "phase1"
            shutil.copytree(self.fixtures_root, artifact_root)
            brief_path = artifact_root / "premarket" / "ES" / "2026-03-25" / "premarket_brief.ready.json"
            brief = self._load_json(brief_path)
            brief["structural_setups"][0].pop("description", None)
            brief["status"] = "READY"
            brief_path.write_text(json.dumps(brief, indent=2) + "\n", encoding="utf-8")

            with patch.dict(
                os.environ,
                {
                    "NTB_CONSOLE_PROFILE": "fixture_es_demo",
                    "NTB_FIXTURES_ROOT": str(artifact_root),
                },
                clear=True,
            ):
                startup = build_startup_artifacts_from_env()

        self.assertTrue(startup.ready)
        self.assertEqual(startup.shell["watchman_gate"]["validator_status"], "NEEDS_REVIEW")
        self.assertFalse(startup.shell["watchman_gate"]["pipeline_gate_open"])
        self.assertEqual(startup.shell["workflow"]["query_action_status"], "BLOCKED")
        self.assertEqual(startup.shell["runtime"]["session_state"], "LIVE_QUERY_BLOCKED")

    def test_operator_entrypoint_contains_real_mo_stop_gate(self) -> None:
        source = Path("src/ntb_marimo_console/operator_console_app.py").read_text(encoding="utf-8")

        self.assertIn("mo.stop(", source)
        self.assertIn("render_watchman_gate_stop_output", source)

    @staticmethod
    def _load_json(path: Path) -> dict[str, object]:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if not isinstance(payload, dict):
            raise ValueError(f"Expected object JSON at {path}")
        return payload


class WatchmanGatePayloadTests(unittest.TestCase):
    def test_payload_marks_ready_only_when_validator_authorizes(self) -> None:
        result = validate_watchman_brief(
            {
                "contract": "ES",
                "session_date": "2026-03-25",
                "version": "live_thesis_brief_v1",
                "structural_setups": [
                    {
                        "id": "es_setup_test",
                        "description": "Narrative substance",
                        "required_live_fields": ["market.current_price"],
                        "warnings": ["Keep the test brief blocked if the price condition is missing."],
                        "query_triggers": [
                            {
                                "id": "es_trigger_test",
                                "description": "Trigger when the fixture price reaches the test level.",
                                "observable_conditions": ["market.current_price >= 5604"],
                                "fields_used": ["market.current_price"],
                                "required_live_fields": ["market.current_price"],
                                "invalidators": [
                                    {
                                        "id": "es_test_price_failure",
                                        "condition": "market.current_price < 5604",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        )

        payload = build_watchman_gate_payload(result)
        self.assertEqual(payload["validator_status"], "READY")
        self.assertTrue(payload["pipeline_gate_open"])


if __name__ == "__main__":
    unittest.main()
