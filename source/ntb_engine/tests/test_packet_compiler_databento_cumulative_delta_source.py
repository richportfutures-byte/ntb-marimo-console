from __future__ import annotations

from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from ninjatradebuilder.packet_compiler.models import ESDatabentoCumulativeDeltaRequest
from ninjatradebuilder.packet_compiler.sources import (
    DatabentoCumulativeDeltaSource,
    JsonDatabentoCumulativeDeltaRequestSource,
    PacketCompilerSourceError,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "compiler"
ET = ZoneInfo("America/New_York")
SYMBOL = "ES.c.0"


def _load_request_fixture() -> Path:
    return FIXTURES_DIR / "es_databento_cumulative_delta_request.valid.json"


def _utc_iso(hh: int, mm: int) -> str:
    return (
        datetime.combine(
            JsonDatabentoCumulativeDeltaRequestSource(_load_request_fixture())
            .load_es_request()
            .current_session_date,
            time(hh, mm),
            tzinfo=ET,
        )
        .astimezone(ZoneInfo("UTC"))
        .isoformat()
        .replace("+00:00", "Z")
    )


def _trade_records() -> list[dict]:
    return [
        {"symbol": SYMBOL, "ts_event": _utc_iso(9, 35), "price": 5010.0, "size": 10.0, "side": "bid"},
        {"symbol": SYMBOL, "ts_event": _utc_iso(10, 5), "price": 5010.25, "size": 7.0, "side": "ask"},
        {"symbol": SYMBOL, "ts_event": _utc_iso(11, 15), "price": 5010.5, "size": 4.0, "side": "b"},
        {"symbol": SYMBOL, "ts_event": _utc_iso(12, 20), "price": 5010.25, "size": 3.0, "side": "a"},
    ]


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
    def __init__(self, trades: list[dict]):
        self._trades = trades

    def get_range(self, **kwargs):
        schema = kwargs["schema"]
        if schema == "trades":
            return _FakeResponse(self._trades)
        raise AssertionError(f"unexpected schema {schema}")


class _FakeHistoricalClient:
    def __init__(self, trades: list[dict]):
        self.timeseries = _FakeTimeseries(trades)


def _client_factory(trades: list[dict]):
    return lambda api_key: _FakeHistoricalClient(trades)


def test_json_databento_cumulative_delta_request_source_loads_valid_request() -> None:
    request = JsonDatabentoCumulativeDeltaRequestSource(_load_request_fixture()).load_es_request()

    assert request.contract == "ES"
    assert request.dataset == "GLBX.MDP3"
    assert request.symbol == "ES.c.0"
    assert request.stype_in == "continuous"
    assert request.trades_schema == "trades"


def test_databento_cumulative_delta_source_maps_provider_response(monkeypatch) -> None:
    monkeypatch.setenv("DATABENTO_API_KEY", "test-key")
    request = JsonDatabentoCumulativeDeltaRequestSource(_load_request_fixture()).load_es_request()
    source = DatabentoCumulativeDeltaSource(
        request=request,
        client_factory=_client_factory(_trade_records()),
    )

    cumulative_delta = source.load_es_cumulative_delta()

    assert cumulative_delta.contract == "ES"
    assert cumulative_delta.cumulative_delta == 4.0


def test_databento_cumulative_delta_source_fails_closed_when_api_key_is_missing(monkeypatch) -> None:
    monkeypatch.delenv("DATABENTO_API_KEY", raising=False)
    request = JsonDatabentoCumulativeDeltaRequestSource(_load_request_fixture()).load_es_request()
    source = DatabentoCumulativeDeltaSource(
        request=request,
        client_factory=_client_factory(_trade_records()),
    )

    with pytest.raises(PacketCompilerSourceError, match="DATABENTO_API_KEY"):
        source.load_es_cumulative_delta()


def test_databento_cumulative_delta_source_fails_closed_on_malformed_provider_response(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATABENTO_API_KEY", "test-key")
    request = JsonDatabentoCumulativeDeltaRequestSource(_load_request_fixture()).load_es_request()
    malformed_trades = _trade_records()
    malformed_trades[0].pop("side")
    source = DatabentoCumulativeDeltaSource(
        request=request,
        client_factory=_client_factory(malformed_trades),
    )

    with pytest.raises(PacketCompilerSourceError, match="include side"):
        source.load_es_cumulative_delta()


def test_databento_cumulative_delta_source_fails_closed_on_incomplete_trade_coverage(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATABENTO_API_KEY", "test-key")
    request = JsonDatabentoCumulativeDeltaRequestSource(_load_request_fixture()).load_es_request()
    off_session_trades = [
        {
            "symbol": SYMBOL,
            "ts_event": _utc_iso(8, 15),
            "price": 5010.0,
            "size": 10.0,
            "side": "bid",
        }
    ]
    source = DatabentoCumulativeDeltaSource(
        request=request,
        client_factory=_client_factory(off_session_trades),
    )

    with pytest.raises(PacketCompilerSourceError, match="usable current-session trade coverage"):
        source.load_es_cumulative_delta()


def test_databento_cumulative_delta_source_fails_closed_on_unsupported_request_schema(
    monkeypatch,
) -> None:
    monkeypatch.setenv("DATABENTO_API_KEY", "test-key")
    request = ESDatabentoCumulativeDeltaRequest.model_construct(
        contract="ES",
        dataset="GLBX.MDP3",
        symbol="ES.c.0",
        stype_in="continuous",
        current_session_date=JsonDatabentoCumulativeDeltaRequestSource(_load_request_fixture())
        .load_es_request()
        .current_session_date,
        trades_schema="mbp-1",
    )
    source = DatabentoCumulativeDeltaSource(
        request=request,
        client_factory=_client_factory(_trade_records()),
    )

    with pytest.raises(PacketCompilerSourceError, match="trades_schema=trades"):
        source.load_es_cumulative_delta()
