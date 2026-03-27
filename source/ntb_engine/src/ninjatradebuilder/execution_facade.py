from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from . import pipeline as pipeline_module
from . import readiness_adapter as readiness_adapter_module
from . import runtime as runtime_module
from . import watchman as watchman_module
from .logging_record import (
    DEFAULT_LOG_PATH,
    RunHistoryRecord,
    append_log_record,
    build_logging_record_from_pipeline,
    build_logging_record_from_watchman,
)
from .pipeline import PipelineExecutionResult
from .schemas.packet import HistoricalPacket
from .schemas.triggers import validate_readiness_trigger
from .watchman import WatchmanReadinessContext


def _normalize_packet_mapping(packet: HistoricalPacket | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(packet, HistoricalPacket):
        return packet.model_dump(mode="json", by_alias=True)
    if not isinstance(packet, Mapping):
        raise TypeError("packet must be a historical_packet_v1 mapping or HistoricalPacket.")
    return dict(packet)


def _extract_packet_from_bundle(packet_bundle: Mapping[str, Any], contract: str) -> dict[str, Any]:
    shared = packet_bundle.get("shared")
    contracts = packet_bundle.get("contracts")
    if not isinstance(shared, Mapping) or not isinstance(contracts, Mapping):
        raise ValueError(
            "Packet bundle must contain object-valued shared and contracts sections."
        )

    contract_payload = contracts.get(contract)
    if not isinstance(contract_payload, Mapping):
        raise ValueError(f"Packet bundle does not contain contract {contract}.")

    return {
        "$schema": "historical_packet_v1",
        "challenge_state": shared["challenge_state"],
        "attached_visuals": shared["attached_visuals"],
        "contract_metadata": contract_payload["contract_metadata"],
        "market_packet": contract_payload["market_packet"],
        "contract_specific_extension": contract_payload["contract_specific_extension"],
    }


def _resolve_single_packet(
    packet: HistoricalPacket | Mapping[str, Any],
    contract: str | None,
) -> dict[str, Any]:
    normalized_packet = _normalize_packet_mapping(packet)

    if "shared" in normalized_packet and "contracts" in normalized_packet:
        if not contract:
            raise ValueError("Packet bundle inputs require an explicit contract.")
        return _extract_packet_from_bundle(normalized_packet, contract)

    packet_contract = normalized_packet.get("market_packet", {}).get("contract")
    if contract and packet_contract is not None and packet_contract != contract:
        raise ValueError(
            f"Requested contract {contract} does not match packet contract {packet_contract}."
        )
    return normalized_packet


def _resolve_pipeline_evaluation_timestamp(
    packet_payload: Mapping[str, Any],
    evaluation_timestamp_iso: str | None,
) -> str:
    if evaluation_timestamp_iso:
        return evaluation_timestamp_iso

    market_packet = packet_payload.get("market_packet")
    if not isinstance(market_packet, Mapping):
        raise ValueError(
            "Pipeline facade requires market_packet.timestamp when no evaluation_timestamp_iso is provided."
        )

    timestamp = market_packet.get("timestamp")
    if not isinstance(timestamp, str) or not timestamp.strip():
        raise ValueError(
            "Pipeline facade requires market_packet.timestamp when no evaluation_timestamp_iso is provided."
        )
    return timestamp


def _summary_field(value: Any, field_name: str) -> Any:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return value.get(field_name)
    return getattr(value, field_name, None)


def sweep_watchman(
    packet_bundle: Mapping[str, Any],
    readiness_trigger: Mapping[str, Any],
) -> dict[str, WatchmanReadinessContext]:
    if not isinstance(packet_bundle, Mapping):
        raise TypeError("packet_bundle must be a mapping.")

    validated_trigger = validate_readiness_trigger(readiness_trigger)

    shared = packet_bundle.get("shared")
    contracts = packet_bundle.get("contracts")
    if not isinstance(shared, Mapping) or not isinstance(contracts, Mapping):
        raise ValueError(
            "Packet bundle must contain object-valued shared and contracts sections."
        )

    supported_contracts = set(readiness_adapter_module.SUPPORTED_PACKET_READINESS_CONTRACTS)
    results: dict[str, WatchmanReadinessContext] = {}
    for contract in contracts:
        if contract not in supported_contracts:
            continue

        packet_payload = _extract_packet_from_bundle(packet_bundle, contract)
        runtime_inputs = readiness_adapter_module.build_readiness_runtime_inputs_from_packet(
            packet_payload
        )
        results[contract] = watchman_module.build_watchman_context_from_runtime_inputs(
            runtime_inputs,
            validated_trigger,
        )

    return results


def sweep_watchman_and_log(
    packet_bundle: Mapping[str, Any],
    readiness_trigger: Mapping[str, Any],
    *,
    trigger_family: str,
    log_path: Path | str = DEFAULT_LOG_PATH,
    notes: str | None = None,
) -> tuple[dict[str, WatchmanReadinessContext], list[RunHistoryRecord]]:
    sweep_results = sweep_watchman(packet_bundle, readiness_trigger)
    records: list[RunHistoryRecord] = []

    for contract in sorted(sweep_results):
        record = build_logging_record_from_watchman(
            sweep_results[contract],
            trigger_family,
            notes=notes,
        )
        append_log_record(record, log_path)
        records.append(record)

    return sweep_results, records


def run_readiness_for_contract(
    packet_or_runtime_inputs: HistoricalPacket | Mapping[str, Any],
    trigger: Any,
    *,
    model_adapter: runtime_module.StructuredModelAdapter,
) -> runtime_module.PromptExecutionResult:
    normalized_payload = _normalize_packet_mapping(packet_or_runtime_inputs)

    if "shared" in normalized_payload and "contracts" in normalized_payload:
        raise ValueError(
            "run_readiness_for_contract requires a single contract packet or readiness runtime inputs."
        )

    validated_trigger = validate_readiness_trigger(trigger)

    return readiness_adapter_module.run_readiness(
        normalized_payload,
        validated_trigger,
        model_adapter=model_adapter,
    )


def run_pipeline(
    packet: HistoricalPacket | Mapping[str, Any],
    contract: str | None,
    *,
    model_adapter: runtime_module.StructuredModelAdapter,
    evaluation_timestamp_iso: str | None = None,
) -> PipelineExecutionResult:
    resolved_packet = _resolve_single_packet(packet, contract)
    resolved_evaluation_timestamp = _resolve_pipeline_evaluation_timestamp(
        resolved_packet,
        evaluation_timestamp_iso,
    )

    return pipeline_module.run_pipeline(
        packet=resolved_packet,
        evaluation_timestamp_iso=resolved_evaluation_timestamp,
        model_adapter=model_adapter,
    )


def run_pipeline_and_log(
    packet: HistoricalPacket | Mapping[str, Any],
    contract: str | None,
    readiness_trigger: Mapping[str, Any],
    *,
    model_adapter: runtime_module.StructuredModelAdapter,
    trigger_family: str,
    evaluation_timestamp_iso: str | None = None,
    log_path: Path | str = DEFAULT_LOG_PATH,
    notes: str | None = None,
) -> tuple[PipelineExecutionResult, RunHistoryRecord]:
    resolved_packet = _resolve_single_packet(packet, contract)
    market_packet = resolved_packet.get("market_packet", {})
    contract_name = (
        market_packet.get("contract")
        if isinstance(market_packet, Mapping)
        else contract or "UNKNOWN"
    )
    if not isinstance(contract_name, str) or not contract_name:
        contract_name = contract or "UNKNOWN"

    validated_trigger = validate_readiness_trigger(readiness_trigger)

    runtime_inputs = readiness_adapter_module.build_readiness_runtime_inputs_from_packet(
        resolved_packet
    )
    watchman_context = watchman_module.build_watchman_context_from_runtime_inputs(
        runtime_inputs,
        validated_trigger,
    )
    pipeline_result = run_pipeline(
        packet,
        contract_name,
        model_adapter=model_adapter,
        evaluation_timestamp_iso=evaluation_timestamp_iso,
    )
    record = build_logging_record_from_pipeline(
        watchman_context,
        pipeline_result,
        trigger_family,
        notes=notes,
    )
    append_log_record(record, log_path)
    return pipeline_result, record


def summarize_pipeline_result(
    result: PipelineExecutionResult | Mapping[str, Any],
) -> dict[str, Any]:
    if isinstance(result, BaseModel):
        normalized_result: PipelineExecutionResult | Mapping[str, Any] = result.model_dump(
            mode="json",
            by_alias=True,
        )
    else:
        normalized_result = result

    return {
        "contract": _summary_field(normalized_result, "contract"),
        "termination_stage": _summary_field(normalized_result, "termination_stage"),
        "final_decision": _summary_field(normalized_result, "final_decision"),
        "sufficiency_gate_status": _summary_field(
            _summary_field(normalized_result, "sufficiency_gate_output"),
            "status",
        ),
        "contract_analysis_outcome": _summary_field(
            _summary_field(normalized_result, "contract_analysis"),
            "outcome",
        ),
        "proposed_setup_outcome": _summary_field(
            _summary_field(normalized_result, "proposed_setup"),
            "outcome",
        ),
        "risk_authorization_decision": _summary_field(
            _summary_field(normalized_result, "risk_authorization"),
            "decision",
        ),
    }


__all__ = [
    "run_pipeline",
    "run_pipeline_and_log",
    "run_readiness_for_contract",
    "summarize_pipeline_result",
    "sweep_watchman",
    "sweep_watchman_and_log",
]
