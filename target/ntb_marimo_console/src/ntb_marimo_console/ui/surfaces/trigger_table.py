from __future__ import annotations

from ...viewmodels.models import TriggerStatusVM


def render_trigger_table_panel(trigger_rows: tuple[TriggerStatusVM, ...]) -> dict[str, object]:
    """Render shell for deterministic trigger predicate status rows."""

    return {
        "surface": "Trigger Table",
        "rows": [
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
