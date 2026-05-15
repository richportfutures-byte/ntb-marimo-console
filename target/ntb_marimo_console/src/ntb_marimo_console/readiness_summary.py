from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final, Literal

from .contract_universe import (
    excluded_final_target_contracts,
    final_target_contracts,
    is_excluded_final_target_contract,
    is_final_target_contract,
    is_never_supported_contract,
)
from .live_observables import build_live_observable_snapshot_v2
from .live_observables.schema_v2 import LiveObservableSnapshotV2
from .market_data.stream_cache import StreamCacheSnapshot
from .market_data.stream_manager import StreamManagerSnapshot


_TRANSIENT_INACTIVE_REASONS: Final[frozenset[str]] = frozenset(
    {"stream_not_active", "provider_disconnected"}
)
LEVELONE_FUTURES_SERVICE: Final[str] = "LEVELONE_FUTURES"
CHART_FUTURES_SERVICE: Final[str] = "CHART_FUTURES"
from .runtime_diagnostics import LaunchRequest, build_preflight_report
from .runtime_modes import build_app_shell_for_profile
from .runtime_profiles import RuntimeProfile, list_runtime_profiles


FIVE_CONTRACT_READINESS_SUMMARY_SCHEMA: Final[str] = "five_contract_readiness_summary_v1"
RuntimeReadinessState = Literal[
    "LIVE_RUNTIME_NOT_REQUESTED",
    "LIVE_RUNTIME_CONNECTED",
    "LIVE_RUNTIME_DISABLED",
    "LIVE_RUNTIME_STALE",
    "LIVE_RUNTIME_ERROR",
    "LIVE_RUNTIME_MISSING_CONTRACT",
    "LIVE_RUNTIME_MISSING_REQUIRED_FIELDS",
    "LIVE_RUNTIME_EXCLUDED_CONTRACT_BLOCKED",
]
RuntimeReadinessSnapshot = StreamManagerSnapshot | StreamCacheSnapshot
PRESERVED_ENGINE_AUTHORITY_STATEMENT: Final[str] = (
    "Readiness summary is a read-only operator visibility surface. The preserved engine remains the only decision authority."
)
MANUAL_ONLY_BOUNDARY_STATEMENT: Final[str] = (
    "Manual execution only. This summary cannot authorize trades, routing, fills, or platform actions."
)
READINESS_SOURCE_FIXTURE_PRESERVED: Final[str] = "fixture_preserved_shell"
READINESS_SOURCE_RUNTIME_CACHE: Final[str] = "runtime_cache_derived"
LIVE_RUNTIME_NOT_REQUESTED: Final[RuntimeReadinessState] = "LIVE_RUNTIME_NOT_REQUESTED"
LIVE_RUNTIME_CONNECTED: Final[RuntimeReadinessState] = "LIVE_RUNTIME_CONNECTED"
LIVE_RUNTIME_DISABLED: Final[RuntimeReadinessState] = "LIVE_RUNTIME_DISABLED"
LIVE_RUNTIME_STALE: Final[RuntimeReadinessState] = "LIVE_RUNTIME_STALE"
LIVE_RUNTIME_ERROR: Final[RuntimeReadinessState] = "LIVE_RUNTIME_ERROR"
LIVE_RUNTIME_MISSING_CONTRACT: Final[RuntimeReadinessState] = "LIVE_RUNTIME_MISSING_CONTRACT"
LIVE_RUNTIME_MISSING_REQUIRED_FIELDS: Final[RuntimeReadinessState] = "LIVE_RUNTIME_MISSING_REQUIRED_FIELDS"
LIVE_RUNTIME_EXCLUDED_CONTRACT_BLOCKED: Final[RuntimeReadinessState] = "LIVE_RUNTIME_EXCLUDED_CONTRACT_BLOCKED"
LIVE_RUNTIME_READINESS_STATUS: Final[RuntimeReadinessState] = LIVE_RUNTIME_NOT_REQUESTED
LIVE_RUNTIME_CACHE_STATUS: Final[str] = "runtime_cache_not_requested"
LIVE_RUNTIME_NOT_REQUESTED_BLOCKERS: Final[tuple[str, ...]] = ("live_runtime_snapshot_not_requested",)


@dataclass(frozen=True)
class FiveContractReadinessRow:
    contract: str
    contract_label: str | None
    runtime_profile_id: str
    readiness_source: str
    final_target_support_status: str
    selectable_final_target: bool
    preflight_status: str
    startup_readiness_state: str
    operator_ready: bool
    non_live_fixture_usable: bool
    market_data_status: str
    live_data_available: bool
    quote_status: str
    chart_status: str
    quote_freshness_state: str
    chart_freshness_state: str
    missing_live_fields: tuple[str, ...]
    live_runtime_readiness_state: RuntimeReadinessState
    operator_runtime_state: str
    runtime_cache_status: str
    runtime_cache_bound: bool
    runtime_cache_blocked_reasons: tuple[str, ...]
    chart_blocking_reasons: tuple[str, ...]
    runtime_provider_status: str | None
    runtime_symbol: str | None
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
            "contract_label": self.contract_label,
            "runtime_profile_id": self.runtime_profile_id,
            "readiness_source": self.readiness_source,
            "final_target_support_status": self.final_target_support_status,
            "selectable_final_target": self.selectable_final_target,
            "preflight_status": self.preflight_status,
            "startup_readiness_state": self.startup_readiness_state,
            "operator_ready": self.operator_ready,
            "non_live_fixture_usable": self.non_live_fixture_usable,
            "market_data_status": self.market_data_status,
            "live_data_available": self.live_data_available,
            "quote_status": self.quote_status,
            "chart_status": self.chart_status,
            "quote_freshness_state": self.quote_freshness_state,
            "chart_freshness_state": self.chart_freshness_state,
            "missing_live_fields": list(self.missing_live_fields),
            "live_runtime_readiness_state": self.live_runtime_readiness_state,
            "operator_runtime_state": self.operator_runtime_state,
            "runtime_cache_status": self.runtime_cache_status,
            "runtime_cache_bound": self.runtime_cache_bound,
            "runtime_cache_blocked_reasons": list(self.runtime_cache_blocked_reasons),
            "chart_blocking_reasons": list(self.chart_blocking_reasons),
            "runtime_provider_status": self.runtime_provider_status,
            "runtime_symbol": self.runtime_symbol,
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
    readiness_source: str = READINESS_SOURCE_FIXTURE_PRESERVED
    default_launch_live: bool = False
    live_credentials_required: bool = False
    decision_authority: str = "preserved_engine_only"
    manual_execution_only: bool = True
    summary_can_authorize_trades: bool = False
    live_runtime_readiness_status: RuntimeReadinessState = LIVE_RUNTIME_READINESS_STATUS
    explicit_opt_in_runtime_cache_required: bool = True
    runtime_cache_bound_to_operator_launch: bool = False
    live_runtime_cache_can_authorize_trades: bool = False
    live_runtime_readiness_blockers: tuple[str, ...] = LIVE_RUNTIME_NOT_REQUESTED_BLOCKERS
    runtime_cache_source_type: str = "not_requested"
    runtime_cache_provider_status: str | None = None
    runtime_cache_generated_at: str | None = None
    runtime_cache_snapshot_ready: bool = False
    runtime_stream_active: bool = False
    runtime_stream_state: str | None = None
    runtime_stream_active_contracts: tuple[str, ...] = ()
    runtime_quote_path_active: bool = False
    runtime_levelone_active_contracts: tuple[str, ...] = ()
    runtime_chart_active_contracts: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "surface": "Five-Contract Readiness Summary",
            "schema": self.schema,
            "mode": self.mode,
            "readiness_source": self.readiness_source,
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
            "runtime_cache_source_type": self.runtime_cache_source_type,
            "runtime_cache_provider_status": self.runtime_cache_provider_status,
            "runtime_cache_generated_at": self.runtime_cache_generated_at,
            "runtime_cache_snapshot_ready": self.runtime_cache_snapshot_ready,
            "runtime_stream_active": self.runtime_stream_active,
            "runtime_stream_state": self.runtime_stream_state,
            "runtime_stream_active_contracts": list(self.runtime_stream_active_contracts),
            "runtime_quote_path_active": self.runtime_quote_path_active,
            "runtime_levelone_active_contracts": list(self.runtime_levelone_active_contracts),
            "runtime_chart_active_contracts": list(self.runtime_chart_active_contracts),
            "rows": [row.to_dict() for row in self.rows],
            "limitations": list(_limitations_for_summary(self)),
        }


def build_five_contract_readiness_summary(
    *,
    active_profile_id: str | None = None,
    runtime_snapshot: RuntimeReadinessSnapshot | None = None,
) -> FiveContractReadinessSummary:
    runtime_context = _build_runtime_context(runtime_snapshot)
    rows = tuple(
        _build_row(profile, active_profile_id=active_profile_id, runtime_context=runtime_context)
        for profile in _final_target_preserved_profiles()
    )
    runtime_status = _summary_runtime_status(rows, runtime_context)
    return FiveContractReadinessSummary(
        rows=rows,
        active_profile_id=active_profile_id,
        mode="runtime_cache_derived" if runtime_context.cache_snapshot is not None else "non_live_fixture_safe",
        readiness_source=(
            READINESS_SOURCE_RUNTIME_CACHE
            if runtime_context.cache_snapshot is not None
            else READINESS_SOURCE_FIXTURE_PRESERVED
        ),
        live_runtime_readiness_status=runtime_status,
        runtime_cache_bound_to_operator_launch=runtime_context.cache_snapshot is not None,
        live_runtime_readiness_blockers=_summary_runtime_blockers(rows, runtime_context, runtime_status),
        runtime_cache_source_type=runtime_context.source_type,
        runtime_cache_provider_status=runtime_context.provider_status,
        runtime_cache_generated_at=runtime_context.generated_at,
        runtime_cache_snapshot_ready=runtime_context.snapshot_ready,
        runtime_stream_active=runtime_context.stream_active,
        runtime_stream_state=runtime_context.manager_state,
        runtime_stream_active_contracts=runtime_context.stream_active_contracts,
        runtime_quote_path_active=runtime_context.quote_path_active,
        runtime_levelone_active_contracts=runtime_context.levelone_active_contracts,
        runtime_chart_active_contracts=runtime_context.chart_active_contracts,
    )


def build_five_contract_readiness_summary_surface(
    *,
    active_profile_id: str | None = None,
    runtime_snapshot: RuntimeReadinessSnapshot | None = None,
) -> dict[str, object]:
    return build_five_contract_readiness_summary(
        active_profile_id=active_profile_id,
        runtime_snapshot=runtime_snapshot,
    ).to_dict()


def _final_target_preserved_profiles() -> tuple[RuntimeProfile, ...]:
    profiles_by_contract = {
        profile.contract: profile
        for profile in list_runtime_profiles()
        if profile.runtime_mode == "preserved_engine" and is_final_target_contract(profile.contract)
    }
    return tuple(profiles_by_contract[contract] for contract in final_target_contracts())


@dataclass(frozen=True)
class _RuntimeReadinessContext:
    cache_snapshot: StreamCacheSnapshot | None
    observable_snapshot: LiveObservableSnapshotV2 | None
    source_type: str
    provider_status: str | None
    generated_at: str | None
    snapshot_ready: bool
    manager_state: str | None
    manager_blocking_reasons: tuple[str, ...]
    excluded_or_unsupported_contracts: tuple[str, ...]
    stream_active: bool = False
    stream_active_contracts: tuple[str, ...] = ()
    levelone_active_contracts: tuple[str, ...] = ()
    chart_active_contracts: tuple[str, ...] = ()
    quote_path_active: bool = False

    @property
    def global_blocking_reasons(self) -> tuple[str, ...]:
        excluded_reasons = tuple(
            f"excluded_contract_in_runtime_snapshot:{contract}"
            if is_excluded_final_target_contract(contract) or is_never_supported_contract(contract)
            else f"unsupported_contract_in_runtime_snapshot:{contract}"
            for contract in self.excluded_or_unsupported_contracts
        )
        return _dedupe(self.manager_blocking_reasons + excluded_reasons)


@dataclass(frozen=True)
class _RuntimeContractReadiness:
    state: RuntimeReadinessState
    cache_status: str
    market_data_status: str
    live_data_available: bool
    quote_status: str
    chart_status: str
    quote_freshness_state: str
    chart_freshness_state: str
    missing_live_fields: tuple[str, ...]
    blocked_reasons: tuple[str, ...]
    chart_blocking_reasons: tuple[str, ...]
    provider_status: str | None
    symbol: str | None
    label: str | None


def _build_runtime_context(runtime_snapshot: RuntimeReadinessSnapshot | None) -> _RuntimeReadinessContext:
    if runtime_snapshot is None:
        return _RuntimeReadinessContext(
            cache_snapshot=None,
            observable_snapshot=None,
            source_type="not_requested",
            provider_status=None,
            generated_at=None,
            snapshot_ready=False,
            manager_state=None,
            manager_blocking_reasons=(),
            excluded_or_unsupported_contracts=(),
        )

    source_type = "stream_cache_snapshot"
    manager_state: str | None = None
    manager_blocking_reasons: tuple[str, ...] = ()
    stream_active = False
    stream_active_contracts: tuple[str, ...] = ()
    levelone_active_contracts: tuple[str, ...] = ()
    chart_active_contracts: tuple[str, ...] = ()
    quote_path_active = False
    cache_snapshot = runtime_snapshot
    if isinstance(runtime_snapshot, StreamManagerSnapshot):
        source_type = "stream_manager_snapshot"
        manager_state = runtime_snapshot.state
        manager_blocking_reasons = tuple(str(reason) for reason in runtime_snapshot.blocking_reasons)
        cache_snapshot = runtime_snapshot.cache
        stream_active_contracts = _stream_active_contracts(runtime_snapshot)
        levelone_active_contracts = _service_active_contracts(
            runtime_snapshot, LEVELONE_FUTURES_SERVICE
        )
        chart_active_contracts = _service_active_contracts(
            runtime_snapshot, CHART_FUTURES_SERVICE
        )
        # The stream manager is the source of truth for stream identity. When the
        # manager reports state="active", the stream/provider classification must
        # follow that — historical transient reasons (e.g., a stream_not_active
        # from before subscription completed) and a normalised
        # provider_disconnected reason must not flip identity to inactive.
        stream_active = manager_state == "active"
        # The QUOTE PATH (LEVELONE_FUTURES) is the freshness signal that drives
        # provider/stream classification. CHART_FUTURES staleness must not
        # globally downgrade provider freshness — chart issues only block the
        # affected per-row chart_status. The quote path is "active" when the
        # manager is reachable (state in {"active","stale"}) AND LEVELONE has
        # active heartbeats for at least one configured contract.
        quote_path_active = (
            manager_state in {"active", "stale"} and bool(levelone_active_contracts)
        )
        if stream_active or quote_path_active:
            cache_snapshot = _cache_snapshot_for_active_quote_path(
                cache_snapshot,
                levelone_active_contracts=levelone_active_contracts,
                chart_active_contracts=chart_active_contracts,
            )
            manager_blocking_reasons = _filter_quote_path_irrelevant_reasons(
                manager_blocking_reasons,
                levelone_active_contracts=levelone_active_contracts,
                chart_active_contracts=chart_active_contracts,
                quote_path_active=quote_path_active,
            )

    observable_snapshot = build_live_observable_snapshot_v2(cache_snapshot)
    provider_status = observable_snapshot.provider_status
    return _RuntimeReadinessContext(
        cache_snapshot=cache_snapshot,
        observable_snapshot=observable_snapshot,
        source_type=source_type,
        provider_status=provider_status,
        generated_at=observable_snapshot.generated_at,
        snapshot_ready=_observable_quote_cache_ready(observable_snapshot),
        manager_state=manager_state,
        manager_blocking_reasons=manager_blocking_reasons,
        excluded_or_unsupported_contracts=_excluded_or_unsupported_runtime_contracts(cache_snapshot),
        stream_active=stream_active,
        stream_active_contracts=stream_active_contracts,
        levelone_active_contracts=levelone_active_contracts,
        chart_active_contracts=chart_active_contracts,
        quote_path_active=quote_path_active,
    )


def _stream_active_contracts(snapshot: StreamManagerSnapshot) -> tuple[str, ...]:
    status = snapshot.contract_heartbeat_status or {}
    return tuple(
        contract
        for contract in snapshot.config.contracts_requested
        if isinstance(status.get(contract), Mapping)
        and str(status[contract].get("status") or "").strip().lower() == "active"
    )


def _service_active_contracts(
    snapshot: StreamManagerSnapshot, service: str
) -> tuple[str, ...]:
    """Per-service active contracts derived from contract_service_status.

    A contract counts as service-active when the manager has recorded
    ``status == "active"`` for the (contract, service) pair within the
    heartbeat threshold — i.e., real ingest progress, not just a connection
    heartbeat. Returns an empty tuple when the manager has not populated
    contract_service_status (no service-level visibility).
    """

    status = snapshot.contract_service_status or {}
    requested_service = service.strip().upper()
    active: list[str] = []
    for contract in snapshot.config.contracts_requested:
        per_contract = status.get(contract)
        if not isinstance(per_contract, Mapping):
            continue
        entry = per_contract.get(requested_service)
        if not isinstance(entry, Mapping):
            continue
        if str(entry.get("status") or "").strip().lower() == "active":
            active.append(contract)
    return tuple(active)


def _is_chart_only_reason(reason: str) -> bool:
    text = reason.strip()
    if not text:
        return False
    if text.startswith("contract_service_stale:") or text.startswith(
        "contract_service_no_data:"
    ):
        return text.upper().endswith(":CHART_FUTURES")
    if text.startswith("chart_bar_stale:") or text.startswith("chart_bars_missing:"):
        return True
    return False


def _filter_quote_path_irrelevant_reasons(
    reasons: tuple[str, ...],
    *,
    levelone_active_contracts: tuple[str, ...],
    chart_active_contracts: tuple[str, ...],  # noqa: ARG001 - reserved for future symmetry
    quote_path_active: bool,
) -> tuple[str, ...]:
    """Filter blocking reasons that should not poison provider/quote identity.

    Always drops historical transient inactive reasons. When the quote path
    is active, also drops chart-only reasons (e.g.
    ``contract_service_stale:CONTRACT:CHART_FUTURES``) and per-contract
    aggregate stale reasons (``contract_stale:CONTRACT`` /
    ``contract_no_data:CONTRACT``) for contracts whose LEVELONE service is
    still active — those are chart-side noise, not quote-path failures.
    Chart-side issues remain visible per-row via the observable snapshot's
    ``chart_bar.blocking_reasons``.
    """

    levelone_set = {contract.strip().upper() for contract in levelone_active_contracts}
    filtered: list[str] = []
    for reason in reasons:
        if reason in _TRANSIENT_INACTIVE_REASONS:
            continue
        if not quote_path_active:
            filtered.append(reason)
            continue
        if _is_chart_only_reason(reason):
            continue
        # ``contract_stale:CONTRACT`` / ``contract_no_data:CONTRACT`` are
        # global per-contract heartbeat aggregates that flip when ANY service
        # is missing/stale. If LEVELONE is still flowing for the contract,
        # the quote path is fine — drop the global aggregate so it does not
        # poison provider/quote identity.
        if reason.startswith("contract_stale:") or reason.startswith("contract_no_data:"):
            _, _, contract_part = reason.partition(":")
            if contract_part.strip().upper() in levelone_set:
                continue
        filtered.append(reason)
    return tuple(filtered)


def _cache_snapshot_for_active_quote_path(
    cache: StreamCacheSnapshot,
    *,
    levelone_active_contracts: tuple[str, ...],
    chart_active_contracts: tuple[str, ...],
) -> StreamCacheSnapshot:
    """Return a cache snapshot view that reflects the currently active quote path.

    When the quote path (LEVELONE_FUTURES) is active, residual cache state
    from earlier transient blocks (a ``provider_status`` of "blocked" set
    before subscription completed, an inherited "stale" set by a per-service
    chart watchdog, or a ``stream_not_active`` / chart-only blocking reason)
    must not be reported as the live identity. Per-record freshness and
    ``stale_symbols`` remain so quote/chart freshness stay independently
    fail-closed at the per-contract level.
    """

    filtered_reasons = _filter_quote_path_irrelevant_reasons(
        cache.blocking_reasons,
        levelone_active_contracts=levelone_active_contracts,
        chart_active_contracts=chart_active_contracts,
        quote_path_active=True,
    )
    provider_status = cache.provider_status
    if provider_status in {"blocked", "disconnected", "shutdown", "error", "stale"}:
        provider_status = "active"
    # Strip per-symbol stale entries that come solely from chart-only
    # records. Quote-side stale per-symbol entries remain (they reflect
    # actual stale LEVELONE data and still belong on the per-row view).
    filtered_stale_symbols = _filter_chart_only_stale_symbols(cache)
    if (
        filtered_reasons == cache.blocking_reasons
        and provider_status == cache.provider_status
        and filtered_stale_symbols == cache.stale_symbols
    ):
        return cache
    return StreamCacheSnapshot(
        generated_at=cache.generated_at,
        provider=cache.provider,
        provider_status=provider_status,
        cache_max_age_seconds=cache.cache_max_age_seconds,
        records=cache.records,
        blocking_reasons=filtered_reasons,
        stale_symbols=filtered_stale_symbols,
    )


def _filter_chart_only_stale_symbols(cache: StreamCacheSnapshot) -> tuple[str, ...]:
    """Remove symbols whose stale entry is ONLY from a stale chart record.

    A symbol with both a stale CHART record and a fresh LEVELONE record
    should not be reported as a stale_symbol because its quote path is
    actually fresh; the chart-side staleness is captured per-row via the
    observable snapshot's chart_bar.blocking_reasons.
    """

    stale = list(cache.stale_symbols)
    if not stale:
        return cache.stale_symbols
    fresh_quote_symbols: set[str] = set()
    stale_chart_symbols: set[str] = set()
    for record in cache.records:
        symbol = str(getattr(record, "symbol", "")).strip().upper()
        if not symbol:
            continue
        message_type = str(getattr(record, "message_type", "")).strip().lower()
        is_fresh = bool(getattr(record, "fresh", False))
        if message_type == "quote" and is_fresh:
            fresh_quote_symbols.add(symbol)
        if message_type == "bar" and not is_fresh:
            stale_chart_symbols.add(symbol)
    chart_only_stale = stale_chart_symbols & fresh_quote_symbols
    if not chart_only_stale:
        return cache.stale_symbols
    return tuple(symbol for symbol in stale if symbol not in chart_only_stale)


# Backward-compatible alias retained for any external callers that imported
# the previous helper name. Internal callers go through
# ``_cache_snapshot_for_active_quote_path``.
def _cache_snapshot_for_active_stream(cache: StreamCacheSnapshot) -> StreamCacheSnapshot:
    return _cache_snapshot_for_active_quote_path(
        cache,
        levelone_active_contracts=(),
        chart_active_contracts=(),
    )


def _build_row(
    profile: RuntimeProfile,
    *,
    active_profile_id: str | None,
    runtime_context: _RuntimeReadinessContext,
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

    runtime_readiness = _runtime_contract_readiness(profile.contract, runtime_context)
    runtime_bound = runtime_context.cache_snapshot is not None
    if runtime_bound:
        market_data_status = runtime_readiness.market_data_status
        missing_live_fields = runtime_readiness.missing_live_fields
        # When the live runtime is fail-closed (no records, missing snapshot,
        # error, disabled, disconnected), the lifecycle reasons must precede
        # the underlying fixture/trigger reasons so the cockpit's first
        # surfaced reason describes WHY the runtime cache is unusable, not
        # the residual fixture trigger state.
        if runtime_readiness.state != LIVE_RUNTIME_CONNECTED:
            blocked_reasons = _dedupe(
                runtime_context.global_blocking_reasons
                + runtime_readiness.blocked_reasons
                + blocked_reasons
            )
        else:
            blocked_reasons = _dedupe(
                blocked_reasons
                + runtime_readiness.blocked_reasons
                + runtime_context.global_blocking_reasons
            )
    else:
        market_data_status = _market_data_status(shell)
        missing_live_fields = _missing_live_fields(shell, market_data_status=market_data_status)

    query_ready = _query_ready(shell)
    runtime_query_blockers: tuple[str, ...] = ()
    if runtime_bound:
        if runtime_readiness.state != LIVE_RUNTIME_CONNECTED or runtime_context.global_blocking_reasons:
            query_ready = False
        elif runtime_readiness.chart_status != "chart available":
            query_ready = False
            runtime_query_blockers = runtime_readiness.chart_blocking_reasons or (
                f"chart_bars_missing:{profile.contract}",
            )
    query_gate_status = _query_gate_status(shell)
    if runtime_bound and not query_ready:
        query_gate_status = "BLOCKED"
    query_blocked_reasons = _dedupe(blocked_reasons + runtime_query_blockers)
    return FiveContractReadinessRow(
        contract=profile.contract,
        contract_label=runtime_readiness.label,
        runtime_profile_id=profile.profile_id,
        readiness_source=(
            READINESS_SOURCE_RUNTIME_CACHE
            if runtime_bound
            else READINESS_SOURCE_FIXTURE_PRESERVED
        ),
        final_target_support_status="final_supported",
        selectable_final_target=True,
        preflight_status=preflight_status,
        startup_readiness_state=startup_readiness_state,
        operator_ready=operator_ready,
        non_live_fixture_usable=(
            (not runtime_bound) and operator_ready and market_data_status == "Market data unavailable"
        ),
        market_data_status=market_data_status,
        live_data_available=runtime_readiness.live_data_available if runtime_bound else market_data_status != "Market data unavailable",
        quote_status=runtime_readiness.quote_status if runtime_bound else "fixture quote unavailable",
        chart_status=runtime_readiness.chart_status if runtime_bound else "fixture chart unavailable",
        quote_freshness_state=runtime_readiness.quote_freshness_state if runtime_bound else "fixture",
        chart_freshness_state=runtime_readiness.chart_freshness_state if runtime_bound else "fixture",
        missing_live_fields=missing_live_fields,
        live_runtime_readiness_state=runtime_readiness.state,
        operator_runtime_state=_operator_runtime_state(runtime_bound, runtime_readiness.state),
        runtime_cache_status=runtime_readiness.cache_status,
        runtime_cache_bound=runtime_bound,
        runtime_cache_blocked_reasons=runtime_readiness.blocked_reasons,
        chart_blocking_reasons=runtime_readiness.chart_blocking_reasons,
        runtime_provider_status=runtime_readiness.provider_status,
        runtime_symbol=runtime_readiness.symbol,
        trigger_state_summary=_trigger_state_summary(shell),
        trigger_valid_count=_trigger_count(shell, field="is_valid"),
        trigger_true_count=_trigger_count(shell, field="is_true"),
        query_gate_status=query_gate_status,
        query_ready=query_ready,
        query_not_ready_reasons=() if query_ready else query_blocked_reasons,
        primary_blocked_reasons=query_blocked_reasons,
        evidence_replay_status=_audit_replay_status(shell),
        run_history_status=_run_history_status(shell),
        manual_only_boundary=MANUAL_ONLY_BOUNDARY_STATEMENT,
        preserved_engine_authority=PRESERVED_ENGINE_AUTHORITY_STATEMENT,
    )


def _runtime_contract_readiness(
    contract: str,
    runtime_context: _RuntimeReadinessContext,
) -> _RuntimeContractReadiness:
    if runtime_context.cache_snapshot is None or runtime_context.observable_snapshot is None:
        return _RuntimeContractReadiness(
            state=LIVE_RUNTIME_NOT_REQUESTED,
            cache_status=LIVE_RUNTIME_CACHE_STATUS,
            market_data_status="Live runtime not requested",
            live_data_available=False,
            quote_status="quote missing",
            chart_status="chart missing",
            quote_freshness_state="missing",
            chart_freshness_state="missing",
            missing_live_fields=("live_runtime_cache",),
            blocked_reasons=LIVE_RUNTIME_NOT_REQUESTED_BLOCKERS,
            chart_blocking_reasons=("chart_bars_missing:" + contract,),
            provider_status=None,
            symbol=None,
            label=_contract_label(contract),
        )

    observable = runtime_context.observable_snapshot.contracts.get(contract)
    provider_status = runtime_context.provider_status or "disabled"
    if observable is None:
        return _RuntimeContractReadiness(
            state=LIVE_RUNTIME_MISSING_CONTRACT,
            cache_status="runtime_cache_missing_contract",
            market_data_status="Runtime cache missing contract",
            live_data_available=False,
            quote_status="quote missing",
            chart_status="chart missing",
            quote_freshness_state="missing",
            chart_freshness_state="missing",
            missing_live_fields=("runtime_cache_record",),
            blocked_reasons=(f"missing_cache_record:{contract}",),
            chart_blocking_reasons=(f"chart_bars_missing:{contract}",),
            provider_status=provider_status,
            symbol=None,
            label=_contract_label(contract),
        )

    payload = observable.to_dict()
    quality = payload.get("quality")
    quality_map = quality if isinstance(quality, Mapping) else {}
    reasons = _dedupe(tuple(str(reason) for reason in quality_map.get("blocking_reasons", ()) if str(reason).strip()))
    chart = payload.get("chart_bar")
    chart_map = chart if isinstance(chart, Mapping) else {}
    chart_reasons = _dedupe(tuple(str(reason) for reason in chart_map.get("blocking_reasons", ()) if str(reason).strip()))
    quote_status = _quote_status(quality_map, reasons)
    chart_status = _chart_status(chart_map, chart_reasons)
    quote_freshness_state = _quote_freshness_state(quote_status)
    chart_freshness_state = _chart_freshness_state(chart_status, chart_map)
    missing_fields = _missing_runtime_fields(contract, reasons)
    symbol = payload.get("symbol")
    symbol_text = str(symbol).strip().upper() if symbol is not None else None
    label = str(payload["label"]) if isinstance(payload.get("label"), str) else _contract_label(contract)

    if provider_status == "disabled":
        state = LIVE_RUNTIME_DISABLED
        status = "runtime_cache_disabled"
        market_data_status = "Runtime cache disabled"
        missing_fields = _dedupe(missing_fields + ("live_runtime_cache",))
    elif provider_status == "stale":
        state = LIVE_RUNTIME_STALE
        status = "runtime_cache_stale"
        market_data_status = "Runtime cache stale"
    elif provider_status in {"error", "disconnected"}:
        state = LIVE_RUNTIME_ERROR
        status = "runtime_cache_error"
        market_data_status = "Runtime cache error"
    elif _has_reason_prefix(reasons, f"missing_cache_record:{contract}"):
        state = LIVE_RUNTIME_MISSING_CONTRACT
        status = "runtime_cache_missing_contract"
        market_data_status = "Runtime cache missing contract"
        missing_fields = _dedupe(missing_fields + ("runtime_cache_record",))
    elif quality_map.get("required_fields_present") is not True:
        state = LIVE_RUNTIME_MISSING_REQUIRED_FIELDS
        status = "runtime_cache_missing_required_fields"
        market_data_status = "Runtime cache missing required fields"
    elif quality_map.get("fresh") is not True:
        state = LIVE_RUNTIME_STALE
        status = "runtime_cache_stale"
        market_data_status = "Runtime cache stale"
    elif quality_map.get("symbol_match") is not True:
        state = LIVE_RUNTIME_MISSING_CONTRACT
        status = "runtime_cache_symbol_mismatch"
        market_data_status = "Runtime cache symbol mismatch"
    elif reasons:
        state = LIVE_RUNTIME_ERROR
        status = "runtime_cache_blocked"
        market_data_status = "Runtime cache blocked"
    else:
        state = LIVE_RUNTIME_CONNECTED
        status = "runtime_cache_connected"
        market_data_status = "Runtime cache connected"

    live_data_available = state == LIVE_RUNTIME_CONNECTED
    if state != LIVE_RUNTIME_CONNECTED and not reasons:
        reasons = (status,)
    return _RuntimeContractReadiness(
        state=state,
        cache_status=status,
        market_data_status=market_data_status,
        live_data_available=live_data_available,
        quote_status=quote_status,
        chart_status=chart_status,
        quote_freshness_state=quote_freshness_state,
        chart_freshness_state=chart_freshness_state,
        missing_live_fields=missing_fields,
        blocked_reasons=() if live_data_available else reasons,
        chart_blocking_reasons=chart_reasons,
        provider_status=provider_status,
        symbol=symbol_text,
        label=label,
    )


def _observable_quote_cache_ready(observable_snapshot: LiveObservableSnapshotV2) -> bool:
    if observable_snapshot.provider_status != "connected":
        return False
    quote_ready_contracts = observable_snapshot.data_quality.get("quote_ready_contracts")
    if isinstance(quote_ready_contracts, list):
        return set(quote_ready_contracts) == set(final_target_contracts())
    return observable_snapshot.ready


def _summary_runtime_status(
    rows: tuple[FiveContractReadinessRow, ...],
    runtime_context: _RuntimeReadinessContext,
) -> RuntimeReadinessState:
    if runtime_context.cache_snapshot is None:
        return LIVE_RUNTIME_NOT_REQUESTED
    if runtime_context.excluded_or_unsupported_contracts:
        return LIVE_RUNTIME_EXCLUDED_CONTRACT_BLOCKED
    states = tuple(row.live_runtime_readiness_state for row in rows)
    for state in (
        LIVE_RUNTIME_DISABLED,
        LIVE_RUNTIME_ERROR,
        LIVE_RUNTIME_STALE,
        LIVE_RUNTIME_MISSING_CONTRACT,
        LIVE_RUNTIME_MISSING_REQUIRED_FIELDS,
    ):
        if state in states:
            return state
    return LIVE_RUNTIME_CONNECTED if all(state == LIVE_RUNTIME_CONNECTED for state in states) else LIVE_RUNTIME_ERROR


def _summary_runtime_blockers(
    rows: tuple[FiveContractReadinessRow, ...],
    runtime_context: _RuntimeReadinessContext,
    runtime_status: RuntimeReadinessState,
) -> tuple[str, ...]:
    if runtime_context.cache_snapshot is None:
        return LIVE_RUNTIME_NOT_REQUESTED_BLOCKERS
    blockers = runtime_context.global_blocking_reasons + tuple(
        f"{row.contract}:{reason}"
        for row in rows
        for reason in row.runtime_cache_blocked_reasons
    )
    if runtime_status == LIVE_RUNTIME_CONNECTED and not blockers:
        return ()
    return _dedupe(blockers or (runtime_status.lower(),))


def _operator_runtime_state(runtime_bound: bool, readiness_state: RuntimeReadinessState) -> str:
    if not runtime_bound:
        return "fixture"
    if readiness_state == LIVE_RUNTIME_CONNECTED:
        return "live-ready"
    if readiness_state in {LIVE_RUNTIME_NOT_REQUESTED, LIVE_RUNTIME_DISABLED}:
        return "live-disabled"
    if readiness_state == LIVE_RUNTIME_STALE:
        return "live-error"
    return "live-error"


def _limitations_for_summary(summary: FiveContractReadinessSummary) -> tuple[str, ...]:
    if summary.readiness_source == READINESS_SOURCE_RUNTIME_CACHE:
        return (
            "runtime_cache_derived_readiness_only",
            "runtime_cache_cannot_authorize_trades",
            "real_schwab_readiness_requires_explicit_operator_live_runtime",
        )
    return (
        "non_live_fixture_summary_only",
        "live_runtime_snapshot_not_requested",
        "real_schwab_readiness_requires_explicit_operator_live_runtime",
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


def _excluded_or_unsupported_runtime_contracts(cache_snapshot: StreamCacheSnapshot) -> tuple[str, ...]:
    contracts: list[str] = []
    for record in cache_snapshot.records:
        contract = str(getattr(record, "contract", "")).strip().upper()
        if not contract or is_final_target_contract(contract):
            continue
        if contract not in contracts:
            contracts.append(contract)
    return tuple(contracts)


def _missing_runtime_fields(contract: str, reasons: tuple[str, ...]) -> tuple[str, ...]:
    prefix = f"missing_required_fields:{contract}:"
    fields: list[str] = []
    for reason in reasons:
        if not reason.startswith(prefix):
            continue
        fields.extend(field.strip() for field in reason[len(prefix) :].split(",") if field.strip())
    return _dedupe(tuple(fields))


def _has_reason_prefix(reasons: tuple[str, ...], prefix: str) -> bool:
    return any(reason.startswith(prefix) for reason in reasons)


def _quote_status(quality: Mapping[str, object], reasons: tuple[str, ...]) -> str:
    if not quality:
        return "quote missing"
    if _has_reason_prefix(reasons, "missing_cache_record:"):
        return "quote missing"
    if quality.get("fresh") is not True:
        return "quote stale"
    if quality.get("required_fields_present") is not True:
        return "quote missing"
    if reasons:
        return "quote blocked"
    return "quote available"


def _chart_status(chart: Mapping[str, object], reasons: tuple[str, ...]) -> str:
    if not chart:
        return "chart missing"
    if _has_reason_prefix(reasons, "malformed_chart_event:") or _has_reason_prefix(
        reasons,
        "chart_bar_missing_required_fields:",
    ):
        return "malformed chart event"
    state = str(chart.get("state") or "unavailable").strip().lower()
    if chart.get("available") is True and chart.get("fresh") is True:
        return "chart available"
    if state == "unavailable":
        return "chart missing"
    if state == "stale" or chart.get("fresh") is False:
        return "chart stale"
    if state == "building" or chart.get("building") is True:
        return "chart building"
    if state == "blocked":
        return "chart blocked"
    return "chart missing"


def _quote_freshness_state(quote_status: str) -> str:
    if quote_status == "quote available":
        return "fresh"
    if quote_status == "quote stale":
        return "stale"
    if quote_status == "quote missing":
        return "missing"
    return "blocked"


def _chart_freshness_state(chart_status: str, chart: Mapping[str, object]) -> str:
    if chart_status == "chart available":
        return "fresh"
    if chart_status == "chart stale":
        return "stale"
    if chart_status in {"chart missing", "chart building"}:
        return "missing"
    if chart.get("fresh") is True:
        return "fresh_blocked"
    return "blocked"


def _contract_label(contract: str) -> str | None:
    return "Micro Gold" if contract == "MGC" else None


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
