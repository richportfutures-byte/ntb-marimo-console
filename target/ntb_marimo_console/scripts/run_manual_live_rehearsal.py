#!/usr/bin/env python3
# ruff: noqa: E402
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

SCRIPT_DIR = Path(__file__).resolve().parent
TARGET_ROOT = SCRIPT_DIR.parent
SRC_ROOT = TARGET_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from ntb_marimo_console.contract_universe import final_target_contracts
from ntb_marimo_console.evidence_replay import (
    create_evidence_event,
    parse_evidence_events_jsonl,
    serialize_evidence_events_jsonl,
)
from ntb_marimo_console.live_observables.builder import build_live_observable_snapshot_v2
from ntb_marimo_console.market_data import ChartFuturesBarBuilder
from ntb_marimo_console.market_data.stream_events import redact_sensitive_text
from ntb_marimo_console.market_data.stream_manager import (
    MIN_STREAM_REFRESH_FLOOR_SECONDS,
    SchwabStreamManager,
    SchwabStreamManagerConfig,
    StreamClientResult,
    StreamSubscriptionRequest,
)
from ntb_marimo_console.pipeline_query_gate import PipelineQueryGateRequest, evaluate_pipeline_query_gate
from ntb_marimo_console.trigger_state import TriggerState, TriggerStateResult


REHEARSAL_SCHEMA = "manual_live_rehearsal_v1"
NOW = datetime(2026, 5, 6, 14, 0, 0, tzinfo=timezone.utc)
FINAL_TARGET_SYMBOLS: dict[str, str] = {
    "ES": "/ESM26",
    "NQ": "/NQM26",
    "CL": "/CLM26",
    "6E": "/6EM26",
    "MGC": "/MGCM26",
}
REHEARSAL_SERVICES = ("LEVELONE_FUTURES", "CHART_FUTURES")
REHEARSAL_FIELDS = (0, 1, 2, 3, 4, 5)
UNSUPPORTED_CONTRACT_CHECKS = ("ZN", "GC")
FIXTURE_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "ES": ("cumulative_delta", "breadth"),
    "NQ": ("relative_strength_vs_es",),
    "CL": ("eia_lockout", "cumulative_delta", "current_volume_vs_average"),
    "6E": ("dxy", "session_sequence"),
    "MGC": ("dxy", "cash_10y_yield", "fear_catalyst_state"),
}
FixtureScenario = Literal["ready", "missing", "stale", "mismatch", "live_failure"]


@dataclass
class FixtureClock:
    current: datetime = NOW

    def __call__(self) -> datetime:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current = self.current + timedelta(seconds=seconds)


class FixtureStreamClient:
    def __init__(self, *, login_succeeds: bool = True, subscription_succeeds: bool = True, reason: str | None = None) -> None:
        self.login_succeeds = login_succeeds
        self.subscription_succeeds = subscription_succeeds
        self.reason = reason
        self.login_calls = 0
        self.subscription_calls = 0
        self.close_calls = 0
        self.subscription_requests: list[StreamSubscriptionRequest] = []

    def login(self, config: SchwabStreamManagerConfig) -> StreamClientResult:
        self.login_calls += 1
        return StreamClientResult(succeeded=self.login_succeeds, reason=self.reason)

    def subscribe(self, request: StreamSubscriptionRequest) -> StreamClientResult:
        self.subscription_calls += 1
        self.subscription_requests.append(request)
        return StreamClientResult(succeeded=self.subscription_succeeds, reason=self.reason)

    def close(self) -> StreamClientResult:
        self.close_calls += 1
        return StreamClientResult(succeeded=True)


@dataclass(frozen=True)
class RehearsalCheck:
    name: str
    status: str
    blocking_reasons: tuple[str, ...] = ()
    details: tuple[str, ...] = ()
    manual_observation_required: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "blocking_reasons": list(self.blocking_reasons),
            "details": list(self.details),
            "manual_observation_required": self.manual_observation_required,
        }


@dataclass(frozen=True)
class RehearsalReport:
    mode: str
    scenario: str
    status: str
    final_target_contracts: tuple[str, ...]
    services: tuple[str, ...]
    refresh_floor_seconds: float
    checks: tuple[RehearsalCheck, ...]
    manual_checklist: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return self.status == "pass"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": REHEARSAL_SCHEMA,
            "mode": self.mode,
            "scenario": self.scenario,
            "status": self.status,
            "final_target_contracts": list(self.final_target_contracts),
            "excluded_contracts_checked": list(UNSUPPORTED_CONTRACT_CHECKS),
            "services": list(self.services),
            "refresh_floor_seconds": self.refresh_floor_seconds,
            "checks": [check.to_dict() for check in self.checks],
            "manual_checklist": list(self.manual_checklist),
        }


def build_stream_config(*, explicit_live_opt_in: bool) -> SchwabStreamManagerConfig:
    return SchwabStreamManagerConfig(
        provider="schwab",
        services_requested=REHEARSAL_SERVICES,
        symbols_requested=tuple(FINAL_TARGET_SYMBOLS[contract] for contract in final_target_contracts()),
        fields_requested=REHEARSAL_FIELDS,
        contracts_requested=final_target_contracts(),
        explicit_live_opt_in=explicit_live_opt_in,
        refresh_floor_seconds=MIN_STREAM_REFRESH_FLOOR_SECONDS,
        cache_max_age_seconds=MIN_STREAM_REFRESH_FLOOR_SECONDS,
    )


def run_fixture_rehearsal(scenario: FixtureScenario = "ready") -> RehearsalReport:
    clock = FixtureClock()
    client = FixtureStreamClient(
        login_succeeds=scenario != "live_failure",
        reason=(
            "login_denied access_token=PRIVATE refresh_token=PRIVATE Authorization: Bearer PRIVATE customerId=PRIVATE"
            if scenario == "live_failure"
            else None
        ),
    )
    manager = SchwabStreamManager(build_stream_config(explicit_live_opt_in=True), client=client, clock=clock)
    start_snapshot = manager.start()
    if scenario == "live_failure":
        return _failure_after_live_denial_report(manager, client, start_snapshot.blocking_reasons, scenario=scenario)

    manager.record_heartbeat()
    _ingest_levelone_fixture_messages(manager, scenario=scenario)
    bar_states = _ingest_chart_fixture_messages(scenario=scenario)
    dependency_states = _fixture_dependency_states()
    refresh_snapshots = tuple(
        build_live_observable_snapshot_v2(
            manager.read_cache_snapshot(),
            expected_symbols=FINAL_TARGET_SYMBOLS,
            bar_states=bar_states,
            dependency_states=dependency_states,
        )
        for _ in range(3)
    )
    cache_snapshot = manager.read_cache_snapshot()
    live_snapshot = refresh_snapshots[-1]
    gate = _fail_closed_query_gate(live_snapshot.to_dict(), bar_states["ES"].usable)
    evidence_check = _evidence_check(cache_snapshot.generated_at, cache_snapshot.ready)
    unsupported_check = _unsupported_contract_check()
    checks = (
        _contract_universe_check(),
        _connection_discipline_check(manager, client),
        _levelone_check(cache_snapshot, scenario=scenario),
        _chart_check(bar_states, scenario=scenario),
        _cache_read_check(cache_snapshot, live_snapshot.to_dict(), scenario=scenario),
        _refresh_cycle_check(manager, client, refresh_count=len(refresh_snapshots)),
        _blocked_data_check(cache_snapshot, bar_states, scenario=scenario),
        _query_gate_check(gate),
        unsupported_check,
        evidence_check,
    )
    return RehearsalReport(
        mode="fixture",
        scenario=scenario,
        status="pass" if all(check.status == "pass" for check in checks) else "blocked",
        final_target_contracts=final_target_contracts(),
        services=REHEARSAL_SERVICES,
        refresh_floor_seconds=MIN_STREAM_REFRESH_FLOOR_SECONDS,
        checks=checks,
    )


def build_manual_live_checklist_report() -> RehearsalReport:
    checks = (
        RehearsalCheck(
            name="explicit_live_opt_in",
            status="manual_required",
            details=("operator_supplied_--live",),
            manual_observation_required=True,
        ),
        RehearsalCheck(
            name="five_contract_subscription",
            status="manual_required",
            details=("confirm_LEVELONE_FUTURES_and_CHART_FUTURES_for_ES_NQ_CL_6E_MGC",),
            manual_observation_required=True,
        ),
        RehearsalCheck(
            name="one_connection_discipline",
            status="manual_required",
            details=("confirm_one_login_and_one_subscription_cycle_for_operator_session",),
            manual_observation_required=True,
        ),
        RehearsalCheck(
            name="fail_closed_query_readiness",
            status="manual_required",
            details=("confirm_no_QUERY_READY_without_preserved_engine_trigger_and_gate_prerequisites",),
            manual_observation_required=True,
        ),
    )
    return RehearsalReport(
        mode="manual_live",
        scenario="manual_operator_observation",
        status="manual_required",
        final_target_contracts=final_target_contracts(),
        services=REHEARSAL_SERVICES,
        refresh_floor_seconds=MIN_STREAM_REFRESH_FLOOR_SECONDS,
        checks=checks,
        manual_checklist=(
            "Run only during an operator-approved Schwab market-data rehearsal window.",
            "Use only the final target contracts ES, NQ, CL, 6E, and MGC.",
            "Confirm one session login and one subscription cycle before repeated UI/cache refresh reads.",
            "Confirm LEVELONE_FUTURES quote updates and CHART_FUTURES bar updates for each final target contract.",
            "Confirm stale, missing, delayed, or mismatched data keeps readiness blocked.",
            "Confirm live data alone does not authorize trades, orders, accounts, fills, P&L, or QUERY_READY.",
            "Do not paste raw credentials, tokens, authorization headers, streamer URLs, customer IDs, correl IDs, account IDs, or payloads into reports.",
        ),
    )


def disabled_report() -> RehearsalReport:
    return RehearsalReport(
        mode="disabled",
        scenario="no_explicit_rehearsal_mode",
        status="blocked",
        final_target_contracts=final_target_contracts(),
        services=REHEARSAL_SERVICES,
        refresh_floor_seconds=MIN_STREAM_REFRESH_FLOOR_SECONDS,
        checks=(
            RehearsalCheck(
                name="explicit_rehearsal_mode_required",
                status="blocked",
                blocking_reasons=("pass_--fixture_or_--dry-run_for_safe_mock_rehearsal_or_--live_for_manual_checklist",),
            ),
        ),
    )


def render_report(report: RehearsalReport) -> str:
    header = {
        "pass": "MANUAL_LIVE_REHEARSAL_FIXTURE_PASS",
        "blocked": "MANUAL_LIVE_REHEARSAL_BLOCKED",
        "manual_required": "MANUAL_LIVE_REHEARSAL_MANUAL_REQUIRED",
    }.get(report.status, "MANUAL_LIVE_REHEARSAL_BLOCKED")
    lines = [header]
    lines.append(f"schema={REHEARSAL_SCHEMA}")
    lines.append(f"mode={_safe(report.mode)}")
    lines.append(f"scenario={_safe(report.scenario)}")
    lines.append(f"status={_safe(report.status)}")
    lines.append("contracts=" + ",".join(report.final_target_contracts))
    lines.append("services=" + ",".join(report.services))
    lines.append(f"refresh_floor_seconds={report.refresh_floor_seconds:g}")
    for check in report.checks:
        reasons = ",".join(check.blocking_reasons) if check.blocking_reasons else "none"
        lines.append(f"check={_safe(check.name)} status={_safe(check.status)} reasons={_safe(reasons)}")
    for item in report.manual_checklist:
        lines.append(f"manual_checklist={_safe(item)}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="R18 explicit manual live rehearsal foundation.")
    parser.add_argument("--fixture", action="store_true", help="Run the deterministic fixture/mock rehearsal.")
    parser.add_argument("--dry-run", action="store_true", help="Alias for --fixture.")
    parser.add_argument("--live", action="store_true", help="Print the explicit manual live checklist; does not run default tests.")
    parser.add_argument(
        "--fixture-scenario",
        choices=("ready", "missing", "stale", "mismatch", "live_failure"),
        default="ready",
        help="Fixture scenario used by --fixture/--dry-run.",
    )
    parser.add_argument("--json", action="store_true", help="Render sanitized JSON instead of text.")
    return parser


def run(argv: tuple[str, ...] | None = None) -> int:
    args = build_parser().parse_args(tuple(sys.argv[1:] if argv is None else argv))
    if args.live and (args.fixture or args.dry_run):
        report = RehearsalReport(
            mode="invalid",
            scenario="mutually_exclusive_modes",
            status="blocked",
            final_target_contracts=final_target_contracts(),
            services=REHEARSAL_SERVICES,
            refresh_floor_seconds=MIN_STREAM_REFRESH_FLOOR_SECONDS,
            checks=(RehearsalCheck(name="mode_selection", status="blocked", blocking_reasons=("choose_fixture_or_live_not_both",)),),
        )
        _print_report(report, as_json=args.json)
        return 1
    if args.fixture or args.dry_run:
        report = run_fixture_rehearsal(args.fixture_scenario)
        _print_report(report, as_json=args.json)
        return 0 if report.passed else 1
    if args.live:
        report = build_manual_live_checklist_report()
        _print_report(report, as_json=args.json)
        return 2
    report = disabled_report()
    _print_report(report, as_json=args.json)
    return 1


def _print_report(report: RehearsalReport, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(_sanitize_payload(report.to_dict()), sort_keys=True))
    else:
        print(render_report(report))


def _ingest_levelone_fixture_messages(manager: SchwabStreamManager, *, scenario: FixtureScenario) -> None:
    for index, contract in enumerate(final_target_contracts()):
        if scenario == "missing" and contract == "MGC":
            continue
        symbol = "/WRONGM26" if scenario == "mismatch" and contract == "ES" else FINAL_TARGET_SYMBOLS[contract]
        received_at = (NOW - timedelta(seconds=MIN_STREAM_REFRESH_FLOOR_SECONDS + 5)).isoformat() if scenario == "stale" else NOW.isoformat()
        manager.ingest_message(
            {
                "service": "LEVELONE_FUTURES",
                "symbol": symbol,
                "contract": contract,
                "message_type": "quote",
                "fields": _complete_levelone_fields(index=index, timestamp=received_at),
                "received_at": received_at,
            }
        )


def _complete_levelone_fields(*, index: int, timestamp: str) -> dict[str, object]:
    return {
        "bid": 100.0 + index,
        "ask": 100.25 + index,
        "last": 100.125 + index,
        "bid_size": 10 + index,
        "ask_size": 12 + index,
        "quote_time": timestamp,
        "trade_time": timestamp,
        "volume": 25_000 + index,
        "open": 99.5 + index,
        "high": 101.0 + index,
        "low": 98.75 + index,
        "prior_close": 99.25 + index,
        "tradable": True,
        "active": True,
        "security_status": "Normal",
    }


def _ingest_chart_fixture_messages(*, scenario: FixtureScenario) -> dict[str, object]:
    builder = ChartFuturesBarBuilder(expected_symbols=FINAL_TARGET_SYMBOLS)
    for contract in final_target_contracts():
        if scenario == "missing" and contract == "MGC":
            continue
        symbol = "/WRONGM26" if scenario == "mismatch" and contract == "ES" else FINAL_TARGET_SYMBOLS[contract]
        for minute in range(5):
            start = NOW + timedelta(minutes=minute)
            builder.ingest(
                {
                    "service": "CHART_FUTURES",
                    "contract": contract,
                    "symbol": symbol,
                    "start_time": start.isoformat(),
                    "end_time": (start + timedelta(minutes=1)).isoformat(),
                    "open": 100.0 + minute,
                    "high": 100.5 + minute,
                    "low": 99.75 + minute,
                    "close": 100.25 + minute,
                    "volume": 100 + minute,
                    "completed": True,
                }
            )
    return builder.states()


def _fixture_dependency_states() -> dict[str, dict[str, dict[str, object]]]:
    return {
        contract: {
            dependency: {
                "status": "available",
                "source": "fixture_manual_rehearsal",
                "source_status": "available",
                "fresh": True,
                "value": "fixture_available",
            }
            for dependency in dependencies
        }
        for contract, dependencies in FIXTURE_DEPENDENCIES.items()
    }


def _fail_closed_query_gate(live_snapshot: dict[str, object], bars_usable: bool) -> object:
    trigger_state = TriggerStateResult(
        contract="ES",
        setup_id="manual_rehearsal_setup",
        trigger_id="manual_rehearsal_trigger",
        state=TriggerState.DORMANT,
        distance_to_trigger_ticks=None,
        required_fields=("quote.bid", "quote.ask", "quote.last"),
        missing_fields=(),
        invalid_reasons=(),
        blocking_reasons=("manual_rehearsal_no_preserved_engine_query_ready",),
        last_updated=NOW.isoformat(),
    )
    return evaluate_pipeline_query_gate(
        PipelineQueryGateRequest(
            contract="ES",
            profile_id="preserved_es_phase1",
            trigger_state=trigger_state,
            profile_exists=True,
            profile_preflight_passed=True,
            watchman_validator_status="READY",
            live_snapshot=live_snapshot,
            bars_available=bars_usable,
            bars_fresh=bars_usable,
            required_trigger_fields_present=True,
            support_matrix_final_supported=True,
            provider_status="connected",
            stream_status="active",
            session_valid=True,
            event_lockout_active=False,
            evaluated_at=NOW.isoformat(),
        )
    )


def _contract_universe_check() -> RehearsalCheck:
    contracts = final_target_contracts()
    status = "pass" if contracts == ("ES", "NQ", "CL", "6E", "MGC") else "blocked"
    return RehearsalCheck(name="final_target_contract_universe", status=status, details=contracts)


def _connection_discipline_check(manager: SchwabStreamManager, client: FixtureStreamClient) -> RehearsalCheck:
    snapshot = manager.snapshot()
    ok = snapshot.login_count == 1 and snapshot.subscription_count == 1 and client.login_calls == 1 and client.subscription_calls == 1
    return RehearsalCheck(
        name="one_stream_connection_discipline",
        status="pass" if ok else "blocked",
        blocking_reasons=() if ok else ("expected_one_login_and_one_subscription",),
        details=(f"login_count={snapshot.login_count}", f"subscription_count={snapshot.subscription_count}"),
    )


def _levelone_check(cache_snapshot: object, *, scenario: FixtureScenario) -> RehearsalCheck:
    records = tuple(getattr(cache_snapshot, "records", ()))
    available = {record.contract for record in records if getattr(record, "service", "") == "LEVELONE_FUTURES"}
    quote_contracts = tuple(contract for contract in final_target_contracts() if contract in available)
    ok = scenario == "ready" and quote_contracts == final_target_contracts()
    blocked_ok = (scenario == "stale" and quote_contracts == final_target_contracts()) or (
        scenario in {"missing", "mismatch"} and quote_contracts != final_target_contracts()
    )
    return RehearsalCheck(
        name="levelone_futures_updates",
        status="pass" if ok or blocked_ok else "blocked",
        blocking_reasons=() if ok else ("levelone_not_ready_for_all_final_targets",),
        details=quote_contracts,
    )


def _chart_check(bar_states: dict[str, object], *, scenario: FixtureScenario) -> RehearsalCheck:
    ready_contracts = tuple(contract for contract, state in bar_states.items() if getattr(state, "usable", False))
    ok = scenario == "ready" and ready_contracts == final_target_contracts()
    blocked_ok = (scenario == "stale" and ready_contracts == final_target_contracts()) or (
        scenario in {"missing", "mismatch"} and ready_contracts != final_target_contracts()
    )
    return RehearsalCheck(
        name="chart_futures_bar_updates",
        status="pass" if ok or blocked_ok else "blocked",
        blocking_reasons=() if ok else ("chart_bars_not_usable_for_all_final_targets",),
        details=ready_contracts,
    )


def _cache_read_check(cache_snapshot: object, live_snapshot: dict[str, object], *, scenario: FixtureScenario) -> RehearsalCheck:
    data_quality = live_snapshot.get("data_quality") if isinstance(live_snapshot, dict) else None
    ready = bool(data_quality.get("ready")) if isinstance(data_quality, dict) else False
    ok = scenario == "ready" and bool(getattr(cache_snapshot, "ready", False)) and ready
    blocked_ok = scenario != "ready" and (not bool(getattr(cache_snapshot, "ready", False)) or not ready)
    return RehearsalCheck(
        name="cache_readable_for_operator_workspace",
        status="pass" if ok or blocked_ok else "blocked",
        blocking_reasons=() if ok else ("cache_or_live_observable_not_ready",),
        details=(f"cache_ready={getattr(cache_snapshot, 'ready', False)}", f"live_snapshot_ready={ready}"),
    )


def _refresh_cycle_check(manager: SchwabStreamManager, client: FixtureStreamClient, *, refresh_count: int) -> RehearsalCheck:
    snapshot = manager.snapshot()
    ok = refresh_count >= 3 and snapshot.login_count == 1 and client.login_calls == 1
    return RehearsalCheck(
        name="repeated_refresh_does_not_relogin",
        status="pass" if ok else "blocked",
        blocking_reasons=() if ok else ("refresh_cycle_relogin_detected",),
        details=(f"refresh_reads={refresh_count}", f"login_count={snapshot.login_count}"),
    )


def _blocked_data_check(cache_snapshot: object, bar_states: dict[str, object], *, scenario: FixtureScenario) -> RehearsalCheck:
    if scenario == "ready":
        return RehearsalCheck(name="stale_missing_mismatched_data_fail_closed", status="pass", details=("ready_fixture_has_no_blocked_fixture_data",))
    cache_blocked = not bool(getattr(cache_snapshot, "ready", False))
    bars_blocked = any(not getattr(state, "usable", False) for state in bar_states.values())
    ok = cache_blocked or bars_blocked
    return RehearsalCheck(
        name="stale_missing_mismatched_data_fail_closed",
        status="pass" if ok else "blocked",
        blocking_reasons=() if ok else ("bad_fixture_data_did_not_block_readiness",),
        details=(f"cache_ready={getattr(cache_snapshot, 'ready', False)}",),
    )


def _query_gate_check(gate: object) -> RehearsalCheck:
    enabled = bool(getattr(gate, "enabled", False))
    authorized = bool(getattr(gate, "pipeline_query_authorized", False))
    ok = not enabled and not authorized
    reasons = tuple(getattr(gate, "blocking_reasons", ()))
    return RehearsalCheck(
        name="no_false_query_ready",
        status="pass" if ok else "blocked",
        blocking_reasons=() if ok else ("query_gate_unexpectedly_enabled",),
        details=reasons,
    )


def _unsupported_contract_check() -> RehearsalCheck:
    client = FixtureStreamClient()
    manager = SchwabStreamManager(
        SchwabStreamManagerConfig(
            provider="schwab",
            services_requested=REHEARSAL_SERVICES,
            symbols_requested=("/ZNM26", "/GCM26"),
            fields_requested=REHEARSAL_FIELDS,
            contracts_requested=UNSUPPORTED_CONTRACT_CHECKS,
            explicit_live_opt_in=True,
        ),
        client=client,
        clock=FixtureClock(),
    )
    snapshot = manager.start()
    ok = snapshot.state == "blocked" and client.login_calls == 0 and all(contract not in final_target_contracts() for contract in UNSUPPORTED_CONTRACT_CHECKS)
    return RehearsalCheck(
        name="no_unsupported_contract_ready_state",
        status="pass" if ok else "blocked",
        blocking_reasons=() if ok else ("unsupported_contract_rehearsal_not_blocked",),
        details=tuple(snapshot.blocking_reasons),
    )


def _evidence_check(timestamp: str, cache_ready: bool) -> RehearsalCheck:
    events = tuple(
        create_evidence_event(
            contract=contract,
            profile_id=f"preserved_{contract.lower()}_phase1",
            event_type="stream_connected",
            source="fixture",
            event_id=f"r18-{contract.lower()}-stream-connected",
            timestamp=timestamp,
            live_snapshot_ref=f"r18_fixture_snapshot_{contract.lower()}",
            data_quality={"ready": cache_ready, "state": "fixture_rehearsal"},
        )
        for contract in final_target_contracts()
    )
    payload = serialize_evidence_events_jsonl(events)
    parsed = parse_evidence_events_jsonl(payload)
    ok = parsed.valid and len(parsed.events) == len(final_target_contracts())
    return RehearsalCheck(
        name="audit_evidence_events_jsonl_serializable",
        status="pass" if ok else "blocked",
        blocking_reasons=() if ok else parsed.errors,
        details=(f"event_count={len(parsed.events)}",),
    )


def _failure_after_live_denial_report(
    manager: SchwabStreamManager,
    client: FixtureStreamClient,
    blocking_reasons: tuple[str, ...],
    *,
    scenario: FixtureScenario,
) -> RehearsalReport:
    snapshot = manager.snapshot()
    no_fallback = snapshot.state == "blocked" and snapshot.login_count == 1 and snapshot.subscription_count == 0 and client.subscription_calls == 0 and not snapshot.cache.ready
    checks = (
        _contract_universe_check(),
        RehearsalCheck(
            name="simulated_live_failure_no_fixture_fallback",
            status="pass" if no_fallback else "blocked",
            blocking_reasons=() if no_fallback else ("fixture_fallback_after_live_failure_detected",),
            details=blocking_reasons,
        ),
        RehearsalCheck(
            name="live_failure_sanitized",
            status="pass" if all("PRIVATE" not in reason for reason in blocking_reasons) else "blocked",
            blocking_reasons=blocking_reasons,
        ),
    )
    return RehearsalReport(
        mode="fixture",
        scenario=scenario,
        status="pass" if all(check.status == "pass" for check in checks) else "blocked",
        final_target_contracts=final_target_contracts(),
        services=REHEARSAL_SERVICES,
        refresh_floor_seconds=MIN_STREAM_REFRESH_FLOOR_SECONDS,
        checks=checks,
    )


def _sanitize_payload(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _sanitize_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sanitize_payload(item) for item in value]
    if isinstance(value, tuple):
        return [_sanitize_payload(item) for item in value]
    if isinstance(value, str):
        return _safe(value)
    return value


def _safe(value: object) -> str:
    text = str(value).replace("\n", " ")
    lower = text.lower()
    sensitive_terms = (
        "access_token",
        "refresh_token",
        "authorization",
        "bearer",
        "secret",
        "app_key",
        "app_secret",
        "credential",
        "customer",
        "correl",
        "account",
        "token",
        "wss://",
        "https://",
        "http://",
    )
    if any(term in lower for term in sensitive_terms):
        return redact_sensitive_text(text)[:320]
    return text[:320]


if __name__ == "__main__":
    raise SystemExit(run())
