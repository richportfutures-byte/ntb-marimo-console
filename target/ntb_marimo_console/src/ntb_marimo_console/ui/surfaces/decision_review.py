from __future__ import annotations

from ...viewmodels.models import (
    EngineReasoningVM,
    KeyLevelsVM,
    NARRATIVE_UNAVAILABLE_LABEL,
    PipelineTraceVM,
    RiskAuthorizationVM,
    TradeThesisVM,
)


NARRATIVE_UNAVAILABLE_DETAIL = (
    "The preserved engine did not surface narrative for this run. "
    "Stage B / Stage C / Stage D fields will appear here when the engine "
    "produces a populated pipeline result."
)
DISQUALIFIERS_UNAVAILABLE_DETAIL = (
    "Disqualifiers list is unavailable for this run. The engine did not "
    "emit Stage C disqualifier tokens."
)


def render_decision_review_panel(trace: PipelineTraceVM | None) -> dict[str, object]:
    """Render shell for Stage A/B/C/D decision review.

    The panel preserves the historical envelope keys (contract,
    termination_stage, final_decision, stage_a..d statuses) and adds four
    optional narrative sections that surface preserved-engine output verbatim.
    Missing narrative is rendered as an explicit 'unavailable' marker, never
    as success.
    """

    if trace is None:
        return {
            "surface": "Decision Review",
            "has_result": False,
            "message": "No pipeline result loaded.",
            "narrative_available": False,
        }

    panel: dict[str, object] = {
        "surface": "Decision Review",
        "has_result": True,
        "contract": trace.contract,
        "termination_stage": trace.termination_stage,
        "final_decision": trace.final_decision,
        "stage_a_status": trace.stage_a_status,
        "stage_b_outcome": trace.stage_b_outcome,
        "stage_c_outcome": trace.stage_c_outcome,
        "stage_d_decision": trace.stage_d_decision,
        "narrative_available": trace.narrative_available,
    }

    panel["engine_reasoning"] = _engine_reasoning_section(trace.engine_reasoning, trace.key_levels)
    panel["trade_thesis"] = _trade_thesis_section(trace.trade_thesis, trace.final_decision)
    panel["risk_authorization_detail"] = _risk_authorization_section(trace.risk_authorization)
    panel["invalidation"] = _invalidation_section(trace.trade_thesis)
    panel["narrative_unavailable_message"] = (
        None if trace.narrative_available else NARRATIVE_UNAVAILABLE_DETAIL
    )

    return panel


def _engine_reasoning_section(
    reasoning: EngineReasoningVM | None,
    key_levels: KeyLevelsVM | None,
) -> dict[str, object]:
    if reasoning is None:
        return {
            "available": False,
            "unavailable_message": NARRATIVE_UNAVAILABLE_LABEL,
        }

    section: dict[str, object] = {
        "available": True,
        "market_regime": reasoning.market_regime,
        "directional_bias": reasoning.directional_bias,
        "evidence_score": reasoning.evidence_score,
        "confidence_band": reasoning.confidence_band,
        "structural_notes": reasoning.structural_notes,
        "outcome": reasoning.outcome,
        "conflicting_signals": list(reasoning.conflicting_signals),
        "assumptions": list(reasoning.assumptions),
    }
    if key_levels is not None:
        section["key_levels"] = {
            "pivot_level": key_levels.pivot_level,
            "support_levels": list(key_levels.support_levels),
            "resistance_levels": list(key_levels.resistance_levels),
        }
    else:
        section["key_levels"] = None
    return section


def _trade_thesis_section(
    thesis: TradeThesisVM | None,
    final_decision: str,
) -> dict[str, object]:
    if thesis is None:
        return {
            "available": False,
            "unavailable_message": NARRATIVE_UNAVAILABLE_LABEL,
        }

    section: dict[str, object] = {
        "available": True,
        "outcome": thesis.outcome,
        "no_trade_reason": thesis.no_trade_reason,
        "direction": thesis.direction,
        "setup_class": thesis.setup_class,
        "entry_price": thesis.entry_price,
        "stop_price": thesis.stop_price,
        "target_1": thesis.target_1,
        "target_2": thesis.target_2,
        "position_size": thesis.position_size,
        "risk_dollars": thesis.risk_dollars,
        "reward_risk_ratio": thesis.reward_risk_ratio,
        "hold_time_estimate_minutes": thesis.hold_time_estimate_minutes,
        "rationale": thesis.rationale,
    }

    is_no_trade_outcome = (
        (thesis.outcome is not None and thesis.outcome.upper() == "NO_TRADE")
        or final_decision == "NO_TRADE"
    )
    section["is_no_trade"] = is_no_trade_outcome

    if thesis.sizing_math is not None:
        section["sizing_math"] = {
            "stop_distance_ticks": thesis.sizing_math.stop_distance_ticks,
            "risk_per_tick": thesis.sizing_math.risk_per_tick,
            "raw_risk_dollars": thesis.sizing_math.raw_risk_dollars,
            "slippage_cost_dollars": thesis.sizing_math.slippage_cost_dollars,
            "adjusted_risk_dollars": thesis.sizing_math.adjusted_risk_dollars,
            "blended_target_distance_ticks": thesis.sizing_math.blended_target_distance_ticks,
            "blended_reward_dollars": thesis.sizing_math.blended_reward_dollars,
        }
    else:
        section["sizing_math"] = None

    return section


def _risk_authorization_section(
    risk: RiskAuthorizationVM | None,
) -> dict[str, object]:
    if risk is None:
        return {
            "available": False,
            "unavailable_message": NARRATIVE_UNAVAILABLE_LABEL,
        }

    return {
        "available": True,
        "decision": risk.decision,
        "checks": [
            {
                "check_id": check.check_id,
                "check_name": check.check_name,
                "passed": check.passed,
                "passed_text": "PASS" if check.passed else "FAIL",
                "detail": check.detail,
            }
            for check in risk.checks
        ],
        "rejection_reasons": list(risk.rejection_reasons),
        "adjusted_position_size": risk.adjusted_position_size,
        "adjusted_risk_dollars": risk.adjusted_risk_dollars,
        "remaining_daily_risk_budget": risk.remaining_daily_risk_budget,
        "remaining_aggregate_risk_budget": risk.remaining_aggregate_risk_budget,
    }


def _invalidation_section(thesis: TradeThesisVM | None) -> dict[str, object]:
    if thesis is None or not thesis.disqualifiers:
        return {
            "available": False,
            "unavailable_message": DISQUALIFIERS_UNAVAILABLE_DETAIL,
            "disqualifiers": [],
        }
    return {
        "available": True,
        "unavailable_message": None,
        "disqualifiers": list(thesis.disqualifiers),
    }
