from __future__ import annotations

from collections.abc import Mapping

from ...viewmodels.models import PreMarketBriefVM


def render_premarket_brief_panel(
    brief: PreMarketBriefVM,
    enrichment: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Render shell for schema-anchored pre-market brief display."""

    panel = {
        "surface": "Pre-Market Brief",
        "contract": brief.contract,
        "session_date": brief.session_date,
        "status": brief.status,
        "setup_summaries": list(brief.setup_summaries),
        "warnings": list(brief.warnings),
    }
    if enrichment is not None:
        panel["enrichment"] = dict(enrichment)
    return panel
