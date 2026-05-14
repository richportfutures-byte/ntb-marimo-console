from __future__ import annotations

import json

from ntb_marimo_console.adapters.contracts import PipelineQueryRequest
from ntb_marimo_console.cockpit_manual_query import (
    no_cockpit_manual_query_result,
    submit_cockpit_manual_query,
    supported_cockpit_query_contracts,
)


class RecordingBackend:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def sweep_watchman(self, request: object) -> dict[str, object]:
        self.calls.append("sweep_watchman")
        return {}

    def run_pipeline(self, request: PipelineQueryRequest) -> object:
        self.calls.append("run_pipeline")
        return {"contract": request.contract, "status": "fixture_result"}

    def summarize_pipeline_result(self, result: object) -> dict[str, object]:
        self.calls.append("summarize_pipeline_result")
        return {
            "contract": "ES",
            "termination_stage": "stage_b",
            "final_decision": "NO_TRADE",
            "sufficiency_gate_status": "READY",
            "contract_analysis_outcome": "NO_TRADE",
            "proposed_setup_outcome": None,
            "risk_authorization_decision": None,
        }

    def narrate_pipeline_result(self, result: object) -> dict[str, object]:
        self.calls.append("narrate_pipeline_result")
        return {
            "contract_analysis": None,
            "proposed_setup": None,
            "risk_authorization": None,
        }


def test_eligible_manual_query_calls_pipeline_backend_boundary() -> None:
    backend = RecordingBackend()

    result = submit_cockpit_manual_query(
        contract="ES",
        action_rows=(_row("ES", "ENABLED"),),
        backend=backend,
        pipeline_query=_query("ES"),
        submitted_at="2026-05-06T14:00:00+00:00",
    )

    assert result.to_dict() == {
        "schema": "cockpit_manual_query_result_v1",
        "contract": "ES",
        "request_status": "SUBMITTED",
        "submitted": True,
        "submitted_at": "2026-05-06T14:00:00+00:00",
        "gate_provenance_basis": "real_trigger_state_result_and_pipeline_gate",
        "pipeline_result_status": "completed",
        "terminal_summary": "NO_TRADE",
        "stage_termination_reason": "stage_b",
        "blocked_reason": None,
        "query_action_state": "ENABLED",
        "query_action_text": "Manual query submitted; preserved pipeline returned a bounded result.",
        "pipeline_boundary": "PipelineBackend",
        "decision_authority": "preserved_engine_only",
        "manual_query_only": True,
        "manual_execution_only": True,
        "raw_quote_values_included": False,
        "raw_bar_values_included": False,
        "raw_streamer_payloads_included": False,
    }
    assert backend.calls == [
        "run_pipeline",
        "summarize_pipeline_result",
        "narrate_pipeline_result",
    ]


def test_blocked_manual_query_does_not_call_pipeline_backend() -> None:
    backend = RecordingBackend()

    result = submit_cockpit_manual_query(
        contract="NQ",
        action_rows=(_row("NQ", "DISABLED", reason="Manual query blocked: chart bars are missing for NQ."),),
        backend=backend,
        pipeline_query=_query("NQ"),
        submitted_at="2026-05-06T14:00:00+00:00",
    )

    assert result.submitted is False
    assert result.request_status == "BLOCKED"
    assert result.pipeline_result_status == "not_submitted"
    assert result.blocked_reason == "Manual query blocked: chart bars are missing for NQ."
    assert backend.calls == []


def test_manual_query_rejects_unsupported_and_excluded_contracts() -> None:
    for contract in ("ZN", "GC"):
        backend = RecordingBackend()
        result = submit_cockpit_manual_query(
            contract=contract,
            action_rows=(),
            backend=backend,
            pipeline_query=_query("ES"),
            submitted_at="2026-05-06T14:00:00+00:00",
        )

        assert result.submitted is False
        assert result.request_status == "BLOCKED"
        assert "not a supported cockpit query contract" in str(result.blocked_reason)
        assert backend.calls == []


def test_manual_query_requires_existing_gate_provenance_not_display_state() -> None:
    backend = RecordingBackend()
    display_only_row = _row("ES", "ENABLED")
    display_only_row["query_action_provenance"] = "unavailable_not_inferred_from_display_or_raw_enabled_mapping"

    result = submit_cockpit_manual_query(
        contract="ES",
        action_rows=(display_only_row,),
        backend=backend,
        pipeline_query=_query("ES"),
        submitted_at="2026-05-06T14:00:00+00:00",
    )

    assert result.submitted is False
    assert result.request_status == "BLOCKED"
    assert result.blocked_reason == "Manual query blocked: QUERY_READY provenance is not verified."
    assert backend.calls == []


def test_manual_query_result_excludes_raw_market_payload_values() -> None:
    backend = RecordingBackend()

    result = submit_cockpit_manual_query(
        contract="ES",
        action_rows=(_row("ES", "ENABLED"),),
        backend=backend,
        pipeline_query=_query("ES"),
        submitted_at="2026-05-06T14:00:00+00:00",
    ).to_dict()
    rendered = json.dumps(result, sort_keys=True)

    assert "7175.25" not in rendered
    assert "raw streamer payload" not in rendered.lower()
    assert "ACCESS_VALUE_PRIVATE" not in rendered


def test_no_query_submitted_status_is_explicit_and_supported_contracts_are_final_five() -> None:
    result = no_cockpit_manual_query_result("MGC")

    assert supported_cockpit_query_contracts() == ("ES", "NQ", "CL", "6E", "MGC")
    assert result["contract"] == "MGC"
    assert result["request_status"] == "NOT_SUBMITTED"
    assert result["submitted"] is False
    assert result["pipeline_result_status"] == "not_submitted"


def _query(contract: str) -> PipelineQueryRequest:
    return PipelineQueryRequest(
        contract=contract,  # type: ignore[arg-type]
        packet={"contract": contract},
        evaluation_timestamp_iso="2026-05-06T14:00:00+00:00",
        readiness_trigger={"trigger_family": "fixture"},
    )


def _row(contract: str, state: str, *, reason: str | None = None) -> dict[str, object]:
    return {
        "contract": contract,
        "query_action_state": state,
        "query_action_text": "Manual query available" if state == "ENABLED" else "Manual query blocked.",
        "query_disabled_reason": reason,
        "query_action_provenance": (
            "real_trigger_state_result_and_pipeline_gate"
            if state == "ENABLED"
            else "unavailable_not_inferred_from_display_or_raw_enabled_mapping"
        ),
        "query_action_source": "existing_pipeline_gate_provenance",
        "query_gate_contract": contract,
    }
