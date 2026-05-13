from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from ..viewmodels.models import (
    LiveObservableVM,
    PipelineTraceVM,
    PreMarketBriefVM,
    ReadinessCardVM,
    RunHistoryRowVM,
    SessionHeaderVM,
    TimelineEventVM,
    TriggerStatusVM,
)
from .surfaces.audit_replay import render_audit_replay_panel
from .surfaces.decision_review import render_decision_review_panel
from .surfaces.live_observables import render_live_observables_panel
from .surfaces.premarket_brief import render_premarket_brief_panel
from .surfaces.query_action import render_query_action_panel
from .surfaces.readiness_matrix import render_readiness_matrix_panel
from .surfaces.run_history import render_run_history_panel
from .surfaces.session_header import render_session_header_panel
from .surfaces.trigger_table import render_trigger_table_panel


@dataclass(frozen=True)
class AppShellPayload:
    """Structured payload consumed by the app-shell renderer."""

    session_header: SessionHeaderVM
    premarket_brief: PreMarketBriefVM
    live_observable: LiveObservableVM
    readiness_cards: tuple[ReadinessCardVM, ...]
    trigger_rows: tuple[TriggerStatusVM, ...]
    pipeline_trace: PipelineTraceVM | None
    run_history_rows: tuple[RunHistoryRowVM, ...]
    timeline_events: tuple[TimelineEventVM, ...] = ()
    premarket_enrichment: Mapping[str, object] | None = None


def build_app_shell(payload: AppShellPayload) -> dict[str, object]:
    """Compose Phase 1 surface shells into one app payload.

    The shell is intentionally declarative and does not perform market inference.
    """

    return {
        "title": "NTB Marimo Console (Phase 1 Scaffold)",
        "surfaces": {
            "session_header": render_session_header_panel(payload.session_header),
            "pre_market_brief": render_premarket_brief_panel(
                payload.premarket_brief,
                payload.premarket_enrichment,
            ),
            "readiness_matrix": render_readiness_matrix_panel(payload.readiness_cards),
            "trigger_table": render_trigger_table_panel(payload.trigger_rows),
            "live_observables": render_live_observables_panel(payload.live_observable),
            "query_action": render_query_action_panel(
                trigger_rows=payload.trigger_rows,
                readiness_cards=payload.readiness_cards,
            ),
            "decision_review": render_decision_review_panel(payload.pipeline_trace),
            "audit_replay": render_audit_replay_panel(payload.pipeline_trace, payload.timeline_events),
            "run_history": render_run_history_panel(payload.run_history_rows),
        },
    }
