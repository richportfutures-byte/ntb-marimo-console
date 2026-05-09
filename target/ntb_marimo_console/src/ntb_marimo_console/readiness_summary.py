from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from .contract_universe import (
    excluded_final_target_contracts,
    final_target_contracts,
    is_final_target_contract,
)
from .runtime_diagnostics import LaunchRequest, build_preflight_report
from .runtime_modes import build_app_shell_for_profile
from .runtime_profiles import RuntimeProfile, list_runtime_profiles


FIVE_CONTRACT_READINESS_SUMMARY_SCHEMA: Final[str] = "five_contract_readiness_summary_v1"
PRESERVED_ENGINE_AUTHORITY_STATEMENT: Final[str] = (
    "Readiness summary is a read-only operator visibility surface. The preserved engine remains the only decision authority."
)
MANUAL_ONLY_BOUNDARY_STATEMENT: Final[str] = (
    "Manual execution only. This summary cannot authorize trades, routing, fills, or platform actions."
)
LIVE_RUNTIME_READINESS_STATUS: Final[str] = "NOT_WIRED"
LIVE_RUNTIME_CACHE_STATUS: Final[str] = "not_wired_to_operator_launch"
LIVE_RUNTIME_READINESS_BLOCKERS: Final[tuple[str, ...]] = (
    "five_contract_summary_builds_from_fixture_preserved_shells",
    "operator_launch_does_not_supply_stream_manager_snapshot",
    "explicit_opt_in_runtime_cache_reader_not_bound_to_summary",
)


@dataclass(frozen=True)
class FiveContractReadinessRow:
    contract: str
    runtime_profile_id: str
    final_target_support_status: str
    selectable_final_target: bool
    preflight_status: str
    startup_readiness_state: str
    operator_ready: bool
    non_live_fixture_usable: bool
    market_data_status: str
    live_data_available: bool
    missing_live_fields: tuple[str, ...]
    live_runtime_readiness_state: str
    runtime_cache_status: str
    runtime_cache_bound: bool
    runtime_cache_blocked_reasons: tuple[str, ...]
    trigger_state_summary: str
    trigger_valid_count: int
    trigger_true_count: int
    query_gate_status: str
    query_ready: bool
    query_not_ready_reasons: tuple[str, ...]
    primary_blocked_reasons: tuple[str, ...]
    evidence_replay_status: str
    run_history_status: str
    manual_only_boundary: str
    preserved_engine_authority: str
    trade_execution_authorized: bool = False
    proof_capture_satisfies_live_readiness: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "runtime_profile_id": self.runtime_profile_id,
            "final_target_support_status": self.final_target_support_status,
            "selectable_final_target": self.selectable_final_target,
            "preflight_status": self.preflight_status,
            "startup_readiness_state": self.startup_readiness_state,
            "operator_ready": self.operator_ready,
            "non_live_fixture_usable": self.non_live_fixture_usable,
            "market_data_status": self.market_data_status,
            "live_data_available": self.live_data_available,
            "missing_live_fields": list(self.missing_live_fields),
            "live_runtime_readiness_state": self.live_runtime_readiness_state,
            "runtime_cache_status": self.runtime_cache_status,
            "runtime_cache_bound": self.runtime_cache_bound,
            "runtime_cache_blocked_reasons": list(self.runtime_cache_blocked_reasons),
            "trigger_state_summary": self.trigger_state_summary,
            "trigger_valid_count": self.trigger_valid_count,
            "trigger_true_count": self.trigger_true_count,
            "query_gate_status": self.query_gate_status,
            "query_ready": self.query_ready,
            "query_not_ready_reasons": list(self.query_not_ready_reasons),
            "primary_blocked_reasons": list(self.primary_blocked_reasons),
            "evidence_replay_status": self.evidence_replay_status,
            "run_history_status": self.run_history_status,
            "manual_only_boundary": self.manual_only_boundary,
            "preserved_engine_authority": self.preserved_engine_authority,
            "trade_execution_authorized": self.trade_execution_authorized,
            "proof_capture_satisfies_live_readiness": self.proof_capture_satisfies_live_readiness,
        }


@dataclass(frozen=True)
class FiveContractReadinessSummary:
    rows: tuple[FiveContractReadinessRow, ...]
    active_profile_id: str | None = None
    schema: str = FIVE_CONTRACT_READINESS_SUMMARY_SCHEMA
    mode: str = "non_live_fixture_safe"
    default_launch_live: bool = False
    live_credentials_required: bool = False
    decision_authority: str = "preserved_engine_only"
    manual_execution_only: bool = True
    summary_can_authorize_trades: bool = False
    live_runtime_readiness_status: str = LIVE_RUNTIME_READINESS_STATUS
    explicit_opt_in_runtime_cache_required: bool = True
    runtime_cache_bound_to_operator_launch: bool = False
    live_runtime_cache_can_authorize_trades: bool = False
    live_runtime_readiness_blockers: tuple[str, ...] = LIVE_RUNTIME_READINESS_BLOCKERS

    def to_dict(self) -> dict[str, object]:
        return {
            "surface": "Five-Contract Readiness Summary",
            "schema": self.schema,
            "mode": self.mode,
            "active_profile_id": self.active_profile_id,
            "final_target_contracts": list(final_target_contracts()),
            "excluded_contracts": list(excluded_final_target_contracts()),
            "default_launch_live": self.default_launch_live,
            "live_credentials_required": self.live_credentials_required,
            "decision_authority": self.decision_authority,
            "manual_execution_only": self.manual_execution_only,
            "summary_can_authorize_trades": self.summary_can_authorize_trades,
            "live_runtime_readiness_status": self.live_runtime_readiness_status,
            "explicit_opt_in_runtime_cache_required": self.explicit_opt_in_runtime_cache_required,
            "runtime_cache_bound_to_operator_launch": self.runtime_cache_bound_to_operator_launch,
            "live_runtime_cache_can_authorize_trades": self.live_runtime_cache_can_authorize_trades,
            "live_runtime_readiness_blockers": list(self.live_runtime_readiness_blockers),
            "rows": [row.to_dict() for row in self.rows],
            "limitations": [
                "non_live_fixture_summary_only",
                "live_data_unavailable_until_explicit_opt_in",
                "explicit_opt_in_live_runtime_cache_not_wired",
                "real_schwab_readiness_requires_sanitized_live_proof",
            ],
        }


def build_five_contract_readiness_summary(
    *,
    active_profile_id: str | None = None,
) -> FiveContractReadinessSummary:
    rows = tuple(
        _build_row(profile, active_profile_id=active_profile_id)
        for profile in _final_target_preserved_profiles()
    )
    return FiveContractReadinessSummary(rows=rows, active_profile_id=active_profile_id)


def build_five_contract_readiness_summary_surface(
    *,
    active_profile_id: str | None = None,
) -> dict[str, object]:
    return build_five_contract_readiness_summary(active_profile_id=active_profile_id).to_dict()


def _final_target_preserved_profiles() -> tuple[RuntimeProfile, ...]:
    profiles_by_contract = {
        profile.contract: profile
        for profile in list_runtime_profiles()
        if profile.runtime_mode == "preserved_engine" and is_final_target_contract(profile.contract)
    }
    return tuple(profiles_by_contract[contract] for contract in final_target_contracts())


def _build_row(
    profile: RuntimeProfile,
    *,
    active_profile_id: str | None,
) -> FiveContractReadinessRow:
    request = LaunchRequest(
        mode=profile.runtime_mode,
        profile=profile,
        lockout=False,
        fixtures_root=None,
        adapter_binding=profile.default_model_adapter_ref,
    )
    report = build_preflight_report(request)
    preflight_status = "PASS" if report.passed else "FAIL"
    shell: dict[str, object] | None = None
    startup_readiness_state = "BLOCKED"
    operator_ready = False
    blocked_reasons: tuple[str, ...] = tuple(_preflight_blockers(report))

    if report.passed:
        try:
            shell = build_app_shell_for_profile(
                profile=profile,
                fixtures_root=request.fixtures_root,
                lockout=request.lockout,
                model_adapter=report.resolved_adapter,
                query_action_requested=False,
            )
        except Exception as exc:
            startup_readiness_state = "ERROR"
            blocked_reasons = (f"runtime_assembly_failed:{type(exc).__name__}",)
        else:
            startup_readiness_state = "OPERATOR_SURFACES_READY"
            operator_ready = True
            blocked_reasons = _blocked_reasons_from_shell(shell)

    market_data_status = _market_data_status(shell)
    missing_live_fields = _missing_live_fields(shell, market_data_status=market_data_status)
    query_ready = _query_ready(shell)
    return FiveContractReadinessRow(
        contract=profile.contract,
        runtime_profile_id=profile.profile_id,
        final_target_support_status="final_supported",
        selectable_final_target=True,
        preflight_status=preflight_status,
        startup_readiness_state=startup_readiness_state,
        operator_ready=operator_ready,
        non_live_fixture_usable=operator_ready and market_data_status == "Market data unavailable",
        market_data_status=market_data_status,
        live_data_available=market_data_status != "Market data unavailable",
        missing_live_fields=missing_live_fields,
        live_runtime_readiness_state=LIVE_RUNTIME_READINESS_STATUS,
        runtime_cache_status=LIVE_RUNTIME_CACHE_STATUS,
        runtime_cache_bound=False,
        runtime_cache_blocked_reasons=LIVE_RUNTIME_READINESS_BLOCKERS,
        trigger_state_summary=_trigger_state_summary(shell),
        trigger_valid_count=_trigger_count(shell, field="is_valid"),
        trigger_true_count=_trigger_count(shell, field="is_true"),
        query_gate_status=_query_gate_status(shell),
        query_ready=query_ready,
        query_not_ready_reasons=() if query_ready else blocked_reasons,
        primary_blocked_reasons=blocked_reasons,
        evidence_replay_status=_audit_replay_status(shell),
        run_history_status=_run_history_status(shell),
        manual_only_boundary=MANUAL_ONLY_BOUNDARY_STATEMENT,
        preserved_engine_authority=PRESERVED_ENGINE_AUTHORITY_STATEMENT,
    )


def _surfaces(shell: Mapping[str, object] | None) -> Mapping[str, object]:
    if not isinstance(shell, Mapping):
        return {}
    surfaces = shell.get("surfaces")
    return surfaces if isinstance(surfaces, Mapping) else {}


def _surface(shell: Mapping[str, object] | None, key: str) -> Mapping[str, object]:
    value = _surfaces(shell).get(key)
    return value if isinstance(value, Mapping) else {}


def _market_data_status(shell: Mapping[str, object] | None) -> str:
    live = _surface(shell, "live_observables")
    market_data = live.get("market_data")
    if not isinstance(market_data, Mapping):
        return "Market data unavailable"
    status = market_data.get("status")
    return str(status).strip() if isinstance(status, str) and status.strip() else "Market data unavailable"


def _missing_live_fields(
    shell: Mapping[str, object] | None,
    *,
    market_data_status: str,
) -> tuple[str, ...]:
    fields: list[str] = []
    if market_data_status == "Market data unavailable":
        fields.append("live_market_data")
    trigger_panel = _surface(shell, "trigger_table")
    rows = trigger_panel.get("rows")
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            missing = row.get("missing_fields")
            if isinstance(missing, list):
                fields.extend(str(item) for item in missing if str(item).strip())
    return _dedupe(tuple(fields))


def _trigger_count(shell: Mapping[str, object] | None, *, field: str) -> int:
    trigger_panel = _surface(shell, "trigger_table")
    rows = trigger_panel.get("rows")
    if not isinstance(rows, list):
        return 0
    return sum(1 for row in rows if isinstance(row, Mapping) and row.get(field) is True)


def _trigger_state_summary(shell: Mapping[str, object] | None) -> str:
    valid_count = _trigger_count(shell, field="is_valid")
    true_count = _trigger_count(shell, field="is_true")
    if valid_count == 0:
        return "trigger_unavailable"
    if true_count > 0:
        return "trigger_true"
    return "query_not_ready_no_declared_trigger_true"


def _query_ready(shell: Mapping[str, object] | None) -> bool:
    query = _surface(shell, "query_action")
    return query.get("query_enabled") is True or query.get("action_available") is True


def _query_gate_status(shell: Mapping[str, object] | None) -> str:
    query = _surface(shell, "query_action")
    for key in ("live_query_status", "query_action_status"):
        value = query.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    if _query_ready(shell):
        return "ELIGIBLE"
    return "BLOCKED"


def _blocked_reasons_from_shell(shell: Mapping[str, object] | None) -> tuple[str, ...]:
    query = _surface(shell, "query_action")
    reasons = query.get("blocked_reasons")
    values: list[str] = []
    if isinstance(reasons, list):
        values.extend(str(reason) for reason in reasons if str(reason).strip())
    if _market_data_status(shell) == "Market data unavailable":
        values.append("live_data_unavailable_non_live_default")
    if not _query_ready(shell):
        values.append("query_not_ready")
    return _dedupe(tuple(values))


def _audit_replay_status(shell: Mapping[str, object] | None) -> str:
    audit = _surface(shell, "audit_replay")
    status = audit.get("status")
    return str(status).strip() if isinstance(status, str) and status.strip() else "NOT_READY"


def _run_history_status(shell: Mapping[str, object] | None) -> str:
    run_history = _surface(shell, "run_history")
    rows = run_history.get("rows")
    if isinstance(rows, list):
        return "AVAILABLE" if rows else "EMPTY"
    return "UNAVAILABLE"


def _preflight_blockers(report: object) -> tuple[str, ...]:
    checks = getattr(report, "checks", ())
    reasons = tuple(
        str(getattr(check, "summary", "preflight_failed"))
        for check in checks
        if getattr(check, "passed", False) is not True
    )
    return reasons or ("preflight_failed",)


def _dedupe(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = value.strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return tuple(result)
