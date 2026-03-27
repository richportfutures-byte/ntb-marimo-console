from __future__ import annotations

from ...viewmodels.models import PipelineTraceVM


def render_audit_replay_panel(trace: PipelineTraceVM | None) -> dict[str, object]:
    """Render shell for audit/replay in Phase 1.

    Stage E semantics remain engine-owned and are not live-backed here.
    """

    return {
        "surface": "Audit/Replay",
        "mode": "fixture_or_stub",
        "stage_e_live_backend": False,
        "trace_summary": (
            None
            if trace is None
            else {
                "contract": trace.contract,
                "termination_stage": trace.termination_stage,
                "final_decision": trace.final_decision,
            }
        ),
    }
