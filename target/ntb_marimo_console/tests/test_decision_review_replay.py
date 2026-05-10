from __future__ import annotations

import json

from ntb_marimo_console.contract_universe import final_target_contracts
from ntb_marimo_console.decision_review_audit import DECISION_REVIEW_AUDIT_EVENT_SCHEMA, build_decision_review_audit_event
from ntb_marimo_console.decision_review_replay import (
    DECISION_REVIEW_REPLAY_VM_SCHEMA,
    DECISION_REVIEW_REPLAY_VM_SCHEMA_VERSION,
    build_decision_review_replay_vm,
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


def test_replay_vm_builds_from_complete_audit_event_and_is_json_serializable() -> None:
    replay = build_decision_review_replay_vm(
        complete_audit_event(),
        audit_replay_record=audit_replay_record(),
    ).to_dict()

    encoded = json.dumps(replay, sort_keys=True)
    decoded = json.loads(encoded)

    assert decoded["schema"] == DECISION_REVIEW_REPLAY_VM_SCHEMA
    assert decoded["schema_version"] == DECISION_REVIEW_REPLAY_VM_SCHEMA_VERSION
    assert decoded["available"] is True
    assert decoded["audit_schema"] == DECISION_REVIEW_AUDIT_EVENT_SCHEMA
    assert decoded["created_at"] == CREATED_AT
    assert decoded["contract"] == "ES"
    assert decoded["profile_id"] == "preserved_es_phase1"
    assert decoded["final_decision"] == "NO_TRADE"
    assert decoded["termination_stage"] == "contract_market_read"
    assert decoded["engine_narrative_available"] is True
    assert decoded["trigger_transition_narrative_available"] is True
    assert decoded["manual_only_execution"] is True
    assert decoded["preserved_engine_authority"] is True
    assert decoded["replay_reference_available"] is True
    assert decoded["replay_reference_status"] == "available"
    assert decoded["replay_reference_source"] == "fixture_backed"
    assert decoded["replay_reference_run_id"] == "run-1"
    assert decoded["replay_reference_final_decision"] == "NO_TRADE"
    assert decoded["replay_reference_consistent"] is True
    assert decoded["engine_reasoning_summary"]["market_regime"] == "choppy"
    assert "deterministic trigger state recorded" in decoded["transition_summary"]
    assert decoded["narrative_quality"]["status"] == "PASS"
    assert decoded["narrative_quality"]["manual_only_language_present"] is True
    assert decoded["narrative_quality"]["preserved_engine_authority_language_present"] is True


def test_replay_vm_builds_from_partial_event_with_explicit_unavailable_fields() -> None:
    event = build_decision_review_audit_event(
        decision_review={"surface": "Decision Review", "has_result": False, "message": "No pipeline result loaded."},
        live_thesis_monitor=None,
        created_at=CREATED_AT,
    ).to_dict()
    replay = build_decision_review_replay_vm(event).to_dict()

    assert replay["available"] is True
    assert replay["final_decision"] is None
    assert replay["engine_narrative_available"] is False
    assert replay["trigger_transition_narrative_available"] is False
    assert "unavailable" in str(replay["transition_summary"]).lower()
    assert "unavailable" in str(replay["missing_data_explanation"]).lower()
    assert replay["manual_only_execution"] is True
    assert replay["preserved_engine_authority"] is True
    assert replay["narrative_quality"]["status"] == "WARN"
    assert replay["narrative_quality"]["missing_narrative_detected"] is True


def test_replay_vm_absent_event_renders_unavailable_without_inference() -> None:
    replay = build_decision_review_replay_vm(None).to_dict()

    assert replay["available"] is False
    assert "unavailable" in str(replay["unavailable_message"]).lower()
    assert replay["contract"] is None
    assert replay["trigger_state"] is None
    assert replay["final_decision"] is None
    assert replay["manual_only_execution"] is False
    assert replay["preserved_engine_authority"] is False
    assert replay["replay_reference_status"] == "unavailable"
    assert replay["replay_reference_source"] == "unknown"
    assert "No trigger readiness is inferred" in str(replay["readiness_explanation"])
    assert replay["narrative_quality"]["status"] == "FAIL"
    assert replay["narrative_quality"]["missing_narrative_detected"] is True


def test_replay_vm_marks_missing_replay_source_reference_unavailable() -> None:
    replay = build_decision_review_replay_vm(complete_audit_event()).to_dict()

    assert replay["replay_reference_available"] is False
    assert replay["replay_reference_status"] == "unavailable"
    assert replay["replay_reference_source"] == "unknown"
    assert replay["replay_reference_run_id"] is None
    assert "unavailable" in str(replay["replay_reference_message"]).lower()
    assert replay["narrative_quality"]["status"] == "WARN"
    assert replay["narrative_quality"]["replay_reference_present"] is False


def test_replay_vm_blocks_replay_source_reference_without_run_id() -> None:
    replay = build_decision_review_replay_vm(
        complete_audit_event(),
        audit_replay_record=audit_replay_record(last_run_id=None),
    ).to_dict()

    assert replay["replay_reference_available"] is False
    assert replay["replay_reference_status"] == "blocked"
    assert replay["replay_reference_run_id"] is None
    assert "run identifier is unavailable" in str(replay["replay_reference_message"])


def test_replay_vm_marks_source_reference_mismatch_without_changing_final_decision() -> None:
    replay = build_decision_review_replay_vm(
        complete_audit_event(final_decision="NO_TRADE"),
        audit_replay_record=audit_replay_record(last_final_decision="TRADE_APPROVED"),
    ).to_dict()

    assert replay["final_decision"] == "NO_TRADE"
    assert replay["replay_reference_status"] == "mismatch"
    assert replay["replay_reference_available"] is True
    assert replay["replay_reference_consistent"] is False
    assert "does not match" in str(replay["replay_reference_message"])


def test_replay_vm_includes_blocking_missing_stale_and_lockout_reasons_when_recorded() -> None:
    stale_replay = build_decision_review_replay_vm(
        complete_audit_event(
            trigger_state="STALE",
            blocking_reasons=("quote_stale", "stale_or_missing_timestamp:ES"),
            missing_fields=("market.current_price",),
            state_flags={"stale": True, "lockout": False, "blocked": True},
        )
    ).to_dict()

    assert stale_replay["stale"] is True
    assert stale_replay["lockout"] is False
    assert stale_replay["blocking_reasons"] == ["quote_stale", "stale_or_missing_timestamp:ES"]
    assert stale_replay["missing_fields"] == ["market.current_price"]
    assert "Fresh deterministic inputs are required" in str(stale_replay["readiness_explanation"])

    lockout_replay = build_decision_review_replay_vm(
        complete_audit_event(
            trigger_state="LOCKOUT",
            blocking_reasons=("event_lockout_active", "operator_event_lockout"),
            state_flags={"stale": False, "lockout": True, "blocked": True},
        )
    ).to_dict()

    assert lockout_replay["stale"] is False
    assert lockout_replay["lockout"] is True
    assert "event_lockout_active" in lockout_replay["blocking_reasons"]
    assert "operator_event_lockout" in str(lockout_replay["blocking_explanation"])


def test_replay_vm_excludes_sensitive_values_and_authorization_payloads() -> None:
    event = complete_audit_event(
        structural_notes=(
            "Authorization: Bearer BEARER_VALUE_PRIVATE_12345678901234567890 "
            "access_token=ACCESS_VALUE_PRIVATE refresh_token=REFRESH_VALUE_PRIVATE "
            "app_key=APP_KEY_PRIVATE app_secret=APP_SECRET_PRIVATE "
            "customerId=CUSTOMER_VALUE_PRIVATE correlId=CORREL_VALUE_PRIVATE "
            "accountNumber=ACCOUNT_VALUE_PRIVATE wss://stream-redaction.invalid/ws"
        ),
        blocking_reasons=(
            "Authorization: Bearer BEARER_VALUE_PRIVATE_12345678901234567890",
            "wss://stream-redaction.invalid/ws?token=ACCESS_VALUE_PRIVATE",
        ),
    )
    rendered = json.dumps(
        build_decision_review_replay_vm(
            event,
            audit_replay_record=audit_replay_record(
                source="Authorization: Bearer BEARER_VALUE_PRIVATE_12345678901234567890",
                last_run_id="ACCESS_VALUE_PRIVATE",
            ),
        ).to_dict(),
        sort_keys=True,
    )

    for value in SENSITIVE_VALUES:
        assert value not in rendered
    assert "[REDACTED" in rendered


def test_replay_vm_excludes_broker_order_fill_account_pnl_and_active_management_fields() -> None:
    event = complete_audit_event()
    event.update(
        {
            "broker": "do-not-include",
            "order": {"id": "do-not-include"},
            "fill": {"id": "do-not-include"},
            "account": "do-not-include",
            "pnl": 100,
            "move_stop": "do-not-include",
            "scale_out": "do-not-include",
        }
    )
    replay = build_decision_review_replay_vm(event).to_dict()
    rendered = json.dumps(replay, sort_keys=True).lower()
    keys = collect_keys(replay)

    for forbidden in ("broker", "order", "fill", "account", "pnl", "move_stop", "scale_out", "trailing_stop"):
        assert forbidden not in keys
        assert "do-not-include" not in rendered


def test_no_trade_replay_does_not_include_alternate_trade_suggestions() -> None:
    event = complete_audit_event(final_decision="NO_TRADE")
    event["pipeline_result"]["alternate_suggestion"] = "try another setup"
    replay = build_decision_review_replay_vm(event).to_dict()
    rendered = json.dumps(replay, sort_keys=True).lower()

    assert replay["final_decision"] == "NO_TRADE"
    assert "alternate_suggestion" not in rendered
    assert "try another setup" not in rendered


def test_query_ready_replay_preserves_engine_authority_and_manual_execution_language() -> None:
    replay = build_decision_review_replay_vm(complete_audit_event(trigger_state="QUERY_READY")).to_dict()
    rendered = json.dumps(replay, sort_keys=True)

    assert replay["trigger_state"] == "QUERY_READY"
    assert replay["manual_only_execution"] is True
    assert replay["preserved_engine_authority"] is True
    assert "The preserved pipeline must still decide" in rendered
    assert "execution remains manual" in rendered


def test_replay_text_has_no_execution_or_active_management_language() -> None:
    rendered = json.dumps(build_decision_review_replay_vm(complete_audit_event()).to_dict(), sort_keys=True).lower()

    for phrase in ("take the trade", "enter", "buy", "sell", "short now", "long now", "move stop", "scale out"):
        assert phrase not in rendered


def test_contract_universe_remains_final_targets_with_zn_and_gc_excluded() -> None:
    replay = build_decision_review_replay_vm(
        complete_audit_event(
            contract="MGC",
            setup_id="mgc_setup_1",
            trigger_id="mgc_trigger_1",
        )
    ).to_dict()
    rendered = json.dumps(replay, sort_keys=True)

    assert final_target_contracts() == ("ES", "NQ", "CL", "6E", "MGC")
    assert "ZN" not in final_target_contracts()
    assert "GC" not in final_target_contracts()
    assert replay["contract"] == "MGC"
    assert '"GC"' not in rendered
    assert "Micro Gold" not in rendered


def complete_audit_event(
    *,
    contract: str = "ES",
    setup_id: str = "es_setup_1",
    trigger_id: str = "es_trigger_1",
    trigger_state: str = "QUERY_READY",
    final_decision: str = "NO_TRADE",
    structural_notes: str = "ES choppy near VWAP; no clean structural anchor.",
    blocking_reasons: tuple[str, ...] = (),
    missing_fields: tuple[str, ...] = (),
    state_flags: dict[str, bool] | None = None,
) -> dict[str, object]:
    return build_decision_review_audit_event(
        decision_review=decision_review_panel(
            contract=contract,
            final_decision=final_decision,
            structural_notes=structural_notes,
        ),
        live_thesis_monitor=live_thesis_monitor(
            setup_id=setup_id,
            trigger_id=trigger_id,
            trigger_state=trigger_state,
            blocking_reasons=blocking_reasons,
            missing_fields=missing_fields,
            state_flags=state_flags,
        ),
        profile_id=f"preserved_{contract.lower()}_phase1",
        created_at=CREATED_AT,
        source="fixture",
    ).to_dict()


def audit_replay_record(
    *,
    source: str = "fixture_backed",
    replay_available: bool = True,
    last_run_id: str | None = "run-1",
    last_final_decision: str | None = "NO_TRADE",
    stage_e_live_backend: bool = False,
) -> dict[str, object]:
    return {
        "source": source,
        "stage_e_live_backend": stage_e_live_backend,
        "replay_available": replay_available,
        "last_run_id": last_run_id,
        "last_final_decision": last_final_decision,
    }


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
    return {
        "setup_id": setup_id,
        "trigger_id": trigger_id,
        "trigger_state": trigger_state,
        "distance_to_trigger_ticks": 0.0 if trigger_state == "QUERY_READY" else None,
        "missing_fields": list(missing_fields),
        "invalid_reasons": [],
        "blocking_reasons": list(blocking_reasons),
        "state_flags": state_flags or {"stale": False, "lockout": False, "blocked": bool(blocking_reasons)},
        "transition_narrative": {
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
        },
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
