from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Final

from ntb_marimo_console.contract_universe import contract_policy_label, is_final_target_contract, normalize_contract_symbol
from ntb_marimo_console.market_data.stream_events import redact_sensitive_text


PERFORMANCE_REVIEW_SCHEMA: Final[str] = "performance_review_v1"
MANUAL_OUTCOME_SCHEMA: Final[str] = "manual_outcome_record_v1"
SYSTEM_DECISION_SCHEMA: Final[str] = "system_decision_record_v1"
DEFAULT_MIN_SAMPLE_SIZE: Final[int] = 20
DEFAULT_MIN_NO_TRADE_RATE: Final[float] = 0.40
DEFAULT_EXPECTANCY_THRESHOLD_R: Final[float] = 0.0
FAILURE_TAXONOMY_CATEGORIES: Final[tuple[str, ...]] = (
    "data_sufficiency_failure",
    "premarket_plan_failure",
    "trigger_logic_failure",
    "market_read_failure",
    "setup_construction_failure",
    "risk_gate_failure",
    "operator_execution_failure",
    "normal_variance",
    "external_event_failure",
)
MINIMAL_REVIEW_V1_FAILURE_CATEGORIES: Final[tuple[str, ...]] = (
    "no_produced_trigger_readiness",
    "query_blocked_by_gate",
    "pipeline_no_trade",
    "pipeline_rejected",
    "pipeline_approved_but_no_manual_execution_recorded",
    "manual_execution_recorded_but_outcome_missing",
    "insufficient_sample",
)
MINIMAL_REVIEW_V1_PAUSE_CRITERIA: Final[tuple[str, ...]] = (
    "high_blocked_query_rate",
    "repeated_missing_required_fields",
    "repeated_stale_or_unavailable_data",
    "repeated_no_trade_outcomes",
    "insufficient_sample_size",
    "missing_manual_outcome_data",
)
METRIC_IDS: Final[tuple[str, ...]] = (
    "no_trade_rate",
    "trigger_to_query_rate",
    "query_to_approval_rate",
    "approval_to_execution_rate",
    "win_rate",
    "expectancy",
    "mfe",
    "mae",
    "realized_rr",
    "slippage",
    "hold_time",
    "time_of_day_performance",
    "contract_performance",
)
SAFE_FAILURE_SUMMARY_KEYS: Final[tuple[str, ...]] = (
    "failure_category",
    "failure_source",
    "reason",
    "record_id",
    "event_id",
)
APPROVAL_DECISIONS: Final[tuple[str, ...]] = ("TRADE_APPROVED", "APPROVED", "TRADE_REDUCED", "REDUCED")
SAFE_REF_RE: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9_.:/=-]+")
SENSITIVE_REF_TERMS: Final[tuple[str, ...]] = (
    "access_token",
    "refresh_token",
    "authorization",
    "bearer",
    "secret",
    "app_key",
    "app_secret",
    "credential",
    "token",
    "customer",
    "correl",
    "account",
    "://",
)


class MetricStatus(StrEnum):
    COMPUTED = "computed"
    UNAVAILABLE = "unavailable"
    INSUFFICIENT_SAMPLE = "insufficient_sample"
    NOT_APPLICABLE = "not_applicable"


class RecordStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"


class ReviewStatus(StrEnum):
    READY = "ready"
    INCOMPLETE = "incomplete"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class SampleSizeAssessment:
    eligible_count: int
    minimum_required: int
    status: MetricStatus
    conclusion: str

    def to_dict(self) -> dict[str, object]:
        return {
            "eligible_count": self.eligible_count,
            "minimum_required": self.minimum_required,
            "status": self.status.value,
            "conclusion": self.conclusion,
            "edge_claim_allowed": False,
        }


@dataclass(frozen=True)
class PerformanceMetric:
    metric_id: str
    status: MetricStatus
    value: object | None
    sample_size: int
    minimum_sample_size: int
    reasons: tuple[str, ...]
    edge_claim: str = "none"

    def to_dict(self) -> dict[str, object]:
        return {
            "metric_id": self.metric_id,
            "status": self.status.value,
            "value": self.value,
            "sample_size": self.sample_size,
            "minimum_sample_size": self.minimum_sample_size,
            "reasons": list(self.reasons),
            "edge_claim": self.edge_claim,
        }


@dataclass(frozen=True)
class FailureTaxonomyClassification:
    category: str
    valid: bool
    status: RecordStatus
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "category": self.category,
            "valid": self.valid,
            "status": self.status.value,
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class PauseRuleResult:
    rule_id: str
    triggered: bool
    severity: str
    reason: str
    supporting_record_ids: tuple[str, ...]
    cannot_authorize_execution: bool = True

    def to_dict(self) -> dict[str, object]:
        return {
            "rule_id": self.rule_id,
            "triggered": self.triggered,
            "severity": self.severity,
            "reason": self.reason,
            "supporting_record_ids": list(self.supporting_record_ids),
            "cannot_authorize_execution": self.cannot_authorize_execution,
        }


@dataclass(frozen=True)
class SystemDecisionRecord:
    record_id: str
    timestamp: str
    contract: str
    profile_id: str
    pipeline_run_id: str | None
    final_decision: str
    trigger_query_ready: bool
    query_submitted: bool
    gate_enabled: bool
    risk_gate_bypassed: bool
    fake_ready_state: bool
    unsupported_contract_ready: bool
    stale_data_hidden_from_operator: bool
    failure_category: str | None
    status: RecordStatus
    invalid_reasons: tuple[str, ...]
    schema: str = SYSTEM_DECISION_SCHEMA

    @property
    def valid(self) -> bool:
        return self.status == RecordStatus.VALID

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "record_id": self.record_id,
            "timestamp": self.timestamp,
            "contract": self.contract,
            "profile_id": self.profile_id,
            "pipeline_run_id": self.pipeline_run_id,
            "final_decision": self.final_decision,
            "trigger_query_ready": self.trigger_query_ready,
            "query_submitted": self.query_submitted,
            "gate_enabled": self.gate_enabled,
            "risk_gate_bypassed": self.risk_gate_bypassed,
            "fake_ready_state": self.fake_ready_state,
            "unsupported_contract_ready": self.unsupported_contract_ready,
            "stale_data_hidden_from_operator": self.stale_data_hidden_from_operator,
            "failure_category": self.failure_category,
            "status": self.status.value,
            "valid": self.valid,
            "invalid_reasons": list(self.invalid_reasons),
        }


@dataclass(frozen=True)
class ManualOutcomeRecord:
    record_id: str
    timestamp: str
    contract: str
    profile_id: str
    pipeline_run_id: str | None
    source: str
    executed: bool
    recorded_system_approved: bool
    query_ready_at_execution: bool
    outcome_r: float | None
    mfe_r: float | None
    mae_r: float | None
    realized_rr: float | None
    slippage_ticks: float | None
    hold_minutes: float | None
    time_of_day: str | None
    daily_stop_out: bool
    week_id: str | None
    failure_category: str | None
    operator_note: str | None
    status: RecordStatus
    invalid_reasons: tuple[str, ...]
    schema: str = MANUAL_OUTCOME_SCHEMA

    @property
    def valid(self) -> bool:
        return self.status == RecordStatus.VALID

    @property
    def loss(self) -> bool:
        return self.executed and self.outcome_r is not None and self.outcome_r < 0

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "record_id": self.record_id,
            "timestamp": self.timestamp,
            "contract": self.contract,
            "profile_id": self.profile_id,
            "pipeline_run_id": self.pipeline_run_id,
            "source": self.source,
            "executed": self.executed,
            "recorded_system_approved": self.recorded_system_approved,
            "query_ready_at_execution": self.query_ready_at_execution,
            "outcome_r": self.outcome_r,
            "mfe_r": self.mfe_r,
            "mae_r": self.mae_r,
            "realized_rr": self.realized_rr,
            "slippage_ticks": self.slippage_ticks,
            "hold_minutes": self.hold_minutes,
            "time_of_day": self.time_of_day,
            "daily_stop_out": self.daily_stop_out,
            "week_id": self.week_id,
            "failure_category": self.failure_category,
            "operator_note": self.operator_note,
            "status": self.status.value,
            "valid": self.valid,
            "invalid_reasons": list(self.invalid_reasons),
        }


@dataclass(frozen=True)
class ReviewInput:
    contract: str
    profile_id: str | None = None
    replay_summaries: tuple[Mapping[str, object], ...] = ()
    evidence_events: tuple[Mapping[str, object], ...] = ()
    system_decisions: tuple[SystemDecisionRecord | Mapping[str, object], ...] = ()
    manual_outcomes: tuple[ManualOutcomeRecord | Mapping[str, object], ...] = ()
    minimum_sample_size: int = DEFAULT_MIN_SAMPLE_SIZE
    no_trade_minimum_rate: float = DEFAULT_MIN_NO_TRADE_RATE
    expectancy_threshold_r: float = DEFAULT_EXPECTANCY_THRESHOLD_R


@dataclass(frozen=True)
class PerformanceReviewSummary:
    contract: str
    profile_id: str | None
    status: ReviewStatus
    sample_size_assessment: SampleSizeAssessment
    system_decision_quality: dict[str, object]
    trader_execution_quality: dict[str, object]
    data_sufficiency_failures: tuple[dict[str, object], ...]
    metrics: tuple[PerformanceMetric, ...]
    failure_taxonomy: tuple[FailureTaxonomyClassification, ...]
    pause_rules: tuple[PauseRuleResult, ...]
    minimal_review_v1: dict[str, object]
    blocking_reasons: tuple[str, ...]
    review_scope: str = "post_session_fixture_or_manual_review_only"
    schema: str = PERFORMANCE_REVIEW_SCHEMA

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "contract": self.contract,
            "profile_id": self.profile_id,
            "status": self.status.value,
            "sample_size_assessment": self.sample_size_assessment.to_dict(),
            "system_decision_quality": self.system_decision_quality,
            "trader_execution_quality": self.trader_execution_quality,
            "data_sufficiency_failures": list(self.data_sufficiency_failures),
            "metrics": [metric.to_dict() for metric in self.metrics],
            "failure_taxonomy": [classification.to_dict() for classification in self.failure_taxonomy],
            "pause_rules": [rule.to_dict() for rule in self.pause_rules],
            "minimal_review_v1": self.minimal_review_v1,
            "blocking_reasons": list(self.blocking_reasons),
            "review_scope": self.review_scope,
            "ui_wiring_status": "available_as_review_model_only_not_query_authority",
            "performance_review_can_authorize_trades": False,
            "cannot_authorize_execution": True,
            "edge_claim_allowed": False,
        }


def create_system_decision_record(
    *,
    record_id: str,
    timestamp: str,
    contract: str,
    profile_id: str,
    final_decision: str,
    pipeline_run_id: str | None = None,
    trigger_query_ready: bool = False,
    query_submitted: bool = False,
    gate_enabled: bool = False,
    risk_gate_bypassed: bool = False,
    fake_ready_state: bool = False,
    unsupported_contract_ready: bool = False,
    stale_data_hidden_from_operator: bool = False,
    failure_category: str | None = None,
) -> SystemDecisionRecord:
    normalized_contract = normalize_contract_symbol(contract)
    invalid_reasons: list[str] = []
    taxonomy = classify_failure_taxonomy(failure_category) if failure_category is not None else None
    if not is_final_target_contract(normalized_contract):
        invalid_reasons.append(f"contract_not_final_supported:{normalized_contract}:{contract_policy_label(normalized_contract)}")
    if not _is_timezone_aware_iso(timestamp):
        invalid_reasons.append("timestamp_not_timezone_aware_iso")
    if taxonomy is not None and not taxonomy.valid:
        invalid_reasons.extend(taxonomy.reasons)
    if unsupported_contract_ready and is_final_target_contract(normalized_contract):
        invalid_reasons.append("unsupported_contract_ready_flag_on_supported_contract")
    status = RecordStatus.INVALID if invalid_reasons else RecordStatus.VALID
    return SystemDecisionRecord(
        record_id=_safe_ref(record_id),
        timestamp=_safe_text(timestamp),
        contract=normalized_contract,
        profile_id=_safe_ref(profile_id),
        pipeline_run_id=_safe_optional_ref(pipeline_run_id),
        final_decision=_safe_text(final_decision).upper(),
        trigger_query_ready=bool(trigger_query_ready),
        query_submitted=bool(query_submitted),
        gate_enabled=bool(gate_enabled),
        risk_gate_bypassed=bool(risk_gate_bypassed),
        fake_ready_state=bool(fake_ready_state),
        unsupported_contract_ready=bool(unsupported_contract_ready),
        stale_data_hidden_from_operator=bool(stale_data_hidden_from_operator),
        failure_category=taxonomy.category if taxonomy is not None and taxonomy.valid else None,
        status=status,
        invalid_reasons=tuple(invalid_reasons),
    )


def create_manual_outcome_record(
    *,
    record_id: str,
    timestamp: str,
    contract: str,
    profile_id: str,
    source: str = "manual",
    pipeline_run_id: str | None = None,
    executed: bool = False,
    recorded_system_approved: bool = False,
    query_ready_at_execution: bool = False,
    outcome_r: float | int | None = None,
    mfe_r: float | int | None = None,
    mae_r: float | int | None = None,
    realized_rr: float | int | None = None,
    slippage_ticks: float | int | None = None,
    hold_minutes: float | int | None = None,
    time_of_day: str | None = None,
    daily_stop_out: bool = False,
    week_id: str | None = None,
    failure_category: str | None = None,
    operator_note: str | None = None,
) -> ManualOutcomeRecord:
    normalized_contract = normalize_contract_symbol(contract)
    safe_source = _safe_text(source).lower()
    invalid_reasons: list[str] = []
    taxonomy = classify_failure_taxonomy(failure_category) if failure_category is not None else None
    if not is_final_target_contract(normalized_contract):
        invalid_reasons.append(f"contract_not_final_supported:{normalized_contract}:{contract_policy_label(normalized_contract)}")
    if safe_source not in {"manual", "fixture"}:
        invalid_reasons.append(f"unsupported_manual_outcome_source:{safe_source or 'missing'}")
    if not _is_timezone_aware_iso(timestamp):
        invalid_reasons.append("timestamp_not_timezone_aware_iso")
    if taxonomy is not None and not taxonomy.valid:
        invalid_reasons.extend(taxonomy.reasons)
    status = RecordStatus.INVALID if invalid_reasons else RecordStatus.VALID
    return ManualOutcomeRecord(
        record_id=_safe_ref(record_id),
        timestamp=_safe_text(timestamp),
        contract=normalized_contract,
        profile_id=_safe_ref(profile_id),
        pipeline_run_id=_safe_optional_ref(pipeline_run_id),
        source=safe_source,
        executed=bool(executed),
        recorded_system_approved=bool(recorded_system_approved),
        query_ready_at_execution=bool(query_ready_at_execution),
        outcome_r=_safe_float(outcome_r),
        mfe_r=_safe_float(mfe_r),
        mae_r=_safe_float(mae_r),
        realized_rr=_safe_float(realized_rr),
        slippage_ticks=_safe_float(slippage_ticks),
        hold_minutes=_safe_float(hold_minutes),
        time_of_day=_safe_optional_ref(time_of_day),
        daily_stop_out=bool(daily_stop_out),
        week_id=_safe_optional_ref(week_id),
        failure_category=taxonomy.category if taxonomy is not None and taxonomy.valid else None,
        operator_note=_safe_optional(operator_note),
        status=status,
        invalid_reasons=tuple(invalid_reasons),
    )


def classify_failure_taxonomy(category: str | None) -> FailureTaxonomyClassification:
    safe_category = _safe_text(category or "").strip().lower()
    if safe_category in FAILURE_TAXONOMY_CATEGORIES:
        return FailureTaxonomyClassification(
            category=safe_category,
            valid=True,
            status=RecordStatus.VALID,
            reasons=(),
        )
    return FailureTaxonomyClassification(
        category=safe_category or "unknown",
        valid=False,
        status=RecordStatus.INVALID,
        reasons=(f"unknown_failure_taxonomy:{safe_category or 'missing'}",),
    )


def serialize_performance_review_summary(summary: PerformanceReviewSummary) -> str:
    return json.dumps(summary.to_dict(), sort_keys=True)


def parse_manual_outcome_record(payload: str | Mapping[str, object]) -> ManualOutcomeRecord:
    loaded = _load_mapping(payload)
    if loaded is None:
        return create_manual_outcome_record(
            record_id="invalid_payload",
            timestamp="",
            contract="UNKNOWN",
            profile_id="unknown",
            failure_category="unknown",
        )
    required = ("record_id", "timestamp", "contract", "profile_id", "source", "executed")
    missing = tuple(field for field in required if field not in loaded)
    if missing:
        record = create_manual_outcome_record(
            record_id=_string_field(loaded.get("record_id") or "missing_required_fields"),
            timestamp=_string_field(loaded.get("timestamp")),
            contract=_string_field(loaded.get("contract")),
            profile_id=_string_field(loaded.get("profile_id")),
            source=_string_field(loaded.get("source")),
        )
        return _manual_with_extra_errors(record, tuple(f"missing_required_field:{field}" for field in missing))
    return create_manual_outcome_record(
        record_id=_string_field(loaded.get("record_id")),
        timestamp=_string_field(loaded.get("timestamp")),
        contract=_string_field(loaded.get("contract")),
        profile_id=_string_field(loaded.get("profile_id")),
        source=_string_field(loaded.get("source")),
        pipeline_run_id=_optional_string_field(loaded.get("pipeline_run_id")),
        executed=loaded.get("executed") is True,
        recorded_system_approved=loaded.get("recorded_system_approved") is True,
        query_ready_at_execution=loaded.get("query_ready_at_execution") is True,
        outcome_r=_numeric_or_none(loaded.get("outcome_r")),
        mfe_r=_numeric_or_none(loaded.get("mfe_r")),
        mae_r=_numeric_or_none(loaded.get("mae_r")),
        realized_rr=_numeric_or_none(loaded.get("realized_rr")),
        slippage_ticks=_numeric_or_none(loaded.get("slippage_ticks")),
        hold_minutes=_numeric_or_none(loaded.get("hold_minutes")),
        time_of_day=_optional_string_field(loaded.get("time_of_day")),
        daily_stop_out=loaded.get("daily_stop_out") is True,
        week_id=_optional_string_field(loaded.get("week_id")),
        failure_category=_optional_string_field(loaded.get("failure_category")),
        operator_note=_optional_string_field(loaded.get("operator_note")),
    )


def build_performance_review_summary(review_input: ReviewInput | Mapping[str, object]) -> PerformanceReviewSummary:
    request = _review_input(review_input)
    contract = normalize_contract_symbol(request.contract)
    manual_outcomes = _normalize_manual_outcomes(request.manual_outcomes)
    replay_summaries = tuple(_safe_mapping(item) for item in request.replay_summaries if isinstance(item, Mapping))
    evidence_events = tuple(_safe_mapping(item) for item in request.evidence_events if isinstance(item, Mapping))
    supplied_system_decisions = _normalize_system_decisions(request.system_decisions)
    system_decisions = supplied_system_decisions or _system_decisions_from_evidence_events(
        contract=contract,
        profile_id=request.profile_id,
        evidence_events=evidence_events,
    )
    blocking: list[str] = []

    if not is_final_target_contract(contract):
        blocking.append(f"review_contract_not_final_supported:{contract}:{contract_policy_label(contract)}")
    for record in system_decisions:
        if record.contract != contract:
            blocking.append(f"cross_contract_system_decision:{record.contract}->{contract}:{record.record_id}")
        if not record.valid:
            blocking.extend(f"invalid_system_decision:{record.record_id}:{reason}" for reason in record.invalid_reasons)
    for record in manual_outcomes:
        if record.contract != contract:
            blocking.append(f"cross_contract_manual_outcome:{record.contract}->{contract}:{record.record_id}")
        if not record.valid:
            blocking.extend(f"invalid_manual_outcome:{record.record_id}:{reason}" for reason in record.invalid_reasons)

    sample = _sample_assessment(manual_outcomes, request.minimum_sample_size)
    metrics = _build_metrics(system_decisions, manual_outcomes, request.minimum_sample_size)
    taxonomy = _taxonomy_summary(system_decisions, manual_outcomes)
    pause_rules = _pause_rules(
        contract=contract,
        system_decisions=system_decisions,
        manual_outcomes=manual_outcomes,
        replay_summaries=replay_summaries,
        evidence_events=evidence_events,
        no_trade_rate_metric=_metric(metrics, "no_trade_rate"),
        minimum_system_sample_size=request.minimum_sample_size,
        no_trade_minimum_rate=request.no_trade_minimum_rate,
        expectancy_threshold_r=request.expectancy_threshold_r,
    )
    minimal_review = _minimal_review_v1(
        system_decisions=system_decisions,
        manual_outcomes=manual_outcomes,
        replay_summaries=replay_summaries,
        evidence_events=evidence_events,
        metrics=metrics,
        minimum_sample_size=request.minimum_sample_size,
    )
    status = ReviewStatus.BLOCKED if blocking else ReviewStatus.INCOMPLETE if not system_decisions else ReviewStatus.READY
    return PerformanceReviewSummary(
        contract=contract,
        profile_id=_safe_optional_ref(request.profile_id),
        status=status,
        sample_size_assessment=sample,
        system_decision_quality=_system_quality(system_decisions),
        trader_execution_quality=_trader_quality(manual_outcomes),
        data_sufficiency_failures=_data_sufficiency_failures(system_decisions, replay_summaries, evidence_events),
        metrics=metrics,
        failure_taxonomy=taxonomy,
        pause_rules=pause_rules,
        minimal_review_v1=minimal_review,
        blocking_reasons=_dedupe(blocking),
    )


def _build_metrics(
    decisions: Sequence[SystemDecisionRecord],
    outcomes: Sequence[ManualOutcomeRecord],
    minimum_sample_size: int,
) -> tuple[PerformanceMetric, ...]:
    metrics = [
        _rate_metric("no_trade_rate", _count_decision(decisions, "NO_TRADE"), len(decisions), minimum_sample_size, "system_decision_records_missing"),
        _rate_metric("trigger_to_query_rate", sum(1 for item in decisions if item.query_submitted), sum(1 for item in decisions if item.trigger_query_ready), minimum_sample_size, "trigger_query_ready_records_missing"),
        _rate_metric("query_to_approval_rate", sum(1 for item in decisions if _is_approval(item.final_decision)), sum(1 for item in decisions if item.query_submitted), minimum_sample_size, "query_submitted_records_missing"),
        _approval_to_execution_metric(decisions, outcomes, minimum_sample_size),
        _outcome_rate_metric("win_rate", outcomes, minimum_sample_size),
        _average_outcome_metric("expectancy", outcomes, minimum_sample_size, "outcome_r"),
        _average_manual_field_metric("mfe", outcomes, minimum_sample_size, "mfe_r"),
        _average_manual_field_metric("mae", outcomes, minimum_sample_size, "mae_r"),
        _average_manual_field_metric("realized_rr", outcomes, minimum_sample_size, "realized_rr"),
        _average_manual_field_metric("slippage", outcomes, minimum_sample_size, "slippage_ticks"),
        _average_manual_field_metric("hold_time", outcomes, minimum_sample_size, "hold_minutes"),
        _grouped_metric("time_of_day_performance", outcomes, minimum_sample_size, "time_of_day"),
        _grouped_metric("contract_performance", outcomes, minimum_sample_size, "contract"),
    ]
    return tuple(metrics)


def _minimal_review_v1(
    *,
    system_decisions: Sequence[SystemDecisionRecord],
    manual_outcomes: Sequence[ManualOutcomeRecord],
    replay_summaries: Sequence[Mapping[str, object]],
    evidence_events: Sequence[Mapping[str, object]],
    metrics: Sequence[PerformanceMetric],
    minimum_sample_size: int,
) -> dict[str, object]:
    approved_run_ids = {
        item.pipeline_run_id
        for item in system_decisions
        if item.pipeline_run_id and _is_approval(item.final_decision)
    }
    executed_run_ids = {item.pipeline_run_id for item in manual_outcomes if item.pipeline_run_id and item.executed}
    trigger_ready_count = sum(1 for item in system_decisions if item.trigger_query_ready)
    blocked_query_count = sum(
        1
        for item in system_decisions
        if item.trigger_query_ready and (not item.query_submitted or not item.gate_enabled)
    )
    no_trade_count = _count_decision(system_decisions, "NO_TRADE")
    missing_manual_outcome_count = len(approved_run_ids - executed_run_ids) + sum(
        1 for item in manual_outcomes if item.executed and item.outcome_r is None
    )
    insufficient_sample = len(system_decisions) < minimum_sample_size
    taxonomy_counts = {
        "no_produced_trigger_readiness": sum(1 for item in system_decisions if not item.trigger_query_ready),
        "query_blocked_by_gate": blocked_query_count,
        "pipeline_no_trade": no_trade_count,
        "pipeline_rejected": sum(1 for item in system_decisions if _is_rejection(item.final_decision)),
        "pipeline_approved_but_no_manual_execution_recorded": len(approved_run_ids - executed_run_ids),
        "manual_execution_recorded_but_outcome_missing": sum(
            1 for item in manual_outcomes if item.executed and item.outcome_r is None
        ),
        "insufficient_sample": 1 if insufficient_sample else 0,
    }
    missing_required_count = _reason_count(
        replay_summaries,
        evidence_events,
        ("missing_required", "missing field", "missing_field", "missing_required_field"),
    )
    stale_unavailable_count = _reason_count(
        replay_summaries,
        evidence_events,
        ("stale", "unavailable", "missing_bar", "missing_chart_bars"),
    )
    blocked_query_rate = blocked_query_count / trigger_ready_count if trigger_ready_count else None
    pause_criteria = (
        _minimal_pause_criterion(
            "high_blocked_query_rate",
            triggered=blocked_query_rate is not None and blocked_query_rate >= 0.50 and blocked_query_count >= 2,
            reason="Review repeated gate-blocked query progression before relying on the workflow.",
            observed_count=blocked_query_count,
        ),
        _minimal_pause_criterion(
            "repeated_missing_required_fields",
            triggered=missing_required_count >= 2,
            reason="Review repeated missing required fields in evidence or replay records.",
            observed_count=missing_required_count,
        ),
        _minimal_pause_criterion(
            "repeated_stale_or_unavailable_data",
            triggered=stale_unavailable_count >= 2,
            reason="Review repeated stale or unavailable data before continuing.",
            observed_count=stale_unavailable_count,
        ),
        _minimal_pause_criterion(
            "repeated_no_trade_outcomes",
            triggered=no_trade_count >= 2,
            reason="Review repeated NO_TRADE outcomes as system behavior, not as a trade signal.",
            observed_count=no_trade_count,
        ),
        _minimal_pause_criterion(
            "insufficient_sample_size",
            triggered=insufficient_sample,
            reason="Sample is insufficient for any statistical edge claim.",
            observed_count=len(system_decisions),
        ),
        _minimal_pause_criterion(
            "missing_manual_outcome_data",
            triggered=missing_manual_outcome_count > 0,
            reason="Manual execution/outcome review is incomplete because operator-entered outcome data is missing.",
            observed_count=missing_manual_outcome_count,
        ),
    )
    return {
        "schema": "minimal_performance_review_v1",
        "review_only": True,
        "can_authorize_query": False,
        "can_authorize_trade": False,
        "manual_only_execution": True,
        "system_decision_quality_statement": (
            "System decision quality reviews trigger, query, and preserved-pipeline outcomes only."
        ),
        "trader_execution_quality_statement": (
            "Trader execution quality uses optional operator-entered manual outcome records only."
        ),
        "metrics": {
            "no_trade_rate": _metric(metrics, "no_trade_rate").to_dict(),
            "trigger_to_query_rate": _metric(metrics, "trigger_to_query_rate").to_dict(),
            "query_to_approval_rate": _metric(metrics, "query_to_approval_rate").to_dict(),
            "approval_to_manual_execution_rate": _metric(metrics, "approval_to_execution_rate").to_dict(),
        },
        "failure_taxonomy": [
            {
                "category": category,
                "count": taxonomy_counts.get(category, 0),
            }
            for category in MINIMAL_REVIEW_V1_FAILURE_CATEGORIES
        ],
        "pause_criteria": [item for item in pause_criteria],
        "warnings": _minimal_review_warnings(
            system_decisions=system_decisions,
            manual_outcomes=manual_outcomes,
            minimum_sample_size=minimum_sample_size,
            missing_manual_outcome_count=missing_manual_outcome_count,
        ),
        "statistical_edge_claim": "not_claimed",
        "production_live_readiness_claim": "not_claimed",
    }


def _system_decisions_from_evidence_events(
    *,
    contract: str,
    profile_id: str | None,
    evidence_events: Sequence[Mapping[str, object]],
) -> tuple[SystemDecisionRecord, ...]:
    if not evidence_events:
        return ()
    query_run_ids = {
        _safe_optional_ref(event.get("pipeline_run_id"))
        for event in evidence_events
        if event.get("event_type") == "query_submitted"
    }
    query_run_ids.discard(None)
    trigger_ready = any(event.get("event_type") == "trigger_query_ready" for event in evidence_events)
    records: list[SystemDecisionRecord] = []
    for index, event in enumerate(evidence_events, start=1):
        if event.get("event_type") != "pipeline_result":
            continue
        event_contract = normalize_contract_symbol(_string_field(event.get("contract")))
        if event_contract != contract:
            continue
        run_id = _safe_optional_ref(event.get("pipeline_run_id"))
        summary = _pipeline_summary_from_event(event)
        records.append(
            create_system_decision_record(
                record_id=_safe_ref(event.get("event_id") or f"evidence_pipeline_result_{index}"),
                timestamp=_string_field(event.get("timestamp")),
                contract=event_contract,
                profile_id=_safe_optional_ref(event.get("profile_id")) or _safe_optional_ref(profile_id) or "",
                pipeline_run_id=run_id,
                final_decision=_string_field(summary.get("final_decision") or event.get("final_decision") or "UNKNOWN"),
                trigger_query_ready=trigger_ready,
                query_submitted=run_id in query_run_ids if run_id else bool(query_run_ids),
                gate_enabled=run_id in query_run_ids if run_id else bool(query_run_ids),
                failure_category=_failure_category_from_pipeline_summary(summary),
            )
        )
    return tuple(records)


def _pipeline_summary_from_event(event: Mapping[str, object]) -> Mapping[str, object]:
    data_quality = event.get("data_quality")
    if isinstance(data_quality, Mapping):
        summary = data_quality.get("pipeline_summary")
        if isinstance(summary, Mapping):
            return _safe_mapping(summary)
        return _safe_mapping(data_quality)
    return {}


def _failure_category_from_pipeline_summary(summary: Mapping[str, object]) -> str | None:
    decision = _string_field(summary.get("final_decision")).upper()
    if decision == "NO_TRADE":
        return "market_read_failure"
    if _is_rejection(decision):
        return "risk_gate_failure"
    return None


def _rate_metric(metric_id: str, numerator: int, denominator: int, minimum_sample_size: int, missing_reason: str) -> PerformanceMetric:
    if denominator <= 0:
        return PerformanceMetric(metric_id, MetricStatus.UNAVAILABLE, None, 0, minimum_sample_size, (missing_reason,))
    value = numerator / denominator
    if denominator < minimum_sample_size:
        return PerformanceMetric(metric_id, MetricStatus.INSUFFICIENT_SAMPLE, value, denominator, minimum_sample_size, ("descriptive_only_insufficient_sample",))
    return PerformanceMetric(metric_id, MetricStatus.COMPUTED, value, denominator, minimum_sample_size, ())


def _approval_to_execution_metric(
    decisions: Sequence[SystemDecisionRecord],
    outcomes: Sequence[ManualOutcomeRecord],
    minimum_sample_size: int,
) -> PerformanceMetric:
    approvals = tuple(item for item in decisions if _is_approval(item.final_decision))
    if not approvals:
        return PerformanceMetric("approval_to_execution_rate", MetricStatus.NOT_APPLICABLE, None, 0, minimum_sample_size, ("system_approval_records_missing",))
    if not outcomes:
        return PerformanceMetric("approval_to_execution_rate", MetricStatus.UNAVAILABLE, None, 0, minimum_sample_size, ("manual_execution_outcome_records_required",))
    approved_run_ids = {item.pipeline_run_id for item in approvals if item.pipeline_run_id}
    executed = sum(1 for item in outcomes if item.executed and item.pipeline_run_id in approved_run_ids)
    return _rate_metric("approval_to_execution_rate", executed, len(approvals), minimum_sample_size, "system_approval_records_missing")


def _outcome_rate_metric(metric_id: str, outcomes: Sequence[ManualOutcomeRecord], minimum_sample_size: int) -> PerformanceMetric:
    eligible = tuple(item for item in outcomes if item.executed and item.outcome_r is not None)
    if not eligible:
        return PerformanceMetric(metric_id, MetricStatus.UNAVAILABLE, None, 0, minimum_sample_size, ("manual_outcomes_missing",))
    wins = sum(1 for item in eligible if item.outcome_r is not None and item.outcome_r > 0)
    return _rate_metric(metric_id, wins, len(eligible), minimum_sample_size, "manual_outcomes_missing")


def _average_outcome_metric(metric_id: str, outcomes: Sequence[ManualOutcomeRecord], minimum_sample_size: int, field: str) -> PerformanceMetric:
    eligible = tuple(getattr(item, field) for item in outcomes if item.executed and getattr(item, field) is not None)
    if not eligible:
        return PerformanceMetric(metric_id, MetricStatus.UNAVAILABLE, None, 0, minimum_sample_size, (f"manual_{field}_missing",))
    value = sum(float(item) for item in eligible) / len(eligible)
    if len(eligible) < minimum_sample_size:
        return PerformanceMetric(metric_id, MetricStatus.INSUFFICIENT_SAMPLE, value, len(eligible), minimum_sample_size, ("descriptive_only_insufficient_sample",))
    return PerformanceMetric(metric_id, MetricStatus.COMPUTED, value, len(eligible), minimum_sample_size, ())


def _average_manual_field_metric(metric_id: str, outcomes: Sequence[ManualOutcomeRecord], minimum_sample_size: int, field: str) -> PerformanceMetric:
    eligible = tuple(getattr(item, field) for item in outcomes if getattr(item, field) is not None)
    if not eligible:
        return PerformanceMetric(metric_id, MetricStatus.UNAVAILABLE, None, 0, minimum_sample_size, (f"manual_{field}_missing",))
    value = sum(float(item) for item in eligible) / len(eligible)
    status = MetricStatus.INSUFFICIENT_SAMPLE if len(eligible) < minimum_sample_size else MetricStatus.COMPUTED
    reasons = ("descriptive_only_insufficient_sample",) if status == MetricStatus.INSUFFICIENT_SAMPLE else ()
    return PerformanceMetric(metric_id, status, value, len(eligible), minimum_sample_size, reasons)


def _grouped_metric(metric_id: str, outcomes: Sequence[ManualOutcomeRecord], minimum_sample_size: int, group_field: str) -> PerformanceMetric:
    groups: dict[str, list[float]] = {}
    for outcome in outcomes:
        outcome_r = outcome.outcome_r
        group_value = getattr(outcome, group_field)
        if outcome.executed and outcome_r is not None and group_value:
            groups.setdefault(str(group_value), []).append(outcome_r)
    sample_size = sum(len(values) for values in groups.values())
    if not groups:
        return PerformanceMetric(metric_id, MetricStatus.UNAVAILABLE, None, 0, minimum_sample_size, (f"manual_{group_field}_outcomes_missing",))
    value = {key: sum(values) / len(values) for key, values in sorted(groups.items())}
    status = MetricStatus.INSUFFICIENT_SAMPLE if sample_size < minimum_sample_size else MetricStatus.COMPUTED
    reasons = ("descriptive_only_insufficient_sample",) if status == MetricStatus.INSUFFICIENT_SAMPLE else ()
    return PerformanceMetric(metric_id, status, value, sample_size, minimum_sample_size, reasons)


def _pause_rules(
    *,
    contract: str,
    system_decisions: Sequence[SystemDecisionRecord],
    manual_outcomes: Sequence[ManualOutcomeRecord],
    replay_summaries: Sequence[Mapping[str, object]],
    evidence_events: Sequence[Mapping[str, object]],
    no_trade_rate_metric: PerformanceMetric,
    minimum_system_sample_size: int,
    no_trade_minimum_rate: float,
    expectancy_threshold_r: float,
) -> tuple[PauseRuleResult, ...]:
    rules = [
        _pause_rule("risk_gate_bypass", "critical", "Risk gate bypass evidence present.", tuple(item.record_id for item in system_decisions if item.risk_gate_bypassed)),
        _pause_rule("fake_ready_state", "critical", "Fake READY state evidence present.", tuple(item.record_id for item in system_decisions if item.fake_ready_state)),
        _pause_rule("unsupported_contract_appears_ready", "critical", "Unsupported contract appeared ready.", tuple(item.record_id for item in system_decisions if item.unsupported_contract_ready or not is_final_target_contract(item.contract))),
        _low_no_trade_rule(no_trade_rate_metric, no_trade_minimum_rate, minimum_system_sample_size),
        _rolling_expectancy_rule(manual_outcomes, expectancy_threshold_r),
        _five_losses_rule(contract, manual_outcomes),
        _daily_stopouts_rule(manual_outcomes),
        _pause_rule("live_data_stale_hidden", "high", "Live data stale state was hidden from the operator.", _stale_hidden_ids(system_decisions, replay_summaries, evidence_events)),
        _pause_rule("operator_execution_outside_query_ready_recorded_system_approved", "critical", "Operator execution outside QUERY_READY was recorded as system-approved.", tuple(item.record_id for item in manual_outcomes if item.executed and item.recorded_system_approved and not item.query_ready_at_execution)),
    ]
    return tuple(rules)


def _low_no_trade_rule(metric: PerformanceMetric, minimum_rate: float, minimum_sample_size: int) -> PauseRuleResult:
    triggered = metric.status == MetricStatus.COMPUTED and isinstance(metric.value, float) and metric.value < minimum_rate
    reason = "NO_TRADE rate below configured threshold over sufficient sample." if triggered else "NO_TRADE rate pause criterion not triggered."
    if metric.sample_size < minimum_sample_size:
        reason = "NO_TRADE rate pause criterion requires sufficient sample."
    return PauseRuleResult(
        rule_id="low_no_trade_rate",
        triggered=triggered,
        severity="medium" if triggered else "info",
        reason=reason,
        supporting_record_ids=(),
    )


def _rolling_expectancy_rule(outcomes: Sequence[ManualOutcomeRecord], threshold: float) -> PauseRuleResult:
    eligible = tuple(item for item in outcomes if item.executed and item.outcome_r is not None)
    if len(eligible) < 20:
        return PauseRuleResult("rolling_20_expectancy_below_threshold", False, "info", "Rolling 20-trade expectancy requires 20 eligible manual outcomes.", ())
    last_20 = eligible[-20:]
    expectancy = sum(float(item.outcome_r) for item in last_20 if item.outcome_r is not None) / 20
    triggered = expectancy < threshold
    return PauseRuleResult(
        "rolling_20_expectancy_below_threshold",
        triggered,
        "high" if triggered else "info",
        "Rolling 20-trade expectancy below configured threshold." if triggered else "Rolling 20-trade expectancy threshold not breached.",
        tuple(item.record_id for item in last_20) if triggered else (),
    )


def _five_losses_rule(contract: str, outcomes: Sequence[ManualOutcomeRecord]) -> PauseRuleResult:
    same_contract = tuple(item for item in outcomes if item.contract == contract and item.executed and item.outcome_r is not None)
    consecutive: list[ManualOutcomeRecord] = []
    for item in same_contract:
        if item.loss:
            consecutive.append(item)
        else:
            consecutive = []
        if len(consecutive) >= 5:
            return PauseRuleResult(
                "five_consecutive_losses_one_contract",
                True,
                "high",
                "Five consecutive losses recorded for the reviewed supported contract.",
                tuple(record.record_id for record in consecutive[-5:]),
            )
    return PauseRuleResult("five_consecutive_losses_one_contract", False, "info", "Five consecutive same-contract losses not present.", ())


def _daily_stopouts_rule(outcomes: Sequence[ManualOutcomeRecord]) -> PauseRuleResult:
    by_week: dict[str, list[str]] = {}
    for item in outcomes:
        if item.daily_stop_out and item.week_id:
            by_week.setdefault(item.week_id, []).append(item.record_id)
    for ids in by_week.values():
        if len(ids) >= 2:
            return PauseRuleResult("two_daily_stopouts_one_week", True, "high", "Two daily stop-outs recorded in one week from manual records.", tuple(ids))
    return PauseRuleResult("two_daily_stopouts_one_week", False, "info", "Two daily stop-outs in one week not present.", ())


def _pause_rule(rule_id: str, severity: str, triggered_reason: str, ids: Sequence[str]) -> PauseRuleResult:
    triggered = bool(ids)
    return PauseRuleResult(
        rule_id=rule_id,
        triggered=triggered,
        severity=severity if triggered else "info",
        reason=triggered_reason if triggered else f"{rule_id} not present.",
        supporting_record_ids=tuple(ids),
    )


def _system_quality(decisions: Sequence[SystemDecisionRecord]) -> dict[str, object]:
    return {
        "record_count": len(decisions),
        "no_trade_count": _count_decision(decisions, "NO_TRADE"),
        "approval_count": sum(1 for item in decisions if _is_approval(item.final_decision)),
        "query_submitted_count": sum(1 for item in decisions if item.query_submitted),
        "risk_gate_bypass_count": sum(1 for item in decisions if item.risk_gate_bypassed),
        "fake_ready_count": sum(1 for item in decisions if item.fake_ready_state),
        "review_statement": "System decision quality reviews preserved evidence only and does not judge trader execution outcomes.",
    }


def _trader_quality(outcomes: Sequence[ManualOutcomeRecord]) -> dict[str, object]:
    return {
        "manual_outcome_count": len(outcomes),
        "executed_count": sum(1 for item in outcomes if item.executed),
        "system_approved_recorded_count": sum(1 for item in outcomes if item.recorded_system_approved),
        "outside_query_ready_recorded_system_approved_count": sum(1 for item in outcomes if item.executed and item.recorded_system_approved and not item.query_ready_at_execution),
        "operator_notes": [item.operator_note for item in outcomes if item.operator_note],
        "review_statement": "Trader execution quality is derived only from manually supplied or fixture supplied outcome records.",
    }


def _data_sufficiency_failures(
    decisions: Sequence[SystemDecisionRecord],
    replay_summaries: Sequence[Mapping[str, object]],
    evidence_events: Sequence[Mapping[str, object]],
) -> tuple[dict[str, object], ...]:
    failures: list[dict[str, object]] = []
    for item in decisions:
        if item.failure_category == "data_sufficiency_failure" or item.stale_data_hidden_from_operator:
            failures.append({"record_id": item.record_id, "failure_category": "data_sufficiency_failure", "reason": "system_decision_evidence"})
    for item in replay_summaries:
        for reason in _sequence_text(item.get("blocking_reasons")) + _sequence_text(item.get("incomplete_reasons")):
            if "data" in reason or "stale" in reason or "missing" in reason:
                failures.append({"record_id": _safe_ref(item.get("profile_id") or "replay_summary"), "failure_category": "data_sufficiency_failure", "reason": reason})
    for item in evidence_events:
        quality = item.get("data_quality")
        if isinstance(quality, Mapping):
            reasons = _sequence_text(quality.get("blocking_reasons"))
            if reasons:
                failures.append({"record_id": _safe_ref(item.get("event_id") or "evidence_event"), "failure_category": "data_sufficiency_failure", "reason": ";".join(reasons)})
    return tuple(failures)


def _taxonomy_summary(
    decisions: Sequence[SystemDecisionRecord],
    outcomes: Sequence[ManualOutcomeRecord],
) -> tuple[FailureTaxonomyClassification, ...]:
    categories = [item.failure_category for item in decisions if item.failure_category]
    categories.extend(item.failure_category for item in outcomes if item.failure_category)
    return tuple(classify_failure_taxonomy(category) for category in _dedupe(tuple(category for category in categories if category)))


def _sample_assessment(outcomes: Sequence[ManualOutcomeRecord], minimum_sample_size: int) -> SampleSizeAssessment:
    eligible = sum(1 for item in outcomes if item.executed and item.outcome_r is not None)
    if eligible == 0:
        return SampleSizeAssessment(0, minimum_sample_size, MetricStatus.UNAVAILABLE, "Manual execution/outcome records are unavailable; no edge conclusion is allowed.")
    if eligible < minimum_sample_size:
        return SampleSizeAssessment(eligible, minimum_sample_size, MetricStatus.INSUFFICIENT_SAMPLE, "Sample is descriptive only; no edge or strategy-validity conclusion is allowed.")
    return SampleSizeAssessment(eligible, minimum_sample_size, MetricStatus.COMPUTED, "Sample threshold met for descriptive metric computation; execution remains unauthorized by review.")


def _normalize_system_decisions(items: Sequence[SystemDecisionRecord | Mapping[str, object]]) -> tuple[SystemDecisionRecord, ...]:
    records: list[SystemDecisionRecord] = []
    for item in items:
        if isinstance(item, SystemDecisionRecord):
            records.append(item)
        elif isinstance(item, Mapping):
            records.append(
                create_system_decision_record(
                    record_id=_string_field(item.get("record_id")),
                    timestamp=_string_field(item.get("timestamp")),
                    contract=_string_field(item.get("contract")),
                    profile_id=_string_field(item.get("profile_id")),
                    pipeline_run_id=_optional_string_field(item.get("pipeline_run_id")),
                    final_decision=_string_field(item.get("final_decision")),
                    trigger_query_ready=item.get("trigger_query_ready") is True,
                    query_submitted=item.get("query_submitted") is True,
                    gate_enabled=item.get("gate_enabled") is True,
                    risk_gate_bypassed=item.get("risk_gate_bypassed") is True,
                    fake_ready_state=item.get("fake_ready_state") is True,
                    unsupported_contract_ready=item.get("unsupported_contract_ready") is True,
                    stale_data_hidden_from_operator=item.get("stale_data_hidden_from_operator") is True,
                    failure_category=_optional_string_field(item.get("failure_category")),
                )
            )
    return tuple(records)


def _normalize_manual_outcomes(items: Sequence[ManualOutcomeRecord | Mapping[str, object]]) -> tuple[ManualOutcomeRecord, ...]:
    records: list[ManualOutcomeRecord] = []
    for item in items:
        if isinstance(item, ManualOutcomeRecord):
            records.append(item)
        elif isinstance(item, Mapping):
            records.append(parse_manual_outcome_record(item))
    return tuple(records)


def _review_input(value: ReviewInput | Mapping[str, object]) -> ReviewInput:
    if isinstance(value, ReviewInput):
        return value
    return ReviewInput(
        contract=_string_field(value.get("contract")),
        profile_id=_optional_string_field(value.get("profile_id")),
        replay_summaries=tuple(item for item in value.get("replay_summaries", ()) if isinstance(item, Mapping)),
        evidence_events=tuple(item for item in value.get("evidence_events", ()) if isinstance(item, Mapping)),
        system_decisions=tuple(item for item in value.get("system_decisions", ()) if isinstance(item, Mapping)),
        manual_outcomes=tuple(item for item in value.get("manual_outcomes", ()) if isinstance(item, Mapping)),
        minimum_sample_size=int(value.get("minimum_sample_size", DEFAULT_MIN_SAMPLE_SIZE)),
        no_trade_minimum_rate=float(value.get("no_trade_minimum_rate", DEFAULT_MIN_NO_TRADE_RATE)),
        expectancy_threshold_r=float(value.get("expectancy_threshold_r", DEFAULT_EXPECTANCY_THRESHOLD_R)),
    )


def _metric(metrics: Sequence[PerformanceMetric], metric_id: str) -> PerformanceMetric:
    for metric in metrics:
        if metric.metric_id == metric_id:
            return metric
    return PerformanceMetric(metric_id, MetricStatus.UNAVAILABLE, None, 0, DEFAULT_MIN_SAMPLE_SIZE, ("metric_missing",))


def _count_decision(decisions: Sequence[SystemDecisionRecord], decision: str) -> int:
    return sum(1 for item in decisions if item.final_decision == decision)


def _is_approval(decision: str) -> bool:
    return decision.upper() in APPROVAL_DECISIONS


def _is_rejection(decision: str) -> bool:
    normalized = decision.upper()
    return "REJECT" in normalized or normalized in {"DENIED", "BLOCKED"}


def _minimal_pause_criterion(
    criterion_id: str,
    *,
    triggered: bool,
    reason: str,
    observed_count: int,
) -> dict[str, object]:
    return {
        "criterion_id": criterion_id,
        "triggered": triggered,
        "reason": reason if triggered else f"{criterion_id} not triggered.",
        "observed_count": observed_count,
        "review_only": True,
        "cannot_authorize_query": True,
        "cannot_authorize_execution": True,
    }


def _minimal_review_warnings(
    *,
    system_decisions: Sequence[SystemDecisionRecord],
    manual_outcomes: Sequence[ManualOutcomeRecord],
    minimum_sample_size: int,
    missing_manual_outcome_count: int,
) -> list[str]:
    warnings: list[str] = [
        "review_metrics_are_descriptive_only",
        "review_metrics_do_not_enable_query_readiness",
        "manual_outcomes_are_operator_entered_not_verified_fills",
    ]
    if len(system_decisions) < minimum_sample_size:
        warnings.append("insufficient_system_decision_sample")
    eligible_outcomes = sum(1 for item in manual_outcomes if item.executed and item.outcome_r is not None)
    if eligible_outcomes < minimum_sample_size:
        warnings.append("insufficient_manual_outcome_sample")
    if missing_manual_outcome_count:
        warnings.append("missing_manual_outcome_data")
    return warnings


def _reason_count(
    replay_summaries: Sequence[Mapping[str, object]],
    evidence_events: Sequence[Mapping[str, object]],
    needles: Sequence[str],
) -> int:
    lowered_needles = tuple(needle.lower() for needle in needles)
    return sum(
        1
        for reason in _review_reasons(replay_summaries, evidence_events)
        if any(needle in reason.lower() for needle in lowered_needles)
    )


def _review_reasons(
    replay_summaries: Sequence[Mapping[str, object]],
    evidence_events: Sequence[Mapping[str, object]],
) -> tuple[str, ...]:
    reasons: list[str] = []
    for item in replay_summaries:
        reasons.extend(_sequence_text(item.get("blocking_reasons")))
        reasons.extend(_sequence_text(item.get("incomplete_reasons")))
    for item in evidence_events:
        quality = item.get("data_quality")
        if isinstance(quality, Mapping):
            reasons.extend(_sequence_text(quality.get("blocking_reasons")))
            reasons.extend(_sequence_text(quality.get("missing_conditions")))
    return tuple(reasons)


def _stale_hidden_ids(
    decisions: Sequence[SystemDecisionRecord],
    replay_summaries: Sequence[Mapping[str, object]],
    evidence_events: Sequence[Mapping[str, object]],
) -> tuple[str, ...]:
    ids = [item.record_id for item in decisions if item.stale_data_hidden_from_operator]
    for item in replay_summaries:
        stream_state = item.get("stream_state")
        if isinstance(stream_state, Mapping) and stream_state.get("quote_state") == "stale" and not stream_state.get("blocking_reasons"):
            ids.append(_safe_ref(item.get("profile_id") or "replay_summary"))
    for item in evidence_events:
        if item.get("event_type") == "quote_stale" and item.get("operator_visible") is False:
            ids.append(_safe_ref(item.get("event_id") or "quote_stale"))
    return _dedupe(ids)


def _manual_with_extra_errors(record: ManualOutcomeRecord, errors: tuple[str, ...]) -> ManualOutcomeRecord:
    return ManualOutcomeRecord(
        record_id=record.record_id,
        timestamp=record.timestamp,
        contract=record.contract,
        profile_id=record.profile_id,
        pipeline_run_id=record.pipeline_run_id,
        source=record.source,
        executed=record.executed,
        recorded_system_approved=record.recorded_system_approved,
        query_ready_at_execution=record.query_ready_at_execution,
        outcome_r=record.outcome_r,
        mfe_r=record.mfe_r,
        mae_r=record.mae_r,
        realized_rr=record.realized_rr,
        slippage_ticks=record.slippage_ticks,
        hold_minutes=record.hold_minutes,
        time_of_day=record.time_of_day,
        daily_stop_out=record.daily_stop_out,
        week_id=record.week_id,
        failure_category=record.failure_category,
        operator_note=record.operator_note,
        status=RecordStatus.INVALID,
        invalid_reasons=(*record.invalid_reasons, *errors),
    )


def _safe_mapping(value: Mapping[str, object]) -> dict[str, object]:
    return {str(_safe_text(key)): _safe_json(item) for key, item in value.items()}


def _safe_json(value: object) -> object:
    if isinstance(value, str):
        return _safe_text(value)
    if value is None or isinstance(value, int | float | bool):
        return value
    if isinstance(value, Mapping):
        return {str(_safe_text(key)): _safe_json(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, bytes):
        return [_safe_json(item) for item in value]
    return _safe_text(value)


def _load_mapping(payload: str | Mapping[str, object]) -> Mapping[str, object] | None:
    if isinstance(payload, Mapping):
        return payload
    try:
        loaded = json.loads(payload)
    except json.JSONDecodeError:
        return None
    return loaded if isinstance(loaded, Mapping) else None


def _sequence_text(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return ()
    return tuple(_safe_text(item) for item in value if str(item).strip())


def _numeric_or_none(value: object) -> float | int | None:
    if isinstance(value, int | float) and not isinstance(value, bool):
        return value
    return None


def _safe_float(value: float | int | None) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    return float(value)


def _parse_aware_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _is_timezone_aware_iso(value: str) -> bool:
    return _parse_aware_datetime(value) is not None


def _string_field(value: object) -> str:
    return "" if value is None else str(value)


def _optional_string_field(value: object) -> str | None:
    return None if value is None else str(value)


def _safe_optional(value: object) -> str | None:
    if value is None:
        return None
    text = _safe_text(value).strip()
    return text or None


def _safe_optional_ref(value: object) -> str | None:
    if value is None:
        return None
    text = _safe_ref(value).strip()
    return text or None


def _safe_ref(value: object) -> str:
    text = str(value).strip()
    lowered = text.lower()
    if SAFE_REF_RE.fullmatch(text) and not any(term in lowered for term in SENSITIVE_REF_TERMS):
        return text
    return _safe_text(text)


def _safe_text(value: object) -> str:
    return redact_sensitive_text(value).strip()


def _dedupe(values: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _safe_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return tuple(result)
