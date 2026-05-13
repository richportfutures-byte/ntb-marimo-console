from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Literal


MARKET_DATA_INFORMATIONAL_DISCLAIMER = (
    "Informational only. Quote values do not affect readiness, trigger validity, "
    "query availability, risk, or execution."
)


@dataclass(frozen=True)
class SessionHeaderVM:
    contract: str
    session_date: str


@dataclass(frozen=True)
class PreMarketBriefVM:
    contract: str
    session_date: str
    status: str
    setup_summaries: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class ReadinessCardVM:
    contract: str
    status: str
    event_risk: str
    vwap_posture: str
    value_location: str
    level_proximity: str
    hard_lockouts: tuple[str, ...]
    awareness_items: tuple[str, ...]
    missing_context: tuple[str, ...]


@dataclass(frozen=True)
class TriggerStatusVM:
    trigger_id: str
    is_valid: bool
    is_true: bool
    missing_fields: tuple[str, ...]
    invalid_reasons: tuple[str, ...]


@dataclass(frozen=True)
class LiveObservableMarketDataVM:
    bid: str
    ask: str
    last: str
    quote_time: str
    status: str
    disclaimer: str = MARKET_DATA_INFORMATIONAL_DISCLAIMER


def unavailable_live_observable_market_data_vm() -> LiveObservableMarketDataVM:
    return LiveObservableMarketDataVM(
        bid="N/A",
        ask="N/A",
        last="N/A",
        quote_time="unknown",
        status="Market data unavailable",
    )


@dataclass(frozen=True)
class LiveObservableVM:
    contract: str
    timestamp_et: str
    snapshot: dict[str, object]
    market_data: LiveObservableMarketDataVM = field(default_factory=unavailable_live_observable_market_data_vm)


@dataclass(frozen=True)
class StreamHealthVM:
    connection_state: str
    token_status: str
    token_expires_in_seconds: int | None
    reconnect_attempts: int
    reconnect_active: bool
    per_contract_status: Mapping[str, str]
    stale_contracts: tuple[str, ...]
    blocking_reasons: tuple[str, ...]
    overall_health: str

    def to_dict(self) -> dict[str, object]:
        return {
            "connection_state": self.connection_state,
            "token_status": self.token_status,
            "token_expires_in_seconds": self.token_expires_in_seconds,
            "reconnect_attempts": self.reconnect_attempts,
            "reconnect_active": self.reconnect_active,
            "per_contract_status": dict(self.per_contract_status),
            "stale_contracts": list(self.stale_contracts),
            "blocking_reasons": list(self.blocking_reasons),
            "overall_health": self.overall_health,
        }


@dataclass(frozen=True)
class ActiveTradeVM:
    trade_id: str
    contract: str
    direction: str
    entry_price: float
    entry_time: str
    stop_loss: float | None
    target: float | None
    status: str
    current_price: float | None
    unrealized_pnl: float | None
    thesis_health: str
    thesis_health_reasons: tuple[str, ...]
    distance_from_stop: float | None
    distance_from_target: float | None
    operator_notes: str

    def to_dict(self) -> dict[str, object]:
        return {
            "trade_id": self.trade_id,
            "contract": self.contract,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "entry_time": self.entry_time,
            "stop_loss": self.stop_loss,
            "target": self.target,
            "status": self.status,
            "current_price": self.current_price,
            "unrealized_pnl": self.unrealized_pnl,
            "thesis_health": self.thesis_health,
            "thesis_health_reasons": list(self.thesis_health_reasons),
            "distance_from_stop": self.distance_from_stop,
            "distance_from_target": self.distance_from_target,
            "operator_notes": self.operator_notes,
        }


NARRATIVE_UNAVAILABLE_LABEL = "Engine narrative unavailable in this run."


@dataclass(frozen=True)
class EngineReasoningVM:
    """Stage B contract_analysis narrative, surfaced verbatim from the engine."""

    market_regime: str | None
    directional_bias: str | None
    evidence_score: int | None
    confidence_band: str | None
    structural_notes: str | None
    conflicting_signals: tuple[str, ...]
    assumptions: tuple[str, ...]
    outcome: str | None


@dataclass(frozen=True)
class KeyLevelsVM:
    """Stage B key_levels payload, surfaced verbatim from the engine."""

    pivot_level: float | None
    support_levels: tuple[float, ...]
    resistance_levels: tuple[float, ...]


@dataclass(frozen=True)
class SizingMathVM:
    """Stage C sizing_math payload, surfaced verbatim from the engine."""

    stop_distance_ticks: float | None
    risk_per_tick: float | None
    raw_risk_dollars: float | None
    slippage_cost_dollars: float | None
    adjusted_risk_dollars: float | None
    blended_target_distance_ticks: float | None
    blended_reward_dollars: float | None


@dataclass(frozen=True)
class TradeThesisVM:
    """Stage C proposed_setup narrative, surfaced verbatim from the engine.

    Both SETUP_PROPOSED and NO_TRADE shapes are representable. The console
    does not infer a setup from a NO_TRADE; the trade-thesis fields are None
    and `no_trade_reason` carries the engine's terminal reason.
    """

    outcome: str | None
    no_trade_reason: str | None
    direction: str | None
    setup_class: str | None
    entry_price: float | None
    stop_price: float | None
    target_1: float | None
    target_2: float | None
    position_size: int | None
    risk_dollars: float | None
    reward_risk_ratio: float | None
    hold_time_estimate_minutes: int | None
    rationale: str | None
    disqualifiers: tuple[str, ...]
    sizing_math: SizingMathVM | None


@dataclass(frozen=True)
class RiskCheckVM:
    """A single Stage D risk_authorization check, surfaced verbatim."""

    check_id: int
    check_name: str
    passed: bool
    detail: str


@dataclass(frozen=True)
class RiskAuthorizationVM:
    """Stage D risk_authorization narrative, surfaced verbatim from the engine."""

    decision: str | None
    checks: tuple[RiskCheckVM, ...]
    rejection_reasons: tuple[str, ...]
    adjusted_position_size: int | None
    adjusted_risk_dollars: float | None
    remaining_daily_risk_budget: float | None
    remaining_aggregate_risk_budget: float | None


@dataclass(frozen=True)
class PipelineTraceVM:
    contract: str
    termination_stage: str
    final_decision: str
    stage_a_status: str | None
    stage_b_outcome: str | None
    stage_c_outcome: str | None
    stage_d_decision: str | None
    engine_reasoning: EngineReasoningVM | None = None
    key_levels: KeyLevelsVM | None = None
    trade_thesis: TradeThesisVM | None = None
    risk_authorization: RiskAuthorizationVM | None = None
    narrative_available: bool = False


TimelineEventType = Literal[
    "trigger_transition",
    "pipeline_result",
    "trade_entry",
    "trade_close",
    "note",
    "anchor_update",
]


@dataclass(frozen=True)
class TimelineEventVM:
    event_id: str
    timestamp: str
    event_type: TimelineEventType
    contract: str | None
    summary: str
    detail: str
    status_badge: str

    def to_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "contract": self.contract,
            "summary": self.summary,
            "detail": self.detail,
            "status_badge": self.status_badge,
        }


@dataclass(frozen=True)
class RunHistoryRowVM:
    run_id: str
    logged_at: str
    contract: str
    run_type: str
    notes: str
    session_date: str | None = None
    final_decision: str | None = None
    termination_stage: str | None = None
    stage_d_decision: str | None = None
