from __future__ import annotations

import json
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from ninjatradebuilder.packet_compiler.sources import (
    DatabentoHistoricalMarketDataSource,
    JsonDatabentoHistoricalRequestSource,
    PacketCompilerSourceError,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "compiler"
ET = ZoneInfo("America/New_York")
SYMBOL = "ES.c.0"


def _load_request_fixture() -> Path:
    return FIXTURES_DIR / "es_databento_request.valid.json"


def _session_dates() -> list[date]:
    return [
        date(2025, 12, 15),
        date(2025, 12, 16),
        date(2025, 12, 17),
        date(2025, 12, 18),
        date(2025, 12, 19),
        date(2025, 12, 22),
        date(2025, 12, 23),
        date(2025, 12, 24),
        date(2025, 12, 26),
        date(2025, 12, 29),
        date(2025, 12, 30),
        date(2025, 12, 31),
        date(2026, 1, 2),
        date(2026, 1, 5),
        date(2026, 1, 6),
        date(2026, 1, 7),
        date(2026, 1, 8),
        date(2026, 1, 9),
        date(2026, 1, 12),
        date(2026, 1, 13),
        date(2026, 1, 14),
    ]


def _utc_iso(session_date: date, hh: int, mm: int) -> str:
    return datetime.combine(session_date, time(hh, mm), tzinfo=ET).astimezone(ZoneInfo("UTC")).isoformat().replace("+00:00", "Z")


def _bar_records() -> list[dict]:
    records: list[dict] = []
    dates = _session_dates()
    for index, session_date in enumerate(dates):
        base = 5000.0 + index
        records.extend(
            [
                {
                    "symbol": SYMBOL,
                    "ts_event": _utc_iso(session_date, 9, 30),
                    "open": base,
                    "high": base + 1.0,
                    "low": base - 1.0,
                    "close": base + 0.5,
                    "volume": 100.0 + index,
                },
                {
                    "symbol": SYMBOL,
                    "ts_event": _utc_iso(session_date, 10, 0),
                    "open": base + 0.5,
                    "high": base + 2.0,
                    "low": base - 0.5,
                    "close": base + 1.0,
                    "volume": 120.0 + index,
                },
                {
                    "symbol": SYMBOL,
                    "ts_event": _utc_iso(session_date, 15, 59),
                    "open": base + 1.0,
                    "high": base + 3.0,
                    "low": base,
                    "close": base + 2.0,
                    "volume": 140.0 + index,
                },
            ]
        )
        if session_date != dates[-1]:
            next_date = dates[index + 1]
            records.extend(
                [
                    {
                        "symbol": SYMBOL,
                        "ts_event": _utc_iso(next_date, 2, 0),
                        "open": base + 0.25,
                        "high": base + 0.5,
                        "low": base - 0.75,
                        "close": base,
                        "volume": 50.0,
                    },
                    {
                        "symbol": SYMBOL,
                        "ts_event": _utc_iso(next_date, 7, 0),
                        "open": base,
                        "high": base + 0.75,
                        "low": base - 0.5,
                        "close": base + 0.25,
                        "volume": 60.0,
                    },
                ]
            )
    return records


def _trade_records() -> list[dict]:
    records: list[dict] = []
    for index, session_date in enumerate(_session_dates()[-2:]):
        base = 5010.0 + index
        records.extend(
            [
                {"symbol": SYMBOL, "ts_event": _utc_iso(session_date, 9, 35), "price": base, "size": 10.0},
                {"symbol": SYMBOL, "ts_event": _utc_iso(session_date, 10, 15), "price": base + 0.25, "size": 20.0},
                {"symbol": SYMBOL, "ts_event": _utc_iso(session_date, 11, 45), "price": base + 0.5, "size": 30.0},
                {"symbol": SYMBOL, "ts_event": _utc_iso(session_date, 13, 15), "price": base + 0.25, "size": 15.0},
            ]
        )
    return records


class _FakeFrame:
    def __init__(self, records: list[dict]):
        self._records = records

    def reset_index(self) -> "_FakeFrame":
        return self

    def to_dict(self, orient: str = "records") -> list[dict]:
        assert orient == "records"
        return list(self._records)


class _FakeResponse:
    def __init__(self, records: list[dict]):
        self._records = records

    def to_df(self) -> _FakeFrame:
        return _FakeFrame(self._records)


class _FakeTimeseries:
    def __init__(self, bars: list[dict], trades: list[dict]):
        self._bars = bars
        self._trades = trades

    def get_range(self, **kwargs):
        schema = kwargs["schema"]
        if schema == "ohlcv-1m":
            return _FakeResponse(self._bars)
        if schema == "trades":
            return _FakeResponse(self._trades)
        raise AssertionError(f"unexpected schema {schema}")


class _FakeHistoricalClient:
    def __init__(self, bars: list[dict], trades: list[dict]):
        self.timeseries = _FakeTimeseries(bars, trades)


def _client_factory(bars: list[dict], trades: list[dict]):
    return lambda api_key: _FakeHistoricalClient(bars, trades)


def test_json_databento_request_source_loads_valid_request() -> None:
    request = JsonDatabentoHistoricalRequestSource(_load_request_fixture()).load_es_request()

    assert request.contract == "ES"
    assert request.dataset == "GLBX.MDP3"
    assert request.symbol == "ES.c.0"
    assert request.stype_in == "continuous"
    assert request.bar_schema == "ohlcv-1m"
    assert request.trades_schema == "trades"


def test_databento_historical_source_maps_provider_responses_to_es_input(monkeypatch) -> None:
    monkeypatch.setenv("DATABENTO_API_KEY", "test-key")
    request = JsonDatabentoHistoricalRequestSource(_load_request_fixture()).load_es_request()
    source = DatabentoHistoricalMarketDataSource(
        request=request,
        client_factory=_client_factory(_bar_records(), _trade_records()),
    )

    historical = source.load_es_input()

    assert historical.contract == "ES"
    assert len(historical.current_rth_bars) == 3
    assert len(historical.prior_rth_bars) == 3
    assert len(historical.overnight_bars) >= 2
    assert len(historical.prior_20_rth_sessions) == 20
    assert len(historical.prior_20_rth_observed_volumes) == 20
    assert len(historical.current_rth_volume_profile) >= 3
    assert len(historical.prior_rth_volume_profile) >= 3


def test_databento_historical_source_fails_closed_when_api_key_is_missing(monkeypatch) -> None:
    monkeypatch.delenv("DATABENTO_API_KEY", raising=False)
    request = JsonDatabentoHistoricalRequestSource(_load_request_fixture()).load_es_request()
    source = DatabentoHistoricalMarketDataSource(
        request=request,
        client_factory=_client_factory(_bar_records(), _trade_records()),
    )

    with pytest.raises(PacketCompilerSourceError, match="DATABENTO_API_KEY"):
        source.load_es_input()


def test_databento_historical_source_fails_closed_on_malformed_provider_response(monkeypatch) -> None:
    monkeypatch.setenv("DATABENTO_API_KEY", "test-key")
    request = JsonDatabentoHistoricalRequestSource(_load_request_fixture()).load_es_request()
    malformed_bars = _bar_records()
    malformed_bars[0].pop("volume")
    source = DatabentoHistoricalMarketDataSource(
        request=request,
        client_factory=_client_factory(malformed_bars, _trade_records()),
    )

    with pytest.raises(PacketCompilerSourceError, match="volume"):
        source.load_es_input()


def test_databento_historical_source_fails_closed_on_incomplete_session_coverage(monkeypatch) -> None:
    monkeypatch.setenv("DATABENTO_API_KEY", "test-key")
    request = JsonDatabentoHistoricalRequestSource(_load_request_fixture()).load_es_request()
    incomplete_bars = [
        record
        for record in _bar_records()
        if not record["ts_event"].startswith("2025-12-15")
    ]
    source = DatabentoHistoricalMarketDataSource(
        request=request,
        client_factory=_client_factory(incomplete_bars, _trade_records()),
    )

    with pytest.raises(PacketCompilerSourceError, match="20 completed prior RTH sessions"):
        source.load_es_input()
