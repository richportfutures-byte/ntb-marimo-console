from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Final, Literal

from ntb_marimo_console.contract_universe import (
    is_excluded_final_target_contract,
    is_final_target_contract,
    is_never_supported_contract,
    normalize_contract_symbol,
)
from ntb_marimo_console.live_observables.quality import contract_tick_size
from ntb_marimo_console.live_observables.schema_v2 import ContractObservableV2
from ntb_marimo_console.market_data.chart_bars import ContractBarState

from .es_live_workstation import SourceClassification, TriggerDirection


SIXE_LIVE_WORKSTATION_SCHEMA: Final[str] = "sixe_live_workstation_v1"
SIXE_CONTRACT: Final[str] = "6E"

SixELiveWorkstationState = Literal[
    "UNAVAILABLE",
    "DORMANT",
    "APPROACHING",
    "TOUCHED",
    "ARMED",
    "QUERY_READY",
    "INVALIDATED",
    "BLOCKED",
    "STALE",
    "LOCKOUT",
    "ERROR",
]
SIXE_LIVE_WORKSTATION_STATES: Final[tuple[SixELiveWorkstationState, ...]] = (
    "UNAVAILABLE",
    "DORMANT",
    "APPROACHING",
    "TOUCHED",
    "ARMED",
    "QUERY_READY",
    "INVALIDATED",
    "BLOCKED",
    "STALE",
    "LOCKOUT",
    "ERROR",
)

DXYChangePredicate = Literal["at_or_above", "at_or_below"]


@dataclass(frozen=True)
class SixETriggerDefinition:
    setup_id: str
    trigger_id: str
    level: float | int
    direction: TriggerDirection = "at_or_above"
    approach_threshold_ticks: int = 8
    dxy_required: bool = True
    dxy_change_threshold: float | int = 0.0
    dxy_change_predicate: DXYChangePredicate = "at_or_below"
    session_sequence_required: bool = True
    range_context_required: bool = True
    thin_liquidity_state_required: bool = True
    source: SourceClassification = "preserved_artifact"

    def to_dict(self) -> dict[str, object]:
        return {
            "setup_id": self.setup_id,
            "trigger_id": self.trigger_id,
            "level": self.level,
            "direction": self.direction,
            "approach_threshold_ticks": self.approach_threshold_ticks,
            "dxy_required": self.dxy_required,
            "dxy_change_threshold": self.dxy_change_threshold,
            "dxy_change_predicate": self.dxy_change_predicate,
            "session_sequence_required": self.session_sequence_required,
            "range_context_required": self.range_context_required,
            "thin_liquidity_state_required": self.thin_liquidity_state_required,
            "source": self.source,
        }


@dataclass(frozen=True)
class SixEInvalidatorDefinition:
    invalidator_id: str
    level: float | int
    direction: TriggerDirection
    source: SourceClassification = "manual_operator_input"

    def to_dict(self) -> dict[str, object]:
        return {
            "invalidator_id": self.invalidator_id,
            "level": self.level,
            "direction": self.direction,
            "source": self.source,
        }


@dataclass(frozen=True)
class SixEPremarketArtifact:
    artifact_id: str
    levels: Mapping[str, float | int] = field(default_factory=dict)
    available: bool = True
    source: SourceClassification = "preserved_artifact"

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "levels": dict(self.levels),
            "available": self.available,
            "source": self.source,
        }


@dataclass(frozen=True)
class SixEWorkstationEventLockout:
    active: bool = False
    reason: str | None = None
    source: SourceClassification = "manual_operator_input"

    def to_dict(self) -> dict[str, object]:
        return {
            "active": self.active,
            "reason": self.reason,
            "source": self.source,
        }


@dataclass(frozen=True)
class SixEDXYState:
    available: bool
    source_label: str | None
    value: float | int | None = None
    change: float | int | None = None
    textual_context: str | None = None
    fresh: bool = True
    missing_fields: tuple[str, ...] = ()
    blocking_reasons: tuple[str, ...] = ()
    source: SourceClassification = "manual_operator_input"

    def to_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "source_label": self.source_label,
            "value": self.value,
            "change": self.change,
            "textual_context": self.textual_context,
            "fresh": self.fresh,
            "missing_fields": list(self.missing_fields),
            "blocking_reasons": list(self.blocking_reasons),
            "source": self.source,
        }


@dataclass(frozen=True)
class SixESessionSequenceState:
    available: bool
    asia_complete: bool | None
    london_complete: bool | None
    ny_active: bool | None
    ny_pending: bool | None
    source_label: str | None
    state: str | None = None
    missing_fields: tuple[str, ...] = ()
    blocking_reasons: tuple[str, ...] = ()
    source: SourceClassification = "manual_operator_input"

    def to_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "asia_complete": self.asia_complete,
            "london_complete": self.london_complete,
            "ny_active": self.ny_active,
            "ny_pending": self.ny_pending,
            "source_label": self.source_label,
            "state": self.state,
            "missing_fields": list(self.missing_fields),
            "blocking_reasons": list(self.blocking_reasons),
            "source": self.source,
        }


@dataclass(frozen=True)
class SixESessionRangeState:
    high: float | int | None
    low: float | int | None
    complete: bool | None
    available: bool = True
    source_label: str | None = None
    missing_fields: tuple[str, ...] = ()
    blocking_reasons: tuple[str, ...] = ()
    source: SourceClassification = "manual_operator_input"

    def to_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "high": self.high,
            "low": self.low,
            "complete": self.complete,
            "source_label": self.source_label,
            "missing_fields": list(self.missing_fields),
            "blocking_reasons": list(self.blocking_reasons),
            "source": self.source,
        }


@dataclass(frozen=True)
class SixEThinLiquidityState:
    available: bool
    active: bool | None
    blocking: bool = True
    reason: str | None = None
    source_label: str | None = None
    missing_fields: tuple[str, ...] = ()
    blocking_reasons: tuple[str, ...] = ()
    source: SourceClassification = "manual_operator_input"

    def to_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "active": self.active,
            "blocking": self.blocking,
            "reason": self.reason,
            "source_label": self.source_label,
            "missing_fields": list(self.missing_fields),
            "blocking_reasons": list(self.blocking_reasons),
            "source": self.source,
        }


@dataclass(frozen=True)
class SixELiveQuoteInput:
    contract: str
    symbol: str | None
    bid: float | int | None
    ask: float | int | None
    last: float | int | None
    spread_ticks: float | int | None
    fresh: bool
    symbol_match: bool
    required_fields_present: bool
    blocking_reasons: tuple[str, ...] = ()
    quote_time: str | None = None
    trade_time: str | None = None
    quote_age_seconds: float | None = None
    trade_age_seconds: float | None = None
    source: SourceClassification = "observed_from_schwab"

    @classmethod
    def from_live_observable(cls, observable: ContractObservableV2) -> SixELiveQuoteInput:
        return cls(
            contract=observable.contract,
            symbol=observable.symbol,
            bid=observable.quote.bid,
            ask=observable.quote.ask,
            last=observable.quote.last,
            spread_ticks=observable.derived.spread_ticks,
            fresh=observable.quality.fresh,
            symbol_match=observable.quality.symbol_match,
            required_fields_present=observable.quality.required_fields_present,
            blocking_reasons=tuple(observable.quality.blocking_reasons),
            quote_time=observable.quote.quote_time,
            trade_time=observable.quote.trade_time,
            quote_age_seconds=observable.quote.quote_age_seconds,
            trade_age_seconds=observable.quote.trade_age_seconds,
            source="observed_from_schwab",
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "symbol": self.symbol,
            "bid": self.bid,
            "ask": self.ask,
            "last": self.last,
            "spread_ticks": self.spread_ticks,
            "fresh": self.fresh,
            "symbol_match": self.symbol_match,
            "required_fields_present": self.required_fields_present,
            "blocking_reasons": list(self.blocking_reasons),
            "quote_time": self.quote_time,
            "trade_time": self.trade_time,
            "quote_age_seconds": self.quote_age_seconds,
            "trade_age_seconds": self.trade_age_seconds,
            "source": self.source,
        }


@dataclass(frozen=True)
class SixECompletedBarEvidence:
    confirmed: bool
    completed_five_minute_bar_count: int
    completed_one_minute_bar_count: int
    latest_completed_five_minute_close: float | None
    building_five_minute_present: bool
    blocking_reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "confirmed": self.confirmed,
            "completed_five_minute_bar_count": self.completed_five_minute_bar_count,
            "completed_one_minute_bar_count": self.completed_one_minute_bar_count,
            "latest_completed_five_minute_close": self.latest_completed_five_minute_close,
            "building_five_minute_present": self.building_five_minute_present,
            "blocking_reasons": list(self.blocking_reasons),
        }


@dataclass(frozen=True)
class SixEWorkstationAuthorizations:
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
class SixELiveWorkstationInput:
    contract: str = SIXE_CONTRACT
    quote: SixELiveQuoteInput | None = None
    bar_state: ContractBarState | None = None
    premarket_artifact: SixEPremarketArtifact | None = None
    trigger: SixETriggerDefinition | None = None
    invalidators: tuple[SixEInvalidatorDefinition, ...] = ()
    event_lockout: SixEWorkstationEventLockout | None = None
    dxy_state: SixEDXYState | None = None
    session_sequence_state: SixESessionSequenceState | None = None
    asia_range_state: SixESessionRangeState | None = None
    london_range_state: SixESessionRangeState | None = None
    ny_range_state: SixESessionRangeState | None = None
    thin_liquidity_state: SixEThinLiquidityState | None = None
    generated_at: str | None = None


@dataclass(frozen=True)
class SixELiveWorkstationReadModel:
    state: SixELiveWorkstationState
    contract: str
    symbol: str | None
    setup_id: str | None
    trigger_id: str | None
    trigger_level: float | None
    last_price: float | None
    distance_to_trigger_ticks: float | None
    required_fields: tuple[str, ...]
    missing_fields: tuple[str, ...]
    blocking_reasons: tuple[str, ...]
    invalid_reasons: tuple[str, ...]
    dxy_source: str | None
    dxy_numeric_value: float | None
    dxy_change: float | None
    dxy_required: bool
    dxy_passed: bool | None
    session_sequence_required: bool
    session_sequence_passed: bool | None
    session_sequence_state: SixESessionSequenceState | None
    asia_range_state: SixESessionRangeState | None
    london_range_state: SixESessionRangeState | None
    ny_range_state: SixESessionRangeState | None
    thin_liquidity_state: SixEThinLiquidityState | None
    completed_bar_evidence: SixECompletedBarEvidence
    event_lockout_state: SixEWorkstationEventLockout | None
    source_classification: Mapping[str, SourceClassification]
    generated_at: str | None = None
    authorizations: SixEWorkstationAuthorizations = field(default_factory=SixEWorkstationAuthorizations)
    decision_authority: str = "preserved_engine_only"
    read_model_only: bool = True
    schema: str = SIXE_LIVE_WORKSTATION_SCHEMA

    @property
    def pipeline_query_authorized(self) -> bool:
        return self.authorizations.pipeline_query_authorized

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "state": self.state,
            "contract": self.contract,
            "symbol": self.symbol,
            "setup_id": self.setup_id,
            "trigger_id": self.trigger_id,
            "trigger_level": self.trigger_level,
            "last_price": self.last_price,
            "distance_to_trigger_ticks": self.distance_to_trigger_ticks,
            "required_fields": list(self.required_fields),
            "missing_fields": list(self.missing_fields),
            "blocking_reasons": list(self.blocking_reasons),
            "invalid_reasons": list(self.invalid_reasons),
            "dxy_source": self.dxy_source,
            "dxy_numeric_value": self.dxy_numeric_value,
            "dxy_change": self.dxy_change,
            "dxy_required": self.dxy_required,
            "dxy_passed": self.dxy_passed,
            "session_sequence_required": self.session_sequence_required,
            "session_sequence_passed": self.session_sequence_passed,
            "session_sequence_state": (
                self.session_sequence_state.to_dict() if self.session_sequence_state is not None else None
            ),
            "asia_range_state": self.asia_range_state.to_dict() if self.asia_range_state is not None else None,
            "london_range_state": self.london_range_state.to_dict() if self.london_range_state is not None else None,
            "ny_range_state": self.ny_range_state.to_dict() if self.ny_range_state is not None else None,
            "thin_liquidity_state": (
                self.thin_liquidity_state.to_dict() if self.thin_liquidity_state is not None else None
            ),
            "completed_bar_evidence": self.completed_bar_evidence.to_dict(),
            "event_lockout_state": (
                self.event_lockout_state.to_dict() if self.event_lockout_state is not None else None
            ),
            "source_classification": dict(self.source_classification),
            "generated_at": self.generated_at,
            "pipeline_query_authorized": self.pipeline_query_authorized,
            "authorizations": self.authorizations.to_dict(),
            "decision_authority": self.decision_authority,
            "read_model_only": self.read_model_only,
        }


@dataclass(frozen=True)
class _DXYGateResult:
    value: float | None
    change: float | None
    passed: bool | None
    blocking_reasons: tuple[str, ...]


@dataclass(frozen=True)
class _SessionGateResult:
    passed: bool | None
    blocking_reasons: tuple[str, ...]


def evaluate_sixe_live_workstation(payload: SixELiveWorkstationInput) -> SixELiveWorkstationReadModel:
    contract = normalize_contract_symbol(payload.contract)
    quote = payload.quote
    trigger = payload.trigger
    evidence = _empty_evidence(payload.bar_state)
    sources = _source_classification(payload)

    contract_reasons = _contract_blocking_reasons(contract, quote)
    if contract_reasons:
        return _read_model(
            "BLOCKED",
            payload,
            blocking_reasons=contract_reasons,
            invalid_reasons=(),
            evidence=evidence,
            sources=sources,
        )

    event_lockout_reasons = _event_lockout_state_reasons(payload)
    if event_lockout_reasons:
        return _read_model(
            "BLOCKED",
            payload,
            blocking_reasons=event_lockout_reasons,
            invalid_reasons=(),
            evidence=evidence,
            sources=sources,
        )

    assert payload.event_lockout is not None
    if payload.event_lockout.active:
        reason = payload.event_lockout.reason or "event_lockout_active"
        return _read_model(
            "LOCKOUT",
            payload,
            blocking_reasons=_dedupe(("event_lockout_active", reason)),
            invalid_reasons=(),
            evidence=evidence,
            sources=sources,
        )

    thin_reasons = _thin_liquidity_lockout_reasons(payload)
    if thin_reasons:
        return _read_model(
            "LOCKOUT",
            payload,
            blocking_reasons=thin_reasons,
            invalid_reasons=(),
            evidence=evidence,
            sources=sources,
        )

    artifact_reasons = _artifact_blocking_reasons(payload.premarket_artifact, trigger)
    if artifact_reasons:
        state: SixELiveWorkstationState = (
            "UNAVAILABLE" if "premarket_artifact_unavailable" in artifact_reasons else "BLOCKED"
        )
        return _read_model(
            state,
            payload,
            blocking_reasons=artifact_reasons,
            invalid_reasons=(),
            evidence=evidence,
            sources=sources,
        )

    assert trigger is not None
    trigger_reasons = _trigger_blocking_reasons(trigger)
    if trigger_reasons:
        return _read_model(
            "BLOCKED",
            payload,
            blocking_reasons=trigger_reasons,
            invalid_reasons=(),
            evidence=evidence,
            sources=sources,
        )

    evidence = _completed_bar_evidence(payload.bar_state, trigger)

    if quote is None:
        return _read_model(
            "UNAVAILABLE",
            payload,
            blocking_reasons=("quote_required",),
            invalid_reasons=(),
            evidence=evidence,
            sources=sources,
        )

    quote_structural_reasons = _quote_structural_reasons(quote)
    if quote_structural_reasons:
        return _read_model(
            "BLOCKED",
            payload,
            blocking_reasons=quote_structural_reasons,
            invalid_reasons=(),
            evidence=evidence,
            sources=sources,
        )

    quote_freshness_reasons = _quote_freshness_reasons(quote)
    if quote_freshness_reasons:
        return _read_model(
            "STALE",
            payload,
            blocking_reasons=quote_freshness_reasons,
            invalid_reasons=(),
            evidence=evidence,
            sources=sources,
        )

    prerequisite_reasons = _prerequisite_structural_reasons(payload)
    if prerequisite_reasons:
        return _read_model(
            "BLOCKED",
            payload,
            blocking_reasons=prerequisite_reasons,
            invalid_reasons=(),
            evidence=evidence,
            sources=sources,
        )

    last_price = _number(quote.last)
    assert last_price is not None
    trigger_level = float(trigger.level)
    tick_size = contract_tick_size(SIXE_CONTRACT)
    assert tick_size is not None
    distance_ticks = round(abs(last_price - trigger_level) / tick_size, 10)

    invalid_reasons = _invalidator_reasons(last_price, payload.invalidators)
    if invalid_reasons:
        return _read_model(
            "INVALIDATED",
            payload,
            blocking_reasons=invalid_reasons,
            invalid_reasons=invalid_reasons,
            evidence=evidence,
            sources=sources,
            last_price=last_price,
            distance_ticks=distance_ticks,
        )

    bar_blocking_reasons = _bar_state_blocking_reasons(payload.bar_state)
    if bar_blocking_reasons:
        return _read_model(
            "BLOCKED",
            payload,
            blocking_reasons=bar_blocking_reasons,
            invalid_reasons=(),
            evidence=_completed_bar_evidence(payload.bar_state, trigger),
            sources=sources,
            last_price=last_price,
            distance_ticks=distance_ticks,
        )

    if not _trigger_touched(last_price, trigger):
        if _within_approach_threshold(last_price, trigger, tick_size=tick_size):
            return _read_model(
                "APPROACHING",
                payload,
                blocking_reasons=("awaiting_trigger_touch",),
                invalid_reasons=(),
                evidence=evidence,
                sources=sources,
                last_price=last_price,
                distance_ticks=distance_ticks,
            )
        return _read_model(
            "DORMANT",
            payload,
            blocking_reasons=("price_outside_approach_threshold",),
            invalid_reasons=(),
            evidence=evidence,
            sources=sources,
            last_price=last_price,
            distance_ticks=distance_ticks,
        )

    evidence = _completed_bar_evidence(payload.bar_state, trigger)
    if not evidence.confirmed:
        state: SixELiveWorkstationState = "ARMED" if evidence.building_five_minute_present else "TOUCHED"
        return _read_model(
            state,
            payload,
            blocking_reasons=evidence.blocking_reasons,
            invalid_reasons=(),
            evidence=evidence,
            sources=sources,
            last_price=last_price,
            distance_ticks=distance_ticks,
        )

    dxy_result = _dxy_gate_result(payload)
    if trigger.dxy_required and dxy_result.passed is not True:
        return _read_model(
            "ARMED",
            payload,
            blocking_reasons=("dxy_predicate_failed",),
            invalid_reasons=(),
            evidence=evidence,
            sources=sources,
            last_price=last_price,
            distance_ticks=distance_ticks,
        )

    session_result = _session_gate_result(payload)
    if trigger.session_sequence_required and session_result.passed is not True:
        return _read_model(
            "ARMED",
            payload,
            blocking_reasons=session_result.blocking_reasons or ("session_sequence_predicate_failed",),
            invalid_reasons=(),
            evidence=evidence,
            sources=sources,
            last_price=last_price,
            distance_ticks=distance_ticks,
        )

    return _read_model(
        "QUERY_READY",
        payload,
        blocking_reasons=(),
        invalid_reasons=(),
        evidence=evidence,
        sources=sources,
        last_price=last_price,
        distance_ticks=distance_ticks,
    )


def _read_model(
    state: SixELiveWorkstationState,
    payload: SixELiveWorkstationInput,
    *,
    blocking_reasons: tuple[str, ...],
    invalid_reasons: tuple[str, ...],
    evidence: SixECompletedBarEvidence,
    sources: Mapping[str, SourceClassification],
    last_price: float | None = None,
    distance_ticks: float | None = None,
) -> SixELiveWorkstationReadModel:
    trigger = payload.trigger
    quote = payload.quote
    dxy_result = _dxy_gate_result(payload)
    session_result = _session_gate_result(payload)
    return SixELiveWorkstationReadModel(
        state=state,
        contract=normalize_contract_symbol(payload.contract),
        symbol=quote.symbol if quote is not None else None,
        setup_id=trigger.setup_id if trigger is not None else None,
        trigger_id=trigger.trigger_id if trigger is not None else None,
        trigger_level=float(trigger.level) if trigger is not None and _number(trigger.level) is not None else None,
        last_price=last_price,
        distance_to_trigger_ticks=distance_ticks,
        required_fields=_required_fields(payload),
        missing_fields=_missing_fields(payload),
        blocking_reasons=_dedupe(blocking_reasons),
        invalid_reasons=_dedupe(invalid_reasons),
        dxy_source=payload.dxy_state.source_label if payload.dxy_state is not None else None,
        dxy_numeric_value=dxy_result.value,
        dxy_change=dxy_result.change,
        dxy_required=_dxy_required(payload),
        dxy_passed=dxy_result.passed,
        session_sequence_required=_session_sequence_required(payload),
        session_sequence_passed=session_result.passed,
        session_sequence_state=payload.session_sequence_state,
        asia_range_state=payload.asia_range_state,
        london_range_state=payload.london_range_state,
        ny_range_state=payload.ny_range_state,
        thin_liquidity_state=payload.thin_liquidity_state,
        completed_bar_evidence=evidence,
        event_lockout_state=payload.event_lockout,
        source_classification=sources,
        generated_at=payload.generated_at,
    )


def _contract_blocking_reasons(contract: str, quote: SixELiveQuoteInput | None) -> tuple[str, ...]:
    reasons: list[str] = []
    if contract != SIXE_CONTRACT:
        if is_never_supported_contract(contract):
            reasons.append(f"never_supported_contract:{contract}")
        elif is_excluded_final_target_contract(contract):
            reasons.append(f"excluded_contract:{contract}")
        elif is_final_target_contract(contract):
            reasons.append(f"contract_not_onboarded_for_sixe_workstation:{contract}")
        else:
            reasons.append(f"unsupported_contract:{contract}")
        reasons.append("sixe_workstation_supports_6e_only")

    if quote is not None:
        quote_contract = normalize_contract_symbol(quote.contract)
        if quote_contract != SIXE_CONTRACT:
            reasons.append(f"quote_contract_mismatch:{quote_contract}")
    return _dedupe(tuple(reasons))


def _event_lockout_state_reasons(payload: SixELiveWorkstationInput) -> tuple[str, ...]:
    if payload.event_lockout is None:
        return ("event_lockout_state_required",)
    return ()


def _thin_liquidity_lockout_reasons(payload: SixELiveWorkstationInput) -> tuple[str, ...]:
    if not _thin_liquidity_required(payload):
        return ()
    thin = payload.thin_liquidity_state
    if thin is None or not thin.available or thin.active is not True or not thin.blocking:
        return ()
    reason = thin.reason or "thin_liquidity_after_london_close_active"
    return _dedupe(("thin_liquidity_after_london_close_active", reason))


def _artifact_blocking_reasons(
    artifact: SixEPremarketArtifact | None,
    trigger: SixETriggerDefinition | None,
) -> tuple[str, ...]:
    if artifact is None:
        return ("premarket_artifact_required",)
    if not artifact.available:
        return ("premarket_artifact_unavailable",)
    if trigger is None:
        return ("premarket_trigger_required",)
    return ()


def _trigger_blocking_reasons(trigger: SixETriggerDefinition) -> tuple[str, ...]:
    reasons: list[str] = []
    if not trigger.setup_id.strip():
        reasons.append("setup_id_required")
    if not trigger.trigger_id.strip():
        reasons.append("trigger_id_required")
    if _number(trigger.level) is None:
        reasons.append("trigger_level_required")
    if trigger.direction not in ("at_or_above", "at_or_below"):
        reasons.append(f"unsupported_trigger_direction:{trigger.direction}")
    if trigger.approach_threshold_ticks < 0:
        reasons.append("approach_threshold_ticks_must_be_non_negative")
    if _number(trigger.dxy_change_threshold) is None:
        reasons.append("dxy_change_threshold_required")
    if trigger.dxy_change_predicate not in ("at_or_above", "at_or_below"):
        reasons.append(f"unsupported_dxy_change_predicate:{trigger.dxy_change_predicate}")
    return tuple(reasons)


def _quote_structural_reasons(quote: SixELiveQuoteInput) -> tuple[str, ...]:
    reasons: list[str] = []
    if quote.symbol is None or not quote.symbol.strip():
        reasons.append("quote_symbol_required")
    if not quote.symbol_match:
        reasons.append("quote_symbol_mismatch")
    if not quote.required_fields_present:
        reasons.append("missing_required_quote_fields")
    for field_name in ("bid", "ask", "last", "spread_ticks"):
        if _number(getattr(quote, field_name)) is None:
            reasons.append(f"quote_{field_name}_required")
    bid = _number(quote.bid)
    ask = _number(quote.ask)
    spread_ticks = _number(quote.spread_ticks)
    if bid is not None and ask is not None and bid > ask:
        reasons.append("malformed_quote_bid_above_ask")
    if spread_ticks is not None and spread_ticks < 0:
        reasons.append("malformed_quote_negative_spread_ticks")
    if reasons:
        reasons.extend(quote.blocking_reasons)
    return _dedupe(tuple(reasons))


def _quote_freshness_reasons(quote: SixELiveQuoteInput) -> tuple[str, ...]:
    if quote.fresh:
        return ()
    return _dedupe(("quote_stale",) + quote.blocking_reasons)


def _prerequisite_structural_reasons(payload: SixELiveWorkstationInput) -> tuple[str, ...]:
    reasons = _dxy_structural_reasons(payload)
    reasons += _session_sequence_structural_reasons(payload)
    reasons += _range_structural_reasons(payload)
    reasons += _thin_liquidity_structural_reasons(payload)
    return _dedupe(reasons)


def _dxy_structural_reasons(payload: SixELiveWorkstationInput) -> tuple[str, ...]:
    if not _dxy_required(payload):
        return ()
    dxy = payload.dxy_state
    if dxy is None:
        return ("dxy_state_required",)

    reasons: list[str] = []
    if not dxy.available:
        reasons.append("dxy_state_unavailable")
    if dxy.source_label is None or not dxy.source_label.strip():
        reasons.append("dxy_source_label_required")
    if not dxy.fresh:
        reasons.append("dxy_state_stale")
    if _number(dxy.change) is None:
        reasons.append("dxy_numeric_change_required")
        if dxy.textual_context is not None:
            reasons.append("dxy_textual_context_not_sufficient")
    if dxy.missing_fields:
        reasons.append("dxy_fields_missing:" + ",".join(dxy.missing_fields))
    reasons.extend(f"dxy_blocked:{reason}" for reason in dxy.blocking_reasons)
    return _dedupe(tuple(reasons))


def _session_sequence_structural_reasons(payload: SixELiveWorkstationInput) -> tuple[str, ...]:
    if not _session_sequence_required(payload):
        return ()
    sequence = payload.session_sequence_state
    if sequence is None:
        return ("session_sequence_state_required",)

    reasons: list[str] = []
    if not sequence.available:
        reasons.append("session_sequence_state_unavailable")
    if sequence.source_label is None or not sequence.source_label.strip():
        reasons.append("session_sequence_source_label_required")
    if sequence.asia_complete is None:
        reasons.append("session_sequence_asia_complete_required")
    if sequence.london_complete is None:
        reasons.append("session_sequence_london_complete_required")
    if sequence.ny_active is None and sequence.ny_pending is None:
        reasons.append("session_sequence_ny_active_or_pending_required")
    if sequence.missing_fields:
        reasons.append("session_sequence_fields_missing:" + ",".join(sequence.missing_fields))
    reasons.extend(f"session_sequence_blocked:{reason}" for reason in sequence.blocking_reasons)
    return _dedupe(tuple(reasons))


def _range_structural_reasons(payload: SixELiveWorkstationInput) -> tuple[str, ...]:
    trigger = payload.trigger
    if trigger is not None and not trigger.range_context_required:
        return ()
    return _dedupe(
        _single_range_structural_reasons("asia", payload.asia_range_state, complete_required=True)
        + _single_range_structural_reasons("london", payload.london_range_state, complete_required=True)
        + _single_range_structural_reasons("ny", payload.ny_range_state, complete_required=False)
    )


def _single_range_structural_reasons(
    name: str,
    range_state: SixESessionRangeState | None,
    *,
    complete_required: bool,
) -> tuple[str, ...]:
    if range_state is None:
        return (f"{name}_range_state_required",)

    reasons: list[str] = []
    if not range_state.available:
        reasons.append(f"{name}_range_state_unavailable")
    if _number(range_state.high) is None:
        reasons.append(f"{name}_range_high_required")
    if _number(range_state.low) is None:
        reasons.append(f"{name}_range_low_required")
    high = _number(range_state.high)
    low = _number(range_state.low)
    if high is not None and low is not None and high < low:
        reasons.append(f"{name}_range_high_below_low")
    if complete_required and range_state.complete is not True:
        reasons.append(f"{name}_range_complete_required")
    if range_state.missing_fields:
        reasons.append(f"{name}_range_fields_missing:" + ",".join(range_state.missing_fields))
    reasons.extend(f"{name}_range_blocked:{reason}" for reason in range_state.blocking_reasons)
    return _dedupe(tuple(reasons))


def _thin_liquidity_structural_reasons(payload: SixELiveWorkstationInput) -> tuple[str, ...]:
    if not _thin_liquidity_required(payload):
        return ()
    thin = payload.thin_liquidity_state
    if thin is None:
        return ("thin_liquidity_state_required",)

    reasons: list[str] = []
    if not thin.available:
        reasons.append("thin_liquidity_state_unavailable")
    if thin.active is None:
        reasons.append("thin_liquidity_active_required")
    if thin.missing_fields:
        reasons.append("thin_liquidity_fields_missing:" + ",".join(thin.missing_fields))
    reasons.extend(f"thin_liquidity_blocked:{reason}" for reason in thin.blocking_reasons)
    return _dedupe(tuple(reasons))


def _dxy_gate_result(payload: SixELiveWorkstationInput) -> _DXYGateResult:
    dxy = payload.dxy_state
    trigger = payload.trigger
    value = _number(dxy.value if dxy is not None else None)
    change = _number(dxy.change if dxy is not None else None)
    if trigger is None or not trigger.dxy_required:
        return _DXYGateResult(value=value, change=change, passed=None, blocking_reasons=())
    structural = _dxy_structural_reasons(payload)
    if structural:
        return _DXYGateResult(value=value, change=change, passed=None, blocking_reasons=structural)
    assert change is not None
    threshold = float(trigger.dxy_change_threshold)
    if trigger.dxy_change_predicate == "at_or_above":
        passed = change >= threshold
    else:
        passed = change <= threshold
    return _DXYGateResult(value=value, change=change, passed=passed, blocking_reasons=())


def _session_gate_result(payload: SixELiveWorkstationInput) -> _SessionGateResult:
    trigger = payload.trigger
    if trigger is None or not trigger.session_sequence_required:
        return _SessionGateResult(passed=None, blocking_reasons=())
    structural = _session_sequence_structural_reasons(payload) + _range_structural_reasons(payload)
    if structural:
        return _SessionGateResult(passed=None, blocking_reasons=_dedupe(structural))
    sequence = payload.session_sequence_state
    assert sequence is not None
    passed = (
        sequence.asia_complete is True
        and sequence.london_complete is True
        and sequence.ny_active is True
        and sequence.ny_pending is not True
    )
    return _SessionGateResult(
        passed=passed,
        blocking_reasons=() if passed else ("session_sequence_predicate_failed",),
    )


def _invalidator_reasons(
    last_price: float,
    invalidators: tuple[SixEInvalidatorDefinition, ...],
) -> tuple[str, ...]:
    fired = tuple(
        invalidator
        for invalidator in invalidators
        if _number(invalidator.level) is not None
        and _price_crosses(last_price, float(invalidator.level), invalidator.direction)
    )
    return tuple(f"invalidator_fired:{invalidator.invalidator_id}" for invalidator in fired)


def _bar_state_blocking_reasons(bar_state: ContractBarState | None) -> tuple[str, ...]:
    if bar_state is None:
        return ("bar_state_required",)
    contract = normalize_contract_symbol(bar_state.contract)
    if contract != SIXE_CONTRACT:
        return (f"bar_contract_mismatch:{contract}",)
    return tuple(f"bar_state_blocked:{reason}" for reason in bar_state.blocking_reasons)


def _completed_bar_evidence(
    bar_state: ContractBarState | None,
    trigger: SixETriggerDefinition,
) -> SixECompletedBarEvidence:
    if bar_state is None:
        return SixECompletedBarEvidence(
            confirmed=False,
            completed_five_minute_bar_count=0,
            completed_one_minute_bar_count=0,
            latest_completed_five_minute_close=None,
            building_five_minute_present=False,
            blocking_reasons=("bar_state_required_for_confirmation",),
        )

    completed_five_minute = tuple(
        bar for bar in bar_state.completed_five_minute_bars if bool(getattr(bar, "completed", False))
    )
    completed_one_minute = tuple(
        bar for bar in bar_state.completed_one_minute_bars if bool(getattr(bar, "completed", False))
    )
    latest_close = _latest_completed_five_minute_close(completed_five_minute)
    building_present = bar_state.building_five_minute_bar is not None

    if not completed_five_minute:
        reasons = ["completed_five_minute_confirmation_required"]
        if building_present:
            reasons.append("building_five_minute_bar_not_confirmation")
        return SixECompletedBarEvidence(
            confirmed=False,
            completed_five_minute_bar_count=0,
            completed_one_minute_bar_count=len(completed_one_minute),
            latest_completed_five_minute_close=None,
            building_five_minute_present=building_present,
            blocking_reasons=tuple(reasons),
        )

    incomplete_completed_bar_seen = False
    confirming_close_without_one_minute_support = False
    for bar in completed_five_minute:
        if not _completed_five_minute_bar_is_usable(bar):
            incomplete_completed_bar_seen = True
            continue
        close = _number(getattr(bar, "close", None))
        if close is None:
            incomplete_completed_bar_seen = True
            continue
        if not _price_crosses(close, float(trigger.level), trigger.direction):
            continue
        if _has_required_completed_one_minute_support(bar, completed_one_minute):
            return SixECompletedBarEvidence(
                confirmed=True,
                completed_five_minute_bar_count=len(completed_five_minute),
                completed_one_minute_bar_count=len(completed_one_minute),
                latest_completed_five_minute_close=latest_close,
                building_five_minute_present=building_present,
                blocking_reasons=(),
            )
        confirming_close_without_one_minute_support = True

    reasons = []
    if confirming_close_without_one_minute_support:
        reasons.append("completed_one_minute_confirmation_bars_required")
    else:
        reasons.append("completed_five_minute_close_not_confirmed")
    if incomplete_completed_bar_seen:
        reasons.append("completed_five_minute_bar_requires_five_one_minute_bars")
    if building_present:
        reasons.append("building_five_minute_bar_not_confirmation")

    return SixECompletedBarEvidence(
        confirmed=False,
        completed_five_minute_bar_count=len(completed_five_minute),
        completed_one_minute_bar_count=len(completed_one_minute),
        latest_completed_five_minute_close=latest_close,
        building_five_minute_present=building_present,
        blocking_reasons=_dedupe(tuple(reasons)),
    )


def _empty_evidence(bar_state: ContractBarState | None) -> SixECompletedBarEvidence:
    if bar_state is None:
        return SixECompletedBarEvidence(
            confirmed=False,
            completed_five_minute_bar_count=0,
            completed_one_minute_bar_count=0,
            latest_completed_five_minute_close=None,
            building_five_minute_present=False,
        )
    return SixECompletedBarEvidence(
        confirmed=False,
        completed_five_minute_bar_count=len(bar_state.completed_five_minute_bars),
        completed_one_minute_bar_count=len(bar_state.completed_one_minute_bars),
        latest_completed_five_minute_close=_latest_completed_five_minute_close(bar_state.completed_five_minute_bars),
        building_five_minute_present=bar_state.building_five_minute_bar is not None,
    )


def _completed_five_minute_bar_is_usable(bar: object) -> bool:
    if not bool(getattr(bar, "completed", False)):
        return False
    if _number(getattr(bar, "contributing_bar_count", None)) != 5.0:
        return False
    quality = getattr(bar, "quality", None)
    return bool(getattr(quality, "usable", True))


def _has_required_completed_one_minute_support(
    five_minute_bar: object,
    completed_one_minute: tuple[object, ...],
) -> bool:
    start = _parse_timestamp(str(getattr(five_minute_bar, "start_time", "")))
    end = _parse_timestamp(str(getattr(five_minute_bar, "end_time", "")))
    if start is None or end is None:
        return False
    expected_starts = {start + timedelta(minutes=offset) for offset in range(5)}
    actual_starts = {
        parsed_start
        for bar in completed_one_minute
        if normalize_contract_symbol(str(getattr(bar, "contract", ""))) == SIXE_CONTRACT
        and bool(getattr(bar, "completed", False))
        for parsed_start in (_parse_timestamp(str(getattr(bar, "start_time", ""))),)
        if parsed_start is not None and start <= parsed_start < end
    }
    return actual_starts == expected_starts


def _latest_completed_five_minute_close(bars: tuple[object, ...]) -> float | None:
    for bar in reversed(bars):
        close = _number(getattr(bar, "close", None))
        if bool(getattr(bar, "completed", False)) and close is not None:
            return close
    return None


def _trigger_touched(price: float, trigger: SixETriggerDefinition) -> bool:
    return _price_crosses(price, float(trigger.level), trigger.direction)


def _within_approach_threshold(
    price: float,
    trigger: SixETriggerDefinition,
    *,
    tick_size: float,
) -> bool:
    threshold = float(trigger.approach_threshold_ticks) * tick_size
    level = float(trigger.level)
    if trigger.direction == "at_or_above":
        return level - threshold <= price < level
    return level < price <= level + threshold


def _price_crosses(price: float, level: float, direction: TriggerDirection) -> bool:
    if direction == "at_or_below":
        return price <= level
    return price >= level


def _required_fields(payload: SixELiveWorkstationInput) -> tuple[str, ...]:
    fields = [
        "contract",
        "quote.symbol",
        "quote.bid",
        "quote.ask",
        "quote.last",
        "quote.spread_ticks",
        "quote.fresh",
        "quote.symbol_match",
        "quote.required_fields_present",
        "event_lockout_state",
        "premarket_artifact",
        "trigger.setup_id",
        "trigger.trigger_id",
        "trigger.level",
        "bar_state",
    ]
    if _dxy_required(payload):
        fields.extend(("dxy_state.source_label", "dxy_state.change"))
    if _session_sequence_required(payload):
        fields.extend(
            (
                "session_sequence_state.asia_complete",
                "session_sequence_state.london_complete",
                "session_sequence_state.ny_active",
                "session_sequence_state.ny_pending",
            )
        )
    if _range_context_required(payload):
        fields.extend(
            (
                "asia_range_state.high",
                "asia_range_state.low",
                "london_range_state.high",
                "london_range_state.low",
                "ny_range_state.high",
                "ny_range_state.low",
            )
        )
    if _thin_liquidity_required(payload):
        fields.append("thin_liquidity_state.active")
    return tuple(fields)


def _missing_fields(payload: SixELiveWorkstationInput) -> tuple[str, ...]:
    missing: list[str] = []
    _append_missing_quote_fields(missing, payload.quote)
    if payload.event_lockout is None:
        missing.append("event_lockout_state")
    if payload.premarket_artifact is None or not payload.premarket_artifact.available:
        missing.append("premarket_artifact")
    trigger = payload.trigger
    if trigger is None:
        missing.extend(("trigger.setup_id", "trigger.trigger_id", "trigger.level"))
    else:
        if not trigger.setup_id.strip():
            missing.append("trigger.setup_id")
        if not trigger.trigger_id.strip():
            missing.append("trigger.trigger_id")
        if _number(trigger.level) is None:
            missing.append("trigger.level")
        if _number(trigger.dxy_change_threshold) is None:
            missing.append("trigger.dxy_change_threshold")
    if payload.bar_state is None:
        missing.append("bar_state")

    if _dxy_required(payload):
        _append_missing_dxy_fields(missing, payload.dxy_state)
    if _session_sequence_required(payload):
        _append_missing_session_sequence_fields(missing, payload.session_sequence_state)
    if _range_context_required(payload):
        _append_missing_range_fields(missing, "asia_range_state", payload.asia_range_state, complete_required=True)
        _append_missing_range_fields(missing, "london_range_state", payload.london_range_state, complete_required=True)
        _append_missing_range_fields(missing, "ny_range_state", payload.ny_range_state, complete_required=False)
    if _thin_liquidity_required(payload):
        _append_missing_thin_liquidity_fields(missing, payload.thin_liquidity_state)
    return _dedupe(tuple(missing))


def _append_missing_quote_fields(missing: list[str], quote: SixELiveQuoteInput | None) -> None:
    if quote is None:
        missing.extend(("quote.symbol", "quote.bid", "quote.ask", "quote.last", "quote.spread_ticks"))
        return
    if quote.symbol is None or not quote.symbol.strip():
        missing.append("quote.symbol")
    for field_name in ("bid", "ask", "last", "spread_ticks"):
        if _number(getattr(quote, field_name)) is None:
            missing.append(f"quote.{field_name}")
    if not quote.required_fields_present:
        missing.append("quote.required_fields_present")


def _append_missing_dxy_fields(missing: list[str], dxy: SixEDXYState | None) -> None:
    if dxy is None:
        missing.append("dxy_state")
        return
    if dxy.source_label is None or not dxy.source_label.strip():
        missing.append("dxy_state.source_label")
    if _number(dxy.change) is None:
        missing.append("dxy_state.change")
    missing.extend(f"dxy_state.{field}" for field in dxy.missing_fields)


def _append_missing_session_sequence_fields(
    missing: list[str],
    sequence: SixESessionSequenceState | None,
) -> None:
    if sequence is None:
        missing.append("session_sequence_state")
        return
    if sequence.asia_complete is None:
        missing.append("session_sequence_state.asia_complete")
    if sequence.london_complete is None:
        missing.append("session_sequence_state.london_complete")
    if sequence.ny_active is None and sequence.ny_pending is None:
        missing.append("session_sequence_state.ny_active_or_pending")
    missing.extend(f"session_sequence_state.{field}" for field in sequence.missing_fields)


def _append_missing_range_fields(
    missing: list[str],
    prefix: str,
    range_state: SixESessionRangeState | None,
    *,
    complete_required: bool,
) -> None:
    if range_state is None:
        missing.append(prefix)
        return
    if _number(range_state.high) is None:
        missing.append(f"{prefix}.high")
    if _number(range_state.low) is None:
        missing.append(f"{prefix}.low")
    if complete_required and range_state.complete is not True:
        missing.append(f"{prefix}.complete")
    missing.extend(f"{prefix}.{field}" for field in range_state.missing_fields)


def _append_missing_thin_liquidity_fields(
    missing: list[str],
    thin: SixEThinLiquidityState | None,
) -> None:
    if thin is None:
        missing.append("thin_liquidity_state")
        return
    if thin.active is None:
        missing.append("thin_liquidity_state.active")
    missing.extend(f"thin_liquidity_state.{field}" for field in thin.missing_fields)


def _source_classification(payload: SixELiveWorkstationInput) -> dict[str, SourceClassification]:
    return {
        "quote": payload.quote.source if payload.quote is not None else "unavailable",
        "quote_quality": "derived_from_schwab" if payload.quote is not None else "unavailable",
        "premarket_artifact": (
            payload.premarket_artifact.source if payload.premarket_artifact is not None else "unavailable"
        ),
        "trigger": payload.trigger.source if payload.trigger is not None else "unavailable",
        "event_lockout": payload.event_lockout.source if payload.event_lockout is not None else "unavailable",
        "bar_confirmation": "derived_from_schwab" if payload.bar_state is not None else "unavailable",
        "dxy": payload.dxy_state.source if payload.dxy_state is not None else "unavailable",
        "session_sequence": (
            payload.session_sequence_state.source if payload.session_sequence_state is not None else "unavailable"
        ),
        "asia_range": payload.asia_range_state.source if payload.asia_range_state is not None else "unavailable",
        "london_range": payload.london_range_state.source if payload.london_range_state is not None else "unavailable",
        "ny_range": payload.ny_range_state.source if payload.ny_range_state is not None else "unavailable",
        "thin_liquidity": (
            payload.thin_liquidity_state.source if payload.thin_liquidity_state is not None else "unavailable"
        ),
    }


def _dxy_required(payload: SixELiveWorkstationInput) -> bool:
    return True if payload.trigger is None else payload.trigger.dxy_required


def _session_sequence_required(payload: SixELiveWorkstationInput) -> bool:
    return True if payload.trigger is None else payload.trigger.session_sequence_required


def _range_context_required(payload: SixELiveWorkstationInput) -> bool:
    return True if payload.trigger is None else payload.trigger.range_context_required


def _thin_liquidity_required(payload: SixELiveWorkstationInput) -> bool:
    return True if payload.trigger is None else payload.trigger.thin_liquidity_state_required


def _number(value: object) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _parse_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _dedupe(reasons: tuple[str, ...]) -> tuple[str, ...]:
    deduped: list[str] = []
    for reason in reasons:
        normalized = str(reason).strip()
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return tuple(deduped)
