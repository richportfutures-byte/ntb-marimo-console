from __future__ import annotations

from typing import Any

import pytest

from ninjatradebuilder.adapters import InProcessStructuredAdapter
from ninjatradebuilder.runtime import StructuredGenerationRequest, execute_prompt
from ninjatradebuilder.schemas.outputs import ContractAnalysis, ProposedSetup


def _stage_ab_inputs(contract: str) -> dict[str, Any]:
    return {
        "master_doctrine_text": "MASTER DOCTRINE",
        "evaluation_timestamp_iso": "2026-01-14T14:05:00Z",
        "challenge_state_json": {"current_balance": 50000},
        "contract_metadata_json": {"contract": contract},
        "market_packet_json": {"contract": contract, "current_price": 72.35},
        "contract_specific_extension_json": {"contract": contract},
        "attached_visuals_json": {"execution_chart_attached": True},
    }


def _stage_c_inputs(contract: str) -> dict[str, Any]:
    return {
        "master_doctrine_text": "MASTER DOCTRINE",
        "evaluation_timestamp_iso": "2026-01-14T14:06:00Z",
        "current_price": 4490.0,
        "challenge_state_json": {"max_risk_per_trade_dollars": 1450},
        "contract_metadata_json": {"contract": contract},
        "contract_analysis_json": {"contract": contract, "evidence_score": 6},
    }


def _valid_contract_analysis(contract: str) -> dict[str, Any]:
    return {
        "$schema": "contract_analysis_v1",
        "stage": "contract_market_read",
        "contract": contract,
        "timestamp": "2026-01-14T14:06:00Z",
        "market_regime": "range_bound",
        "directional_bias": "bullish",
        "key_levels": {
            "support_levels": [72.1],
            "resistance_levels": [72.8],
            "pivot_level": 72.4,
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
        "outcome": "ANALYSIS_COMPLETE",
        "conflicting_signals": ["delta mixed"],
        "assumptions": [],
    }


def _valid_proposed_setup(contract: str) -> dict[str, Any]:
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


def _valid_risk_authorization(contract: str) -> dict[str, Any]:
    return {
        "$schema": "risk_authorization_v1",
        "stage": "risk_authorization",
        "contract": contract,
        "timestamp": "2026-01-14T14:08:00Z",
        "decision": "APPROVED",
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


def test_successful_end_to_end_execution_through_concrete_adapter() -> None:
    adapter = InProcessStructuredAdapter({8: _valid_proposed_setup("ES")})

    result = execute_prompt(
        prompt_id=8,
        runtime_inputs=_stage_c_inputs("ES"),
        model_adapter=adapter,
    )

    assert result.output_boundary == "proposed_setup"
    assert isinstance(result.validated_output, ProposedSetup)
    assert result.validated_output.contract == "ES"
    assert adapter.calls[0]["request"] == StructuredGenerationRequest(
        prompt_id=8,
        rendered_prompt=adapter.calls[0]["request"].rendered_prompt,
        expected_output_boundaries=("proposed_setup",),
        schema_model_names=("ProposedSetup",),
    )
    assert "Setup Construction" in adapter.calls[0]["request"].rendered_prompt


def test_adapter_rejects_non_structured_payloads() -> None:
    adapter = InProcessStructuredAdapter({8: "not-structured"})

    with pytest.raises(TypeError) as exc_info:
        execute_prompt(
            prompt_id=8,
            runtime_inputs=_stage_c_inputs("ES"),
            model_adapter=adapter,
        )

    assert "structured mapping responses only" in str(exc_info.value)


def test_runtime_invariants_hold_through_adapter_path() -> None:
    adapter = InProcessStructuredAdapter({4: _valid_contract_analysis("CL")})

    with pytest.raises(ValueError) as exc_info:
        execute_prompt(
            prompt_id=4,
            runtime_inputs=_stage_ab_inputs("ES"),
            model_adapter=adapter,
        )

    assert "bound to contract CL" in str(exc_info.value)
    assert adapter.calls == []


def test_caller_cannot_bypass_prompt_bound_output_validation_via_adapter_behavior() -> None:
    adapter = InProcessStructuredAdapter({8: _valid_risk_authorization("ES")})

    with pytest.raises(ValueError) as exc_info:
        execute_prompt(
            prompt_id=8,
            runtime_inputs=_stage_c_inputs("ES"),
            model_adapter=adapter,
        )

    assert "failed schema validation" in str(exc_info.value)


def test_boundary_metadata_is_propagated_unchanged_through_adapter() -> None:
    captured: dict[str, Any] = {}

    def response_factory(request: StructuredGenerationRequest) -> dict[str, Any]:
        captured["request"] = request
        return _valid_contract_analysis("CL")

    adapter = InProcessStructuredAdapter({4: response_factory})

    execute_prompt(
        prompt_id=4,
        runtime_inputs=_stage_ab_inputs("CL"),
        model_adapter=adapter,
    )

    request = captured["request"]
    assert request.prompt_id == 4
    assert request.expected_output_boundaries == (
        "sufficiency_gate_output",
        "contract_analysis",
    )
    assert request.schema_model_names == (
        "SufficiencyGateOutput",
        "ContractAnalysis",
    )


def test_contract_specific_prompt_executes_through_concrete_adapter() -> None:
    adapter = InProcessStructuredAdapter(
        {
            4: lambda request: _valid_contract_analysis("CL"),
        }
    )

    result = execute_prompt(
        prompt_id=4,
        runtime_inputs=_stage_ab_inputs("CL"),
        model_adapter=adapter,
    )

    assert result.output_boundary == "contract_analysis"
    assert isinstance(result.validated_output, ContractAnalysis)
    assert result.validated_output.contract == "CL"


def test_adapter_cannot_override_prompt_bound_schema_via_response_factory() -> None:
    def response_factory(request: StructuredGenerationRequest) -> dict[str, Any]:
        assert request.schema_model_names == ("ProposedSetup",)
        return _valid_risk_authorization("ES")

    adapter = InProcessStructuredAdapter({8: response_factory})

    with pytest.raises(ValueError) as exc_info:
        execute_prompt(
            prompt_id=8,
            runtime_inputs=_stage_c_inputs("ES"),
            model_adapter=adapter,
        )

    assert "failed schema validation" in str(exc_info.value)
