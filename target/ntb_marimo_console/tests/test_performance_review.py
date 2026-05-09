from __future__ import annotations

import json

import pytest

from ntb_marimo_console.contract_universe import final_target_contracts
from ntb_marimo_console.performance_review import (
    FAILURE_TAXONOMY_CATEGORIES,
    METRIC_IDS,
    ReviewInput,
    build_performance_review_summary,
    classify_failure_taxonomy,
    create_manual_outcome_record,
    create_system_decision_record,
    parse_manual_outcome_record,
    serialize_performance_review_summary,
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
)


def test_builds_review_summary_from_fixture_evidence_and_replay_records() -> None:
    summary = review_summary().to_dict()

    assert summary["schema"] == "performance_review_v1"
    assert summary["contract"] == "ES"
    assert summary["status"] == "ready"
    assert summary["review_scope"] == "post_session_fixture_or_manual_review_only"
    assert summary["ui_wiring_status"] == "deferred_no_app_or_notebook_wiring_in_r16_foundation"
    assert summary["data_sufficiency_failures"][0]["failure_category"] == "data_sufficiency_failure"


def test_distinguishes_system_decision_quality_from_trader_execution_quality() -> None:
    summary = review_summary().to_dict()

    assert summary["system_decision_quality"]["record_count"] == 4
    assert summary["system_decision_quality"]["no_trade_count"] == 2
    assert "does not judge trader execution" in summary["system_decision_quality"]["review_statement"]
    assert summary["trader_execution_quality"]["manual_outcome_count"] == 2
    assert summary["trader_execution_quality"]["executed_count"] == 2
    assert "manually supplied" in summary["trader_execution_quality"]["review_statement"]


def test_no_trade_rate_is_computed_and_not_automatic_failure() -> None:
    summary = review_summary(system_decisions=system_decisions(count=20, no_trade_count=10), manual_outcomes=manual_outcomes(20)).to_dict()
    metric = metric_by_id(summary, "no_trade_rate")
    low_no_trade_rule = rule_by_id(summary, "low_no_trade_rate")

    assert metric["status"] == "computed"
    assert metric["value"] == 0.5
    assert low_no_trade_rule["triggered"] is False


def test_trigger_to_query_and_query_to_approval_rates_from_replay_query_events() -> None:
    summary = review_summary(
        system_decisions=(
            decision("sys-1", trigger_query_ready=True, query_submitted=True, final_decision="NO_TRADE"),
            decision("sys-2", trigger_query_ready=True, query_submitted=False, final_decision="NO_TRADE"),
            decision("sys-3", trigger_query_ready=True, query_submitted=True, final_decision="TRADE_APPROVED"),
        ),
        minimum_sample_size=2,
    ).to_dict()

    assert metric_by_id(summary, "trigger_to_query_rate")["value"] == pytest.approx(2 / 3)
    assert metric_by_id(summary, "query_to_approval_rate")["value"] == pytest.approx(1 / 2)


def test_approval_to_execution_requires_manual_execution_outcome_records() -> None:
    without_manual = review_summary(system_decisions=(decision("sys-1", final_decision="TRADE_APPROVED", pipeline_run_id="run-1", query_submitted=True),), manual_outcomes=()).to_dict()
    with_manual = review_summary(system_decisions=(decision("sys-1", final_decision="TRADE_APPROVED", pipeline_run_id="run-1", query_submitted=True),), manual_outcomes=(outcome("out-1", pipeline_run_id="run-1", executed=True),), minimum_sample_size=1).to_dict()

    assert metric_by_id(without_manual, "approval_to_execution_rate")["status"] == "unavailable"
    assert "manual_execution_outcome_records_required" in metric_by_id(without_manual, "approval_to_execution_rate")["reasons"]
    assert metric_by_id(with_manual, "approval_to_execution_rate")["status"] == "computed"
    assert metric_by_id(with_manual, "approval_to_execution_rate")["value"] == 1.0


def test_win_rate_and_expectancy_unavailable_when_outcomes_are_missing() -> None:
    summary = review_summary(manual_outcomes=()).to_dict()

    assert metric_by_id(summary, "win_rate")["status"] == "unavailable"
    assert metric_by_id(summary, "expectancy")["status"] == "unavailable"
    assert summary["sample_size_assessment"]["status"] == "unavailable"


def test_win_rate_and_expectancy_are_insufficient_sample_below_threshold() -> None:
    summary = review_summary(manual_outcomes=(outcome("out-1", outcome_r=1), outcome("out-2", outcome_r=-1)), minimum_sample_size=20).to_dict()

    assert metric_by_id(summary, "win_rate")["status"] == "insufficient_sample"
    assert metric_by_id(summary, "expectancy")["status"] == "insufficient_sample"
    assert summary["sample_size_assessment"]["status"] == "insufficient_sample"


def test_metrics_do_not_claim_edge_before_sufficient_sample_size() -> None:
    summary = review_summary(manual_outcomes=(outcome("out-1", outcome_r=5),), minimum_sample_size=20).to_dict()

    assert summary["edge_claim_allowed"] is False
    assert summary["sample_size_assessment"]["edge_claim_allowed"] is False
    for metric in summary["metrics"]:
        assert metric["edge_claim"] == "none"


def test_mfe_mae_rr_slippage_and_hold_time_unavailable_unless_manually_supplied() -> None:
    missing = review_summary(manual_outcomes=(outcome("out-1", mfe_r=None, mae_r=None, realized_rr=None, slippage_ticks=None, hold_minutes=None),)).to_dict()
    supplied = review_summary(manual_outcomes=(outcome("out-1", mfe_r=2, mae_r=-1, realized_rr=1.5, slippage_ticks=1, hold_minutes=12),), minimum_sample_size=1).to_dict()

    for metric_id in ("mfe", "mae", "realized_rr", "slippage", "hold_time"):
        assert metric_by_id(missing, metric_id)["status"] == "unavailable"
        assert metric_by_id(supplied, metric_id)["status"] == "computed"


def test_failure_taxonomy_accepts_only_known_categories_and_fails_closed() -> None:
    valid = classify_failure_taxonomy("risk_gate_failure")
    invalid = classify_failure_taxonomy("unknown_edge_case")

    assert valid.valid is True
    assert valid.category in FAILURE_TAXONOMY_CATEGORIES
    assert invalid.valid is False
    assert "unknown_failure_taxonomy:unknown_edge_case" in invalid.reasons


def test_pause_rule_triggers_for_risk_gate_bypass() -> None:
    summary = review_summary(system_decisions=(decision("sys-1", risk_gate_bypassed=True),)).to_dict()

    assert rule_by_id(summary, "risk_gate_bypass")["triggered"] is True
    assert rule_by_id(summary, "risk_gate_bypass")["cannot_authorize_execution"] is True


def test_pause_rule_triggers_for_fake_ready_state() -> None:
    summary = review_summary(system_decisions=(decision("sys-1", fake_ready_state=True),)).to_dict()

    assert rule_by_id(summary, "fake_ready_state")["triggered"] is True


def test_pause_rule_triggers_for_unsupported_contract_appears_ready() -> None:
    unsupported = create_system_decision_record(
        record_id="sys-zn",
        timestamp="2026-05-06T14:00:00+00:00",
        contract="ZN",
        profile_id="preserved_zn_phase1",
        final_decision="NO_TRADE",
        unsupported_contract_ready=True,
    )
    summary = review_summary(system_decisions=(unsupported,)).to_dict()

    assert rule_by_id(summary, "unsupported_contract_appears_ready")["triggered"] is True
    assert "ZN" not in final_target_contracts()


def test_pause_rule_triggers_for_low_no_trade_rate_only_when_sample_is_sufficient() -> None:
    insufficient = review_summary(system_decisions=system_decisions(count=5, no_trade_count=0), minimum_sample_size=20).to_dict()
    sufficient = review_summary(system_decisions=system_decisions(count=20, no_trade_count=7), minimum_sample_size=20).to_dict()

    assert rule_by_id(insufficient, "low_no_trade_rate")["triggered"] is False
    assert "requires sufficient sample" in rule_by_id(insufficient, "low_no_trade_rate")["reason"]
    assert rule_by_id(sufficient, "low_no_trade_rate")["triggered"] is True


def test_rolling_20_trade_expectancy_rule_does_not_trigger_before_20_records() -> None:
    summary = review_summary(manual_outcomes=tuple(outcome(f"out-{index}", outcome_r=-1) for index in range(19))).to_dict()

    assert rule_by_id(summary, "rolling_20_expectancy_below_threshold")["triggered"] is False
    assert "requires 20" in rule_by_id(summary, "rolling_20_expectancy_below_threshold")["reason"]


def test_rolling_20_trade_expectancy_rule_triggers_at_20_records_below_threshold() -> None:
    summary = review_summary(manual_outcomes=tuple(outcome(f"out-{index}", outcome_r=-0.25) for index in range(20))).to_dict()

    assert rule_by_id(summary, "rolling_20_expectancy_below_threshold")["triggered"] is True
    assert len(rule_by_id(summary, "rolling_20_expectancy_below_threshold")["supporting_record_ids"]) == 20


def test_five_consecutive_losses_trigger_only_for_same_reviewed_supported_contract() -> None:
    mixed = tuple(outcome(f"out-es-{index}", outcome_r=-1) for index in range(4)) + (outcome("out-nq", contract="NQ", outcome_r=-1),)
    same = tuple(outcome(f"out-es-{index}", outcome_r=-1) for index in range(5))

    assert rule_by_id(review_summary(manual_outcomes=mixed).to_dict(), "five_consecutive_losses_one_contract")["triggered"] is False
    assert rule_by_id(review_summary(manual_outcomes=same).to_dict(), "five_consecutive_losses_one_contract")["triggered"] is True


def test_two_daily_stopouts_one_week_triggers_only_from_manual_records() -> None:
    summary = review_summary(manual_outcomes=(outcome("out-1", daily_stop_out=True, week_id="2026-W18"), outcome("out-2", daily_stop_out=True, week_id="2026-W18"))).to_dict()

    assert rule_by_id(summary, "two_daily_stopouts_one_week")["triggered"] is True
    assert rule_by_id(summary, "two_daily_stopouts_one_week")["supporting_record_ids"] == ["out-1", "out-2"]


def test_stale_data_hidden_from_operator_triggers_when_evidence_supports_condition() -> None:
    summary = review_summary(system_decisions=(decision("sys-1", stale_data_hidden_from_operator=True),)).to_dict()

    assert rule_by_id(summary, "live_data_stale_hidden")["triggered"] is True


def test_operator_execution_outside_query_ready_cannot_be_recorded_as_system_approved() -> None:
    summary = review_summary(manual_outcomes=(outcome("out-1", executed=True, recorded_system_approved=True, query_ready_at_execution=False),)).to_dict()

    rule = rule_by_id(summary, "operator_execution_outside_query_ready_recorded_system_approved")
    assert rule["triggered"] is True
    assert rule["cannot_authorize_execution"] is True


def test_review_never_authorizes_trades_and_exposes_cannot_authorize_execution() -> None:
    summary = review_summary().to_dict()

    assert summary["performance_review_can_authorize_trades"] is False
    assert summary["cannot_authorize_execution"] is True
    for rule in summary["pause_rules"]:
        assert rule["cannot_authorize_execution"] is True


def test_zn_is_not_repromoted_into_final_target_support() -> None:
    summary = build_performance_review_summary(ReviewInput(contract="ZN", system_decisions=(decision("sys-1", contract="ZN"),))).to_dict()

    assert summary["status"] == "blocked"
    assert "review_contract_not_final_supported:ZN:legacy_historical_excluded" in summary["blocking_reasons"]
    assert "ZN" not in final_target_contracts()


def test_gc_remains_excluded() -> None:
    summary = build_performance_review_summary(ReviewInput(contract="GC", system_decisions=(decision("sys-1", contract="GC"),))).to_dict()
    rendered = json.dumps(summary, sort_keys=True)

    assert summary["contract"] == "GC"
    assert "review_contract_not_final_supported:GC:never_supported_excluded" in summary["blocking_reasons"]
    assert "MGC" not in rendered


def test_mgc_is_not_mapped_to_gc() -> None:
    summary = review_summary(contract="MGC", system_decisions=(decision("sys-1", contract="MGC"),)).to_dict()
    rendered = json.dumps(summary, sort_keys=True)

    assert summary["contract"] == "MGC"
    assert "GC" not in rendered.replace("MGC", "")


def test_all_expected_metric_ids_are_present() -> None:
    summary = review_summary().to_dict()
    metric_ids = {metric["metric_id"] for metric in summary["metrics"]}

    assert metric_ids == set(METRIC_IDS)


def test_serialization_helper_outputs_json() -> None:
    encoded = serialize_performance_review_summary(review_summary())
    decoded = json.loads(encoded)

    assert decoded["schema"] == "performance_review_v1"
    assert decoded["contract"] == "ES"


def test_parse_manual_outcome_fails_closed_on_malformed_or_missing_required_fields() -> None:
    malformed = parse_manual_outcome_record("{not-json}")
    missing = parse_manual_outcome_record({"record_id": "out-1"})

    assert malformed.valid is False
    assert missing.valid is False
    assert "missing_required_field:timestamp" in missing.invalid_reasons


def test_sensitive_values_are_redacted_from_records_and_review_output() -> None:
    summary = review_summary(
        manual_outcomes=(
            outcome(
                "out-1",
                operator_note=(
                    "Authorization: Bearer BEARER_VALUE_PRIVATE_12345678901234567890 "
                    "access_token=ACCESS_VALUE_PRIVATE refresh_token=REFRESH_VALUE_PRIVATE "
                    "customerId=CUSTOMER_VALUE_PRIVATE correlId=CORREL_VALUE_PRIVATE "
                    "accountNumber=ACCOUNT_VALUE_PRIVATE wss://stream-redaction.invalid/ws"
                ),
            ),
        ),
        replay_summaries=(
            {
                "profile_id": "preserved_es_phase1",
                "blocking_reasons": ["Authorization: Bearer BEARER_VALUE_PRIVATE_12345678901234567890"],
            },
        ),
    ).to_dict()
    rendered = json.dumps(summary, sort_keys=True)

    for value in SENSITIVE_VALUES:
        assert value not in rendered
    assert "[REDACTED" in rendered


def test_no_broker_order_account_fill_pnl_fields_are_introduced() -> None:
    summary = review_summary().to_dict()
    rendered = json.dumps(summary, sort_keys=True).lower()
    keys = collect_keys(summary)

    for forbidden in FORBIDDEN_KEYS:
        assert forbidden not in keys
        assert f'"{forbidden}"' not in rendered


def test_review_does_not_infer_unavailable_macro_or_order_flow_data() -> None:
    summary = review_summary(
        contract="MGC",
        system_decisions=(decision("sys-1", contract="MGC", failure_category="data_sufficiency_failure"),),
        replay_summaries=(
            {
                "profile_id": "preserved_mgc_phase1",
                "incomplete_reasons": [
                    "cross_asset.dxy missing",
                    "cross_asset.cash_10y_yield missing",
                    "macro_context.fear_catalyst_state missing",
                    "order_flow.footprint missing",
                    "order_flow.dom missing",
                    "order_flow.sweep missing",
                    "order_flow.cumulative_delta missing",
                    "order_flow.aggressive_order_flow missing",
                ],
            },
        ),
    ).to_dict()
    rendered = json.dumps(summary, sort_keys=True).lower()

    assert "dxy_value" not in rendered
    assert "yield_value" not in rendered
    assert "fear_catalyst_value" not in rendered
    assert "footprint_value" not in rendered
    assert "dom_value" not in rendered
    assert "sweep_value" not in rendered
    assert "cumulative_delta_value" not in rendered
    assert "aggressive_order_flow_value" not in rendered


def review_summary(
    *,
    contract: str = "ES",
    system_decisions: tuple[object, ...] | None = None,
    manual_outcomes: tuple[object, ...] | None = None,
    replay_summaries: tuple[dict[str, object], ...] | None = None,
    minimum_sample_size: int = 20,
) -> object:
    return build_performance_review_summary(
        ReviewInput(
            contract=contract,
            profile_id=f"preserved_{contract.lower()}_phase1",
            replay_summaries=replay_summaries
            if replay_summaries is not None
            else (
                {
                    "profile_id": f"preserved_{contract.lower()}_phase1",
                    "stream_state": {"quote_state": "recovered", "blocking_reasons": []},
                    "blocking_reasons": [],
                    "incomplete_reasons": ["stale data missing context"],
                },
            ),
            system_decisions=system_decisions if system_decisions is not None else default_system_decisions(),
            manual_outcomes=manual_outcomes if manual_outcomes is not None else (outcome("out-1", outcome_r=1), outcome("out-2", outcome_r=-1)),
            minimum_sample_size=minimum_sample_size,
        )
    )


def default_system_decisions() -> tuple[object, ...]:
    return (
        decision("sys-1", final_decision="NO_TRADE", trigger_query_ready=True, query_submitted=False),
        decision("sys-2", final_decision="NO_TRADE", trigger_query_ready=True, query_submitted=True),
        decision("sys-3", final_decision="TRADE_APPROVED", trigger_query_ready=True, query_submitted=True, pipeline_run_id="run-3"),
        decision("sys-4", final_decision="TRADE_REJECTED", trigger_query_ready=False, query_submitted=False, failure_category="data_sufficiency_failure"),
    )


def system_decisions(*, count: int, no_trade_count: int) -> tuple[object, ...]:
    records = []
    for index in range(count):
        records.append(
            decision(
                f"sys-{index}",
                final_decision="NO_TRADE" if index < no_trade_count else "TRADE_APPROVED",
                trigger_query_ready=True,
                query_submitted=index >= no_trade_count,
                pipeline_run_id=f"run-{index}",
            )
        )
    return tuple(records)


def manual_outcomes(count: int) -> tuple[object, ...]:
    return tuple(outcome(f"out-{index}", outcome_r=1 if index % 2 == 0 else -1, pipeline_run_id=f"run-{index}") for index in range(count))


def decision(
    record_id: str,
    *,
    contract: str = "ES",
    profile_id: str = "preserved_es_phase1",
    final_decision: str = "NO_TRADE",
    pipeline_run_id: str | None = None,
    trigger_query_ready: bool = False,
    query_submitted: bool = False,
    gate_enabled: bool = False,
    risk_gate_bypassed: bool = False,
    fake_ready_state: bool = False,
    unsupported_contract_ready: bool = False,
    stale_data_hidden_from_operator: bool = False,
    failure_category: str | None = None,
) -> object:
    return create_system_decision_record(
        record_id=record_id,
        timestamp="2026-05-06T14:00:00+00:00",
        contract=contract,
        profile_id=profile_id,
        pipeline_run_id=pipeline_run_id,
        final_decision=final_decision,
        trigger_query_ready=trigger_query_ready,
        query_submitted=query_submitted,
        gate_enabled=gate_enabled,
        risk_gate_bypassed=risk_gate_bypassed,
        fake_ready_state=fake_ready_state,
        unsupported_contract_ready=unsupported_contract_ready,
        stale_data_hidden_from_operator=stale_data_hidden_from_operator,
        failure_category=failure_category,
    )


def outcome(
    record_id: str,
    *,
    contract: str = "ES",
    profile_id: str = "preserved_es_phase1",
    pipeline_run_id: str | None = "run-1",
    executed: bool = True,
    recorded_system_approved: bool = False,
    query_ready_at_execution: bool = True,
    outcome_r: float | int | None = 1,
    mfe_r: float | int | None = None,
    mae_r: float | int | None = None,
    realized_rr: float | int | None = None,
    slippage_ticks: float | int | None = None,
    hold_minutes: float | int | None = None,
    time_of_day: str | None = "09:45",
    daily_stop_out: bool = False,
    week_id: str | None = "2026-W18",
    failure_category: str | None = None,
    operator_note: str | None = None,
) -> object:
    return create_manual_outcome_record(
        record_id=record_id,
        timestamp="2026-05-06T15:00:00+00:00",
        contract=contract,
        profile_id=profile_id,
        pipeline_run_id=pipeline_run_id,
        executed=executed,
        recorded_system_approved=recorded_system_approved,
        query_ready_at_execution=query_ready_at_execution,
        outcome_r=outcome_r,
        mfe_r=mfe_r,
        mae_r=mae_r,
        realized_rr=realized_rr,
        slippage_ticks=slippage_ticks,
        hold_minutes=hold_minutes,
        time_of_day=time_of_day,
        daily_stop_out=daily_stop_out,
        week_id=week_id,
        failure_category=failure_category,
        operator_note=operator_note,
    )


def metric_by_id(summary: dict[str, object], metric_id: str) -> dict[str, object]:
    for metric in summary["metrics"]:
        if metric["metric_id"] == metric_id:
            return metric
    raise AssertionError(f"missing metric {metric_id}")


def rule_by_id(summary: dict[str, object], rule_id: str) -> dict[str, object]:
    for rule in summary["pause_rules"]:
        if rule["rule_id"] == rule_id:
            return rule
    raise AssertionError(f"missing rule {rule_id}")


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
