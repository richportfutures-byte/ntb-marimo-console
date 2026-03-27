from __future__ import annotations

from ...viewmodels.models import SessionHeaderVM


def render_session_header_panel(header: SessionHeaderVM) -> dict[str, object]:
    """Render shell for session/contract picker context."""

    return {
        "surface": "Session Header",
        "contract": header.contract,
        "session_date": header.session_date,
    }
