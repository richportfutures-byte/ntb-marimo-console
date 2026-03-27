from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Mapping
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .audit import AuditError, append_audit_record, utc_now_iso
from .config import (
    DEFAULT_GEMINI_MODEL,
    ConfigError,
    GeminiStartupConfig,
    load_gemini_startup_config,
)
from .gemini_adapter import GeminiAdapterError, GeminiResponsesAdapter, genai
from .pipeline import PipelineExecutionResult, run_pipeline
from .schemas.packet import HistoricalPacket
from .validation import validate_historical_packet

SUPPORTED_CONTRACTS = ("ES", "NQ", "CL", "ZN", "6E", "MGC")
ClientFactory = Callable[[GeminiStartupConfig], Any]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m ninjatradebuilder.cli",
        description="Run the validated NinjaTradeBuilder pipeline on one packet file.",
    )
    parser.add_argument(
        "--packet",
        required=True,
        help="Path to a historical_packet_v1 JSON file, or a contract bundle like tests/fixtures/packets.valid.json.",
    )
    parser.add_argument(
        "--contract",
        choices=SUPPORTED_CONTRACTS,
        help="Required only when --packet points to a multi-contract bundle.",
    )
    parser.add_argument(
        "--evaluation-timestamp",
        help="Optional override for the evaluation timestamp. Defaults to market_packet.timestamp.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_GEMINI_MODEL,
        help=f"Gemini model identifier. Defaults to {DEFAULT_GEMINI_MODEL}.",
    )
    parser.add_argument(
        "--audit-log",
        help="Optional path to append one structured JSON audit record per CLI run.",
    )
    return parser


def _load_json(path: Path) -> Any:
    if not path.is_file():
        raise ValueError(f"Packet file does not exist: {path}")
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ValueError(f"Packet file did not contain valid JSON: {path}") from exc


def _extract_bundle_packet(bundle: Mapping[str, Any], contract: str) -> dict[str, Any]:
    if contract not in bundle.get("contracts", {}):
        raise ValueError(f"Bundle packet does not contain contract {contract}.")

    return {
        "$schema": "historical_packet_v1",
        "challenge_state": bundle["shared"]["challenge_state"],
        "attached_visuals": bundle["shared"]["attached_visuals"],
        "contract_metadata": bundle["contracts"][contract]["contract_metadata"],
        "market_packet": bundle["contracts"][contract]["market_packet"],
        "contract_specific_extension": bundle["contracts"][contract]["contract_specific_extension"],
    }


def load_packet_input(path: Path, *, contract: str | None) -> HistoricalPacket:
    payload = _load_json(path)
    if not isinstance(payload, Mapping):
        raise ValueError("Packet file must decode to a JSON object.")

    if payload.get("$schema") == "historical_packet_v1":
        return validate_historical_packet(payload)

    if "shared" in payload and "contracts" in payload:
        if not contract:
            raise ValueError("Bundle packet files require --contract.")
        return validate_historical_packet(_extract_bundle_packet(payload, contract))

    raise ValueError(
        "Packet file must be a historical_packet_v1 object or a supported multi-contract bundle."
    )


def _normalize_for_json(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True)
    if is_dataclass(value):
        return {key: _normalize_for_json(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {key: _normalize_for_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_for_json(item) for item in value]
    if isinstance(value, tuple):
        return [_normalize_for_json(item) for item in value]
    return value


def serialize_pipeline_result(result: PipelineExecutionResult) -> dict[str, Any]:
    return _normalize_for_json(result)


def _classify_failure(exc: Exception) -> str:
    if isinstance(exc, ConfigError):
        return "config_error"
    if isinstance(exc, GeminiAdapterError):
        return "provider_error"
    if isinstance(exc, ImportError):
        return "dependency_error"
    if isinstance(exc, ValueError):
        return "input_error"
    return "unexpected_error"


def _build_audit_record(
    *,
    started_at: str,
    finished_at: str,
    packet_path: str,
    requested_contract: str | None,
    evaluation_timestamp: str | None,
    config: GeminiStartupConfig | None,
    result: PipelineExecutionResult | None,
    error: Exception | None,
) -> dict[str, Any]:
    return {
        "audit_schema": "operator_cli_run_v1",
        "started_at": started_at,
        "finished_at": finished_at,
        "provider": "gemini",
        "packet_path": packet_path,
        "requested_contract": requested_contract,
        "contract": result.contract if result is not None else requested_contract,
        "evaluation_timestamp": evaluation_timestamp,
        "model": config.model if config is not None else None,
        "timeout_seconds": config.timeout_seconds if config is not None else None,
        "max_retries": config.max_retries if config is not None else None,
        "retry_initial_delay_seconds": (
            config.retry_initial_delay_seconds if config is not None else None
        ),
        "retry_max_delay_seconds": config.retry_max_delay_seconds if config is not None else None,
        "success": error is None,
        "status": "success" if error is None else "failure",
        "termination_stage": result.termination_stage if result is not None else None,
        "final_decision": result.final_decision if result is not None else None,
        "error_category": _classify_failure(error) if error is not None else None,
        "error_type": error.__class__.__name__ if error is not None else None,
        "error_message": str(error) if error is not None else None,
    }


def _build_client(config: GeminiStartupConfig, client_factory: ClientFactory | None) -> Any:
    if client_factory is not None:
        return client_factory(config)
    if genai is None:
        raise ImportError("google-genai SDK is required for Gemini CLI execution.")
    return genai.Client(
        api_key=config.api_key,
        http_options=GeminiResponsesAdapter._build_http_options(config),
    )


def run_cli(
    argv: list[str] | None = None,
    *,
    stdout: Any = None,
    stderr: Any = None,
    client_factory: ClientFactory | None = None,
) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    parser = build_parser()
    args = parser.parse_args(argv)
    started_at = utc_now_iso()
    config: GeminiStartupConfig | None = None
    result: PipelineExecutionResult | None = None
    error: Exception | None = None
    evaluation_timestamp: str | None = None

    try:
        config = load_gemini_startup_config(model=args.model)
        packet = load_packet_input(Path(args.packet), contract=args.contract)
        evaluation_timestamp = (
            args.evaluation_timestamp
            or packet.market_packet.timestamp.isoformat().replace("+00:00", "Z")
        )
        adapter = GeminiResponsesAdapter(
            client=_build_client(config, client_factory),
            model=config.model,
            timeout_seconds=config.timeout_seconds,
            max_retries=config.max_retries,
        )
        result = run_pipeline(
            packet=packet,
            evaluation_timestamp_iso=evaluation_timestamp,
            model_adapter=adapter,
        )
    except (ConfigError, GeminiAdapterError, ImportError, ValueError) as exc:
        error = exc

    if args.audit_log:
        audit_record = _build_audit_record(
            started_at=started_at,
            finished_at=utc_now_iso(),
            packet_path=str(Path(args.packet)),
            requested_contract=args.contract,
            evaluation_timestamp=evaluation_timestamp,
            config=config,
            result=result,
            error=error,
        )
        try:
            append_audit_record(Path(args.audit_log), audit_record)
        except AuditError as exc:
            stderr.write(f"ERROR: {exc}\n")
            return 2

    if error is not None:
        stderr.write(f"ERROR: {error}\n")
        return 2

    stdout.write(json.dumps(serialize_pipeline_result(result), indent=2, sort_keys=True))
    stdout.write("\n")
    return 0


def main() -> int:
    return run_cli()


if __name__ == "__main__":
    raise SystemExit(main())
