from __future__ import annotations

import io
import json
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from ninjatradebuilder.packet_compiler.cli import run_cli as run_compile_cli
from ninjatradebuilder.packet_compiler.sixe import compile_six_e_packet
from ninjatradebuilder.packet_compiler.sources import (
    DatabentoSixEHistoricalMarketDataSource,
    JsonSixEDatabentoHistoricalRequestSource,
    PacketCompilerSourceError,
)
from ninjatradebuilder.validation import validate_historical_packet

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "compiler"
SYMBOL = "6E.c.0"
UTC = ZoneInfo("UTC")


def _load_json(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


def _load_request_fixture() -> Path:
    return FIXTURES_DIR / "6e_databento_request.valid.json"


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
    return datetime.combine(session_date, time(hh, mm), tzinfo=UTC).isoformat().replace("+00:00", "Z")


def _bar_records() -> list[dict]:
    records: list[dict] = []
    for index, session_date in enumerate(_session_dates()):
        base = 1.075 + (index * 0.0005)
        records.extend(
            [
                {
                    "symbol": SYMBOL,
                    "ts_event": _utc_iso(session_date, 0, 0),
                    "open": base - 0.0008,
                    "high": base - 0.0002,
                    "low": base - 0.0014,
                    "close": base - 0.0005,
                    "volume": 80.0 + index,
                },
                {
                    "symbol": SYMBOL,
                    "ts_event": _utc_iso(session_date, 2, 0),
                    "open": base - 0.0005,
                    "high": base,
                    "low": base - 0.0011,
                    "close": base - 0.0001,
                    "volume": 82.0 + index,
                },
                {
                    "symbol": SYMBOL,
                    "ts_event": _utc_iso(session_date, 6, 0),
                    "open": base - 0.0001,
                    "high": base + 0.0002,
                    "low": base - 0.0007,
                    "close": base + 0.0001,
                    "volume": 84.0 + index,
                },
                {
                    "symbol": SYMBOL,
                    "ts_event": _utc_iso(session_date, 7, 0),
                    "open": base + 0.0001,
                    "high": base + 0.0004,
                    "low": base - 0.0003,
                    "close": base + 0.0003,
                    "volume": 95.0 + index,
                },
                {
                    "symbol": SYMBOL,
                    "ts_event": _utc_iso(session_date, 9, 0),
                    "open": base + 0.0003,
                    "high": base + 0.0009,
                    "low": base + 0.0001,
                    "close": base + 0.0007,
                    "volume": 98.0 + index,
                },
                {
                    "symbol": SYMBOL,
                    "ts_event": _utc_iso(session_date, 12, 0),
                    "open": base + 0.0007,
                    "high": base + 0.0012,
                    "low": base + 0.0002,
                    "close": base + 0.001,
                    "volume": 102.0 + index,
                },
                {
                    "symbol": SYMBOL,
                    "ts_event": _utc_iso(session_date, 13, 0),
                    "open": base + 0.001,
                    "high": base + 0.0014,
                    "low": base + 0.0006,
                    "close": base + 0.0012,
                    "volume": 115.0 + index,
                },
                {
                    "symbol": SYMBOL,
                    "ts_event": _utc_iso(session_date, 15, 0),
                    "open": base + 0.0012,
                    "high": base + 0.0018,
                    "low": base + 0.0009,
                    "close": base + 0.0015,
                    "volume": 120.0 + index,
                },
                {
                    "symbol": SYMBOL,
                    "ts_event": _utc_iso(session_date, 17, 0),
                    "open": base + 0.0015,
                    "high": base + 0.0019,
                    "low": base + 0.0011,
                    "close": base + 0.0017,
                    "volume": 125.0 + index,
                },
            ]
        )
    return records


def _trade_records() -> list[dict]:
    records: list[dict] = []
    prior_date, current_date = _session_dates()[-2:]
    for session_date, base in ((prior_date, 1.0845), (current_date, 1.0850)):
        records.extend(
            [
                {"symbol": SYMBOL, "ts_event": _utc_iso(session_date, 13, 5), "price": base, "size": 10.0, "side": "bid"},
                {"symbol": SYMBOL, "ts_event": _utc_iso(session_date, 13, 40), "price": base + 0.0005, "size": 15.0, "side": "ask"},
                {"symbol": SYMBOL, "ts_event": _utc_iso(session_date, 14, 20), "price": base + 0.001, "size": 20.0, "side": "bid"},
                {"symbol": SYMBOL, "ts_event": _utc_iso(session_date, 15, 10), "price": base + 0.0005, "size": 12.0, "side": "bid"},
                {"symbol": SYMBOL, "ts_event": _utc_iso(session_date, 16, 15), "price": base + 0.0015, "size": 18.0, "side": "ask"},
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


def test_json_six_e_databento_request_source_loads_valid_request() -> None:
    request = JsonSixEDatabentoHistoricalRequestSource(_load_request_fixture()).load_six_e_request()

    assert request.contract == "6E"
    assert request.dataset == "GLBX.MDP3"
    assert request.symbol == "6E.c.0"
    assert request.stype_in == "continuous"
    assert request.bar_schema == "ohlcv-1m"
    assert request.trades_schema == "trades"


def test_databento_six_e_historical_source_maps_provider_responses_to_six_e_input(monkeypatch) -> None:
    monkeypatch.setenv("DATABENTO_API_KEY", "test-key")
    request = JsonSixEDatabentoHistoricalRequestSource(_load_request_fixture()).load_six_e_request()
    source = DatabentoSixEHistoricalMarketDataSource(
        request=request,
        client_factory=_client_factory(_bar_records(), _trade_records()),
    )

    historical = source.load_six_e_input()
    artifact = compile_six_e_packet(
        historical,
        _load_json("6e_overlay.assisted.valid.json"),
        _load_json("6e_extension.valid.json"),
        compiled_at_iso="2026-01-14T17:05:00Z",
    )
    validated = validate_historical_packet(artifact.packet.model_dump(by_alias=True, mode="json"))

    assert historical.contract == "6E"
    assert historical.current_price > 0
    assert historical.current_session_vah >= historical.current_session_poc >= historical.current_session_val
    assert historical.previous_session_vah >= historical.previous_session_poc >= historical.previous_session_val
    assert historical.avg_20d_session_range > 0
    assert historical.current_volume_vs_average > 0
    assert historical.event_calendar_remainder == []
    assert len(historical.asia_bars) == 3
    assert len(historical.london_bars) == 3
    assert len(historical.ny_bars) == 3
    assert validated.contract_specific_extension.asia_high_low.high == max(bar.high for bar in historical.asia_bars)
    assert validated.contract_specific_extension.london_high_low.low == min(bar.low for bar in historical.london_bars)
    assert validated.contract_specific_extension.ny_high_low_so_far.high == max(bar.high for bar in historical.ny_bars)


def test_databento_six_e_historical_source_fails_closed_when_api_key_is_missing(monkeypatch) -> None:
    monkeypatch.delenv("DATABENTO_API_KEY", raising=False)
    request = JsonSixEDatabentoHistoricalRequestSource(_load_request_fixture()).load_six_e_request()
    source = DatabentoSixEHistoricalMarketDataSource(
        request=request,
        client_factory=_client_factory(_bar_records(), _trade_records()),
    )

    with pytest.raises(PacketCompilerSourceError, match="DATABENTO_API_KEY"):
        source.load_six_e_input()


def test_databento_six_e_historical_source_fails_closed_on_malformed_provider_response(monkeypatch) -> None:
    monkeypatch.setenv("DATABENTO_API_KEY", "test-key")
    request = JsonSixEDatabentoHistoricalRequestSource(_load_request_fixture()).load_six_e_request()
    malformed_bars = _bar_records()
    malformed_bars[0].pop("close")
    source = DatabentoSixEHistoricalMarketDataSource(
        request=request,
        client_factory=_client_factory(malformed_bars, _trade_records()),
    )

    with pytest.raises(PacketCompilerSourceError, match="close"):
        source.load_six_e_input()


def test_databento_six_e_historical_source_fails_closed_on_incomplete_session_coverage(monkeypatch) -> None:
    monkeypatch.setenv("DATABENTO_API_KEY", "test-key")
    request = JsonSixEDatabentoHistoricalRequestSource(_load_request_fixture()).load_six_e_request()
    incomplete_bars = [
        record
        for record in _bar_records()
        if not (
            record["ts_event"].startswith("2026-01-14T07:")
            or record["ts_event"].startswith("2026-01-14T09:")
            or record["ts_event"].startswith("2026-01-14T12:")
        )
    ]
    source = DatabentoSixEHistoricalMarketDataSource(
        request=request,
        client_factory=_client_factory(incomplete_bars, _trade_records()),
    )

    with pytest.raises(PacketCompilerSourceError, match="London coverage"):
        source.load_six_e_input()


def test_compiler_cli_writes_six_e_packet_from_databento_historical_source(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "ninjatradebuilder.packet_compiler.sources._build_databento_client",
        lambda *, api_key_env_var, client_factory: _FakeHistoricalClient(_bar_records(), _trade_records()),
    )
    output_path = tmp_path / "6e.databento.packet.json"
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = run_compile_cli(
        [
            "--contract",
            "6E",
            "--historical-source",
            "databento",
            "--databento-request",
            str(_load_request_fixture()),
            "--overlay",
            str(FIXTURES_DIR / "6e_overlay.assisted.valid.json"),
            "--extension-input",
            str(FIXTURES_DIR / "6e_extension.valid.json"),
            "--output",
            str(output_path),
        ],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    summary = json.loads(stdout.getvalue())
    assert summary["contract"] == "6E"
    assert output_path.is_file()
    validate_historical_packet(json.loads(output_path.read_text()))
