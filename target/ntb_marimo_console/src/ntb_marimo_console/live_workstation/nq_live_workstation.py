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


NQ_LIVE_WORKSTATION_SCHEMA: Final[str] = "nq_live_workstation_v1"
NQ_CONTRACT: Final[str] = "NQ"
ES_CONTEXT_CONTRACT: Final[str] = "ES"

NQLiveWorkstationState = Literal[
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
NQ_LIVE_WORKSTATION_STATES: Final[tuple[NQLiveWorkstationState, ...]] = (
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

NQAnchorKind = Literal["prior_close", "rth_open", "premarket_plan_anchor", "unavailable"]
RelativeStrengthPredicate = Literal["at_or_above", "at_or_below"]


@dataclass(frozen=True)
class NQAnchor:
    kind: NQAnchorKind
    value: float | int | None
    source: SourceClassification = "manual_operator_input"

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "value": self.value,
            "source": self.source,
        }


@dataclass(frozen=True)
class NQLeadershipProxyState:
    available: bool = False
    state: str | None = "unavailable"
    source: SourceClassification = "unavailable"
    missing_fields: tuple[str, ...] = ()
    blocking_reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "available": self.available,
            "state": self.state,
            "source": self.source,
            "missing_fields": list(self.missing_fields),
            "blocking_reasons": list(self.blocking_reasons),
        }


@dataclass(frozen=True)
class NQTriggerDefinition:
    setup_id: str
    trigger_id: str
    level: float | int
    direction: TriggerDirection = "at_or_above"
    approach_threshold_ticks: int = 12
    relative_strength_required: bool = True
    relative_strength_threshold: float | int = 0.0
    relative_strength_predicate: RelativeStrengthPredicate = "at_or_above"
    source: SourceClassification = "preserved_artifact"

    def to_dict(self) -> dict[str, object]:
        return {
            "setup_id": self.setup_id,
            "trigger_id": self.trigger_id,
            "level": self.level,
            "direction": self.direction,
            "approach_threshold_ticks": self.approach_threshold_ticks,
            "relative_strength_required": self.relative_strength_required,
            "relative_strength_threshold": self.relative_strength_threshold,
            "relative_strength_predicate": self.relative_strength_predicate,
            "source": self.source,
        }


@dataclass(frozen=True)
class NQInvalidatorDefinition:
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
class NQPremarketArtifact:
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
class NQWorkstationEventLockout:
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
class NQLiveQuoteInput:
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
    def from_live_observable(cls, observable: ContractObservableV2) -> NQLiveQuoteInput:
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
class NQBarEvidence:
    contract: str
    confirmed: bool
    completed_five_minute_bar_count: int
    completed_one_minute_bar_count: int
    latest_completed_five_minute_close: float | None
    building_five_minute_present: bool
    blocking_reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "confirmed": self.confirmed,
            "completed_five_minute_bar_count": self.completed_five_minute_bar_count,
            "completed_one_minute_bar_count": self.completed_one_minute_bar_count,
            "latest_completed_five_minute_close": self.latest_completed_five_minute_close,
            "building_five_minute_present": self.building_five_minute_present,
            "blocking_reasons": list(self.blocking_reasons),
        }


@dataclass(frozen=True)
class NQCompletedBarEvidence:
    nq: NQBarEvidence
    es: NQBarEvidence | None = None

    @property
    def confirmed(self) -> bool:
        return self.nq.confirmed

    def to_dict(self) -> dict[str, object]:
        return {
            "nq": self.nq.to_dict(),
            "es": self.es.to_dict() if self.es is not None else None,
        }


@dataclass(frozen=True)
class NQWorkstationAuthorizations:
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
class NQLiveWorkstationInput:
    contract: str = NQ_CONTRACT
    nq_quote: NQLiveQuoteInput | None = None
    es_quote: NQLiveQuoteInput | None = None
    nq_bar_state: ContractBarState | None = None
    es_bar_state: ContractBarState | None = None
    nq_anchor: NQAnchor | None = None
    es_anchor: NQAnchor | None = None
    premarket_artifact: NQPremarketArtifact | None = None
    trigger: NQTriggerDefinition | None = None
    invalidators: tuple[NQInvalidatorDefinition, ...] = ()
    event_lockout: NQWorkstationEventLockout | None = None
    leadership_proxy_state: NQLeadershipProxyState | None = None
    generated_at: str | None = None


@dataclass(frozen=True)
class NQLiveWorkstationReadModel:
    state: NQLiveWorkstationState
    contract: str
    symbol: str | None
    es_symbol: str | None
    setup_id: str | None
    trigger_id: str | None
    trigger_level: float | None
    last_price: float | None
    distance_to_trigger_ticks: float | None
    required_fields: tuple[str, ...]
    missing_fields: tuple[str, ...]
    blocking_reasons: tuple[str, ...]
    invalid_reasons: tuple[str, ...]
    nq_anchor: NQAnchor | None
    es_anchor: NQAnchor | None
    nq_return_since_anchor: float | None
    es_return_since_anchor: float | None
    relative_strength_vs_es: float | None
    relative_strength_required: bool
    relative_strength_passed: bool | None
    leadership_proxy_state: NQLeadershipProxyState
    completed_bar_evidence: NQCompletedBarEvidence
    event_lockout_state: NQWorkstationEventLockout | None
    source_classification: Mapping[str, SourceClassification]
    generated_at: str | None = None
    authorizations: NQWorkstationAuthorizations = field(default_factory=NQWorkstationAuthorizations)
    decision_authority: str = "preserved_engine_only"
    read_model_only: bool = True
    schema: str = NQ_LIVE_WORKSTATION_SCHEMA

    @property
    def pipeline_query_authorized(self) -> bool:
        return self.authorizations.pipeline_query_authorized

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "state": self.state,
            "contract": self.contract,
            "symbol": self.symbol,
            "es_symbol": self.es_symbol,
            "setup_id": self.setup_id,
            "trigger_id": self.trigger_id,
            "trigger_level": self.trigger_level,
            "last_price": self.last_price,
            "distance_to_trigger_ticks": self.distance_to_trigger_ticks,
            "required_fields": list(self.required_fields),
            "missing_fields": list(self.missing_fields),
            "blocking_reasons": list(self.blocking_reasons),
            "invalid_reasons": list(self.invalid_reasons),
            "nq_anchor": self.nq_anchor.to_dict() if self.nq_anchor is not None else None,
            "es_anchor": self.es_anchor.to_dict() if self.es_anchor is not None else None,
            "nq_return_since_anchor": self.nq_return_since_anchor,
            "es_return_since_anchor": self.es_return_since_anchor,
            "relative_strength_vs_es": self.relative_strength_vs_es,
            "relative_strength_required": self.relative_strength_required,
            "relative_strength_passed": self.relative_strength_passed,
            "leadership_proxy_state": self.leadership_proxy_state.to_dict(),
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
class _RelativeStrengthResult:
    nq_return: float | None
    es_return: float | None
    relative_strength: float | None
    passed: bool | None
    blocking_reasons: tuple[str, ...]


def evaluate_nq_live_workstation(payload: NQLiveWorkstationInput) -> NQLiveWorkstationReadModel:
    contract = normalize_contract_symbol(payload.contract)
    trigger = payload.trigger
    evidence = _empty_completed_bar_evidence(payload)
    sources = _source_classification(payload)

    contract_reasons = _contract_blocking_reasons(contract, payload.nq_quote, payload.es_quote, trigger)
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

    artifact_reasons = _artifact_blocking_reasons(payload.premarket_artifact, trigger)
    if artifact_reasons:
        state: NQLiveWorkstationState = "UNAVAILABLE" if "premarket_artifact_unavailable" in artifact_reasons else "BLOCKED"
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

    evidence = _completed_bar_evidence(payload, trigger)

    if payload.nq_quote is None:
        return _read_model(
            "UNAVAILABLE",
            payload,
            blocking_reasons=("nq_quote_required",),
            invalid_reasons=(),
            evidence=evidence,
            sources=sources,
        )

    nq_quote_structural_reasons = _quote_structural_reasons("nq", payload.nq_quote)
    if nq_quote_structural_reasons:
        return _read_model(
            "BLOCKED",
            payload,
            blocking_reasons=nq_quote_structural_reasons,
            invalid_reasons=(),
            evidence=evidence,
            sources=sources,
        )

    nq_quote_freshness_reasons = _quote_freshness_reasons("nq", payload.nq_quote)
    if nq_quote_freshness_reasons:
        return _read_model(
            "STALE",
            payload,
            blocking_reasons=nq_quote_freshness_reasons,
            invalid_reasons=(),
            evidence=evidence,
            sources=sources,
        )

    if trigger.relative_strength_required:
        es_quote_reasons = _es_quote_blocking_reasons(payload.es_quote)
        if es_quote_reasons:
            return _read_model(
                "BLOCKED",
                payload,
                blocking_reasons=es_quote_reasons,
                invalid_reasons=(),
                evidence=evidence,
                sources=sources,
            )

    anchor_reasons = _anchor_blocking_reasons(payload)
    if anchor_reasons:
        return _read_model(
            "BLOCKED",
            payload,
            blocking_reasons=anchor_reasons,
            invalid_reasons=(),
            evidence=evidence,
            sources=sources,
        )

    relative_strength = _relative_strength_result(payload)
    if trigger.relative_strength_required and relative_strength.blocking_reasons:
        return _read_model(
            "BLOCKED",
            payload,
            blocking_reasons=relative_strength.blocking_reasons,
            invalid_reasons=(),
            evidence=evidence,
            sources=sources,
        )

    nq_last_price = _number(payload.nq_quote.last)
    assert nq_last_price is not None
    tick_size = contract_tick_size(NQ_CONTRACT)
    assert tick_size is not None
    distance_ticks = round(abs(nq_last_price - float(trigger.level)) / tick_size, 10)

    invalid_reasons = _invalidator_reasons(nq_last_price, payload.invalidators)
    if invalid_reasons:
        return _read_model(
            "INVALIDATED",
            payload,
            blocking_reasons=invalid_reasons,
            invalid_reasons=invalid_reasons,
            evidence=evidence,
            sources=sources,
            last_price=nq_last_price,
            distance_ticks=distance_ticks,
        )

    bar_blocking_reasons = _bar_state_blocking_reasons(payload)
    if bar_blocking_reasons:
        return _read_model(
            "BLOCKED",
            payload,
            blocking_reasons=bar_blocking_reasons,
            invalid_reasons=(),
            evidence=_completed_bar_evidence(payload, trigger),
            sources=sources,
            last_price=nq_last_price,
            distance_ticks=distance_ticks,
        )

    if not _trigger_touched(nq_last_price, trigger):
        if _within_approach_threshold(nq_last_price, trigger, tick_size=tick_size):
            return _read_model(
                "APPROACHING",
                payload,
                blocking_reasons=("awaiting_trigger_touch",),
                invalid_reasons=(),
                evidence=evidence,
                sources=sources,
                last_price=nq_last_price,
                distance_ticks=distance_ticks,
            )
        return _read_model(
            "DORMANT",
            payload,
            blocking_reasons=("price_outside_approach_threshold",),
            invalid_reasons=(),
            evidence=evidence,
            sources=sources,
            last_price=nq_last_price,
            distance_ticks=distance_ticks,
        )

    evidence = _completed_bar_evidence(payload, trigger)
    if not evidence.nq.confirmed:
        state: NQLiveWorkstationState = "ARMED" if evidence.nq.building_five_minute_present else "TOUCHED"
        return _read_model(
            state,
            payload,
            blocking_reasons=evidence.nq.blocking_reasons,
            invalid_reasons=(),
            evidence=evidence,
            sources=sources,
            last_price=nq_last_price,
            distance_ticks=distance_ticks,
        )

    if trigger.relative_strength_required:
        es_evidence = evidence.es
        if es_evidence is None or not es_evidence.confirmed:
            return _read_model(
                "ARMED",
                payload,
                blocking_reasons=_dedupe(
                    ("es_completed_bar_context_required",)
                    + (() if es_evidence is None else es_evidence.blocking_reasons)
                ),
                invalid_reasons=(),
                evidence=evidence,
                sources=sources,
                last_price=nq_last_price,
                distance_ticks=distance_ticks,
            )
        if relative_strength.passed is not True:
            return _read_model(
                "ARMED",
                payload,
                blocking_reasons=("relative_strength_predicate_failed",),
                invalid_reasons=(),
                evidence=evidence,
                sources=sources,
                last_price=nq_last_price,
                distance_ticks=distance_ticks,
            )

    return _read_model(
        "QUERY_READY",
        payload,
        blocking_reasons=(),
        invalid_reasons=(),
        evidence=evidence,
        sources=sources,
        last_price=nq_last_price,
        distance_ticks=distance_ticks,
    )


def _read_model(
    state: NQLiveWorkstationState,
    payload: NQLiveWorkstationInput,
    *,
    blocking_reasons: tuple[str, ...],
    invalid_reasons: tuple[str, ...],
    evidence: NQCompletedBarEvidence,
    sources: Mapping[str, SourceClassification],
    last_price: float | None = None,
    distance_ticks: float | None = None,
) -> NQLiveWorkstationReadModel:
    trigger = payload.trigger
    relative_strength = _relative_strength_result(payload)
    return NQLiveWorkstationReadModel(
        state=state,
        contract=normalize_contract_symbol(payload.contract),
        symbol=payload.nq_quote.symbol if payload.nq_quote is not None else None,
        es_symbol=payload.es_quote.symbol if payload.es_quote is not None else None,
        setup_id=trigger.setup_id if trigger is not None else None,
        trigger_id=trigger.trigger_id if trigger is not None else None,
        trigger_level=float(trigger.level) if trigger is not None and _number(trigger.level) is not None else None,
        last_price=last_price,
        distance_to_trigger_ticks=distance_ticks,
        required_fields=_required_fields(payload),
        missing_fields=_missing_fields(payload),
        blocking_reasons=_dedupe(blocking_reasons),
        invalid_reasons=_dedupe(invalid_reasons),
        nq_anchor=payload.nq_anchor,
        es_anchor=payload.es_anchor,
        nq_return_since_anchor=relative_strength.nq_return,
        es_return_since_anchor=relative_strength.es_return,
        relative_strength_vs_es=relative_strength.relative_strength,
        relative_strength_required=_relative_strength_required(payload),
        relative_strength_passed=relative_strength.passed,
        leadership_proxy_state=payload.leadership_proxy_state or NQLeadershipProxyState(),
        completed_bar_evidence=evidence,
        event_lockout_state=payload.event_lockout,
        source_classification=sources,
        generated_at=payload.generated_at,
    )


def _contract_blocking_reasons(
    contract: str,
    nq_quote: NQLiveQuoteInput | None,
    es_quote: NQLiveQuoteInput | None,
    trigger: NQTriggerDefinition | None,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if contract != NQ_CONTRACT:
        if is_never_supported_contract(contract):
            reasons.append(f"never_supported_contract:{contract}")
        elif is_excluded_final_target_contract(contract):
            reasons.append(f"excluded_contract:{contract}")
        elif is_final_target_contract(contract):
            reasons.append(f"contract_not_onboarded_for_nq_workstation:{contract}")
        else:
            reasons.append(f"unsupported_contract:{contract}")
        reasons.append("nq_workstation_supports_nq_only")

    if nq_quote is not None:
        quote_contract = normalize_contract_symbol(nq_quote.contract)
        if quote_contract != NQ_CONTRACT:
            reasons.append(f"nq_quote_contract_mismatch:{quote_contract}")

    if trigger is not None and trigger.relative_strength_required and es_quote is not None:
        es_quote_contract = normalize_contract_symbol(es_quote.contract)
        if es_quote_contract != ES_CONTEXT_CONTRACT:
            reasons.append(f"es_quote_contract_mismatch:{es_quote_contract}")
    return _dedupe(tuple(reasons))


def _event_lockout_state_reasons(payload: NQLiveWorkstationInput) -> tuple[str, ...]:
    if payload.event_lockout is None:
        return ("event_lockout_state_required",)
    return ()


def _artifact_blocking_reasons(
    artifact: NQPremarketArtifact | None,
    trigger: NQTriggerDefinition | None,
) -> tuple[str, ...]:
    if artifact is None:
        return ("premarket_artifact_required",)
    if not artifact.available:
        return ("premarket_artifact_unavailable",)
    if trigger is None:
        return ("premarket_trigger_required",)
    return ()


def _trigger_blocking_reasons(trigger: NQTriggerDefinition) -> tuple[str, ...]:
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
    if _number(trigger.relative_strength_threshold) is None:
        reasons.append("relative_strength_threshold_required")
    if trigger.relative_strength_predicate not in ("at_or_above", "at_or_below"):
        reasons.append(f"unsupported_relative_strength_predicate:{trigger.relative_strength_predicate}")
    return tuple(reasons)


def _es_quote_blocking_reasons(quote: NQLiveQuoteInput | None) -> tuple[str, ...]:
    if quote is None:
        return ("es_quote_required_for_relative_strength",)
    structural = _quote_structural_reasons("es", quote)
    if structural:
        return structural
    freshness = _quote_freshness_reasons("es", quote)
    if freshness:
        return freshness
    return ()


def _quote_structural_reasons(prefix: str, quote: NQLiveQuoteInput) -> tuple[str, ...]:
    reasons: list[str] = []
    if quote.symbol is None or not quote.symbol.strip():
        reasons.append(f"{prefix}_quote_symbol_required")
    if not quote.symbol_match:
        reasons.append(f"{prefix}_quote_symbol_mismatch")
    if not quote.required_fields_present:
        reasons.append(f"{prefix}_missing_required_quote_fields")
    for field_name in ("bid", "ask", "last", "spread_ticks"):
        if _number(getattr(quote, field_name)) is None:
            reasons.append(f"{prefix}_quote_{field_name}_required")
    bid = _number(quote.bid)
    ask = _number(quote.ask)
    spread_ticks = _number(quote.spread_ticks)
    if bid is not None and ask is not None and bid > ask:
        reasons.append(f"{prefix}_malformed_quote_bid_above_ask")
    if spread_ticks is not None and spread_ticks < 0:
        reasons.append(f"{prefix}_malformed_quote_negative_spread_ticks")
    if reasons:
        reasons.extend(quote.blocking_reasons)
    return _dedupe(tuple(reasons))


def _quote_freshness_reasons(prefix: str, quote: NQLiveQuoteInput) -> tuple[str, ...]:
    if quote.fresh:
        return ()
    return _dedupe((f"{prefix}_quote_stale",) + quote.blocking_reasons)


def _anchor_blocking_reasons(payload: NQLiveWorkstationInput) -> tuple[str, ...]:
    reasons = _single_anchor_blocking_reasons("nq", payload.nq_anchor, required=True)
    if _relative_strength_required(payload):
        reasons += _single_anchor_blocking_reasons("es", payload.es_anchor, required=True)
    return _dedupe(reasons)


def _single_anchor_blocking_reasons(
    prefix: str,
    anchor: NQAnchor | None,
    *,
    required: bool,
) -> tuple[str, ...]:
    if not required:
        return ()
    if anchor is None:
        return (f"{prefix}_anchor_required",)
    reasons: list[str] = []
    if anchor.kind == "unavailable":
        reasons.append(f"{prefix}_anchor_unavailable")
    value = _number(anchor.value)
    if value is None:
        reasons.append(f"{prefix}_anchor_value_required")
    elif value <= 0:
        reasons.append(f"{prefix}_anchor_value_must_be_positive")
    return tuple(reasons)


def _relative_strength_result(payload: NQLiveWorkstationInput) -> _RelativeStrengthResult:
    if not _relative_strength_required(payload):
        return _RelativeStrengthResult(
            nq_return=None,
            es_return=None,
            relative_strength=None,
            passed=None,
            blocking_reasons=(),
        )
    trigger = payload.trigger
    nq_last = _number(payload.nq_quote.last if payload.nq_quote is not None else None)
    es_last = _number(payload.es_quote.last if payload.es_quote is not None else None)
    nq_anchor = _anchor_value(payload.nq_anchor)
    es_anchor = _anchor_value(payload.es_anchor)
    if trigger is None or nq_last is None or es_last is None or nq_anchor is None or es_anchor is None:
        return _RelativeStrengthResult(
            nq_return=None,
            es_return=None,
            relative_strength=None,
            passed=None,
            blocking_reasons=("relative_strength_vs_es_unavailable",),
        )

    nq_return = round((nq_last - nq_anchor) / nq_anchor, 12)
    es_return = round((es_last - es_anchor) / es_anchor, 12)
    relative_strength = round(nq_return - es_return, 12)
    threshold = float(trigger.relative_strength_threshold)
    if trigger.relative_strength_predicate == "at_or_below":
        passed = relative_strength <= threshold
    else:
        passed = relative_strength >= threshold
    return _RelativeStrengthResult(
        nq_return=nq_return,
        es_return=es_return,
        relative_strength=relative_strength,
        passed=passed,
        blocking_reasons=(),
    )


def _anchor_value(anchor: NQAnchor | None) -> float | None:
    if anchor is None or anchor.kind == "unavailable":
        return None
    value = _number(anchor.value)
    if value is None or value <= 0:
        return None
    return value


def _invalidator_reasons(
    last_price: float,
    invalidators: tuple[NQInvalidatorDefinition, ...],
) -> tuple[str, ...]:
    fired = tuple(
        invalidator
        for invalidator in invalidators
        if _number(invalidator.level) is not None
        and _price_crosses(last_price, float(invalidator.level), invalidator.direction)
    )
    return tuple(f"invalidator_fired:{invalidator.invalidator_id}" for invalidator in fired)


def _bar_state_blocking_reasons(payload: NQLiveWorkstationInput) -> tuple[str, ...]:
    reasons = _single_bar_state_blocking_reasons(
        "nq",
        payload.nq_bar_state,
        expected_contract=NQ_CONTRACT,
        required=True,
    )
    if _relative_strength_required(payload):
        reasons += _single_bar_state_blocking_reasons(
            "es",
            payload.es_bar_state,
            expected_contract=ES_CONTEXT_CONTRACT,
            required=True,
        )
    return _dedupe(reasons)


def _single_bar_state_blocking_reasons(
    prefix: str,
    bar_state: ContractBarState | None,
    *,
    expected_contract: str,
    required: bool,
) -> tuple[str, ...]:
    if not required:
        return ()
    if bar_state is None:
        return (f"{prefix}_bar_state_required",)
    contract = normalize_contract_symbol(bar_state.contract)
    if contract != expected_contract:
        return (f"{prefix}_bar_contract_mismatch:{contract}",)
    return tuple(f"{prefix}_bar_state_blocked:{reason}" for reason in bar_state.blocking_reasons)


def _completed_bar_evidence(
    payload: NQLiveWorkstationInput,
    trigger: NQTriggerDefinition,
) -> NQCompletedBarEvidence:
    return NQCompletedBarEvidence(
        nq=_trigger_confirmation_evidence(
            payload.nq_bar_state,
            expected_contract=NQ_CONTRACT,
            trigger=trigger,
            prefix="nq",
        ),
        es=(
            _context_bar_evidence(
                payload.es_bar_state,
                expected_contract=ES_CONTEXT_CONTRACT,
                prefix="es",
            )
            if trigger.relative_strength_required
            else None
        ),
    )


def _trigger_confirmation_evidence(
    bar_state: ContractBarState | None,
    *,
    expected_contract: str,
    trigger: NQTriggerDefinition,
    prefix: str,
) -> NQBarEvidence:
    if bar_state is None:
        return NQBarEvidence(
            contract=expected_contract,
            confirmed=False,
            completed_five_minute_bar_count=0,
            completed_one_minute_bar_count=0,
            latest_completed_five_minute_close=None,
            building_five_minute_present=False,
            blocking_reasons=(f"{prefix}_bar_state_required_for_confirmation",),
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
        reasons = [f"{prefix}_completed_five_minute_confirmation_required"]
        if building_present:
            reasons.append(f"{prefix}_building_five_minute_bar_not_confirmation")
        return NQBarEvidence(
            contract=expected_contract,
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
        if _has_required_completed_one_minute_support(bar, completed_one_minute, expected_contract=expected_contract):
            return NQBarEvidence(
                contract=expected_contract,
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
        reasons.append(f"{prefix}_completed_one_minute_confirmation_bars_required")
    else:
        reasons.append(f"{prefix}_completed_five_minute_close_not_confirmed")
    if incomplete_completed_bar_seen:
        reasons.append(f"{prefix}_completed_five_minute_bar_requires_five_one_minute_bars")
    if building_present:
        reasons.append(f"{prefix}_building_five_minute_bar_not_confirmation")

    return NQBarEvidence(
        contract=expected_contract,
        confirmed=False,
        completed_five_minute_bar_count=len(completed_five_minute),
        completed_one_minute_bar_count=len(completed_one_minute),
        latest_completed_five_minute_close=latest_close,
        building_five_minute_present=building_present,
        blocking_reasons=_dedupe(tuple(reasons)),
    )


def _context_bar_evidence(
    bar_state: ContractBarState | None,
    *,
    expected_contract: str,
    prefix: str,
) -> NQBarEvidence:
    if bar_state is None:
        return NQBarEvidence(
            contract=expected_contract,
            confirmed=False,
            completed_five_minute_bar_count=0,
            completed_one_minute_bar_count=0,
            latest_completed_five_minute_close=None,
            building_five_minute_present=False,
            blocking_reasons=(f"{prefix}_bar_state_required_for_context",),
        )

    completed_five_minute = tuple(
        bar for bar in bar_state.completed_five_minute_bars if bool(getattr(bar, "completed", False))
    )
    completed_one_minute = tuple(
        bar for bar in bar_state.completed_one_minute_bars if bool(getattr(bar, "completed", False))
    )
    latest_close = _latest_completed_five_minute_close(completed_five_minute)
    building_present = bar_state.building_five_minute_bar is not None

    for bar in completed_five_minute:
        if _completed_five_minute_bar_is_usable(bar) and _has_required_completed_one_minute_support(
            bar,
            completed_one_minute,
            expected_contract=expected_contract,
        ):
            return NQBarEvidence(
                contract=expected_contract,
                confirmed=True,
                completed_five_minute_bar_count=len(completed_five_minute),
                completed_one_minute_bar_count=len(completed_one_minute),
                latest_completed_five_minute_close=latest_close,
                building_five_minute_present=building_present,
                blocking_reasons=(),
            )

    reasons = [f"{prefix}_completed_five_minute_context_required"]
    if completed_five_minute:
        reasons.append(f"{prefix}_completed_one_minute_context_bars_required")
    if building_present:
        reasons.append(f"{prefix}_building_five_minute_bar_not_context")
    return NQBarEvidence(
        contract=expected_contract,
        confirmed=False,
        completed_five_minute_bar_count=len(completed_five_minute),
        completed_one_minute_bar_count=len(completed_one_minute),
        latest_completed_five_minute_close=latest_close,
        building_five_minute_present=building_present,
        blocking_reasons=_dedupe(tuple(reasons)),
    )


def _empty_completed_bar_evidence(payload: NQLiveWorkstationInput) -> NQCompletedBarEvidence:
    return NQCompletedBarEvidence(
        nq=_empty_bar_evidence(payload.nq_bar_state, expected_contract=NQ_CONTRACT),
        es=(
            _empty_bar_evidence(payload.es_bar_state, expected_contract=ES_CONTEXT_CONTRACT)
            if _relative_strength_required(payload)
            else None
        ),
    )


def _empty_bar_evidence(
    bar_state: ContractBarState | None,
    *,
    expected_contract: str,
) -> NQBarEvidence:
    if bar_state is None:
        return NQBarEvidence(
            contract=expected_contract,
            confirmed=False,
            completed_five_minute_bar_count=0,
            completed_one_minute_bar_count=0,
            latest_completed_five_minute_close=None,
            building_five_minute_present=False,
        )
    return NQBarEvidence(
        contract=expected_contract,
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
    *,
    expected_contract: str,
) -> bool:
    start = _parse_timestamp(str(getattr(five_minute_bar, "start_time", "")))
    end = _parse_timestamp(str(getattr(five_minute_bar, "end_time", "")))
    if start is None or end is None:
        return False
    expected_starts = {start + timedelta(minutes=offset) for offset in range(5)}
    actual_starts = {
        parsed_start
        for bar in completed_one_minute
        if normalize_contract_symbol(str(getattr(bar, "contract", ""))) == expected_contract
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


def _trigger_touched(price: float, trigger: NQTriggerDefinition) -> bool:
    return _price_crosses(price, float(trigger.level), trigger.direction)


def _within_approach_threshold(
    price: float,
    trigger: NQTriggerDefinition,
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


def _required_fields(payload: NQLiveWorkstationInput) -> tuple[str, ...]:
    fields = [
        "contract",
        "nq_quote.symbol",
        "nq_quote.bid",
        "nq_quote.ask",
        "nq_quote.last",
        "nq_quote.spread_ticks",
        "nq_quote.fresh",
        "nq_quote.symbol_match",
        "nq_quote.required_fields_present",
        "event_lockout_state",
        "premarket_artifact",
        "trigger.setup_id",
        "trigger.trigger_id",
        "trigger.level",
        "nq_anchor",
        "nq_bar_state",
    ]
    if _relative_strength_required(payload):
        fields.extend(
            (
                "es_quote.symbol",
                "es_quote.bid",
                "es_quote.ask",
                "es_quote.last",
                "es_quote.spread_ticks",
                "es_quote.fresh",
                "es_quote.symbol_match",
                "es_quote.required_fields_present",
                "es_anchor",
                "relative_strength_threshold",
                "relative_strength_vs_es",
                "es_bar_state",
            )
        )
    return tuple(fields)


def _missing_fields(payload: NQLiveWorkstationInput) -> tuple[str, ...]:
    missing: list[str] = []
    _append_missing_quote_fields(missing, "nq_quote", payload.nq_quote)
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
        if _number(trigger.relative_strength_threshold) is None:
            missing.append("relative_strength_threshold")
    if _single_anchor_blocking_reasons("nq", payload.nq_anchor, required=True):
        missing.append("nq_anchor")
    if payload.nq_bar_state is None:
        missing.append("nq_bar_state")

    if _relative_strength_required(payload):
        _append_missing_quote_fields(missing, "es_quote", payload.es_quote)
        if _single_anchor_blocking_reasons("es", payload.es_anchor, required=True):
            missing.append("es_anchor")
        if payload.es_bar_state is None:
            missing.append("es_bar_state")
        if _relative_strength_result(payload).relative_strength is None:
            missing.append("relative_strength_vs_es")
    return _dedupe(tuple(missing))


def _append_missing_quote_fields(
    missing: list[str],
    prefix: str,
    quote: NQLiveQuoteInput | None,
) -> None:
    if quote is None:
        missing.extend(
            (
                f"{prefix}.symbol",
                f"{prefix}.bid",
                f"{prefix}.ask",
                f"{prefix}.last",
                f"{prefix}.spread_ticks",
            )
        )
        return
    if quote.symbol is None or not quote.symbol.strip():
        missing.append(f"{prefix}.symbol")
    for field_name in ("bid", "ask", "last", "spread_ticks"):
        if _number(getattr(quote, field_name)) is None:
            missing.append(f"{prefix}.{field_name}")
    if not quote.required_fields_present:
        missing.append(f"{prefix}.required_fields_present")


def _source_classification(payload: NQLiveWorkstationInput) -> dict[str, SourceClassification]:
    return {
        "nq_quote": payload.nq_quote.source if payload.nq_quote is not None else "unavailable",
        "nq_quote_quality": "derived_from_schwab" if payload.nq_quote is not None else "unavailable",
        "es_quote": payload.es_quote.source if payload.es_quote is not None else "unavailable",
        "es_quote_quality": "derived_from_schwab" if payload.es_quote is not None else "unavailable",
        "premarket_artifact": (
            payload.premarket_artifact.source if payload.premarket_artifact is not None else "unavailable"
        ),
        "trigger": payload.trigger.source if payload.trigger is not None else "unavailable",
        "event_lockout": payload.event_lockout.source if payload.event_lockout is not None else "unavailable",
        "nq_anchor": payload.nq_anchor.source if payload.nq_anchor is not None else "unavailable",
        "es_anchor": payload.es_anchor.source if payload.es_anchor is not None else "unavailable",
        "nq_bar_confirmation": "derived_from_schwab" if payload.nq_bar_state is not None else "unavailable",
        "es_bar_context": "derived_from_schwab" if payload.es_bar_state is not None else "unavailable",
        "leadership_proxy": (
            payload.leadership_proxy_state.source if payload.leadership_proxy_state is not None else "unavailable"
        ),
    }


def _relative_strength_required(payload: NQLiveWorkstationInput) -> bool:
    return True if payload.trigger is None else payload.trigger.relative_strength_required


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
