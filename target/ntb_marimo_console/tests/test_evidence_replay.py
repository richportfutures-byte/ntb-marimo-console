from __future__ import annotations

import json
import uuid
from datetime import datetime

import pytest

from ntb_marimo_console.contract_universe import final_target_contracts
from ntb_marimo_console.evidence_replay import (
    ALLOWED_EVIDENCE_EVENT_TYPES,
    ALLOWED_EVIDENCE_SOURCES,
    EVIDENCE_EVENT_SCHEMA,
    REQUIRED_EVIDENCE_EVENT_FIELDS,
    build_replay_summary,
    create_evidence_event,
    parse_evidence_event,
    parse_evidence_events_jsonl,
    serialize_evidence_event,
    serialize_evidence_events_jsonl,
)


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
    "expectancy",
    "win_rate",
    "performance",
)


@pytest.mark.parametrize("contract", ("ES", "NQ", "CL", "6E", "MGC"))
def test_supported_contract_events_can_be_created_and_serialized(contract: str) -> None:
    event = evidence_event(contract=contract)
    payload = event.to_dict()

    assert event.valid is True
    assert payload["schema"] == EVIDENCE_EVENT_SCHEMA
    assert payload["contract"] == contract
    assert payload["source"] == "fixture"
    assert payload["event_type"] == "stream_connected"
    assert contract in final_target_contracts()
    assert json.loads(serialize_evidence_event(event))["event_id"] == event.event_id


def test_zn_is_excluded_legacy_and_cannot_be_final_supported_replay_target() -> None:
    event = evidence_event(contract="ZN")
    replay = build_replay_summary((event,), contract="ZN").to_dict()

    assert event.valid is False
    assert "contract_not_final_supported:ZN:legacy_historical_excluded" in event.invalid_reasons
    assert replay["status"] == "blocked"
    assert "replay_contract_not_final_supported:ZN:legacy_historical_excluded" in replay["blocking_reasons"]
    assert "ZN" not in final_target_contracts()


def test_gc_is_excluded_and_never_described_as_mgc() -> None:
    event = evidence_event(contract="GC")
    replay = build_replay_summary((event,), contract="GC").to_dict()
    rendered = json.dumps({"event": event.to_dict(), "replay": replay}, sort_keys=True)

    assert event.valid is False
    assert event.contract == "GC"
    assert "contract_not_final_supported:GC:never_supported_excluded" in event.invalid_reasons
    assert "MGC" not in rendered


def test_generated_event_id_is_uuid_string() -> None:
    event = create_evidence_event(
        contract="ES",
        profile_id="preserved_es_phase1",
        event_type="stream_connected",
        source="fixture",
        timestamp="2026-05-06T14:00:00+00:00",
    )

    assert str(uuid.UUID(event.event_id)) == event.event_id


def test_caller_supplied_event_id_and_timestamp_make_tests_deterministic() -> None:
    event = evidence_event(event_id="evt-fixed", timestamp="2026-05-06T14:00:00+00:00")

    assert event.event_id == "evt-fixed"
    assert event.timestamp == "2026-05-06T14:00:00+00:00"


def test_generated_timestamp_is_iso_formatted_and_timezone_aware() -> None:
    event = create_evidence_event(
        contract="ES",
        profile_id="preserved_es_phase1",
        event_type="stream_connected",
        source="fixture",
    )
    parsed = datetime.fromisoformat(event.timestamp)

    assert parsed.tzinfo is not None
    assert parsed.utcoffset() is not None


def test_required_record_fields_are_present() -> None:
    payload = evidence_event().to_dict()

    for field in REQUIRED_EVIDENCE_EVENT_FIELDS:
        assert field in payload


def test_missing_required_fields_fail_closed_on_parse() -> None:
    payload = evidence_event().to_dict()
    payload.pop("event_type")
    result = parse_evidence_event(payload)

    assert result.valid is False
    assert result.event is None
    assert "missing_required_field:event_type" in result.errors


def test_unsupported_event_type_fails_closed() -> None:
    event = evidence_event(event_type="trade_signal")

    assert event.valid is False
    assert "unsupported_event_type:trade_signal" in event.invalid_reasons
    assert "trade_signal" not in ALLOWED_EVIDENCE_EVENT_TYPES


def test_unsupported_source_fails_closed() -> None:
    event = evidence_event(source="broker")

    assert event.valid is False
    assert "unsupported_source:broker" in event.invalid_reasons
    assert "broker" not in ALLOWED_EVIDENCE_SOURCES


def test_json_serialization_and_parse_round_trip() -> None:
    event = evidence_event(event_type="operator_note_added", operator_note="Review only note.")
    result = parse_evidence_event(serialize_evidence_event(event))

    assert result.valid is True
    assert result.event is not None
    assert result.event.to_dict() == event.to_dict()


def test_jsonl_serialization_and_parsing_round_trip() -> None:
    events = (
        evidence_event(event_id="evt-1", event_type="stream_connected"),
        evidence_event(event_id="evt-2", event_type="trigger_query_ready", data_quality={"trigger_state": "QUERY_READY"}),
    )
    result = parse_evidence_events_jsonl(serialize_evidence_events_jsonl(events))

    assert result.valid is True
    assert tuple(event.event_id for event in result.events) == ("evt-1", "evt-2")
    assert result.errors == ()


def test_blank_and_malformed_jsonl_lines_fail_with_explicit_reasons() -> None:
    payload = serialize_evidence_event(evidence_event(event_id="evt-1")) + "\n\n{not-json}\n"
    result = parse_evidence_events_jsonl(payload)

    assert result.valid is False
    assert "line_2:blank_line" in result.errors
    assert any(error.startswith("line_3:malformed_json:") for error in result.errors)


def test_trigger_transition_replay_is_deterministic() -> None:
    events = sufficient_events()
    replay_a = build_replay_summary(events, contract="ES").to_dict()
    replay_b = build_replay_summary(events, contract="ES").to_dict()

    assert replay_a["trigger_transitions"] == replay_b["trigger_transitions"]
    assert [item["trigger_state"] for item in replay_a["trigger_transitions"]] == [
        "APPROACHING",
        "TOUCHED",
        "ARMED",
        "QUERY_READY",
    ]


def test_replay_reconstructs_sufficient_session_summary() -> None:
    replay = build_replay_summary(sufficient_events(), contract="ES", profile_id="preserved_es_phase1").to_dict()

    assert replay["status"] == "complete"
    assert replay["complete"] is True
    assert replay["morning_plan_reference"] == "premarket/ES/2026-05-06/brief.json"
    assert replay["stream_state"]["state"] == "connected"
    assert replay["stream_state"]["subscription_count"] == 1
    assert replay["query_eligibility_events"][-1]["event_type"] == "query_submitted"
    assert replay["query_eligibility_events"][-1]["manual_query_allowed"] is True
    assert replay["pipeline_results"][0]["pipeline_run_id"] == "run-1"
    assert replay["pipeline_results"][0]["summary"]["final_decision"] == "NO_TRADE"
    assert replay["operator_notes"][0]["operator_note"] == "Operator review note."
    assert replay["replay_authority"] == "review_only_no_trade_authorization"
    assert replay["replay_can_authorize_trades"] is False


def test_replay_marks_incomplete_when_required_evidence_is_missing() -> None:
    replay = build_replay_summary(
        (evidence_event(event_type="stream_connected", premarket_brief_ref=None),),
        contract="ES",
    ).to_dict()

    assert replay["status"] == "incomplete"
    assert replay["complete"] is False
    assert "premarket_brief_ref_missing" in replay["incomplete_reasons"]
    assert "trigger_transition_evidence_missing" in replay["incomplete_reasons"]


def test_replay_blocks_pipeline_result_without_prior_query_submitted() -> None:
    result_event = evidence_event(
        event_id="evt-pipeline",
        event_type="pipeline_result",
        pipeline_run_id="run-1",
        data_quality={"pipeline_summary": {"contract": "ES", "final_decision": "NO_TRADE"}},
    )
    replay = build_replay_summary((result_event,), contract="ES").to_dict()

    assert replay["status"] == "blocked"
    assert "pipeline_result_without_prior_query_submitted:evt-pipeline" in replay["blocking_reasons"]


def test_replay_blocks_query_submitted_without_prior_query_ready_or_gate_enabled() -> None:
    query_event = evidence_event(event_id="evt-query", event_type="query_submitted", pipeline_run_id="run-1")
    replay = build_replay_summary((query_event,), contract="ES").to_dict()

    assert replay["status"] == "blocked"
    assert "query_submitted_without_query_ready_or_gate_enabled:evt-query" in replay["blocking_reasons"]


def test_replay_blocks_cross_contract_evidence_bleed() -> None:
    replay = build_replay_summary((evidence_event(contract="ES"),), contract="NQ").to_dict()

    assert replay["status"] == "blocked"
    assert "cross_contract_evidence:ES->NQ" in replay["blocking_reasons"]


def test_synthetic_or_fixture_evidence_is_never_labeled_as_live_stream() -> None:
    synthetic_live = evidence_event(source="live_stream", synthetic=True)
    fixture_event = evidence_event(source="fixture", synthetic=False)

    assert synthetic_live.valid is False
    assert "synthetic_event_cannot_be_live_stream" in synthetic_live.invalid_reasons
    assert fixture_event.source == "fixture"
    assert fixture_event.synthetic is False


def test_no_synthetic_replay_appears_as_real() -> None:
    replay = build_replay_summary(sufficient_events(), contract="ES").to_dict()

    assert replay["source_integrity"]["synthetic_replay_labeled_real"] is False
    assert replay["synthetic_replay_labeled_real"] is False


def test_sensitive_values_are_redacted_from_event_and_replay_output() -> None:
    event = evidence_event(
        operator_note=(
            "Authorization: Bearer BEARER_VALUE_PRIVATE_12345678901234567890 "
            "access_token=ACCESS_VALUE_PRIVATE refresh_token=REFRESH_VALUE_PRIVATE "
            "customerId=CUSTOMER_VALUE_PRIVATE correlId=CORREL_VALUE_PRIVATE "
            "accountNumber=ACCOUNT_VALUE_PRIVATE wss://stream-redaction.invalid/ws"
        ),
        data_quality={
            "status": "token=ACCESS_VALUE_PRIVATE",
            "blocking_reasons": ["Authorization: Bearer BEARER_VALUE_PRIVATE_12345678901234567890"],
        },
    )
    replay = build_replay_summary((event,), contract="ES").to_dict()
    rendered = json.dumps({"event": event.to_dict(), "replay": replay}, sort_keys=True)

    for value in SENSITIVE_VALUES:
        assert value not in rendered
    assert "[REDACTED" in rendered


def test_no_broker_order_account_fill_pnl_fields_are_introduced() -> None:
    rendered = json.dumps(
        {
            "event": evidence_event().to_dict(),
            "replay": build_replay_summary(sufficient_events(), contract="ES").to_dict(),
        },
        sort_keys=True,
    ).lower()
    keys = collect_keys(json.loads(rendered))

    for forbidden in FORBIDDEN_KEYS:
        assert forbidden not in keys
        assert f'"{forbidden}"' not in rendered


def test_replay_does_not_bypass_r13_query_gate() -> None:
    query_event = evidence_event(
        event_id="evt-query",
        event_type="query_submitted",
        pipeline_run_id="run-1",
        data_quality={"gate_enabled": False, "manual_query_allowed": False},
    )
    replay = build_replay_summary((query_event,), contract="ES").to_dict()

    assert replay["status"] == "blocked"
    assert "query_submitted_without_query_ready_or_gate_enabled:evt-query" in replay["blocking_reasons"]
    assert replay["replay_can_authorize_trades"] is False


def test_replay_does_not_infer_unavailable_macro_or_order_flow_data() -> None:
    event = evidence_event(
        contract="MGC",
        data_quality={
            "blocking_reasons": [
                "cross_asset.dxy unavailable",
                "cross_asset.cash_10y_yield unavailable",
                "macro_context.fear_catalyst_state unavailable",
                "order_flow.footprint unavailable",
                "order_flow.dom unavailable",
                "order_flow.sweep unavailable",
                "order_flow.cumulative_delta unavailable",
                "order_flow.aggressive_order_flow unavailable",
            ],
        },
    )
    replay = build_replay_summary((event,), contract="MGC").to_dict()
    rendered = json.dumps({"event": event.to_dict(), "replay": replay}, sort_keys=True).lower()

    assert "dxy_value" not in rendered
    assert "yield_value" not in rendered
    assert "fear_catalyst_value" not in rendered
    assert "footprint_value" not in rendered
    assert "dom_value" not in rendered
    assert "sweep_value" not in rendered
    assert "cumulative_delta_value" not in rendered
    assert "aggressive_order_flow_value" not in rendered


def test_timestamp_invalid_and_impossible_ordering_block_replay() -> None:
    invalid_timestamp = evidence_event(event_id="evt-invalid-time", timestamp="2026-05-06T14:00:00")
    later = evidence_event(event_id="evt-late", timestamp="2026-05-06T14:02:00+00:00")
    earlier = evidence_event(event_id="evt-early", timestamp="2026-05-06T14:01:00+00:00")
    replay = build_replay_summary((invalid_timestamp, later, earlier), contract="ES").to_dict()

    assert replay["status"] == "blocked"
    assert "timestamp_invalid:evt-invalid-time" in replay["blocking_reasons"]
    assert "event_ordering_invalid" in replay["blocking_reasons"]


def evidence_event(
    *,
    contract: str = "ES",
    profile_id: str = "preserved_es_phase1",
    event_id: str = "evt-1",
    timestamp: str = "2026-05-06T14:00:00+00:00",
    event_type: str = "stream_connected",
    source: str = "fixture",
    setup_id: str | None = "es_setup_1",
    trigger_id: str | None = "es_trigger_1",
    live_snapshot_ref: str | None = "observables/ES/trigger_true.json",
    premarket_brief_ref: str | None = "premarket/ES/2026-05-06/brief.json",
    pipeline_run_id: str | None = None,
    operator_note: str | None = None,
    data_quality: dict[str, object] | None = None,
    synthetic: bool = False,
) -> object:
    return create_evidence_event(
        contract=contract,
        profile_id=profile_id,
        event_id=event_id,
        timestamp=timestamp,
        event_type=event_type,
        source=source,
        setup_id=setup_id,
        trigger_id=trigger_id,
        live_snapshot_ref=live_snapshot_ref,
        premarket_brief_ref=premarket_brief_ref,
        pipeline_run_id=pipeline_run_id,
        operator_note=operator_note,
        data_quality=data_quality or {"state": "ready"},
        synthetic=synthetic,
    )


def sufficient_events() -> tuple[object, ...]:
    return (
        evidence_event(event_id="evt-1", timestamp="2026-05-06T14:00:00+00:00", event_type="stream_connected"),
        evidence_event(event_id="evt-2", timestamp="2026-05-06T14:00:01+00:00", event_type="subscription_added"),
        evidence_event(
            event_id="evt-3",
            timestamp="2026-05-06T14:00:02+00:00",
            event_type="trigger_approaching",
            data_quality={"trigger_state": "APPROACHING"},
        ),
        evidence_event(
            event_id="evt-4",
            timestamp="2026-05-06T14:00:03+00:00",
            event_type="trigger_touched",
            data_quality={"trigger_state": "TOUCHED"},
        ),
        evidence_event(
            event_id="evt-5",
            timestamp="2026-05-06T14:00:04+00:00",
            event_type="trigger_armed",
            data_quality={"trigger_state": "ARMED"},
        ),
        evidence_event(
            event_id="evt-6",
            timestamp="2026-05-06T14:00:05+00:00",
            event_type="trigger_query_ready",
            data_quality={"trigger_state": "QUERY_READY", "gate_enabled": True, "manual_query_allowed": True},
        ),
        evidence_event(
            event_id="evt-7",
            timestamp="2026-05-06T14:00:06+00:00",
            event_type="query_submitted",
            pipeline_run_id="run-1",
            data_quality={"gate_enabled": True, "manual_query_allowed": True},
        ),
        evidence_event(
            event_id="evt-8",
            timestamp="2026-05-06T14:00:07+00:00",
            event_type="pipeline_result",
            pipeline_run_id="run-1",
            data_quality={
                "pipeline_summary": {
                    "contract": "ES",
                    "termination_stage": "contract_market_read",
                    "final_decision": "NO_TRADE",
                    "sufficiency_gate_status": "READY",
                    "contract_analysis_outcome": "NO_TRADE",
                    "proposed_setup_outcome": None,
                    "risk_authorization_decision": "BLOCKED",
                }
            },
        ),
        evidence_event(
            event_id="evt-9",
            timestamp="2026-05-06T14:00:08+00:00",
            event_type="operator_note_added",
            source="manual",
            operator_note="Operator review note.",
        ),
    )


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
