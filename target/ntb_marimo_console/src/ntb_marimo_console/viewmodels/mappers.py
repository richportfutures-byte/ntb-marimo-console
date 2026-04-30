from __future__ import annotations

from collections.abc import Mapping

from ..adapters.contracts import PipelineSummary, RunHistoryRowRecord, TriggerEvaluation, WatchmanContextLike
from ..market_data.futures_quote_service import FuturesQuoteService, FuturesQuoteServiceResult
from .models import (
    LiveObservableVM,
    LiveObservableMarketDataVM,
    PipelineTraceVM,
    PreMarketBriefVM,
    ReadinessCardVM,
    RunHistoryRowVM,
    SessionHeaderVM,
    TriggerStatusVM,
    unavailable_live_observable_market_data_vm,
)


def session_header_vm(contract: str, session_date: str) -> SessionHeaderVM:
    return SessionHeaderVM(contract=contract, session_date=session_date)


def premarket_brief_vm_from_brief(
    brief: Mapping[str, object],
    *,
    status_override: str | None = None,
) -> PreMarketBriefVM:
    setups = brief.get("structural_setups", [])
    setup_summaries: list[str] = []
    warnings: list[str] = []
    for setup in setups if isinstance(setups, list) else []:
        if not isinstance(setup, Mapping):
            continue
        summary = setup.get("summary")
        if isinstance(summary, str):
            setup_summaries.append(summary)
        setup_warnings = setup.get("warnings")
        if isinstance(setup_warnings, list):
            for warning in setup_warnings:
                if isinstance(warning, str):
                    warnings.append(warning)

    return PreMarketBriefVM(
        contract=str(brief.get("contract", "UNKNOWN")),
        session_date=str(brief.get("session_date", "")),
        status=status_override or str(brief.get("status", "UNKNOWN")),
        setup_summaries=tuple(setup_summaries),
        warnings=tuple(warnings),
    )


def readiness_card_vm_from_context(context: WatchmanContextLike) -> ReadinessCardVM:
    return ReadinessCardVM(
        contract=str(getattr(context, "contract", "UNKNOWN")),
        status="blocked" if getattr(context, "hard_lockout_flags", []) else "ready",
        event_risk=str(getattr(context, "event_risk_state", "unknown")),
        vwap_posture=str(getattr(context, "vwap_posture_state", "unknown")),
        value_location=str(getattr(context, "value_location_state", "unknown")),
        level_proximity=str(getattr(context, "level_proximity_state", "unknown")),
        hard_lockouts=tuple(getattr(context, "hard_lockout_flags", [])),
        awareness_items=tuple(getattr(context, "awareness_flags", [])),
        missing_context=tuple(getattr(context, "missing_inputs", [])),
    )


def trigger_status_vm_from_eval(evaluation: TriggerEvaluation) -> TriggerStatusVM:
    return TriggerStatusVM(
        trigger_id=evaluation.trigger_id,
        is_valid=evaluation.is_valid,
        is_true=evaluation.is_true,
        missing_fields=evaluation.missing_fields,
        invalid_reasons=evaluation.invalid_reasons,
    )


def live_observable_vm_from_snapshot(
    snapshot: Mapping[str, object],
    *,
    market_data_service: FuturesQuoteService | None = None,
    market_data_symbol: str | None = None,
) -> LiveObservableVM:
    contract = str(snapshot.get("contract", "UNKNOWN"))
    timestamp_et = str(snapshot.get("timestamp_et", ""))
    return LiveObservableVM(
        contract=contract,
        timestamp_et=timestamp_et,
        snapshot=dict(snapshot),
        market_data=_market_data_display_vm(
            market_data_service=market_data_service,
            market_data_symbol=market_data_symbol or contract,
        ),
    )


def _market_data_display_vm(
    *,
    market_data_service: FuturesQuoteService | None,
    market_data_symbol: str,
) -> LiveObservableMarketDataVM:
    symbol = market_data_symbol.strip()
    if market_data_service is None or not symbol:
        return unavailable_live_observable_market_data_vm()

    try:
        result = market_data_service.get_quote(symbol)
    except Exception:
        return unavailable_live_observable_market_data_vm()
    return _market_data_display_vm_from_result(result)


def _market_data_display_vm_from_result(result: FuturesQuoteServiceResult) -> LiveObservableMarketDataVM:
    quote = result.quote
    if result.provider_name != "fixture" or result.status not in {"connected", "stale"} or quote is None:
        return unavailable_live_observable_market_data_vm()

    return LiveObservableMarketDataVM(
        bid=_quote_value_text(quote.bid_price),
        ask=_quote_value_text(quote.ask_price),
        last=_quote_value_text(quote.last_price),
        quote_time=quote.received_at.strip() or "unknown",
        status="Fixture quote (stale)" if result.status == "stale" else "Fixture quote",
    )


def _quote_value_text(value: object) -> str:
    return "N/A" if value is None else str(value)


def pipeline_trace_vm_from_summary(summary: PipelineSummary) -> PipelineTraceVM:
    return PipelineTraceVM(
        contract=str(summary.get("contract", "UNKNOWN")),
        termination_stage=str(summary.get("termination_stage", "UNKNOWN")),
        final_decision=str(summary.get("final_decision", "UNKNOWN")),
        stage_a_status=(
            str(summary["sufficiency_gate_status"])
            if summary.get("sufficiency_gate_status") is not None
            else None
        ),
        stage_b_outcome=(
            str(summary["contract_analysis_outcome"])
            if summary.get("contract_analysis_outcome") is not None
            else None
        ),
        stage_c_outcome=(
            str(summary["proposed_setup_outcome"])
            if summary.get("proposed_setup_outcome") is not None
            else None
        ),
        stage_d_decision=(
            str(summary["risk_authorization_decision"])
            if summary.get("risk_authorization_decision") is not None
            else None
        ),
    )


def run_history_row_vm_from_row(row: RunHistoryRowRecord) -> RunHistoryRowVM:
    return RunHistoryRowVM(
        run_id=str(row.get("run_id", "")),
        logged_at=str(row.get("logged_at", "")),
        contract=str(row.get("contract", "UNKNOWN")),
        run_type=str(row.get("run_type", "")),
        notes=str(row.get("notes", "")),
        session_date=(
            str(row["session_date"])
            if row.get("session_date") is not None
            else None
        ),
        final_decision=(
            str(row["final_decision"])
            if row.get("final_decision") is not None
            else None
        ),
        termination_stage=(
            str(row["termination_stage"])
            if row.get("termination_stage") is not None
            else None
        ),
        stage_d_decision=(
            str(row["stage_d_decision"])
            if row.get("stage_d_decision") is not None
            else None
        ),
    )
