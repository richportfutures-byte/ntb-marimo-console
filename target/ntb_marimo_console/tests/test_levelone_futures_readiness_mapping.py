from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Mapping

from ntb_marimo_console.contract_universe import final_target_contracts
from ntb_marimo_console.live_observables import build_live_observable_snapshot_v2
from ntb_marimo_console.market_data.stream_manager import (
    SchwabStreamManager,
    SchwabStreamManagerConfig,
    StreamClientResult,
)
from ntb_marimo_console.readiness_summary import (
    LIVE_RUNTIME_CONNECTED,
    LIVE_RUNTIME_MISSING_REQUIRED_FIELDS,
    build_five_contract_readiness_summary_surface,
)
from ntb_marimo_console.schwab_client_factory_builder import build_default_live_stream_config
from ntb_marimo_console.schwab_streamer_session import (
    DEFAULT_LEVELONE_FUTURES_FIELD_IDS,
    LEVELONE_FUTURES_READINESS_FIELD_IDS,
    extract_data_entries,
)


NOW = datetime(2026, 5, 15, 14, 0, 0, tzinfo=timezone.utc)
NOW_ISO = NOW.isoformat()
NOW_MILLIS = int(NOW.timestamp() * 1000)
SYMBOL_BY_CONTRACT = {
    "ES": "/ESM26",
    "NQ": "/NQM26",
    "CL": "/CLM26",
    "6E": "/6EM26",
    "MGC": "/MGCM26",
}


class FakeStreamClient:
    def login(self, config: SchwabStreamManagerConfig) -> StreamClientResult:
        return StreamClientResult(succeeded=True)

    def subscribe(self, request: object) -> StreamClientResult:
        return StreamClientResult(succeeded=True)

    def close(self) -> StreamClientResult:
        return StreamClientResult(succeeded=True)


def _manager() -> SchwabStreamManager:
    manager = SchwabStreamManager(
        SchwabStreamManagerConfig(
            provider="schwab",
            services_requested=("LEVELONE_FUTURES", "CHART_FUTURES"),
            symbols_requested=tuple(SYMBOL_BY_CONTRACT[contract] for contract in final_target_contracts()),
            fields_requested=DEFAULT_LEVELONE_FUTURES_FIELD_IDS,
            contracts_requested=final_target_contracts(),
            explicit_live_opt_in=True,
        ),
        client=FakeStreamClient(),
        clock=lambda: NOW,
    )
    manager.start()
    return manager


def _levelone_frame(fields: Mapping[str, object], *, symbol: str = "/ESM26") -> str:
    content = {"key": symbol, **dict(fields)}
    return json.dumps(
        {
            "data": [
                {
                    "service": "LEVELONE_FUTURES",
                    "command": "SUBS",
                    "timestamp": NOW_MILLIS,
                    "content": [content],
                }
            ]
        }
    )


def _complete_levelone_fields() -> dict[str, object]:
    return {
        "0": "/ESM26",
        "1": 100.0,
        "2": 100.25,
        "3": 100.125,
        "4": 10,
        "5": 12,
        "8": 25_000,
        "10": NOW_MILLIS,
        "11": NOW_MILLIS,
        "12": 101.0,
        "13": 98.75,
        "14": 99.25,
        "18": 99.5,
        "22": "Normal",
        "30": "true",
        "32": 1,
    }


def test_default_live_stream_requests_levelone_readiness_fields() -> None:
    required_field_ids = {
        0,  # symbol
        1,  # bid
        2,  # ask
        3,  # last
        4,  # bid size
        5,  # ask size
        8,  # total volume
        10,  # quote time
        11,  # trade time
        12,  # high
        13,  # low
        14,  # prior/close
        18,  # open
        22,  # security status
        30,  # tradable
        32,  # active
    }

    assert DEFAULT_LEVELONE_FUTURES_FIELD_IDS == LEVELONE_FUTURES_READINESS_FIELD_IDS
    assert set(DEFAULT_LEVELONE_FUTURES_FIELD_IDS) == required_field_ids
    assert build_default_live_stream_config({}).fields_requested == DEFAULT_LEVELONE_FUTURES_FIELD_IDS


def test_schwab_levelone_numeric_fields_map_into_normalized_readiness_model() -> None:
    entries = extract_data_entries(_levelone_frame(_complete_levelone_fields()))

    assert len(entries) == 1
    entry = entries[0]
    fields = entry["fields"]
    assert isinstance(fields, dict)
    assert fields["1"] == fields["bid"]
    assert fields["2"] == fields["ask"]
    assert fields["3"] == fields["last"]
    assert fields["4"] == fields["bid_size"]
    assert fields["5"] == fields["ask_size"]
    assert fields["8"] == fields["volume"]
    assert fields["10"] == fields["quote_time"]
    assert fields["11"] == fields["trade_time"]
    assert fields["12"] == fields["high"]
    assert fields["13"] == fields["low"]
    assert fields["14"] == fields["prior_close"]
    assert fields["18"] == fields["open"]
    assert fields["22"] == fields["security_status"]
    assert fields["30"] == fields["tradable"]
    assert fields["32"] == fields["active"]

    manager = _manager()
    snapshot = manager.ingest_message(entry)
    observable = build_live_observable_snapshot_v2(snapshot.cache).to_dict()
    es = observable["contracts"]["ES"]

    assert es["quote"]["bid"] == 100.0
    assert es["quote"]["ask"] == 100.25
    assert es["quote"]["last"] == 100.125
    assert es["quote"]["quote_time"] == NOW_ISO
    assert es["quote"]["trade_time"] == NOW_ISO
    assert es["session"]["volume"] == 25_000
    assert es["session"]["open"] == 99.5
    assert es["session"]["high"] == 101.0
    assert es["session"]["low"] == 98.75
    assert es["session"]["prior_close"] == 99.25
    assert es["session"]["security_status"] == "Normal"
    assert es["session"]["tradable"] is True
    assert es["session"]["active"] is True
    assert es["quality"]["required_fields_present"] is True

    surface = build_five_contract_readiness_summary_surface(runtime_snapshot=snapshot)
    rows = {row["contract"]: row for row in surface["rows"]}
    es_row = rows["ES"]

    assert surface["runtime_cache_provider_status"] == "connected"
    assert surface["runtime_quote_path_active"] is True
    assert tuple(surface["runtime_levelone_active_contracts"]) == ("ES",)
    assert tuple(surface["runtime_chart_active_contracts"]) == ()
    assert es_row["live_runtime_readiness_state"] == LIVE_RUNTIME_CONNECTED
    assert es_row["live_data_available"] is True
    assert es_row["quote_status"] == "quote available"
    assert es_row["chart_status"] == "chart missing"
    assert "chart_bars_missing:ES" in es_row["chart_blocking_reasons"]
    assert es_row["query_ready"] is False
    assert es_row["query_gate_status"] == "BLOCKED"


def test_missing_levelone_readiness_fields_remain_explicit_and_fail_closed() -> None:
    entries = extract_data_entries(
        _levelone_frame(
            {
                "0": "/ESM26",
                "1": 100.0,
                "2": 100.25,
                "3": 100.125,
                "4": 10,
                "5": 12,
            }
        )
    )
    manager = _manager()
    snapshot = manager.ingest_message(entries[0])

    observable = build_live_observable_snapshot_v2(snapshot.cache).to_dict()
    es = observable["contracts"]["ES"]
    assert es["quality"]["required_fields_present"] is False
    assert es["sources"]["session"]["volume"] == "unavailable"
    assert es["sources"]["session"]["tradable"] == "unavailable"
    assert set(es["quality"]["missing_fields"]) >= {
        "quote_time",
        "trade_time",
        "volume",
        "open",
        "high",
        "low",
        "prior_close",
        "tradable",
        "active",
        "security_status",
    }

    surface = build_five_contract_readiness_summary_surface(runtime_snapshot=snapshot)
    rows = {row["contract"]: row for row in surface["rows"]}
    es_row = rows["ES"]

    assert surface["runtime_cache_provider_status"] == "connected"
    assert surface["runtime_quote_path_active"] is True
    assert es_row["live_runtime_readiness_state"] == LIVE_RUNTIME_MISSING_REQUIRED_FIELDS
    assert es_row["live_data_available"] is False
    assert es_row["query_ready"] is False
    assert set(es_row["missing_live_fields"]) >= set(es["quality"]["missing_fields"])
    assert any(
        reason.startswith("missing_required_fields:ES:")
        for reason in es_row["runtime_cache_blocked_reasons"]
    )
