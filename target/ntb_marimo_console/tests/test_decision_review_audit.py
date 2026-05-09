from __future__ import annotations

import json

from ntb_marimo_console.contract_universe import final_target_contracts
from ntb_marimo_console.decision_review_audit import (
    DECISION_REVIEW_AUDIT_EVENT_SCHEMA,
    DECISION_REVIEW_AUDIT_EVENT_SCHEMA_VERSION,
    build_decision_review_audit_event,
)


CREATED_AT = "2026-05-09T12:00:00Z"
SENSITIVE_VALUES = (
    "ACCESS_VALUE_PRIVATE",
    "REFRESH_VALUE_PRIVATE",
    "BEARER_VALUE_PRIVATE",
    "APP_KEY_PRIVATE",
    "APP_SECRET_PRIVATE",
    "CUSTOMER_VALUE_PRIVATE",
    "CORREL_VALUE_PRIVATE",
    "ACCOUNT_VALUE_PRIVATE",
    "stream-redaction",
)


def test_audit_event_is_json_serializable_with_stable_schema_and_authority_flags() -> None:
    event = build_decision_review_audit_event(
        decision_review=decision_review_panel(),
        live_thesis_monitor=live_thesis_monitor(),
        profile_id="preserved_es_phase1",
        created_at=CREATED_AT,
        source="fixture",
    ).to_dict()

    encoded = json.dumps(event, sort_keys=True)
    decoded = json.loads(encoded)

    assert decoded["schema"] == DECISION_REVIEW_AUDIT_EVENT_SCHEMA
    assert decoded["schema_version"] == DECISION_REVIEW_AUDIT_EVENT_SCHEMA_VERSION
    assert decoded["created_at"] == CREATED_AT
    assert decoded["manual_only_execution"] is True
    assert decoded["preserved_engine_authority"] is True
    assert decoded["source"] == "fixture"
    assert decoded["contract"] == "ES"
    assert decoded["profile_id"] == "preserved_es_phase1"


def test_audit_event_includes_decision_review_narrative_flags_and_engine_reasoning_summary() -> None:
    event = build_decision_review_audit_event(
        decision_review=decision_review_panel(),
        live_thesis_monitor=live_thesis_monitor(),
        created_at=CREATED_AT,
    ).to_dict()

    assert event["pipeline_result"]["final_decision"] == "NO_TRADE"
    assert event["pipeline_result"]["termination_stage"] == "contract_market_read"
    assert event["decision_review_narrative"]["narrative_available"] is True
    assert event["decision_review_narrative"]["engine_reasoning_available"] is True
    assert event["decision_review_narrative"]["trade_thesis_available"] is False
    assert event["decision_review_narrative"]["risk_authorization_available"] is False
    assert event["engine_reasoning_summary"] == {
        "available": True,
        "market_regime": "choppy",
        "directional_bias": "unclear",
        "evidence_score": 3,
        "confidence_band": "LOW",
        "outcome": "NO_TRADE",
        "structural_notes": "ES choppy near VWAP; no clean structural anchor.",
        "key_levels": {
            "pivot_level": 5602.0,
            "support_levels": [5598.0],
            "resistance_levels": [5606.0],
        },
    }


def test_audit_event_includes_trigger_transition_narrative_and_reasons_when_available() -> None:
    event = build_decision_review_audit_event(
        decision_review=decision_review_panel(),
        live_thesis_monitor=live_thesis_monitor(
            trigger_state="STALE",
            blocking_reasons=("quote_stale", "stale_or_missing_timestamp:ES"),
            missing_fields=("market.current_price",),
            state_flags={"stale": True, "lockout": False, "blocked": True},
        ),
        created_at=CREATED_AT,
    ).to_dict()

    trigger = event["trigger_review"]
    assert trigger["trigger_state"] == "STALE"
    assert trigger["setup_id"] == "es_setup_1"
    assert trigger["trigger_id"] == "es_trigger_1"
    assert trigger["blocking_reasons"] == ["quote_stale", "stale_or_missing_timestamp:ES"]
    assert trigger["missing_fields"] == ["market.current_price"]
    assert trigger["state_flags"]["stale"] is True
    assert trigger["state_flags"]["lockout"] is False
    assert trigger["transition_narrative"]["narrative_available"] is True
    assert "Fresh deterministic inputs are required" in trigger["transition_narrative"]["readiness_explanation"]
    assert "transition_narrative" in event["source_fields"]


def test_audit_event_records_explicit_unavailable_text_when_narrative_fields_are_absent() -> None:
    event = build_decision_review_audit_event(
        decision_review={"surface": "Decision Review", "has_result": False, "message": "No pipeline result loaded."},
        live_thesis_monitor=None,
        created_at=CREATED_AT,
    ).to_dict()

    assert event["decision_review_narrative"]["narrative_available"] is False
    assert event["decision_review_narrative"]["unavailable_message"] == "Decision Review narrative is unavailable."
    assert event["engine_reasoning_summary"]["available"] is False
    assert "unavailable" in event["engine_reasoning_summary"]["unavailable_message"].lower()
    assert event["trigger_review"]["transition_narrative"]["narrative_available"] is False
    assert "unavailable" in event["trigger_review"]["transition_narrative"]["transition_summary"].lower()


def test_audit_event_includes_lockout_reasons_when_available() -> None:
    event = build_decision_review_audit_event(
        decision_review=decision_review_panel(),
        live_thesis_monitor=live_thesis_monitor(
            trigger_state="LOCKOUT",
            blocking_reasons=("event_lockout_active", "operator_event_lockout"),
            state_flags={"stale": False, "lockout": True, "blocked": True},
        ),
        created_at=CREATED_AT,
    ).to_dict()

    assert event["trigger_review"]["state_flags"]["lockout"] is True
    assert "event_lockout_active" in event["trigger_review"]["blocking_reasons"]
    assert "operator_event_lockout" in event["trigger_review"]["transition_narrative"]["blocking_explanation"]


def test_query_ready_audit_event_preserves_manual_pipeline_authority_language() -> None:
    event = build_decision_review_audit_event(
        decision_review=decision_review_panel(),
        live_thesis_monitor=live_thesis_monitor(trigger_state="QUERY_READY"),
        created_at=CREATED_AT,
    ).to_dict()
    text = json.dumps(event, sort_keys=True)

    assert event["manual_only_execution"] is True
    assert event["preserved_engine_authority"] is True
    assert "The preserved pipeline must still decide" in text
    assert "execution remains manual" in text


def test_no_trade_audit_event_does_not_include_alternate_trade_suggestions() -> None:
    event = build_decision_review_audit_event(
        decision_review={
            **decision_review_panel(final_decision="NO_TRADE"),
            "alternate_suggestion": "try another setup",
        },
        live_thesis_monitor=live_thesis_monitor(),
        created_at=CREATED_AT,
    ).to_dict()
    rendered = json.dumps(event, sort_keys=True).lower()

    assert event["pipeline_result"]["final_decision"] == "NO_TRADE"
    assert "alternate_suggestion" not in rendered
    assert "try another setup" not in rendered


def test_audit_event_excludes_sensitive_values_and_authorization_payloads() -> None:
    event = build_decision_review_audit_event(
        decision_review=decision_review_panel(
            structural_notes=(
                "Authorization: Bearer BEARER_VALUE_PRIVATE_12345678901234567890 "
                "access_token=ACCESS_VALUE_PRIVATE refresh_token=REFRESH_VALUE_PRIVATE "
                "app_key=APP_KEY_PRIVATE app_secret=APP_SECRET_PRIVATE "
                "customerId=CUSTOMER_VALUE_PRIVATE correlId=CORREL_VALUE_PRIVATE "
                "accountNumber=ACCOUNT_VALUE_PRIVATE wss://stream-redaction.invalid/ws"
            )
        ),
        live_thesis_monitor=live_thesis_monitor(
            blocking_reasons=(
                "Authorization: Bearer BEARER_VALUE_PRIVATE_12345678901234567890",
                "wss://stream-redaction.invalid/ws?token=ACCESS_VALUE_PRIVATE",
            )
        ),
        created_at=CREATED_AT,
    ).to_dict()
    rendered = json.dumps(event, sort_keys=True)

    for value in SENSITIVE_VALUES:
        assert value not in rendered
    assert "[REDACTED" in rendered


def test_audit_event_excludes_broker_order_fill_account_pnl_and_active_management_fields() -> None:
    event = build_decision_review_audit_event(
        decision_review={
            **decision_review_panel(),
            "broker": "fixture",
            "order": {"id": "do-not-include"},
            "fill": {"id": "do-not-include"},
            "account": "do-not-include",
            "pnl": 100,
            "move_stop": "do-not-include",
            "scale_out": "do-not-include",
        },
        live_thesis_monitor=live_thesis_monitor(),
        created_at=CREATED_AT,
    ).to_dict()
    rendered = json.dumps(event, sort_keys=True).lower()
    keys = collect_keys(event)

    for forbidden in ("broker", "order", "fill", "account", "pnl", "move_stop", "scale_out", "trailing_stop"):
        assert forbidden not in keys
        assert "do-not-include" not in rendered


def test_trigger_narrative_audit_text_has_no_execution_language() -> None:
    event = build_decision_review_audit_event(
        decision_review=decision_review_panel(),
        live_thesis_monitor=live_thesis_monitor(trigger_state="QUERY_READY"),
        created_at=CREATED_AT,
    ).to_dict()
    rendered = json.dumps(event, sort_keys=True).lower()

    for phrase in ("take the trade", "enter", "buy", "sell", "short now", "long now"):
        assert phrase not in rendered


def test_contract_universe_remains_final_targets_with_zn_and_gc_excluded() -> None:
    event = build_decision_review_audit_event(
        decision_review=decision_review_panel(contract="MGC"),
        live_thesis_monitor=live_thesis_monitor(setup_id="mgc_setup_1", trigger_id="mgc_trigger_1"),
        created_at=CREATED_AT,
    ).to_dict()
    rendered = json.dumps(event, sort_keys=True)

    assert final_target_contracts() == ("ES", "NQ", "CL", "6E", "MGC")
    assert "ZN" not in final_target_contracts()
    assert "GC" not in final_target_contracts()
    assert event["contract"] == "MGC"
    assert '"GC"' not in rendered
    assert "Micro Gold" not in rendered


def test_unknown_source_is_explicit_when_source_is_not_supplied() -> None:
    event = build_decision_review_audit_event(
        decision_review=decision_review_panel(),
        live_thesis_monitor=live_thesis_monitor(),
        created_at=CREATED_AT,
    ).to_dict()

    assert event["source"] == "unknown"


def decision_review_panel(
    *,
    contract: str = "ES",
    final_decision: str = "NO_TRADE",
    structural_notes: str = "ES choppy near VWAP; no clean structural anchor.",
) -> dict[str, object]:
    return {
        "surface": "Decision Review",
        "has_result": True,
        "contract": contract,
        "termination_stage": "contract_market_read",
        "final_decision": final_decision,
        "stage_a_status": "READY",
        "stage_b_outcome": "NO_TRADE",
        "stage_c_outcome": None,
        "stage_d_decision": None,
        "narrative_available": True,
        "engine_reasoning": {
            "available": True,
            "market_regime": "choppy",
            "directional_bias": "unclear",
            "evidence_score": 3,
            "confidence_band": "LOW",
            "structural_notes": structural_notes,
            "outcome": "NO_TRADE",
            "conflicting_signals": ["delta_divergence"],
            "assumptions": [],
            "key_levels": {
                "pivot_level": 5602.0,
                "support_levels": [5598.0],
                "resistance_levels": [5606.0],
            },
        },
        "trade_thesis": {"available": False, "unavailable_message": "Engine narrative unavailable in this run."},
        "risk_authorization_detail": {
            "available": False,
            "unavailable_message": "Engine narrative unavailable in this run.",
        },
        "invalidation": {
            "available": False,
            "unavailable_message": "Disqualifiers list is unavailable for this run.",
            "disqualifiers": [],
        },
    }


def live_thesis_monitor(
    *,
    setup_id: str = "es_setup_1",
    trigger_id: str = "es_trigger_1",
    trigger_state: str = "QUERY_READY",
    blocking_reasons: tuple[str, ...] = (),
    missing_fields: tuple[str, ...] = (),
    state_flags: dict[str, bool] | None = None,
) -> dict[str, object]:
    transition_narrative = {
        "narrative_available": True,
        "state_label": trigger_state,
        "transition_summary": f"setup {setup_id} / trigger {trigger_id}: deterministic trigger state recorded.",
        "readiness_explanation": (
            "The preserved pipeline must still decide; QUERY_READY does not approve or authorize a trade, "
            "and execution remains manual."
        )
        if trigger_state == "QUERY_READY"
        else "Fresh deterministic inputs are required before a bounded pipeline query is available.",
        "blocking_explanation": "Blocking reasons: " + ", ".join(blocking_reasons) + "." if blocking_reasons else None,
        "invalidation_explanation": None,
        "missing_data_explanation": "Missing required trigger data: " + ", ".join(missing_fields) + "." if missing_fields else None,
        "operator_guidance": (
            "Use this deterministic read model for audit context only. The preserved pipeline remains the decision "
            "authority, and any execution remains manual."
        ),
        "source_fields": ["state", "setup_id", "trigger_id", "blocking_reasons"],
    }
    return {
        "setup_id": setup_id,
        "trigger_id": trigger_id,
        "trigger_state": trigger_state,
        "distance_to_trigger_ticks": 0.0 if trigger_state == "QUERY_READY" else None,
        "missing_fields": list(missing_fields),
        "invalid_reasons": [],
        "blocking_reasons": list(blocking_reasons),
        "state_flags": state_flags or {"stale": False, "lockout": False, "blocked": bool(blocking_reasons)},
        "transition_narrative": transition_narrative,
    }


def collect_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            keys.add(str(key).lower())
            keys.update(collect_keys(nested))
    elif isinstance(value, list):
        for item in value:
            keys.update(collect_keys(item))
    return keys
