from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final, Literal

from ntb_marimo_console.adapters.contracts import TriggerSpec
from ntb_marimo_console.adapters.trigger_evaluator import TriggerEvaluator
from ntb_marimo_console.adapters.trigger_specs import trigger_specs_from_brief
from ntb_marimo_console.contract_universe import (
    is_excluded_final_target_contract,
    is_final_target_contract,
    is_never_supported_contract,
    normalize_contract_symbol,
)
from ntb_marimo_console.live_observables.quality import contract_tick_size
from ntb_marimo_console.live_observables.schema_v2 import ContractObservableV2, LiveObservableSnapshotV2
from ntb_marimo_console.market_data.chart_bars import ContractBarState


TRIGGER_STATE_SCHEMA: Final[str] = "trigger_state_engine_v1"
TriggerDirection = Literal["at_or_above", "at_or_below"]


class TriggerState(StrEnum):
    UNAVAILABLE = "UNAVAILABLE"
    DORMANT = "DORMANT"
    APPROACHING = "APPROACHING"
    TOUCHED = "TOUCHED"
    ARMED = "ARMED"
    QUERY_READY = "QUERY_READY"
    INVALIDATED = "INVALIDATED"
    BLOCKED = "BLOCKED"
    LOCKOUT = "LOCKOUT"
    STALE = "STALE"
    ERROR = "ERROR"


TRIGGER_STATES: Final[tuple[TriggerState, ...]] = tuple(TriggerState)


@dataclass(frozen=True)
class TriggerLockoutState:
    active: bool = False
    reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "active": self.active,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class TriggerInvalidatorState:
    invalidator_id: str
    active: bool = False
    reason: str | None = None
    reset_condition_met: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "invalidator_id": self.invalidator_id,
            "active": self.active,
            "reason": self.reason,
            "reset_condition_met": self.reset_condition_met,
        }


@dataclass(frozen=True)
class TriggerStateRequest:
    contract: str
    trigger_spec: TriggerSpec | None
    live_snapshot: Mapping[str, Any] | LiveObservableSnapshotV2 | None
    setup_id: str | None = None
    artifact_available: bool = True
    trigger_level: float | int | None = None
    trigger_direction: TriggerDirection | None = None
    approach_threshold_ticks: int = 4
    quote_fresh: bool | None = None
    quote_blocking_reasons: tuple[str, ...] = ()
    bar_state: ContractBarState | None = None
    bar_fresh: bool | None = None
    event_lockout: TriggerLockoutState = field(default_factory=TriggerLockoutState)
    session_lockout: TriggerLockoutState = field(default_factory=TriggerLockoutState)
    invalidators: tuple[TriggerInvalidatorState, ...] = ()
    require_completed_bar_confirmation: bool = True
    last_updated: str | None = None


@dataclass(frozen=True)
class TriggerStateAuthorizations:
    pipeline_query_authorized: bool = False
    trade_authorized: bool = False
    broker_authorized: bool = False
    order_authorized: bool = False
    fill_authorized: bool = False
    account_authorized: bool = False
    pnl_authorized: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "pipeline_query_authorized": self.pipeline_query_authorized,
            "trade_authorized": self.trade_authorized,
            "broker_authorized": self.broker_authorized,
            "order_authorized": self.order_authorized,
            "fill_authorized": self.fill_authorized,
            "account_authorized": self.account_authorized,
            "pnl_authorized": self.pnl_authorized,
        }


@dataclass(frozen=True)
class TriggerStateResult:
    contract: str
    setup_id: str | None
    trigger_id: str | None
    state: TriggerState
    distance_to_trigger_ticks: float | None
    required_fields: tuple[str, ...]
    missing_fields: tuple[str, ...]
    invalid_reasons: tuple[str, ...]
    blocking_reasons: tuple[str, ...]
    last_updated: str | None
    authorizations: TriggerStateAuthorizations = field(default_factory=TriggerStateAuthorizations)
    decision_authority: str = "preserved_engine_only"
    read_model_only: bool = True
    schema: str = TRIGGER_STATE_SCHEMA
    pipeline_query_authorized: bool = field(default=False, init=False)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "contract": self.contract,
            "setup_id": self.setup_id,
            "trigger_id": self.trigger_id,
            "state": self.state.value,
            "distance_to_trigger_ticks": self.distance_to_trigger_ticks,
            "required_fields": list(self.required_fields),
            "missing_fields": list(self.missing_fields),
            "invalid_reasons": list(self.invalid_reasons),
            "blocking_reasons": list(self.blocking_reasons),
            "last_updated": self.last_updated,
            "pipeline_query_authorized": self.pipeline_query_authorized,
            "authorizations": self.authorizations.to_dict(),
            "decision_authority": self.decision_authority,
            "read_model_only": self.read_model_only,
        }


@dataclass(frozen=True)
class _SnapshotInputs:
    payload: dict[str, Any]
    quote_fresh: bool | None
    quote_blocking_reasons: tuple[str, ...]
    required_fields_present: bool | None
    quality_blocking_reasons: tuple[str, ...]
    last_updated: str | None


@dataclass(frozen=True)
class _ConfirmationFacts:
    confirmed: bool
    partial: bool
    latest_completed_five_minute_close: float | None
    completed_five_minute_close_count_at_or_beyond_level: int | None
    blocking_reasons: tuple[str, ...]


def evaluate_trigger_state(request: TriggerStateRequest) -> TriggerStateResult:
    contract = normalize_contract_symbol(request.contract)
    spec = request.trigger_spec
    required_fields = tuple(spec.required_live_field_paths if spec is not None else ())
    trigger_id = spec.id if spec is not None else None
    last_updated = request.last_updated or _last_updated_from_snapshot(request.live_snapshot, contract)

    contract_reasons = _contract_blocking_reasons(contract)
    if contract_reasons:
        return _result(
            TriggerState.BLOCKED,
            contract=contract,
            setup_id=request.setup_id,
            trigger_id=trigger_id,
            required_fields=required_fields,
            blocking_reasons=contract_reasons,
            last_updated=last_updated,
        )

    if not request.artifact_available:
        return _result(
            TriggerState.UNAVAILABLE,
            contract=contract,
            setup_id=request.setup_id,
            trigger_id=trigger_id,
            required_fields=required_fields,
            blocking_reasons=("artifact_unavailable",),
            last_updated=last_updated,
        )

    if spec is None:
        return _result(
            TriggerState.UNAVAILABLE,
            contract=contract,
            setup_id=request.setup_id,
            trigger_id=None,
            required_fields=(),
            blocking_reasons=("trigger_spec_unavailable",),
            last_updated=last_updated,
        )

    if request.live_snapshot is None:
        return _result(
            TriggerState.UNAVAILABLE,
            contract=contract,
            setup_id=request.setup_id,
            trigger_id=trigger_id,
            required_fields=required_fields,
            blocking_reasons=("live_snapshot_unavailable",),
            last_updated=last_updated,
        )

    trigger_level, trigger_direction = _trigger_level_and_direction(request, spec)
    if trigger_level is None or trigger_direction is None:
        return _result(
            TriggerState.BLOCKED,
            contract=contract,
            setup_id=request.setup_id,
            trigger_id=trigger_id,
            required_fields=required_fields,
            blocking_reasons=("trigger_level_required",),
            last_updated=last_updated,
        )

    snapshot_inputs = _snapshot_inputs(request.live_snapshot, contract)
    last_updated = request.last_updated or snapshot_inputs.last_updated or last_updated
    bar_provenance_reasons = _bar_state_provenance_reasons(request.bar_state)
    if bar_provenance_reasons:
        return _result(
            TriggerState.BLOCKED,
            contract=contract,
            setup_id=request.setup_id,
            trigger_id=trigger_id,
            required_fields=required_fields,
            blocking_reasons=bar_provenance_reasons,
            last_updated=last_updated,
        )
    payload = _payload_with_completed_bar_facts(
        snapshot_inputs.payload,
        request.bar_state,
        level=trigger_level,
        direction=trigger_direction,
    )

    quote_quality_reasons = _quote_quality_reasons(request, snapshot_inputs)
    if quote_quality_reasons:
        return _result(
            TriggerState.BLOCKED,
            contract=contract,
            setup_id=request.setup_id,
            trigger_id=trigger_id,
            required_fields=required_fields,
            blocking_reasons=quote_quality_reasons,
            last_updated=last_updated,
        )

    quote_stale_reasons = _quote_stale_reasons(request, snapshot_inputs)
    if quote_stale_reasons:
        return _result(
            TriggerState.STALE,
            contract=contract,
            setup_id=request.setup_id,
            trigger_id=trigger_id,
            required_fields=required_fields,
            blocking_reasons=quote_stale_reasons,
            last_updated=last_updated,
        )

    missing_fields = _missing_required_fields(payload, required_fields)
    if missing_fields:
        return _result(
            TriggerState.BLOCKED,
            contract=contract,
            setup_id=request.setup_id,
            trigger_id=trigger_id,
            required_fields=required_fields,
            missing_fields=missing_fields,
            blocking_reasons=("missing_required_live_fields",),
            last_updated=last_updated,
        )

    bar_stale_reasons = _bar_stale_reasons(request)
    if bar_stale_reasons:
        return _result(
            TriggerState.STALE,
            contract=contract,
            setup_id=request.setup_id,
            trigger_id=trigger_id,
            required_fields=required_fields,
            blocking_reasons=bar_stale_reasons,
            last_updated=last_updated,
        )

    bar_blocking_reasons = _bar_blocking_reasons(request.bar_state)
    if bar_blocking_reasons:
        return _result(
            TriggerState.BLOCKED,
            contract=contract,
            setup_id=request.setup_id,
            trigger_id=trigger_id,
            required_fields=required_fields,
            blocking_reasons=bar_blocking_reasons,
            last_updated=last_updated,
        )

    evaluation = TriggerEvaluator().evaluate([spec], payload).evaluations[0]
    if not evaluation.is_valid:
        return _result(
            TriggerState.ERROR,
            contract=contract,
            setup_id=request.setup_id,
            trigger_id=trigger_id,
            required_fields=required_fields,
            missing_fields=evaluation.missing_fields,
            invalid_reasons=evaluation.invalid_reasons,
            blocking_reasons=("trigger_predicate_invalid",),
            last_updated=last_updated,
        )

    last_price = _number(_resolve_path(payload, "market.current_price"))
    tick_size = contract_tick_size(contract)
    if last_price is None:
        return _result(
            TriggerState.BLOCKED,
            contract=contract,
            setup_id=request.setup_id,
            trigger_id=trigger_id,
            required_fields=required_fields,
            missing_fields=("market.current_price",),
            blocking_reasons=("current_price_required",),
            last_updated=last_updated,
        )
    if tick_size is None:
        return _result(
            TriggerState.BLOCKED,
            contract=contract,
            setup_id=request.setup_id,
            trigger_id=trigger_id,
            required_fields=required_fields,
            blocking_reasons=("contract_tick_size_unavailable",),
            last_updated=last_updated,
        )

    distance_ticks = round(abs(last_price - trigger_level) / tick_size, 10)

    lockout_reasons = _lockout_reasons(request, payload)
    if lockout_reasons:
        return _result(
            TriggerState.LOCKOUT,
            contract=contract,
            setup_id=request.setup_id,
            trigger_id=trigger_id,
            required_fields=required_fields,
            blocking_reasons=lockout_reasons,
            distance_to_trigger_ticks=distance_ticks,
            last_updated=last_updated,
        )

    invalid_reasons = _active_invalidator_reasons(request.invalidators)
    if invalid_reasons:
        return _result(
            TriggerState.INVALIDATED,
            contract=contract,
            setup_id=request.setup_id,
            trigger_id=trigger_id,
            required_fields=required_fields,
            invalid_reasons=invalid_reasons,
            blocking_reasons=invalid_reasons,
            distance_to_trigger_ticks=distance_ticks,
            last_updated=last_updated,
        )

    if not _price_crosses(last_price, trigger_level, trigger_direction):
        if _within_approach_threshold(
            last_price,
            level=trigger_level,
            direction=trigger_direction,
            approach_threshold_ticks=request.approach_threshold_ticks,
            tick_size=tick_size,
        ):
            return _result(
                TriggerState.APPROACHING,
                contract=contract,
                setup_id=request.setup_id,
                trigger_id=trigger_id,
                required_fields=required_fields,
                blocking_reasons=("awaiting_trigger_touch",),
                distance_to_trigger_ticks=distance_ticks,
                last_updated=last_updated,
            )
        return _result(
            TriggerState.DORMANT,
            contract=contract,
            setup_id=request.setup_id,
            trigger_id=trigger_id,
            required_fields=required_fields,
            blocking_reasons=("price_outside_approach_threshold",),
            distance_to_trigger_ticks=distance_ticks,
            last_updated=last_updated,
        )

    confirmation = _confirmation_facts(
        request.bar_state,
        level=trigger_level,
        direction=trigger_direction,
        required=request.require_completed_bar_confirmation,
    )
    if not confirmation.confirmed:
        state = TriggerState.ARMED if confirmation.partial else TriggerState.TOUCHED
        return _result(
            state,
            contract=contract,
            setup_id=request.setup_id,
            trigger_id=trigger_id,
            required_fields=required_fields,
            blocking_reasons=confirmation.blocking_reasons,
            distance_to_trigger_ticks=distance_ticks,
            last_updated=last_updated,
        )

    if not evaluation.is_true:
        return _result(
            TriggerState.ARMED,
            contract=contract,
            setup_id=request.setup_id,
            trigger_id=trigger_id,
            required_fields=required_fields,
            blocking_reasons=("trigger_predicate_not_satisfied",),
            distance_to_trigger_ticks=distance_ticks,
            last_updated=last_updated,
        )

    return _result(
        TriggerState.QUERY_READY,
        contract=contract,
        setup_id=request.setup_id,
        trigger_id=trigger_id,
        required_fields=required_fields,
        blocking_reasons=(),
        distance_to_trigger_ticks=distance_ticks,
        last_updated=last_updated,
    )


def evaluate_trigger_state_from_brief(
    brief: Mapping[str, Any] | None,
    live_snapshot: Mapping[str, Any] | LiveObservableSnapshotV2 | None,
    *,
    trigger_id: str | None = None,
    artifact_available: bool = True,
    quote_fresh: bool | None = None,
    quote_blocking_reasons: tuple[str, ...] = (),
    bar_state: ContractBarState | None = None,
    bar_fresh: bool | None = None,
    event_lockout: TriggerLockoutState | None = None,
    session_lockout: TriggerLockoutState | None = None,
    invalidators: tuple[TriggerInvalidatorState, ...] = (),
    approach_threshold_ticks: int = 4,
    require_completed_bar_confirmation: bool = True,
    last_updated: str | None = None,
) -> TriggerStateResult:
    if brief is None:
        return _result(
            TriggerState.UNAVAILABLE,
            contract="",
            setup_id=None,
            trigger_id=trigger_id,
            required_fields=(),
            blocking_reasons=("brief_unavailable",),
            last_updated=last_updated,
        )

    contract = normalize_contract_symbol(str(brief.get("contract", "")))
    specs = trigger_specs_from_brief(brief)
    spec = _select_trigger_spec(specs, trigger_id)
    setup_id = _setup_id_for_trigger(brief, spec.id if spec is not None else trigger_id)
    return evaluate_trigger_state(
        TriggerStateRequest(
            contract=contract,
            setup_id=setup_id,
            trigger_spec=spec,
            live_snapshot=live_snapshot,
            artifact_available=artifact_available,
            approach_threshold_ticks=approach_threshold_ticks,
            quote_fresh=quote_fresh,
            quote_blocking_reasons=quote_blocking_reasons,
            bar_state=bar_state,
            bar_fresh=bar_fresh,
            event_lockout=event_lockout or TriggerLockoutState(),
            session_lockout=session_lockout or TriggerLockoutState(),
            invalidators=invalidators,
            require_completed_bar_confirmation=require_completed_bar_confirmation,
            last_updated=last_updated,
        )
    )


def _result(
    state: TriggerState,
    *,
    contract: str,
    setup_id: str | None,
    trigger_id: str | None,
    required_fields: tuple[str, ...],
    blocking_reasons: tuple[str, ...],
    last_updated: str | None,
    missing_fields: tuple[str, ...] = (),
    invalid_reasons: tuple[str, ...] = (),
    distance_to_trigger_ticks: float | None = None,
) -> TriggerStateResult:
    return TriggerStateResult(
        contract=contract,
        setup_id=setup_id,
        trigger_id=trigger_id,
        state=state,
        distance_to_trigger_ticks=distance_to_trigger_ticks,
        required_fields=required_fields,
        missing_fields=_dedupe(missing_fields),
        invalid_reasons=_dedupe(invalid_reasons),
        blocking_reasons=_dedupe(blocking_reasons),
        last_updated=last_updated,
    )


def _contract_blocking_reasons(contract: str) -> tuple[str, ...]:
    if is_never_supported_contract(contract):
        return (f"never_supported_contract:{contract}", "trigger_state_final_target_only")
    if is_excluded_final_target_contract(contract):
        return (f"excluded_contract:{contract}", "trigger_state_final_target_only")
    if not is_final_target_contract(contract):
        return (f"unsupported_contract:{contract}", "trigger_state_final_target_only")
    return ()


def _select_trigger_spec(specs: list[TriggerSpec], trigger_id: str | None) -> TriggerSpec | None:
    if trigger_id is None:
        return specs[0] if specs else None
    for spec in specs:
        if spec.id == trigger_id:
            return spec
    return None


def _setup_id_for_trigger(brief: Mapping[str, Any], trigger_id: str | None) -> str | None:
    setups = brief.get("structural_setups", ())
    if not isinstance(setups, list):
        return None
    for setup in setups:
        if not isinstance(setup, Mapping):
            continue
        triggers = setup.get("query_triggers", ())
        if not isinstance(triggers, list):
            continue
        for trigger in triggers:
            if isinstance(trigger, Mapping) and str(trigger.get("id", "")) == trigger_id:
                setup_id = setup.get("id")
                return str(setup_id) if isinstance(setup_id, str) and setup_id.strip() else None
    return None


def _trigger_level_and_direction(
    request: TriggerStateRequest,
    spec: TriggerSpec,
) -> tuple[float | None, TriggerDirection | None]:
    level = _number(request.trigger_level)
    direction = request.trigger_direction
    if level is not None and direction is not None:
        return level, direction
    parsed_level, parsed_direction = _trigger_level_from_predicate(spec.predicate)
    return level if level is not None else parsed_level, direction or parsed_direction


def _trigger_level_from_predicate(predicate: str) -> tuple[float | None, TriggerDirection | None]:
    match = _PRICE_LEVEL_RE.search(predicate)
    if match is None:
        return None, None
    operator = match.group("operator")
    level = _number_from_string(match.group("level"))
    if level is None:
        return None, None
    if operator in ("<", "<="):
        return level, "at_or_below"
    return level, "at_or_above"


def _snapshot_inputs(
    live_snapshot: Mapping[str, Any] | LiveObservableSnapshotV2,
    contract: str,
) -> _SnapshotInputs:
    if isinstance(live_snapshot, LiveObservableSnapshotV2):
        return _snapshot_inputs_from_v2(live_snapshot, contract)
    if _looks_like_snapshot_v2_mapping(live_snapshot):
        return _snapshot_inputs_from_v2_mapping(live_snapshot, contract)
    return _SnapshotInputs(
        payload=copy.deepcopy(dict(live_snapshot)),
        quote_fresh=None,
        quote_blocking_reasons=(),
        required_fields_present=None,
        quality_blocking_reasons=(),
        last_updated=_string_value(live_snapshot.get("timestamp_et")),
    )


def _snapshot_inputs_from_v2(snapshot: LiveObservableSnapshotV2, contract: str) -> _SnapshotInputs:
    observable = snapshot.contracts.get(contract)
    if observable is None:
        return _SnapshotInputs(
            payload={"contract": contract, "timestamp_et": snapshot.generated_at},
            quote_fresh=False,
            quote_blocking_reasons=(f"missing_contract_observable:{contract}",),
            required_fields_present=False,
            quality_blocking_reasons=(f"missing_contract_observable:{contract}",),
            last_updated=snapshot.generated_at,
        )
    return _SnapshotInputs(
        payload=_payload_from_contract_observable(observable, generated_at=snapshot.generated_at),
        quote_fresh=observable.quality.fresh,
        quote_blocking_reasons=tuple(observable.quality.blocking_reasons),
        required_fields_present=observable.quality.required_fields_present,
        quality_blocking_reasons=tuple(observable.quality.blocking_reasons),
        last_updated=snapshot.generated_at,
    )


def _snapshot_inputs_from_v2_mapping(snapshot: Mapping[str, Any], contract: str) -> _SnapshotInputs:
    generated_at = _string_value(snapshot.get("generated_at"))
    contracts = snapshot.get("contracts", {})
    contract_payload = contracts.get(contract) if isinstance(contracts, Mapping) else None
    if not isinstance(contract_payload, Mapping):
        return _SnapshotInputs(
            payload={"contract": contract, "timestamp_et": generated_at},
            quote_fresh=False,
            quote_blocking_reasons=(f"missing_contract_observable:{contract}",),
            required_fields_present=False,
            quality_blocking_reasons=(f"missing_contract_observable:{contract}",),
            last_updated=generated_at,
        )
    quality = contract_payload.get("quality", {})
    quality_mapping = quality if isinstance(quality, Mapping) else {}
    blocking = _tuple_of_strings(quality_mapping.get("blocking_reasons", ()))
    required_fields_present = quality_mapping.get("required_fields_present")
    return _SnapshotInputs(
        payload=_payload_from_contract_observable_mapping(contract_payload, generated_at=generated_at),
        quote_fresh=_bool_or_none(quality_mapping.get("fresh")),
        quote_blocking_reasons=blocking,
        required_fields_present=_bool_or_none(required_fields_present),
        quality_blocking_reasons=blocking,
        last_updated=generated_at,
    )


def _payload_from_contract_observable(
    observable: ContractObservableV2,
    *,
    generated_at: str,
) -> dict[str, Any]:
    market: dict[str, Any] = {"current_price": observable.quote.last}
    if observable.derived.bar_5m_close is not None:
        market["bar_5m_close"] = observable.derived.bar_5m_close
    if observable.derived.bar_5m_close_count_at_or_beyond_level is not None:
        market["bar_5m_close_count_at_or_beyond_level"] = (
            observable.derived.bar_5m_close_count_at_or_beyond_level
        )
    return {
        "contract": observable.contract,
        "timestamp_et": generated_at,
        "market": market,
        **_dependency_payload_from_observable(observable.dependencies),
    }


def _payload_from_contract_observable_mapping(
    observable: Mapping[str, Any],
    *,
    generated_at: str | None,
) -> dict[str, Any]:
    quote = observable.get("quote", {})
    derived = observable.get("derived", {})
    quote_mapping = quote if isinstance(quote, Mapping) else {}
    derived_mapping = derived if isinstance(derived, Mapping) else {}
    market: dict[str, Any] = {"current_price": quote_mapping.get("last")}
    if derived_mapping.get("bar_5m_close") is not None:
        market["bar_5m_close"] = derived_mapping.get("bar_5m_close")
    if derived_mapping.get("bar_5m_close_count_at_or_beyond_level") is not None:
        market["bar_5m_close_count_at_or_beyond_level"] = derived_mapping.get(
            "bar_5m_close_count_at_or_beyond_level"
        )
    return {
        "contract": observable.get("contract"),
        "timestamp_et": generated_at,
        "market": market,
        **_dependency_payload_from_mapping(observable.get("dependencies")),
    }


def _dependency_payload_from_observable(dependencies: Mapping[str, object]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for name, dependency in dependencies.items():
        status = str(getattr(dependency, "status", "")).strip().lower()
        if status not in {"available", "derived_with_source", "lockout"}:
            continue
        value = getattr(dependency, "value", None)
        fields = getattr(dependency, "fields", {})
        _merge_dependency_value(payload, str(name), status=status, value=value, fields=fields)
    return payload


def _dependency_payload_from_mapping(dependencies: object) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if not isinstance(dependencies, Mapping):
        return payload
    for name, dependency in dependencies.items():
        if not isinstance(dependency, Mapping):
            continue
        status = str(dependency.get("status") or "").strip().lower()
        if status not in {"available", "derived_with_source", "lockout"}:
            continue
        _merge_dependency_value(
            payload,
            str(name),
            status=status,
            value=dependency.get("value"),
            fields=dependency.get("fields"),
        )
    return payload


def _merge_dependency_value(
    payload: dict[str, Any],
    name: str,
    *,
    status: str,
    value: object,
    fields: object,
) -> None:
    if name == "relative_strength_vs_es":
        _set_path(payload, "cross_asset.relative_strength_vs_es", value)
    elif name == "dxy":
        _set_path(payload, "cross_asset.dxy", value)
    elif name == "cash_10y_yield":
        _set_path(payload, "cross_asset.cash_10y_yield", value)
    elif name == "fear_catalyst_state":
        _set_path(payload, "macro_context.fear_catalyst_state", value)
    elif name == "eia_lockout":
        _set_path(payload, "macro_context.eia_lockout_active", True if status == "lockout" else value)
    elif name == "session_sequence" and isinstance(fields, Mapping):
        for key in ("asia_complete", "london_complete", "ny_pending"):
            if key in fields:
                _set_path(payload, f"session_sequence.{key}", fields[key])
    elif name == "breadth" and isinstance(fields, Mapping):
        for key, item in fields.items():
            _set_path(payload, f"cross_asset.breadth.{key}", item)
    elif name == "cumulative_delta":
        _set_path(payload, "market.cumulative_delta", value)
    elif name == "current_volume_vs_average":
        _set_path(payload, "volatility_context.current_volume_vs_average", value)


def _set_path(payload: dict[str, Any], path: str, value: object) -> None:
    if value is None:
        return
    current: dict[str, Any] = payload
    parts = path.split(".")
    for part in parts[:-1]:
        next_value = current.setdefault(part, {})
        if not isinstance(next_value, dict):
            return
        current = next_value
    current[parts[-1]] = value


def _payload_with_completed_bar_facts(
    payload: Mapping[str, Any],
    bar_state: ContractBarState | None,
    *,
    level: float,
    direction: TriggerDirection,
) -> dict[str, Any]:
    merged = copy.deepcopy(dict(payload))
    if bar_state is not None and not isinstance(bar_state, ContractBarState):
        return merged
    confirmation = _confirmation_facts(bar_state, level=level, direction=direction, required=True)
    if not confirmation.confirmed:
        return merged
    market = merged.setdefault("market", {})
    if not isinstance(market, dict):
        return merged
    market.setdefault("bar_5m_close", confirmation.latest_completed_five_minute_close)
    market.setdefault(
        "bar_5m_close_count_at_or_beyond_level",
        confirmation.completed_five_minute_close_count_at_or_beyond_level,
    )
    return merged


def _quote_quality_reasons(request: TriggerStateRequest, snapshot_inputs: _SnapshotInputs) -> tuple[str, ...]:
    if snapshot_inputs.required_fields_present is False:
        return _dedupe(("live_observable_required_fields_missing",) + snapshot_inputs.quality_blocking_reasons)
    return ()


def _quote_stale_reasons(request: TriggerStateRequest, snapshot_inputs: _SnapshotInputs) -> tuple[str, ...]:
    quote_fresh = request.quote_fresh if request.quote_fresh is not None else snapshot_inputs.quote_fresh
    if quote_fresh is not False:
        return ()
    return _dedupe(("quote_stale",) + request.quote_blocking_reasons + snapshot_inputs.quote_blocking_reasons)


def _bar_stale_reasons(request: TriggerStateRequest) -> tuple[str, ...]:
    explicit_reasons = ("bar_data_stale",) if request.bar_fresh is False else ()
    if request.bar_state is not None and not isinstance(request.bar_state, ContractBarState):
        return _dedupe(explicit_reasons + ("bar_state_provenance_not_verified",))
    state_reasons = tuple(
        f"bar_state_stale:{reason}"
        for reason in getattr(request.bar_state, "blocking_reasons", ())
        if str(reason).startswith("stale_bar_data")
    )
    return _dedupe(explicit_reasons + state_reasons)


def _bar_blocking_reasons(bar_state: ContractBarState | None) -> tuple[str, ...]:
    if bar_state is None:
        return ()
    if not isinstance(bar_state, ContractBarState):
        return ("bar_state_provenance_not_verified",)
    return tuple(
        f"bar_state_blocked:{reason}"
        for reason in bar_state.blocking_reasons
        if not str(reason).startswith("stale_bar_data")
    )


def _missing_required_fields(payload: Mapping[str, Any], required_fields: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(path for path in required_fields if _is_missing_value(_resolve_path(payload, path)))


def _lockout_reasons(request: TriggerStateRequest, payload: Mapping[str, Any]) -> tuple[str, ...]:
    reasons: list[str] = []
    if request.event_lockout.active:
        reasons.extend(("event_lockout_active", request.event_lockout.reason or "event_lockout_active"))
    if request.session_lockout.active:
        reasons.extend(("session_lockout_active", request.session_lockout.reason or "session_lockout_active"))
    for path in (
        "macro_context.event_lockout_active",
        "macro_context.tier1_lockout_active",
        "macro_context.eia_lockout_active",
        "session_context.session_lockout_active",
        "session_sequence.thin_liquidity_after_london_close_active",
    ):
        if _resolve_path(payload, path) is True:
            reasons.append(path.replace(".", "_"))
    return _dedupe(tuple(reasons))


def _active_invalidator_reasons(invalidators: tuple[TriggerInvalidatorState, ...]) -> tuple[str, ...]:
    reasons: list[str] = []
    for invalidator in invalidators:
        if not invalidator.active or invalidator.reset_condition_met:
            continue
        reasons.append(invalidator.reason or f"invalidator_fired:{invalidator.invalidator_id}")
    return _dedupe(tuple(reasons))


def _confirmation_facts(
    bar_state: ContractBarState | None,
    *,
    level: float,
    direction: TriggerDirection,
    required: bool,
) -> _ConfirmationFacts:
    if not required:
        return _ConfirmationFacts(
            confirmed=True,
            partial=False,
            latest_completed_five_minute_close=None,
            completed_five_minute_close_count_at_or_beyond_level=None,
            blocking_reasons=(),
        )
    if bar_state is None:
        return _ConfirmationFacts(
            confirmed=False,
            partial=False,
            latest_completed_five_minute_close=None,
            completed_five_minute_close_count_at_or_beyond_level=None,
            blocking_reasons=("bar_state_required_for_confirmation",),
        )
    if not isinstance(bar_state, ContractBarState):
        return _ConfirmationFacts(
            confirmed=False,
            partial=False,
            latest_completed_five_minute_close=None,
            completed_five_minute_close_count_at_or_beyond_level=None,
            blocking_reasons=("bar_state_provenance_not_verified",),
        )
    completed_five_minute = tuple(
        bar for bar in bar_state.completed_five_minute_bars if bool(getattr(bar, "completed", False))
    )
    completed_one_minute = tuple(
        bar for bar in bar_state.completed_one_minute_bars if bool(getattr(bar, "completed", False))
    )
    latest_close = _latest_completed_five_minute_close(completed_five_minute)
    count_at_or_beyond = sum(
        1
        for bar in completed_five_minute
        if _completed_five_minute_bar_is_usable(bar)
        and _price_crosses(float(getattr(bar, "close")), level, direction)
    )
    partial = bar_state.building_five_minute_bar is not None

    if not completed_five_minute:
        reasons = ["completed_five_minute_confirmation_required"]
        if partial:
            reasons.append("building_five_minute_bar_not_confirmation")
        return _ConfirmationFacts(
            confirmed=False,
            partial=partial,
            latest_completed_five_minute_close=None,
            completed_five_minute_close_count_at_or_beyond_level=0,
            blocking_reasons=tuple(reasons),
        )

    for bar in completed_five_minute:
        close = _number(getattr(bar, "close", None))
        if close is None or not _completed_five_minute_bar_is_usable(bar):
            continue
        if not _price_crosses(close, level, direction):
            continue
        if _has_required_completed_one_minute_support(bar, completed_one_minute):
            return _ConfirmationFacts(
                confirmed=True,
                partial=partial,
                latest_completed_five_minute_close=latest_close,
                completed_five_minute_close_count_at_or_beyond_level=count_at_or_beyond,
                blocking_reasons=(),
            )

    reasons = ["completed_five_minute_close_not_confirmed"]
    if count_at_or_beyond:
        reasons = ["completed_one_minute_confirmation_bars_required"]
    if partial:
        reasons.append("building_five_minute_bar_not_confirmation")
    return _ConfirmationFacts(
        confirmed=False,
        partial=partial or bool(completed_five_minute),
        latest_completed_five_minute_close=latest_close,
        completed_five_minute_close_count_at_or_beyond_level=count_at_or_beyond,
        blocking_reasons=_dedupe(tuple(reasons)),
    )


def _completed_five_minute_bar_is_usable(bar: object) -> bool:
    if not bool(getattr(bar, "completed", False)):
        return False
    if _number(getattr(bar, "contributing_bar_count", None)) != 5.0:
        return False
    close = _number(getattr(bar, "close", None))
    if close is None:
        return False
    quality = getattr(bar, "quality", None)
    return bool(getattr(quality, "usable", True))


def _bar_state_provenance_reasons(bar_state: object | None) -> tuple[str, ...]:
    if bar_state is None or isinstance(bar_state, ContractBarState):
        return ()
    return ("bar_state_provenance_not_verified",)


def _has_required_completed_one_minute_support(
    five_minute_bar: object,
    completed_one_minute: tuple[object, ...],
) -> bool:
    start = str(getattr(five_minute_bar, "start_time", ""))
    end = str(getattr(five_minute_bar, "end_time", ""))
    expected_starts = {
        _minute_offset(start, offset)
        for offset in range(5)
        if _minute_offset(start, offset) is not None
    }
    if len(expected_starts) != 5:
        return False
    actual_starts = {
        str(getattr(bar, "start_time", ""))
        for bar in completed_one_minute
        if bool(getattr(bar, "completed", False))
        and str(getattr(bar, "start_time", "")) in expected_starts
        and str(getattr(bar, "end_time", "")) <= end
    }
    return actual_starts == expected_starts


def _latest_completed_five_minute_close(bars: tuple[object, ...]) -> float | None:
    for bar in reversed(bars):
        close = _number(getattr(bar, "close", None))
        if bool(getattr(bar, "completed", False)) and close is not None:
            return close
    return None


def _minute_offset(value: str, minutes: int) -> str | None:
    from datetime import datetime, timedelta, timezone

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (parsed.astimezone(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def _last_updated_from_snapshot(
    live_snapshot: Mapping[str, Any] | LiveObservableSnapshotV2 | None,
    contract: str,
) -> str | None:
    if live_snapshot is None:
        return None
    if isinstance(live_snapshot, LiveObservableSnapshotV2):
        return live_snapshot.generated_at
    if _looks_like_snapshot_v2_mapping(live_snapshot):
        return _string_value(live_snapshot.get("generated_at"))
    value = live_snapshot.get("timestamp_et")
    return _string_value(value)


def _looks_like_snapshot_v2_mapping(snapshot: Mapping[str, Any]) -> bool:
    return "contracts" in snapshot and "data_quality" in snapshot


def _within_approach_threshold(
    price: float,
    *,
    level: float,
    direction: TriggerDirection,
    approach_threshold_ticks: int,
    tick_size: float,
) -> bool:
    threshold = float(approach_threshold_ticks) * tick_size
    if direction == "at_or_below":
        return level < price <= level + threshold
    return level - threshold <= price < level


def _price_crosses(price: float, level: float, direction: TriggerDirection) -> bool:
    if direction == "at_or_below":
        return price <= level
    return price >= level


def _resolve_path(snapshot: Mapping[str, Any], path: str) -> Any:
    current: Any = snapshot
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _is_missing_value(value: object) -> bool:
    return value is _MISSING or value is None or (isinstance(value, str) and not value.strip())


def _number(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _number_from_string(value: str) -> float | None:
    try:
        return float(value)
    except ValueError:
        return None


def _string_value(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _bool_or_none(value: object) -> bool | None:
    return value if isinstance(value, bool) else None


def _tuple_of_strings(value: object) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value if str(item).strip())
    return ()


def _dedupe(reasons: tuple[str, ...]) -> tuple[str, ...]:
    deduped: list[str] = []
    for reason in reasons:
        normalized = str(reason).strip()
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return tuple(deduped)


_MISSING = object()
_PRICE_LEVEL_RE: Final[re.Pattern[str]] = re.compile(
    r"\bmarket\.current_price\s*(?P<operator>>=|<=|>|<|==)\s*(?P<level>-?\d+(?:\.\d+)?)"
)
