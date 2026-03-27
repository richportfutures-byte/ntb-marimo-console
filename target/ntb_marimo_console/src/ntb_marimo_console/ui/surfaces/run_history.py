from __future__ import annotations

from ...viewmodels.models import RunHistoryRowVM


def render_run_history_panel(rows: tuple[RunHistoryRowVM, ...]) -> dict[str, object]:
    """Render shell for fixture-backed run history rows."""

    return {
        "surface": "Run History",
        "source": "fixture_backed",
        "rows": [
            {
                "run_id": row.run_id,
                "logged_at": row.logged_at,
                "contract": row.contract,
                "run_type": row.run_type,
                "final_decision": row.final_decision,
                "notes": row.notes,
            }
            for row in rows
        ],
    }
