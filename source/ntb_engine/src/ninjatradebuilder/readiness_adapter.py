from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .prompt_assets import MASTER_DOCTRINE_TEMPLATE
from . import runtime as runtime_module
from .runtime import PromptExecutionResult, StructuredModelAdapter
from .validation import validate_historical_packet

SUPPORTED_PACKET_READINESS_CONTRACTS = ("ES", "NQ", "CL", "ZN", "6E", "MGC")
READINESS_RUNTIME_INPUT_SLOT_NAMES: tuple[str, ...] = (
    "master_doctrine_text",
    "evaluation_timestamp_iso",
    "challenge_state_json",
    "contract_metadata_json",
    "market_packet_json",
    "contract_specific_extension_json",
    "attached_visuals_json",
)


def build_readiness_runtime_inputs_from_packet(packet_payload: Mapping[str, Any]) -> dict[str, Any]:
    packet = validate_historical_packet(packet_payload)
    if packet.market_packet.contract not in SUPPORTED_PACKET_READINESS_CONTRACTS:
        raise ValueError(
            "Packet-backed readiness conversion is currently supported for ES, NQ, CL, ZN, 6E, and MGC only."
        )

    return {
        "master_doctrine_text": MASTER_DOCTRINE_TEMPLATE,
        "evaluation_timestamp_iso": packet.market_packet.timestamp.isoformat().replace("+00:00", "Z"),
        "challenge_state_json": packet.challenge_state.model_dump(mode="json", by_alias=True),
        "contract_metadata_json": packet.contract_metadata.model_dump(mode="json", by_alias=True),
        "market_packet_json": packet.market_packet.model_dump(mode="json", by_alias=True),
        "contract_specific_extension_json": packet.contract_specific_extension.model_dump(
            mode="json",
            by_alias=True,
        ),
        "attached_visuals_json": packet.attached_visuals.model_dump(mode="json", by_alias=True),
    }


def is_readiness_runtime_inputs(payload: Mapping[str, Any]) -> bool:
    return all(slot_name in payload for slot_name in READINESS_RUNTIME_INPUT_SLOT_NAMES)


def run_readiness(
    packet_or_runtime_inputs: Mapping[str, Any],
    readiness_trigger: Any,
    *,
    model_adapter: StructuredModelAdapter,
) -> PromptExecutionResult:
    if is_readiness_runtime_inputs(packet_or_runtime_inputs):
        runtime_inputs = dict(packet_or_runtime_inputs)
    else:
        runtime_inputs = build_readiness_runtime_inputs_from_packet(packet_or_runtime_inputs)

    return runtime_module.run_readiness(
        runtime_inputs=runtime_inputs,
        readiness_trigger=readiness_trigger,
        model_adapter=model_adapter,
    )
