from __future__ import annotations

from ...viewmodels.models import PreMarketBriefVM


def render_premarket_brief_panel(brief: PreMarketBriefVM) -> dict[str, object]:
    """Render shell for schema-anchored pre-market brief display."""

    return {
        "surface": "Pre-Market Brief",
        "contract": brief.contract,
        "session_date": brief.session_date,
        "status": brief.status,
        "setup_summaries": list(brief.setup_summaries),
        "warnings": list(brief.warnings),
    }
