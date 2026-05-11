from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import ntb_marimo_console.app as app_module
from ntb_marimo_console.adapters.contracts import PipelineQueryRequest, PipelineSummary, TriggerEvaluation
from ntb_marimo_console.adapters.trigger_evaluator import TriggerEvaluationBundle
from ntb_marimo_console.app import build_phase1_payload
from ntb_marimo_console.demo_fixture_runtime import build_es_runtime_inputs, build_phase1_dependencies
from ntb_marimo_console.trigger_state import TriggerState, TriggerStateResult


FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "golden" / "phase1"


class _Backend:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def sweep_watchman(self, request: object) -> dict[str, SimpleNamespace]:
        self.calls.append("sweep_watchman")
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
        self.calls.append("run_pipeline")
        return {"ok": True, "contract": request.contract}

    def summarize_pipeline_result(self, result: object) -> PipelineSummary:
        self.calls.append("summarize_pipeline_result")
        return {
            "contract": "ES",
            "termination_stage": "stage_d",
            "final_decision": "NO_TRADE",
            "sufficiency_gate_status": "PASS",
            "contract_analysis_outcome": "complete",
            "proposed_setup_outcome": "complete",
            "risk_authorization_decision": "NO_TRADE",
        }

    def narrate_pipeline_result(self, result: object) -> dict[str, object]:
        self.calls.append("narrate_pipeline_result")
        return {
            "contract_analysis": None,
            "proposed_setup": None,
            "risk_authorization": None,
        }


class _FalseDisplayEvaluator:
    def evaluate(self, trigger_specs: list[object], live_snapshot: dict[str, object]) -> TriggerEvaluationBundle:
        return TriggerEvaluationBundle(
            evaluations=tuple(
                TriggerEvaluation(
                    trigger_id=getattr(spec, "id"),
                    is_valid=True,
                    is_true=False,
                    missing_fields=(),
                    invalid_reasons=(),
                )
                for spec in trigger_specs
            )
        )


def test_display_trigger_truth_does_not_enable_pipeline_query_without_query_ready_trigger_state() -> None:
    backend = _Backend()
    artifacts = build_phase1_payload(
        backend=backend,
        inputs=build_es_runtime_inputs(FIXTURES_ROOT),
        dependencies=build_phase1_dependencies(FIXTURES_ROOT),
        query_action_requested=True,
    )

    assert artifacts.pipeline_query_gate.enabled is False
    assert artifacts.pipeline_query_gate.trigger_state == "TOUCHED"
    assert "trigger_state_not_query_ready:TOUCHED" in artifacts.pipeline_query_gate.disabled_reasons
    assert "bar_state_required_for_confirmation" in artifacts.pipeline_query_gate.disabled_reasons
    assert artifacts.workflow_status.query_action_status == "FAILED"
    assert backend.calls == ["sweep_watchman"]


def test_real_query_ready_trigger_state_enables_pipeline_even_when_display_rows_are_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _Backend()
    dependencies = build_phase1_dependencies(FIXTURES_ROOT)
    dependencies.trigger_evaluator = _FalseDisplayEvaluator()  # type: ignore[assignment]

    monkeypatch.setattr(
        app_module,
        "build_trigger_state_results",
        lambda request: (_trigger_result("ES", TriggerState.QUERY_READY),),
    )

    artifacts = build_phase1_payload(
        backend=backend,
        inputs=build_es_runtime_inputs(FIXTURES_ROOT),
        dependencies=dependencies,
        query_action_requested=True,
    )

    assert artifacts.pipeline_query_gate.enabled is True
    assert artifacts.pipeline_query_gate.trigger_state == "QUERY_READY"
    assert artifacts.workflow_status.query_action_status == "COMPLETED"
    assert artifacts.payload.trigger_rows[0].is_true is False
    assert backend.calls == [
        "sweep_watchman",
        "run_pipeline",
        "summarize_pipeline_result",
        "narrate_pipeline_result",
    ]


def _trigger_result(contract: str, state: TriggerState) -> TriggerStateResult:
    return TriggerStateResult(
        contract=contract,
        setup_id=f"{contract.lower()}_setup_1",
        trigger_id=f"{contract.lower()}_trigger_acceptance",
        state=state,
        distance_to_trigger_ticks=0.0 if state == TriggerState.QUERY_READY else None,
        required_fields=("market.current_price",),
        missing_fields=(),
        invalid_reasons=(),
        blocking_reasons=(),
        last_updated="2026-03-25T09:35:00-04:00",
    )
