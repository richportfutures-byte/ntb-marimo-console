from __future__ import annotations

from ...viewmodels.models import PipelineTraceVM


def render_decision_review_panel(trace: PipelineTraceVM | None) -> dict[str, object]:
    """Render shell for Stage A/B/C/D decision review."""

    if trace is None:
        return {
            "surface": "Decision Review",
            "has_result": False,
            "message": "No pipeline result loaded.",
        }

    return {
        "surface": "Decision Review",
        "has_result": True,
        "contract": trace.contract,
        "termination_stage": trace.termination_stage,
        "final_decision": trace.final_decision,
        "stage_a_status": trace.stage_a_status,
        "stage_b_outcome": trace.stage_b_outcome,
        "stage_c_outcome": trace.stage_c_outcome,
        "stage_d_decision": trace.stage_d_decision,
    }
