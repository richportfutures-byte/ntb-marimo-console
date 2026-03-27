from __future__ import annotations

from ...viewmodels.models import ReadinessCardVM


def render_readiness_matrix_panel(cards: tuple[ReadinessCardVM, ...]) -> dict[str, object]:
    """Render shell for readiness matrix review."""

    rows = [
        {
            "contract": card.contract,
            "status": card.status,
            "event_risk": card.event_risk,
            "hard_lockouts": list(card.hard_lockouts),
            "awareness_items": list(card.awareness_items),
            "missing_context": list(card.missing_context),
        }
        for card in cards
    ]
    return {
        "surface": "Readiness Matrix",
        "rows": rows,
    }
