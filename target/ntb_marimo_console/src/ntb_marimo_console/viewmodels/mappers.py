from __future__ import annotations

from collections.abc import Mapping

from ..adapters.contracts import (
    PipelineNarrative,
    PipelineSummary,
    RunHistoryRowRecord,
    TriggerEvaluation,
    WatchmanContextLike,
)
from ..market_data.futures_quote_service import FuturesQuoteService, FuturesQuoteServiceResult
from .models import (
    EngineReasoningVM,
    KeyLevelsVM,
    LiveObservableVM,
    LiveObservableMarketDataVM,
    PipelineTraceVM,
    PreMarketBriefVM,
    ReadinessCardVM,
    RiskAuthorizationVM,
    RiskCheckVM,
    RunHistoryRowVM,
    SessionHeaderVM,
    SizingMathVM,
    TradeThesisVM,
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
    if result.provider_name not in {"fixture", "schwab"} or result.status not in {"connected", "stale"} or quote is None:
        return unavailable_live_observable_market_data_vm()

    status_prefix = "Schwab quote" if result.provider_name == "schwab" else "Fixture quote"
    return LiveObservableMarketDataVM(
        bid=_quote_value_text(quote.bid_price),
        ask=_quote_value_text(quote.ask_price),
        last=_quote_value_text(quote.last_price),
        quote_time=quote.received_at.strip() or "unknown",
        status=f"{status_prefix} (stale)" if result.status == "stale" else status_prefix,
    )


def _quote_value_text(value: object) -> str:
    return "N/A" if value is None else str(value)


def pipeline_trace_vm_from_summary(
    summary: PipelineSummary,
    narrative: PipelineNarrative | None = None,
) -> PipelineTraceVM:
    """Build a PipelineTraceVM from the existing summary plus optional narrative.

    The summary supplies the seven-field envelope (contract / termination /
    final_decision / four stage statuses) the console has always carried.

    The narrative, if provided, supplies engine output verbatim — Stage B
    contract_analysis fields, Stage C proposed_setup fields, Stage D
    risk_authorization checks. Each section is extracted by plain field
    access; the mapper does not parse, derive, rank, or re-interpret any
    narrative content.

    When narrative is None or all sections are empty, narrative_available is
    False and the renderer is expected to surface "unavailable in this run".
    """

    engine_reasoning, key_levels = _engine_reasoning_and_key_levels_vm(
        narrative.get("contract_analysis") if narrative else None
    )
    trade_thesis = _trade_thesis_vm(
        narrative.get("proposed_setup") if narrative else None
    )
    risk_authorization = _risk_authorization_vm(
        narrative.get("risk_authorization") if narrative else None
    )
    narrative_available = any(
        section is not None
        for section in (engine_reasoning, key_levels, trade_thesis, risk_authorization)
    )

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
        engine_reasoning=engine_reasoning,
        key_levels=key_levels,
        trade_thesis=trade_thesis,
        risk_authorization=risk_authorization,
        narrative_available=narrative_available,
    )


def _engine_reasoning_and_key_levels_vm(
    contract_analysis: Mapping[str, object] | None,
) -> tuple[EngineReasoningVM | None, KeyLevelsVM | None]:
    if not isinstance(contract_analysis, Mapping):
        return None, None

    engine_reasoning = EngineReasoningVM(
        market_regime=_optional_str(contract_analysis.get("market_regime")),
        directional_bias=_optional_str(contract_analysis.get("directional_bias")),
        evidence_score=_optional_int(contract_analysis.get("evidence_score")),
        confidence_band=_optional_str(contract_analysis.get("confidence_band")),
        structural_notes=_optional_str(contract_analysis.get("structural_notes")),
        conflicting_signals=_string_tuple(contract_analysis.get("conflicting_signals")),
        assumptions=_string_tuple(contract_analysis.get("assumptions")),
        outcome=_optional_str(contract_analysis.get("outcome")),
    )

    key_levels_payload = contract_analysis.get("key_levels")
    if isinstance(key_levels_payload, Mapping):
        key_levels = KeyLevelsVM(
            pivot_level=_optional_float(key_levels_payload.get("pivot_level")),
            support_levels=_float_tuple(key_levels_payload.get("support_levels")),
            resistance_levels=_float_tuple(key_levels_payload.get("resistance_levels")),
        )
    else:
        key_levels = None

    return engine_reasoning, key_levels


def _trade_thesis_vm(
    proposed_setup: Mapping[str, object] | None,
) -> TradeThesisVM | None:
    if not isinstance(proposed_setup, Mapping):
        return None

    sizing_math_payload = proposed_setup.get("sizing_math")
    if isinstance(sizing_math_payload, Mapping):
        sizing_math = SizingMathVM(
            stop_distance_ticks=_optional_float(sizing_math_payload.get("stop_distance_ticks")),
            risk_per_tick=_optional_float(sizing_math_payload.get("risk_per_tick")),
            raw_risk_dollars=_optional_float(sizing_math_payload.get("raw_risk_dollars")),
            slippage_cost_dollars=_optional_float(sizing_math_payload.get("slippage_cost_dollars")),
            adjusted_risk_dollars=_optional_float(sizing_math_payload.get("adjusted_risk_dollars")),
            blended_target_distance_ticks=_optional_float(
                sizing_math_payload.get("blended_target_distance_ticks")
            ),
            blended_reward_dollars=_optional_float(sizing_math_payload.get("blended_reward_dollars")),
        )
    else:
        sizing_math = None

    return TradeThesisVM(
        outcome=_optional_str(proposed_setup.get("outcome")),
        no_trade_reason=_optional_str(proposed_setup.get("no_trade_reason")),
        direction=_optional_str(proposed_setup.get("direction")),
        setup_class=_optional_str(proposed_setup.get("setup_class")),
        entry_price=_optional_float(proposed_setup.get("entry_price")),
        stop_price=_optional_float(proposed_setup.get("stop_price")),
        target_1=_optional_float(proposed_setup.get("target_1")),
        target_2=_optional_float(proposed_setup.get("target_2")),
        position_size=_optional_int(proposed_setup.get("position_size")),
        risk_dollars=_optional_float(proposed_setup.get("risk_dollars")),
        reward_risk_ratio=_optional_float(proposed_setup.get("reward_risk_ratio")),
        hold_time_estimate_minutes=_optional_int(proposed_setup.get("hold_time_estimate_minutes")),
        rationale=_optional_str(proposed_setup.get("rationale")),
        disqualifiers=_string_tuple(proposed_setup.get("disqualifiers")),
        sizing_math=sizing_math,
    )


def _risk_authorization_vm(
    risk_authorization: Mapping[str, object] | None,
) -> RiskAuthorizationVM | None:
    if not isinstance(risk_authorization, Mapping):
        return None

    raw_checks = risk_authorization.get("checks")
    checks: list[RiskCheckVM] = []
    if isinstance(raw_checks, list):
        for entry in raw_checks:
            if not isinstance(entry, Mapping):
                continue
            try:
                check_id = int(entry["check_id"]) if entry.get("check_id") is not None else None
            except (TypeError, ValueError):
                check_id = None
            check_name = _optional_str(entry.get("check_name"))
            passed_value = entry.get("passed")
            detail = _optional_str(entry.get("detail"))
            if (
                check_id is None
                or check_name is None
                or not isinstance(passed_value, bool)
                or detail is None
            ):
                continue
            checks.append(
                RiskCheckVM(
                    check_id=check_id,
                    check_name=check_name,
                    passed=passed_value,
                    detail=detail,
                )
            )

    return RiskAuthorizationVM(
        decision=_optional_str(risk_authorization.get("decision")),
        checks=tuple(checks),
        rejection_reasons=_string_tuple(risk_authorization.get("rejection_reasons")),
        adjusted_position_size=_optional_int(risk_authorization.get("adjusted_position_size")),
        adjusted_risk_dollars=_optional_float(risk_authorization.get("adjusted_risk_dollars")),
        remaining_daily_risk_budget=_optional_float(
            risk_authorization.get("remaining_daily_risk_budget")
        ),
        remaining_aggregate_risk_budget=_optional_float(
            risk_authorization.get("remaining_aggregate_risk_budget")
        ),
    )


def _optional_str(value: object) -> str | None:
    return str(value) if isinstance(value, str) and value != "" else None


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item for item in value if isinstance(item, str) and item != "")


def _float_tuple(value: object) -> tuple[float, ...]:
    if not isinstance(value, list):
        return ()
    floats: list[float] = []
    for item in value:
        if isinstance(item, bool):
            continue
        if isinstance(item, (int, float)):
            floats.append(float(item))
    return tuple(floats)


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
