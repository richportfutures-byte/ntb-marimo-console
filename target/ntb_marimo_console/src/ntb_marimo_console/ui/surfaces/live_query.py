from __future__ import annotations

from ...viewmodels.models import TriggerStatusVM


def render_live_query_panel(trigger_rows: tuple[TriggerStatusVM, ...]) -> dict[str, object]:
    """Render shell for live query gating status.

    Manual override is excluded by freeze.
    """

    query_enabled = any(row.is_valid and row.is_true for row in trigger_rows)
    return {
        "surface": "Live Query",
        "query_enabled": query_enabled,
        "manual_override_available": False,
        "triggers": [
            {
                "trigger_id": row.trigger_id,
                "is_valid": row.is_valid,
                "is_true": row.is_true,
                "missing_fields": list(row.missing_fields),
                "invalid_reasons": list(row.invalid_reasons),
            }
            for row in trigger_rows
        ],
    }
