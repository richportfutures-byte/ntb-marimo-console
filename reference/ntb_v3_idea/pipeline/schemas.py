"""
All Pydantic schemas for NinjaTradeBuilder-v3.
Covers market data input, per-contract extensions, and all pipeline outputs.
"""

from __future__ import annotations
from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Enums / Literals
# ---------------------------------------------------------------------------

ContractSymbol = Literal["ES", "NQ", "CL", "ZN", "6E", "MGC"]
ConfidenceBand = Literal["LOW", "MEDIUM", "HIGH"]
DirectionalBias = Literal["LONG", "SHORT", "NEUTRAL", "CONFLICTED"]
MarketRegime = Literal[
    "TREND_UP", "TREND_DOWN", "RANGE_BOUND", "BREAKOUT_PENDING",
    "POST_BREAKOUT", "REVERSAL_SETUP", "UNDEFINED"
]
SufficiencyStatus = Literal["READY", "NEED_INPUT", "INSUFFICIENT_DATA", "EVENT_LOCKOUT"]
RiskDecision = Literal["APPROVED", "REJECTED", "REDUCED"]
ReadinessStatus = Literal["READY", "WAIT_FOR_TRIGGER", "LOCKED_OUT", "INSUFFICIENT_DATA"]
SetupClass = Literal["SCALP", "INTRADAY_SWING", "SESSION_HOLD"]


# ---------------------------------------------------------------------------
# Challenge State
# ---------------------------------------------------------------------------

class ChallengeState(BaseModel):
    account_balance: float = Field(..., description="Current account balance in USD")
    daily_pnl: float = Field(..., description="Today's realized P&L in USD")
    open_positions: dict[str, int] = Field(default_factory=dict, description="Open lots by contract")
    open_risk_dollars: float = Field(default=0.0, description="Aggregate open risk USD")
    daily_trade_count: int = Field(default=0)
    trade_count_by_contract: dict[str, int] = Field(default_factory=dict)
    last_stop_out_time: Optional[str] = Field(default=None, description="ISO timestamp of last stop-out")
    last_trade_direction: dict[str, str] = Field(default_factory=dict, description="Last direction per contract")
    max_daily_loss_stop: float = Field(default=10000.0)
    max_per_trade_risk: float = Field(default=1450.0)
    max_aggregate_open_risk: float = Field(default=40000.0)
    max_daily_trades: int = Field(default=60)
    max_trades_per_contract_per_day: int = Field(default=3)
    cooldown_minutes_after_stop: int = Field(default=30)


# ---------------------------------------------------------------------------
# Event Calendar
# ---------------------------------------------------------------------------

class EventEntry(BaseModel):
    name: str
    tier: Literal[1, 2]
    scheduled_time_et: str
    state: Literal["upcoming", "released"]
    minutes_until: Optional[float] = None


# ---------------------------------------------------------------------------
# Market Packet (shared fields across all contracts)
# ---------------------------------------------------------------------------

class KeyLevels(BaseModel):
    prior_day_high: Optional[float] = None
    prior_day_low: Optional[float] = None
    prior_day_close: Optional[float] = None
    prior_day_settlement: Optional[float] = None
    previous_session_vah: Optional[float] = None
    previous_session_val: Optional[float] = None
    previous_session_poc: Optional[float] = None
    current_session_vah: Optional[float] = None
    current_session_val: Optional[float] = None
    current_session_poc: Optional[float] = None
    overnight_high: Optional[float] = None
    overnight_low: Optional[float] = None
    vwap: Optional[float] = None
    major_htf_resistance: Optional[float] = None
    major_htf_support: Optional[float] = None
    key_hvn_1: Optional[float] = None
    key_lvn_1: Optional[float] = None


class MarketPacket(BaseModel):
    contract: ContractSymbol
    timestamp_et: str = Field(..., description="ISO timestamp of this packet in ET")
    current_price: float
    session_open: Optional[float] = None
    session_high: Optional[float] = None
    session_low: Optional[float] = None
    levels: KeyLevels = Field(default_factory=KeyLevels)
    cumulative_delta: Optional[float] = None
    delta_trend: Optional[Literal["positive", "negative", "neutral"]] = None
    current_volume: Optional[float] = None
    avg_20d_session_volume: Optional[float] = None
    volume_vs_average_ratio: Optional[float] = None
    opening_type: Optional[str] = None
    avg_20d_session_range: Optional[float] = None
    current_session_range: Optional[float] = None
    event_calendar: list[EventEntry] = Field(default_factory=list)
    packet_age_seconds: Optional[float] = None
    data_quality_notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Contract-Specific Extensions
# ---------------------------------------------------------------------------

class ESExtension(BaseModel):
    contract: Literal["ES"] = "ES"
    breadth_advancing_pct: Optional[float] = Field(default=None, description="% of S&P500 stocks advancing")
    index_cash_tone: Optional[Literal["positive", "negative", "mixed", "neutral"]] = None
    spx_cash_level: Optional[float] = None
    opening_initiative: Optional[str] = None


class NQExtension(BaseModel):
    contract: Literal["NQ"] = "NQ"
    relative_strength_vs_es: Optional[float] = Field(default=None, description="NQ/ES ratio or spread")
    megacap_leadership: Optional[str] = Field(default=None, description="Leading or lagging megacap names/context")
    tech_sector_beta: Optional[float] = None


class CLExtension(BaseModel):
    contract: Literal["CL"] = "CL"
    eia_today: bool = Field(default=False, description="Is EIA report today?")
    eia_scheduled_time_et: Optional[str] = None
    realized_volatility_context: Optional[Literal["compressed", "normal", "expanded"]] = None
    dom_sweep_summary: Optional[str] = None
    oil_headlines: Optional[str] = None


class ZNExtension(BaseModel):
    contract: Literal["ZN"] = "ZN"
    cash_10y_yield: Optional[float] = Field(default=None, description="Current 10Y yield")
    prior_day_10y_yield: Optional[float] = None
    yield_change_bps: Optional[float] = None
    treasury_auction_schedule: Optional[str] = Field(default=None, description="e.g. '10Y auction in 2 days'")
    macro_release_today: Optional[str] = None
    macro_release_context: Optional[str] = Field(default=None, description="Actual print vs expectation")
    absorption_summary: Optional[str] = None


class SixEExtension(BaseModel):
    contract: Literal["6E"] = "6E"
    asia_high: Optional[float] = None
    asia_low: Optional[float] = None
    london_high: Optional[float] = None
    london_low: Optional[float] = None
    ny_high_so_far: Optional[float] = None
    ny_low_so_far: Optional[float] = None
    dxy_current: Optional[float] = None
    dxy_prior_close: Optional[float] = None
    europe_initiative_status: Optional[str] = None
    session_sequence_complete: Optional[bool] = None


class MGCExtension(BaseModel):
    contract: Literal["MGC"] = "MGC"
    dxy_current: Optional[float] = None
    dxy_prior_close: Optional[float] = None
    yield_10y_current: Optional[float] = None
    yield_10y_prior: Optional[float] = None
    macro_fear_catalyst: Optional[str] = None
    swing_penetration_volume: Optional[str] = None


ContractExtension = ESExtension | NQExtension | CLExtension | ZNExtension | SixEExtension | MGCExtension


# ---------------------------------------------------------------------------
# Full Packet Bundle (all contracts + challenge state)
# ---------------------------------------------------------------------------

class PacketBundle(BaseModel):
    challenge_state: ChallengeState
    packets: dict[str, MarketPacket] = Field(..., description="Keyed by contract symbol")
    extensions: dict[str, dict] = Field(default_factory=dict, description="Keyed by contract symbol")
    session_date: str = Field(..., description="Trading date YYYY-MM-DD")


# ---------------------------------------------------------------------------
# Pipeline Stage Outputs
# ---------------------------------------------------------------------------

class SufficiencyOutput(BaseModel):
    contract: ContractSymbol
    status: SufficiencyStatus
    missing_fields: list[str] = Field(default_factory=list)
    disqualifiers: list[str] = Field(default_factory=list)
    packet_age_seconds: Optional[float] = None
    event_lockout_detail: Optional[str] = None
    challenge_state_valid: bool = True
    notes: Optional[str] = None


class KeyLevelAnalysis(BaseModel):
    level_name: str
    value: float
    significance: str


class ContractAnalysis(BaseModel):
    contract: ContractSymbol
    outcome: Literal["ANALYSIS_COMPLETE", "NO_TRADE"]
    market_regime: Optional[MarketRegime] = None
    directional_bias: Optional[DirectionalBias] = None
    evidence_score: Optional[int] = Field(default=None, ge=1, le=10)
    confidence_band: Optional[ConfidenceBand] = None
    key_levels: list[KeyLevelAnalysis] = Field(default_factory=list)
    value_context: Optional[str] = None
    structural_notes: Optional[str] = None
    conflicting_signals: list[str] = Field(default_factory=list)
    no_trade_reason: Optional[str] = None

    @model_validator(mode="after")
    def validate_score_band_alignment(self) -> "ContractAnalysis":
        if self.evidence_score is not None and self.confidence_band is not None:
            score = self.evidence_score
            band = self.confidence_band
            if band == "LOW" and score > 4:
                raise ValueError(f"LOW confidence requires evidence_score ≤ 4, got {score}")
            if band == "MEDIUM" and not (5 <= score <= 7):
                raise ValueError(f"MEDIUM confidence requires evidence_score 5–7, got {score}")
            if band == "HIGH" and score < 8:
                raise ValueError(f"HIGH confidence requires evidence_score ≥ 8, got {score}")
        return self


class SizingMath(BaseModel):
    stop_distance_ticks: float
    risk_per_tick_dollars: float
    raw_risk_dollars: float
    slippage_cost_dollars: float
    adjusted_risk_dollars: float
    position_size: int


class ProposedSetup(BaseModel):
    contract: ContractSymbol
    outcome: Literal["TRADE_PROPOSED", "NO_TRADE"]
    direction: Optional[DirectionalBias] = None
    entry_price: Optional[float] = None
    stop_price: Optional[float] = None
    target_1: Optional[float] = None
    target_2: Optional[float] = None
    reward_risk_ratio: Optional[float] = None
    setup_class: Optional[SetupClass] = None
    hold_time_estimate_minutes: Optional[int] = None
    sizing_math: Optional[SizingMath] = None
    rationale: Optional[str] = None
    no_trade_reason: Optional[str] = None
    disqualifiers: list[str] = Field(default_factory=list)


class RiskCheck(BaseModel):
    check_id: int
    name: str
    passed: bool
    detail: str


class RiskAuthorization(BaseModel):
    contract: ContractSymbol
    decision: RiskDecision
    checks: list[RiskCheck] = Field(..., min_length=13, max_length=13)
    rejection_reasons: list[str] = Field(default_factory=list)
    adjusted_position_size: Optional[int] = None
    adjusted_risk_dollars: Optional[float] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Pre-Market Brief Output
# ---------------------------------------------------------------------------

class QueryTrigger(BaseModel):
    condition: str = Field(..., description="Observable condition that means: send updated packet now")
    schema_fields: list[str] = Field(..., description="Schema fields the operator needs to verify")
    level_or_value: Optional[str] = None


class PreMarketBrief(BaseModel):
    contract: ContractSymbol
    session_date: str
    analytical_framework: str = Field(..., description="Contract-specific causal logic summary")
    key_structural_levels: list[KeyLevelAnalysis]
    long_thesis: Optional[str] = Field(default=None, description="Conditions that activate long bias")
    short_thesis: Optional[str] = Field(default=None, description="Conditions that activate short bias")
    current_structure_summary: str = Field(..., description="Where price is RIGHT NOW relative to structure")
    query_triggers: list[QueryTrigger] = Field(..., description="Explicit conditions = time to query pipeline")
    watch_for: list[str] = Field(..., description="Bullet list of specific things to monitor")
    schema_fields_referenced: list[str] = Field(..., description="Every schema field cited in this brief")
    generated_at: str


# ---------------------------------------------------------------------------
# Readiness Engine Output
# ---------------------------------------------------------------------------

class ReadinessGateResult(BaseModel):
    gate: str
    state: Literal["PASS", "FAIL", "WARN"]
    rationale: str


class ReadinessEngineOutput(BaseModel):
    contract: ContractSymbol
    status: ReadinessStatus
    doctrine_gates: list[ReadinessGateResult]
    trigger_condition: Optional[str] = None
    wait_reason: Optional[str] = None
    lockout_reason: Optional[str] = None
    missing_inputs: list[str] = Field(default_factory=list)
    watchman_summary: Optional[str] = None


# ---------------------------------------------------------------------------
# Full Pipeline Run Record
# ---------------------------------------------------------------------------

class PipelineRunRecord(BaseModel):
    run_id: str
    contract: ContractSymbol
    session_date: str
    run_type: Literal["full_pipeline", "premarket_brief", "readiness_only"]
    started_at: str
    completed_at: Optional[str] = None
    sufficiency: Optional[SufficiencyOutput] = None
    analysis: Optional[ContractAnalysis] = None
    setup: Optional[ProposedSetup] = None
    authorization: Optional[RiskAuthorization] = None
    final_decision: Optional[str] = None
    termination_stage: Optional[str] = None
    error: Optional[str] = None
