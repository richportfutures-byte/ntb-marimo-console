from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from pydantic import BaseModel

from .prompt_assets import render_prompt
from .runtime import StructuredModelAdapter, execute_prompt
from .schemas.outputs import (
    ContractAnalysis,
    FinalDecision,
    ProposedSetup,
    RiskAuthorization,
    SufficiencyGateOutput,
    TerminationStage,
)
from .schemas.packet import HistoricalPacket
from .validation import validate_historical_packet

STAGE_AB_PROMPT_BY_CONTRACT = {
    "ES": 2,
    "NQ": 3,
    "CL": 4,
    "ZN": 5,
    "6E": 6,
    "MGC": 7,
}

MASTER_DOCTRINE_TEXT = render_prompt(1)


@dataclass(frozen=True)
class PipelineExecutionResult:
    contract: str
    termination_stage: TerminationStage
    final_decision: FinalDecision
    sufficiency_gate_output: SufficiencyGateOutput | None = None
    contract_analysis: ContractAnalysis | None = None
    proposed_setup: ProposedSetup | None = None
    risk_authorization: RiskAuthorization | None = None


def _coerce_packet(packet: HistoricalPacket | Mapping[str, Any]) -> HistoricalPacket:
    if isinstance(packet, HistoricalPacket):
        return packet
    return validate_historical_packet(packet)


def _map_stage_d_final_decision(decision: str) -> FinalDecision:
    return {
        "APPROVED": "TRADE_APPROVED",
        "REDUCED": "TRADE_REDUCED",
        "REJECTED": "TRADE_REJECTED",
    }[decision]


def _normalize_json_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True)
    if isinstance(value, list):
        return [_normalize_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _normalize_json_value(item) for key, item in value.items()}
    return value


def run_pipeline(
    *,
    packet: HistoricalPacket | Mapping[str, Any],
    evaluation_timestamp_iso: str,
    model_adapter: StructuredModelAdapter,
) -> PipelineExecutionResult:
    validated_packet = _coerce_packet(packet)
    contract = validated_packet.market_packet.contract
    stage_ab_prompt_id = STAGE_AB_PROMPT_BY_CONTRACT[contract]

    stage_ab_result = execute_prompt(
        prompt_id=stage_ab_prompt_id,
        runtime_inputs={
            "master_doctrine_text": MASTER_DOCTRINE_TEXT,
            "evaluation_timestamp_iso": evaluation_timestamp_iso,
            "challenge_state_json": validated_packet.challenge_state,
            "contract_metadata_json": validated_packet.contract_metadata,
            "market_packet_json": validated_packet.market_packet,
            "contract_specific_extension_json": validated_packet.contract_specific_extension,
            "attached_visuals_json": validated_packet.attached_visuals,
        },
        model_adapter=model_adapter,
    )

    if stage_ab_result.output_boundary == "sufficiency_gate_output":
        sufficiency_gate_output = stage_ab_result.validated_output
        assert isinstance(sufficiency_gate_output, SufficiencyGateOutput)
        return PipelineExecutionResult(
            contract=contract,
            termination_stage="sufficiency_gate",
            final_decision=sufficiency_gate_output.status,
            sufficiency_gate_output=sufficiency_gate_output,
        )

    contract_analysis = stage_ab_result.validated_output
    assert isinstance(contract_analysis, ContractAnalysis)

    if contract_analysis.outcome == "NO_TRADE":
        return PipelineExecutionResult(
            contract=contract,
            termination_stage="contract_market_read",
            final_decision="NO_TRADE",
            contract_analysis=contract_analysis,
        )

    stage_c_result = execute_prompt(
        prompt_id=8,
        runtime_inputs={
            "master_doctrine_text": MASTER_DOCTRINE_TEXT,
            "evaluation_timestamp_iso": evaluation_timestamp_iso,
            "current_price": validated_packet.market_packet.current_price,
            "challenge_state_json": validated_packet.challenge_state,
            "contract_metadata_json": validated_packet.contract_metadata,
            "contract_analysis_json": contract_analysis,
        },
        model_adapter=model_adapter,
    )

    proposed_setup = stage_c_result.validated_output
    assert isinstance(proposed_setup, ProposedSetup)
    if proposed_setup.outcome == "NO_TRADE":
        return PipelineExecutionResult(
            contract=contract,
            termination_stage="setup_construction",
            final_decision="NO_TRADE",
            contract_analysis=contract_analysis,
            proposed_setup=proposed_setup,
        )

    stage_d_result = execute_prompt(
        prompt_id=9,
        runtime_inputs={
            "master_doctrine_text": MASTER_DOCTRINE_TEXT,
            "evaluation_timestamp_iso": evaluation_timestamp_iso,
            "challenge_state_json": validated_packet.challenge_state,
            "contract_metadata_json": validated_packet.contract_metadata,
            "proposed_setup_json": proposed_setup,
            "event_calendar_remainder_json": _normalize_json_value(
                validated_packet.market_packet.event_calendar_remainder
            ),
        },
        model_adapter=model_adapter,
    )

    risk_authorization = stage_d_result.validated_output
    assert isinstance(risk_authorization, RiskAuthorization)
    return PipelineExecutionResult(
        contract=contract,
        termination_stage="risk_authorization",
        final_decision=_map_stage_d_final_decision(risk_authorization.decision),
        contract_analysis=contract_analysis,
        proposed_setup=proposed_setup,
        risk_authorization=risk_authorization,
    )
