from __future__ import annotations

import json

import pytest

from ntb_marimo_console.contract_universe import final_target_contracts
from ntb_marimo_console.operator_workspace import (
    OPERATOR_WORKSPACE_SCHEMA,
    OperatorWorkspaceRequest,
    build_operator_workspace_view_model,
)
from ntb_marimo_console.pipeline_query_gate import PipelineQueryGateRequest, evaluate_pipeline_query_gate
from ntb_marimo_console.trigger_state import TriggerState, TriggerStateResult


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
        )
    )


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
        "evaluated_at": "2026-05-06T14:00:00+00:00",
    }
    values.update(overrides)
    return evaluate_pipeline_query_gate(PipelineQueryGateRequest(**values))  # type: ignore[arg-type]


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
