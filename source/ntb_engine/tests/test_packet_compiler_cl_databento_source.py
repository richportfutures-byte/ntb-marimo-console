from __future__ import annotations

import io
import json
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from ninjatradebuilder.packet_compiler.models import CLDatabentoHistoricalRequest
from ninjatradebuilder.packet_compiler.cli import run_cli as run_compile_cli
from ninjatradebuilder.packet_compiler.sources import (
    DatabentoCLHistoricalMarketDataSource,
    JsonCLDatabentoHistoricalRequestSource,
    PacketCompilerSourceError,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "compiler"
ET = ZoneInfo("America/New_York")
SYMBOL = "CL.c.0"


def _load_request_fixture() -> Path:
    return FIXTURES_DIR / "cl_databento_request.valid.json"


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
    return (
        datetime.combine(session_date, time(hh, mm), tzinfo=ET)
        .astimezone(ZoneInfo("UTC"))
        .isoformat()
        .replace("+00:00", "Z")
    )


def _bar_records() -> list[dict]:
    records: list[dict] = []
    dates = _session_dates()
    for index, session_date in enumerate(dates):
        base = 72.0 + (index * 0.1)
        records.extend(
            [
                {
                    "symbol": SYMBOL,
                    "ts_event": _utc_iso(session_date, 9, 0),
                    "open": base,
                    "high": base + 0.2,
                    "low": base - 0.1,
                    "close": base + 0.1,
                    "volume": 100.0 + index,
                },
                {
                    "symbol": SYMBOL,
                    "ts_event": _utc_iso(session_date, 11, 0),
                    "open": base + 0.1,
                    "high": base + 0.3,
                    "low": base,
                    "close": base + 0.2,
                    "volume": 120.0 + index,
                },
                {
                    "symbol": SYMBOL,
                    "ts_event": _utc_iso(session_date, 14, 5),
                    "open": base + 0.2,
                    "high": base + 0.4,
                    "low": base + 0.05,
                    "close": base + 0.25,
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
                        "open": base + 0.05,
                        "high": base + 0.1,
                        "low": base - 0.15,
                        "close": base,
                        "volume": 50.0,
                    },
                    {
                        "symbol": SYMBOL,
                        "ts_event": _utc_iso(next_date, 6, 0),
                        "open": base,
                        "high": base + 0.15,
                        "low": base - 0.05,
                        "close": base + 0.05,
                        "volume": 60.0,
                    },
                ]
            )
    return records


def _trade_records() -> list[dict]:
    records: list[dict] = []
    prior_date, current_date = _session_dates()[-2:]
    records.extend(
        [
            {"symbol": SYMBOL, "ts_event": _utc_iso(prior_date, 9, 15), "price": 73.00, "size": 10.0, "side": "bid"},
            {"symbol": SYMBOL, "ts_event": _utc_iso(prior_date, 10, 0), "price": 73.01, "size": 30.0, "side": "ask"},
            {"symbol": SYMBOL, "ts_event": _utc_iso(prior_date, 11, 30), "price": 73.02, "size": 15.0, "side": "bid"},
            {"symbol": SYMBOL, "ts_event": _utc_iso(current_date, 9, 10), "price": 73.10, "size": 10.0, "side": "bid"},
            {"symbol": SYMBOL, "ts_event": _utc_iso(current_date, 10, 0), "price": 73.11, "size": 30.0, "side": "ask"},
            {"symbol": SYMBOL, "ts_event": _utc_iso(current_date, 11, 30), "price": 73.12, "size": 20.0, "side": "bid"},
            {"symbol": SYMBOL, "ts_event": _utc_iso(current_date, 12, 45), "price": 73.11, "size": 5.0, "side": "bid"},
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


def test_json_cl_databento_request_source_loads_valid_request() -> None:
    request = JsonCLDatabentoHistoricalRequestSource(_load_request_fixture()).load_cl_request()

    assert request.contract == "CL"
    assert request.dataset == "GLBX.MDP3"
    assert request.symbol == "CL.c.0"
    assert request.stype_in == "continuous"
    assert request.bar_schema == "ohlcv-1m"
    assert request.trades_schema == "trades"


def test_databento_cl_historical_source_maps_provider_responses_to_cl_input(monkeypatch) -> None:
    monkeypatch.setenv("DATABENTO_API_KEY", "test-key")
    request = JsonCLDatabentoHistoricalRequestSource(_load_request_fixture()).load_cl_request()
    source = DatabentoCLHistoricalMarketDataSource(
        request=request,
        client_factory=_client_factory(_bar_records(), _trade_records()),
    )

    historical = source.load_cl_input()

    assert historical.contract == "CL"
    assert historical.current_price > 0
    assert historical.current_session_vah >= historical.current_session_poc >= historical.current_session_val
    assert historical.previous_session_vah >= historical.previous_session_poc >= historical.previous_session_val
    assert historical.avg_20d_session_range > 0
    assert historical.current_volume_vs_average > 0
    assert historical.event_calendar_remainder == []


def test_databento_cl_historical_source_fails_closed_when_api_key_is_missing(monkeypatch) -> None:
    monkeypatch.delenv("DATABENTO_API_KEY", raising=False)
    request = JsonCLDatabentoHistoricalRequestSource(_load_request_fixture()).load_cl_request()
    source = DatabentoCLHistoricalMarketDataSource(
        request=request,
        client_factory=_client_factory(_bar_records(), _trade_records()),
    )

    with pytest.raises(PacketCompilerSourceError, match="DATABENTO_API_KEY"):
        source.load_cl_input()


def test_databento_cl_historical_source_fails_closed_on_malformed_provider_response(monkeypatch) -> None:
    monkeypatch.setenv("DATABENTO_API_KEY", "test-key")
    request = JsonCLDatabentoHistoricalRequestSource(_load_request_fixture()).load_cl_request()
    malformed_bars = _bar_records()
    malformed_bars[0].pop("close")
    source = DatabentoCLHistoricalMarketDataSource(
        request=request,
        client_factory=_client_factory(malformed_bars, _trade_records()),
    )

    with pytest.raises(PacketCompilerSourceError, match="close"):
        source.load_cl_input()


def test_databento_cl_historical_source_fails_closed_on_incomplete_session_coverage(monkeypatch) -> None:
    monkeypatch.setenv("DATABENTO_API_KEY", "test-key")
    request = JsonCLDatabentoHistoricalRequestSource(_load_request_fixture()).load_cl_request()
    incomplete_bars = [
        record
        for record in _bar_records()
        if not record["ts_event"].startswith("2025-12-15")
    ]
    source = DatabentoCLHistoricalMarketDataSource(
        request=request,
        client_factory=_client_factory(incomplete_bars, _trade_records()),
    )

    with pytest.raises(PacketCompilerSourceError, match="20 completed prior CL RTH sessions"):
        source.load_cl_input()


def test_databento_cl_historical_source_fails_closed_on_unsupported_request_input(monkeypatch) -> None:
    monkeypatch.setenv("DATABENTO_API_KEY", "test-key")
    valid_request = JsonCLDatabentoHistoricalRequestSource(_load_request_fixture()).load_cl_request()
    request = CLDatabentoHistoricalRequest.model_construct(
        contract="CL",
        dataset=valid_request.dataset,
        symbol=valid_request.symbol,
        stype_in=valid_request.stype_in,
        current_session_date=valid_request.current_session_date,
        bar_schema="ohlcv-1m",
        trades_schema="mbp-1",
    )
    source = DatabentoCLHistoricalMarketDataSource(
        request=request,
        client_factory=_client_factory(_bar_records(), _trade_records()),
    )

    with pytest.raises(PacketCompilerSourceError, match="only supports ohlcv-1m and trades"):
        source.load_cl_input()


def test_compiler_cli_accepts_cl_databento_branch_with_mocked_source(monkeypatch, tmp_path: Path) -> None:
    class FakeDatabentoCLHistoricalMarketDataSource:
        def __init__(self, request):
            self.request = request

        def load_cl_input(self):
            return json.loads((FIXTURES_DIR / "cl_historical_input.valid.json").read_text())

    monkeypatch.setattr(
        "ninjatradebuilder.packet_compiler.cli.DatabentoCLHistoricalMarketDataSource",
        FakeDatabentoCLHistoricalMarketDataSource,
    )
    stdout = io.StringIO()
    stderr = io.StringIO()
    output_path = tmp_path / "cl-databento.packet.json"

    exit_code = run_compile_cli(
        [
            "--contract",
            "CL",
            "--historical-source",
            "databento",
            "--databento-request",
            str(_load_request_fixture()),
            "--overlay",
            str(FIXTURES_DIR / "cl_overlay.assisted.valid.json"),
            "--extension-input",
            str(FIXTURES_DIR / "cl_extension.valid.json"),
            "--output",
            str(output_path),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    summary = json.loads(stdout.getvalue())
    assert summary["contract"] == "CL"
    assert output_path.is_file()
