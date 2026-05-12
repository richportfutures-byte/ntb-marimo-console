from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ntb_marimo_console.live_observables import (
    LIVE_OBSERVABLE_SNAPSHOT_V2_SCHEMA,
    build_live_observable_snapshot_v2,
)
from ntb_marimo_console.market_data.stream_cache import (
    NormalizedStreamMessage,
    StreamCache,
    StreamCacheRecord,
    StreamCacheSnapshot,
)
from ntb_marimo_console.market_data.stream_manager import (
    SchwabStreamManager,
    SchwabStreamManagerConfig,
    StreamClientResult,
    StreamSubscriptionRequest,
)


NOW = datetime(2026, 5, 6, 14, 0, 0, tzinfo=timezone.utc)


@dataclass
class FakeClock:
    current: datetime = NOW

    def __call__(self) -> datetime:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current = self.current + timedelta(seconds=seconds)


class FakeStreamClient:
    def __init__(self) -> None:
        self.login_calls = 0
        self.subscription_calls = 0

    def login(self, config: SchwabStreamManagerConfig) -> StreamClientResult:
        self.login_calls += 1
        return StreamClientResult(succeeded=True)

    def subscribe(self, request: StreamSubscriptionRequest) -> StreamClientResult:
        self.subscription_calls += 1
        return StreamClientResult(succeeded=True)

    def close(self) -> StreamClientResult:
        return StreamClientResult(succeeded=True)


def cache_snapshot(
    *,
    provider_status: str = "active",
    record: StreamCacheRecord | None = None,
    records: tuple[StreamCacheRecord, ...] | None = None,
    blocking_reasons: tuple[str, ...] = (),
    stale_symbols: tuple[str, ...] = (),
) -> StreamCacheSnapshot:
    resolved_records = records if records is not None else (() if record is None else (record,))
    return StreamCacheSnapshot(
        generated_at=NOW.isoformat(),
        provider="schwab",
        provider_status=provider_status,  # type: ignore[arg-type]
        cache_max_age_seconds=15.0,
        records=resolved_records,
        blocking_reasons=blocking_reasons,
        stale_symbols=stale_symbols,
    )


def record(
    *,
    contract: str = "ES",
    symbol: str = "/ESM26",
    fields: tuple[tuple[str, object], ...] | None = None,
    updated_at: str = "2026-05-06T13:59:58+00:00",
    fresh: bool = True,
    blocking_reasons: tuple[str, ...] = (),
) -> StreamCacheRecord:
    return StreamCacheRecord(
        provider="schwab",
        service="LEVELONE_FUTURES",
        symbol=symbol,
        contract=contract,
        message_type="quote",
        fields=fields
        or (
            ("bid", 7175.0),
            ("ask", 7175.5),
            ("last", 7175.25),
            ("bid_size", 19),
            ("ask_size", 14),
            ("last_size", 3),
            ("quote_time", "2026-05-06T13:59:58+00:00"),
            ("trade_time", "2026-05-06T13:59:58+00:00"),
            ("volume", 180432),
            ("open", 7160.0),
            ("high", 7188.0),
            ("low", 7144.25),
            ("prior_close", 7158.5),
            ("tradable", True),
            ("active", True),
            ("security_status", "Normal"),
        ),
        updated_at=updated_at,
        age_seconds=2.0 if fresh else 120.0,
        fresh=fresh,
        blocking_reasons=blocking_reasons,
    )


def test_snapshot_includes_schema_provider_status_and_generated_at() -> None:
    snapshot = build_live_observable_snapshot_v2(cache_snapshot(record=record()))
    payload = snapshot.to_dict()

    assert payload["schema"] == LIVE_OBSERVABLE_SNAPSHOT_V2_SCHEMA
    assert payload["provider"] == "schwab"
    assert payload["provider_status"] == "connected"
    assert payload["generated_at"] == NOW.isoformat()
    assert tuple(payload.keys()) == (
        "schema",
        "generated_at",
        "provider",
        "provider_status",
        "contracts",
        "cross_asset",
        "macro_context",
        "session_context",
        "data_quality",
    )


def test_primary_contract_map_is_final_target_only() -> None:
    payload = build_live_observable_snapshot_v2(cache_snapshot(record=record())).to_dict()

    assert tuple(payload["contracts"].keys()) == ("ES", "NQ", "CL", "6E", "MGC")
    assert "ZN" not in payload["contracts"]
    assert "GC" not in payload["contracts"]
    assert payload["contracts"]["MGC"]["contract"] == "MGC"
    assert payload["contracts"]["MGC"]["label"] == "Micro Gold"
    assert payload["contracts"]["MGC"]["label"] != "GC"
    assert payload["contracts"]["ES"]["label"] is None


def test_missing_cache_default_disabled_input_fails_closed() -> None:
    payload = build_live_observable_snapshot_v2(clock=lambda: NOW).to_dict()

    assert payload["provider"] == "disabled"
    assert payload["provider_status"] == "disabled"
    assert payload["data_quality"]["ready"] is False
    assert "cache_snapshot_missing" in payload["data_quality"]["blocking_reasons"]
    assert payload["contracts"]["ES"]["quality"]["fresh"] is False
    assert payload["contracts"]["ES"]["quality"]["required_fields_present"] is False


def test_complete_fixture_quote_sets_required_fields_present_for_contract() -> None:
    payload = build_live_observable_snapshot_v2(
        cache_snapshot(record=record()),
        expected_symbols={"ES": "/ESM26"},
    ).to_dict()
    es = payload["contracts"]["ES"]

    assert es["quality"]["required_fields_present"] is True
    assert es["quality"]["fresh"] is True
    assert es["quality"]["symbol_match"] is True
    assert es["quote"]["bid"] == 7175.0
    assert es["quote"]["ask"] == 7175.5
    assert es["quote"]["last"] == 7175.25
    assert es["quote"]["bid_size"] == 19
    assert es["quote"]["ask_size"] == 14
    assert es["session"]["volume"] == 180432
    assert es["session"]["open"] == 7160.0
    assert es["session"]["high"] == 7188.0
    assert es["session"]["low"] == 7144.25
    assert es["session"]["prior_close"] == 7158.5
    assert es["session"]["tradable"] is True
    assert es["session"]["active"] is True
    assert es["session"]["security_status"] == "Normal"


def test_numeric_level_one_field_ids_map_to_required_observables() -> None:
    timestamp_ms = int(datetime(2026, 5, 6, 13, 59, 58, tzinfo=timezone.utc).timestamp() * 1000)
    payload = build_live_observable_snapshot_v2(
        cache_snapshot(
            record=record(
                fields=(
                    ("1", 7175.0),
                    ("2", 7175.5),
                    ("3", 7175.25),
                    ("4", 19),
                    ("5", 14),
                    ("8", 180432),
                    ("10", timestamp_ms),
                    ("11", timestamp_ms),
                    ("12", 7188.0),
                    ("13", 7144.25),
                    ("14", 7158.5),
                    ("18", 7160.0),
                    ("22", "Normal"),
                    ("30", True),
                    ("32", True),
                ),
            )
        ),
        expected_symbols={"ES": "/ESM26"},
    ).to_dict()
    es = payload["contracts"]["ES"]

    assert es["quality"]["required_fields_present"] is True
    assert es["quote"]["quote_time"] == "2026-05-06T13:59:58+00:00"
    assert es["quote"]["trade_time"] == "2026-05-06T13:59:58+00:00"
    assert es["session"]["volume"] == 180432
    assert es["session"]["security_status"] == "Normal"


def test_contract_observable_includes_source_labels() -> None:
    payload = build_live_observable_snapshot_v2(
        cache_snapshot(record=record()),
        expected_symbols={"ES": "/ESM26"},
    ).to_dict()
    es = payload["contracts"]["ES"]

    assert es["sources"]["quote"]["bid"] == "stream_cache_level_one"
    assert es["sources"]["quote"]["quote_time"] == "stream_cache_level_one"
    assert es["sources"]["session"]["volume"] == "stream_cache_level_one"
    assert es["sources"]["derived"]["mid"] == "derived_from_level_one_quote"
    assert es["sources"]["derived"]["bar_5m_close"] == "unavailable_until_chart_futures"
    assert es["sources"]["quality"]["required_fields_present"] == "level_one_required_field_check"


def test_missing_required_level_one_fields_block_required_fields() -> None:
    payload = build_live_observable_snapshot_v2(
        cache_snapshot(record=record(fields=(("quote_time", NOW.isoformat()),))),
        expected_symbols={"ES": "/ESM26"},
    ).to_dict()
    quality = payload["contracts"]["ES"]["quality"]

    assert quality["required_fields_present"] is False
    reason = next(reason for reason in quality["blocking_reasons"] if reason.startswith("missing_required_fields:ES:"))
    for field_name in (
        "bid",
        "ask",
        "last",
        "bid_size",
        "ask_size",
        "trade_time",
        "volume",
        "open",
        "high",
        "low",
        "prior_close",
        "tradable",
        "active",
        "security_status",
    ):
        assert field_name in reason


def test_quote_and_trade_times_must_be_observed_not_filled_from_record_updated_at() -> None:
    payload = build_live_observable_snapshot_v2(
        cache_snapshot(
            record=record(
                fields=(
                    ("bid", 7175.0),
                    ("ask", 7175.5),
                    ("last", 7175.25),
                    ("bid_size", 19),
                    ("ask_size", 14),
                    ("volume", 180432),
                    ("open", 7160.0),
                    ("high", 7188.0),
                    ("low", 7144.25),
                    ("prior_close", 7158.5),
                    ("tradable", True),
                    ("active", True),
                    ("security_status", "Normal"),
                ),
                updated_at="2026-05-06T13:59:58+00:00",
            )
        ),
        expected_symbols={"ES": "/ESM26"},
    ).to_dict()
    es = payload["contracts"]["ES"]

    assert es["quote"]["quote_time"] is None
    assert es["quote"]["trade_time"] is None
    assert es["sources"]["quote"]["quote_time"] == "unavailable"
    assert es["quality"]["required_fields_present"] is False
    assert "missing_required_fields:ES:quote_time,trade_time" in es["quality"]["blocking_reasons"]


def test_stale_quote_trade_or_cache_timestamps_block_freshness() -> None:
    payload = build_live_observable_snapshot_v2(
        cache_snapshot(
            provider_status="stale",
            record=record(
                updated_at="2026-05-06T13:58:00+00:00",
                fields=(
                    ("bid", 7175.0),
                    ("ask", 7175.5),
                    ("last", 7175.25),
                    ("quote_time", "2026-05-06T13:58:00+00:00"),
                    ("trade_time", "2026-05-06T13:58:00+00:00"),
                ),
                fresh=False,
            ),
            stale_symbols=("/ESM26",),
        ),
        expected_symbols={"ES": "/ESM26"},
    ).to_dict()
    quality = payload["contracts"]["ES"]["quality"]

    assert payload["provider_status"] == "stale"
    assert quality["fresh"] is False
    assert "provider_stale" in quality["blocking_reasons"]
    assert "stale_or_missing_timestamp:ES" in quality["blocking_reasons"]
    assert "cache_stale_symbol:/ESM26" in payload["data_quality"]["blocking_reasons"]


def test_provider_error_disconnected_and_stale_propagate_blocking_reasons() -> None:
    for status, expected in (
        ("error", "provider_error"),
        ("blocked", "provider_disconnected"),
        ("shutdown", "provider_disconnected"),
        ("stale", "provider_stale"),
    ):
        payload = build_live_observable_snapshot_v2(cache_snapshot(provider_status=status, record=record())).to_dict()
        assert expected in payload["data_quality"]["blocking_reasons"]
        assert expected in payload["contracts"]["ES"]["quality"]["blocking_reasons"]


def test_symbol_mismatch_blocks_affected_contract() -> None:
    payload = build_live_observable_snapshot_v2(
        cache_snapshot(record=record(symbol="/NQM26")),
        expected_symbols={"ES": "/ESM26"},
    ).to_dict()
    quality = payload["contracts"]["ES"]["quality"]

    assert quality["symbol_match"] is False
    assert "symbol_mismatch:ES:/NQM26" in quality["blocking_reasons"]


def test_mid_and_spread_ticks_compute_only_when_numeric_and_tick_size_available() -> None:
    es_payload = build_live_observable_snapshot_v2(cache_snapshot(record=record())).to_dict()
    es_derived = es_payload["contracts"]["ES"]["derived"]

    assert es_derived["mid"] == 7175.25
    assert es_derived["spread_ticks"] == 2.0

    missing_payload = build_live_observable_snapshot_v2(
        cache_snapshot(record=record(fields=(("bid", 7175.0), ("last", 7175.25), ("quote_time", NOW.isoformat()))))
    ).to_dict()
    missing_derived = missing_payload["contracts"]["ES"]["derived"]

    assert missing_derived["mid"] is None
    assert missing_derived["spread_ticks"] is None


def test_r04_bar_and_trigger_derived_fields_remain_null() -> None:
    derived = build_live_observable_snapshot_v2(cache_snapshot(record=record())).to_dict()["contracts"]["ES"]["derived"]

    assert derived["distance_to_primary_trigger_ticks"] is None
    assert derived["bar_5m_close"] is None
    assert derived["bar_5m_close_count_at_or_beyond_level"] is None
    assert derived["range_expansion_state"] is None
    assert derived["volume_velocity_state"] is None


def test_cache_read_snapshot_builder_does_not_start_login_or_subscription() -> None:
    client = FakeStreamClient()
    manager = SchwabStreamManager(
        SchwabStreamManagerConfig(
            provider="schwab",
            services_requested=("LEVELONE_FUTURES",),
            symbols_requested=("/ESM26",),
            fields_requested=(0, 1, 2, 3, 4, 5),
            contracts_requested=("ES",),
            explicit_live_opt_in=True,
        ),
        client=client,
        clock=FakeClock(),
    )
    manager.start()
    manager.ingest_message(
        {
            "service": "LEVELONE_FUTURES",
            "symbol": "/ESM26",
            "contract": "ES",
            "message_type": "quote",
            "fields": {"bid": 7175.0, "ask": 7175.5, "last": 7175.25},
            "received_at": NOW.isoformat(),
        }
    )

    for _ in range(3):
        build_live_observable_snapshot_v2(manager.read_cache_snapshot())

    assert client.login_calls == 1
    assert client.subscription_calls == 1


def test_snapshot_is_json_serializable() -> None:
    payload = build_live_observable_snapshot_v2(cache_snapshot(record=record())).to_dict()

    encoded = json.dumps(payload, sort_keys=True)

    assert "live_observable_snapshot_v2" in encoded


def test_cross_asset_macro_and_session_contexts_are_unavailable_not_inferred() -> None:
    payload = build_live_observable_snapshot_v2(cache_snapshot(record=record())).to_dict()

    assert payload["cross_asset"]["dxy"] == {"source": "unavailable", "value": None}
    assert payload["cross_asset"]["yield_context"] == {"source": "unavailable", "value": None}
    assert payload["cross_asset"]["es_relative_strength"] == {"source": "unavailable", "value": None}
    assert payload["macro_context"]["event_lockout"] == {"source": "unavailable", "value": None}
    assert payload["session_context"]["session_sequence"] == {"source": "unavailable", "value": None}
    assert "dxy" not in payload["contracts"]["ES"]["derived"]
    assert "event_lockout" not in payload["contracts"]["ES"]["quality"]


def test_snapshot_ready_requires_all_five_final_targets_complete_and_unblocked() -> None:
    records = (
        record(contract="ES", symbol="/ESM26"),
        record(contract="NQ", symbol="/NQM26"),
        record(contract="CL", symbol="/CLM26"),
        record(contract="6E", symbol="/6EM26"),
        record(contract="MGC", symbol="/MGCM26"),
    )

    payload = build_live_observable_snapshot_v2(
        cache_snapshot(records=records),
        expected_symbols={
            "ES": "/ESM26",
            "NQ": "/NQM26",
            "CL": "/CLM26",
            "6E": "/6EM26",
            "MGC": "/MGCM26",
        },
    ).to_dict()

    assert payload["data_quality"]["ready"] is True
    assert payload["data_quality"]["state"] == "ready"
    assert tuple(payload["data_quality"]["ready_contracts"]) == ("ES", "NQ", "CL", "6E", "MGC")
    assert payload["data_quality"]["blocking_reasons"] == []


def test_partial_es_quote_does_not_make_snapshot_ready() -> None:
    payload = build_live_observable_snapshot_v2(
        cache_snapshot(record=record()),
        expected_symbols={"ES": "/ESM26"},
    ).to_dict()

    assert payload["contracts"]["ES"]["quality"]["required_fields_present"] is True
    assert payload["data_quality"]["ready"] is False
    assert payload["data_quality"]["ready_contracts"] == ["ES"]
    for missing_contract in ("NQ", "CL", "6E", "MGC"):
        assert f"{missing_contract}:missing_cache_record:{missing_contract}" in payload["data_quality"]["blocking_reasons"]


def test_builder_accepts_stream_cache_snapshot_without_network_side_effects() -> None:
    cache = StreamCache(provider="schwab", cache_max_age_seconds=15.0, clock=lambda: NOW)
    cache.set_provider_status("active")
    cache.put_message(
        NormalizedStreamMessage(
            provider="schwab",
            service="LEVELONE_FUTURES",
            symbol="/ESM26",
            contract="ES",
            message_type="quote",
            fields={
                "bid": 7175.0,
                "ask": 7175.5,
                "last": 7175.25,
                "bid_size": 19,
                "ask_size": 14,
                "quote_time": "2026-05-06T13:59:58+00:00",
                "trade_time": "2026-05-06T13:59:58+00:00",
                "volume": 180432,
                "open": 7160.0,
                "high": 7188.0,
                "low": 7144.25,
                "prior_close": 7158.5,
                "tradable": True,
                "active": True,
                "security_status": "Normal",
            },
            received_at="2026-05-06T13:59:58+00:00",
        )
    )

    payload = build_live_observable_snapshot_v2(cache.snapshot()).to_dict()

    assert payload["contracts"]["ES"]["quality"]["required_fields_present"] is True
    assert payload["contracts"]["ES"]["quality"]["fresh"] is True
