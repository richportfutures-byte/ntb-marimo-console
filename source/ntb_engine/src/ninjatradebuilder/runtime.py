from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from pydantic import BaseModel, ValidationError

from .prompt_assets import (
    READINESS_PROMPT_ID,
    READINESS_SUPPORTED_TRIGGER_FAMILIES,
    PromptAsset,
    get_prompt_asset,
)
from .schemas.outputs import (
    ContractAnalysis,
    ProposedSetup,
    ReadinessEngineOutput,
    RiskAuthorization,
    SufficiencyGateOutput,
)
from .watchman import build_watchman_context_json_from_runtime_inputs

ValidatedOutput = (
    SufficiencyGateOutput
    | ContractAnalysis
    | ProposedSetup
    | RiskAuthorization
    | ReadinessEngineOutput
)

BOUNDARY_MODEL_REGISTRY = {
    "sufficiency_gate_output": SufficiencyGateOutput,
    "contract_analysis": ContractAnalysis,
    "proposed_setup": ProposedSetup,
    "risk_authorization": RiskAuthorization,
    "readiness_engine_output": ReadinessEngineOutput,
}

CONTRACT_SLOT_NAMES = (
    "contract_metadata_json",
    "market_packet_json",
    "contract_specific_extension_json",
    "contract_analysis_json",
    "proposed_setup_json",
)

READINESS_TIME_RECHECK_TIMESTAMP_SLOT_NAMES = (
    "recheck_at_time",
)

READINESS_PRICE_LEVEL_SLOT_NAMES = (
    "price_level",
)


class StructuredModelAdapter(Protocol):
    def generate_structured(self, request: "StructuredGenerationRequest") -> Mapping[str, Any]:
        ...


@dataclass(frozen=True)
class PromptExecutionResult:
    prompt_id: int
    output_boundary: str
    rendered_prompt: str
    raw_model_output: Mapping[str, Any]
    validated_output: ValidatedOutput


@dataclass(frozen=True)
class StructuredGenerationRequest:
    prompt_id: int
    rendered_prompt: str
    expected_output_boundaries: tuple[str, ...]
    schema_model_names: tuple[str, ...]


def _normalize_runtime_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True)
    return value


def _extract_contracts(runtime_inputs: Mapping[str, Any]) -> dict[str, str]:
    contracts: dict[str, str] = {}
    for slot_name in CONTRACT_SLOT_NAMES:
        value = runtime_inputs.get(slot_name)
        if isinstance(value, Mapping):
            contract = value.get("contract")
            if isinstance(contract, str):
                contracts[slot_name] = contract
    return contracts


def _validate_contract_scope(asset: PromptAsset, runtime_inputs: Mapping[str, Any]) -> str | None:
    contracts_by_slot = _extract_contracts(runtime_inputs)
    unique_contracts = set(contracts_by_slot.values())

    if len(unique_contracts) > 1:
        raise ValueError(
            f"Contract mismatch across runtime inputs for prompt {asset.prompt_id}: {contracts_by_slot}"
        )

    resolved_contract = next(iter(unique_contracts), None)
    if asset.contract_scope != "shared":
        if resolved_contract is None:
            raise ValueError(
                f"Prompt {asset.prompt_id} requires a contract-bearing runtime input for contract validation."
            )
        if resolved_contract != asset.contract_scope:
            raise ValueError(
                f"Prompt {asset.prompt_id} is bound to contract {asset.contract_scope}, "
                f"but runtime inputs resolved to {resolved_contract}."
            )

    return resolved_contract


def _validate_structured_output(asset: PromptAsset, raw_model_output: Any) -> tuple[str, ValidatedOutput]:
    if not isinstance(raw_model_output, Mapping):
        raise TypeError("Model adapter must return structured output as a mapping.")

    matches: list[tuple[str, ValidatedOutput]] = []
    validation_errors: dict[str, str] = {}
    for boundary in asset.expected_output_boundaries:
        model_cls = BOUNDARY_MODEL_REGISTRY[boundary]
        try:
            validated = model_cls.model_validate(raw_model_output)
        except ValidationError as exc:
            validation_errors[boundary] = str(exc)
            continue
        matches.append((boundary, validated))

    if not matches:
        details = "; ".join(
            f"{boundary}: {message}" for boundary, message in validation_errors.items()
        )
        raise ValueError(
            f"Model output failed schema validation for prompt {asset.prompt_id}: {details}"
        )

    if len(matches) > 1:
        boundaries = ", ".join(boundary for boundary, _ in matches)
        raise ValueError(
            f"Model output matched multiple output boundaries for prompt {asset.prompt_id}: {boundaries}"
        )

    return matches[0]


def _first_non_empty_string(
    payload: Mapping[str, Any],
    slot_names: tuple[str, ...],
) -> tuple[str, str] | None:
    for slot_name in slot_names:
        value = payload.get(slot_name)
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                return slot_name, normalized
    return None


def _first_numeric_value(payload: Mapping[str, Any], slot_names: tuple[str, ...]) -> tuple[str, float] | None:
    for slot_name in slot_names:
        value = payload.get(slot_name)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            return slot_name, float(value)
    return None


def _normalize_readiness_trigger(readiness_trigger: Any) -> dict[str, Any]:
    normalized_trigger = _normalize_runtime_value(readiness_trigger)
    if not isinstance(normalized_trigger, Mapping):
        raise ValueError("Readiness trigger must be a mapping payload.")

    family_match = _first_non_empty_string(normalized_trigger, ("trigger_family",))
    if family_match is None:
        raise ValueError(
            "Readiness trigger is malformed: missing non-empty trigger_family."
        )

    _, trigger_family = family_match
    if trigger_family not in READINESS_SUPPORTED_TRIGGER_FAMILIES:
        raise ValueError(
            "Readiness trigger family is unsupported; supported families are "
            f"{READINESS_SUPPORTED_TRIGGER_FAMILIES}."
        )

    normalized_payload = dict(normalized_trigger)
    normalized_payload["trigger_family"] = trigger_family

    if trigger_family == "recheck_at_time":
        recheck_match = _first_non_empty_string(
            normalized_trigger,
            READINESS_TIME_RECHECK_TIMESTAMP_SLOT_NAMES,
        )
        if recheck_match is None:
            raise ValueError(
                "Readiness trigger is malformed for recheck_at_time: "
                "missing non-empty recheck_at_time/target_time."
            )
        _, recheck_at_time = recheck_match
        normalized_payload["recheck_at_time"] = recheck_at_time
        return normalized_payload

    price_level_match = _first_numeric_value(normalized_trigger, READINESS_PRICE_LEVEL_SLOT_NAMES)
    if price_level_match is None:
        raise ValueError(
            "Readiness trigger is malformed for price_level_touch: "
            "missing numeric price_level/trigger_price/price."
        )
    _, price_level = price_level_match
    normalized_payload["price_level"] = price_level
    return normalized_payload


def _build_generation_request(asset: PromptAsset, rendered_prompt: str) -> StructuredGenerationRequest:
    return StructuredGenerationRequest(
        prompt_id=asset.prompt_id,
        rendered_prompt=rendered_prompt,
        expected_output_boundaries=asset.expected_output_boundaries,
        schema_model_names=tuple(
            BOUNDARY_MODEL_REGISTRY[boundary].__name__
            for boundary in asset.expected_output_boundaries
        ),
    )


def execute_prompt(
    *,
    prompt_id: int,
    runtime_inputs: Mapping[str, Any],
    model_adapter: StructuredModelAdapter,
) -> PromptExecutionResult:
    try:
        asset = get_prompt_asset(prompt_id)
    except KeyError as exc:
        raise ValueError(f"Unknown prompt_id: {prompt_id}") from exc

    if not asset.expected_output_boundaries:
        raise ValueError(f"Prompt {prompt_id} has no executable output boundary.")

    normalized_inputs = {
        key: _normalize_runtime_value(value) for key, value in runtime_inputs.items()
    }
    expected_contract = _validate_contract_scope(asset, normalized_inputs)
    rendered_prompt = asset.render(normalized_inputs)
    request = _build_generation_request(asset, rendered_prompt)

    raw_model_output = model_adapter.generate_structured(request)
    output_boundary, validated_output = _validate_structured_output(asset, raw_model_output)

    output_contract = getattr(validated_output, "contract", None)
    if expected_contract is not None and output_contract != expected_contract:
        raise ValueError(
            f"Validated output contract {output_contract} does not match runtime contract {expected_contract}."
        )

    return PromptExecutionResult(
        prompt_id=asset.prompt_id,
        output_boundary=output_boundary,
        rendered_prompt=rendered_prompt,
        raw_model_output=raw_model_output,
        validated_output=validated_output,
    )


def run_readiness(
    *,
    runtime_inputs: Mapping[str, Any],
    readiness_trigger: Any,
    model_adapter: StructuredModelAdapter,
) -> PromptExecutionResult:
    normalized_runtime_inputs = dict(runtime_inputs)
    normalized_trigger = _normalize_readiness_trigger(readiness_trigger)
    normalized_runtime_inputs["readiness_trigger_json"] = normalized_trigger
    normalized_runtime_inputs["watchman_context_json"] = (
        build_watchman_context_json_from_runtime_inputs(
            normalized_runtime_inputs,
            normalized_trigger,
        )
    )

    result = execute_prompt(
        prompt_id=READINESS_PROMPT_ID,
        runtime_inputs=normalized_runtime_inputs,
        model_adapter=model_adapter,
    )

    if result.output_boundary != "readiness_engine_output":
        raise ValueError(
            "Readiness execution matched an unexpected boundary; "
            f"expected readiness_engine_output, got {result.output_boundary}."
        )

    return result
