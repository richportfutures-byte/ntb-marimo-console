from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from .config import DEFAULT_GEMINI_MODEL, ConfigError, GeminiStartupConfig, load_gemini_startup_config
from .gemini_adapter import GeminiAdapterError, GeminiResponsesAdapter, genai
from .prompt_assets import READINESS_PROMPT_ID
from .readiness_adapter import (
    SUPPORTED_PACKET_READINESS_CONTRACTS,
    build_readiness_runtime_inputs_from_packet,
)
from .runtime import PromptExecutionResult, StructuredGenerationRequest, run_readiness

ClientFactory = Callable[[GeminiStartupConfig], Any]
FAILURE_CLASSES = (
    "configuration_error",
    "input_error",
    "provider_error",
    "schema_validation_error",
    "contract_mismatch_error",
    "unexpected_runtime_error",
)
FIXTURE_ROOT = Path("tests/fixtures/readiness")


class ReadinessVerificationError(ValueError):
    pass


class ContractMismatchError(ReadinessVerificationError):
    pass


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ninjatradebuilder.readiness_verify",
        description=(
            "Operator-invoked live readiness verification for the frozen readiness_engine_output_v1 contract. "
            "Use one explicit input mode per run, then either target a single contract or sweep all supported contracts."
        ),
    )
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--fixture",
        action="store_true",
        help=(
            "Use deterministic readiness fixtures under tests/fixtures/readiness. "
            "Combine with --contract for a single fixture check or --all-contracts for a contract sweep."
        ),
    )
    mode_group.add_argument(
        "--packet-file",
        help=(
            "Path to a historical_packet_v1 JSON file or supported multi-contract packet bundle. "
            "This mode converts packet input into readiness runtime inputs before verification."
        ),
    )
    mode_group.add_argument(
        "--runtime-input-file",
        help=(
            "Path to an explicit readiness runtime input JSON object. "
            "Use this when packet conversion is not desired and the runtime inputs are already prepared."
        ),
    )
    parser.add_argument(
        "--trigger-file",
        help=(
            "Path to the readiness trigger JSON file. Required for --packet-file and --runtime-input-file. "
            "Ignored for --fixture because fixture mode uses contract-specific fixture triggers."
        ),
    )
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument(
        "--contract",
        choices=SUPPORTED_PACKET_READINESS_CONTRACTS,
        help="Verify a single readiness contract.",
    )
    target_group.add_argument(
        "--all-contracts",
        action="store_true",
        help=(
            "Sweep every supported readiness contract backed by packet conversion support: "
            "ES, NQ, CL, ZN, 6E, and MGC."
        ),
    )
    parser.add_argument(
        "--packet-contract",
        choices=SUPPORTED_PACKET_READINESS_CONTRACTS,
        help=(
            "Required when --packet-file points to a multi-contract bundle so the packet source contract is explicit. "
            "Not used for single historical_packet_v1 files."
        ),
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_GEMINI_MODEL,
        help=f"Gemini model identifier. Defaults to {DEFAULT_GEMINI_MODEL}.",
    )
    parser.add_argument(
        "--artifact-file",
        help=(
            "Optional path for the operator-facing verification artifact JSON. "
            "Defaults to ./artifacts/readiness-verification/<timestamp>.json."
        ),
    )
    return parser


def _normalize_for_json(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True)
    if is_dataclass(value):
        return {key: _normalize_for_json(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _normalize_for_json(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_normalize_for_json(item) for item in value]
    return value


def _load_json_file(path: Path, *, label: str) -> Any:
    if not path.is_file():
        raise ReadinessVerificationError(f"{label} does not exist: {path}")
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ReadinessVerificationError(f"{label} is not valid JSON: {path}") from exc


def _extract_packet_from_bundle(bundle: Mapping[str, Any], contract: str) -> dict[str, Any]:
    contracts = bundle.get("contracts")
    shared = bundle.get("shared")
    if not isinstance(contracts, Mapping) or not isinstance(shared, Mapping):
        raise ReadinessVerificationError(
            "Packet bundle must contain object-valued shared and contracts sections."
        )
    contract_payload = contracts.get(contract)
    if not isinstance(contract_payload, Mapping):
        raise ReadinessVerificationError(
            f"Packet bundle does not contain the requested contract {contract}."
        )
    return {
        "$schema": "historical_packet_v1",
        "challenge_state": shared["challenge_state"],
        "attached_visuals": shared["attached_visuals"],
        "contract_metadata": contract_payload["contract_metadata"],
        "market_packet": contract_payload["market_packet"],
        "contract_specific_extension": contract_payload["contract_specific_extension"],
    }


def _resolve_packet_payload(path: Path, *, packet_contract: str | None) -> tuple[str, dict[str, Any], dict[str, str]]:
    payload = _load_json_file(path, label="Packet file")
    if not isinstance(payload, Mapping):
        raise ReadinessVerificationError("Packet file must decode to a JSON object.")
    source_details = {"packet_file": str(path)}
    if payload.get("$schema") == "historical_packet_v1":
        if packet_contract is not None:
            source_details["packet_contract"] = packet_contract
        return "packet_file", dict(payload), source_details
    if "shared" in payload and "contracts" in payload:
        if packet_contract is None:
            raise ReadinessVerificationError(
                "Packet bundle verification requires --packet-contract so the source packet is explicit."
            )
        source_details["packet_contract"] = packet_contract
        return "packet_bundle", _extract_packet_from_bundle(payload, packet_contract), source_details
    raise ReadinessVerificationError(
        "Packet file must be a historical_packet_v1 object or a supported multi-contract packet bundle."
    )


def _fixture_runtime_inputs(contract: str) -> dict[str, Any]:
    path = FIXTURE_ROOT / "zn_runtime_inputs.valid.json"
    if contract != "ZN":
        raise ReadinessVerificationError(
            f"Fixture verification currently supports only ZN; {contract} requires packet or runtime-input mode."
        )
    payload = _load_json_file(path, label="Fixture runtime input")
    if not isinstance(payload, Mapping):
        raise ReadinessVerificationError("Fixture runtime input must decode to an object.")
    return dict(payload)


def _fixture_trigger(contract: str) -> dict[str, Any]:
    path = FIXTURE_ROOT / "zn_recheck_trigger.valid.json"
    if contract != "ZN":
        raise ReadinessVerificationError(
            f"Fixture verification currently supports only ZN; {contract} requires packet or runtime-input mode."
        )
    payload = _load_json_file(path, label="Fixture trigger")
    if not isinstance(payload, Mapping):
        raise ReadinessVerificationError("Fixture trigger must decode to an object.")
    return dict(payload)


def _default_artifact_path() -> Path:
    from datetime import datetime, UTC

    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return Path("artifacts") / "readiness-verification" / f"{timestamp}.json"


def _classify_failure(exc: Exception) -> str:
    if isinstance(exc, ConfigError):
        return "configuration_error"
    if isinstance(exc, ContractMismatchError):
        return "contract_mismatch_error"
    if isinstance(exc, (ReadinessVerificationError, FileNotFoundError, json.JSONDecodeError)):
        return "input_error"
    if isinstance(exc, GeminiAdapterError):
        return "provider_error"
    if isinstance(exc, ValidationError):
        return "schema_validation_error"
    message = str(exc).lower()
    if "schema validation" in message or "matched multiple output boundaries" in message:
        return "schema_validation_error"
    if "contract mismatch" in message or "does not match runtime contract" in message:
        return "contract_mismatch_error"
    return "unexpected_runtime_error"


def _operator_summary(*, contract: str, passed: bool, validation_outcome: str, failure_classification: str | None) -> str:
    if passed:
        return f"{contract}: PASS ({validation_outcome})."
    return f"{contract}: FAIL ({failure_classification or 'unexpected_runtime_error'})."


def _truncate_excerpt(value: Any, *, limit: int = 280) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = value.strip()
    else:
        text = json.dumps(_normalize_for_json(value), sort_keys=True)
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _build_result_record(
    *,
    contract: str,
    invocation_mode: str,
    source_descriptor: dict[str, str],
    config: GeminiStartupConfig | None,
    result: PromptExecutionResult | None,
    error: Exception | None,
    requested_trigger_path: str | None,
) -> dict[str, Any]:
    passed = error is None and result is not None
    failure_classification = None if passed else _classify_failure(error or RuntimeError("missing result"))
    validated_output = None
    validation_outcome = "failed"
    prompt_sha256 = None
    raw_excerpt = None
    if result is not None:
        validated_output = _normalize_for_json(result.validated_output)
        validation_outcome = "validated" if passed else "validation_failed"
        prompt_sha256 = hashlib.sha256(result.rendered_prompt.encode("utf-8")).hexdigest()
        raw_excerpt = _truncate_excerpt(result.raw_model_output)
    return {
        "contract": contract,
        "passed": passed,
        "summary": _operator_summary(
            contract=contract,
            passed=passed,
            validation_outcome=validation_outcome,
            failure_classification=failure_classification,
        ),
        "model": config.model if config is not None else None,
        "invocation_mode": invocation_mode,
        "source": {
            **source_descriptor,
            **({"trigger_file": requested_trigger_path} if requested_trigger_path is not None else {}),
        },
        "prompt": {
            "prompt_id": READINESS_PROMPT_ID,
            "rendered_prompt_sha256": prompt_sha256,
        },
        "validation": {
            "outcome": validation_outcome,
            "output_boundary": result.output_boundary if result is not None else None,
        },
        "failure_classification": failure_classification,
        "error": None
        if error is None
        else {
            "type": error.__class__.__name__,
            "message": str(error),
        },
        "validated_output": validated_output,
        "debug": {
            "raw_model_output_excerpt": raw_excerpt,
        },
    }


def _build_client(config: GeminiStartupConfig, client_factory: ClientFactory | None) -> Any:
    if client_factory is not None:
        return client_factory(config)
    if genai is None:
        raise ImportError("google-genai SDK is required for readiness verification execution.")
    return genai.Client(
        api_key=config.api_key,
        http_options=GeminiResponsesAdapter._build_http_options(config),
    )


def _load_run_inputs(args: argparse.Namespace, contract: str) -> tuple[str, dict[str, Any], dict[str, Any], dict[str, str]]:
    if args.fixture:
        return (
            "fixture",
            _fixture_runtime_inputs(contract),
            _fixture_trigger(contract),
            {
                "fixture_runtime_inputs": f"readiness/{contract.lower()}_runtime_inputs.valid.json",
                "fixture_trigger": f"readiness/{contract.lower()}_recheck_trigger.valid.json",
            },
        )
    if args.packet_file:
        invocation_mode, packet_payload, source = _resolve_packet_payload(
            Path(args.packet_file),
            packet_contract=(contract if args.all_contracts else args.packet_contract),
        )
        if args.trigger_file is None:
            raise ReadinessVerificationError("--trigger-file is required with --packet-file.")
        runtime_inputs = build_readiness_runtime_inputs_from_packet(packet_payload)
        runtime_contract = runtime_inputs.get("contract_metadata_json", {}).get("contract")
        if runtime_contract != contract:
            raise ContractMismatchError(
                f"Requested contract {contract} does not match packet-derived contract {runtime_contract}."
            )
        trigger_payload = _load_json_file(Path(args.trigger_file), label="Trigger file")
        if not isinstance(trigger_payload, Mapping):
            raise ReadinessVerificationError("Trigger file must decode to a JSON object.")
        return invocation_mode, runtime_inputs, dict(trigger_payload), source
    if args.runtime_input_file:
        if args.trigger_file is None:
            raise ReadinessVerificationError("--trigger-file is required with --runtime-input-file.")
        runtime_inputs = _load_json_file(Path(args.runtime_input_file), label="Runtime input file")
        if not isinstance(runtime_inputs, Mapping):
            raise ReadinessVerificationError("Runtime input file must decode to a JSON object.")
        runtime_contract = runtime_inputs.get("contract_metadata_json", {}).get("contract")
        if runtime_contract != contract:
            raise ContractMismatchError(
                f"Requested contract {contract} does not match runtime-input contract {runtime_contract}."
            )
        trigger_payload = _load_json_file(Path(args.trigger_file), label="Trigger file")
        if not isinstance(trigger_payload, Mapping):
            raise ReadinessVerificationError("Trigger file must decode to a JSON object.")
        return (
            "runtime_input_file",
            dict(runtime_inputs),
            dict(trigger_payload),
            {"runtime_input_file": str(Path(args.runtime_input_file))},
        )
    raise ReadinessVerificationError("Exactly one verification input mode must be selected.")


def _validate_args(args: argparse.Namespace) -> None:
    if args.fixture and args.trigger_file is not None:
        raise ReadinessVerificationError("--trigger-file is not used with --fixture; fixture mode provides its own trigger fixture.")
    if args.runtime_input_file and args.packet_contract is not None:
        raise ReadinessVerificationError("--packet-contract is only valid with --packet-file.")
    if args.packet_file is None and args.packet_contract is not None:
        raise ReadinessVerificationError("--packet-contract requires --packet-file.")
    if args.packet_file is not None and args.trigger_file is None:
        raise ReadinessVerificationError("--trigger-file is required with --packet-file.")
    if args.runtime_input_file is not None and args.trigger_file is None:
        raise ReadinessVerificationError("--trigger-file is required with --runtime-input-file.")


def _contracts_for_run(args: argparse.Namespace) -> list[str]:
    if args.all_contracts:
        if args.fixture:
            return ["ZN"]
        if args.packet_file:
            if args.packet_contract is not None:
                raise ReadinessVerificationError(
                    "--all-contracts cannot be combined with --packet-contract; provide one packet or runtime-input file per contract instead."
                )
            payload = _load_json_file(Path(args.packet_file), label="Packet file")
            if not isinstance(payload, Mapping) or "contracts" not in payload:
                raise ReadinessVerificationError(
                    "--all-contracts with --packet-file requires a supported multi-contract packet bundle."
                )
            return list(SUPPORTED_PACKET_READINESS_CONTRACTS)
        raise ReadinessVerificationError(
            "--all-contracts is supported with --fixture or a multi-contract --packet-file bundle only."
        )
    return [args.contract]


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    stdout: Any = None,
    stderr: Any = None,
    client_factory: ClientFactory | None = None,
) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    args = build_parser().parse_args(list(argv) if argv is not None else None)

    try:
        _validate_args(args)
        contracts = _contracts_for_run(args)
    except Exception as exc:
        stderr.write(f"ERROR: {exc}\n")
        return 2

    artifact_path = Path(args.artifact_file) if args.artifact_file else _default_artifact_path()
    run_started_at = None
    try:
        from datetime import datetime, UTC

        run_started_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        config = load_gemini_startup_config(model=args.model)
        adapter = GeminiResponsesAdapter(
            client=_build_client(config, client_factory),
            model=config.model,
            timeout_seconds=config.timeout_seconds,
            max_retries=config.max_retries,
        )
        results: list[dict[str, Any]] = []
        failures = 0
        for contract in contracts:
            result = None
            error = None
            invocation_mode = "unknown"
            source = {}
            requested_trigger_path = str(Path(args.trigger_file)) if args.trigger_file else None
            try:
                invocation_mode, runtime_inputs, trigger_payload, source = _load_run_inputs(args, contract)
                result = run_readiness(
                    runtime_inputs=runtime_inputs,
                    readiness_trigger=trigger_payload,
                    model_adapter=adapter,
                )
            except Exception as exc:
                error = exc
                failures += 1
            results.append(
                _build_result_record(
                    contract=contract,
                    invocation_mode=invocation_mode,
                    source_descriptor=source,
                    config=config,
                    result=result,
                    error=error,
                    requested_trigger_path=requested_trigger_path,
                )
            )
        finished_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        artifact = {
            "artifact_schema": "readiness_verification_run_v1",
            "run": {
                "started_at": run_started_at,
                "finished_at": finished_at,
                "model": config.model,
                "invocation_mode": "contract_sweep" if len(contracts) > 1 else "single_contract",
                "requested_contracts": contracts,
                "artifact_path": str(artifact_path),
                "success": failures == 0,
                "summary": (
                    f"Readiness verification passed for {len(contracts)}/{len(contracts)} contract(s)."
                    if failures == 0
                    else f"Readiness verification failed for {failures} of {len(contracts)} contract(s)."
                ),
            },
            "results": results,
        }
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        artifact_path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
        stdout.write(json.dumps(artifact, indent=2, sort_keys=True))
        stdout.write("\n")
        return 0 if failures == 0 else 1
    except Exception as exc:
        failure_classification = _classify_failure(exc)
        stderr.write(f"ERROR [{failure_classification}]: {exc}\n")
        return 2


if __name__ == "__main__":
    raise SystemExit(run_cli())
