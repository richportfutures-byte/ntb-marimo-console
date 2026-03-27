from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from .contracts import AllMarketPacket
from .inputs import ChallengeState, ContractSymbol, StrictModel, TradeDirection

ConfidenceBand = Literal["LOW", "MEDIUM", "HIGH"]
DirectionalBias = Literal["bullish", "bearish", "neutral", "unclear"]
ExitType = Literal[
    "target_1_hit",
    "target_2_hit",
    "stop_hit",
    "trailing_stop_hit",
    "time_exit",
    "manual_exit",
    "session_close_exit",
    "event_lockout_exit",
]
FinalDecision = Literal[
    "TRADE_APPROVED",
    "TRADE_REDUCED",
    "TRADE_REJECTED",
    "NO_TRADE",
    "INSUFFICIENT_DATA",
    "NEED_INPUT",
    "EVENT_LOCKOUT",
]
GateStatus = Literal["READY", "NEED_INPUT", "INSUFFICIENT_DATA", "EVENT_LOCKOUT"]
LockoutType = Literal["pre_event", "post_event"]
MarketRegime = Literal[
    "trending_up",
    "trending_down",
    "range_bound",
    "breakout",
    "breakdown",
    "choppy",
    "unclear",
]
RiskDecision = Literal["APPROVED", "REJECTED", "REDUCED"]
SetupClass = Literal["scalp", "intraday_swing", "session_hold"]
TerminationStage = Literal[
    "sufficiency_gate",
    "contract_market_read",
    "setup_construction",
    "risk_authorization",
]
ReadinessTopLevelStatus = Literal[
    "READY",
    "WAIT_FOR_TRIGGER",
    "LOCKED_OUT",
    "INSUFFICIENT_DATA",
]
ReadinessDoctrineGate = Literal[
    "data_sufficiency_gate",
    "context_alignment_gate",
    "structure_quality_gate",
    "trigger_gate",
    "risk_window_gate",
    "lockout_gate",
]
ReadinessDoctrineGateState = Literal["PASS", "FAIL", "WAIT"]
ReadinessWaitForTriggerReason = Literal[
    "entry_not_yet_confirmed",
    "pullback_not_complete",
    "breakout_not_confirmed",
    "timing_window_not_open",
]
ReadinessLockoutReason = Literal[
    "event_lockout_active",
    "session_closed",
    "risk_hard_stop_active",
    "governance_lock_active",
]
ReadinessInsufficientDataReason = Literal[
    "missing_required_fields",
    "stale_market_packet",
    "incomplete_contract_extension",
    "invalid_challenge_state",
    "missing_trigger_context",
]
ReadinessTriggerFamily = Literal[
    "recheck_at_time",
    "price_level_touch",
]

READINESS_DOCTRINE_GATES: tuple[ReadinessDoctrineGate, ...] = (
    "data_sufficiency_gate",
    "context_alignment_gate",
    "structure_quality_gate",
    "trigger_gate",
    "risk_window_gate",
    "lockout_gate",
)


class EventLockoutDetail(StrictModel):
    event_name: str
    event_time: AwareDatetime
    minutes_until: int
    lockout_type: LockoutType


class StalenessCheck(StrictModel):
    packet_age_seconds: int
    stale: bool
    threshold_seconds: int


class SufficiencyGateOutput(StrictModel):
    schema_name: Literal["sufficiency_gate_output_v1"] = Field(
        default="sufficiency_gate_output_v1",
        alias="$schema",
    )
    stage: Literal["sufficiency_gate"] = "sufficiency_gate"
    contract: ContractSymbol
    timestamp: AwareDatetime
    status: GateStatus
    missing_inputs: list[str]
    disqualifiers: list[str]
    data_quality_flags: list[str] | None
    staleness_check: StalenessCheck
    challenge_state_valid: bool
    event_lockout_detail: EventLockoutDetail | None = None

    @model_validator(mode="after")
    def validate_status_details(self) -> "SufficiencyGateOutput":
        if self.status == "READY" and self.missing_inputs:
            raise ValueError("READY status must not include missing_inputs.")
        if self.status == "NEED_INPUT" and not self.missing_inputs:
            raise ValueError("NEED_INPUT status must include missing_inputs.")
        if self.status == "EVENT_LOCKOUT":
            if self.event_lockout_detail is None:
                raise ValueError(
                    "EVENT_LOCKOUT status must include event_lockout_detail."
                )
            if not self.disqualifiers:
                raise ValueError("EVENT_LOCKOUT status must include disqualifiers.")
        elif self.event_lockout_detail is not None:
            raise ValueError(
                "event_lockout_detail must only be populated when status is EVENT_LOCKOUT."
            )
        return self


class ReadinessDoctrineGateResult(StrictModel):
    gate: ReadinessDoctrineGate
    state: ReadinessDoctrineGateState
    rationale: str


class ReadinessTriggerData(StrictModel):
    family: ReadinessTriggerFamily
    recheck_at_time: AwareDatetime | None = None
    price_level: float | None = None

    @model_validator(mode="after")
    def validate_family_shape(self) -> "ReadinessTriggerData":
        if self.family == "recheck_at_time":
            if self.recheck_at_time is None:
                raise ValueError(
                    "recheck_at_time trigger_data requires recheck_at_time."
                )
            if self.price_level is not None:
                raise ValueError(
                    "recheck_at_time trigger_data must not include price_level."
                )
            return self

        if self.price_level is None:
            raise ValueError("price_level_touch trigger_data requires price_level.")
        if self.recheck_at_time is not None:
            raise ValueError(
                "price_level_touch trigger_data must not include recheck_at_time."
            )
        return self


class ReadinessEngineOutput(StrictModel):
    schema_name: Literal["readiness_engine_output_v1"] = Field(
        default="readiness_engine_output_v1",
        alias="$schema",
    )
    stage: Literal["readiness_engine"] = "readiness_engine"
    authority: Literal["ESCALATE_ONLY"] = "ESCALATE_ONLY"
    contract: ContractSymbol
    timestamp: AwareDatetime
    status: ReadinessTopLevelStatus
    doctrine_gates: list[ReadinessDoctrineGateResult]
    trigger_data: ReadinessTriggerData | None = None
    wait_for_trigger_reason: ReadinessWaitForTriggerReason | None = None
    lockout_reason: ReadinessLockoutReason | None = None
    insufficient_data_reasons: list[ReadinessInsufficientDataReason] = Field(
        default_factory=list
    )
    missing_inputs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_status_and_gate_non_interchangeability(self) -> "ReadinessEngineOutput":
        if len(self.doctrine_gates) != len(READINESS_DOCTRINE_GATES):
            raise ValueError("doctrine_gates must contain exactly one result for each doctrine gate.")

        gate_map: dict[ReadinessDoctrineGate, ReadinessDoctrineGateState] = {}
        for result in self.doctrine_gates:
            if result.gate in gate_map:
                raise ValueError(f"doctrine_gates contains duplicate gate: {result.gate}.")
            gate_map[result.gate] = result.state

        missing = [gate for gate in READINESS_DOCTRINE_GATES if gate not in gate_map]
        if missing:
            raise ValueError(
                f"doctrine_gates missing required gates: {', '.join(missing)}."
            )

        if self.trigger_data is None:
            if (
                self.status != "INSUFFICIENT_DATA"
                or "missing_trigger_context" not in self.insufficient_data_reasons
            ):
                raise ValueError(
                    "Missing trigger_data must fail closed as INSUFFICIENT_DATA "
                    "with insufficient_data_reasons including missing_trigger_context."
                )
        elif (
            self.status == "INSUFFICIENT_DATA"
            and "missing_trigger_context" in self.insufficient_data_reasons
        ):
            raise ValueError(
                "missing_trigger_context is invalid when trigger_data is present."
            )

        if self.status == "READY":
            if any(state != "PASS" for state in gate_map.values()):
                raise ValueError("READY requires all doctrine_gates states to be PASS.")
            if (
                self.wait_for_trigger_reason is not None
                or self.lockout_reason is not None
                or self.insufficient_data_reasons
                or self.missing_inputs
            ):
                raise ValueError(
                    "READY must not include wait_for_trigger_reason, lockout_reason, "
                    "insufficient_data_reasons, or missing_inputs."
                )
            return self

        if self.status == "WAIT_FOR_TRIGGER":
            if gate_map["trigger_gate"] != "WAIT":
                raise ValueError(
                    "WAIT_FOR_TRIGGER requires doctrine_gates.trigger_gate state = WAIT."
                )
            for gate in (
                "data_sufficiency_gate",
                "context_alignment_gate",
                "structure_quality_gate",
                "risk_window_gate",
                "lockout_gate",
            ):
                if gate_map[gate] != "PASS":
                    raise ValueError(
                        "WAIT_FOR_TRIGGER requires all non-trigger doctrine_gates to be PASS."
                    )
            if self.wait_for_trigger_reason is None:
                raise ValueError("WAIT_FOR_TRIGGER requires wait_for_trigger_reason.")
            if self.lockout_reason is not None or self.insufficient_data_reasons or self.missing_inputs:
                raise ValueError(
                    "WAIT_FOR_TRIGGER must not include lockout_reason, "
                    "insufficient_data_reasons, or missing_inputs."
                )
            return self

        if self.status == "LOCKED_OUT":
            if gate_map["lockout_gate"] != "FAIL":
                raise ValueError("LOCKED_OUT requires doctrine_gates.lockout_gate state = FAIL.")
            for gate in (
                "data_sufficiency_gate",
                "context_alignment_gate",
                "structure_quality_gate",
                "trigger_gate",
                "risk_window_gate",
            ):
                if gate_map[gate] != "PASS":
                    raise ValueError(
                        "LOCKED_OUT requires all non-lockout doctrine_gates to be PASS."
                    )
            if self.lockout_reason is None:
                raise ValueError("LOCKED_OUT requires lockout_reason.")
            if (
                self.wait_for_trigger_reason is not None
                or self.insufficient_data_reasons
                or self.missing_inputs
            ):
                raise ValueError(
                    "LOCKED_OUT must not include wait_for_trigger_reason, "
                    "insufficient_data_reasons, or missing_inputs."
                )
            return self

        if gate_map["data_sufficiency_gate"] != "FAIL":
            raise ValueError(
                "INSUFFICIENT_DATA requires doctrine_gates.data_sufficiency_gate state = FAIL."
            )
        for gate in (
            "context_alignment_gate",
            "structure_quality_gate",
            "trigger_gate",
            "risk_window_gate",
            "lockout_gate",
        ):
            if gate_map[gate] != "PASS":
                raise ValueError(
                    "INSUFFICIENT_DATA requires all non-data-sufficiency doctrine_gates to be PASS."
                )
        if not self.insufficient_data_reasons:
            raise ValueError("INSUFFICIENT_DATA requires insufficient_data_reasons.")
        if not self.missing_inputs:
            raise ValueError("INSUFFICIENT_DATA requires missing_inputs.")
        if self.wait_for_trigger_reason is not None or self.lockout_reason is not None:
            raise ValueError(
                "INSUFFICIENT_DATA must not include wait_for_trigger_reason or lockout_reason."
            )
        return self


class KeyLevels(StrictModel):
    support_levels: list[float] = Field(max_length=3)
    resistance_levels: list[float] = Field(max_length=3)
    pivot_level: float | None


class ValueContext(StrictModel):
    relative_to_prior_value_area: Literal["above", "inside", "below"]
    relative_to_current_developing_value: Literal["above_vah", "inside_value", "below_val"]
    relative_to_vwap: Literal["above", "at", "below"]
    relative_to_prior_day_range: Literal["above", "inside", "below"]


class ContractAnalysis(StrictModel):
    schema_name: Literal["contract_analysis_v1"] = Field(
        default="contract_analysis_v1",
        alias="$schema",
    )
    stage: Literal["contract_market_read"] = "contract_market_read"
    contract: ContractSymbol
    timestamp: AwareDatetime
    market_regime: MarketRegime
    directional_bias: DirectionalBias
    key_levels: KeyLevels
    evidence_score: int = Field(ge=1, le=10)
    confidence_band: ConfidenceBand
    value_context: ValueContext
    structural_notes: str
    outcome: Literal["ANALYSIS_COMPLETE", "NO_TRADE"]
    conflicting_signals: list[str] | None = None
    assumptions: list[str] | None = None

    @model_validator(mode="after")
    def validate_confidence_and_conflicts(self) -> "ContractAnalysis":
        expected_band = (
            "LOW"
            if self.evidence_score <= 3
            else "MEDIUM"
            if self.evidence_score <= 6
            else "HIGH"
        )
        if self.confidence_band != expected_band:
            raise ValueError(
                "confidence_band must match evidence_score buckets: "
                "1-3 LOW, 4-6 MEDIUM, 7-10 HIGH."
            )

        conflicts = len(self.conflicting_signals or [])
        if conflicts >= 3 and self.evidence_score > 4:
            raise ValueError(
                "evidence_score must be <= 4 when three or more conflicting_signals are present."
            )
        if conflicts >= 2 and self.evidence_score > 6:
            raise ValueError(
                "evidence_score must be <= 6 when two or more conflicting_signals are present."
            )
        return self


class SizingMath(StrictModel):
    stop_distance_ticks: float
    risk_per_tick: float
    raw_risk_dollars: float
    slippage_cost_dollars: float
    adjusted_risk_dollars: float
    blended_target_distance_ticks: float
    blended_reward_dollars: float


class ProposedSetup(StrictModel):
    schema_name: Literal["proposed_setup_v1"] = Field(
        default="proposed_setup_v1",
        alias="$schema",
    )
    stage: Literal["setup_construction"] = "setup_construction"
    contract: ContractSymbol
    timestamp: AwareDatetime
    outcome: Literal["SETUP_PROPOSED", "NO_TRADE"]
    no_trade_reason: str | None = None
    direction: TradeDirection | None = None
    entry_price: float | None = None
    stop_price: float | None = None
    target_1: float | None = None
    target_2: float | None = None
    position_size: int | None = Field(default=None, ge=1)
    risk_dollars: float | None = None
    reward_risk_ratio: float | None = None
    setup_class: SetupClass | None = None
    hold_time_estimate_minutes: int | None = Field(default=None, ge=0)
    rationale: str | None = None
    disqualifiers: list[str] | None = None
    sizing_math: SizingMath | None = None

    @model_validator(mode="after")
    def validate_outcome_shape(self) -> "ProposedSetup":
        setup_required = {
            "direction": self.direction,
            "entry_price": self.entry_price,
            "stop_price": self.stop_price,
            "target_1": self.target_1,
            "position_size": self.position_size,
            "risk_dollars": self.risk_dollars,
            "reward_risk_ratio": self.reward_risk_ratio,
            "setup_class": self.setup_class,
            "hold_time_estimate_minutes": self.hold_time_estimate_minutes,
            "rationale": self.rationale,
            "disqualifiers": self.disqualifiers,
            "sizing_math": self.sizing_math,
        }

        if self.outcome == "NO_TRADE":
            if not self.no_trade_reason:
                raise ValueError("NO_TRADE outcome requires no_trade_reason.")
            if any(value is not None for value in setup_required.values()) or self.target_2 is not None:
                raise ValueError("NO_TRADE outcome must not include setup fields.")
            return self

        if self.no_trade_reason is not None:
            raise ValueError("SETUP_PROPOSED must not include no_trade_reason.")
        missing = [name for name, value in setup_required.items() if value is None]
        if missing:
            raise ValueError(
                f"SETUP_PROPOSED requires non-null values for: {', '.join(missing)}."
            )
        if self.position_size == 1:
            if self.target_2 is not None:
                raise ValueError("target_2 must be null when position_size is 1.")
        elif self.target_2 is None:
            raise ValueError("target_2 is required when position_size is greater than 1.")
        return self


class RiskCheck(StrictModel):
    check_id: int = Field(ge=1, le=13)
    check_name: str
    passed: bool
    detail: str


class RiskAuthorization(StrictModel):
    schema_name: Literal["risk_authorization_v1"] = Field(
        default="risk_authorization_v1",
        alias="$schema",
    )
    stage: Literal["risk_authorization"] = "risk_authorization"
    contract: ContractSymbol
    timestamp: AwareDatetime
    decision: RiskDecision
    checks_count: Literal[13] = 13
    checks: list[RiskCheck]
    rejection_reasons: list[str] = Field(default_factory=list)
    adjusted_position_size: int | None = Field(default=None, ge=1)
    adjusted_risk_dollars: float | None = None
    remaining_daily_risk_budget: float | None = None
    remaining_aggregate_risk_budget: float | None = None

    @model_validator(mode="after")
    def validate_checks_and_decision(self) -> "RiskAuthorization":
        if len(self.checks) != 13:
            raise ValueError("risk_authorization.checks must contain exactly 13 entries.")

        expected_ids = list(range(1, 14))
        actual_ids = [check.check_id for check in self.checks]
        if actual_ids != expected_ids:
            raise ValueError(
                "risk_authorization.checks must contain check_id values 1 through 13 in order."
            )

        if self.decision == "REDUCED":
            if self.adjusted_position_size is None or self.adjusted_risk_dollars is None:
                raise ValueError(
                    "REDUCED decision requires adjusted_position_size and adjusted_risk_dollars."
                )
        elif self.adjusted_position_size is not None or self.adjusted_risk_dollars is not None:
            raise ValueError(
                "adjusted_position_size and adjusted_risk_dollars are only valid for REDUCED decisions."
            )

        if self.decision == "REJECTED" and not self.rejection_reasons:
            raise ValueError("REJECTED decision must include rejection_reasons.")
        return self


class LoggingRecord(StrictModel):
    schema_name: Literal["logging_record_v1"] = Field(
        default="logging_record_v1",
        alias="$schema",
    )
    record_id: str
    contract: ContractSymbol
    pipeline_start_timestamp: AwareDatetime
    pipeline_end_timestamp: AwareDatetime
    final_decision: FinalDecision
    termination_stage: TerminationStage
    stages_completed: list[TerminationStage]
    sufficiency_gate_output: SufficiencyGateOutput
    contract_analysis: ContractAnalysis | None
    proposed_setup: ProposedSetup | None
    risk_authorization: RiskAuthorization | None
    challenge_state_snapshot: ChallengeState
    market_packet_snapshot: AllMarketPacket
    data_quality_flags: list[str] | None = None

    @model_validator(mode="after")
    def validate_pipeline_shape(self) -> "LoggingRecord":
        if self.pipeline_end_timestamp < self.pipeline_start_timestamp:
            raise ValueError("pipeline_end_timestamp must be after pipeline_start_timestamp.")

        if self.sufficiency_gate_output.contract != self.contract:
            raise ValueError("sufficiency_gate_output contract must match logging_record contract.")
        if self.market_packet_snapshot.contract != self.contract:
            raise ValueError("market_packet_snapshot contract must match logging_record contract.")
        if self.contract_analysis and self.contract_analysis.contract != self.contract:
            raise ValueError("contract_analysis contract must match logging_record contract.")
        if self.proposed_setup and self.proposed_setup.contract != self.contract:
            raise ValueError("proposed_setup contract must match logging_record contract.")
        if self.risk_authorization and self.risk_authorization.contract != self.contract:
            raise ValueError("risk_authorization contract must match logging_record contract.")

        expected_stage_sequences: dict[TerminationStage, list[TerminationStage]] = {
            "sufficiency_gate": ["sufficiency_gate"],
            "contract_market_read": ["sufficiency_gate", "contract_market_read"],
            "setup_construction": [
                "sufficiency_gate",
                "contract_market_read",
                "setup_construction",
            ],
            "risk_authorization": [
                "sufficiency_gate",
                "contract_market_read",
                "setup_construction",
                "risk_authorization",
            ],
        }
        if self.stages_completed != expected_stage_sequences[self.termination_stage]:
            raise ValueError("stages_completed must match termination_stage in order.")

        if self.termination_stage == "sufficiency_gate":
            if any(
                value is not None
                for value in (self.contract_analysis, self.proposed_setup, self.risk_authorization)
            ):
                raise ValueError("Stage A termination must not include later-stage outputs.")
            if self.final_decision != self.sufficiency_gate_output.status:
                raise ValueError(
                    "Stage A termination final_decision must match sufficiency_gate_output.status."
                )
            return self

        if self.contract_analysis is None:
            raise ValueError("contract_analysis is required after Stage A.")

        if self.termination_stage == "contract_market_read":
            if self.proposed_setup is not None or self.risk_authorization is not None:
                raise ValueError("Stage B termination must not include Stage C or D outputs.")
            if self.contract_analysis.outcome != "NO_TRADE" or self.final_decision != "NO_TRADE":
                raise ValueError(
                    "Stage B termination requires contract_analysis.outcome = NO_TRADE and final_decision = NO_TRADE."
                )
            return self

        if self.proposed_setup is None:
            raise ValueError("proposed_setup is required after Stage B.")

        if self.termination_stage == "setup_construction":
            if self.risk_authorization is not None:
                raise ValueError("Stage C termination must not include Stage D output.")
            if self.proposed_setup.outcome != "NO_TRADE" or self.final_decision != "NO_TRADE":
                raise ValueError(
                    "Stage C termination requires proposed_setup.outcome = NO_TRADE and final_decision = NO_TRADE."
                )
            return self

        if self.risk_authorization is None:
            raise ValueError("risk_authorization is required for Stage D termination.")
        if self.proposed_setup.outcome != "SETUP_PROPOSED":
            raise ValueError("Stage D termination requires proposed_setup.outcome = SETUP_PROPOSED.")

        expected_final_decision = {
            "APPROVED": "TRADE_APPROVED",
            "REDUCED": "TRADE_REDUCED",
            "REJECTED": "TRADE_REJECTED",
        }[self.risk_authorization.decision]
        if self.final_decision != expected_final_decision:
            raise ValueError(
                "final_decision must match risk_authorization.decision for Stage D termination."
            )
        return self


class ScaleOutFill(StrictModel):
    target: Literal["target_1", "target_2"]
    fill_price: float
    size: int = Field(ge=1)
    pnl: float


class PostTradeReviewRecord(StrictModel):
    schema_name: Literal["post_trade_review_record_v1"] = Field(
        default="post_trade_review_record_v1",
        alias="$schema",
    )
    review_id: str
    logging_record_id: str
    contract: ContractSymbol
    direction: TradeDirection
    entry_price: float
    exit_price: float
    actual_entry_slippage_ticks: float
    actual_exit_slippage_ticks: float
    position_size: int = Field(ge=1)
    realized_pnl: float
    mae_ticks: float
    mfe_ticks: float
    hold_time_minutes: int = Field(ge=0)
    exit_type: ExitType
    setup_class: SetupClass
    scale_out_fills: list[ScaleOutFill] | None = None
    planned_reward_risk_ratio: float
    actual_reward_risk_ratio: float
    market_regime_at_entry: MarketRegime
    confidence_band_at_entry: ConfidenceBand
    operator_notes: str | None = None
