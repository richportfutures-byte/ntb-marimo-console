#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal


SCRIPT_DIR = Path(__file__).resolve().parent
TARGET_ROOT = SCRIPT_DIR.parent
SRC_ROOT = TARGET_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ntb_marimo_console.contract_universe import (  # noqa: E402
    excluded_final_target_contracts,
    final_target_contracts,
)
from ntb_marimo_console.market_data.stream_manager import (  # noqa: E402
    MIN_STREAM_REFRESH_FLOOR_SECONDS,
)


SCHEMA_NAME = "five_contract_schwab_live_proof_capture"
SCHEMA_VERSION = 1
SERVICES = ("LEVELONE_FUTURES", "CHART_FUTURES")
PROOF_VERDICTS = ("PASS", "PARTIAL", "FAIL", "MANUAL_REQUIRED")
LIVE_REQUIRED_FLAGS = (
    "operator_attested_live",
    "one_connection_observed",
    "no_relogin_observed",
    "no_fixture_fallback_observed",
    "fail_closed_query_readiness_observed",
    "manual_only_execution_observed",
    "preserved_engine_authority_observed",
    "sensitive_output_reviewed",
)
FORBIDDEN_LABEL_FRAGMENTS = (
    "access_token",
    "refresh_token",
    "authorization",
    "bearer",
    "app_key",
    "app_secret",
    "client_secret",
    "credential",
    "customer_id",
    "customerid",
    "correl_id",
    "correlid",
    "account_id",
    "accountid",
    "account_number",
    "displayacctid",
    "streamer_socket_url",
    "streamer_url",
    "token_json",
    "raw_payload",
    "payload",
    "secret",
)
FORBIDDEN_VALUE_FRAGMENTS = (
    "authorization:",
    "bearer ",
    "access_token",
    "refresh_token",
    "app_key",
    "app_secret",
    "customerid",
    "correlid",
    "accountid",
    "displayacctid",
    "streamer-api",
)
SECRET_LIKE_PATTERN = re.compile(
    r"\b(?=[A-Za-z0-9._~+/=-]{24,}\b)(?=[A-Za-z0-9._~+/=-]*[0-9./+=~-])"
    r"[A-Za-z0-9._~+/=-]+\b"
)
URL_PATTERN = re.compile(r"(?i)\b(?:wss?|https?)://[^\s,}\"']+")

ProofVerdict = Literal["PASS", "PARTIAL", "FAIL", "MANUAL_REQUIRED"]
ProofStatus = Literal["observed", "blocked", "manual_required"]


class ArtifactSanitizationError(RuntimeError):
    pass


def build_fixture_artifact(*, generated_at: str | None = None) -> dict[str, object]:
    return _with_sensitive_scan(
        {
            "schema_name": SCHEMA_NAME,
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at or _utc_now(),
            "mode": "fixture",
            "operator_attested_live": False,
            "final_target_contracts": list(final_target_contracts()),
            "excluded_contracts": list(excluded_final_target_contracts()),
            "services": list(SERVICES),
            "refresh_floor_seconds": MIN_STREAM_REFRESH_FLOOR_SECONDS,
            "per_contract_proof_rows": _fixture_rows(),
            "one_connection_discipline_observation": {
                "status": "observed",
                "mode": "fixture",
                "login_count": 1,
                "subscription_count": 1,
            },
            "repeated_refresh_no_relogin_observation": {
                "status": "observed",
                "mode": "fixture",
                "refresh_reads": 3,
                "login_count": 1,
            },
            "no_fixture_fallback_after_live_failure_assertion": {
                "asserted": True,
                "status": "represented",
            },
            "fail_closed_query_readiness_assertion": {
                "asserted": True,
                "status": "represented",
            },
            "manual_only_execution_assertion": {
                "asserted": True,
                "status": "represented",
            },
            "preserved_engine_authority_assertion": {
                "asserted": True,
                "status": "represented",
            },
            "proof_verdict": "MANUAL_REQUIRED",
            "fixture_verification": "FIXTURE_PASS",
            "limitations": [
                "fixture_mode_is_not_real_live_proof",
                "operator_review_required_before_commit",
                "current_automated_harness_is_single_symbol_levelone_only",
                "chart_futures_live_observation_is_operator_attested",
            ],
        }
    )


def build_live_artifact(args: argparse.Namespace, *, generated_at: str | None = None) -> tuple[dict[str, object], tuple[str, ...]]:
    validation_errors = _live_validation_errors(args)
    levelone_rows = _live_rows(
        service="LEVELONE_FUTURES",
        observed_contracts=_parse_contracts(args.levelone_observed),
        blocked_contracts=_parse_contracts(args.levelone_blocked),
    )
    chart_rows = _live_rows(
        service="CHART_FUTURES",
        observed_contracts=_parse_contracts(args.chart_observed),
        blocked_contracts=_parse_contracts(args.chart_blocked),
    )
    rows = [*levelone_rows, *chart_rows]
    verdict = _proof_verdict(rows, validation_errors=validation_errors)
    artifact = _with_sensitive_scan(
        {
            "schema_name": SCHEMA_NAME,
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated_at or _utc_now(),
            "mode": "live",
            "operator_attested_live": bool(args.operator_attested_live and not validation_errors),
            "final_target_contracts": list(final_target_contracts()),
            "excluded_contracts": list(excluded_final_target_contracts()),
            "services": list(SERVICES),
            "refresh_floor_seconds": MIN_STREAM_REFRESH_FLOOR_SECONDS,
            "per_contract_proof_rows": rows,
            "one_connection_discipline_observation": _flag_observation(args.one_connection_observed),
            "repeated_refresh_no_relogin_observation": _flag_observation(args.no_relogin_observed),
            "no_fixture_fallback_after_live_failure_assertion": _flag_assertion(args.no_fixture_fallback_observed),
            "fail_closed_query_readiness_assertion": _flag_assertion(args.fail_closed_query_readiness_observed),
            "manual_only_execution_assertion": _flag_assertion(args.manual_only_execution_observed),
            "preserved_engine_authority_assertion": _flag_assertion(args.preserved_engine_authority_observed),
            "proof_verdict": verdict,
            "operator_input_gaps": list(validation_errors),
            "limitations": [
                "manual_operator_artifact",
                "operator_review_required_before_commit",
                "current_automated_harness_is_single_symbol_levelone_only",
                "chart_futures_live_observation_is_operator_attested",
            ],
        }
    )
    return artifact, validation_errors


def validate_artifact_safe(artifact: Mapping[str, object]) -> dict[str, object]:
    label_count, value_count = _scan_forbidden(artifact)
    if label_count or value_count:
        raise ArtifactSanitizationError("artifact_sanitizer_rejected_forbidden_content")
    return {
        "status": "pass",
        "passed": True,
        "sanitizer_version": 1,
        "scan_scope": "artifact_json",
        "forbidden_label_count": 0,
        "forbidden_value_count": 0,
    }


def render_artifact_json(artifact: Mapping[str, object]) -> str:
    validate_artifact_safe(artifact)
    return json.dumps(artifact, indent=2, sort_keys=True) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a sanitized five-contract Schwab proof artifact; fixture mode is the default."
    )
    parser.add_argument("--fixture", action="store_true", help="Create the deterministic fixture artifact.")
    parser.add_argument("--dry-run", action="store_true", help="Alias for fixture mode.")
    parser.add_argument("--live", action="store_true", help="Required for operator-attested live proof artifact mode.")
    parser.add_argument(
        "--operator-attested-live",
        action="store_true",
        help="Attest that observations came from an operator-approved live rehearsal window.",
    )
    parser.add_argument("--levelone-observed", default="", help="Comma-separated final target contracts observed for LEVELONE.")
    parser.add_argument("--levelone-blocked", default="", help="Comma-separated final target contracts blocked for LEVELONE.")
    parser.add_argument("--chart-observed", default="", help="Comma-separated final target contracts observed for CHART.")
    parser.add_argument("--chart-blocked", default="", help="Comma-separated final target contracts blocked for CHART.")
    parser.add_argument("--one-connection-observed", action="store_true", help="Attest one live connection was used.")
    parser.add_argument("--no-relogin-observed", action="store_true", help="Attest repeated refreshes did not relogin.")
    parser.add_argument(
        "--no-fixture-fallback-observed",
        action="store_true",
        help="Attest live failure remained blocked with no fixture fallback.",
    )
    parser.add_argument(
        "--fail-closed-query-readiness-observed",
        action="store_true",
        help="Attest query readiness remained fail-closed.",
    )
    parser.add_argument("--manual-only-execution-observed", action="store_true", help="Attest execution remained manual-only.")
    parser.add_argument(
        "--preserved-engine-authority-observed",
        action="store_true",
        help="Attest the preserved engine remained the only decision authority.",
    )
    parser.add_argument("--sensitive-output-reviewed", action="store_true", help="Attest the artifact was reviewed.")
    parser.add_argument("--output", type=Path, help="Optional destination for the sanitized JSON artifact.")
    return parser


def run(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(tuple(sys.argv[1:] if argv is None else argv))
    if args.live and (args.fixture or args.dry_run):
        artifact = _invalid_mode_artifact("choose_fixture_or_live_not_both")
        sys.stdout.write(render_artifact_json(artifact))
        return 1

    if args.live:
        artifact, validation_errors = build_live_artifact(args)
        sys.stdout.write(render_artifact_json(artifact))
        if validation_errors:
            return 2
        _write_output_if_requested(args.output, artifact)
        return 0 if artifact["proof_verdict"] == "PASS" else 1

    artifact = build_fixture_artifact()
    sys.stdout.write(render_artifact_json(artifact))
    _write_output_if_requested(args.output, artifact)
    return 0


def _fixture_rows() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for service in SERVICES:
        for contract in final_target_contracts():
            rows.append(
                {
                    "contract": contract,
                    "service": service,
                    "status": "observed",
                    "observed": True,
                    "blocked": False,
                    "source": "fixture_mock",
                    "raw_data_recorded": False,
                    "blocking_reasons": [],
                }
            )
    return rows


def _live_rows(
    *,
    service: str,
    observed_contracts: tuple[str, ...],
    blocked_contracts: tuple[str, ...],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    observed = set(observed_contracts)
    blocked = set(blocked_contracts)
    for contract in final_target_contracts():
        status: ProofStatus = "manual_required"
        if contract in observed:
            status = "observed"
        elif contract in blocked:
            status = "blocked"
        rows.append(
            {
                "contract": contract,
                "service": service,
                "status": status,
                "observed": status == "observed",
                "blocked": status == "blocked",
                "source": "operator_attestation",
                "raw_data_recorded": False,
                "blocking_reasons": [] if status != "blocked" else ["operator_reported_blocked"],
            }
        )
    return rows


def _live_validation_errors(args: argparse.Namespace) -> tuple[str, ...]:
    errors: list[str] = []
    for flag_name in LIVE_REQUIRED_FLAGS:
        if not bool(getattr(args, flag_name)):
            errors.append(f"{flag_name}_required")
    errors.extend(_service_contract_errors("levelone", args.levelone_observed, args.levelone_blocked))
    errors.extend(_service_contract_errors("chart", args.chart_observed, args.chart_blocked))
    return tuple(errors)


def _service_contract_errors(service_name: str, observed_value: str, blocked_value: str) -> tuple[str, ...]:
    errors: list[str] = []
    final_contracts = set(final_target_contracts())
    observed = set(_parse_contracts(observed_value))
    blocked = set(_parse_contracts(blocked_value))
    unsupported = sorted((observed | blocked) - final_contracts)
    overlap = sorted(observed & blocked)
    missing = sorted(final_contracts - observed - blocked)
    if unsupported:
        errors.append(f"{service_name}_unsupported_contracts:{','.join(unsupported)}")
    if overlap:
        errors.append(f"{service_name}_observed_and_blocked_overlap:{','.join(overlap)}")
    if missing:
        errors.append(f"{service_name}_missing_contracts:{','.join(missing)}")
    return tuple(errors)


def _parse_contracts(value: str) -> tuple[str, ...]:
    return tuple(
        item.strip().upper()
        for item in value.split(",")
        if item.strip()
    )


def _flag_observation(observed: bool) -> dict[str, object]:
    return {
        "status": "observed" if observed else "manual_required",
        "observed": bool(observed),
    }


def _flag_assertion(asserted: bool) -> dict[str, object]:
    return {
        "status": "asserted" if asserted else "manual_required",
        "asserted": bool(asserted),
    }


def _proof_verdict(rows: Sequence[Mapping[str, object]], *, validation_errors: tuple[str, ...]) -> ProofVerdict:
    if validation_errors:
        return "MANUAL_REQUIRED"
    observed_count = sum(1 for row in rows if row.get("status") == "observed")
    blocked_count = sum(1 for row in rows if row.get("status") == "blocked")
    if observed_count == len(rows):
        return "PASS"
    if observed_count and blocked_count:
        return "PARTIAL"
    return "FAIL"


def _invalid_mode_artifact(reason: str) -> dict[str, object]:
    return _with_sensitive_scan(
        {
            "schema_name": SCHEMA_NAME,
            "schema_version": SCHEMA_VERSION,
            "generated_at": _utc_now(),
            "mode": "invalid",
            "operator_attested_live": False,
            "final_target_contracts": list(final_target_contracts()),
            "excluded_contracts": list(excluded_final_target_contracts()),
            "services": list(SERVICES),
            "per_contract_proof_rows": [],
            "proof_verdict": "MANUAL_REQUIRED",
            "operator_input_gaps": [reason],
            "limitations": ["choose_one_mode"],
        }
    )


def _with_sensitive_scan(artifact: dict[str, object]) -> dict[str, object]:
    artifact = dict(artifact)
    artifact["sensitive_output_scan"] = validate_artifact_safe(artifact)
    validate_artifact_safe(artifact)
    return artifact


def _scan_forbidden(value: object) -> tuple[int, int]:
    label_count = 0
    value_count = 0
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_text = str(key).lower()
            if any(fragment in key_text for fragment in FORBIDDEN_LABEL_FRAGMENTS):
                label_count += 1
            child_label_count, child_value_count = _scan_forbidden(item)
            label_count += child_label_count
            value_count += child_value_count
    elif isinstance(value, (list, tuple)):
        for item in value:
            child_label_count, child_value_count = _scan_forbidden(item)
            label_count += child_label_count
            value_count += child_value_count
    elif isinstance(value, str):
        lower = value.lower()
        if (
            any(fragment in lower for fragment in FORBIDDEN_VALUE_FRAGMENTS)
            or URL_PATTERN.search(value)
            or SECRET_LIKE_PATTERN.search(value)
        ):
            value_count += 1
    return label_count, value_count


def _write_output_if_requested(path: Path | None, artifact: Mapping[str, object]) -> None:
    if path is None:
        return
    rendered = render_artifact_json(artifact)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    raise SystemExit(run())
