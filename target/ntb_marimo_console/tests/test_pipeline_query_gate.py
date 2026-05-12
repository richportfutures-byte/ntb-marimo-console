from __future__ import annotations

import json

import pytest

from ntb_marimo_console.contract_universe import final_target_contracts
from ntb_marimo_console.pipeline_query_gate import (
    PIPELINE_QUERY_GATE_SCHEMA,
    PipelineQueryGateRequest,
    evaluate_pipeline_query_gate,
)
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
FORBIDDEN_OUTPUT_KEYS = (
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
)


@pytest.mark.parametrize("contract", ("ES", "NQ", "CL", "6E", "MGC"))
def test_enabled_gate_for_final_supported_contracts_when_all_inputs_ready(contract: str) -> None:
    gate = evaluate_pipeline_query_gate(ready_request(contract))

    assert gate.enabled is True
    assert gate.pipeline_query_authorized is True
    assert gate.status == "ENABLED"
    assert gate.contract == contract
    assert gate.trigger_state == "QUERY_READY"
    assert gate.profile_id == f"preserved_{contract.lower()}_phase1"
    assert gate.disabled_reasons == ()
    assert tuple(gate.to_dict()["enabled_reasons"]) == tuple(gate.to_dict()["required_conditions"])
    assert contract in final_target_contracts()


@pytest.mark.parametrize(
    ("contract", "expected_reason"),
    (
        ("ZN", "excluded_contract:ZN"),
        ("GC", "excluded_contract:GC"),
        ("YM", "unsupported_contract:YM"),
    ),
)
def test_contract_universe_blocks_excluded_gc_and_unsupported_contracts(contract: str, expected_reason: str) -> None:
    gate = evaluate_pipeline_query_gate(ready_request(contract))

    assert gate.enabled is False
    assert gate.pipeline_query_authorized is False
    assert expected_reason in gate.blocking_reasons
    assert "contract_final_supported" in gate.missing_conditions
    assert "ZN" not in final_target_contracts()
    assert "GC" not in final_target_contracts()


def test_support_matrix_mismatch_blocks_even_for_final_supported_contract() -> None:
    gate = evaluate_pipeline_query_gate(ready_request("ES", support_matrix_final_supported=False))

    assert gate.enabled is False
    assert "support_matrix_mismatch:ES" in gate.blocking_reasons


@pytest.mark.parametrize(
    ("override", "expected_reason", "missing_condition"),
    (
        ({"profile_preflight_passed": False}, "profile_preflight_failed", "runtime_profile_preflight_passed"),
        ({"profile_exists": False}, "runtime_profile_unavailable", "runtime_profile_preflight_passed"),
        ({"watchman_validator_status": "NEEDS_REVIEW"}, "watchman_validator_not_ready:NEEDS_REVIEW", "watchman_validator_ready"),
        ({"live_snapshot_fresh": False}, "live_snapshot_stale", "live_snapshot_fresh"),
        ({"quote_fresh": False}, "quote_stale", "quote_fresh"),
        ({"bars_fresh": False}, "bars_stale", "bars_fresh_and_available"),
        ({"bars_available": False}, "bars_missing", "bars_fresh_and_available"),
        ({"required_trigger_fields_present": False}, "missing_required_trigger_fields", "required_trigger_fields_present"),
        ({"event_lockout_active": True}, "event_lockout_active", "event_lockout_inactive"),
        ({"session_valid": False}, "session_invalid", "session_valid"),
    ),
)
def test_gate_disables_with_explicit_reasons_for_higher_level_failures(
    override: dict[str, object],
    expected_reason: str,
    missing_condition: str,
) -> None:
    gate = evaluate_pipeline_query_gate(ready_request("ES", **override))

    assert gate.enabled is False
    assert gate.pipeline_query_authorized is False
    assert expected_reason in gate.blocking_reasons
    assert missing_condition in gate.missing_conditions


@pytest.mark.parametrize("provider_status", ("disconnected", "stale", "error", "disabled"))
def test_provider_state_disconnected_stale_or_error_blocks(provider_status: str) -> None:
    gate = evaluate_pipeline_query_gate(ready_request("ES", provider_status=provider_status))

    assert gate.enabled is False
    assert f"provider_status_blocked:{provider_status}" in gate.blocking_reasons
    assert "provider_ready" in gate.missing_conditions


@pytest.mark.parametrize("stream_status", ("disconnected", "stale", "error", "blocked"))
def test_stream_state_disconnected_stale_or_error_blocks(stream_status: str) -> None:
    gate = evaluate_pipeline_query_gate(ready_request("ES", stream_status=stream_status))

    assert gate.enabled is False
    assert f"stream_status_blocked:{stream_status}" in gate.blocking_reasons
    assert "stream_ready" in gate.missing_conditions


@pytest.mark.parametrize("fixture_mode_accepted", (False, True))
def test_fixture_mode_satisfies_provider_and_stream_only_when_explicitly_accepted(
    fixture_mode_accepted: bool,
) -> None:
    gate = evaluate_pipeline_query_gate(
        ready_request(
            "ES",
            provider_status="fixture",
            stream_status="fixture",
            fixture_mode_accepted=fixture_mode_accepted,
        )
    )

    assert gate.enabled is fixture_mode_accepted
    assert gate.pipeline_query_authorized is fixture_mode_accepted
    if not fixture_mode_accepted:
        assert "provider_status_blocked:disabled" in gate.blocking_reasons
        assert "stream_status_blocked:fixture" in gate.blocking_reasons


@pytest.mark.parametrize(
    "trigger_state",
    (
        TriggerState.INVALIDATED,
        TriggerState.BLOCKED,
        TriggerState.UNAVAILABLE,
        TriggerState.STALE,
        TriggerState.LOCKOUT,
        TriggerState.ERROR,
        TriggerState.DORMANT,
        TriggerState.APPROACHING,
        TriggerState.TOUCHED,
        TriggerState.ARMED,
    ),
)
def test_non_query_ready_trigger_states_disable_gate(trigger_state: TriggerState) -> None:
    gate = evaluate_pipeline_query_gate(ready_request("ES", trigger_state=trigger_result("ES", trigger_state)))

    assert gate.enabled is False
    assert gate.pipeline_query_authorized is False
    assert f"trigger_state_not_query_ready:{trigger_state.value}" in gate.blocking_reasons
    assert "trigger_state_query_ready" in gate.missing_conditions


def test_query_ready_does_not_enable_when_higher_level_gate_condition_fails() -> None:
    gate = evaluate_pipeline_query_gate(
        ready_request(
            "ES",
            trigger_state=trigger_result("ES", TriggerState.QUERY_READY),
            watchman_validator_status="FAILED",
            stream_status="stale",
            event_lockout_active=True,
        )
    )

    assert gate.trigger_state == "QUERY_READY"
    assert gate.enabled is False
    assert gate.pipeline_query_authorized is False
    assert "watchman_validator_not_ready:FAILED" in gate.blocking_reasons
    assert "stream_status_blocked:stale" in gate.blocking_reasons
    assert "event_lockout_active" in gate.blocking_reasons


def test_live_snapshot_quality_blocks_stale_quote_and_missing_required_fields() -> None:
    gate = evaluate_pipeline_query_gate(
        ready_request(
            "ES",
            live_snapshot=live_snapshot(
                "ES",
                ready=False,
                fresh=False,
                required_fields_present=False,
                blocking_reasons=("stale_or_missing_timestamp:ES", "missing_required_fields:ES:bid,last"),
            ),
            live_snapshot_fresh=None,
            quote_fresh=None,
            required_trigger_fields_present=None,
        )
    )

    assert gate.enabled is False
    assert "live_snapshot_stale" in gate.blocking_reasons
    assert "quote_stale" in gate.blocking_reasons
    assert "live_observable_required_fields_missing" in gate.blocking_reasons
    assert "stale_or_missing_timestamp:ES" in gate.blocking_reasons


def test_missing_contract_observable_blocks_fail_closed() -> None:
    gate = evaluate_pipeline_query_gate(
        ready_request(
            "NQ",
            live_snapshot=live_snapshot("ES"),
            live_snapshot_fresh=None,
            quote_fresh=None,
            required_trigger_fields_present=None,
        )
    )

    assert gate.enabled is False
    assert "quote_stale" in gate.blocking_reasons
    assert "live_observable_required_fields_missing" in gate.blocking_reasons
    assert "missing_contract_observable:NQ" in gate.blocking_reasons


def test_required_trigger_fields_missing_from_trigger_result_are_reported() -> None:
    gate = evaluate_pipeline_query_gate(
        ready_request(
            "ES",
            trigger_state=trigger_result(
                "ES",
                TriggerState.BLOCKED,
                missing_fields=("market.cumulative_delta", "cross_asset.breadth.current_advancers_pct"),
                blocking_reasons=("missing_required_live_fields",),
            ),
        )
    )

    assert gate.enabled is False
    assert "missing_required_trigger_fields" in gate.blocking_reasons
    assert "missing_trigger_field:market.cumulative_delta" in gate.blocking_reasons
    assert "missing_trigger_field:cross_asset.breadth.current_advancers_pct" in gate.blocking_reasons
    assert "trigger_blocked" in gate.blocking_reasons


def test_unsupported_live_field_dependency_blocks_query_gate() -> None:
    gate = evaluate_pipeline_query_gate(
        ready_request(
            "MGC",
            unsupported_live_field_dependencies=("unsupported.dom.depth",),
        )
    )

    assert gate.enabled is False
    assert "unsupported_live_field_dependency" in gate.blocking_reasons
    assert "unsupported_live_field_dependency:unsupported.dom.depth" in gate.blocking_reasons
    assert gate.contract == "MGC"
    assert "GC" not in gate.trigger_id


def test_output_is_serializable_and_has_stable_shape() -> None:
    payload = evaluate_pipeline_query_gate(ready_request("CL")).to_dict()

    encoded = json.dumps(payload, sort_keys=True)
    decoded = json.loads(encoded)

    assert decoded["schema"] == PIPELINE_QUERY_GATE_SCHEMA
    assert decoded["contract"] == "CL"
    assert decoded["enabled"] is True
    assert decoded["pipeline_query_authorized"] is True
    assert decoded["query_scope"] == "operator_initiated_preserved_pipeline_query"
    assert decoded["pipeline_result_source"] == "engine_derived"


def test_output_contains_no_broker_order_account_fill_pnl_or_separate_decision_authority_fields() -> None:
    payload = evaluate_pipeline_query_gate(ready_request("ES")).to_dict()
    rendered = json.dumps(payload, sort_keys=True).lower()

    for key in FORBIDDEN_OUTPUT_KEYS:
        assert key not in payload
        assert f'"{key}"' not in rendered
    assert payload["decision_authority"] == "preserved_engine_only"
    assert payload["pipeline_query_authorized"] is True


def test_sensitive_values_are_redacted_from_output() -> None:
    gate = evaluate_pipeline_query_gate(
        ready_request(
            "ES",
            provider_status="error",
            stream_status="Authorization: Bearer BEARER_VALUE_PRIVATE_12345678901234567890",
            unsupported_live_field_dependencies=(
                "access_token=ACCESS_VALUE_PRIVATE refresh_token=REFRESH_VALUE_PRIVATE",
                "customerId=CUSTOMER_VALUE_PRIVATE correlId=CORREL_VALUE_PRIVATE accountNumber=ACCOUNT_VALUE_PRIVATE",
                "wss://stream-redaction.invalid/ws?credential=hidden",
            ),
        )
    )
    rendered = json.dumps(gate.to_dict(), sort_keys=True)

    for value in SENSITIVE_VALUES:
        assert value not in rendered
    assert "[REDACTED" in rendered


def test_trigger_state_from_real_producer_flag_propagates_into_gate_result_and_to_dict() -> None:
    real = evaluate_pipeline_query_gate(
        ready_request("ES", trigger_state_from_real_producer=True)
    )
    synthetic = evaluate_pipeline_query_gate(
        ready_request(
            "ES",
            trigger_state=trigger_result(
                "ES",
                TriggerState.UNAVAILABLE,
                blocking_reasons=("trigger_state_result_unavailable",),
            ),
            trigger_state_from_real_producer=False,
        )
    )

    assert real.trigger_state_from_real_producer is True
    assert real.to_dict()["trigger_state_from_real_producer"] is True
    assert synthetic.trigger_state_from_real_producer is False
    assert synthetic.to_dict()["trigger_state_from_real_producer"] is False
    assert synthetic.enabled is False
    assert "trigger_state_not_query_ready:UNAVAILABLE" in synthetic.blocking_reasons


@pytest.mark.parametrize("synthetic_state", (TriggerState.QUERY_READY, "QUERY_READY"))
def test_synthetic_query_ready_state_does_not_enable_gate(synthetic_state: object) -> None:
    gate = evaluate_pipeline_query_gate(
        ready_request(
            "ES",
            trigger_state=synthetic_state,
            trigger_state_from_real_producer=False,
        )
    )

    assert gate.enabled is False
    assert gate.pipeline_query_authorized is False
    assert gate.trigger_state == "QUERY_READY"
    assert gate.trigger_state_from_real_producer is False
    assert "trigger_state_not_from_real_producer" in gate.blocking_reasons
    assert "trigger_state_query_ready" in gate.missing_conditions


def test_query_ready_result_still_requires_real_producer_provenance_flag() -> None:
    gate = evaluate_pipeline_query_gate(
        ready_request("ES", trigger_state_from_real_producer=False)
    )

    assert gate.enabled is False
    assert gate.pipeline_query_authorized is False
    assert gate.trigger_state == "QUERY_READY"
    assert "trigger_state_not_from_real_producer" in gate.blocking_reasons


def test_no_fixture_fallback_after_live_failure_semantics_are_not_weakened() -> None:
    live_failure = evaluate_pipeline_query_gate(
        ready_request(
            "ES",
            provider_status="error",
            stream_status="error",
            fixture_mode_accepted=True,
        )
    )
    explicit_fixture = evaluate_pipeline_query_gate(
        ready_request(
            "ES",
            provider_status="fixture",
            stream_status="fixture",
            fixture_mode_accepted=True,
        )
    )

    assert live_failure.enabled is False
    assert "provider_status_blocked:error" in live_failure.blocking_reasons
    assert "stream_status_blocked:error" in live_failure.blocking_reasons
    assert explicit_fixture.enabled is True


def ready_request(contract: str, **overrides: object) -> PipelineQueryGateRequest:
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
    return PipelineQueryGateRequest(**values)  # type: ignore[arg-type]


def trigger_result(
    contract: str,
    state: TriggerState,
    *,
    missing_fields: tuple[str, ...] = (),
    blocking_reasons: tuple[str, ...] = (),
) -> TriggerStateResult:
    return TriggerStateResult(
        contract=contract,
        setup_id=f"{contract.lower()}_setup",
        trigger_id=f"{contract.lower()}_trigger",
        state=state,
        distance_to_trigger_ticks=0.0 if state == TriggerState.QUERY_READY else None,
        required_fields=("market.current_price",),
        missing_fields=missing_fields,
        invalid_reasons=(),
        blocking_reasons=blocking_reasons,
        last_updated="2026-05-06T14:00:00+00:00",
    )


def live_snapshot(
    contract: str,
    *,
    ready: bool = True,
    fresh: bool = True,
    required_fields_present: bool = True,
    blocking_reasons: tuple[str, ...] = (),
) -> dict[str, object]:
    return {
        "schema": "live_observable_snapshot_v2",
        "generated_at": "2026-05-06T14:00:00+00:00",
        "provider": "fixture",
        "provider_status": "connected",
        "contracts": {
            contract: {
                "contract": contract,
                "symbol": f"/{contract}M26",
                "quote": {
                    "bid": 1.0,
                    "ask": 1.25,
                    "last": 1.125,
                    "quote_time": "2026-05-06T13:59:58+00:00",
                    "trade_time": "2026-05-06T13:59:58+00:00",
                    "quote_age_seconds": 2.0,
                    "trade_age_seconds": 2.0,
                },
                "quality": {
                    "fresh": fresh,
                    "symbol_match": True,
                    "required_fields_present": required_fields_present,
                    "blocking_reasons": list(blocking_reasons),
                },
            }
        },
        "data_quality": {"ready": ready, "blocking_reasons": []},
    }
