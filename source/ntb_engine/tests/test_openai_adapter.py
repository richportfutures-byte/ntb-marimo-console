from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest

from ninjatradebuilder.openai_adapter import OpenAIAdapterError, OpenAIResponsesAdapter
from ninjatradebuilder.runtime import StructuredGenerationRequest, execute_prompt
from ninjatradebuilder.schemas.outputs import ContractAnalysis, ProposedSetup


@dataclass
class FakeOpenAIResponse:
    output_text: Any


class FakeResponsesClient:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return self.response


class FakeOpenAIClient:
    def __init__(self, response: Any) -> None:
        self.responses = FakeResponsesClient(response)


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


def _envelope(boundary: str, payload: dict[str, Any]) -> FakeOpenAIResponse:
    return FakeOpenAIResponse(output_text=json.dumps({"boundary": boundary, "payload": payload}))


def test_request_translation_is_correct() -> None:
    client = FakeOpenAIClient(_envelope("proposed_setup", _valid_proposed_setup("ES")))
    adapter = OpenAIResponsesAdapter(client=client, model="gpt-5")
    request = StructuredGenerationRequest(
        prompt_id=8,
        rendered_prompt="rendered prompt text",
        expected_output_boundaries=("proposed_setup",),
        schema_model_names=("ProposedSetup",),
    )

    payload = adapter.generate_structured(request)

    assert payload["contract"] == "ES"
    call = client.responses.calls[0]
    assert call["model"] == "gpt-5"
    assert call["input"] == "rendered prompt text"
    assert call["text"]["format"]["type"] == "json_schema"
    assert call["text"]["format"]["name"] == "ninjatradebuilder_prompt_8_response_envelope"
    assert call["text"]["format"]["strict"] is False
    assert call["text"]["format"]["schema"]["properties"]["boundary"]["enum"] == ["proposed_setup"]


def test_multi_boundary_metadata_is_preserved_correctly() -> None:
    client = FakeOpenAIClient(_envelope("contract_analysis", _valid_contract_analysis("CL")))
    adapter = OpenAIResponsesAdapter(client=client, model="gpt-5")
    request = StructuredGenerationRequest(
        prompt_id=4,
        rendered_prompt="cl prompt",
        expected_output_boundaries=("sufficiency_gate_output", "contract_analysis"),
        schema_model_names=("SufficiencyGateOutput", "ContractAnalysis"),
    )

    adapter.generate_structured(request)

    schema = client.responses.calls[0]["text"]["format"]["schema"]
    assert schema["properties"]["boundary"]["enum"] == [
        "sufficiency_gate_output",
        "contract_analysis",
    ]
    assert "SufficiencyGateOutput, ContractAnalysis" in client.responses.calls[0]["text"]["format"][
        "description"
    ]


def test_malformed_provider_output_is_rejected() -> None:
    client = FakeOpenAIClient(FakeOpenAIResponse(output_text="not json"))
    adapter = OpenAIResponsesAdapter(client=client, model="gpt-5")

    with pytest.raises(OpenAIAdapterError) as exc_info:
        adapter.generate_structured(
            StructuredGenerationRequest(
                prompt_id=8,
                rendered_prompt="prompt",
                expected_output_boundaries=("proposed_setup",),
                schema_model_names=("ProposedSetup",),
            )
        )

    assert "valid JSON" in str(exc_info.value)


def test_adapter_cannot_bypass_runtime_validation() -> None:
    client = FakeOpenAIClient(_envelope("proposed_setup", {"contract": "ES"}))
    adapter = OpenAIResponsesAdapter(client=client, model="gpt-5")

    with pytest.raises(ValueError) as exc_info:
        execute_prompt(
            prompt_id=8,
            runtime_inputs=_stage_c_inputs("ES"),
            model_adapter=adapter,
        )

    assert "failed schema validation" in str(exc_info.value)


def test_no_caller_supplied_override_can_replace_prompt_bound_validation() -> None:
    client = FakeOpenAIClient(_envelope("risk_authorization", _valid_proposed_setup("ES")))
    adapter = OpenAIResponsesAdapter(client=client, model="gpt-5")

    with pytest.raises(OpenAIAdapterError) as exc_info:
        execute_prompt(
            prompt_id=8,
            runtime_inputs=_stage_c_inputs("ES"),
            model_adapter=adapter,
        )

    assert "not allowed for prompt 8" in str(exc_info.value)


def test_end_to_end_execution_through_openai_adapter_boundary() -> None:
    client = FakeOpenAIClient(_envelope("contract_analysis", _valid_contract_analysis("CL")))
    adapter = OpenAIResponsesAdapter(client=client, model="gpt-5")

    result = execute_prompt(
        prompt_id=4,
        runtime_inputs=_stage_ab_inputs("CL"),
        model_adapter=adapter,
    )

    assert result.output_boundary == "contract_analysis"
    assert isinstance(result.validated_output, ContractAnalysis)
    assert result.validated_output.contract == "CL"
