from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final

from ntb_marimo_console.contract_universe import (
    is_excluded_final_target_contract,
    is_final_target_contract,
    is_never_supported_contract,
    normalize_contract_symbol,
)
from ntb_marimo_console.live_observables.quality import normalize_provider_status
from ntb_marimo_console.live_observables.schema_v2 import LiveObservableSnapshotV2
from ntb_marimo_console.market_data.chart_bars import ContractBarReadiness
from ntb_marimo_console.market_data.stream_events import redact_sensitive_text
from ntb_marimo_console.trigger_state import TriggerState, TriggerStateResult


PIPELINE_QUERY_GATE_SCHEMA: Final[str] = "pipeline_query_gate_v1"
REQUIRED_PIPELINE_QUERY_GATE_CONDITIONS: Final[tuple[str, ...]] = (
    "contract_final_supported",
    "runtime_profile_preflight_passed",
    "watchman_validator_ready",
    "live_snapshot_fresh",
    "quote_fresh",
    "bars_fresh_and_available",
    "required_trigger_fields_present",
    "trigger_state_query_ready",
    "session_valid",
    "event_lockout_inactive",
    "provider_ready",
    "stream_ready",
)
QUERY_READY_TRIGGER_ENABLED_REASONS: Final[tuple[str, ...]] = REQUIRED_PIPELINE_QUERY_GATE_CONDITIONS
_FIXTURE_READY_STATUSES: Final[tuple[str, ...]] = ("fixture", "fixture_accepted", "accepted_fixture")
_READY_STREAM_STATUSES: Final[tuple[str, ...]] = ("active", "connected")


class PipelineQueryGateStatus(StrEnum):
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"


@dataclass(frozen=True)
class PipelineQueryGateRequest:
    contract: str
    trigger_state: TriggerStateResult | TriggerState | str
    profile_id: str | None = None
    profile_exists: bool = True
    profile_preflight_passed: bool = False
    watchman_validator_status: str | None = None
    live_snapshot: Mapping[str, Any] | LiveObservableSnapshotV2 | None = None
    live_snapshot_fresh: bool | None = None
    quote_fresh: bool | None = None
    bars_available: bool = True
    bars_fresh: bool | None = None
    bar_readiness: ContractBarReadiness | object | None = None
    required_trigger_fields_present: bool | None = None
    unsupported_live_field_dependencies: tuple[str, ...] = ()
    support_matrix_final_supported: bool | None = None
    provider_status: str | None = None
    stream_status: str | None = None
    session_valid: bool = False
    event_lockout_active: bool = False
    fixture_mode_accepted: bool = False
    evaluated_at: str | None = None
    trigger_state_from_real_producer: bool = False


@dataclass(frozen=True)
class PipelineQueryGateResult:
    contract: str
    enabled: bool
    status: PipelineQueryGateStatus
    enabled_reasons: tuple[str, ...]
    disabled_reasons: tuple[str, ...]
    blocking_reasons: tuple[str, ...]
    required_conditions: tuple[str, ...]
    missing_conditions: tuple[str, ...]
    trigger_state: str
    setup_id: str | None
    trigger_id: str | None
    profile_id: str | None
    provider_status: str
    stream_status: str
    session_valid: bool
    event_lockout_active: bool
    evaluated_at: str | None
    trigger_state_from_real_producer: bool
    pipeline_query_authorized: bool = field(init=False)
    schema: str = PIPELINE_QUERY_GATE_SCHEMA
    decision_authority: str = "preserved_engine_only"
    query_scope: str = "operator_initiated_preserved_pipeline_query"
    pipeline_result_source: str = "engine_derived"

    def __post_init__(self) -> None:
        object.__setattr__(self, "pipeline_query_authorized", self.enabled)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "contract": self.contract,
            "enabled": self.enabled,
            "status": self.status.value,
            "enabled_reasons": list(self.enabled_reasons),
            "disabled_reasons": list(self.disabled_reasons),
            "blocking_reasons": list(self.blocking_reasons),
            "required_conditions": list(self.required_conditions),
            "missing_conditions": list(self.missing_conditions),
            "trigger_state": self.trigger_state,
            "setup_id": self.setup_id,
            "trigger_id": self.trigger_id,
            "profile_id": self.profile_id,
            "provider_status": self.provider_status,
            "stream_status": self.stream_status,
            "session_valid": self.session_valid,
            "event_lockout_active": self.event_lockout_active,
            "evaluated_at": self.evaluated_at,
            "trigger_state_from_real_producer": self.trigger_state_from_real_producer,
            "pipeline_query_authorized": self.pipeline_query_authorized,
            "decision_authority": self.decision_authority,
            "query_scope": self.query_scope,
            "pipeline_result_source": self.pipeline_result_source,
        }


def evaluate_pipeline_query_gate(request: PipelineQueryGateRequest) -> PipelineQueryGateResult:
    contract = normalize_contract_symbol(request.contract)
    trigger_state, setup_id, trigger_id, trigger_missing, trigger_blocking = _trigger_state_parts(request.trigger_state)
    provider_status = _provider_status(request, contract)
    stream_status = _stream_status(request)
    evaluated_at = request.evaluated_at or _snapshot_generated_at(request.live_snapshot)

    passed: list[str] = []
    missing: list[str] = []
    disabled: list[str] = []

    _check_contract(contract, request.support_matrix_final_supported, passed, missing, disabled)
    _check_profile(request, passed, missing, disabled)
    _check_watchman(request.watchman_validator_status, passed, missing, disabled)
    _check_live_snapshot(request, contract, passed, missing, disabled)
    _check_bars(request, contract, passed, missing, disabled)
    _check_trigger_fields(request, trigger_missing, passed, missing, disabled)
    _check_trigger_state(trigger_state, trigger_blocking, passed, missing, disabled)
    _check_trigger_state_provenance(request, trigger_state, missing, disabled)
    _check_session(request, passed, missing, disabled)
    _check_provider(provider_status, request.fixture_mode_accepted, passed, missing, disabled)
    _check_stream(stream_status, request.fixture_mode_accepted, passed, missing, disabled)

    blocking_reasons = _dedupe(tuple(disabled))
    enabled = not blocking_reasons and tuple(passed) == REQUIRED_PIPELINE_QUERY_GATE_CONDITIONS
    status = PipelineQueryGateStatus.ENABLED if enabled else PipelineQueryGateStatus.DISABLED
    return PipelineQueryGateResult(
        contract=contract,
        enabled=enabled,
        status=status,
        enabled_reasons=QUERY_READY_TRIGGER_ENABLED_REASONS if enabled else _dedupe(tuple(passed)),
        disabled_reasons=blocking_reasons,
        blocking_reasons=blocking_reasons,
        required_conditions=REQUIRED_PIPELINE_QUERY_GATE_CONDITIONS,
        missing_conditions=_dedupe(tuple(missing)),
        trigger_state=trigger_state,
        setup_id=setup_id,
        trigger_id=trigger_id,
        profile_id=request.profile_id,
        provider_status=provider_status,
        stream_status=stream_status,
        session_valid=request.session_valid,
        event_lockout_active=request.event_lockout_active,
        evaluated_at=evaluated_at,
        trigger_state_from_real_producer=request.trigger_state_from_real_producer,
    )


def _check_contract(
    contract: str,
    support_matrix_final_supported: bool | None,
    passed: list[str],
    missing: list[str],
    disabled: list[str],
) -> None:
    if is_never_supported_contract(contract):
        missing.append("contract_final_supported")
        disabled.append(f"never_supported_contract:{contract}")
        if is_excluded_final_target_contract(contract):
            disabled.append(f"excluded_contract:{contract}")
        return
    if is_excluded_final_target_contract(contract):
        missing.append("contract_final_supported")
        disabled.append(f"excluded_contract:{contract}")
        return
    if not is_final_target_contract(contract):
        missing.append("contract_final_supported")
        disabled.append(f"unsupported_contract:{contract}")
        return
    if support_matrix_final_supported is False:
        missing.append("contract_final_supported")
        disabled.append(f"support_matrix_mismatch:{contract}")
        return
    passed.append("contract_final_supported")


def _check_profile(
    request: PipelineQueryGateRequest,
    passed: list[str],
    missing: list[str],
    disabled: list[str],
) -> None:
    if not request.profile_exists:
        missing.append("runtime_profile_preflight_passed")
        disabled.append("runtime_profile_unavailable")
        return
    if not request.profile_preflight_passed:
        missing.append("runtime_profile_preflight_passed")
        disabled.append("profile_preflight_failed")
        return
    passed.append("runtime_profile_preflight_passed")


def _check_watchman(
    status: str | None,
    passed: list[str],
    missing: list[str],
    disabled: list[str],
) -> None:
    normalized = _normalized_status(status)
    if normalized != "READY":
        missing.append("watchman_validator_ready")
        disabled.append(f"watchman_validator_not_ready:{normalized or 'UNAVAILABLE'}")
        return
    passed.append("watchman_validator_ready")


def _check_live_snapshot(
    request: PipelineQueryGateRequest,
    contract: str,
    passed: list[str],
    missing: list[str],
    disabled: list[str],
) -> None:
    snapshot_fresh, quote_fresh, required_fields_present, quality_reasons = _live_snapshot_quality(
        request.live_snapshot,
        contract,
    )
    snapshot_fresh = request.live_snapshot_fresh if request.live_snapshot_fresh is not None else snapshot_fresh
    quote_fresh = request.quote_fresh if request.quote_fresh is not None else quote_fresh

    if request.live_snapshot is None:
        missing.append("live_snapshot_fresh")
        disabled.append("live_snapshot_unavailable")
    elif snapshot_fresh is not True:
        missing.append("live_snapshot_fresh")
        disabled.append("live_snapshot_stale")
    else:
        passed.append("live_snapshot_fresh")

    if quote_fresh is not True:
        missing.append("quote_fresh")
        disabled.append("quote_stale")
    else:
        passed.append("quote_fresh")

    if request.required_trigger_fields_present is None and required_fields_present is False:
        missing.append("required_trigger_fields_present")
        disabled.append("live_observable_required_fields_missing")

    disabled.extend(quality_reasons)


def _check_bars(
    request: PipelineQueryGateRequest,
    contract: str,
    passed: list[str],
    missing: list[str],
    disabled: list[str],
) -> None:
    if request.bar_readiness is not None:
        _check_bar_readiness(request.bar_readiness, passed, missing, disabled)
        return
    snapshot_bar_readiness = _bar_readiness_from_live_snapshot(request.live_snapshot, contract)
    if snapshot_bar_readiness is not None:
        _check_serialized_bar_readiness(snapshot_bar_readiness, passed, missing, disabled)
        return
    if not request.bars_available:
        missing.append("bars_fresh_and_available")
        disabled.append("bars_missing")
        return
    if request.bars_fresh is not True:
        missing.append("bars_fresh_and_available")
        disabled.append("bars_stale")
        return
    passed.append("bars_fresh_and_available")


def _check_bar_readiness(
    bar_readiness: ContractBarReadiness | object,
    passed: list[str],
    missing: list[str],
    disabled: list[str],
) -> None:
    if not isinstance(bar_readiness, ContractBarReadiness):
        missing.append("bars_fresh_and_available")
        disabled.append("bar_readiness_provenance_not_verified")
        return
    reasons = tuple(_safe_reason(reason) for reason in bar_readiness.blocking_reasons)
    if not bar_readiness.completed_one_minute_available or not bar_readiness.completed_five_minute_available:
        missing.append("bars_fresh_and_available")
        disabled.append("bars_missing")
        disabled.extend(reasons)
        return
    if not bar_readiness.fresh or bar_readiness.state == "stale":
        missing.append("bars_fresh_and_available")
        disabled.append("bars_stale")
        disabled.extend(reasons)
        return
    if bar_readiness.building or bar_readiness.state != "available":
        missing.append("bars_fresh_and_available")
        disabled.append("bars_partial_or_blocked")
        disabled.extend(reasons)
        return
    passed.append("bars_fresh_and_available")


def _check_serialized_bar_readiness(
    bar_readiness: Mapping[str, Any],
    passed: list[str],
    missing: list[str],
    disabled: list[str],
) -> None:
    reasons = _string_items(bar_readiness.get("blocking_reasons"))
    one_minute = bar_readiness.get("completed_one_minute_available") is True
    five_minute = bar_readiness.get("completed_five_minute_available") is True
    fresh = bar_readiness.get("fresh") is True
    available = bar_readiness.get("available") is True
    state = str(bar_readiness.get("state") or "unavailable").strip().lower()
    if not one_minute or not five_minute:
        missing.append("bars_fresh_and_available")
        disabled.append("bars_missing")
        disabled.extend(reasons)
        return
    if not fresh or state == "stale":
        missing.append("bars_fresh_and_available")
        disabled.append("bars_stale")
        disabled.extend(reasons)
        return
    if not available or state != "available":
        missing.append("bars_fresh_and_available")
        disabled.append("bars_partial_or_blocked")
        disabled.extend(reasons)
        return
    passed.append("bars_fresh_and_available")


def _check_trigger_fields(
    request: PipelineQueryGateRequest,
    trigger_missing: tuple[str, ...],
    passed: list[str],
    missing: list[str],
    disabled: list[str],
) -> None:
    unsupported = tuple(_safe_reason(f"unsupported_live_field_dependency:{path}") for path in request.unsupported_live_field_dependencies)
    if unsupported:
        missing.append("required_trigger_fields_present")
        disabled.extend(unsupported)
        disabled.append("unsupported_live_field_dependency")
        return
    if request.required_trigger_fields_present is False or trigger_missing:
        missing.append("required_trigger_fields_present")
        disabled.append("missing_required_trigger_fields")
        disabled.extend(f"missing_trigger_field:{_safe_field_path(path)}" for path in trigger_missing)
        return
    passed.append("required_trigger_fields_present")


def _check_trigger_state(
    trigger_state: str,
    trigger_blocking: tuple[str, ...],
    passed: list[str],
    missing: list[str],
    disabled: list[str],
) -> None:
    if trigger_state != TriggerState.QUERY_READY.value:
        missing.append("trigger_state_query_ready")
        disabled.append(f"trigger_state_not_query_ready:{trigger_state}")
        mapped = _trigger_state_reason(trigger_state)
        if mapped is not None:
            disabled.append(mapped)
        disabled.extend(trigger_blocking)
        return
    passed.append("trigger_state_query_ready")


def _check_trigger_state_provenance(
    request: PipelineQueryGateRequest,
    trigger_state: str,
    missing: list[str],
    disabled: list[str],
) -> None:
    if trigger_state != TriggerState.QUERY_READY.value:
        return
    if isinstance(request.trigger_state, TriggerStateResult) and request.trigger_state_from_real_producer:
        return
    missing.append("trigger_state_query_ready")
    disabled.append("trigger_state_not_from_real_producer")


def _check_session(
    request: PipelineQueryGateRequest,
    passed: list[str],
    missing: list[str],
    disabled: list[str],
) -> None:
    if not request.session_valid:
        missing.append("session_valid")
        disabled.append("session_invalid")
    else:
        passed.append("session_valid")
    if request.event_lockout_active:
        missing.append("event_lockout_inactive")
        disabled.append("event_lockout_active")
    else:
        passed.append("event_lockout_inactive")


def _check_provider(
    provider_status: str,
    fixture_mode_accepted: bool,
    passed: list[str],
    missing: list[str],
    disabled: list[str],
) -> None:
    normalized = normalize_provider_status(provider_status)
    if normalized == "connected" or _fixture_ready(provider_status, fixture_mode_accepted):
        passed.append("provider_ready")
        return
    missing.append("provider_ready")
    disabled.append(f"provider_status_blocked:{normalized}")


def _check_stream(
    stream_status: str,
    fixture_mode_accepted: bool,
    passed: list[str],
    missing: list[str],
    disabled: list[str],
) -> None:
    normalized = stream_status.strip().lower() or "disabled"
    if normalized in _READY_STREAM_STATUSES or _fixture_ready(stream_status, fixture_mode_accepted):
        passed.append("stream_ready")
        return
    missing.append("stream_ready")
    disabled.append(f"stream_status_blocked:{normalized}")


def _trigger_state_parts(value: TriggerStateResult | TriggerState | str) -> tuple[str, str | None, str | None, tuple[str, ...], tuple[str, ...]]:
    if isinstance(value, TriggerStateResult):
        return (
            value.state.value,
            value.setup_id,
            value.trigger_id,
            tuple(_safe_field_path(item) for item in value.missing_fields),
            tuple(_safe_reason(item) for item in value.blocking_reasons + value.invalid_reasons),
        )
    if isinstance(value, TriggerState):
        return value.value, None, None, (), ()
    state = str(value).strip().upper() or TriggerState.UNAVAILABLE.value
    return state, None, None, (), ()


def _live_snapshot_quality(
    live_snapshot: Mapping[str, Any] | LiveObservableSnapshotV2 | None,
    contract: str,
) -> tuple[bool | None, bool | None, bool | None, tuple[str, ...]]:
    if live_snapshot is None:
        return False, False, False, ()
    if isinstance(live_snapshot, LiveObservableSnapshotV2):
        observable = live_snapshot.contracts.get(contract)
        if observable is None:
            reason = _safe_reason(f"missing_contract_observable:{contract}")
            return live_snapshot.ready, False, False, (reason,)
        return (
            live_snapshot.ready and observable.quality.fresh,
            observable.quality.fresh,
            observable.quality.required_fields_present,
            tuple(
                _safe_reason(reason)
                for reason in observable.quality.blocking_reasons
                + observable.quality.dependency_blocking_reasons
            ),
        )
    generated_ready = _bool_or_none(_resolve_path(live_snapshot, "data_quality.ready"))
    contracts = live_snapshot.get("contracts")
    observable = contracts.get(contract) if isinstance(contracts, Mapping) else None
    if isinstance(observable, Mapping):
        quality = observable.get("quality")
        quality_mapping = quality if isinstance(quality, Mapping) else {}
        quote_fresh = _bool_or_none(quality_mapping.get("fresh"))
        required_fields = _bool_or_none(quality_mapping.get("required_fields_present"))
        reasons = _dedupe(
            _string_items(quality_mapping.get("blocking_reasons"))
            + _string_items(quality_mapping.get("dependency_blocking_reasons"))
        )
        return (
            (generated_ready is not False) and quote_fresh is True,
            quote_fresh,
            required_fields,
            reasons,
        )
    if "contracts" in live_snapshot:
        reason = _safe_reason(f"missing_contract_observable:{contract}")
        return generated_ready, False, False, (reason,)
    return True, True, None, ()


def _bar_readiness_from_live_snapshot(
    live_snapshot: Mapping[str, Any] | LiveObservableSnapshotV2 | None,
    contract: str,
) -> Mapping[str, Any] | None:
    if live_snapshot is None:
        return None
    if isinstance(live_snapshot, LiveObservableSnapshotV2):
        observable = live_snapshot.contracts.get(contract)
        return observable.chart_bar.to_dict() if observable is not None else None
    if live_snapshot.get("schema") != "live_observable_snapshot_v2":
        return None
    contracts = live_snapshot.get("contracts")
    observable = contracts.get(contract) if isinstance(contracts, Mapping) else None
    if not isinstance(observable, Mapping):
        return None
    chart_bar = observable.get("chart_bar")
    return chart_bar if isinstance(chart_bar, Mapping) else None


def _provider_status(request: PipelineQueryGateRequest, contract: str) -> str:
    if request.provider_status is not None:
        return _safe_reason(request.provider_status).strip().lower()
    if isinstance(request.live_snapshot, LiveObservableSnapshotV2):
        return _safe_reason(request.live_snapshot.provider_status).strip().lower()
    if isinstance(request.live_snapshot, Mapping) and request.live_snapshot.get("provider_status") is not None:
        return _safe_reason(request.live_snapshot.get("provider_status")).strip().lower()
    return "disabled" if not contract else "disabled"


def _stream_status(request: PipelineQueryGateRequest) -> str:
    if request.stream_status is not None:
        return _safe_reason(request.stream_status).strip().lower()
    return _provider_status(request, request.contract)


def _snapshot_generated_at(live_snapshot: Mapping[str, Any] | LiveObservableSnapshotV2 | None) -> str | None:
    if isinstance(live_snapshot, LiveObservableSnapshotV2):
        return live_snapshot.generated_at
    if isinstance(live_snapshot, Mapping):
        generated_at = live_snapshot.get("generated_at") or live_snapshot.get("timestamp_et")
        if isinstance(generated_at, str) and generated_at.strip():
            return generated_at
    return None


def _trigger_state_reason(trigger_state: str) -> str | None:
    return {
        TriggerState.INVALIDATED.value: "trigger_invalidated",
        TriggerState.BLOCKED.value: "trigger_blocked",
        TriggerState.UNAVAILABLE.value: "trigger_unavailable",
        TriggerState.STALE.value: "trigger_stale",
        TriggerState.LOCKOUT.value: "trigger_lockout",
        TriggerState.ERROR.value: "trigger_error",
        TriggerState.DORMANT.value: "trigger_dormant",
        TriggerState.APPROACHING.value: "trigger_approaching",
        TriggerState.TOUCHED.value: "trigger_touched",
        TriggerState.ARMED.value: "trigger_armed",
    }.get(trigger_state)


def _fixture_ready(status: str, fixture_mode_accepted: bool) -> bool:
    return fixture_mode_accepted and status.strip().lower() in _FIXTURE_READY_STATUSES


def _resolve_path(payload: Mapping[str, Any], path: str) -> object:
    current: object = payload
    for part in path.split("."):
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
    return current


def _bool_or_none(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _normalized_status(value: str | None) -> str:
    return "" if value is None else _safe_reason(value).strip().upper()


def _string_items(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(_safe_reason(item) for item in value if str(item).strip())


def _safe_reason(value: object) -> str:
    return redact_sensitive_text(value).strip()


def _safe_field_path(value: object) -> str:
    text = str(value).strip()
    if re.fullmatch(r"[A-Za-z0-9_.:-]+", text):
        return text
    return _safe_reason(text)


def _dedupe(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value).strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return tuple(result)
