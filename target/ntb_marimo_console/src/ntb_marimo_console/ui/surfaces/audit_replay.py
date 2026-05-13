from __future__ import annotations

from ...viewmodels.models import PipelineTraceVM, TimelineEventVM


def render_audit_replay_panel(
    trace: PipelineTraceVM | None,
    timeline_events: tuple[TimelineEventVM, ...] = (),
) -> dict[str, object]:
    """Render shell for audit/replay in Phase 1.

    Stage E semantics remain engine-owned and are not live-backed here.
    """

    event_type_filters = sorted({event.event_type for event in timeline_events})
    contract_filters = sorted({event.contract for event in timeline_events if event.contract is not None})
    return {
        "surface": "Audit/Replay",
        "mode": "fixture_or_stub",
        "stage_e_live_backend": False,
        "timeline_status": "ready" if timeline_events else "empty",
        "timeline_events": [event.to_dict() for event in timeline_events],
        "timeline_filters": {
            "event_types": event_type_filters,
            "contracts": contract_filters,
        },
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
