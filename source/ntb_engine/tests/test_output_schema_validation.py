from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from ninjatradebuilder.schemas.outputs import (
    ContractAnalysis,
    LoggingRecord,
    PostTradeReviewRecord,
    ProposedSetup,
    ReadinessEngineOutput,
    RiskAuthorization,
    SufficiencyGateOutput,
)

CONTRACTS = ["ES", "NQ", "CL", "ZN", "6E", "MGC"]
FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_packets_fixture() -> dict:
    return json.loads((FIXTURES_DIR / "packets.valid.json").read_text())


def _challenge_state_snapshot() -> dict:
    return copy.deepcopy(_load_packets_fixture()["shared"]["challenge_state"])


def _market_packet_snapshot(contract: str) -> dict:
    return copy.deepcopy(_load_packets_fixture()["contracts"][contract]["market_packet"])


def _sufficiency_gate_output(contract: str, status: str = "READY") -> dict:
    payload = {
        "$schema": "sufficiency_gate_output_v1",
        "stage": "sufficiency_gate",
        "contract": contract,
        "timestamp": "2026-01-14T14:05:00Z",
        "status": status,
        "missing_inputs": [],
        "disqualifiers": [],
        "data_quality_flags": [],
        "staleness_check": {
            "packet_age_seconds": 75,
            "stale": False,
            "threshold_seconds": 300,
        },
        "challenge_state_valid": True,
        "event_lockout_detail": None,
    }
    if status == "EVENT_LOCKOUT":
        payload["disqualifiers"] = ["Tier-1 event lockout active"]
        payload["event_lockout_detail"] = {
            "event_name": "CPI",
            "event_time": "2026-01-14T13:30:00Z",
            "minutes_until": 4,
            "lockout_type": "pre_event",
        }
    return payload


def _readiness_engine_output(contract: str, family: str = "recheck_at_time") -> dict:
    trigger_data = {
        "family": "recheck_at_time",
        "recheck_at_time": "2026-03-22T12:05:00Z",
    }
    if family == "price_level_touch":
        trigger_data = {
            "family": "price_level_touch",
            "price_level": 4492.25,
        }

    return {
        "$schema": "readiness_engine_output_v1",
        "stage": "readiness_engine",
        "authority": "ESCALATE_ONLY",
        "contract": contract,
        "timestamp": "2026-03-22T12:00:00Z",
        "status": "WAIT_FOR_TRIGGER",
        "doctrine_gates": [
            {
                "gate": "data_sufficiency_gate",
                "state": "PASS",
                "rationale": "Data complete.",
            },
            {
                "gate": "context_alignment_gate",
                "state": "PASS",
                "rationale": "Context aligned.",
            },
            {
                "gate": "structure_quality_gate",
                "state": "PASS",
                "rationale": "Structure valid.",
            },
            {
                "gate": "trigger_gate",
                "state": "WAIT",
                "rationale": "Waiting for trigger.",
            },
            {
                "gate": "risk_window_gate",
                "state": "PASS",
                "rationale": "Risk window open.",
            },
            {
                "gate": "lockout_gate",
                "state": "PASS",
                "rationale": "No lockout active.",
            },
        ],
        "trigger_data": trigger_data,
        "wait_for_trigger_reason": "timing_window_not_open",
        "lockout_reason": None,
        "insufficient_data_reasons": [],
        "missing_inputs": [],
    }


def _contract_analysis(contract: str) -> dict:
    return {
        "$schema": "contract_analysis_v1",
        "stage": "contract_market_read",
        "contract": contract,
        "timestamp": "2026-01-14T14:06:00Z",
        "market_regime": "range_bound",
        "directional_bias": "bullish",
        "key_levels": {
            "support_levels": [4485.0, 4480.0],
            "resistance_levels": [4495.0, 4500.0],
            "pivot_level": 4490.0,
        },
        "evidence_score": 6,
        "confidence_band": "MEDIUM",
        "value_context": {
            "relative_to_prior_value_area": "inside",
            "relative_to_current_developing_value": "inside_value",
            "relative_to_vwap": "above",
            "relative_to_prior_day_range": "inside",
        },
        "structural_notes": "Price is holding above pivot with balanced auction conditions.",
        "outcome": "ANALYSIS_COMPLETE",
        "conflicting_signals": ["delta mixed"],
        "assumptions": [],
    }


def _proposed_setup(contract: str) -> dict:
    return {
        "$schema": "proposed_setup_v1",
        "stage": "setup_construction",
        "contract": contract,
        "timestamp": "2026-01-14T14:07:00Z",
        "outcome": "SETUP_PROPOSED",
        "no_trade_reason": None,
        "direction": "LONG",
        "entry_price": 4490.0,
        "stop_price": 4486.0,
        "target_1": 4498.0,
        "target_2": 4502.0,
        "position_size": 2,
        "risk_dollars": 112.5,
        "reward_risk_ratio": 2.1,
        "setup_class": "intraday_swing",
        "hold_time_estimate_minutes": 45,
        "rationale": "Long from pivot toward resistance ladder.",
        "disqualifiers": [],
        "sizing_math": {
            "stop_distance_ticks": 16.0,
            "risk_per_tick": 12.5,
            "raw_risk_dollars": 100.0,
            "slippage_cost_dollars": 12.5,
            "adjusted_risk_dollars": 112.5,
            "blended_target_distance_ticks": 33.6,
            "blended_reward_dollars": 236.25,
        },
    }


def _risk_authorization(contract: str, decision: str = "APPROVED") -> dict:
    payload = {
        "$schema": "risk_authorization_v1",
        "stage": "risk_authorization",
        "contract": contract,
        "timestamp": "2026-01-14T14:08:00Z",
        "decision": decision,
        "checks_count": 13,
        "checks": [
            {
                "check_id": check_id,
                "check_name": f"Check {check_id}",
                "passed": True,
                "detail": f"Rule {check_id} passed.",
            }
            for check_id in range(1, 14)
        ],
        "rejection_reasons": [],
        "adjusted_position_size": None,
        "adjusted_risk_dollars": None,
        "remaining_daily_risk_budget": 650.0,
        "remaining_aggregate_risk_budget": 400.0,
    }
    if decision == "REDUCED":
        payload["adjusted_position_size"] = 1
        payload["adjusted_risk_dollars"] = 58.75
    if decision == "REJECTED":
        payload["rejection_reasons"] = ["Would exceed daily risk budget."]
    return payload


def _logging_record(contract: str, final_decision: str = "TRADE_APPROVED") -> dict:
    return {
        "$schema": "logging_record_v1",
        "record_id": f"{contract}_2026-01-14_001",
        "contract": contract,
        "pipeline_start_timestamp": "2026-01-14T14:05:00Z",
        "pipeline_end_timestamp": "2026-01-14T14:08:30Z",
        "final_decision": final_decision,
        "termination_stage": "risk_authorization",
        "stages_completed": [
            "sufficiency_gate",
            "contract_market_read",
            "setup_construction",
            "risk_authorization",
        ],
        "sufficiency_gate_output": _sufficiency_gate_output(contract),
        "contract_analysis": _contract_analysis(contract),
        "proposed_setup": _proposed_setup(contract),
        "risk_authorization": _risk_authorization(contract),
        "challenge_state_snapshot": _challenge_state_snapshot(),
        "market_packet_snapshot": _market_packet_snapshot(contract),
        "data_quality_flags": [],
    }


def _post_trade_review_record(contract: str) -> dict:
    return {
        "$schema": "post_trade_review_record_v1",
        "review_id": f"{contract}_review_001",
        "logging_record_id": f"{contract}_2026-01-14_001",
        "contract": contract,
        "direction": "LONG",
        "entry_price": 4490.0,
        "exit_price": 4499.0,
        "actual_entry_slippage_ticks": 1.0,
        "actual_exit_slippage_ticks": 0.5,
        "position_size": 2,
        "realized_pnl": 215.0,
        "mae_ticks": 6.0,
        "mfe_ticks": 40.0,
        "hold_time_minutes": 38,
        "exit_type": "target_1_hit",
        "setup_class": "intraday_swing",
        "scale_out_fills": [
            {"target": "target_1", "fill_price": 4498.0, "size": 1, "pnl": 100.0},
            {"target": "target_2", "fill_price": 4500.0, "size": 1, "pnl": 115.0},
        ],
        "planned_reward_risk_ratio": 2.1,
        "actual_reward_risk_ratio": 1.9,
        "market_regime_at_entry": "range_bound",
        "confidence_band_at_entry": "MEDIUM",
        "operator_notes": "Held through rotation back to resistance.",
    }


@pytest.mark.parametrize("contract", CONTRACTS)
def test_shared_output_schemas_accept_all_supported_contracts(contract: str) -> None:
    stage_a = SufficiencyGateOutput.model_validate(_sufficiency_gate_output(contract))
    stage_b = ContractAnalysis.model_validate(_contract_analysis(contract))
    stage_c = ProposedSetup.model_validate(_proposed_setup(contract))
    stage_d = RiskAuthorization.model_validate(_risk_authorization(contract))
    stage_e = LoggingRecord.model_validate(_logging_record(contract))
    review = PostTradeReviewRecord.model_validate(_post_trade_review_record(contract))

    assert stage_a.contract == contract
    assert stage_b.contract == contract
    assert stage_c.contract == contract
    assert stage_d.contract == contract
    assert stage_e.contract == contract
    assert review.contract == contract


def test_contract_analysis_requires_evidence_confidence_alignment() -> None:
    invalid = _contract_analysis("ES")
    invalid["evidence_score"] = 3
    invalid["confidence_band"] = "HIGH"

    with pytest.raises(ValidationError) as exc_info:
        ContractAnalysis.model_validate(invalid)

    assert "confidence_band" in str(exc_info.value)


def test_event_lockout_requires_event_lockout_detail() -> None:
    invalid = _sufficiency_gate_output("ES", status="EVENT_LOCKOUT")
    invalid["event_lockout_detail"] = None

    with pytest.raises(ValidationError) as exc_info:
        SufficiencyGateOutput.model_validate(invalid)

    assert "event_lockout_detail" in str(exc_info.value)


def test_event_lockout_detail_is_forbidden_when_status_is_not_event_lockout() -> None:
    invalid = _sufficiency_gate_output("ES", status="READY")
    invalid["event_lockout_detail"] = {
        "event_name": "CPI",
        "event_time": "2026-01-14T13:30:00Z",
        "minutes_until": 4,
        "lockout_type": "pre_event",
    }

    with pytest.raises(ValidationError) as exc_info:
        SufficiencyGateOutput.model_validate(invalid)

    assert "only be populated" in str(exc_info.value)

def test_valid_event_lockout_trigger_payload_passes_sufficiency_validation() -> None:
    validated = SufficiencyGateOutput.model_validate(
        _sufficiency_gate_output("ES", status="EVENT_LOCKOUT")
    )

    assert validated.status == "EVENT_LOCKOUT"
    assert validated.event_lockout_detail is not None
    assert validated.event_lockout_detail.lockout_type == "pre_event"


def test_readiness_engine_accepts_recheck_at_time_trigger_family() -> None:
    validated = ReadinessEngineOutput.model_validate(
        _readiness_engine_output("ES", family="recheck_at_time")
    )

    assert validated.trigger_data is not None
    assert validated.trigger_data.family == "recheck_at_time"


def test_readiness_engine_accepts_price_level_touch_trigger_family() -> None:
    validated = ReadinessEngineOutput.model_validate(
        _readiness_engine_output("ES", family="price_level_touch")
    )

    assert validated.trigger_data is not None
    assert validated.trigger_data.family == "price_level_touch"


def test_readiness_engine_rejects_unsupported_time_recheck_trigger_family() -> None:
    invalid = _readiness_engine_output("ES", family="recheck_at_time")
    invalid["trigger_data"]["family"] = "time_recheck"

    with pytest.raises(ValidationError) as exc_info:
        ReadinessEngineOutput.model_validate(invalid)

    message = str(exc_info.value)
    assert "trigger_data.family" in message
    assert "recheck_at_time" in message
    assert "price_level_touch" in message


def test_event_lockout_rejects_malformed_trigger_payload() -> None:
    invalid = _sufficiency_gate_output("ES", status="EVENT_LOCKOUT")
    invalid["event_lockout_detail"] = {
        "event_name": "CPI",
        "event_time": "2026-01-14T13:30:00Z",
        "minutes_since": 2,
        "lockout_type": "post_event",
        "trigger_payload": {"price": 4490.0},
    }

    with pytest.raises(ValidationError) as exc_info:
        SufficiencyGateOutput.model_validate(invalid)

    message = str(exc_info.value)
    assert "event_lockout_detail.minutes_until" in message
    assert "event_lockout_detail.minutes_since" in message
    assert "event_lockout_detail.trigger_payload" in message


def test_readiness_output_cannot_be_used_as_stage_c_contract_analysis_input() -> None:
    with pytest.raises(ValidationError) as exc_info:
        ContractAnalysis.model_validate(_readiness_engine_output("ES"))

    message = str(exc_info.value)
    assert "market_regime" in message
    assert "value_context" in message
    assert "evidence_score" in message


def test_readiness_engine_requires_escalate_only_authority() -> None:
    invalid = _readiness_engine_output("ES")
    invalid["authority"] = "TRADE_AUTHORIZATION"

    with pytest.raises(ValidationError) as exc_info:
        ReadinessEngineOutput.model_validate(invalid)

    message = str(exc_info.value)
    assert "authority" in message
    assert "ESCALATE_ONLY" in message


def test_readiness_output_cannot_be_used_as_risk_authorization_input() -> None:
    with pytest.raises(ValidationError) as exc_info:
        RiskAuthorization.model_validate(_readiness_engine_output("ES"))

    message = str(exc_info.value)
    assert "decision" in message
    assert "checks" in message
def test_risk_authorization_requires_checks_count_and_ordered_check_ids() -> None:
    invalid = _risk_authorization("ES")
    invalid["checks_count"] = 12
    invalid["checks"][0]["check_id"] = 2

    with pytest.raises(ValidationError) as exc_info:
        RiskAuthorization.model_validate(invalid)

    assert "13" in str(exc_info.value) or "check_id" in str(exc_info.value)


def test_post_trade_review_requires_denormalized_entry_fields() -> None:
    invalid = _post_trade_review_record("ES")
    invalid.pop("market_regime_at_entry")

    with pytest.raises(ValidationError) as exc_info:
        PostTradeReviewRecord.model_validate(invalid)

    assert "market_regime_at_entry" in str(exc_info.value)


def test_logging_record_enforces_final_decision_mapping() -> None:
    invalid = _logging_record("ES", final_decision="TRADE_REJECTED")

    with pytest.raises(ValidationError) as exc_info:
        LoggingRecord.model_validate(invalid)

    assert "final_decision" in str(exc_info.value)
