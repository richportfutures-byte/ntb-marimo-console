from __future__ import annotations

import io
import json
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from ninjatradebuilder.packet_compiler.cli import run_cli as run_compile_cli
from ninjatradebuilder.packet_compiler.mgc import compile_mgc_packet
from ninjatradebuilder.packet_compiler.sources import (
    DatabentoMGCHistoricalMarketDataSource,
    JsonMGCDatabentoHistoricalRequestSource,
    PacketCompilerSourceError,
)
from ninjatradebuilder.validation import validate_historical_packet

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "compiler"
ET = ZoneInfo("America/New_York")
SYMBOL = "MGC.c.0"


def _load_json(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


def _load_request_fixture() -> Path:
    return FIXTURES_DIR / "mgc_databento_request.valid.json"


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
        base = 2025.0 + (index * 1.5)
        records.extend(
            [
                {
                    "symbol": SYMBOL,
                    "ts_event": _utc_iso(session_date, 8, 20),
                    "open": base,
                    "high": base + 2.4,
                    "low": base - 1.8,
                    "close": base + 1.1,
                    "volume": 70.0 + index,
                },
                {
                    "symbol": SYMBOL,
                    "ts_event": _utc_iso(session_date, 10, 30),
                    "open": base + 1.1,
                    "high": base + 4.8,
                    "low": base - 0.6,
                    "close": base + 3.2,
                    "volume": 82.0 + index,
                },
                {
                    "symbol": SYMBOL,
                    "ts_event": _utc_iso(session_date, 13, 15),
                    "open": base + 3.2,
                    "high": base + 6.1,
                    "low": base + 1.5,
                    "close": base + 4.4,
                    "volume": 95.0 + index,
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
                        "open": base + 0.4,
                        "high": base + 1.2,
                        "low": base - 1.4,
                        "close": base - 0.2,
                        "volume": 35.0,
                    },
                    {
                        "symbol": SYMBOL,
                        "ts_event": _utc_iso(next_date, 6, 0),
                        "open": base - 0.2,
                        "high": base + 0.9,
                        "low": base - 1.0,
                        "close": base + 0.3,
                        "volume": 42.0,
                    },
                ]
            )
    return records


def _trade_records() -> list[dict]:
    records: list[dict] = []
    prior_date, current_date = _session_dates()[-2:]
    records.extend(
        [
            {"symbol": SYMBOL, "ts_event": _utc_iso(prior_date, 8, 25), "price": 2053.0, "size": 6.0, "side": "bid"},
            {"symbol": SYMBOL, "ts_event": _utc_iso(prior_date, 9, 45), "price": 2053.2, "size": 8.0, "side": "ask"},
            {"symbol": SYMBOL, "ts_event": _utc_iso(prior_date, 11, 10), "price": 2053.5, "size": 10.0, "side": "bid"},
            {"symbol": SYMBOL, "ts_event": _utc_iso(prior_date, 12, 40), "price": 2053.7, "size": 12.0, "side": "bid"},
            {"symbol": SYMBOL, "ts_event": _utc_iso(current_date, 8, 25), "price": 2054.0, "size": 6.0, "side": "bid"},
            {"symbol": SYMBOL, "ts_event": _utc_iso(current_date, 9, 45), "price": 2054.2, "size": 8.0, "side": "ask"},
            {"symbol": SYMBOL, "ts_event": _utc_iso(current_date, 11, 10), "price": 2054.5, "size": 10.0, "side": "bid"},
            {"symbol": SYMBOL, "ts_event": _utc_iso(current_date, 12, 40), "price": 2054.7, "size": 12.0, "side": "bid"},
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


def test_json_mgc_databento_request_source_loads_valid_request() -> None:
    request = JsonMGCDatabentoHistoricalRequestSource(_load_request_fixture()).load_mgc_request()

    assert request.contract == "MGC"
    assert request.dataset == "GLBX.MDP3"
    assert request.symbol == "MGC.c.0"
    assert request.stype_in == "continuous"
    assert request.bar_schema == "ohlcv-1m"
    assert request.trades_schema == "trades"


def test_databento_mgc_historical_source_maps_provider_responses_to_mgc_input(monkeypatch) -> None:
    monkeypatch.setenv("DATABENTO_API_KEY", "test-key")
    request = JsonMGCDatabentoHistoricalRequestSource(_load_request_fixture()).load_mgc_request()
    source = DatabentoMGCHistoricalMarketDataSource(
        request=request,
        client_factory=_client_factory(_bar_records(), _trade_records()),
    )

    historical = source.load_mgc_input()
    artifact = compile_mgc_packet(
        historical,
        _load_json("mgc_overlay.assisted.valid.json"),
        _load_json("mgc_extension.valid.json"),
        compiled_at_iso="2026-01-14T18:20:00Z",
    )
    validated = validate_historical_packet(artifact.packet.model_dump(by_alias=True, mode="json"))

    assert historical.contract == "MGC"
    assert historical.current_price > 0
    assert historical.current_session_vah >= historical.current_session_poc >= historical.current_session_val
    assert historical.previous_session_vah >= historical.previous_session_poc >= historical.previous_session_val
    assert historical.avg_20d_session_range > 0
    assert historical.current_volume_vs_average > 0
    assert historical.event_calendar_remainder == []
    assert validated.market_packet.contract == "MGC"
    assert validated.contract_specific_extension.dxy_context == "weakening"
    assert validated.contract_specific_extension.yield_context == "falling"


def test_databento_mgc_historical_source_fails_closed_when_api_key_is_missing(monkeypatch) -> None:
    monkeypatch.delenv("DATABENTO_API_KEY", raising=False)
    request = JsonMGCDatabentoHistoricalRequestSource(_load_request_fixture()).load_mgc_request()
    source = DatabentoMGCHistoricalMarketDataSource(
        request=request,
        client_factory=_client_factory(_bar_records(), _trade_records()),
    )

    with pytest.raises(PacketCompilerSourceError, match="DATABENTO_API_KEY"):
        source.load_mgc_input()


def test_databento_mgc_historical_source_fails_closed_on_malformed_provider_response(monkeypatch) -> None:
    monkeypatch.setenv("DATABENTO_API_KEY", "test-key")
    request = JsonMGCDatabentoHistoricalRequestSource(_load_request_fixture()).load_mgc_request()
    malformed_bars = _bar_records()
    malformed_bars[0].pop("close")
    source = DatabentoMGCHistoricalMarketDataSource(
        request=request,
        client_factory=_client_factory(malformed_bars, _trade_records()),
    )

    with pytest.raises(PacketCompilerSourceError, match="close"):
        source.load_mgc_input()


def test_databento_mgc_historical_source_fails_closed_on_incomplete_session_coverage(monkeypatch) -> None:
    monkeypatch.setenv("DATABENTO_API_KEY", "test-key")
    request = JsonMGCDatabentoHistoricalRequestSource(_load_request_fixture()).load_mgc_request()
    incomplete_bars = [
        record
        for record in _bar_records()
        if not record["ts_event"].startswith("2025-12-15")
    ]
    source = DatabentoMGCHistoricalMarketDataSource(
        request=request,
        client_factory=_client_factory(incomplete_bars, _trade_records()),
    )

    with pytest.raises(PacketCompilerSourceError, match="20 completed prior MGC RTH sessions"):
        source.load_mgc_input()


def test_compiler_cli_writes_mgc_packet_from_databento_historical_source(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "ninjatradebuilder.packet_compiler.sources._build_databento_client",
        lambda *, api_key_env_var, client_factory: _FakeHistoricalClient(_bar_records(), _trade_records()),
    )
    output_path = tmp_path / "mgc.databento.packet.json"
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = run_compile_cli(
        [
            "--contract",
            "MGC",
            "--historical-source",
            "databento",
            "--databento-request",
            str(_load_request_fixture()),
            "--overlay",
            str(FIXTURES_DIR / "mgc_overlay.assisted.valid.json"),
            "--extension-input",
            str(FIXTURES_DIR / "mgc_extension.valid.json"),
            "--output",
            str(output_path),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    summary = json.loads(stdout.getvalue())
    assert summary["contract"] == "MGC"
    assert output_path.is_file()
    validate_historical_packet(json.loads(output_path.read_text()))
