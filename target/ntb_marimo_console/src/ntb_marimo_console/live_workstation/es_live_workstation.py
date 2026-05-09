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


ES_LIVE_WORKSTATION_SCHEMA: Final[str] = "es_live_workstation_v1"
ES_CONTRACT: Final[str] = "ES"

ESLiveWorkstationState = Literal[
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
ES_LIVE_WORKSTATION_STATES: Final[tuple[ESLiveWorkstationState, ...]] = (
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

SourceClassification = Literal[
    "observed_from_schwab",
    "derived_from_schwab",
    "preserved_artifact",
    "manual_operator_input",
    "unavailable",
]
TriggerDirection = Literal["at_or_above", "at_or_below"]


@dataclass(frozen=True)
class ESTriggerDefinition:
    trigger_id: str
    level: float | int
    direction: TriggerDirection = "at_or_above"
    approach_threshold_ticks: int = 4
    source: SourceClassification = "preserved_artifact"

    def to_dict(self) -> dict[str, object]:
        return {
            "trigger_id": self.trigger_id,
            "level": self.level,
            "direction": self.direction,
            "approach_threshold_ticks": self.approach_threshold_ticks,
            "source": self.source,
        }


@dataclass(frozen=True)
class ESInvalidatorDefinition:
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
class ESPremarketArtifact:
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
class ESWorkstationEventLockout:
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
class ESLiveQuoteInput:
    contract: str
    symbol: str | None
    bid: float | int | None
    ask: float | int | None
    last: float | int | None
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
    def from_live_observable(cls, observable: ContractObservableV2) -> ESLiveQuoteInput:
        return cls(
            contract=observable.contract,
            symbol=observable.symbol,
            bid=observable.quote.bid,
            ask=observable.quote.ask,
            last=observable.quote.last,
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
class ESWorkstationConfirmationFacts:
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
class ESWorkstationAuthorizations:
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
class ESLiveWorkstationInput:
    contract: str = ES_CONTRACT
    quote: ESLiveQuoteInput | None = None
    bar_state: ContractBarState | None = None
    premarket_artifact: ESPremarketArtifact | None = None
    trigger: ESTriggerDefinition | None = None
    invalidators: tuple[ESInvalidatorDefinition, ...] = ()
    event_lockout: ESWorkstationEventLockout = field(default_factory=ESWorkstationEventLockout)


@dataclass(frozen=True)
class ESLiveWorkstationReadModel:
    state: ESLiveWorkstationState
    contract: str
    symbol: str | None
    trigger_id: str | None
    trigger_level: float | None
    last_price: float | None
    distance_to_trigger_ticks: float | None
    blocking_reasons: tuple[str, ...]
    confirmation: ESWorkstationConfirmationFacts
    source_classification: Mapping[str, SourceClassification]
    authorizations: ESWorkstationAuthorizations = field(default_factory=ESWorkstationAuthorizations)
    decision_authority: str = "preserved_engine_only"
    read_model_only: bool = True
    schema: str = ES_LIVE_WORKSTATION_SCHEMA

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "state": self.state,
            "contract": self.contract,
            "symbol": self.symbol,
            "trigger_id": self.trigger_id,
            "trigger_level": self.trigger_level,
            "last_price": self.last_price,
            "distance_to_trigger_ticks": self.distance_to_trigger_ticks,
            "blocking_reasons": list(self.blocking_reasons),
            "confirmation": self.confirmation.to_dict(),
            "source_classification": dict(self.source_classification),
            "authorizations": self.authorizations.to_dict(),
            "decision_authority": self.decision_authority,
            "read_model_only": self.read_model_only,
        }


def evaluate_es_live_workstation(payload: ESLiveWorkstationInput) -> ESLiveWorkstationReadModel:
    contract = normalize_contract_symbol(payload.contract)
    quote = payload.quote
    trigger = payload.trigger
    confirmation = _empty_confirmation(payload.bar_state)
    sources = _source_classification(payload)

    contract_reasons = _contract_blocking_reasons(contract, quote)
    if contract_reasons:
        return _read_model(
            "BLOCKED",
            payload,
            blocking_reasons=contract_reasons,
            confirmation=confirmation,
            sources=sources,
        )

    if payload.event_lockout.active:
        reason = payload.event_lockout.reason or "event_lockout_active"
        return _read_model(
            "LOCKOUT",
            payload,
            blocking_reasons=_dedupe(("event_lockout_active", reason)),
            confirmation=confirmation,
            sources=sources,
        )

    artifact_reasons = _artifact_blocking_reasons(payload.premarket_artifact, trigger)
    if artifact_reasons:
        state: ESLiveWorkstationState = "UNAVAILABLE" if "premarket_artifact_unavailable" in artifact_reasons else "BLOCKED"
        return _read_model(
            state,
            payload,
            blocking_reasons=artifact_reasons,
            confirmation=confirmation,
            sources=sources,
        )

    assert trigger is not None
    trigger_reasons = _trigger_blocking_reasons(trigger)
    if trigger_reasons:
        return _read_model(
            "BLOCKED",
            payload,
            blocking_reasons=trigger_reasons,
            confirmation=confirmation,
            sources=sources,
        )

    if quote is None:
        return _read_model(
            "UNAVAILABLE",
            payload,
            blocking_reasons=("quote_required",),
            confirmation=confirmation,
            sources=sources,
        )

    quote_structural_reasons = _quote_structural_reasons(quote)
    if quote_structural_reasons:
        return _read_model(
            "BLOCKED",
            payload,
            blocking_reasons=quote_structural_reasons,
            confirmation=confirmation,
            sources=sources,
        )

    quote_freshness_reasons = _quote_freshness_reasons(quote)
    if quote_freshness_reasons:
        return _read_model(
            "STALE",
            payload,
            blocking_reasons=quote_freshness_reasons,
            confirmation=confirmation,
            sources=sources,
        )

    last_price = _number(quote.last)
    assert last_price is not None
    trigger_level = float(trigger.level)
    tick_size = contract_tick_size(ES_CONTRACT)
    assert tick_size is not None
    distance_ticks = round(abs(last_price - trigger_level) / tick_size, 10)

    invalidator_reasons = _invalidator_reasons(last_price, payload.invalidators)
    if invalidator_reasons:
        return _read_model(
            "INVALIDATED",
            payload,
            blocking_reasons=invalidator_reasons,
            confirmation=confirmation,
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
            confirmation=_confirmation_facts(payload.bar_state, trigger),
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
                confirmation=confirmation,
                sources=sources,
                last_price=last_price,
                distance_ticks=distance_ticks,
            )
        return _read_model(
            "DORMANT",
            payload,
            blocking_reasons=("price_outside_approach_threshold",),
            confirmation=confirmation,
            sources=sources,
            last_price=last_price,
            distance_ticks=distance_ticks,
        )

    confirmation = _confirmation_facts(payload.bar_state, trigger)
    if confirmation.confirmed:
        return _read_model(
            "QUERY_READY",
            payload,
            blocking_reasons=(),
            confirmation=confirmation,
            sources=sources,
            last_price=last_price,
            distance_ticks=distance_ticks,
        )

    state: ESLiveWorkstationState = "ARMED" if confirmation.building_five_minute_present else "TOUCHED"
    return _read_model(
        state,
        payload,
        blocking_reasons=confirmation.blocking_reasons,
        confirmation=confirmation,
        sources=sources,
        last_price=last_price,
        distance_ticks=distance_ticks,
    )


def _read_model(
    state: ESLiveWorkstationState,
    payload: ESLiveWorkstationInput,
    *,
    blocking_reasons: tuple[str, ...],
    confirmation: ESWorkstationConfirmationFacts,
    sources: Mapping[str, SourceClassification],
    last_price: float | None = None,
    distance_ticks: float | None = None,
) -> ESLiveWorkstationReadModel:
    trigger = payload.trigger
    quote = payload.quote
    return ESLiveWorkstationReadModel(
        state=state,
        contract=normalize_contract_symbol(payload.contract),
        symbol=quote.symbol if quote is not None else None,
        trigger_id=trigger.trigger_id if trigger is not None else None,
        trigger_level=float(trigger.level) if trigger is not None and _number(trigger.level) is not None else None,
        last_price=last_price,
        distance_to_trigger_ticks=distance_ticks,
        blocking_reasons=_dedupe(blocking_reasons),
        confirmation=confirmation,
        source_classification=sources,
    )


def _contract_blocking_reasons(contract: str, quote: ESLiveQuoteInput | None) -> tuple[str, ...]:
    reasons: list[str] = []
    if contract != ES_CONTRACT:
        if is_never_supported_contract(contract):
            reasons.append(f"never_supported_contract:{contract}")
        elif is_excluded_final_target_contract(contract):
            reasons.append(f"excluded_contract:{contract}")
        elif is_final_target_contract(contract):
            reasons.append(f"contract_not_onboarded_for_es_workstation:{contract}")
        else:
            reasons.append(f"unsupported_contract:{contract}")
        reasons.append("es_workstation_supports_es_only")

    if quote is not None:
        quote_contract = normalize_contract_symbol(quote.contract)
        if quote_contract != ES_CONTRACT:
            reasons.append(f"quote_contract_mismatch:{quote_contract}")
    return _dedupe(tuple(reasons))


def _artifact_blocking_reasons(
    artifact: ESPremarketArtifact | None,
    trigger: ESTriggerDefinition | None,
) -> tuple[str, ...]:
    if artifact is None:
        return ("premarket_artifact_required",)
    if not artifact.available:
        return ("premarket_artifact_unavailable",)
    if trigger is None:
        return ("premarket_trigger_required",)
    return ()


def _trigger_blocking_reasons(trigger: ESTriggerDefinition) -> tuple[str, ...]:
    reasons: list[str] = []
    if not trigger.trigger_id.strip():
        reasons.append("trigger_id_required")
    if _number(trigger.level) is None:
        reasons.append("trigger_level_required")
    if trigger.direction not in ("at_or_above", "at_or_below"):
        reasons.append(f"unsupported_trigger_direction:{trigger.direction}")
    if trigger.approach_threshold_ticks < 0:
        reasons.append("approach_threshold_ticks_must_be_non_negative")
    return tuple(reasons)


def _quote_structural_reasons(quote: ESLiveQuoteInput) -> tuple[str, ...]:
    reasons: list[str] = []
    if quote.symbol is None or not quote.symbol.strip():
        reasons.append("quote_symbol_required")
    if not quote.symbol_match:
        reasons.append("quote_symbol_mismatch")
    if not quote.required_fields_present:
        reasons.append("missing_required_quote_fields")
    for field_name in ("bid", "ask", "last"):
        if _number(getattr(quote, field_name)) is None:
            reasons.append(f"quote_{field_name}_required")
    bid = _number(quote.bid)
    ask = _number(quote.ask)
    if bid is not None and ask is not None and bid > ask:
        reasons.append("malformed_quote_bid_above_ask")
    if reasons:
        reasons.extend(quote.blocking_reasons)
    return _dedupe(tuple(reasons))


def _quote_freshness_reasons(quote: ESLiveQuoteInput) -> tuple[str, ...]:
    if quote.fresh:
        return ()
    return _dedupe(("quote_stale",) + quote.blocking_reasons)


def _invalidator_reasons(
    last_price: float,
    invalidators: tuple[ESInvalidatorDefinition, ...],
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
        return ()
    contract = normalize_contract_symbol(bar_state.contract)
    if contract != ES_CONTRACT:
        return (f"bar_contract_mismatch:{contract}",)
    return tuple(f"bar_state_blocked:{reason}" for reason in bar_state.blocking_reasons)


def _confirmation_facts(
    bar_state: ContractBarState | None,
    trigger: ESTriggerDefinition,
) -> ESWorkstationConfirmationFacts:
    if bar_state is None:
        return ESWorkstationConfirmationFacts(
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
        return ESWorkstationConfirmationFacts(
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
            return ESWorkstationConfirmationFacts(
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

    return ESWorkstationConfirmationFacts(
        confirmed=False,
        completed_five_minute_bar_count=len(completed_five_minute),
        completed_one_minute_bar_count=len(completed_one_minute),
        latest_completed_five_minute_close=latest_close,
        building_five_minute_present=building_present,
        blocking_reasons=_dedupe(tuple(reasons)),
    )


def _empty_confirmation(bar_state: ContractBarState | None) -> ESWorkstationConfirmationFacts:
    if bar_state is None:
        return ESWorkstationConfirmationFacts(
            confirmed=False,
            completed_five_minute_bar_count=0,
            completed_one_minute_bar_count=0,
            latest_completed_five_minute_close=None,
            building_five_minute_present=False,
        )
    return ESWorkstationConfirmationFacts(
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
        if normalize_contract_symbol(str(getattr(bar, "contract", ""))) == ES_CONTRACT
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


def _trigger_touched(price: float, trigger: ESTriggerDefinition) -> bool:
    return _price_crosses(price, float(trigger.level), trigger.direction)


def _within_approach_threshold(
    price: float,
    trigger: ESTriggerDefinition,
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


def _source_classification(payload: ESLiveWorkstationInput) -> dict[str, SourceClassification]:
    quote_available = payload.quote is not None
    return {
        "quote": payload.quote.source if quote_available else "unavailable",
        "quote_quality": "derived_from_schwab" if quote_available else "unavailable",
        "premarket_artifact": (
            payload.premarket_artifact.source if payload.premarket_artifact is not None else "unavailable"
        ),
        "trigger": payload.trigger.source if payload.trigger is not None else "unavailable",
        "event_lockout": payload.event_lockout.source,
        "bar_confirmation": "derived_from_schwab" if payload.bar_state is not None else "unavailable",
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
