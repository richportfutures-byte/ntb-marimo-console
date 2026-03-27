from __future__ import annotations

from ...viewmodels.models import ReadinessCardVM, TriggerStatusVM


def render_query_action_panel(
    *,
    trigger_rows: tuple[TriggerStatusVM, ...],
    readiness_cards: tuple[ReadinessCardVM, ...],
) -> dict[str, object]:
    """Render shell for query action gating.

    Query is enabled only when at least one trigger is true and no readiness card is blocked.
    """

    trigger_gate = any(row.is_valid and row.is_true for row in trigger_rows)
    readiness_gate = all(card.status != "blocked" for card in readiness_cards)

    return {
        "surface": "Query Action",
        "trigger_gate": trigger_gate,
        "readiness_gate": readiness_gate,
        "query_enabled": trigger_gate and readiness_gate,
        "manual_override_available": False,
    }
