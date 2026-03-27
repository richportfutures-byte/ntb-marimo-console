from __future__ import annotations

import json
from typing import Any, Mapping
from pathlib import Path

import pytest

from ninjatradebuilder.runtime import (
    PromptExecutionResult,
    StructuredGenerationRequest,
    execute_prompt,
    run_readiness,
)
from ninjatradebuilder.schemas.outputs import ContractAnalysis, ProposedSetup, ReadinessEngineOutput


FIXTURES_DIR = Path(__file__).parent / "fixtures"


class FakeStructuredAdapter:
    def __init__(self, payload: Any) -> None:
        self.payload = payload
        self.calls: list[StructuredGenerationRequest] = []

    def generate_structured(self, request: StructuredGenerationRequest) -> Mapping[str, Any]:
        self.calls.append(request)
        return self.payload


def _load_json_fixture(relative_path: str) -> dict[str, Any]:
    return json.loads((FIXTURES_DIR / relative_path).read_text())


def _stage_ab_inputs(contract: str) -> dict[str, Any]:
    return {
        "master_doctrine_text": "MASTER DOCTRINE",
        "evaluation_timestamp_iso": "2026-01-14T14:05:00Z",
        "challenge_state_json": {"current_balance": 50000},
        "contract_metadata_json": {"contract": contract},
        "market_packet_json": {"contract": contract, "current_price": 4490.0},
        "contract_specific_extension_json": {"contract": contract},
        "attached_visuals_json": {"execution_chart_attached": True},
    }


def _stage_ab_inputs_trade_friendly_es() -> dict[str, Any]:
    return {
        "master_doctrine_text": "MASTER DOCTRINE",
        "evaluation_timestamp_iso": "2026-01-14T15:05:00Z",
        "challenge_state_json": {
            "current_balance": 50000,
            "event_lockout_minutes_before": 5,
            "event_lockout_minutes_after": 5,
        },
        "contract_metadata_json": {"contract": "ES"},
        "market_packet_json": {
            "contract": "ES",
            "timestamp": "2026-01-14T15:04:30Z",
            "current_price": 4490.0,
            "session_open": 4484.0,
            "day_open": 4484.0,
            "prior_day_high": 4498.0,
            "prior_day_low": 4472.0,
            "prior_day_close": 4483.0,
            "overnight_high": 4489.0,
            "overnight_low": 4478.0,
            "vwap": 4488.0,
            "current_session_vah": 4489.5,
            "current_session_val": 4483.5,
            "current_session_poc": 4487.5,
            "previous_session_vah": 4486.0,
            "previous_session_val": 4479.0,
            "previous_session_poc": 4482.5,
            "session_range": 11.0,
            "avg_20d_session_range": 24.0,
            "cumulative_delta": 18500,
            "current_volume_vs_average": 1.18,
            "opening_type": "open_drive",
            "event_calendar_remainder": [],
        },
        "contract_specific_extension_json": {
            "contract": "ES",
            "breadth": "strongly_positive",
            "index_cash_tone": "risk_on",
        },
        "attached_visuals_json": {
            "execution_chart_attached": True,
            "daily_chart_attached": True,
        },
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


def _stage_c_inputs_trade_friendly(contract: str) -> dict[str, Any]:
    return {
        "master_doctrine_text": "MASTER DOCTRINE",
        "evaluation_timestamp_iso": "2026-01-14T14:06:00Z",
        "current_price": 4490.0,
        "challenge_state_json": {"max_risk_per_trade_dollars": 1450},
        "contract_metadata_json": {
            "contract": contract,
            "max_position_size": 2,
            "tick_size": 0.25,
            "tick_value": 12.5,
            "slippage_per_side_ticks": 1,
        },
        "contract_analysis_json": {
            "contract": contract,
            "timestamp": "2026-01-14T14:05:30Z",
            "market_regime": "trending_up",
            "directional_bias": "bullish",
            "key_levels": {
                "support_levels": [4488.0],
                "resistance_levels": [4496.0, 4500.0],
                "pivot_level": 4490.0,
            },
            "evidence_score": 8,
            "confidence_band": "HIGH",
            "value_context": {
                "relative_to_prior_value_area": "above",
                "relative_to_current_developing_value": "above_vah",
                "relative_to_vwap": "above",
                "relative_to_prior_day_range": "inside",
            },
            "structural_notes": "Price is trending above pivot and above value with clean resistance ladder overhead.",
            "outcome": "ANALYSIS_COMPLETE",
            "conflicting_signals": [],
            "assumptions": [],
        },
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


def _minimal_valid_proposed_setup(contract: str) -> dict[str, Any]:
    return {
        "$schema": "proposed_setup_v1",
        "stage": "setup_construction",
        "contract": contract,
        "timestamp": "2026-01-14T14:07:00Z",
        "outcome": "SETUP_PROPOSED",
        "no_trade_reason": None,
        "direction": "LONG",
        "entry_price": 4490.0,
        "stop_price": 4488.0,
        "target_1": 4494.0,
        "target_2": None,
        "position_size": 1,
        "risk_dollars": 37.5,
        "reward_risk_ratio": 2.0,
        "setup_class": "scalp",
        "hold_time_estimate_minutes": 10,
        "rationale": "Bullish bias from contract_analysis supports a scalp to first resistance.",
        "disqualifiers": [],
        "sizing_math": {
            "stop_distance_ticks": 8.0,
            "risk_per_tick": 12.5,
            "raw_risk_dollars": 25.0,
            "slippage_cost_dollars": 12.5,
            "adjusted_risk_dollars": 37.5,
            "blended_target_distance_ticks": 16.0,
            "blended_reward_dollars": 50.0,
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


def _valid_sufficiency_gate_output(contract: str, status: str = "READY") -> dict[str, Any]:
    output = {
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
    if status == "INSUFFICIENT_DATA":
        output["disqualifiers"] = ["outside_allowed_hours"]
    return output


@pytest.mark.parametrize(
    ("trigger_payload", "expected_fixture", "expected_prompt_fragment"),
    [
        (
            {"trigger_family": "price_level_touch", "price_level": 110.40625},
            "readiness/zn_ready.expected.json",
            '"trigger_family": "price_level_touch"',
        ),
        (
            {"trigger_family": "recheck_at_time", "recheck_at_time": "2026-01-14T15:15:00Z"},
            "readiness/zn_wait_for_trigger.expected.json",
            '"recheck_at_time": "2026-01-14T15:15:00Z"',
        ),
        (
            {"trigger_family": "price_level_touch", "price_level": 110.5},
            "readiness/zn_locked_out.expected.json",
            '"price_level": 110.5',
        ),
    ],
)
def test_run_readiness_executes_end_to_end_for_zn_golden_paths(
    trigger_payload: dict[str, Any],
    expected_fixture: str,
    expected_prompt_fragment: str,
) -> None:
    runtime_inputs = _load_json_fixture("readiness/zn_runtime_inputs.valid.json")
    expected_output = _load_json_fixture(expected_fixture)
    adapter = FakeStructuredAdapter(expected_output)

    result = run_readiness(
        runtime_inputs=runtime_inputs,
        readiness_trigger=trigger_payload,
        model_adapter=adapter,
    )

    assert isinstance(result, PromptExecutionResult)
    assert result.output_boundary == "readiness_engine_output"
    assert isinstance(result.validated_output, ReadinessEngineOutput)
    assert result.validated_output.model_dump(mode="json", by_alias=True) == expected_output
    assert adapter.calls[0].expected_output_boundaries == ("readiness_engine_output",)
    assert adapter.calls[0].schema_model_names == ("ReadinessEngineOutput",)
    assert '"contract": "ZN"' in result.rendered_prompt
    assert expected_prompt_fragment in result.rendered_prompt
    assert "watchman_context JSON:" in result.rendered_prompt
    assert '"contract_specific_macro_state": "auction_sensitive"' in result.rendered_prompt
    assert '"session_wind_down_state": "normal"' in result.rendered_prompt


def test_successful_shared_prompt_execution_returns_typed_result() -> None:
    adapter = FakeStructuredAdapter(_valid_proposed_setup("ES"))

    result = execute_prompt(
        prompt_id=8,
        runtime_inputs=_stage_c_inputs("ES"),
        model_adapter=adapter,
    )

    assert isinstance(result, PromptExecutionResult)
    assert result.prompt_id == 8
    assert result.output_boundary == "proposed_setup"
    assert isinstance(result.validated_output, ProposedSetup)
    assert "Entry price defaults to current_price (market order)." in result.rendered_prompt
    assert adapter.calls[0].prompt_id == 8
    assert adapter.calls[0].expected_output_boundaries == ("proposed_setup",)
    assert adapter.calls[0].schema_model_names == ("ProposedSetup",)


def test_successful_minimal_single_unit_prompt_8_execution_returns_typed_result() -> None:
    adapter = FakeStructuredAdapter(_minimal_valid_proposed_setup("ES"))

    result = execute_prompt(
        prompt_id=8,
        runtime_inputs=_stage_c_inputs("ES"),
        model_adapter=adapter,
    )

    assert isinstance(result, PromptExecutionResult)
    assert result.output_boundary == "proposed_setup"
    assert isinstance(result.validated_output, ProposedSetup)
    assert result.validated_output.position_size == 1
    assert result.validated_output.target_2 is None
    assert result.validated_output.outcome == "SETUP_PROPOSED"


def test_trade_friendly_prompt_8_inputs_support_minimal_setup_proposed_execution() -> None:
    adapter = FakeStructuredAdapter(_minimal_valid_proposed_setup("ES"))

    result = execute_prompt(
        prompt_id=8,
        runtime_inputs=_stage_c_inputs_trade_friendly("ES"),
        model_adapter=adapter,
    )

    assert isinstance(result, PromptExecutionResult)
    assert result.output_boundary == "proposed_setup"
    assert isinstance(result.validated_output, ProposedSetup)
    assert result.validated_output.outcome == "SETUP_PROPOSED"
    assert result.validated_output.direction == "LONG"
    assert result.validated_output.position_size == 1


def test_prompt_8_accepts_validated_stage_b_model_inputs() -> None:
    adapter = FakeStructuredAdapter(_minimal_valid_proposed_setup("ES"))
    contract_analysis = ContractAnalysis.model_validate(_valid_contract_analysis("ES"))
    runtime_inputs = _stage_c_inputs_trade_friendly("ES")
    runtime_inputs["contract_analysis_json"] = contract_analysis

    result = execute_prompt(
        prompt_id=8,
        runtime_inputs=runtime_inputs,
        model_adapter=adapter,
    )

    assert result.output_boundary == "proposed_setup"
    assert isinstance(result.validated_output, ProposedSetup)
    assert '"timestamp": "2026-01-14T14:06:00Z"' in result.rendered_prompt


def test_successful_contract_specific_prompt_execution_returns_typed_result() -> None:
    adapter = FakeStructuredAdapter(_valid_contract_analysis("CL"))

    result = execute_prompt(
        prompt_id=4,
        runtime_inputs=_stage_ab_inputs("CL"),
        model_adapter=adapter,
    )

    assert result.output_boundary == "contract_analysis"
    assert isinstance(result.validated_output, ContractAnalysis)
    assert result.validated_output.contract == "CL"
    assert "CL (Crude Oil)" in result.rendered_prompt
    assert adapter.calls[0].expected_output_boundaries == (
        "sufficiency_gate_output",
        "contract_analysis",
    )
    assert adapter.calls[0].schema_model_names == (
        "SufficiencyGateOutput",
        "ContractAnalysis",
    )


def test_trade_friendly_es_stage_ab_inputs_support_contract_analysis_execution() -> None:
    adapter = FakeStructuredAdapter(_valid_contract_analysis("ES"))

    result = execute_prompt(
        prompt_id=2,
        runtime_inputs=_stage_ab_inputs_trade_friendly_es(),
        model_adapter=adapter,
    )

    assert result.output_boundary == "contract_analysis"
    assert isinstance(result.validated_output, ContractAnalysis)
    assert result.validated_output.contract == "ES"


def test_stage_ab_rendered_prompt_forbids_ready_early_stop() -> None:
    adapter = FakeStructuredAdapter(_valid_contract_analysis("ES"))

    result = execute_prompt(
        prompt_id=2,
        runtime_inputs=_stage_ab_inputs_trade_friendly_es(),
        model_adapter=adapter,
    )

    assert (
        "If Part 1 status = READY, do not stop and do not return sufficiency_gate_output as the final answer."
        in result.rendered_prompt
    )
    assert "Continue to Part 2 and return contract_analysis JSON only." in result.rendered_prompt
    assert "Always emit the full contract_analysis schema fields" in result.rendered_prompt
    assert "outcome must be Stage B outcome only: ANALYSIS_COMPLETE or NO_TRADE. Never emit READY in Stage B." in result.rendered_prompt
    assert "key_levels must be the schema object" in result.rendered_prompt
    assert "structural_notes must be a single string." in result.rendered_prompt
    assert "Copy one literal verbatim from this list." in result.rendered_prompt
    assert "Do not emit assumptions as a scalar string, sentence, or paragraph." in result.rendered_prompt


def test_rejects_live_like_stage_b_hybrid_payload_after_ready_gate() -> None:
    invalid_output = {
        "contract": "ES",
        "timestamp": "2026-01-14T15:05:00Z",
        "outcome": "READY",
        "directional_bias": "bullish",
        "evidence_score": 8,
        "confidence_band": "HIGH",
        "conflicting_signals": [],
        "structural_notes": [
            "The session exhibited a strong positive breadth backdrop."
        ],
        "key_levels": [
            {"price": 4498.0, "type": "resistance", "context": "prior_day_high"},
            {"price": 4488.0, "type": "support", "context": "VWAP"},
        ],
    }
    adapter = FakeStructuredAdapter(invalid_output)

    with pytest.raises(ValueError) as exc_info:
        execute_prompt(
            prompt_id=2,
            runtime_inputs=_stage_ab_inputs_trade_friendly_es(),
            model_adapter=adapter,
        )

    message = str(exc_info.value)
    assert "market_regime" in message
    assert "value_context" in message
    assert "ANALYSIS_COMPLETE" in message
    assert "NO_TRADE" in message
    assert "key_levels" in message
    assert "structural_notes" in message
    assert "status" in message or "READY" in message


def test_rejects_stage_b_market_regime_near_synonym() -> None:
    invalid_output = _valid_contract_analysis("ES")
    invalid_output["market_regime"] = "trend_up"
    adapter = FakeStructuredAdapter(invalid_output)

    with pytest.raises(ValueError) as exc_info:
        execute_prompt(
            prompt_id=2,
            runtime_inputs=_stage_ab_inputs_trade_friendly_es(),
            model_adapter=adapter,
        )

    assert "trending_up" in str(exc_info.value)


def test_rejects_stage_b_prior_value_area_near_synonym() -> None:
    invalid_output = _valid_contract_analysis("ES")
    invalid_output["value_context"]["relative_to_prior_value_area"] = "overlapping_higher"
    adapter = FakeStructuredAdapter(invalid_output)

    with pytest.raises(ValueError) as exc_info:
        execute_prompt(
            prompt_id=2,
            runtime_inputs=_stage_ab_inputs_trade_friendly_es(),
            model_adapter=adapter,
        )

    message = str(exc_info.value)
    assert "above" in message
    assert "inside" in message
    assert "below" in message


def test_rejects_stage_b_current_developing_value_near_synonym() -> None:
    invalid_output = _valid_contract_analysis("ES")
    invalid_output["value_context"]["relative_to_current_developing_value"] = "above"
    adapter = FakeStructuredAdapter(invalid_output)

    with pytest.raises(ValueError) as exc_info:
        execute_prompt(
            prompt_id=2,
            runtime_inputs=_stage_ab_inputs_trade_friendly_es(),
            model_adapter=adapter,
        )

    message = str(exc_info.value)
    assert "above_vah" in message
    assert "inside_value" in message
    assert "below_val" in message


def test_rejects_stage_b_scalar_assumptions() -> None:
    invalid_output = _valid_contract_analysis("ES")
    invalid_output["assumptions"] = "Assume continuation."
    adapter = FakeStructuredAdapter(invalid_output)

    with pytest.raises(ValueError) as exc_info:
        execute_prompt(
            prompt_id=2,
            runtime_inputs=_stage_ab_inputs_trade_friendly_es(),
            model_adapter=adapter,
        )

    assert "valid list" in str(exc_info.value)


def test_accepts_stage_b_exact_valid_literals_on_es_case() -> None:
    adapter = FakeStructuredAdapter(_valid_contract_analysis("ES"))

    result = execute_prompt(
        prompt_id=2,
        runtime_inputs=_stage_ab_inputs_trade_friendly_es(),
        model_adapter=adapter,
    )

    assert result.validated_output.market_regime == "range_bound"
    assert result.validated_output.value_context.relative_to_prior_value_area == "inside"
    assert (
        result.validated_output.value_context.relative_to_current_developing_value
        == "inside_value"
    )
    assert result.validated_output.assumptions == []


def test_rejects_prompt_3_nq_stage_b_with_too_many_support_levels() -> None:
    invalid_output = _valid_contract_analysis("NQ")
    invalid_output["key_levels"]["support_levels"] = [18334.0, 18320.0, 18302.0, 18290.0]
    adapter = FakeStructuredAdapter(invalid_output)

    with pytest.raises(ValueError) as exc_info:
        execute_prompt(
            prompt_id=3,
            runtime_inputs={
                **_stage_ab_inputs("NQ"),
                "contract_specific_extension_json": {
                    "contract": "NQ",
                    "relative_strength_vs_es": 1.35,
                    "megacap_leadership_table": {"NVDA": "leading_higher"},
                },
            },
            model_adapter=adapter,
        )

    assert "support_levels" in str(exc_info.value)
    assert "at most 3 items" in str(exc_info.value)


def test_stage_ab_rendered_prompt_requires_full_sufficiency_gate_output_shape() -> None:
    adapter = FakeStructuredAdapter(_valid_sufficiency_gate_output("ES"))

    result = execute_prompt(
        prompt_id=2,
        runtime_inputs=_stage_ab_inputs_trade_friendly_es(),
        model_adapter=adapter,
    )

    assert "Always emit the full sufficiency_gate_output schema fields" in result.rendered_prompt
    assert "Do not emit shorthand fields such as reason, missing_fields" in result.rendered_prompt


def test_rejects_live_like_stage_a_shorthand_insufficiency_output() -> None:
    invalid_output = {
        "status": "INSUFFICIENT_DATA",
        "reason": "outside_allowed_hours",
        "missing_fields": ["session_open"],
        "data_quality_flags": [],
    }
    adapter = FakeStructuredAdapter(invalid_output)

    with pytest.raises(ValueError) as exc_info:
        execute_prompt(
            prompt_id=2,
            runtime_inputs=_stage_ab_inputs_trade_friendly_es(),
            model_adapter=adapter,
        )

    message = str(exc_info.value)
    assert "contract" in message
    assert "timestamp" in message
    assert "missing_inputs" in message
    assert "disqualifiers" in message
    assert "staleness_check" in message
    assert "challenge_state_valid" in message
    assert "reason" in message
    assert "missing_fields" in message


def test_rejects_live_like_stage_a_string_staleness_check() -> None:
    invalid_output = _valid_sufficiency_gate_output("ES", status="NEED_INPUT")
    invalid_output["missing_inputs"] = ["session_open"]
    invalid_output["staleness_check"] = "pass"
    adapter = FakeStructuredAdapter(invalid_output)

    with pytest.raises(ValueError) as exc_info:
        execute_prompt(
            prompt_id=2,
            runtime_inputs=_stage_ab_inputs_trade_friendly_es(),
            model_adapter=adapter,
        )

    message = str(exc_info.value)
    assert "staleness_check" in message
    assert "valid dictionary" in message


def test_rejects_wrong_contract_mapping() -> None:
    adapter = FakeStructuredAdapter(_valid_contract_analysis("ES"))

    with pytest.raises(ValueError) as exc_info:
        execute_prompt(
            prompt_id=4,
            runtime_inputs=_stage_ab_inputs("ES"),
            model_adapter=adapter,
        )

    assert "bound to contract CL" in str(exc_info.value)


def test_rejects_missing_render_slot() -> None:
    adapter = FakeStructuredAdapter(_valid_proposed_setup("ES"))
    runtime_inputs = _stage_c_inputs("ES")
    runtime_inputs.pop("contract_analysis_json")

    with pytest.raises(ValueError) as exc_info:
        execute_prompt(
            prompt_id=8,
            runtime_inputs=runtime_inputs,
            model_adapter=adapter,
        )

    assert "missing required runtime inputs" in str(exc_info.value)


def test_rejects_extra_render_slot() -> None:
    adapter = FakeStructuredAdapter(_valid_proposed_setup("ES"))
    runtime_inputs = _stage_c_inputs("ES")
    runtime_inputs["unexpected"] = "extra"

    with pytest.raises(ValueError) as exc_info:
        execute_prompt(
            prompt_id=8,
            runtime_inputs=runtime_inputs,
            model_adapter=adapter,
        )

    assert "unexpected runtime inputs" in str(exc_info.value)


def test_rejects_non_structured_model_output() -> None:
    adapter = FakeStructuredAdapter("not-json")

    with pytest.raises(TypeError) as exc_info:
        execute_prompt(
            prompt_id=8,
            runtime_inputs=_stage_c_inputs("ES"),
            model_adapter=adapter,
        )

    assert "structured output as a mapping" in str(exc_info.value)


def test_rejects_model_output_that_fails_bound_schema() -> None:
    invalid_output = _valid_proposed_setup("ES")
    invalid_output["direction"] = None
    adapter = FakeStructuredAdapter(invalid_output)

    with pytest.raises(ValueError) as exc_info:
        execute_prompt(
            prompt_id=8,
            runtime_inputs=_stage_c_inputs("ES"),
            model_adapter=adapter,
        )

    assert "failed schema validation" in str(exc_info.value)


def test_rejects_live_like_no_trade_reason_list_drift() -> None:
    invalid_output = {
        "$schema": "proposed_setup_v1",
        "stage": "setup_construction",
        "contract": "ES",
        "timestamp": "2026-01-14T14:07:00Z",
        "outcome": "NO_TRADE",
        "no_trade_reason": "directional_bias_unclear",
        "disqualification_reasons": ["directional_bias_unclear"],
    }
    adapter = FakeStructuredAdapter(invalid_output)

    with pytest.raises(ValueError) as exc_info:
        execute_prompt(
            prompt_id=8,
            runtime_inputs=_stage_c_inputs("ES"),
            model_adapter=adapter,
        )

    assert "disqualification_reasons" in str(exc_info.value)


def test_rejects_live_like_no_trade_missing_required_top_level_fields() -> None:
    invalid_output = {
        "$schema": "proposed_setup_v1",
        "stage": "setup_construction",
        "outcome": "NO_TRADE",
        "no_trade_reason": "directional_bias_unclear",
        "direction": None,
        "entry_price": None,
        "stop_price": None,
        "target_1": None,
        "target_2": None,
        "position_size": None,
        "risk_dollars": None,
        "reward_risk_ratio": None,
        "setup_class": None,
        "hold_time_estimate_minutes": None,
        "rationale": None,
        "disqualifiers": None,
        "sizing_math": None,
    }
    adapter = FakeStructuredAdapter(invalid_output)

    with pytest.raises(ValueError) as exc_info:
        execute_prompt(
            prompt_id=8,
            runtime_inputs=_stage_c_inputs("ES"),
            model_adapter=adapter,
        )

    message = str(exc_info.value)
    assert "contract" in message
    assert "timestamp" in message


def test_rejects_live_like_setup_proposed_missing_required_top_level_fields() -> None:
    invalid_output = _minimal_valid_proposed_setup("ES")
    invalid_output.pop("contract")
    invalid_output.pop("timestamp")
    adapter = FakeStructuredAdapter(invalid_output)

    with pytest.raises(ValueError) as exc_info:
        execute_prompt(
            prompt_id=8,
            runtime_inputs=_stage_c_inputs("ES"),
            model_adapter=adapter,
        )

    message = str(exc_info.value)
    assert "contract" in message
    assert "timestamp" in message


def test_rejects_live_like_setup_proposed_outcome_direction_and_sizing_math_drift() -> None:
    invalid_output = _minimal_valid_proposed_setup("ES")
    invalid_output.pop("outcome")
    invalid_output["direction"] = "bullish"
    invalid_output["sizing_math"] = "Max position size is 2 contracts and risk remains below the limit."
    adapter = FakeStructuredAdapter(invalid_output)

    with pytest.raises(ValueError) as exc_info:
        execute_prompt(
            prompt_id=8,
            runtime_inputs=_stage_c_inputs("ES"),
            model_adapter=adapter,
        )

    message = str(exc_info.value)
    assert "outcome" in message
    assert "LONG" in message
    assert "SHORT" in message
    assert "sizing_math" in message


def test_rejects_live_like_setup_proposed_invalid_setup_class_label() -> None:
    invalid_output = _minimal_valid_proposed_setup("ES")
    invalid_output["setup_class"] = "intraday_trend"
    adapter = FakeStructuredAdapter(invalid_output)

    with pytest.raises(ValueError) as exc_info:
        execute_prompt(
            prompt_id=8,
            runtime_inputs=_stage_c_inputs_trade_friendly("ES"),
            model_adapter=adapter,
        )

    message = str(exc_info.value)
    assert "setup_class" in message
    assert "intraday_swing" in message


def test_runtime_uses_prompt_asset_boundary_binding_not_caller_schema_name() -> None:
    adapter = FakeStructuredAdapter(_valid_risk_authorization("ES"))

    with pytest.raises(ValueError) as exc_info:
        execute_prompt(
            prompt_id=8,
            runtime_inputs=_stage_c_inputs("ES"),
            model_adapter=adapter,
        )

    assert "failed schema validation" in str(exc_info.value)


def test_runtime_constructs_request_and_propagates_boundary_metadata_unchanged() -> None:
    adapter = FakeStructuredAdapter(_valid_contract_analysis("CL"))

    execute_prompt(
        prompt_id=4,
        runtime_inputs=_stage_ab_inputs("CL"),
        model_adapter=adapter,
    )

    request = adapter.calls[0]
    assert request == StructuredGenerationRequest(
        prompt_id=4,
        rendered_prompt=request.rendered_prompt,
        expected_output_boundaries=("sufficiency_gate_output", "contract_analysis"),
        schema_model_names=("SufficiencyGateOutput", "ContractAnalysis"),
    )


def test_caller_cannot_override_prompt_asset_schema_binding_via_runtime_inputs() -> None:
    adapter = FakeStructuredAdapter(_valid_proposed_setup("ES"))
    runtime_inputs = _stage_c_inputs("ES")
    runtime_inputs["schema_model_names"] = ["RiskAuthorization"]

    with pytest.raises(ValueError) as exc_info:
        execute_prompt(
            prompt_id=8,
            runtime_inputs=runtime_inputs,
            model_adapter=adapter,
        )

    assert "unexpected runtime inputs" in str(exc_info.value)
