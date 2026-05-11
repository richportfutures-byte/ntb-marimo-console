from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ntb_marimo_console.adapters.trigger_specs import trigger_specs_from_brief
from ntb_marimo_console.contract_universe import normalize_contract_symbol
from ntb_marimo_console.live_observables.schema_v2 import LiveObservableSnapshotV2
from ntb_marimo_console.market_data.chart_bars import ContractBarState
from ntb_marimo_console.trigger_state import (
    TriggerInvalidatorState,
    TriggerLockoutState,
    TriggerStateRequest,
    TriggerStateResult,
    evaluate_trigger_state,
    evaluate_trigger_state_from_brief,
)


@dataclass(frozen=True)
class TriggerStateResultProducerRequest:
    contract: str
    premarket_brief: Mapping[str, Any] | None
    live_snapshot: Mapping[str, Any] | LiveObservableSnapshotV2 | None
    artifact_available: bool = True
    quote_fresh: bool | None = None
    quote_blocking_reasons: tuple[str, ...] = ()
    bar_state: ContractBarState | None = None
    bar_fresh: bool | None = None
    event_lockout: TriggerLockoutState | None = None
    session_lockout: TriggerLockoutState | None = None
    invalidators: tuple[TriggerInvalidatorState, ...] = ()
    approach_threshold_ticks: int = 4
    require_completed_bar_confirmation: bool = True
    last_updated: str | None = None


def build_trigger_state_results(
    request: TriggerStateResultProducerRequest,
) -> tuple[TriggerStateResult, ...]:
    if not isinstance(request, TriggerStateResultProducerRequest):
        raise TypeError("build_trigger_state_results requires a TriggerStateResultProducerRequest")
    if request.premarket_brief is not None and not isinstance(request.premarket_brief, Mapping):
        raise TypeError("premarket_brief must be a mapping")
    if request.live_snapshot is not None and not isinstance(request.live_snapshot, Mapping | LiveObservableSnapshotV2):
        raise TypeError("live_snapshot must be a mapping or LiveObservableSnapshotV2")

    contract = normalize_contract_symbol(request.contract)
    if request.premarket_brief is None or not request.artifact_available:
        return (
            evaluate_trigger_state(
                TriggerStateRequest(
                    contract=contract,
                    setup_id=None,
                    trigger_spec=None,
                    live_snapshot=request.live_snapshot,
                    artifact_available=False,
                    quote_fresh=request.quote_fresh,
                    quote_blocking_reasons=request.quote_blocking_reasons,
                    bar_state=request.bar_state,
                    bar_fresh=request.bar_fresh,
                    event_lockout=request.event_lockout or TriggerLockoutState(),
                    session_lockout=request.session_lockout or TriggerLockoutState(),
                    invalidators=request.invalidators,
                    approach_threshold_ticks=request.approach_threshold_ticks,
                    require_completed_bar_confirmation=request.require_completed_bar_confirmation,
                    last_updated=request.last_updated,
                )
            ),
        )

    brief_contract = normalize_contract_symbol(str(request.premarket_brief.get("contract", "")))
    if brief_contract != contract:
        return (
            evaluate_trigger_state(
                TriggerStateRequest(
                    contract=contract,
                    setup_id=None,
                    trigger_spec=None,
                    live_snapshot=request.live_snapshot,
                    artifact_available=False,
                    quote_fresh=request.quote_fresh,
                    quote_blocking_reasons=request.quote_blocking_reasons,
                    bar_state=request.bar_state,
                    bar_fresh=request.bar_fresh,
                    event_lockout=request.event_lockout or TriggerLockoutState(),
                    session_lockout=request.session_lockout or TriggerLockoutState(),
                    invalidators=request.invalidators,
                    approach_threshold_ticks=request.approach_threshold_ticks,
                    require_completed_bar_confirmation=request.require_completed_bar_confirmation,
                    last_updated=request.last_updated,
                )
            ),
        )

    specs = trigger_specs_from_brief(request.premarket_brief)
    if not specs:
        return (
            evaluate_trigger_state(
                TriggerStateRequest(
                    contract=contract,
                    setup_id=None,
                    trigger_spec=None,
                    live_snapshot=request.live_snapshot,
                    artifact_available=True,
                    quote_fresh=request.quote_fresh,
                    quote_blocking_reasons=request.quote_blocking_reasons,
                    bar_state=request.bar_state,
                    bar_fresh=request.bar_fresh,
                    event_lockout=request.event_lockout or TriggerLockoutState(),
                    session_lockout=request.session_lockout or TriggerLockoutState(),
                    invalidators=request.invalidators,
                    approach_threshold_ticks=request.approach_threshold_ticks,
                    require_completed_bar_confirmation=request.require_completed_bar_confirmation,
                    last_updated=request.last_updated,
                )
            ),
        )

    return tuple(
        evaluate_trigger_state_from_brief(
            request.premarket_brief,
            request.live_snapshot,
            trigger_id=spec.id,
            artifact_available=True,
            quote_fresh=request.quote_fresh,
            quote_blocking_reasons=request.quote_blocking_reasons,
            bar_state=request.bar_state,
            bar_fresh=request.bar_fresh,
            event_lockout=request.event_lockout,
            session_lockout=request.session_lockout,
            invalidators=request.invalidators,
            approach_threshold_ticks=request.approach_threshold_ticks,
            require_completed_bar_confirmation=request.require_completed_bar_confirmation,
            last_updated=request.last_updated,
        )
        for spec in specs
    )
