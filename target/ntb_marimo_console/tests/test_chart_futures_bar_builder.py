from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ntb_marimo_console.market_data import ChartFuturesBarBuilder


BASE_TIME = datetime(2026, 5, 6, 14, 0, 0, tzinfo=timezone.utc)
EXPECTED_SYMBOLS = {
    "ES": "/ESM26",
    "NQ": "/NQM26",
    "CL": "/CLM26",
    "6E": "/6EM26",
    "MGC": "/MGCM26",
}


def bar_message(
    contract: str = "ES",
    *,
    minute: int = 0,
    symbol: str | None = None,
    open_price: float = 100.0,
    high: float | None = None,
    low: float | None = None,
    close: float | None = None,
    volume: int = 100,
    completed: bool = True,
) -> dict[str, object]:
    start = BASE_TIME + timedelta(minutes=minute)
    close_price = open_price + 0.25 if close is None else close
    return {
        "service": "CHART_FUTURES",
        "contract": contract,
        "symbol": symbol or EXPECTED_SYMBOLS.get(contract, f"/{contract}M26"),
        "start_time": start.isoformat(),
        "end_time": (start + timedelta(minutes=1)).isoformat(),
        "open": open_price,
        "high": max(open_price, close_price) + 0.25 if high is None else high,
        "low": min(open_price, close_price) - 0.25 if low is None else low,
        "close": close_price,
        "volume": volume,
        "completed": completed,
    }


def ingest_minutes(builder: ChartFuturesBarBuilder, minutes: range | tuple[int, ...], *, contract: str = "ES") -> None:
    for minute in minutes:
        builder.ingest(
            bar_message(
                contract,
                minute=minute,
                open_price=100.0 + minute,
                close=100.5 + minute,
                volume=100 + minute,
            )
        )


def test_one_minute_bar_schema_serializes_deterministically() -> None:
    builder = ChartFuturesBarBuilder(expected_symbols=EXPECTED_SYMBOLS)

    result = builder.ingest(bar_message())
    payload = result.one_minute_bar.to_dict()

    assert result.accepted is True
    assert payload == {
        "contract": "ES",
        "symbol": "/ESM26",
        "interval": "1m",
        "start_time": "2026-05-06T14:00:00+00:00",
        "end_time": "2026-05-06T14:01:00+00:00",
        "open": 100.0,
        "high": 100.5,
        "low": 99.75,
        "close": 100.25,
        "volume": 100,
        "completed": True,
        "source": "chart_futures_fixture",
        "quality": {"state": "usable", "usable": True, "blocking_reasons": []},
        "blocking_reasons": [],
    }
    assert json.loads(json.dumps(payload, sort_keys=True))["interval"] == "1m"


def test_valid_fixture_bars_are_accepted_for_final_targets() -> None:
    builder = ChartFuturesBarBuilder(expected_symbols=EXPECTED_SYMBOLS)

    for contract in ("ES", "NQ", "CL", "6E", "MGC"):
        result = builder.ingest(bar_message(contract, minute=len(builder.states()[contract].completed_one_minute_bars)))
        assert result.accepted is True
        assert result.contract == contract


def test_zn_and_gc_are_excluded_from_final_target_bar_state() -> None:
    builder = ChartFuturesBarBuilder(expected_symbols=EXPECTED_SYMBOLS)

    zn_result = builder.ingest(bar_message("ZN", symbol="/ZNM26"))
    gc_result = builder.ingest(bar_message("GC", symbol="/GCM26"))

    assert zn_result.accepted is False
    assert "excluded_contract:ZN" in zn_result.blocking_reasons
    assert gc_result.accepted is False
    assert "never_supported_contract:GC" in gc_result.blocking_reasons
    assert "MGC" in builder.states()
    assert "GC" not in builder.states()


def test_malformed_bar_missing_ohlcv_fields_is_rejected() -> None:
    builder = ChartFuturesBarBuilder(expected_symbols=EXPECTED_SYMBOLS)
    message = bar_message()
    message.pop("close")

    result = builder.ingest(message)

    assert result.accepted is False
    assert "missing_ohlcv_fields:close" in result.blocking_reasons
    assert builder.state("ES").completed_one_minute_bars == ()


def test_symbol_mismatch_is_rejected() -> None:
    builder = ChartFuturesBarBuilder(expected_symbols=EXPECTED_SYMBOLS)

    result = builder.ingest(bar_message(symbol="/NQM26"))

    assert result.accepted is False
    assert "symbol_mismatch:ES:/NQM26" in result.blocking_reasons


def test_five_minute_bar_completes_only_after_all_required_one_minute_bars_are_present() -> None:
    builder = ChartFuturesBarBuilder(expected_symbols=EXPECTED_SYMBOLS)

    ingest_minutes(builder, range(4))
    partial_state = builder.state("ES")
    assert partial_state.completed_five_minute_bars == ()
    assert partial_state.usable is False
    assert partial_state.building_five_minute_bar is not None
    assert partial_state.building_five_minute_bar.completed is False

    builder.ingest(bar_message(minute=4, open_price=104.0, close=104.5, volume=104))
    state = builder.state("ES")

    assert len(state.completed_five_minute_bars) == 1
    completed = state.completed_five_minute_bars[0]
    assert completed.interval == "5m"
    assert completed.completed is True
    assert completed.start_time == "2026-05-06T14:00:00+00:00"
    assert completed.end_time == "2026-05-06T14:05:00+00:00"
    assert completed.open == 100.0
    assert completed.close == 104.5
    assert completed.volume == 510
    assert state.building_five_minute_bar is None
    assert state.usable is True


def test_gap_prevents_completed_five_minute_confirmation() -> None:
    builder = ChartFuturesBarBuilder(expected_symbols=EXPECTED_SYMBOLS)

    ingest_minutes(builder, (0, 1, 2, 3, 5))
    state = builder.state("ES")

    assert state.completed_five_minute_bars == ()
    assert "gap_in_one_minute_bars:ES:2026-05-06T14:00:00+00:00" in state.blocking_reasons
    assert state.building_five_minute_bar is not None
    assert state.building_five_minute_bar.start_time == "2026-05-06T14:05:00+00:00"


def test_out_of_order_input_is_rejected_deterministically() -> None:
    builder = ChartFuturesBarBuilder(expected_symbols=EXPECTED_SYMBOLS)
    ingest_minutes(builder, (0, 2))

    result = builder.ingest(bar_message(minute=1, open_price=101.0, close=101.5))
    state = builder.state("ES")

    assert result.accepted is False
    assert "out_of_order_bar:ES:2026-05-06T14:01:00+00:00" in result.blocking_reasons
    assert len(state.completed_one_minute_bars) == 2
    assert "out_of_order_bar:ES:2026-05-06T14:01:00+00:00" in state.blocking_reasons


def test_reset_clears_only_requested_contract_state() -> None:
    builder = ChartFuturesBarBuilder(expected_symbols=EXPECTED_SYMBOLS)
    ingest_minutes(builder, range(5), contract="ES")
    ingest_minutes(builder, range(5), contract="NQ")

    es_state = builder.reset_contract("ES")
    nq_state = builder.state("NQ")

    assert es_state.completed_one_minute_bars == ()
    assert es_state.completed_five_minute_bars == ()
    assert len(nq_state.completed_one_minute_bars) == 5
    assert len(nq_state.completed_five_minute_bars) == 1


def test_bars_from_one_contract_do_not_bleed_into_another_contract() -> None:
    builder = ChartFuturesBarBuilder(expected_symbols=EXPECTED_SYMBOLS)
    ingest_minutes(builder, range(5), contract="ES")

    es_state = builder.state("ES")
    nq_state = builder.state("NQ")

    assert len(es_state.completed_five_minute_bars) == 1
    assert nq_state.completed_one_minute_bars == ()
    assert nq_state.completed_five_minute_bars == ()


def test_completed_close_count_uses_completed_five_minute_bars_only() -> None:
    builder = ChartFuturesBarBuilder(expected_symbols=EXPECTED_SYMBOLS)
    ingest_minutes(builder, range(5))
    builder.ingest(bar_message(minute=5, open_price=110.0, close=111.0))

    result = builder.completed_close_count_at_or_beyond_level("ES", level=104.0)

    assert result.status == "available"
    assert result.value == 1
    assert builder.state("ES").building_five_minute_bar is not None


def test_range_and_volume_helpers_return_insufficient_when_data_is_missing() -> None:
    builder = ChartFuturesBarBuilder(expected_symbols=EXPECTED_SYMBOLS)
    ingest_minutes(builder, range(5))

    range_result = builder.basic_range_state("ES")
    volume_result = builder.volume_velocity_state("ES")

    assert range_result.status == "insufficient"
    assert "insufficient_completed_bars_for_range_state" in range_result.blocking_reasons
    assert volume_result.status == "insufficient"
    assert "insufficient_completed_bars_for_volume_velocity" in volume_result.blocking_reasons


def test_stale_bar_state_adds_blocking_reason_without_fabricating_data() -> None:
    builder = ChartFuturesBarBuilder(expected_symbols=EXPECTED_SYMBOLS)
    ingest_minutes(builder, range(5))

    state = builder.state(
        "ES",
        now=BASE_TIME + timedelta(minutes=30),
        max_completed_bar_age_seconds=60,
    )

    assert any(reason.startswith("stale_bar_data:") for reason in state.blocking_reasons)
    assert len(state.completed_five_minute_bars) == 1


def test_bar_builder_has_no_network_or_stream_client_surface() -> None:
    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "ntb_marimo_console"
        / "market_data"
        / "bar_builder.py"
    ).read_text(encoding="utf-8")

    assert "SchwabStreamClient" not in source
    assert ".login(" not in source
    assert ".subscribe(" not in source
    assert "websocket" not in source.lower()
