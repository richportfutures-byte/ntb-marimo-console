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


CL_LIVE_WORKSTATION_SCHEMA: Final[str] = "cl_live_workstation_v1"
CL_CONTRACT: Final[str] = "CL"

CLLiveWorkstationState = Literal[
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
CL_LIVE_WORKSTATION_STATES: Final[tuple[CLLiveWorkstationState, ...]] = (
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


@dataclass(frozen=True)
class CLTriggerDefinition:
    setup_id: str
    trigger_id: str
    level: float | int
    direction: TriggerDirection = "at_or_above"
    approach_threshold_ticks: int = 10
    requires_volume_prerequisite: bool = True
    requires_range_expansion_prerequisite: bool = True
    source: SourceClassification = "preserved_artifact"

    def to_dict(self) -> dict[str, object]:
        return {
            "setup_id": self.setup_id,
            "trigger_id": self.trigger_id,
            "level": self.level,
            "direction": self.direction,
            "approach_threshold_ticks": self.approach_threshold_ticks,
            "requires_volume_prerequisite": self.requires_volume_prerequisite,
            "requires_range_expansion_prerequisite": self.requires_range_expansion_prerequisite,
            "source": self.source,
        }


@dataclass(frozen=True)
class CLInvalidatorDefinition:
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
class CLPremarketArtifact:
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
class CLWorkstationEventLockout:
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
class CLPostEIASettlingState:
    active: bool = False
    blocking: bool = True
    reason: str | None = None
    source: SourceClassification = "manual_operator_input"

    def to_dict(self) -> dict[str, object]:
        return {
            "active": self.active,
            "blocking": self.blocking,
            "reason": self.reason,
            "source": self.source,
        }


@dataclass(frozen=True)
class CLPrerequisiteState:
    available: bool
    passed: bool
    state: str | None = None
    missing_fields: tuple[str, ...] = ()
    blocking_reasons: tuple[str, ...] = ()
    source: SourceClassification = "manual_operator_input"

    def to_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "passed": self.passed,
            "state": self.state,
            "missing_fields": list(self.missing_fields),
            "blocking_reasons": list(self.blocking_reasons),
            "source": self.source,
        }


@dataclass(frozen=True)
class CLLiveQuoteInput:
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
    def from_live_observable(cls, observable: ContractObservableV2) -> CLLiveQuoteInput:
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
class CLCompletedBarEvidence:
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
class CLWorkstationAuthorizations:
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
class CLLiveWorkstationInput:
    contract: str = CL_CONTRACT
    quote: CLLiveQuoteInput | None = None
    bar_state: ContractBarState | None = None
    premarket_artifact: CLPremarketArtifact | None = None
    trigger: CLTriggerDefinition | None = None
    invalidators: tuple[CLInvalidatorDefinition, ...] = ()
    event_lockout: CLWorkstationEventLockout | None = None
    eia_lockout: CLWorkstationEventLockout | None = None
    post_eia_settling: CLPostEIASettlingState | None = None
    volatility_state: CLPrerequisiteState | None = None
    volume_state: CLPrerequisiteState | None = None
    range_expansion_state: CLPrerequisiteState | None = None
    generated_at: str | None = None


@dataclass(frozen=True)
class CLLiveWorkstationReadModel:
    state: CLLiveWorkstationState
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
    eia_state: CLWorkstationEventLockout | None
    event_lockout_state: CLWorkstationEventLockout | None
    post_eia_settling_state: CLPostEIASettlingState | None
    volatility_state: CLPrerequisiteState | None
    volume_state: CLPrerequisiteState | None
    range_expansion_state: CLPrerequisiteState | None
    completed_bar_evidence: CLCompletedBarEvidence
    source_classification: Mapping[str, SourceClassification]
    generated_at: str | None = None
    authorizations: CLWorkstationAuthorizations = field(default_factory=CLWorkstationAuthorizations)
    decision_authority: str = "preserved_engine_only"
    read_model_only: bool = True
    schema: str = CL_LIVE_WORKSTATION_SCHEMA

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
            "eia_state": self.eia_state.to_dict() if self.eia_state is not None else None,
            "event_lockout_state": (
                self.event_lockout_state.to_dict() if self.event_lockout_state is not None else None
            ),
            "post_eia_settling_state": (
                self.post_eia_settling_state.to_dict() if self.post_eia_settling_state is not None else None
            ),
            "volatility_state": self.volatility_state.to_dict() if self.volatility_state is not None else None,
            "volume_state": self.volume_state.to_dict() if self.volume_state is not None else None,
            "range_expansion_state": (
                self.range_expansion_state.to_dict() if self.range_expansion_state is not None else None
            ),
            "completed_bar_evidence": self.completed_bar_evidence.to_dict(),
            "source_classification": dict(self.source_classification),
            "generated_at": self.generated_at,
            "pipeline_query_authorized": self.pipeline_query_authorized,
            "authorizations": self.authorizations.to_dict(),
            "decision_authority": self.decision_authority,
            "read_model_only": self.read_model_only,
        }


def evaluate_cl_live_workstation(payload: CLLiveWorkstationInput) -> CLLiveWorkstationReadModel:
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

    lockout_state_reasons = _required_lockout_state_reasons(payload)
    if lockout_state_reasons:
        return _read_model(
            "BLOCKED",
            payload,
            blocking_reasons=lockout_state_reasons,
            invalid_reasons=(),
            evidence=evidence,
            sources=sources,
        )

    assert payload.eia_lockout is not None
    assert payload.post_eia_settling is not None
    assert payload.event_lockout is not None

    if payload.eia_lockout.active:
        reason = payload.eia_lockout.reason or "eia_lockout_active"
        return _read_model(
            "LOCKOUT",
            payload,
            blocking_reasons=_dedupe(("eia_lockout_active", reason)),
            invalid_reasons=(),
            evidence=evidence,
            sources=sources,
        )

    if payload.post_eia_settling.active and payload.post_eia_settling.blocking:
        reason = payload.post_eia_settling.reason or "post_eia_settling_active"
        return _read_model(
            "LOCKOUT",
            payload,
            blocking_reasons=_dedupe(("post_eia_settling_active", reason)),
            invalid_reasons=(),
            evidence=evidence,
            sources=sources,
        )

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

    artifact_reasons = _artifact_blocking_reasons(payload.premarket_artifact, trigger)
    if artifact_reasons:
        state: CLLiveWorkstationState = "UNAVAILABLE" if "premarket_artifact_unavailable" in artifact_reasons else "BLOCKED"
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

    last_price = _number(quote.last)
    assert last_price is not None
    trigger_level = float(trigger.level)
    tick_size = contract_tick_size(CL_CONTRACT)
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

    prerequisite_reasons = _prerequisite_blocking_reasons(payload)
    if prerequisite_reasons:
        return _read_model(
            "BLOCKED",
            payload,
            blocking_reasons=prerequisite_reasons,
            invalid_reasons=(),
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
    if evidence.confirmed:
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

    state: CLLiveWorkstationState = "ARMED" if evidence.building_five_minute_present else "TOUCHED"
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


def _read_model(
    state: CLLiveWorkstationState,
    payload: CLLiveWorkstationInput,
    *,
    blocking_reasons: tuple[str, ...],
    invalid_reasons: tuple[str, ...],
    evidence: CLCompletedBarEvidence,
    sources: Mapping[str, SourceClassification],
    last_price: float | None = None,
    distance_ticks: float | None = None,
) -> CLLiveWorkstationReadModel:
    trigger = payload.trigger
    quote = payload.quote
    return CLLiveWorkstationReadModel(
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
        eia_state=payload.eia_lockout,
        event_lockout_state=payload.event_lockout,
        post_eia_settling_state=payload.post_eia_settling,
        volatility_state=payload.volatility_state,
        volume_state=payload.volume_state,
        range_expansion_state=payload.range_expansion_state,
        completed_bar_evidence=evidence,
        source_classification=sources,
        generated_at=payload.generated_at,
    )


def _contract_blocking_reasons(contract: str, quote: CLLiveQuoteInput | None) -> tuple[str, ...]:
    reasons: list[str] = []
    if contract != CL_CONTRACT:
        if is_never_supported_contract(contract):
            reasons.append(f"never_supported_contract:{contract}")
        elif is_excluded_final_target_contract(contract):
            reasons.append(f"excluded_contract:{contract}")
        elif is_final_target_contract(contract):
            reasons.append(f"contract_not_onboarded_for_cl_workstation:{contract}")
        else:
            reasons.append(f"unsupported_contract:{contract}")
        reasons.append("cl_workstation_supports_cl_only")

    if quote is not None:
        quote_contract = normalize_contract_symbol(quote.contract)
        if quote_contract != CL_CONTRACT:
            reasons.append(f"quote_contract_mismatch:{quote_contract}")
    return _dedupe(tuple(reasons))


def _required_lockout_state_reasons(payload: CLLiveWorkstationInput) -> tuple[str, ...]:
    reasons: list[str] = []
    if payload.eia_lockout is None:
        reasons.append("eia_lockout_state_required")
    if payload.post_eia_settling is None:
        reasons.append("post_eia_settling_state_required")
    if payload.event_lockout is None:
        reasons.append("event_lockout_state_required")
    return tuple(reasons)


def _artifact_blocking_reasons(
    artifact: CLPremarketArtifact | None,
    trigger: CLTriggerDefinition | None,
) -> tuple[str, ...]:
    if artifact is None:
        return ("premarket_artifact_required",)
    if not artifact.available:
        return ("premarket_artifact_unavailable",)
    if trigger is None:
        return ("premarket_trigger_required",)
    return ()


def _trigger_blocking_reasons(trigger: CLTriggerDefinition) -> tuple[str, ...]:
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
    return tuple(reasons)


def _quote_structural_reasons(quote: CLLiveQuoteInput) -> tuple[str, ...]:
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


def _quote_freshness_reasons(quote: CLLiveQuoteInput) -> tuple[str, ...]:
    if quote.fresh:
        return ()
    return _dedupe(("quote_stale",) + quote.blocking_reasons)


def _invalidator_reasons(
    last_price: float,
    invalidators: tuple[CLInvalidatorDefinition, ...],
) -> tuple[str, ...]:
    fired = tuple(
        invalidator
        for invalidator in invalidators
        if _number(invalidator.level) is not None
        and _price_crosses(last_price, float(invalidator.level), invalidator.direction)
    )
    return tuple(f"invalidator_fired:{invalidator.invalidator_id}" for invalidator in fired)


def _prerequisite_blocking_reasons(payload: CLLiveWorkstationInput) -> tuple[str, ...]:
    trigger = payload.trigger
    assert trigger is not None
    reasons = _single_prerequisite_blocking_reasons("volatility", payload.volatility_state, required=True)
    reasons += _single_prerequisite_blocking_reasons(
        "volume",
        payload.volume_state,
        required=trigger.requires_volume_prerequisite,
    )
    reasons += _single_prerequisite_blocking_reasons(
        "range_expansion",
        payload.range_expansion_state,
        required=trigger.requires_range_expansion_prerequisite,
    )
    return _dedupe(reasons)


def _single_prerequisite_blocking_reasons(
    name: str,
    prerequisite: CLPrerequisiteState | None,
    *,
    required: bool,
) -> tuple[str, ...]:
    if not required:
        return ()
    if prerequisite is None:
        return (f"{name}_state_required",)

    reasons: list[str] = []
    if not prerequisite.available:
        reasons.append(f"{name}_state_unavailable")
    if prerequisite.missing_fields:
        reasons.append(f"{name}_fields_missing:{','.join(prerequisite.missing_fields)}")
    if not prerequisite.passed:
        reasons.append(f"{name}_prerequisite_not_passed")
    reasons.extend(f"{name}_blocked:{reason}" for reason in prerequisite.blocking_reasons)
    return _dedupe(tuple(reasons))


def _bar_state_blocking_reasons(bar_state: ContractBarState | None) -> tuple[str, ...]:
    if bar_state is None:
        return ("bar_state_required",)
    contract = normalize_contract_symbol(bar_state.contract)
    if contract != CL_CONTRACT:
        return (f"bar_contract_mismatch:{contract}",)
    return tuple(f"bar_state_blocked:{reason}" for reason in bar_state.blocking_reasons)


def _completed_bar_evidence(
    bar_state: ContractBarState | None,
    trigger: CLTriggerDefinition,
) -> CLCompletedBarEvidence:
    if bar_state is None:
        return CLCompletedBarEvidence(
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
        return CLCompletedBarEvidence(
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
            return CLCompletedBarEvidence(
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

    return CLCompletedBarEvidence(
        confirmed=False,
        completed_five_minute_bar_count=len(completed_five_minute),
        completed_one_minute_bar_count=len(completed_one_minute),
        latest_completed_five_minute_close=latest_close,
        building_five_minute_present=building_present,
        blocking_reasons=_dedupe(tuple(reasons)),
    )


def _empty_evidence(bar_state: ContractBarState | None) -> CLCompletedBarEvidence:
    if bar_state is None:
        return CLCompletedBarEvidence(
            confirmed=False,
            completed_five_minute_bar_count=0,
            completed_one_minute_bar_count=0,
            latest_completed_five_minute_close=None,
            building_five_minute_present=False,
        )
    return CLCompletedBarEvidence(
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
        if normalize_contract_symbol(str(getattr(bar, "contract", ""))) == CL_CONTRACT
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


def _trigger_touched(price: float, trigger: CLTriggerDefinition) -> bool:
    return _price_crosses(price, float(trigger.level), trigger.direction)


def _within_approach_threshold(
    price: float,
    trigger: CLTriggerDefinition,
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


def _required_fields(payload: CLLiveWorkstationInput) -> tuple[str, ...]:
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
        "eia_lockout_state",
        "post_eia_settling_state",
        "premarket_artifact",
        "trigger.setup_id",
        "trigger.trigger_id",
        "trigger.level",
        "bar_state",
        "volatility_state",
    ]
    trigger = payload.trigger
    if trigger is not None and trigger.requires_volume_prerequisite:
        fields.append("volume_state")
    if trigger is not None and trigger.requires_range_expansion_prerequisite:
        fields.append("range_expansion_state")
    return tuple(fields)


def _missing_fields(payload: CLLiveWorkstationInput) -> tuple[str, ...]:
    missing: list[str] = []
    quote = payload.quote
    trigger = payload.trigger

    if quote is None:
        missing.extend(
            (
                "quote.symbol",
                "quote.bid",
                "quote.ask",
                "quote.last",
                "quote.spread_ticks",
            )
        )
    else:
        if quote.symbol is None or not quote.symbol.strip():
            missing.append("quote.symbol")
        for field_name in ("bid", "ask", "last", "spread_ticks"):
            if _number(getattr(quote, field_name)) is None:
                missing.append(f"quote.{field_name}")
        if not quote.required_fields_present:
            missing.append("quote.required_fields_present")

    if payload.event_lockout is None:
        missing.append("event_lockout_state")
    if payload.eia_lockout is None:
        missing.append("eia_lockout_state")
    if payload.post_eia_settling is None:
        missing.append("post_eia_settling_state")
    if payload.premarket_artifact is None or not payload.premarket_artifact.available:
        missing.append("premarket_artifact")
    if trigger is None:
        missing.extend(("trigger.setup_id", "trigger.trigger_id", "trigger.level"))
    else:
        if not trigger.setup_id.strip():
            missing.append("trigger.setup_id")
        if not trigger.trigger_id.strip():
            missing.append("trigger.trigger_id")
        if _number(trigger.level) is None:
            missing.append("trigger.level")

    if payload.bar_state is None:
        missing.append("bar_state")

    missing.extend(_missing_prerequisite_fields("volatility", payload.volatility_state, required=True))
    if trigger is not None and trigger.requires_volume_prerequisite:
        missing.extend(_missing_prerequisite_fields("volume", payload.volume_state, required=True))
    if trigger is not None and trigger.requires_range_expansion_prerequisite:
        missing.extend(_missing_prerequisite_fields("range_expansion", payload.range_expansion_state, required=True))
    return _dedupe(tuple(missing))


def _missing_prerequisite_fields(
    name: str,
    prerequisite: CLPrerequisiteState | None,
    *,
    required: bool,
) -> tuple[str, ...]:
    if not required:
        return ()
    if prerequisite is None:
        return (f"{name}_state",)
    return tuple(f"{name}.{field}" for field in prerequisite.missing_fields)


def _source_classification(payload: CLLiveWorkstationInput) -> dict[str, SourceClassification]:
    quote_available = payload.quote is not None
    return {
        "quote": payload.quote.source if quote_available else "unavailable",
        "quote_quality": "derived_from_schwab" if quote_available else "unavailable",
        "premarket_artifact": (
            payload.premarket_artifact.source if payload.premarket_artifact is not None else "unavailable"
        ),
        "trigger": payload.trigger.source if payload.trigger is not None else "unavailable",
        "event_lockout": payload.event_lockout.source if payload.event_lockout is not None else "unavailable",
        "eia_lockout": payload.eia_lockout.source if payload.eia_lockout is not None else "unavailable",
        "post_eia_settling": (
            payload.post_eia_settling.source if payload.post_eia_settling is not None else "unavailable"
        ),
        "bar_confirmation": "derived_from_schwab" if payload.bar_state is not None else "unavailable",
        "volatility": payload.volatility_state.source if payload.volatility_state is not None else "unavailable",
        "volume": payload.volume_state.source if payload.volume_state is not None else "unavailable",
        "range_expansion": (
            payload.range_expansion_state.source if payload.range_expansion_state is not None else "unavailable"
        ),
    }


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
