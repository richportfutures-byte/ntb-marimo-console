from __future__ import annotations

import json

import pytest

from ntb_marimo_console.contract_universe import final_target_contracts
from ntb_marimo_console.evidence_replay import EVIDENCE_REPLAY_SCHEMA, build_replay_summary, create_evidence_event
from ntb_marimo_console.operator_workspace import (
    OPERATOR_WORKSPACE_SCHEMA,
    R14_COCKPIT_SCHEMA,
    OperatorWorkspaceRequest,
    build_r14_cockpit_view_model,
    build_operator_workspace_view_model,
)
from ntb_marimo_console.pipeline_query_gate import PipelineQueryGateRequest, evaluate_pipeline_query_gate
from ntb_marimo_console.runtime_modes import build_es_app_shell_for_mode
from ntb_marimo_console.trigger_state import TriggerState, TriggerStateResult
from ntb_marimo_console.viewmodels.models import TriggerStatusVM
from ntb_marimo_console.trigger_transition_evidence import build_trigger_transition_evidence_events


SENSITIVE_VALUES = (
    "ACCESS_VALUE_PRIVATE",
    "REFRESH_VALUE_PRIVATE",
    "BEARER_VALUE_PRIVATE",
    "CUSTOMER_VALUE_PRIVATE",
    "CORREL_VALUE_PRIVATE",
    "ACCOUNT_VALUE_PRIVATE",
    "stream-redaction",
)
FORBIDDEN_KEYS = (
    "trade_authorized",
    "broker_authorized",
    "order_authorized",
    "account_authorized",
    "fill_authorized",
    "pnl_authorized",
    "broker",
    "order",
    "account",
    "fill",
    "pnl",
    "risk_authorization_decision",
)


@pytest.mark.parametrize("contract", ("ES", "NQ", "CL", "6E", "MGC"))
def test_supported_contracts_build_operator_workspace_models(contract: str) -> None:
    workspace = ready_workspace(contract).to_dict()

    assert workspace["schema"] == OPERATOR_WORKSPACE_SCHEMA
    assert workspace["header"]["contract"] == contract
    assert workspace["header"]["final_support_status"] == "final_supported"
    assert workspace["pipeline_gate"]["gate_enabled"] is True
    assert workspace["pipeline_gate"]["manual_query_allowed"] is True
    assert contract in final_target_contracts()


@pytest.mark.parametrize(
    ("contract", "support_status"),
    (
        ("ZN", "excluded"),
        ("GC", "never_supported_excluded"),
    ),
)
def test_excluded_contracts_do_not_appear_as_final_supported_operator_targets(
    contract: str,
    support_status: str,
) -> None:
    workspace = ready_workspace(contract).to_dict()

    assert workspace["header"]["contract"] == contract
    assert workspace["header"]["final_support_status"] == support_status
    assert workspace["pipeline_gate"]["manual_query_allowed"] is False
    assert "contract_final_supported" in workspace["pipeline_gate"]["missing_conditions"]
    assert contract not in final_target_contracts()
    assert workspace["header"]["contract"] != "MGC"


def test_gc_is_excluded_and_never_described_as_mgc() -> None:
    workspace = ready_workspace("GC").to_dict()
    rendered = json.dumps(workspace, sort_keys=True)

    assert workspace["header"]["contract"] == "GC"
    assert workspace["header"]["final_support_status"] == "never_supported_excluded"
    assert "MGC" not in rendered


def test_output_is_json_serializable() -> None:
    payload = ready_workspace("ES").to_dict()

    encoded = json.dumps(payload, sort_keys=True)
    decoded = json.loads(encoded)

    assert decoded["schema"] == OPERATOR_WORKSPACE_SCHEMA
    assert decoded["header"]["contract"] == "ES"


def test_header_contains_required_operator_fields() -> None:
    header = ready_workspace("NQ").to_dict()["header"]

    assert header == {
        "contract": "NQ",
        "profile_id": "preserved_nq_phase1",
        "final_support_status": "final_supported",
        "provider_status": "connected",
        "stream_status": "connected",
        "quote_freshness": "fresh",
        "bar_freshness": "fresh",
        "session_status": "valid",
        "event_lockout_status": "inactive",
        "evaluated_at": "2026-05-06T14:00:00+00:00",
    }


def test_premarket_plan_exposes_summaries_without_raw_full_brief_json() -> None:
    plan = ready_workspace("ES").to_dict()["premarket_plan"]

    assert plan["validator_status"] == "READY"
    assert plan["setup_summaries"] == [
        {
            "setup_id": "es_setup_1",
            "summary": "ES fixture setup requires explicit read-model confirmation.",
        }
    ]
    assert plan["trigger_summaries"][0]["trigger_id"] == "es_trigger_1"
    assert plan["trigger_summaries"][0]["summary"] == "Query readiness trigger for ES fixture setup."
    assert "market.current_price" in plan["required_live_fields"]
    assert plan["unavailable_fields"] == [
        {
            "field": "cross_asset.index_cash_tone",
            "reason": "not present in fixture inputs",
            "status": "unavailable_not_inferred",
        }
    ]
    assert "Do not infer unavailable market state." in plan["warnings"]
    assert plan["invalidators"][0]["invalidator_id"] == "es_invalidator_1"
    assert plan["source_context_blockers"] == []
    assert plan["validation_blockers"] == []
    assert plan["raw_brief_json_included"] is False
    assert "structural_setups" not in plan
    assert "source_context" not in plan


def test_live_thesis_section_exposes_trigger_state_fields_and_reasons() -> None:
    workspace = ready_workspace(
        "CL",
        trigger_state=trigger_result(
            "CL",
            TriggerState.BLOCKED,
            missing_fields=("market.cumulative_delta",),
            invalid_reasons=("invalidator_active",),
            blocking_reasons=("missing_required_live_fields",),
        ),
    ).to_dict()
    monitor = workspace["live_thesis_monitor"]

    assert monitor["setup_id"] == "cl_setup_1"
    assert monitor["trigger_id"] == "cl_trigger_1"
    assert monitor["trigger_state"] == "BLOCKED"
    assert monitor["distance_to_trigger_ticks"] is None
    assert monitor["required_fields"] == ["market.current_price", "market.cumulative_delta"]
    assert monitor["missing_fields"] == ["market.cumulative_delta"]
    assert monitor["invalid_reasons"] == ["invalidator_active"]
    assert monitor["blocking_reasons"] == ["missing_required_live_fields"]
    assert monitor["state_flags"]["blocked"] is True
    assert monitor["transition_narrative"]["state_label"] == "BLOCKED"
    assert "missing_required_live_fields" in monitor["transition_narrative"]["blocking_explanation"]
    assert "market.cumulative_delta" in monitor["transition_narrative"]["missing_data_explanation"]


def test_pipeline_gate_section_mirrors_r13_disabled_gate_and_cannot_bypass_it() -> None:
    gate = query_gate("ES", watchman_validator_status="FAILED")
    workspace = ready_workspace("ES", gate=gate).to_dict()
    pipeline_gate = workspace["pipeline_gate"]

    assert gate.enabled is False
    assert pipeline_gate["gate_enabled"] is False
    assert pipeline_gate["manual_query_allowed"] is False
    assert pipeline_gate["disabled_reasons"] == list(gate.disabled_reasons)
    assert "watchman_validator_not_ready:FAILED" in pipeline_gate["blocking_reasons"]


def test_disabled_gate_displays_explicit_text_reasons() -> None:
    gate = query_gate("ES", stream_status="stale", event_lockout_active=True)
    pipeline_gate = ready_workspace("ES", gate=gate).to_dict()["pipeline_gate"]

    assert pipeline_gate["manual_query_allowed"] is False
    assert "stream_status_blocked:stale" in pipeline_gate["blocking_reasons"]
    assert "event_lockout_active" in pipeline_gate["blocking_reasons"]
    assert pipeline_gate["gate_statement"]


def test_enabled_gate_displays_explicit_text_reasons() -> None:
    pipeline_gate = ready_workspace("MGC").to_dict()["pipeline_gate"]

    assert pipeline_gate["manual_query_allowed"] is True
    assert "contract_final_supported" in pipeline_gate["enabled_reasons"]
    assert "trigger_state_query_ready" in pipeline_gate["enabled_reasons"]
    assert pipeline_gate["disabled_reasons"] == []
    assert pipeline_gate["gate_statement"] == (
        "Gate enabled means only that the operator may manually query the preserved Stage A through D pipeline."
    )


def test_pipeline_gate_section_surfaces_selected_contract_setup_trigger_and_producer_origin() -> None:
    gate = query_gate("ES", trigger_state_from_real_producer=True)
    pipeline_gate = ready_workspace("ES", gate=gate).to_dict()["pipeline_gate"]

    assert pipeline_gate["contract"] == "ES"
    assert pipeline_gate["setup_id"] == "es_setup_1"
    assert pipeline_gate["trigger_id"] == "es_trigger_1"
    assert pipeline_gate["trigger_state"] == "QUERY_READY"
    assert pipeline_gate["trigger_state_from_real_producer"] is True


def test_pipeline_gate_section_marks_fallback_producer_when_trigger_state_result_is_synthetic() -> None:
    fallback_trigger = TriggerStateResult(
        contract="ES",
        setup_id=None,
        trigger_id=None,
        state=TriggerState.UNAVAILABLE,
        distance_to_trigger_ticks=None,
        required_fields=(),
        missing_fields=(),
        invalid_reasons=(),
        blocking_reasons=("trigger_state_result_unavailable",),
        last_updated=None,
    )
    gate = query_gate("ES", trigger_state=fallback_trigger, trigger_state_from_real_producer=False)
    pipeline_gate = ready_workspace("ES", gate=gate).to_dict()["pipeline_gate"]

    assert pipeline_gate["manual_query_allowed"] is False
    assert pipeline_gate["trigger_state"] == "UNAVAILABLE"
    assert pipeline_gate["trigger_state_from_real_producer"] is False
    assert "trigger_state_not_query_ready:UNAVAILABLE" in pipeline_gate["blocking_reasons"]


def test_pipeline_gate_section_refuses_raw_enabled_mapping_without_query_ready_provenance() -> None:
    fake_gate = {
        "enabled": True,
        "pipeline_query_authorized": True,
        "contract": "ES",
        "profile_id": "preserved_es_phase1",
        "setup_id": "es_setup_1",
        "trigger_id": "es_trigger_1",
        "trigger_state": "QUERY_READY",
        "trigger_state_from_real_producer": False,
        "enabled_reasons": ["trigger_state_query_ready"],
        "disabled_reasons": [],
        "blocking_reasons": [],
        "required_conditions": ["trigger_state_query_ready"],
        "missing_conditions": [],
        "provider_status": "connected",
        "stream_status": "connected",
        "session_valid": True,
        "event_lockout_active": False,
    }

    pipeline_gate = ready_workspace("ES", gate=fake_gate).to_dict()["pipeline_gate"]

    assert pipeline_gate["gate_enabled"] is False
    assert pipeline_gate["manual_query_allowed"] is False
    assert pipeline_gate["trigger_state"] == "QUERY_READY"
    assert pipeline_gate["trigger_state_from_real_producer"] is False
    assert "pipeline_gate_provenance_not_verified" in pipeline_gate["blocking_reasons"]


def test_query_ready_is_displayed_as_query_readiness_only_not_trade_authorization() -> None:
    monitor = ready_workspace("ES").to_dict()["live_thesis_monitor"]

    assert monitor["trigger_state"] == "QUERY_READY"
    assert "query readiness only" in monitor["query_readiness_statement"]
    assert "not trade authorization" in monitor["query_readiness_statement"]
    assert "The preserved pipeline must still decide" in monitor["transition_narrative"]["readiness_explanation"]
    assert "execution remains manual" in monitor["transition_narrative"]["readiness_explanation"]


def test_live_thesis_transition_narrative_surfaces_stale_reason_text() -> None:
    monitor = ready_workspace(
        "ES",
        trigger_state=trigger_result(
            "ES",
            TriggerState.STALE,
            blocking_reasons=("quote_stale", "stale_or_missing_timestamp:ES"),
        ),
    ).to_dict()["live_thesis_monitor"]

    narrative = monitor["transition_narrative"]
    assert narrative["state_label"] == "STALE"
    assert "quote_stale" in narrative["blocking_explanation"]
    assert "Fresh deterministic inputs are required" in narrative["readiness_explanation"]


def test_absent_pipeline_result_is_not_queried() -> None:
    result = ready_workspace("ES", last_pipeline_result=None).to_dict()["last_pipeline_result"]

    assert result["status"] == "not_queried"
    assert result["summary"] == {}
    assert result["unavailable_reason"] == "No preserved pipeline result summary has been supplied."


def test_no_trade_pipeline_result_does_not_create_alternate_suggestions() -> None:
    result = ready_workspace(
        "ES",
        last_pipeline_result={
            "status": "completed",
            "contract": "ES",
            "termination_stage": "contract_market_read",
            "final_decision": "NO_TRADE",
            "sufficiency_gate_status": "READY",
            "contract_analysis_outcome": "NO_TRADE",
            "proposed_setup_outcome": None,
            "risk_authorization_decision": "BLOCKED",
            "alternate_suggestion": "do something else",
        },
    ).to_dict()["last_pipeline_result"]

    assert result["status"] == "completed"
    assert result["summary"]["final_decision"] == "NO_TRADE"
    assert "alternate_suggestion" not in result
    assert "risk_authorization_decision" not in result["summary"]
    assert "no alternate suggestions" in result["result_statement"]


def test_no_broker_order_account_fill_pnl_fields_are_introduced() -> None:
    payload = ready_workspace("ES").to_dict()
    keys = collect_keys(payload)

    for forbidden in FORBIDDEN_KEYS:
        assert forbidden not in keys


def test_sensitive_values_are_redacted_from_workspace_output() -> None:
    workspace = ready_workspace(
        "ES",
        brief=brief(
            "ES",
            warning="Authorization: Bearer BEARER_VALUE_PRIVATE_12345678901234567890",
            unavailable_reason=(
                "access_token=ACCESS_VALUE_PRIVATE refresh_token=REFRESH_VALUE_PRIVATE "
                "customerId=CUSTOMER_VALUE_PRIVATE correlId=CORREL_VALUE_PRIVATE "
                "accountNumber=ACCOUNT_VALUE_PRIVATE wss://stream-redaction.invalid/ws"
            ),
        ),
        provider_status="Authorization: Bearer BEARER_VALUE_PRIVATE_12345678901234567890",
        stream_status="wss://stream-redaction.invalid/ws?token=ACCESS_VALUE_PRIVATE",
    )
    rendered = json.dumps(workspace.to_dict(), sort_keys=True)

    for value in SENSITIVE_VALUES:
        assert value not in rendered
    assert "[REDACTED" in rendered


def test_unavailable_macro_and_order_flow_fields_are_not_inferred() -> None:
    workspace = ready_workspace(
        "MGC",
        brief=brief(
            "MGC",
            unavailable_field="cross_asset.dxy",
            unavailable_reason="numeric DXY unavailable in fixture; do not infer",
            required_fields=(
                "market.current_price",
                "cross_asset.dxy",
                "cross_asset.cash_10y_yield",
                "macro_context.fear_catalyst_state",
                "order_flow.footprint",
                "order_flow.dom",
                "order_flow.sweep",
                "order_flow.cumulative_delta",
                "order_flow.aggressive_order_flow",
            ),
        ),
    ).to_dict()
    rendered = json.dumps(workspace, sort_keys=True).lower()

    assert "dxy_value" not in rendered
    assert "yield_value" not in rendered
    assert "fear_catalyst_value" not in rendered
    assert "footprint_value" not in rendered
    assert "dom_value" not in rendered
    assert "sweep_value" not in rendered
    assert "cumulative_delta_value" not in rendered
    assert "aggressive_order_flow_value" not in rendered
    assert "unavailable_not_inferred" in rendered


def test_evidence_and_replay_placeholder_has_explicit_unavailable_reasons() -> None:
    evidence = ready_workspace("6E").to_dict()["evidence_and_replay"]

    assert evidence["run_history_status"] == "unavailable"
    assert evidence["audit_replay_status"] == "unavailable"
    assert evidence["operator_notes_status"] == "unavailable"
    assert evidence["trigger_transition_log_status"] == "unavailable"
    assert evidence["trigger_transition_log"] == {
        "status": "unavailable",
        "count": 0,
        "contract": "6E",
        "blocking_reasons": ["log_source_not_wired"],
        "source_schema": None,
    }
    assert len(evidence["unavailable_reasons"]) == 4
    assert evidence["decision_review_audit_event"]["manual_only_execution"] is True
    assert evidence["decision_review_audit_event"]["preserved_engine_authority"] is True
    assert evidence["decision_review_audit_event"]["trigger_review"]["transition_narrative"]["narrative_available"] is True
    assert evidence["decision_review_replay"]["available"] is True
    assert evidence["decision_review_replay"]["manual_only_execution"] is True
    assert evidence["decision_review_replay"]["preserved_engine_authority"] is True
    assert evidence["decision_review_replay"]["trigger_transition_narrative_available"] is True
    assert evidence["decision_review_replay"]["replay_reference_status"] == "unavailable"
    assert "unavailable" in evidence["decision_review_replay"]["replay_reference_message"].lower()
    assert evidence["decision_review_replay"]["narrative_quality"]["status"] == "WARN"
    assert evidence["decision_review_replay"]["narrative_quality"]["replay_reference_present"] is False
    assert evidence["replay_statement"] == "No synthetic replay is labeled as real evidence."


def test_workspace_evidence_links_supplied_audit_replay_record_without_synthetic_replay() -> None:
    evidence = ready_workspace(
        "ES",
        last_pipeline_result={
            "status": "completed",
            "contract": "ES",
            "termination_stage": "contract_market_read",
            "final_decision": "NO_TRADE",
            "sufficiency_gate_status": "READY",
            "contract_analysis_outcome": "NO_TRADE",
            "proposed_setup_outcome": None,
        },
        audit_replay_record={
            "source": "stage_e_jsonl",
            "stage_e_live_backend": True,
            "replay_available": True,
            "last_run_id": "run-es-1",
            "last_final_decision": "NO_TRADE",
        },
    ).to_dict()["evidence_and_replay"]
    replay = evidence["decision_review_replay"]

    assert evidence["audit_replay_status"] == "available"
    assert replay["replay_reference_available"] is True
    assert replay["replay_reference_status"] == "available"
    assert replay["replay_reference_source"] == "stage_e_jsonl"
    assert replay["replay_reference_run_id"] == "run-es-1"
    assert replay["replay_reference_final_decision"] == "NO_TRADE"
    assert replay["replay_reference_stage_e_live_backend"] is True
    assert replay["replay_reference_consistent"] is True
    assert "audit_replay_record" in replay["source_fields"]
    assert evidence["replay_statement"] == "No synthetic replay is labeled as real evidence."


def test_workspace_evidence_surfaces_supplied_trigger_transition_log_with_count_and_contract() -> None:
    log = {
        "schema": "evidence_replay_v1",
        "contract": "ES",
        "profile_id": "preserved_es_phase1",
        "trigger_transitions": (
            {
                "event_id": "evt-es-1",
                "timestamp": "2026-05-06T13:55:00+00:00",
                "event_type": "trigger_query_ready",
                "setup_id": "es_setup_1",
                "trigger_id": "es_trigger_1",
                "trigger_state": "QUERY_READY",
                "source": "fixture_backed",
            },
            {
                "event_id": "evt-es-2",
                "timestamp": "2026-05-06T13:56:00+00:00",
                "event_type": "trigger_invalidated",
                "setup_id": "es_setup_1",
                "trigger_id": "es_trigger_1",
                "trigger_state": "INVALIDATED",
                "source": "fixture_backed",
            },
        ),
    }

    evidence = ready_workspace("ES", trigger_transition_log=log).to_dict()["evidence_and_replay"]

    assert evidence["trigger_transition_log_status"] == "available"
    assert evidence["trigger_transition_log"] == {
        "status": "available",
        "count": 2,
        "contract": "ES",
        "profile_id": "preserved_es_phase1",
        "blocking_reasons": [],
        "source_schema": "evidence_replay_v1",
    }
    assert "Trigger transition log source not wired in this foundation." not in evidence["unavailable_reasons"]


def test_workspace_evidence_accepts_replay_summary_from_trigger_transition_builder() -> None:
    trigger_events = build_trigger_transition_evidence_events(
        trigger_result("ES", TriggerState.ARMED),
        trigger_result("ES", TriggerState.QUERY_READY),
        timestamp="2026-05-06T14:00:05+00:00",
        profile_id="preserved_es_phase1",
        source="fixture",
        premarket_brief_ref="premarket/ES/2026-05-06/brief.json",
    )
    replay = build_replay_summary(
        (
            create_evidence_event(
                contract="ES",
                profile_id="preserved_es_phase1",
                event_id="evt-stream",
                timestamp="2026-05-06T14:00:00+00:00",
                event_type="stream_connected",
                source="fixture",
                premarket_brief_ref="premarket/ES/2026-05-06/brief.json",
            ),
            *trigger_events,
        ),
        contract="ES",
        profile_id="preserved_es_phase1",
    ).to_dict()

    evidence = ready_workspace("ES", trigger_transition_log=replay).to_dict()["evidence_and_replay"]

    assert replay["schema"] == EVIDENCE_REPLAY_SCHEMA
    assert evidence["trigger_transition_log_status"] == "available"
    assert evidence["trigger_transition_log"] == {
        "status": "available",
        "count": 1,
        "contract": "ES",
        "profile_id": "preserved_es_phase1",
        "blocking_reasons": [],
        "source_schema": EVIDENCE_REPLAY_SCHEMA,
    }


def test_workspace_evidence_blocks_cross_profile_trigger_transition_log() -> None:
    trigger_events = build_trigger_transition_evidence_events(
        trigger_result("ES", TriggerState.ARMED),
        trigger_result("ES", TriggerState.QUERY_READY),
        timestamp="2026-05-06T14:00:05+00:00",
        profile_id="fixture_es_demo",
        source="fixture",
        premarket_brief_ref="premarket/ES/2026-05-06/brief.json",
    )
    replay = build_replay_summary(
        (
            create_evidence_event(
                contract="ES",
                profile_id="fixture_es_demo",
                event_id="evt-stream",
                timestamp="2026-05-06T14:00:00+00:00",
                event_type="stream_connected",
                source="fixture",
                premarket_brief_ref="premarket/ES/2026-05-06/brief.json",
            ),
            *trigger_events,
        ),
        contract="ES",
        profile_id="fixture_es_demo",
    ).to_dict()

    evidence = ready_workspace("ES", trigger_transition_log=replay).to_dict()["evidence_and_replay"]

    assert evidence["trigger_transition_log_status"] == "blocked"
    assert evidence["trigger_transition_log"] == {
        "status": "blocked",
        "count": 0,
        "contract": "ES",
        "profile_id": "preserved_es_phase1",
        "blocking_reasons": ["cross_profile_replay_summary:fixture_es_demo"],
        "source_schema": EVIDENCE_REPLAY_SCHEMA,
    }


def test_workspace_evidence_blocks_cross_contract_trigger_transition_log() -> None:
    log = {
        "schema": "evidence_replay_v1",
        "contract": "NQ",
        "trigger_transitions": (
            {
                "event_id": "evt-nq-1",
                "timestamp": "2026-05-06T13:55:00+00:00",
                "event_type": "trigger_query_ready",
                "setup_id": "nq_setup_1",
                "trigger_id": "nq_trigger_1",
                "trigger_state": "QUERY_READY",
                "source": "fixture_backed",
            },
        ),
    }

    evidence = ready_workspace("ES", trigger_transition_log=log).to_dict()["evidence_and_replay"]

    assert evidence["trigger_transition_log_status"] == "blocked"
    assert evidence["trigger_transition_log"]["status"] == "blocked"
    assert evidence["trigger_transition_log"]["count"] == 0
    assert evidence["trigger_transition_log"]["contract"] == "ES"
    assert evidence["trigger_transition_log"]["blocking_reasons"] == ["cross_contract_replay_summary:NQ"]


def test_workspace_evidence_marks_supplied_but_empty_trigger_transition_log_unavailable() -> None:
    log = {"schema": "evidence_replay_v1", "contract": "MGC", "trigger_transitions": ()}

    evidence = ready_workspace("MGC", trigger_transition_log=log).to_dict()["evidence_and_replay"]

    assert evidence["trigger_transition_log_status"] == "unavailable"
    assert evidence["trigger_transition_log"]["status"] == "unavailable"
    assert evidence["trigger_transition_log"]["count"] == 0
    assert evidence["trigger_transition_log"]["profile_id"] == "preserved_mgc_phase1"
    assert evidence["trigger_transition_log"]["blocking_reasons"] == ["log_empty_no_transitions_recorded"]


def test_workspace_evidence_blocks_transition_log_without_evidence_replay_schema() -> None:
    log = {
        "contract": "ES",
        "trigger_transitions": (
            {
                "event_id": "evt-derived",
                "timestamp": "2026-05-06T13:55:00+00:00",
                "event_type": "trigger_query_ready",
                "setup_id": "es_setup_1",
                "trigger_id": "es_trigger_1",
                "trigger_state": "QUERY_READY",
                "source": "fixture_backed",
            },
        ),
    }

    evidence = ready_workspace("ES", trigger_transition_log=log).to_dict()["evidence_and_replay"]

    assert evidence["trigger_transition_log_status"] == "blocked"
    assert evidence["trigger_transition_log"] == {
        "status": "blocked",
        "count": 0,
        "contract": "ES",
        "profile_id": "preserved_es_phase1",
        "blocking_reasons": ["unsupported_transition_log_schema:<missing>"],
        "source_schema": None,
    }


def test_workspace_evidence_blocks_transition_log_derived_from_decision_replay_shape() -> None:
    log = {
        "schema": "decision_review_replay_shape",
        "contract": "ES",
        "final_decision": "NO_TRADE",
        "trigger_state": "QUERY_READY",
        "transition_summary": "Final trigger state text is not a transition log.",
        "trigger_transitions": (
            {
                "event_id": "evt-after-the-fact",
                "timestamp": "2026-05-06T13:55:00+00:00",
                "event_type": "trigger_query_ready",
                "setup_id": "es_setup_1",
                "trigger_id": "es_trigger_1",
                "trigger_state": "QUERY_READY",
                "source": "fixture_backed",
            },
        ),
    }

    evidence = ready_workspace("ES", trigger_transition_log=log).to_dict()["evidence_and_replay"]

    assert evidence["trigger_transition_log_status"] == "blocked"
    assert evidence["trigger_transition_log"]["count"] == 0
    assert evidence["trigger_transition_log"]["source_schema"] == "decision_review_replay_shape"
    assert evidence["trigger_transition_log"]["blocking_reasons"] == [
        "unsupported_transition_log_schema:decision_review_replay_shape",
    ]


@pytest.mark.parametrize("contract", ("ES", "NQ", "CL", "6E", "MGC"))
def test_workspace_evidence_attributes_trigger_transition_log_per_contract_without_bleed(contract: str) -> None:
    profile_id = f"preserved_{contract.lower()}_phase1"
    log = {
        "schema": "evidence_replay_v1",
        "contract": contract,
        "profile_id": profile_id,
        "trigger_transitions": (
            {
                "event_id": f"evt-{contract.lower()}-1",
                "timestamp": "2026-05-06T13:55:00+00:00",
                "event_type": "trigger_query_ready",
                "setup_id": f"{contract.lower()}_setup_1",
                "trigger_id": f"{contract.lower()}_trigger_1",
                "trigger_state": "QUERY_READY",
                "source": "fixture_backed",
            },
        ),
    }

    evidence = ready_workspace(contract, trigger_transition_log=log).to_dict()["evidence_and_replay"]

    assert evidence["trigger_transition_log"]["status"] == "available"
    assert evidence["trigger_transition_log"]["count"] == 1
    assert evidence["trigger_transition_log"]["contract"] == contract
    assert evidence["trigger_transition_log"]["blocking_reasons"] == []
    rendered = json.dumps(evidence, sort_keys=True)
    for other in ("ES", "NQ", "CL", "6E", "MGC"):
        if other == contract:
            continue
        assert f"{other.lower()}_setup_1" not in rendered.lower()


def test_workspace_evidence_explicit_status_override_takes_precedence_over_log() -> None:
    log = {
        "schema": "evidence_replay_v1",
        "contract": "ES",
        "profile_id": "preserved_es_phase1",
        "trigger_transitions": (
            {
                "event_id": "evt-es-override",
                "timestamp": "2026-05-06T13:55:00+00:00",
                "event_type": "trigger_query_ready",
                "setup_id": "es_setup_1",
                "trigger_id": "es_trigger_1",
                "trigger_state": "QUERY_READY",
                "source": "fixture_backed",
            },
        ),
    }

    evidence = ready_workspace(
        "ES",
        trigger_transition_log=log,
        trigger_transition_log_status="unavailable",
    ).to_dict()["evidence_and_replay"]

    assert evidence["trigger_transition_log_status"] == "unavailable"
    assert evidence["trigger_transition_log"]["status"] == "available"
    assert evidence["trigger_transition_log"]["count"] == 1


def test_no_fixture_fallback_after_live_failure_behavior_is_weakened() -> None:
    gate = query_gate(
        "ES",
        provider_status="error",
        stream_status="error",
        fixture_mode_accepted=True,
    )
    workspace = ready_workspace("ES", gate=gate).to_dict()

    assert gate.enabled is False
    assert workspace["pipeline_gate"]["manual_query_allowed"] is False
    assert "provider_status_blocked:error" in workspace["pipeline_gate"]["blocking_reasons"]
    assert "stream_status_blocked:error" in workspace["pipeline_gate"]["blocking_reasons"]


def test_r14_cockpit_contract_serializes_deterministically_from_fixture_safe_inputs() -> None:
    cockpit = ready_cockpit(
        "MGC",
        last_pipeline_result={
            "status": "completed",
            "contract": "MGC",
            "termination_stage": "contract_market_read",
            "stage_termination_reason": "stage_b_no_trade",
            "final_decision": "NO_TRADE",
            "sufficiency_gate_status": "READY",
            "contract_analysis_outcome": "NO_TRADE",
            "proposed_setup_outcome": None,
            "risk_authorization_decision": None,
        },
    )

    encoded = json.dumps(cockpit, sort_keys=True)
    decoded = json.loads(encoded)

    assert decoded["schema"] == R14_COCKPIT_SCHEMA
    assert decoded["identity"] == {
        "current_profile": "preserved_mgc_phase1",
        "contract": "MGC",
        "contract_support_status": "final_supported",
        "runtime_profile_status": "available",
    }
    assert decoded["runtime_status"]["provider_status"] == "connected"
    assert decoded["premarket"]["active_setup_count"] == 1
    assert decoded["premarket"]["global_guidance"] == ["unavailable"]
    assert decoded["premarket"]["required_fields"] == ["market.current_price", "market.cumulative_delta"]
    assert decoded["premarket"]["trigger_definitions"][0]["trigger_id"] == "mgc_trigger_1"
    assert decoded["premarket"]["warnings"] == ["Do not infer unavailable market state."]
    assert decoded["premarket"]["invalidators"][0]["invalidator_id"] == "mgc_invalidator_1"
    assert decoded["triggers"][0]["query_ready_provenance"] == "real_trigger_state_result"
    assert decoded["triggers"][0]["current_values"][0] == {
        "field": "market.current_price",
        "value": "unavailable",
        "status": "unavailable",
    }
    assert decoded["query_readiness"]["query_ready"] is True
    assert decoded["query_readiness"]["manual_query_allowed"] is True
    assert decoded["query_readiness"]["query_disabled_reason"] is None
    assert {
        (state["category"], state["state"])
        for state in decoded["operator_states"]
    } == {
        ("query_ready", "query_ready"),
    }
    assert decoded["last_pipeline_result"]["status"] == "completed"
    assert decoded["last_pipeline_result"]["no_trade_summary"] == "Preserved engine returned NO_TRADE."
    assert decoded["replay_availability"]["session_evidence_status"] == "unavailable"
    assert decoded["replay_availability"]["audit_replay_available"] is False


def test_r14_cockpit_disabled_query_state_carries_plain_text_reason() -> None:
    cockpit = ready_cockpit(
        "ES",
        gate=query_gate("ES", stream_status="stale", event_lockout_active=True),
    )
    query = cockpit["query_readiness"]

    assert query["query_ready"] is False
    assert query["manual_query_allowed"] is False
    assert query["query_disabled_reason"].startswith("Manual query disabled:")
    assert "stream_status_blocked:stale" in query["blocking_reasons"]
    assert "event_lockout_active" in query["blocking_reasons"]
    assert "QUERY_READY requires real TriggerStateResult provenance" in query["query_disabled_reason"]
    states = states_by_category(cockpit)
    assert states["event_lockout"]["state"] == "lockout"


def test_r14_cockpit_query_readiness_requires_real_trigger_state_result_not_raw_enabled_mapping() -> None:
    fake_gate = {
        "enabled": True,
        "pipeline_query_authorized": True,
        "status": "ENABLED",
        "contract": "ES",
        "profile_id": "preserved_es_phase1",
        "setup_id": "es_setup_1",
        "trigger_id": "es_trigger_1",
        "trigger_state": "QUERY_READY",
        "trigger_state_from_real_producer": True,
        "enabled_reasons": ["trigger_state_query_ready"],
        "disabled_reasons": [],
        "blocking_reasons": [],
        "required_conditions": ["trigger_state_query_ready"],
        "missing_conditions": [],
        "provider_status": "connected",
        "stream_status": "connected",
        "session_valid": True,
        "event_lockout_active": False,
    }
    cockpit = ready_cockpit("ES", gate=fake_gate, trigger_state={"state": "QUERY_READY"})
    query = cockpit["query_readiness"]

    assert query["pipeline_gate_enabled"] is True
    assert query["query_ready"] is False
    assert query["manual_query_allowed"] is False
    assert query["trigger_state_from_real_producer"] is False
    assert "cockpit_trigger_state_result_provenance_not_verified" in query["blocking_reasons"]
    assert query["query_ready_provenance"] == "unavailable_not_inferred_from_display_or_raw_enabled_mapping"
    states = states_by_category(cockpit)
    assert states["no_trigger_state_result_provenance"]["state"] == "unavailable"


def test_r14_cockpit_query_readiness_cannot_be_inferred_from_display_trigger_status_vm() -> None:
    display_trigger = TriggerStatusVM(
        trigger_id="display_query_ready",
        is_valid=True,
        is_true=True,
        missing_fields=(),
        invalid_reasons=(),
    )
    gate = query_gate("ES", trigger_state=trigger_result("ES", TriggerState.QUERY_READY))
    cockpit = ready_cockpit("ES", gate=gate, trigger_state=display_trigger)  # type: ignore[arg-type]
    query = cockpit["query_readiness"]

    assert gate.enabled is True
    assert query["pipeline_gate_enabled"] is True
    assert query["query_ready"] is False
    assert "cockpit_trigger_state_result_provenance_not_verified" in query["blocking_reasons"]
    assert states_by_category(cockpit)["no_trigger_state_result_provenance"]["state"] == "unavailable"


def test_r14_cockpit_operator_states_surface_stable_plain_text_categories() -> None:
    stale_gate = query_gate("ES", quote_fresh=False)
    bars_gate = query_gate("ES", bars_available=False)
    lockout_gate = query_gate("ES", event_lockout_active=True)
    disabled_stream_gate = query_gate("ES", stream_status="disabled")
    error_stream_gate = query_gate("ES", stream_status="error")
    missing_profile_gate = query_gate("ES", profile_id=None, profile_exists=False)
    fixture_gate = query_gate("ES", provider_status="fixture", stream_status="fixture", fixture_mode_accepted=True)
    invalidated_trigger = trigger_result(
        "ES",
        TriggerState.INVALIDATED,
        invalid_reasons=("invalidator_active",),
    )
    not_ready_brief = brief("ES")
    not_ready_brief["status"] = "BLOCKED"

    cases = [
        (ready_cockpit("YM"), "unsupported_contract", "blocked"),
        (ready_cockpit("ZN"), "excluded_contract", "blocked"),
        (ready_cockpit("ES", gate=missing_profile_gate), "missing_runtime_profile", "unavailable"),
        (ready_cockpit("ES", brief=not_ready_brief), "premarket_brief_not_ready", "blocked"),
        (
            ready_cockpit(
                "ES",
                trigger_state=trigger_result(
                    "ES",
                    TriggerState.BLOCKED,
                    missing_fields=("market.cumulative_delta",),
                    blocking_reasons=("missing_required_live_fields",),
                ),
            ),
            "missing_required_live_field",
            "blocked",
        ),
        (ready_cockpit("ES", gate=stale_gate), "stale_quote", "stale"),
        (ready_cockpit("ES", gate=bars_gate), "missing_chart_bars", "unavailable"),
        (ready_cockpit("ES", gate=lockout_gate), "event_lockout", "lockout"),
        (
            ready_cockpit(
                "ES",
                trigger_state=invalidated_trigger,
                gate=query_gate("ES", trigger_state=invalidated_trigger),
            ),
            "trigger_invalidated",
            "invalidated",
        ),
        (ready_cockpit("ES", gate=disabled_stream_gate, stream_status="disabled"), "stream_disabled", "unavailable"),
        (ready_cockpit("ES", gate=error_stream_gate, stream_status="error"), "stream_error", "unavailable"),
        (
            ready_cockpit(
                "ES",
                gate=fixture_gate,
                profile_id="fixture_es_demo",
                provider_status="fixture",
                stream_status="fixture",
            ),
            "fixture_mode",
            "fixture_mode",
        ),
        (ready_cockpit("ES", last_pipeline_result=None), "no_pipeline_result_yet", "no_result_yet"),
        (ready_cockpit("ES"), "query_ready", "query_ready"),
    ]

    for cockpit, category, state in cases:
        states = states_by_category(cockpit)
        assert category in states
        assert states[category]["state"] == state
        assert states[category]["summary"]
        assert states[category]["reason"]


def test_r14_cockpit_missing_stale_and_non_provenance_states_remain_fail_closed() -> None:
    fake_gate = {
        "enabled": True,
        "pipeline_query_authorized": True,
        "status": "ENABLED",
        "contract": "ES",
        "profile_id": "preserved_es_phase1",
        "setup_id": "es_setup_1",
        "trigger_id": "es_trigger_1",
        "trigger_state": "QUERY_READY",
        "trigger_state_from_real_producer": False,
        "enabled_reasons": ["trigger_state_query_ready"],
        "disabled_reasons": [],
        "blocking_reasons": [],
        "required_conditions": ["trigger_state_query_ready"],
        "missing_conditions": [],
        "provider_status": "connected",
        "stream_status": "connected",
        "session_valid": True,
        "event_lockout_active": False,
    }
    stale_cockpit = ready_cockpit("ES", gate=query_gate("ES", quote_fresh=False))
    missing_cockpit = ready_cockpit(
        "ES",
        trigger_state=trigger_result("ES", TriggerState.BLOCKED, missing_fields=("market.current_price",)),
    )
    non_provenance_cockpit = ready_cockpit("ES", gate=fake_gate, trigger_state={"state": "QUERY_READY"})

    for cockpit, category in (
        (stale_cockpit, "stale_quote"),
        (missing_cockpit, "missing_required_live_field"),
        (non_provenance_cockpit, "no_trigger_state_result_provenance"),
    ):
        states = states_by_category(cockpit)
        assert cockpit["query_readiness"]["query_ready"] is False
        assert cockpit["query_readiness"]["manual_query_allowed"] is False
        assert category in states


def test_phase1_shell_exposes_r14_cockpit_contract_without_adding_layout_surface() -> None:
    shell = build_es_app_shell_for_mode(mode="fixture_demo", query_action_requested=False)

    cockpit = shell["r14_cockpit"]
    assert cockpit["schema"] == R14_COCKPIT_SCHEMA
    assert cockpit["identity"]["contract"] == "ES"
    assert cockpit["query_readiness"]["query_ready"] is False
    assert cockpit["query_readiness"]["manual_query_allowed"] is False
    assert "r14_cockpit" not in shell["surfaces"]


def ready_workspace(
    contract: str,
    *,
    gate: object | None = None,
    trigger_state: TriggerStateResult | None = None,
    brief: dict[str, object] | None = None,
    last_pipeline_result: dict[str, object] | None = None,
    provider_status: str | None = None,
    stream_status: str | None = None,
    audit_replay_record: dict[str, object] | None = None,
    trigger_transition_log: dict[str, object] | None = None,
    trigger_transition_log_status: str | None = None,
) -> object:
    selected_trigger = trigger_state or trigger_result(contract, TriggerState.QUERY_READY)
    selected_gate = gate or query_gate(contract, trigger_state=selected_trigger)
    return build_operator_workspace_view_model(
        OperatorWorkspaceRequest(
            contract=contract,
            profile_id=f"preserved_{contract.lower()}_phase1",
            watchman_validator="READY",
            trigger_state=selected_trigger,
            pipeline_query_gate=selected_gate,
            premarket_brief=brief or globals()["brief"](contract),
            live_observable=live_snapshot(contract),
            provider_status=provider_status,
            stream_status=stream_status,
            quote_freshness="fresh",
            bar_freshness="fresh",
            session_status="valid",
            event_lockout_status="inactive",
            evaluated_at="2026-05-06T14:00:00+00:00",
            last_pipeline_result=last_pipeline_result,
            audit_replay_record=audit_replay_record,
            trigger_transition_log=trigger_transition_log,
            trigger_transition_log_status=trigger_transition_log_status,
        )
    )


def ready_cockpit(
    contract: str,
    *,
    gate: object | None = None,
    trigger_state: object | None = None,
    brief: dict[str, object] | None = None,
    last_pipeline_result: dict[str, object] | None = None,
    profile_id: str | None = None,
    provider_status: str = "connected",
    stream_status: str = "connected",
) -> dict[str, object]:
    selected_trigger = trigger_state if trigger_state is not None else trigger_result(contract, TriggerState.QUERY_READY)
    selected_gate = gate or query_gate(contract, trigger_state=selected_trigger)
    return build_r14_cockpit_view_model(
        OperatorWorkspaceRequest(
            contract=contract,
            profile_id=profile_id or f"preserved_{contract.lower()}_phase1",
            watchman_validator="READY",
            trigger_state=selected_trigger,  # type: ignore[arg-type]
            pipeline_query_gate=selected_gate,  # type: ignore[arg-type]
            premarket_brief=brief or globals()["brief"](contract),
            live_observable=live_snapshot(contract),
            provider_status=provider_status,
            stream_status=stream_status,
            quote_freshness="fresh",
            bar_freshness="fresh",
            session_status="valid",
            event_lockout_status="inactive",
            evaluated_at="2026-05-06T14:00:00+00:00",
            last_pipeline_result=last_pipeline_result,
        )
    ).to_dict()


def query_gate(contract: str, **overrides: object) -> object:
    values: dict[str, object] = {
        "contract": contract,
        "profile_id": f"preserved_{contract.lower()}_phase1",
        "profile_exists": True,
        "profile_preflight_passed": True,
        "watchman_validator_status": "READY",
        "live_snapshot": live_snapshot(contract),
        "live_snapshot_fresh": True,
        "quote_fresh": True,
        "bars_available": True,
        "bars_fresh": True,
        "required_trigger_fields_present": True,
        "trigger_state": trigger_result(contract, TriggerState.QUERY_READY),
        "provider_status": "connected",
        "stream_status": "connected",
        "session_valid": True,
        "event_lockout_active": False,
        "fixture_mode_accepted": False,
        "trigger_state_from_real_producer": True,
        "evaluated_at": "2026-05-06T14:00:00+00:00",
    }
    values.update(overrides)
    return evaluate_pipeline_query_gate(PipelineQueryGateRequest(**values))  # type: ignore[arg-type]


def states_by_category(cockpit: dict[str, object]) -> dict[str, dict[str, object]]:
    states = cockpit["operator_states"]
    assert isinstance(states, list)
    return {
        state["category"]: state
        for state in states
        if isinstance(state, dict) and isinstance(state.get("category"), str)
    }


def trigger_result(
    contract: str,
    state: TriggerState,
    *,
    missing_fields: tuple[str, ...] = (),
    invalid_reasons: tuple[str, ...] = (),
    blocking_reasons: tuple[str, ...] = (),
) -> TriggerStateResult:
    return TriggerStateResult(
        contract=contract,
        setup_id=f"{contract.lower()}_setup_1",
        trigger_id=f"{contract.lower()}_trigger_1",
        state=state,
        distance_to_trigger_ticks=0.0 if state == TriggerState.QUERY_READY else None,
        required_fields=("market.current_price", "market.cumulative_delta"),
        missing_fields=missing_fields,
        invalid_reasons=invalid_reasons,
        blocking_reasons=blocking_reasons,
        last_updated="2026-05-06T14:00:00+00:00",
    )


def brief(
    contract: str,
    *,
    warning: str = "Do not infer unavailable market state.",
    unavailable_field: str = "cross_asset.index_cash_tone",
    unavailable_reason: str = "not present in fixture inputs",
    required_fields: tuple[str, ...] = ("market.current_price", "market.cumulative_delta"),
) -> dict[str, object]:
    prefix = contract.lower()
    return {
        "contract": contract,
        "session_date": "2026-05-06",
        "status": "READY",
        "source_context": {
            "required_context": list(required_fields),
            "missing_required_context": [],
            "unavailable_required_context": [],
        },
        "unavailable_fields": [
            {
                "field": unavailable_field,
                "reason": unavailable_reason,
            }
        ],
        "structural_setups": [
            {
                "id": f"{prefix}_setup_1",
                "summary": f"{contract} fixture setup requires explicit read-model confirmation.",
                "description": "Full raw description stays out of the primary workspace model.",
                "required_live_fields": list(required_fields),
                "query_triggers": [
                    {
                        "id": f"{prefix}_trigger_1",
                        "logic": f"{prefix}_fixture_trigger",
                        "description": f"Query readiness trigger for {contract} fixture setup.",
                        "required_live_fields": list(required_fields),
                        "invalidators": [
                            {
                                "id": f"{prefix}_invalidator_1",
                                "condition": "required read-model fields unavailable",
                                "action": "block_query_ready_read_model",
                            }
                        ],
                    }
                ],
                "warnings": [warning],
            }
        ],
    }


def live_snapshot(contract: str) -> dict[str, object]:
    return {
        "schema": "live_observable_snapshot_v2",
        "generated_at": "2026-05-06T14:00:00+00:00",
        "provider": "fixture",
        "provider_status": "connected",
        "contracts": {
            contract: {
                "contract": contract,
                "symbol": f"/{contract}M26",
                "quality": {
                    "fresh": True,
                    "required_fields_present": True,
                    "blocking_reasons": [],
                },
            }
        },
        "data_quality": {"ready": True, "blocking_reasons": []},
    }


def collect_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        keys = set(value.keys())
        for child in value.values():
            keys.update(collect_keys(child))
        return keys
    if isinstance(value, list):
        keys: set[str] = set()
        for child in value:
            keys.update(collect_keys(child))
        return keys
    return set()
