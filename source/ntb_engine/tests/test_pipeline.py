from __future__ import annotations

import copy
import json
from pathlib import Path

from ninjatradebuilder.adapters import InProcessStructuredAdapter
from ninjatradebuilder.pipeline import run_pipeline
from ninjatradebuilder.runtime import StructuredGenerationRequest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_packet(contract: str) -> dict:
    payload = json.loads((FIXTURES_DIR / "packets.valid.json").read_text())
    return {
        "$schema": "historical_packet_v1",
        "challenge_state": copy.deepcopy(payload["shared"]["challenge_state"]),
        "attached_visuals": copy.deepcopy(payload["shared"]["attached_visuals"]),
        "contract_metadata": copy.deepcopy(payload["contracts"][contract]["contract_metadata"]),
        "market_packet": copy.deepcopy(payload["contracts"][contract]["market_packet"]),
        "contract_specific_extension": copy.deepcopy(
            payload["contracts"][contract]["contract_specific_extension"]
        ),
    }


def _valid_contract_analysis(contract: str, outcome: str = "ANALYSIS_COMPLETE") -> dict:
    return {
        "$schema": "contract_analysis_v1",
        "stage": "contract_market_read",
        "contract": contract,
        "timestamp": "2026-01-14T14:06:00Z",
        "market_regime": "range_bound",
        "directional_bias": "bullish",
        "key_levels": {
            "support_levels": [4485.0],
            "resistance_levels": [4495.0],
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
        "structural_notes": "Price is holding above pivot with one conflicting signal.",
        "outcome": outcome,
        "conflicting_signals": ["delta mixed"] if outcome == "ANALYSIS_COMPLETE" else ["conflict"],
        "assumptions": [],
    }


def _valid_sufficiency_gate_output(contract: str, status: str) -> dict:
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
            "packet_age_seconds": 30,
            "stale": False,
            "threshold_seconds": 300,
        },
        "challenge_state_valid": True,
        "event_lockout_detail": None,
    }
    if status != "READY":
        payload["disqualifiers"] = ["outside_allowed_hours"]
    return payload


def _valid_proposed_setup(contract: str, outcome: str = "SETUP_PROPOSED") -> dict:
    payload = {
        "$schema": "proposed_setup_v1",
        "stage": "setup_construction",
        "contract": contract,
        "timestamp": "2026-01-14T14:07:00Z",
        "outcome": outcome,
        "no_trade_reason": "market_read_returned_no_trade" if outcome == "NO_TRADE" else None,
        "direction": "LONG" if outcome == "SETUP_PROPOSED" else None,
        "entry_price": 4490.0 if outcome == "SETUP_PROPOSED" else None,
        "stop_price": 4486.0 if outcome == "SETUP_PROPOSED" else None,
        "target_1": 4498.0 if outcome == "SETUP_PROPOSED" else None,
        "target_2": 4502.0 if outcome == "SETUP_PROPOSED" else None,
        "position_size": 2 if outcome == "SETUP_PROPOSED" else None,
        "risk_dollars": 112.5 if outcome == "SETUP_PROPOSED" else None,
        "reward_risk_ratio": 2.1 if outcome == "SETUP_PROPOSED" else None,
        "setup_class": "intraday_swing" if outcome == "SETUP_PROPOSED" else None,
        "hold_time_estimate_minutes": 45 if outcome == "SETUP_PROPOSED" else None,
        "rationale": "Long from pivot toward resistance ladder." if outcome == "SETUP_PROPOSED" else None,
        "disqualifiers": [] if outcome == "SETUP_PROPOSED" else None,
        "sizing_math": {
            "stop_distance_ticks": 16.0,
            "risk_per_tick": 12.5,
            "raw_risk_dollars": 100.0,
            "slippage_cost_dollars": 12.5,
            "adjusted_risk_dollars": 112.5,
            "blended_target_distance_ticks": 33.6,
            "blended_reward_dollars": 236.25,
        }
        if outcome == "SETUP_PROPOSED"
        else None,
    }
    return payload


def _valid_risk_authorization(contract: str, decision: str) -> dict:
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
                "passed": decision != "REJECTED",
                "detail": f"Rule {check_id} {'passed' if decision != 'REJECTED' else 'failed'}.",
            }
            for check_id in range(1, 14)
        ],
        "rejection_reasons": [] if decision != "REJECTED" else ["event_lockout_active"],
        "adjusted_position_size": 1 if decision == "REDUCED" else None,
        "adjusted_risk_dollars": 56.25 if decision == "REDUCED" else None,
        "remaining_daily_risk_budget": 650.0,
        "remaining_aggregate_risk_budget": 400.0,
    }
    return payload


def test_pipeline_terminates_at_stage_a() -> None:
    adapter = InProcessStructuredAdapter({4: _valid_sufficiency_gate_output("CL", "INSUFFICIENT_DATA")})

    result = run_pipeline(
        packet=_load_packet("CL"),
        evaluation_timestamp_iso="2026-01-14T14:05:00Z",
        model_adapter=adapter,
    )

    assert result.termination_stage == "sufficiency_gate"
    assert result.final_decision == "INSUFFICIENT_DATA"
    assert result.contract_analysis is None


def test_pipeline_terminates_at_stage_b() -> None:
    adapter = InProcessStructuredAdapter({2: _valid_contract_analysis("ES", outcome="NO_TRADE")})

    result = run_pipeline(
        packet=_load_packet("ES"),
        evaluation_timestamp_iso="2026-01-14T14:05:00Z",
        model_adapter=adapter,
    )

    assert result.termination_stage == "contract_market_read"
    assert result.final_decision == "NO_TRADE"
    assert result.sufficiency_gate_output is None
    assert result.contract_analysis is not None
    assert result.proposed_setup is None


def test_pipeline_terminates_at_stage_c() -> None:
    adapter = InProcessStructuredAdapter(
        {
            2: _valid_contract_analysis("ES"),
            8: _valid_proposed_setup("ES", outcome="NO_TRADE"),
        }
    )

    result = run_pipeline(
        packet=_load_packet("ES"),
        evaluation_timestamp_iso="2026-01-14T14:05:00Z",
        model_adapter=adapter,
    )

    assert result.termination_stage == "setup_construction"
    assert result.final_decision == "NO_TRADE"
    assert result.sufficiency_gate_output is None
    assert result.proposed_setup is not None
    assert result.risk_authorization is None


def test_pipeline_terminates_at_stage_d_with_final_decision_mapping() -> None:
    adapter = InProcessStructuredAdapter(
        {
            2: _valid_contract_analysis("ES"),
            8: _valid_proposed_setup("ES"),
            9: _valid_risk_authorization("ES", decision="REDUCED"),
        }
    )

    result = run_pipeline(
        packet=_load_packet("ES"),
        evaluation_timestamp_iso="2026-01-14T14:05:00Z",
        model_adapter=adapter,
    )

    assert result.termination_stage == "risk_authorization"
    assert result.final_decision == "TRADE_REDUCED"
    assert result.sufficiency_gate_output is None
    assert result.risk_authorization is not None


def test_pipeline_injects_master_doctrine_into_stage_prompts() -> None:
    captured: dict[str, StructuredGenerationRequest] = {}

    def response_factory(request: StructuredGenerationRequest) -> dict:
        captured["request"] = request
        return _valid_contract_analysis("ES", outcome="NO_TRADE")

    adapter = InProcessStructuredAdapter({2: response_factory})

    result = run_pipeline(
        packet=_load_packet("ES"),
        evaluation_timestamp_iso="2026-01-14T14:05:00Z",
        model_adapter=adapter,
    )

    assert result.termination_stage == "contract_market_read"
    assert "MASTER DOCTRINE — RUNTIME SYSTEM RULES" in captured["request"].rendered_prompt
