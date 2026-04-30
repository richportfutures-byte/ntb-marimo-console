from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from ntb_marimo_console.market_data.futures_quote_service import (
    FixtureFuturesQuoteProvider,
    FuturesQuote,
    FuturesQuoteService,
    NullFuturesQuoteProvider,
)
from ntb_marimo_console.ui.surfaces.live_observables import render_live_observables_panel
from ntb_marimo_console.viewmodels.mappers import live_observable_vm_from_snapshot


NOW = datetime(2026, 4, 30, 12, 0, 0, tzinfo=timezone.utc)


def _quote(
    *,
    bid: float | int | None = 7175,
    ask: float | int | None = 7175.5,
    last: float | int | None = 7175.25,
    received_at: str = "2026-04-30T11:59:58+00:00",
) -> FuturesQuote:
    return FuturesQuote(
        symbol="ES",
        bid_price=bid,
        ask_price=ask,
        last_price=last,
        bid_size=19,
        ask_size=14,
        received_at=received_at,
    )


def _panel(service: FuturesQuoteService | None) -> dict[str, object]:
    vm = live_observable_vm_from_snapshot(
        {
            "contract": "ES",
            "timestamp_et": "2026-03-25T09:35:00-04:00",
            "market": {"current_price": 5600.0},
        },
        market_data_service=service,
        market_data_symbol="ES",
    )
    return render_live_observables_panel(vm)


def test_disabled_service_renders_market_data_unavailable_safely() -> None:
    panel = _panel(FuturesQuoteService(NullFuturesQuoteProvider(), clock=lambda: NOW))

    assert panel["market_data"] == {
        "bid": "N/A",
        "ask": "N/A",
        "last": "N/A",
        "quote_time": "unknown",
        "status": "Market data unavailable",
        "disclaimer": (
            "Informational only. Quote values do not affect readiness, trigger validity, "
            "query availability, risk, or execution."
        ),
    }


def test_fixture_service_renders_bid_ask_last_with_fixture_status() -> None:
    panel = _panel(
        FuturesQuoteService(
            FixtureFuturesQuoteProvider(_quote()),
            clock=lambda: NOW,
        )
    )

    market_data = panel["market_data"]
    assert market_data["bid"] == "7175"
    assert market_data["ask"] == "7175.5"
    assert market_data["last"] == "7175.25"
    assert market_data["quote_time"] == "2026-04-30T11:59:58+00:00"
    assert market_data["status"] == "Fixture quote"
    assert "provider_name" not in market_data
    assert "failure_reason" not in market_data


def test_missing_quote_values_render_na() -> None:
    panel = _panel(
        FuturesQuoteService(
            FixtureFuturesQuoteProvider(_quote(bid=None, ask=None, last=None)),
            clock=lambda: NOW,
        )
    )

    market_data = panel["market_data"]
    assert market_data["bid"] == "N/A"
    assert market_data["ask"] == "N/A"
    assert market_data["last"] == "N/A"
    assert market_data["status"] == "Fixture quote"


def test_missing_quote_timestamp_renders_unknown() -> None:
    panel = _panel(
        FuturesQuoteService(
            FixtureFuturesQuoteProvider(_quote(received_at="")),
            clock=lambda: NOW,
        )
    )

    market_data = panel["market_data"]
    assert market_data["quote_time"] == "unknown"
    assert market_data["status"] == "Market data unavailable"


def test_stale_fixture_quote_renders_stale_status() -> None:
    panel = _panel(
        FuturesQuoteService(
            FixtureFuturesQuoteProvider(_quote(received_at="2026-04-30T11:58:00+00:00")),
            clock=lambda: NOW,
        )
    )

    market_data = panel["market_data"]
    assert market_data["status"] == "Fixture quote (stale)"
    assert market_data["bid"] == "7175"
    assert market_data["ask"] == "7175.5"
    assert market_data["last"] == "7175.25"


def test_surface_projection_does_not_import_probe_or_launch_profile_modules() -> None:
    source_root = Path(__file__).resolve().parents[1] / "src" / "ntb_marimo_console"
    mapper_source = (source_root / "viewmodels" / "mappers.py").read_text(encoding="utf-8")
    surface_source = (source_root / "ui" / "surfaces" / "live_observables.py").read_text(encoding="utf-8")

    assert "probe_schwab_futures_market_data_adapter" not in mapper_source
    assert "launch_config" not in mapper_source
    assert "runtime_profiles" not in mapper_source
    assert "probe_schwab_futures_market_data_adapter" not in surface_source
