from __future__ import annotations

from ...viewmodels.models import LiveObservableVM


def render_live_observables_panel(observables: LiveObservableVM) -> dict[str, object]:
    """Render shell for live observable fields used by trigger predicates."""

    return {
        "surface": "Live Observables",
        "contract": observables.contract,
        "timestamp_et": observables.timestamp_et,
        "snapshot": observables.snapshot,
        "market_data": {
            "bid": observables.market_data.bid,
            "ask": observables.market_data.ask,
            "last": observables.market_data.last,
            "quote_time": observables.market_data.quote_time,
            "status": observables.market_data.status,
            "disclaimer": observables.market_data.disclaimer,
        },
    }
