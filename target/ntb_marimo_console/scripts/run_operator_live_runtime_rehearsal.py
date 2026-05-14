#!/usr/bin/env python3
"""Explicit operator live runtime rehearsal harness (R30).

This script wires the R29 :class:`OperatorSchwabStreamerSession` adapter
behind R28's stream-client factory and R27's operator launcher into a
runnable manual rehearsal command.

The harness is **explicit-live only** and inert at import time. It performs
no env reads, file opens, network calls, websocket imports, or runtime
starts at import. Every Schwab interaction requires both ``--live`` and
``NTB_OPERATOR_RUNTIME_MODE=OPERATOR_LIVE_RUNTIME``. Output is sanitized to
boolean/status keys only — no Schwab-sensitive value (token, URL, customer
id, correl id, account id, auth header) ever appears in stdout, stderr,
or the JSON payload.

This script does NOT open ``.state/secrets/schwab_live.env`` itself. The
operator is expected to source that file in their shell before invoking
this command.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Mapping, Sequence

from ntb_marimo_console.contract_universe import (
    final_target_contracts,
    is_excluded_final_target_contract,
    is_final_target_contract,
    is_never_supported_contract,
    normalize_contract_symbol,
)
from ntb_marimo_console.market_data import ChartFuturesBarBuilder
from ntb_marimo_console.market_data.stream_manager import (
    MIN_STREAM_REFRESH_FLOOR_SECONDS,
    SchwabStreamManagerConfig,
    StreamManagerSnapshot,
)
from ntb_marimo_console.market_data.stream_events import redact_sensitive_text
from ntb_marimo_console.operator_live_launcher import (
    OperatorLiveLaunchResult,
    OperatorLiveRuntimeFactoryError,
    OperatorLiveRuntimeOptInRequired,
    OperatorLiveRuntimeStartError,
    start_operator_live_runtime,
    stop_operator_live_runtime,
)
from ntb_marimo_console.operator_live_runtime import (
    OPERATOR_LIVE_RUNTIME,
)
from ntb_marimo_console.schwab_stream_client import (
    build_operator_schwab_stream_client_factory,
)
from ntb_marimo_console.schwab_reconnect import (
    SchwabReconnectController,
    should_attempt_reconnect,
)
from ntb_marimo_console.schwab_streamer_session import (
    DEFAULT_LEVELONE_FUTURES_FIELD_IDS,
    OperatorSchwabStreamerSession,
    OperatorSchwabStreamerSessionError,
    SchwabAccessTokenProvider,
    SchwabStreamerCredentialsProvider,
    SchwabWebsocketFactory,
    StreamerCredentials,
    build_operator_schwab_streamer_session_factory,
    default_schwab_websocket_factory,
)
from ntb_marimo_console.schwab_token_lifecycle import (
    DEFAULT_TOKEN_URL,
    RefreshableAccessTokenProvider,
    TokenContractReport,
    validate_token_contract,
)


_THIS_DIR = Path(__file__).resolve().parent
_TARGET_ROOT = _THIS_DIR.parent


def _load_sibling_module(name: str):
    spec = importlib.util.spec_from_file_location(name, _THIS_DIR / f"{name}.py")
    if spec is None or spec.loader is None:
        raise ImportError(f"could not load sibling script module: {name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(name, module)
    spec.loader.exec_module(module)
    return module


# Sibling scripts. Loading this is import-time inert (only stdlib imports
# at module top). Its network/file work happens only when its functions are
# called.
levelone_probe = _load_sibling_module("probe_schwab_levelone_futures")


REQUIRED_ENV_KEYS: tuple[str, ...] = (
    "SCHWAB_APP_KEY",
    "SCHWAB_APP_SECRET",
    "SCHWAB_TOKEN_PATH",
)
DEFAULT_DURATION_SECONDS = 10
MIN_DURATION_SECONDS = 1
MAX_DURATION_SECONDS = 30
MAX_IDLE_DISPATCH_SLEEP_SECONDS = 0.05
DEFAULT_FRONT_MONTH_SYMBOLS: dict[str, str] = {
    "ES": "/ESM26",
    "NQ": "/NQM26",
    "CL": "/CLM26",
    "6E": "/6EM26",
    "MGC": "/MGCM26",
}
DRY_RUN_SERVICES: tuple[str, ...] = ("LEVELONE_FUTURES", "CHART_FUTURES")
CONTRACT_DISPLAY_NAMES: dict[str, str] = {
    "ES": "E-mini S&P 500",
    "NQ": "E-mini Nasdaq-100",
    "CL": "Crude Oil",
    "6E": "Euro FX",
    "MGC": "Micro Gold",
}


_FORBIDDEN_FRAGMENT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"streamer-api"),
    re.compile(r"wss?://", re.IGNORECASE),
    re.compile(r"https?://", re.IGNORECASE),
    re.compile(r"(?i)bearer\s+\S+"),
    re.compile(r"(?i)access[_-]?token"),
    re.compile(r"(?i)refresh[_-]?token"),
    re.compile(r"(?i)customer[_-]?id"),
    re.compile(r"(?i)correl[_-]?id"),
    re.compile(r"(?i)account[_-]?(id|number)"),
    re.compile(r"\.state/secrets"),
    re.compile(r"schwab_live\.env"),
    re.compile(r"token\.json"),
)
_GATE_SAFE_TEXT_FIELDS: frozenset[str] = frozenset(
    {
        "credential_free_gate_command",
        "intentional_live_command",
        "production_readiness_blockers",
    }
)


# ---------------------------------------------------------------------------
# Report types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RehearsalCheck:
    name: str
    status: str  # "ok" | "blocked" | "info" | "error"
    detail: str = ""


@dataclass(frozen=True)
class DryRunContractPlan:
    contract: str
    display_name: str
    symbol: str
    services: tuple[str, ...]
    final_target_supported: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "display_name": self.display_name,
            "symbol": self.symbol,
            "services": list(self.services),
            "final_target_supported": _yes_no(self.final_target_supported),
        }


@dataclass(frozen=True)
class DryRunRejectedContract:
    contract: str
    policy: str
    included_in_final_plan: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "policy": self.policy,
            "included_in_final_plan": _yes_no(self.included_in_final_plan),
        }


@dataclass(frozen=True)
class RehearsalDryRunReport:
    mode: str
    status: str
    readiness_gate: str
    rehearsal_ready_to_run: bool
    live_behavior_attempted: bool
    runtime_start_attempted: bool
    login_attempted: bool
    subscribe_attempted: bool
    provider_connection_attempted: bool
    explicit_live_opt_in_required: bool
    operator_runtime_mode_required: str
    secrets_or_token_files_read: bool
    credentials_required_for_dry_run: bool
    services: tuple[str, ...]
    contract_plan: tuple[DryRunContractPlan, ...]
    rejected_contracts: tuple[DryRunRejectedContract, ...]
    provider_diagnostics: tuple[str, ...]
    refresh_floor_seconds: float
    credential_free_gate_command: str
    intentional_live_command: str
    production_readiness_blockers: tuple[str, ...]
    limitations: tuple[str, ...]
    values_printed: str = "no"

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "status": self.status,
            "readiness_gate": self.readiness_gate,
            "rehearsal_ready_to_run": _yes_no(self.rehearsal_ready_to_run),
            "live_behavior_attempted": _yes_no(self.live_behavior_attempted),
            "runtime_start_attempted": _yes_no(self.runtime_start_attempted),
            "login_attempted": _yes_no(self.login_attempted),
            "subscribe_attempted": _yes_no(self.subscribe_attempted),
            "provider_connection_attempted": _yes_no(self.provider_connection_attempted),
            "explicit_live_opt_in_required": _yes_no(self.explicit_live_opt_in_required),
            "operator_runtime_mode_required": self.operator_runtime_mode_required,
            "secrets_or_token_files_read": _yes_no(self.secrets_or_token_files_read),
            "credentials_required_for_dry_run": _yes_no(self.credentials_required_for_dry_run),
            "services": list(self.services),
            "contract_plan": [item.to_dict() for item in self.contract_plan],
            "rejected_contracts": [item.to_dict() for item in self.rejected_contracts],
            "provider_diagnostics": list(self.provider_diagnostics),
            "refresh_floor_seconds": self.refresh_floor_seconds,
            "credential_free_gate_command": self.credential_free_gate_command,
            "intentional_live_command": self.intentional_live_command,
            "production_readiness_blockers": list(self.production_readiness_blockers),
            "limitations": list(self.limitations),
            "values_printed": self.values_printed,
        }


@dataclass(frozen=True)
class RehearsalReadinessAssessment:
    classification: str
    login_subscription_plumbing_proven: bool
    market_data_delivery_proven: bool
    production_live_ready: bool
    query_ready_allowed: bool
    blocking_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "classification": self.classification,
            "login_subscription_plumbing_proven": _yes_no(self.login_subscription_plumbing_proven),
            "market_data_delivery_proven": _yes_no(self.market_data_delivery_proven),
            "production_live_ready": _yes_no(self.production_live_ready),
            "query_ready_allowed": _yes_no(self.query_ready_allowed),
            "blocking_reasons": list(self.blocking_reasons),
        }


@dataclass
class RehearsalReport:
    mode: str = "blocked"  # "live" | "blocked" | "error"
    status: str = "blocked"
    repo_check: bool = False
    live_flag: bool = False
    operator_live_runtime_env: bool = False
    env_keys_present: bool = False
    token_path_under_target_state: bool = False
    token_file_present: bool = False
    token_file_parseable: bool = False
    token_contract_valid: bool = False
    access_token_present: bool = False
    refresh_token_present: bool = False
    token_fresh: str = "unknown"  # "yes" | "no" | "unknown"
    streamer_credentials_obtained: bool = False
    runtime_start_attempted: bool = False
    live_login_succeeded: bool = False
    live_subscribe_succeeded: bool = False
    subscribed_contracts_count: int = 0
    market_data_received: bool = False
    received_contracts_count: int = 0
    market_data_diagnostic: str = "not_evaluated"
    chart_data_received: bool = False
    chart_received_contracts_count: int = 0
    chart_completed_five_minute_contracts_count: int = 0
    chart_data_diagnostic: str = "not_evaluated"
    per_contract_status: dict[str, dict[str, str]] = field(default_factory=dict)
    repeated_login_on_refresh: bool = False
    cleanup_status: str = "skipped"  # "ok" | "skipped" | "error"
    duration_seconds: float = 0.0
    blocking_reason: str = ""
    checks: list[RehearsalCheck] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "status": self.status,
            "repo_check": _yes_no(self.repo_check),
            "live_flag": _yes_no(self.live_flag),
            "operator_live_runtime_env": _yes_no(self.operator_live_runtime_env),
            "env_keys_present": _yes_no(self.env_keys_present),
            "token_path_under_target_state": _yes_no(self.token_path_under_target_state),
            "token_file_present": _yes_no(self.token_file_present),
            "token_file_parseable": _yes_no(self.token_file_parseable),
            "token_contract_valid": _yes_no(self.token_contract_valid),
            "access_token_present": _yes_no(self.access_token_present),
            "refresh_token_present": _yes_no(self.refresh_token_present),
            "token_fresh": self.token_fresh,
            "streamer_credentials_obtained": _yes_no(self.streamer_credentials_obtained),
            "runtime_start_attempted": _yes_no(self.runtime_start_attempted),
            "live_login_succeeded": _yes_no(self.live_login_succeeded),
            "live_subscribe_succeeded": _yes_no(self.live_subscribe_succeeded),
            "subscribed_contracts_count": int(self.subscribed_contracts_count),
            "market_data_received": _yes_no(self.market_data_received),
            "received_contracts_count": int(self.received_contracts_count),
            "market_data_diagnostic": self.market_data_diagnostic,
            "chart_data_received": _yes_no(self.chart_data_received),
            "chart_received_contracts_count": int(self.chart_received_contracts_count),
            "chart_completed_five_minute_contracts_count": int(self.chart_completed_five_minute_contracts_count),
            "chart_data_diagnostic": self.chart_data_diagnostic,
            "per_contract_status": self.per_contract_status,
            "repeated_login_on_refresh": "no",
            "cleanup_status": self.cleanup_status,
            "duration_seconds": float(self.duration_seconds),
            "blocking_reason": self.blocking_reason,
            "values_printed": "no",
            "checks": [
                {"name": check.name, "status": check.status, "detail": check.detail}
                for check in self.checks
            ],
        }


@dataclass(frozen=True)
class ReceiveLoopObservation:
    market_data_received: bool
    received_contracts_count: int
    chart_data_received: bool = False
    chart_received_contracts_count: int = 0
    chart_completed_five_minute_contracts_count: int = 0
    chart_blocking_reasons: tuple[str, ...] = ()
    quote_contracts: tuple[str, ...] = ()
    chart_contracts: tuple[str, ...] = ()
    chart_completed_contracts: tuple[str, ...] = ()

    def __iter__(self):
        yield self.market_data_received
        yield self.received_contracts_count


def assess_rehearsal_readiness(report: RehearsalReport) -> RehearsalReadinessAssessment:
    plumbing_proven = (
        report.mode == "live"
        and report.status == "ok"
        and report.live_flag
        and report.operator_live_runtime_env
        and report.streamer_credentials_obtained
        and report.runtime_start_attempted
        and report.live_login_succeeded
        and report.live_subscribe_succeeded
        and report.subscribed_contracts_count == len(final_target_contracts())
        and report.cleanup_status == "ok"
        and not report.repeated_login_on_refresh
    )
    levelone_data_proven = (
        plumbing_proven
        and report.market_data_received
        and report.received_contracts_count == len(final_target_contracts())
    )
    chart_data_proven = (
        plumbing_proven
        and report.chart_data_received
        and report.chart_completed_five_minute_contracts_count == len(final_target_contracts())
    )
    if levelone_data_proven and chart_data_proven:
        classification = "live_levelone_and_chart_market_data_delivery_proven"
        blocking_reasons = (
            "full_live_session_marimo_usability_not_proven",
            "production_readiness_requires_non_levelone_predicates",
            "rehearsal_result_is_review_only_not_query_authority",
        )
    elif levelone_data_proven:
        classification = "live_levelone_market_data_delivery_proven"
        blocking_reasons: tuple[str, ...] = (
            "chart_futures_delivery_not_proven",
            "full_live_session_marimo_usability_not_proven",
            "production_readiness_requires_non_levelone_predicates",
            "rehearsal_result_is_review_only_not_query_authority",
        )
    elif plumbing_proven:
        classification = "partial_live_login_and_subscription_only"
        blocking_reasons = (
            "market_data_delivery_not_proven",
            "rehearsal_result_is_review_only_not_query_authority",
        )
    else:
        classification = "blocked_live_rehearsal"
        blocking_reasons = (
            "live_login_subscription_not_proven",
            "rehearsal_result_is_review_only_not_query_authority",
        )
    return RehearsalReadinessAssessment(
        classification=classification,
        login_subscription_plumbing_proven=plumbing_proven,
        market_data_delivery_proven=levelone_data_proven,
        production_live_ready=False,
        query_ready_allowed=False,
        blocking_reasons=blocking_reasons,
    )


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


# ---------------------------------------------------------------------------
# Sanitization
# ---------------------------------------------------------------------------


def _sanitize_text(value: str) -> str:
    sanitized = redact_sensitive_text(value)
    for pattern in _FORBIDDEN_FRAGMENT_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized


def _sanitize_gate_safe_text(value: str) -> str:
    sanitized = str(value)
    for pattern in _FORBIDDEN_FRAGMENT_PATTERNS:
        sanitized = pattern.sub("[REDACTED]", sanitized)
    return sanitized[:300]


def _sanitize_payload(payload: object, *, field_name: str | None = None) -> object:
    if isinstance(payload, dict):
        return {key: _sanitize_payload(item, field_name=str(key)) for key, item in payload.items()}
    if isinstance(payload, list):
        return [_sanitize_payload(item, field_name=field_name) for item in payload]
    if isinstance(payload, tuple):
        return tuple(_sanitize_payload(item, field_name=field_name) for item in payload)
    if isinstance(payload, str):
        if field_name in _GATE_SAFE_TEXT_FIELDS:
            return _sanitize_gate_safe_text(payload)
        return _sanitize_text(payload)
    return payload


def render_text(report: RehearsalReport) -> str:
    payload = _sanitize_payload(report.to_dict())
    assert isinstance(payload, dict)
    keys_in_order = (
        "mode",
        "status",
        "repo_check",
        "live_flag",
        "operator_live_runtime_env",
        "env_keys_present",
        "token_path_under_target_state",
        "token_file_present",
        "token_file_parseable",
        "token_contract_valid",
        "access_token_present",
        "refresh_token_present",
        "token_fresh",
        "streamer_credentials_obtained",
        "runtime_start_attempted",
        "live_login_succeeded",
        "live_subscribe_succeeded",
        "subscribed_contracts_count",
        "market_data_received",
        "received_contracts_count",
        "market_data_diagnostic",
        "chart_data_received",
        "chart_received_contracts_count",
        "chart_completed_five_minute_contracts_count",
        "chart_data_diagnostic",
        "repeated_login_on_refresh",
        "cleanup_status",
        "duration_seconds",
        "values_printed",
    )
    body = "\n".join(f"{key}={payload[key]}" for key in keys_in_order)
    if report.blocking_reason:
        body += f"\nblocking_reason={payload['blocking_reason']}"
    return body


def render_json(report: RehearsalReport) -> str:
    payload = _sanitize_payload(report.to_dict())
    return json.dumps(payload, sort_keys=True)


def render_dry_run_json(report: RehearsalDryRunReport) -> str:
    payload = _sanitize_payload(report.to_dict())
    return json.dumps(payload, sort_keys=True)


def render_dry_run_text(report: RehearsalDryRunReport) -> str:
    payload = _sanitize_payload(report.to_dict())
    assert isinstance(payload, dict)
    lines = [
        f"mode={payload['mode']}",
        f"status={payload['status']}",
        f"readiness_gate={payload['readiness_gate']}",
        f"rehearsal_ready_to_run={payload['rehearsal_ready_to_run']}",
        f"live_behavior_attempted={payload['live_behavior_attempted']}",
        f"runtime_start_attempted={payload['runtime_start_attempted']}",
        f"login_attempted={payload['login_attempted']}",
        f"subscribe_attempted={payload['subscribe_attempted']}",
        f"provider_connection_attempted={payload['provider_connection_attempted']}",
        f"explicit_live_opt_in_required={payload['explicit_live_opt_in_required']}",
        f"operator_runtime_mode_required={payload['operator_runtime_mode_required']}",
        f"secrets_or_token_files_read={payload['secrets_or_token_files_read']}",
        f"credentials_required_for_dry_run={payload['credentials_required_for_dry_run']}",
        "services=" + ",".join(str(item) for item in payload["services"]),
        f"refresh_floor_seconds={payload['refresh_floor_seconds']}",
        f"credential_free_gate_command={payload['credential_free_gate_command']}",
        f"intentional_live_command={payload['intentional_live_command']}",
        f"values_printed={payload['values_printed']}",
    ]
    for item in payload["contract_plan"]:
        assert isinstance(item, dict)
        lines.append(
            "plan_contract="
            f"{item['contract']}|{item['display_name']}|{item['symbol']}|"
            + ",".join(str(service) for service in item["services"])
        )
    for item in payload["rejected_contracts"]:
        assert isinstance(item, dict)
        lines.append(
            f"rejected_contract={item['contract']}|{item['policy']}|included={item['included_in_final_plan']}"
        )
    for diagnostic in payload["provider_diagnostics"]:
        lines.append(f"provider_diagnostic={diagnostic}")
    for blocker in payload["production_readiness_blockers"]:
        lines.append(f"production_readiness_blocker={blocker}")
    for limitation in payload["limitations"]:
        lines.append(f"limitation={limitation}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class _SymbolOverrideAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        existing: dict[str, str] = getattr(namespace, self.dest, None) or {}
        if isinstance(values, str):
            values_list = [values]
        else:
            values_list = list(values or ())
        for entry in values_list:
            if "=" not in entry:
                parser.error("--symbol must be of the form ROOT=KEY (e.g. ES=/ESM26)")
            root, _, key = entry.partition("=")
            root_normalized = normalize_contract_symbol(root)
            if is_never_supported_contract(root_normalized):
                parser.error(f"--symbol root rejected (never_supported): {root_normalized}")
            if is_excluded_final_target_contract(root_normalized):
                parser.error(f"--symbol root rejected (excluded): {root_normalized}")
            if not is_final_target_contract(root_normalized):
                parser.error(f"--symbol root must be a final target contract: {root_normalized}")
            existing[root_normalized] = key.strip()
        setattr(namespace, self.dest, existing)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="run_operator_live_runtime_rehearsal",
        description=(
            "Explicit live only: drive a real Schwab login, LEVELONE_FUTURES "
            "subscription, bounded receive loop, and clean shutdown through "
            "the operator runtime path. Prints sanitized status keys only; "
            "no Schwab-sensitive values are emitted. Requires --live and "
            "NTB_OPERATOR_RUNTIME_MODE=OPERATOR_LIVE_RUNTIME."
        ),
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Required for any live behavior. Without --live the command exits without touching env, tokens, or network.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Render the deterministic five-contract live rehearsal plan without reading env, opening files, logging in, or subscribing.",
    )
    parser.add_argument(
        "--readiness-gate",
        action="store_true",
        help="Alias for --dry-run; render the credential-free five-contract live rehearsal readiness gate.",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=DEFAULT_DURATION_SECONDS,
        help="Bounded receive-loop duration in seconds (clamped to [%(min)d, %(max)d])." % {
            "min": MIN_DURATION_SECONDS,
            "max": MAX_DURATION_SECONDS,
        },
    )
    parser.add_argument(
        "--symbol",
        action=_SymbolOverrideAction,
        default={},
        metavar="ROOT=KEY",
        help="Override an active front-month symbol for one final target contract (e.g. ES=/ESH26). May be repeated. ZN and GC are rejected.",
    )
    parser.add_argument(
        "--dry-run-contract",
        action="append",
        default=[],
        metavar="ROOT",
        help="Dry-run-only candidate contract to classify if it appears in future rehearsal config. Does not add it to the final plan.",
    )
    parser.add_argument(
        "--provider-diagnostic",
        action="append",
        default=[],
        help="Dry-run-only provider diagnostic text to sanitize before rendering. No live provider call is made.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Render sanitized JSON instead of key=value lines.",
    )
    return parser


# ---------------------------------------------------------------------------
# Default front-month symbol resolution (calendar-dependent default).
# ---------------------------------------------------------------------------


def default_front_month_symbols() -> dict[str, str]:
    """Return the default contract->Schwab-key map for the active front month.

    The default is calendar-dependent. Operators must override at roll dates
    via ``--symbol ROOT=KEY``. ZN and GC are explicitly excluded.
    """

    return dict(DEFAULT_FRONT_MONTH_SYMBOLS)


def resolve_symbol_map(overrides: Mapping[str, str] | None) -> dict[str, str]:
    base = default_front_month_symbols()
    if overrides:
        for root, key in overrides.items():
            normalized = normalize_contract_symbol(root)
            if is_never_supported_contract(normalized) or is_excluded_final_target_contract(normalized):
                continue
            if not is_final_target_contract(normalized):
                continue
            base[normalized] = key
    return base


def _build_stream_config(
    *,
    symbol_overrides: Mapping[str, str] | None,
) -> SchwabStreamManagerConfig:
    contracts = final_target_contracts()
    symbol_map = resolve_symbol_map(symbol_overrides)
    symbols = tuple(symbol_map[contract] for contract in contracts)
    return SchwabStreamManagerConfig(
        provider="schwab",
        services_requested=("LEVELONE_FUTURES", "CHART_FUTURES"),
        symbols_requested=symbols,
        fields_requested=DEFAULT_LEVELONE_FUTURES_FIELD_IDS,
        explicit_live_opt_in=True,
        contracts_requested=contracts,
    )


def build_dry_run_report(
    *,
    symbol_overrides: Mapping[str, str] | None = None,
    candidate_contracts: Sequence[str] = (),
    provider_diagnostics: Sequence[str] = (),
) -> RehearsalDryRunReport:
    symbol_map = resolve_symbol_map(symbol_overrides)
    plan = tuple(
        DryRunContractPlan(
            contract=contract,
            display_name=CONTRACT_DISPLAY_NAMES[contract],
            symbol=symbol_map[contract],
            services=DRY_RUN_SERVICES,
        )
        for contract in final_target_contracts()
    )
    rejected = tuple(_rejected_contracts(candidate_contracts))
    safe_diagnostics = tuple(
        _sanitize_text(item).strip()
        for item in provider_diagnostics
        if str(item).strip()
    )
    diagnostics = safe_diagnostics or (
        "provider_status_not_checked",
        "live_delivery_unproven_until_manual_rehearsal",
    )
    return RehearsalDryRunReport(
        mode="dry_run",
        status="review_only_non_live",
        readiness_gate="READY_TO_RUN_WITH_INTENTIONAL_LIVE_OPT_IN",
        rehearsal_ready_to_run=True,
        live_behavior_attempted=False,
        runtime_start_attempted=False,
        login_attempted=False,
        subscribe_attempted=False,
        provider_connection_attempted=False,
        explicit_live_opt_in_required=True,
        operator_runtime_mode_required=OPERATOR_LIVE_RUNTIME,
        secrets_or_token_files_read=False,
        credentials_required_for_dry_run=False,
        services=DRY_RUN_SERVICES,
        contract_plan=plan,
        rejected_contracts=rejected,
        provider_diagnostics=diagnostics,
        refresh_floor_seconds=MIN_STREAM_REFRESH_FLOOR_SECONDS,
        credential_free_gate_command=(
            "PYTHONPATH=src:../../source/ntb_engine/src:. "
            "uv run python scripts/run_operator_live_runtime_rehearsal.py --readiness-gate"
        ),
        intentional_live_command=(
            "NTB_OPERATOR_RUNTIME_MODE=OPERATOR_LIVE_RUNTIME "
            "PYTHONPATH=src:../../source/ntb_engine/src:. "
            "uv run python scripts/run_operator_live_runtime_rehearsal.py --live --duration 10"
        ),
        production_readiness_blockers=(
            "real_CHART_FUTURES_delivery_not_recorded_for_ES_NQ_CL_6E_MGC",
            "symbol_entitlement_and_rollover_proof_beyond_exact_run_not_recorded",
            "full_live_session_marimo_usability_not_proven",
            "production_release_remains_premature_until_non_levelone_predicates_are_satisfied",
        ),
        limitations=(
            "review_preflight_only_not_subscription_or_login",
            "schwab_live_readiness_unproven_until_authorized_manual_rehearsal",
            "levelone_futures_and_chart_futures_delivery_not_assumed",
            "mgc_micro_gold_not_gc_substitute",
            "default_app_launch_remains_non_live",
        ),
    )


def _rejected_contracts(candidate_contracts: Sequence[str]) -> tuple[DryRunRejectedContract, ...]:
    rejected: list[DryRunRejectedContract] = []
    seen: set[str] = set()
    for contract in candidate_contracts:
        normalized = normalize_contract_symbol(str(contract))
        if not normalized or normalized in seen or is_final_target_contract(normalized):
            continue
        seen.add(normalized)
        if is_never_supported_contract(normalized):
            policy = "never_supported_excluded"
        elif is_excluded_final_target_contract(normalized):
            policy = "excluded"
        else:
            policy = "unsupported"
        rejected.append(DryRunRejectedContract(contract=normalized, policy=policy))
    return tuple(rejected)


# ---------------------------------------------------------------------------
# Token + credentials providers
# ---------------------------------------------------------------------------


@dataclass
class _CachedStreamerCredentialsProvider:
    """Fetches user-preference once via the existing probe helper, then caches."""

    fetch_func: Callable[[], object]
    extract_func: Callable[[object], object]
    _credentials: StreamerCredentials | None = None

    def load_streamer_credentials(self) -> StreamerCredentials:
        if self._credentials is not None:
            return self._credentials
        try:
            payload = self.fetch_func()
        except Exception as exc:
            raise OperatorSchwabStreamerSessionError(
                f"user_preference_fetch_failed:{type(exc).__name__}"
            ) from exc
        try:
            probe_credentials = self.extract_func(payload)
        except Exception as exc:
            raise OperatorSchwabStreamerSessionError(
                f"streamer_credentials_extract_failed:{type(exc).__name__}"
            ) from exc
        try:
            self._credentials = StreamerCredentials(
                streamer_socket_url=str(probe_credentials.streamer_socket_url),
                streamer_socket_host=str(probe_credentials.streamer_socket_host),
                schwab_client_customer_id=str(probe_credentials.schwab_client_customer_id),
                schwab_client_correl_id=str(probe_credentials.schwab_client_correl_id),
                schwab_client_channel=str(probe_credentials.schwab_client_channel),
                schwab_client_function_id=str(probe_credentials.schwab_client_function_id),
            )
        except AttributeError as exc:
            raise OperatorSchwabStreamerSessionError(
                f"streamer_credentials_shape_invalid:{type(exc).__name__}"
            ) from exc
        return self._credentials


@dataclass
class _OnceCachingCredentialsProvider:
    """Cache the streamer credentials so the harness probe and the session login share one fetch.

    The harness validates ``streamer_credentials_obtained`` before calling
    :func:`start_operator_live_runtime`. The session subsequently invokes
    ``load_streamer_credentials`` from inside ``login()``. This wrapper guarantees
    a single underlying fetch per rehearsal regardless of how many times the
    method is called.
    """

    inner: SchwabStreamerCredentialsProvider
    _cached: StreamerCredentials | None = None

    def load_streamer_credentials(self) -> StreamerCredentials:
        if self._cached is None:
            self._cached = self.inner.load_streamer_credentials()
        return self._cached


def _build_default_credentials_provider(
    *,
    token_path: Path,
    target_root: Path,
    app_key: str,
    app_secret: str,
    token_url: str,
) -> _CachedStreamerCredentialsProvider:
    probe_config = levelone_probe.ProbeConfig(
        app_key_present=True,
        app_secret_present=True,
        app_key=app_key,
        app_secret=app_secret,
        callback_url="",
        token_path=token_path,
        token_path_display="",
        futures_symbol="/ESM26",
        futures_root="ES",
        futures_month_code="M",
        futures_month_name="June",
        futures_year="26",
        stream_fields=DEFAULT_LEVELONE_FUTURES_FIELD_IDS,
        timeout_seconds=10.0,
        dry_run=False,
        token_url=token_url or DEFAULT_TOKEN_URL,
        repo_root=target_root.parent.parent,
        target_root=target_root,
    )

    def _fetch() -> object:
        payload, _access_token = levelone_probe.fetch_user_preference_with_refresh_retry(probe_config)
        return payload

    return _CachedStreamerCredentialsProvider(
        fetch_func=_fetch,
        extract_func=levelone_probe.extract_streamer_credentials,
    )


# ---------------------------------------------------------------------------
# Validation phases
# ---------------------------------------------------------------------------


def _validate_repo_check(target_root: Path) -> bool:
    return target_root.is_dir() and (target_root / "src" / "ntb_marimo_console").is_dir()


def _validate_env_keys_present(env: Mapping[str, str]) -> bool:
    return all(env.get(name, "").strip() for name in REQUIRED_ENV_KEYS)


def _validate_token_path_under_target_state(env: Mapping[str, str], target_root: Path) -> tuple[bool, Path | None]:
    raw = env.get("SCHWAB_TOKEN_PATH", "").strip()
    if not raw:
        return False, None
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = (target_root / candidate).resolve()
    else:
        candidate = candidate.resolve()
    state_root = (target_root / ".state").resolve()
    try:
        return candidate.is_relative_to(state_root), candidate
    except AttributeError:
        try:
            candidate.relative_to(state_root)
            return True, candidate
        except ValueError:
            return False, candidate


def _apply_token_contract_report(
    report: RehearsalReport,
    token_contract: TokenContractReport,
) -> None:
    report.token_file_present = token_contract.token_file_present
    report.token_file_parseable = token_contract.token_file_parseable
    report.token_contract_valid = token_contract.token_contract_valid
    report.access_token_present = token_contract.access_token_present
    report.refresh_token_present = token_contract.refresh_token_present
    report.token_fresh = token_contract.token_fresh


# ---------------------------------------------------------------------------
# Receive-loop pump
# ---------------------------------------------------------------------------


def _pump_receive_loop(
    *,
    session: OperatorSchwabStreamerSession,
    manager: object,
    duration_seconds: float,
    clock: Callable[[], float],
    reconnect_controller: SchwabReconnectController | None = None,
    chart_bar_builder: ChartFuturesBarBuilder | None = None,
) -> ReceiveLoopObservation:
    """Drive the bounded dispatch loop.

    Returns (market_data_received, distinct_contract_count) as observed via
    the manager's snapshot at loop exit. The loop only invokes
    ``session.dispatch_one`` and ``manager.snapshot()`` — no login, no
    subscribe, no start.
    """

    contracts_seen: set[str] = set()
    chart_contracts_seen: set[str] = set()
    chart_completed_contracts_seen: set[str] = set()
    chart_blocking_reasons: list[str] = []
    received_at_least_one = False
    chart_received_at_least_one = False

    def _handler(message: Mapping[str, object]) -> None:
        nonlocal chart_received_at_least_one, received_at_least_one
        service = str(message.get("service", "")).strip().upper()
        if service == "CHART_FUTURES":
            try:
                manager.ingest_message(message)
            except Exception:
                pass
            if chart_bar_builder is None:
                chart_blocking_reasons.append("chart_bar_builder_unavailable")
                return
            result = chart_bar_builder.ingest(message)
            if result.accepted and result.contract:
                chart_contracts_seen.add(result.contract)
                chart_received_at_least_one = True
                state = chart_bar_builder.state(result.contract)
                if state.completed_five_minute_bars:
                    chart_completed_contracts_seen.add(result.contract)
                return
            chart_blocking_reasons.extend(str(reason) for reason in result.blocking_reasons)
            return
        try:
            ingested = manager.ingest_message(message)
        except Exception:
            return
        if isinstance(ingested, StreamManagerSnapshot):
            for record in ingested.cache.records:
                if record.fresh:
                    contracts_seen.add(str(record.contract))
                    received_at_least_one = True

    active_session = session
    deadline = clock() + max(0.0, duration_seconds)
    while clock() < deadline:
        if not active_session.dispatch_one(handler=_handler):
            token_refresh_reason = _token_refresh_blocking_reason(active_session)
            if token_refresh_reason:
                marker = getattr(manager, "mark_connection_lost", None)
                if callable(marker):
                    marker(token_refresh_reason)
                break
            if reconnect_controller is not None and should_attempt_reconnect(active_session):
                result = reconnect_controller.reconnect(
                    current_session=active_session,
                    reason="connection_lost",
                )
                if result.reconnected and result.session is not None:
                    active_session = result.session
                    continue
                break
            remaining = deadline - clock()
            if remaining <= 0:
                break
            # ``dispatch_one`` intentionally collapses timeout/EOF/inactive
            # into False. Stay within the rehearsal duration so one quiet
            # receive interval does not prove the whole bounded window quiet.
            time.sleep(min(MAX_IDLE_DISPATCH_SLEEP_SECONDS, max(0.0, remaining)))
            continue
    return ReceiveLoopObservation(
        market_data_received=received_at_least_one,
        received_contracts_count=len(contracts_seen),
        chart_data_received=chart_received_at_least_one,
        chart_received_contracts_count=len(chart_contracts_seen),
        chart_completed_five_minute_contracts_count=len(chart_completed_contracts_seen),
        chart_blocking_reasons=tuple(dict.fromkeys(chart_blocking_reasons)),
        quote_contracts=tuple(sorted(contracts_seen)),
        chart_contracts=tuple(sorted(chart_contracts_seen)),
        chart_completed_contracts=tuple(sorted(chart_completed_contracts_seen)),
    )


def _token_refresh_blocking_reason(session: object) -> str | None:
    reason_func = getattr(session, "token_refresh_blocking_reason", None)
    if not callable(reason_func):
        return None
    try:
        reason = reason_func()
    except Exception:
        return "token_refresh_status_unavailable"
    if not isinstance(reason, str) or not reason.strip():
        return None
    return _sanitize_text(reason.strip())


def _per_contract_runtime_status(observation: ReceiveLoopObservation) -> dict[str, dict[str, str]]:
    quote_contracts = set(observation.quote_contracts)
    chart_contracts = set(observation.chart_contracts)
    chart_completed_contracts = set(observation.chart_completed_contracts)
    statuses: dict[str, dict[str, str]] = {}
    for contract in final_target_contracts():
        quote_status = "fresh_quote_update_received" if contract in quote_contracts else "no_quote_event_received"
        if contract in chart_completed_contracts:
            chart_status = "completed_five_minute_bar_available"
            last_chart_event_status = "completed_bar"
        elif contract in chart_contracts:
            chart_status = "chart_event_received_building_or_partial"
            last_chart_event_status = "building_or_partial_bar"
        else:
            chart_status = "no_chart_event_received"
            last_chart_event_status = "none"
        statuses[contract] = {
            "quote_status": quote_status,
            "chart_status": chart_status,
            "last_chart_event_status": last_chart_event_status,
        }
    return statuses


# ---------------------------------------------------------------------------
# Public entry point with injectable seam (for tests)
# ---------------------------------------------------------------------------


@dataclass
class RehearsalDependencies:
    token_provider: SchwabAccessTokenProvider | None = None
    credentials_provider: SchwabStreamerCredentialsProvider | None = None
    websocket_factory: SchwabWebsocketFactory | None = None
    manager_builder: Callable[[SchwabStreamManagerConfig, object], object] | None = None
    clock: Callable[[], float] | None = None


def run_with_dependencies(
    *,
    args: argparse.Namespace,
    env: Mapping[str, str],
    target_root: Path,
    deps: RehearsalDependencies | None = None,
) -> RehearsalReport:
    """Tested seam. The CLI wraps this with real defaults; tests inject mocks."""

    deps = deps or RehearsalDependencies()
    clock = deps.clock or time.monotonic
    report = RehearsalReport()

    repo_ok = _validate_repo_check(target_root)
    report.repo_check = repo_ok
    report.checks.append(RehearsalCheck("repo_check", "ok" if repo_ok else "blocked"))
    if not repo_ok:
        report.mode = "blocked"
        report.status = "blocked"
        report.blocking_reason = "repo_check_failed"
        return report

    report.live_flag = bool(getattr(args, "live", False))
    if not report.live_flag:
        report.mode = "blocked"
        report.status = "blocked"
        report.blocking_reason = "live_flag_required"
        report.checks.append(RehearsalCheck("live_flag", "blocked"))
        return report
    report.checks.append(RehearsalCheck("live_flag", "ok"))

    report.operator_live_runtime_env = env.get("NTB_OPERATOR_RUNTIME_MODE", "").strip().upper() == OPERATOR_LIVE_RUNTIME
    if not report.operator_live_runtime_env:
        report.mode = "blocked"
        report.status = "blocked"
        report.blocking_reason = "operator_live_runtime_opt_in_required"
        report.checks.append(RehearsalCheck("operator_live_runtime_env", "blocked"))
        return report
    report.checks.append(RehearsalCheck("operator_live_runtime_env", "ok"))

    report.env_keys_present = _validate_env_keys_present(env)
    if not report.env_keys_present:
        report.mode = "blocked"
        report.status = "blocked"
        report.blocking_reason = "required_env_keys_missing"
        report.checks.append(RehearsalCheck("env_keys_present", "blocked"))
        return report
    report.checks.append(RehearsalCheck("env_keys_present", "ok"))

    token_under_state, token_path = _validate_token_path_under_target_state(env, target_root)
    report.token_path_under_target_state = token_under_state
    if not token_under_state or token_path is None:
        report.mode = "blocked"
        report.status = "blocked"
        report.blocking_reason = "token_path_outside_target_state"
        report.checks.append(RehearsalCheck("token_path_under_target_state", "blocked"))
        return report
    report.checks.append(RehearsalCheck("token_path_under_target_state", "ok"))

    token_contract = validate_token_contract(token_path, target_root=target_root)
    _apply_token_contract_report(report, token_contract)
    if not report.token_file_present:
        report.mode = "blocked"
        report.status = "blocked"
        report.blocking_reason = "token_file_missing"
        report.checks.append(RehearsalCheck("token_file_present", "blocked"))
        return report
    report.checks.append(RehearsalCheck("token_file_present", "ok"))
    report.checks.append(
        RehearsalCheck("token_file_parseable", "ok" if report.token_file_parseable else "blocked")
    )
    report.checks.append(
        RehearsalCheck("access_token_present", "ok" if report.access_token_present else "blocked")
    )
    report.checks.append(
        RehearsalCheck("refresh_token_present", "ok" if report.refresh_token_present else "blocked")
    )
    report.checks.append(
        RehearsalCheck("token_contract_valid", "ok" if report.token_contract_valid else "blocked")
    )
    if not report.token_contract_valid:
        report.mode = "blocked"
        report.status = "blocked"
        report.blocking_reason = token_contract.blocking_reason
        return report

    report.checks.append(RehearsalCheck("token_fresh", "ok" if report.token_fresh == "yes" else "info", report.token_fresh))

    app_key = env.get("SCHWAB_APP_KEY", "").strip()
    app_secret = env.get("SCHWAB_APP_SECRET", "").strip()
    token_url = env.get("SCHWAB_TOKEN_URL", "").strip() or DEFAULT_TOKEN_URL

    token_provider = deps.token_provider or RefreshableAccessTokenProvider(
        token_path=token_path,
        target_root=target_root,
        app_key=app_key,
        app_secret=app_secret,
        token_url=token_url,
    )
    raw_credentials_provider = deps.credentials_provider or _build_default_credentials_provider(
        token_path=token_path,
        target_root=target_root,
        app_key=app_key,
        app_secret=app_secret,
        token_url=token_url,
    )
    credentials_provider = _OnceCachingCredentialsProvider(inner=raw_credentials_provider)
    websocket_factory = deps.websocket_factory or default_schwab_websocket_factory()

    # Probe the credentials provider once before runtime start so the rehearsal
    # surface reports streamer_credentials_obtained accurately.
    try:
        credentials_provider.load_streamer_credentials()
        report.streamer_credentials_obtained = True
        report.checks.append(RehearsalCheck("streamer_credentials_obtained", "ok"))
    except Exception:
        report.mode = "blocked"
        report.status = "blocked"
        report.streamer_credentials_obtained = False
        report.blocking_reason = "streamer_credentials_unavailable"
        report.checks.append(RehearsalCheck("streamer_credentials_obtained", "blocked"))
        return report

    symbol_overrides = getattr(args, "symbol", None) or {}
    config = _build_stream_config(symbol_overrides=symbol_overrides)
    chart_bar_builder = ChartFuturesBarBuilder(expected_symbols=resolve_symbol_map(symbol_overrides))
    report.subscribed_contracts_count = len(config.contracts_requested)

    captured_sessions: list[OperatorSchwabStreamerSession] = []
    base_session_factory = build_operator_schwab_streamer_session_factory(
        access_token_provider=token_provider,
        credentials_provider=credentials_provider,
        websocket_factory=websocket_factory,
    )

    def _capturing_session_factory(c: SchwabStreamManagerConfig) -> OperatorSchwabStreamerSession:
        session = base_session_factory(c)
        captured_sessions.append(session)
        return session

    client_factory = build_operator_schwab_stream_client_factory(
        streamer_session_factory=_capturing_session_factory,
    )

    launch: OperatorLiveLaunchResult | None = None
    reconnect_controller: SchwabReconnectController | None = None
    initial_session: OperatorSchwabStreamerSession | None = None
    report.runtime_start_attempted = True
    report.checks.append(RehearsalCheck("runtime_start_attempted", "ok"))
    duration_clamped = max(MIN_DURATION_SECONDS, min(MAX_DURATION_SECONDS, int(getattr(args, "duration", DEFAULT_DURATION_SECONDS))))
    report.duration_seconds = float(duration_clamped)

    try:
        try:
            launch = start_operator_live_runtime(
                client_factory=client_factory,
                config=config,
                values=dict(env),
                manager_builder=deps.manager_builder,
                register=False,
            )
        except OperatorLiveRuntimeOptInRequired:
            report.mode = "blocked"
            report.status = "blocked"
            report.blocking_reason = "operator_live_runtime_opt_in_required"
            report.checks.append(RehearsalCheck("live_login_succeeded", "blocked"))
            return report
        except OperatorLiveRuntimeFactoryError:
            report.mode = "blocked"
            report.status = "blocked"
            report.blocking_reason = "client_factory_error"
            report.checks.append(RehearsalCheck("live_login_succeeded", "blocked"))
            return report
        except OperatorLiveRuntimeStartError:
            report.mode = "blocked"
            report.status = "blocked"
            report.blocking_reason = "live_login_or_subscribe_failed"
            report.checks.append(RehearsalCheck("live_login_succeeded", "blocked"))
            return report

        # Successful start: login + subscribe both succeeded inside manager.start().
        report.live_login_succeeded = True
        report.live_subscribe_succeeded = True
        report.checks.append(RehearsalCheck("live_login_succeeded", "ok"))
        report.checks.append(RehearsalCheck("live_subscribe_succeeded", "ok"))

        if not captured_sessions:
            report.mode = "blocked"
            report.status = "blocked"
            report.blocking_reason = "session_capture_missing"
            return report
        session = captured_sessions[-1]
        initial_session = session
        reconnect_controller = SchwabReconnectController(
            config=config,
            session_factory=_capturing_session_factory,
            manager=launch.manager,
        )

        receive_observation = _pump_receive_loop(
            session=session,
            manager=launch.manager,
            duration_seconds=float(duration_clamped),
            clock=clock,
            reconnect_controller=reconnect_controller,
            chart_bar_builder=chart_bar_builder,
        )
        report.market_data_received = receive_observation.market_data_received
        report.received_contracts_count = receive_observation.received_contracts_count
        report.chart_data_received = receive_observation.chart_data_received
        report.chart_received_contracts_count = receive_observation.chart_received_contracts_count
        report.chart_completed_five_minute_contracts_count = (
            receive_observation.chart_completed_five_minute_contracts_count
        )
        report.per_contract_status = _per_contract_runtime_status(receive_observation)
        report.checks.append(
            RehearsalCheck(
                "market_data_received",
                "ok" if receive_observation.market_data_received else "info",
            )
        )
        report.checks.append(
            RehearsalCheck(
                "chart_data_received",
                "ok" if receive_observation.chart_data_received else "info",
            )
        )

        post_receive_snapshot = launch.manager.snapshot()
        if receive_observation.market_data_received:
            report.market_data_diagnostic = "levelone_futures_updates_received"
        elif (
            isinstance(post_receive_snapshot, StreamManagerSnapshot)
            and post_receive_snapshot.blocking_reasons
        ):
            report.market_data_diagnostic = "stream_blocked_after_subscription"
        else:
            report.market_data_diagnostic = "no_levelone_futures_updates_received_during_bounded_window"
        if receive_observation.chart_completed_five_minute_contracts_count == len(final_target_contracts()):
            report.chart_data_diagnostic = "chart_futures_completed_five_minute_bars_received"
        elif receive_observation.chart_data_received:
            report.chart_data_diagnostic = "chart_futures_building_or_partial_bars_received"
        elif receive_observation.chart_blocking_reasons:
            report.chart_data_diagnostic = "chart_futures_malformed_or_blocked"
        else:
            report.chart_data_diagnostic = "no_chart_futures_updates_received_during_bounded_window"
        if isinstance(post_receive_snapshot, StreamManagerSnapshot) and post_receive_snapshot.state in {
            "blocked",
            "disconnected",
            "error",
        }:
            report.mode = "blocked"
            report.status = "blocked"
            report.blocking_reason = (
                post_receive_snapshot.blocking_reasons[0]
                if post_receive_snapshot.blocking_reasons
                else f"stream_manager_state:{post_receive_snapshot.state}"
            )
        else:
            report.mode = "live"
            report.status = "ok"
    finally:
        if launch is not None:
            try:
                if (
                    reconnect_controller is not None
                    and reconnect_controller.active_session is not None
                    and reconnect_controller.active_session is not initial_session
                ):
                    reconnect_controller.active_session.close()
                stop_operator_live_runtime(launch.manager)
                report.cleanup_status = "ok"
                report.checks.append(RehearsalCheck("cleanup_status", "ok"))
            except Exception:
                report.cleanup_status = "error"
                report.checks.append(RehearsalCheck("cleanup_status", "error"))
        else:
            report.cleanup_status = "skipped"

    return report


def _print_report(report: RehearsalReport, *, as_json: bool) -> None:
    if as_json:
        print(render_json(report))
    else:
        print(render_text(report))


def _print_dry_run_report(report: RehearsalDryRunReport, *, as_json: bool) -> None:
    if as_json:
        print(render_dry_run_json(report))
    else:
        print(render_dry_run_text(report))


def run(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(sys.argv[1:] if argv is None else argv))
    if getattr(args, "dry_run", False) or getattr(args, "readiness_gate", False):
        report = build_dry_run_report(
            symbol_overrides=getattr(args, "symbol", None) or {},
            candidate_contracts=tuple(getattr(args, "dry_run_contract", ()) or ()),
            provider_diagnostics=tuple(getattr(args, "provider_diagnostic", ()) or ()),
        )
        _print_dry_run_report(report, as_json=getattr(args, "json", False))
        return 0
    report = run_with_dependencies(
        args=args,
        env=dict(os.environ),
        target_root=_TARGET_ROOT,
    )
    _print_report(report, as_json=getattr(args, "json", False))
    if report.status == "ok":
        return 0
    if report.mode == "blocked":
        return 2
    return 1


if __name__ == "__main__":
    sys.exit(run())
