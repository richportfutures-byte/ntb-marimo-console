from __future__ import annotations

from dataclasses import dataclass, field


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
class PipelineTraceVM:
    contract: str
    termination_stage: str
    final_decision: str
    stage_a_status: str | None
    stage_b_outcome: str | None
    stage_c_outcome: str | None
    stage_d_decision: str | None


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
