from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .logging_record import RunHistoryRecord
from .pipeline import PipelineExecutionResult
from .watchman import TriggerProximity, WatchmanReadinessContext

ReadinessCardStatus = Literal["ready", "blocked", "caution"]


@dataclass(frozen=True)
class ReadinessCard:
    contract: str
    status: ReadinessCardStatus
    hard_lockouts: tuple[str, ...]
    awareness_items: tuple[str, ...]
    missing_context: tuple[str, ...]
    session_state: str
    vwap_posture: str
    value_location: str
    level_proximity: str
    trigger_state: str
    trigger_proximity_summary: str
    macro_state: str
    event_risk: str


@dataclass(frozen=True)
class StageProgressionRow:
    stage_name: str
    reached: bool
    outcome: str | None


@dataclass(frozen=True)
class PipelineResultView:
    contract: str
    final_decision: str
    termination_stage: str
    stages: tuple[StageProgressionRow, ...]


@dataclass(frozen=True)
class LogHistoryRow:
    run_id: str
    logged_at: str
    contract: str
    run_type: str
    watchman_status: str
    trigger_family: str
    vwap_posture: str
    value_location: str
    level_proximity: str
    event_risk: str
    final_decision: str
    notes: str


def _format_metric(value: float) -> str:
    return f"{value:g}"


def _readiness_card_status(context: WatchmanReadinessContext) -> ReadinessCardStatus:
    if context.hard_lockout_flags:
        return "blocked"
    if context.awareness_flags or context.missing_inputs:
        return "caution"
    return "ready"


def _trigger_proximity_summary(trigger_proximity: TriggerProximity) -> str:
    if trigger_proximity.trigger_family == "recheck_at_time":
        minutes = trigger_proximity.time_distance_minutes
        if minutes is None:
            return "recheck timing unavailable"
        if minutes < 0:
            return f"recheck overdue by {_format_metric(abs(minutes))} min"
        return f"{_format_metric(minutes)} min until recheck"

    distance_ticks = trigger_proximity.price_distance_ticks
    if distance_ticks is None:
        return "trigger distance unavailable"
    return f"{_format_metric(distance_ticks)} ticks from trigger level"


def readiness_card_from_context(context: WatchmanReadinessContext) -> ReadinessCard:
    return ReadinessCard(
        contract=context.contract,
        status=_readiness_card_status(context),
        hard_lockouts=tuple(context.hard_lockout_flags),
        awareness_items=tuple(context.awareness_flags),
        missing_context=tuple(context.missing_inputs),
        session_state=context.session_state,
        vwap_posture=context.vwap_posture_state,
        value_location=context.value_location_state,
        level_proximity=context.level_proximity_state,
        trigger_state=context.trigger_context_state,
        trigger_proximity_summary=_trigger_proximity_summary(context.trigger_proximity),
        macro_state=context.contract_specific_macro_state,
        event_risk=context.event_risk_state,
    )


def readiness_cards_from_sweep(
    sweep_result: dict[str, WatchmanReadinessContext],
) -> list[ReadinessCard]:
    return [
        readiness_card_from_context(sweep_result[contract])
        for contract in sorted(sweep_result)
    ]


def pipeline_result_view(result: PipelineExecutionResult) -> PipelineResultView:
    stage_rows = (
        StageProgressionRow(
            stage_name="sufficiency_gate",
            reached=getattr(result, "sufficiency_gate_output", None) is not None,
            outcome=getattr(getattr(result, "sufficiency_gate_output", None), "status", None),
        ),
        StageProgressionRow(
            stage_name="contract_market_read",
            reached=getattr(result, "contract_analysis", None) is not None,
            outcome=getattr(getattr(result, "contract_analysis", None), "outcome", None),
        ),
        StageProgressionRow(
            stage_name="setup_construction",
            reached=getattr(result, "proposed_setup", None) is not None,
            outcome=getattr(getattr(result, "proposed_setup", None), "outcome", None),
        ),
        StageProgressionRow(
            stage_name="risk_authorization",
            reached=getattr(result, "risk_authorization", None) is not None,
            outcome=getattr(getattr(result, "risk_authorization", None), "decision", None),
        ),
    )
    return PipelineResultView(
        contract=result.contract,
        final_decision=result.final_decision,
        termination_stage=result.termination_stage,
        stages=stage_rows,
    )


WATCHMAN_DIFF_STATE_FIELDS: tuple[str, ...] = (
    "session_state",
    "allowed_hours_state",
    "event_risk_state",
    "session_wind_down_state",
    "staleness_state",
    "visual_readiness_state",
    "value_location_state",
    "vwap_posture_state",
    "level_proximity_state",
    "opening_state",
    "range_expansion_state",
    "volume_participation_state",
    "delta_agreement_state",
    "trigger_context_state",
    "contract_specific_macro_state",
)

WATCHMAN_DIFF_LIST_FIELDS: tuple[str, ...] = (
    "hard_lockout_flags",
    "awareness_flags",
    "missing_inputs",
)


@dataclass(frozen=True)
class WatchmanFieldChange:
    field: str
    previous: str
    current: str


@dataclass(frozen=True)
class WatchmanDiff:
    contract: str
    changes: tuple[WatchmanFieldChange, ...]

    @property
    def has_changes(self) -> bool:
        return len(self.changes) > 0


def diff_watchman_contexts(
    previous: WatchmanReadinessContext,
    current: WatchmanReadinessContext,
) -> WatchmanDiff:
    if previous.contract != current.contract:
        raise ValueError(
            f"Cannot diff contexts for different contracts: "
            f"{previous.contract} vs {current.contract}."
        )

    changes: list[WatchmanFieldChange] = []

    for field in WATCHMAN_DIFF_STATE_FIELDS:
        prev_val = getattr(previous, field)
        curr_val = getattr(current, field)
        if prev_val != curr_val:
            changes.append(WatchmanFieldChange(
                field=field,
                previous=str(prev_val),
                current=str(curr_val),
            ))

    for field in WATCHMAN_DIFF_LIST_FIELDS:
        prev_val = sorted(getattr(previous, field))
        curr_val = sorted(getattr(current, field))
        if prev_val != curr_val:
            changes.append(WatchmanFieldChange(
                field=field,
                previous=", ".join(prev_val) if prev_val else "—",
                current=", ".join(curr_val) if curr_val else "—",
            ))

    return WatchmanDiff(contract=current.contract, changes=tuple(changes))


def log_history_rows_from_records(
    records: list[RunHistoryRecord],
    *,
    contract_filter: str | None = None,
) -> list[LogHistoryRow]:
    filtered_records = (
        [record for record in records if record.contract == contract_filter]
        if contract_filter is not None
        else records
    )
    return [
        LogHistoryRow(
            run_id=record.run_id,
            logged_at=record.logged_at.isoformat(),
            contract=record.contract,
            run_type=record.run_type,
            watchman_status=record.watchman_status,
            trigger_family=record.trigger_family,
            vwap_posture=record.vwap_posture,
            value_location=record.value_location,
            level_proximity=record.level_proximity,
            event_risk=record.event_risk,
            final_decision=record.final_decision or "—",
            notes=record.notes or "—",
        )
        for record in filtered_records
    ]


__all__ = [
    "LogHistoryRow",
    "PipelineResultView",
    "ReadinessCard",
    "ReadinessCardStatus",
    "StageProgressionRow",
    "WatchmanDiff",
    "WatchmanFieldChange",
    "diff_watchman_contexts",
    "log_history_rows_from_records",
    "pipeline_result_view",
    "readiness_card_from_context",
    "readiness_cards_from_sweep",
]
