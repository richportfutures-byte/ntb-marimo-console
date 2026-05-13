from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from ntb_marimo_console.live_observables import (
    LIVE_OBSERVABLE_SNAPSHOT_V2_SCHEMA,
    build_live_observable_snapshot_v2,
)
from ntb_marimo_console.market_data import ChartFuturesBarBuilder
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
EXPECTED_SYMBOLS = {
    "ES": "/ESM26",
    "NQ": "/NQM26",
    "CL": "/CLM26",
    "6E": "/6EM26",
    "MGC": "/MGCM26",
}


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


def chart_record(
    *,
    contract: str = "ES",
    symbol: str = "/ESM26",
    fields: tuple[tuple[str, object], ...] | None = None,
    fresh: bool = True,
    blocking_reasons: tuple[str, ...] = (),
) -> StreamCacheRecord:
    return StreamCacheRecord(
        provider="schwab",
        service="CHART_FUTURES",
        symbol=symbol,
        contract=contract,
        message_type="bar",
        fields=fields
        or (
            ("start_time", "2026-05-06T13:59:00+00:00"),
            ("end_time", "2026-05-06T14:00:00+00:00"),
            ("open", 7170.0),
            ("high", 7177.0),
            ("low", 7168.0),
            ("close", 7175.0),
            ("volume", 120),
            ("completed", True),
        ),
        updated_at="2026-05-06T14:00:00+00:00",
        age_seconds=0.0 if fresh else 120.0,
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
    assert payload["contracts"]["ES"]["chart_bar"]["available"] is False
    assert "chart_bars_missing:ES" in payload["contracts"]["ES"]["chart_bar"]["blocking_reasons"]


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
    assert es["quality"]["missing_fields"] == []


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
    assert es["sources"]["derived_source_status"]["bar_5m_close"] == "unavailable"
    assert es["sources"]["quality"]["required_fields_present"] == "level_one_required_field_check"


def test_missing_required_level_one_fields_block_required_fields() -> None:
    payload = build_live_observable_snapshot_v2(
        cache_snapshot(record=record(fields=(("quote_time", NOW.isoformat()),))),
        expected_symbols={"ES": "/ESM26"},
    ).to_dict()
    quality = payload["contracts"]["ES"]["quality"]

    assert quality["required_fields_present"] is False
    assert "bid" in quality["missing_fields"]
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


def test_missing_chart_bars_block_contract_and_snapshot_readiness() -> None:
    payload = build_live_observable_snapshot_v2(
        cache_snapshot(record=record()),
        expected_symbols={"ES": "/ESM26"},
        dependency_states=complete_dependency_states(),
    ).to_dict()
    es = payload["contracts"]["ES"]

    assert es["chart_bar"]["state"] == "unavailable"
    assert es["chart_bar"]["available"] is False
    assert "chart_bars_missing:ES" in es["chart_bar"]["blocking_reasons"]
    assert "ES:chart_bars_missing:ES" in payload["data_quality"]["blocking_reasons"]
    assert payload["data_quality"]["ready"] is False


def test_partial_chart_bars_do_not_satisfy_completed_bar_readiness() -> None:
    builder = ChartFuturesBarBuilder(expected_symbols=EXPECTED_SYMBOLS)
    for minute in range(4):
        builder.ingest(bar_message("ES", minute=minute))
    builder.ingest(bar_message("ES", minute=4, completed=False))

    payload = build_live_observable_snapshot_v2(
        cache_snapshot(record=record()),
        expected_symbols={"ES": "/ESM26"},
        bar_states={"ES": builder.state("ES")},
        dependency_states=complete_dependency_states(),
    ).to_dict()
    es = payload["contracts"]["ES"]

    assert es["chart_bar"]["state"] == "building"
    assert es["chart_bar"]["available"] is False
    assert "building_five_minute_bar_not_confirmation" in es["chart_bar"]["blocking_reasons"]
    assert payload["data_quality"]["ready"] is False


def test_chart_futures_bar_state_can_surface_completed_close_as_derived_metadata_only() -> None:
    builder = ChartFuturesBarBuilder(expected_symbols={"ES": "/ESM26"})
    for minute in range(5):
        start = NOW + timedelta(minutes=minute)
        builder.ingest(
            {
                "service": "CHART_FUTURES",
                "contract": "ES",
                "symbol": "/ESM26",
                "start_time": start.isoformat(),
                "end_time": (start + timedelta(minutes=1)).isoformat(),
                "open": 100.0 + minute,
                "high": 100.75 + minute,
                "low": 99.75 + minute,
                "close": 100.5 + minute,
                "completed": True,
            }
        )

    payload = build_live_observable_snapshot_v2(
        cache_snapshot(record=record()),
        expected_symbols={"ES": "/ESM26"},
        bar_states={"ES": builder.state("ES")},
        dependency_states=complete_dependency_states(),
    ).to_dict()
    es = payload["contracts"]["ES"]

    assert es["derived"]["bar_5m_close"] == 104.5
    assert es["sources"]["derived"]["bar_5m_close"] == "chart_futures_bar_contract"
    assert es["sources"]["derived_source_status"]["bar_5m_close"] == "derived_with_source"
    assert es["derived"]["bar_5m_close_count_at_or_beyond_level"] is None
    assert payload["data_quality"]["ready"] is False


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


def test_contract_dependencies_are_explicitly_unavailable_by_default() -> None:
    payload = build_live_observable_snapshot_v2(cache_snapshot(records=complete_records())).to_dict()

    assert payload["contracts"]["NQ"]["dependencies"]["relative_strength_vs_es"]["status"] == "unavailable"
    assert "dependency_unavailable:NQ:relative_strength_vs_es" in payload["contracts"]["NQ"]["quality"]["dependency_blocking_reasons"]
    assert payload["contracts"]["CL"]["dependencies"]["eia_lockout"]["status"] == "unavailable"
    assert "dependency_unavailable:CL:eia_lockout" in payload["contracts"]["CL"]["quality"]["dependency_blocking_reasons"]
    assert payload["contracts"]["6E"]["dependencies"]["dxy"]["status"] == "unavailable"
    assert "dependency_unavailable:6E:dxy" in payload["contracts"]["6E"]["quality"]["dependency_blocking_reasons"]
    assert payload["contracts"]["MGC"]["dependencies"]["cash_10y_yield"]["status"] == "unavailable"
    assert "dependency_unavailable:MGC:cash_10y_yield" in payload["contracts"]["MGC"]["quality"]["dependency_blocking_reasons"]
    assert payload["data_quality"]["ready"] is False


def test_eia_lockout_active_is_explicit_and_blocks_cl() -> None:
    dependencies = complete_dependency_states()
    dependencies["CL"] = {
        **dependencies["CL"],
        "eia_lockout": {"status": "lockout", "value": True, "source": "operator_fixture"},
    }

    payload = build_live_observable_snapshot_v2(
        cache_snapshot(records=complete_records()),
        expected_symbols=EXPECTED_SYMBOLS,
        bar_states=complete_bar_states(),
        dependency_states=dependencies,
    ).to_dict()

    assert payload["contracts"]["CL"]["dependencies"]["eia_lockout"]["status"] == "lockout"
    assert "dependency_lockout:CL:eia_lockout" in payload["contracts"]["CL"]["quality"]["dependency_blocking_reasons"]
    assert payload["data_quality"]["ready"] is False


def test_derived_dependency_without_source_blocks_readiness() -> None:
    dependencies = complete_dependency_states()
    dependencies["MGC"] = {
        **dependencies["MGC"],
        "dxy": {"status": "derived_without_source", "value": 102.0, "source": "display_row"},
    }

    payload = build_live_observable_snapshot_v2(
        cache_snapshot(records=complete_records()),
        expected_symbols=EXPECTED_SYMBOLS,
        bar_states=complete_bar_states(),
        dependency_states=dependencies,
    ).to_dict()

    assert payload["contracts"]["MGC"]["dependencies"]["dxy"]["status"] == "derived_without_source"
    assert "derived_without_source:MGC:dxy" in payload["contracts"]["MGC"]["quality"]["dependency_blocking_reasons"]
    assert payload["data_quality"]["ready"] is False


def test_snapshot_ready_requires_all_five_final_targets_complete_and_unblocked() -> None:
    payload = build_live_observable_snapshot_v2(
        cache_snapshot(records=complete_records()),
        expected_symbols=EXPECTED_SYMBOLS,
        bar_states=complete_bar_states(),
        dependency_states=complete_dependency_states(),
    ).to_dict()

    assert payload["data_quality"]["ready"] is True
    assert payload["data_quality"]["state"] == "ready"
    assert tuple(payload["data_quality"]["ready_contracts"]) == ("ES", "NQ", "CL", "6E", "MGC")
    assert payload["data_quality"]["blocking_reasons"] == []


def test_five_contract_complete_snapshot_serializes_cleanly() -> None:
    payload = build_live_observable_snapshot_v2(
        cache_snapshot(records=complete_records()),
        expected_symbols=EXPECTED_SYMBOLS,
        bar_states=complete_bar_states(),
        dependency_states=complete_dependency_states(),
    ).to_dict()

    decoded = json.loads(json.dumps(payload))

    assert tuple(decoded["contracts"].keys()) == ("ES", "NQ", "CL", "6E", "MGC")
    assert decoded["contracts"]["MGC"]["label"] == "Micro Gold"
    assert "GC" not in decoded["contracts"]
    for contract in ("ES", "NQ", "CL", "6E", "MGC"):
        assert decoded["contracts"][contract]["quality"]["fresh"] is True
        assert decoded["contracts"][contract]["chart_bar"]["available"] is True


def test_partial_es_quote_does_not_make_snapshot_ready() -> None:
    payload = build_live_observable_snapshot_v2(
        cache_snapshot(record=record()),
        expected_symbols={"ES": "/ESM26"},
    ).to_dict()

    assert payload["contracts"]["ES"]["quality"]["required_fields_present"] is True
    assert payload["data_quality"]["ready"] is False
    assert payload["data_quality"]["ready_contracts"] == []
    assert payload["data_quality"]["quote_ready_contracts"] == ["ES"]
    assert "ES:chart_bars_missing:ES" in payload["data_quality"]["blocking_reasons"]
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


def test_mixed_quote_and_chart_records_keep_quote_status_and_surface_chart_building() -> None:
    payload = build_live_observable_snapshot_v2(
        cache_snapshot(records=(chart_record(), record())),
    ).to_dict()
    es = payload["contracts"]["ES"]

    assert es["quote"]["bid"] == 7175.0
    assert es["quality"]["fresh"] is True
    assert es["chart_bar"]["state"] == "building"
    assert es["chart_bar"]["source"] == "chart_futures"
    assert es["chart_bar"]["completed_one_minute_available"] is True
    assert es["chart_bar"]["completed_five_minute_available"] is False
    assert "completed_five_minute_bars_unavailable" in es["chart_bar"]["blocking_reasons"]


def test_stale_and_malformed_chart_records_surface_chart_blocking_status_without_quote_loss() -> None:
    stale_payload = build_live_observable_snapshot_v2(
        cache_snapshot(records=(record(), chart_record(fresh=False))),
    ).to_dict()
    malformed_payload = build_live_observable_snapshot_v2(
        cache_snapshot(
            records=(
                record(),
                chart_record(fields=(("start_time", "2026-05-06T13:59:00+00:00"),)),
            )
        ),
    ).to_dict()

    assert stale_payload["contracts"]["ES"]["quality"]["fresh"] is True
    assert stale_payload["contracts"]["ES"]["chart_bar"]["state"] == "stale"
    assert "chart_bar_stale:ES" in stale_payload["contracts"]["ES"]["chart_bar"]["blocking_reasons"]
    assert malformed_payload["contracts"]["ES"]["chart_bar"]["state"] == "blocked"
    assert "malformed_chart_event:ES" in malformed_payload["contracts"]["ES"]["chart_bar"]["blocking_reasons"]


def complete_records() -> tuple[StreamCacheRecord, ...]:
    return (
        record(contract="ES", symbol="/ESM26"),
        record(contract="NQ", symbol="/NQM26"),
        record(contract="CL", symbol="/CLM26"),
        record(contract="6E", symbol="/6EM26"),
        record(contract="MGC", symbol="/MGCM26"),
    )


def complete_bar_states() -> dict[str, object]:
    return {contract: completed_bar_state(contract) for contract in EXPECTED_SYMBOLS}


def completed_bar_state(contract: str):
    builder = ChartFuturesBarBuilder(expected_symbols=EXPECTED_SYMBOLS)
    for minute in range(5):
        builder.ingest(bar_message(contract, minute=minute))
    return builder.state(contract)


def bar_message(contract: str, *, minute: int, completed: bool = True) -> dict[str, object]:
    start = NOW + timedelta(minutes=minute)
    return {
        "service": "CHART_FUTURES",
        "contract": contract,
        "symbol": EXPECTED_SYMBOLS[contract],
        "start_time": start.isoformat(),
        "end_time": (start + timedelta(minutes=1)).isoformat(),
        "open": 100.0 + minute,
        "high": 100.75 + minute,
        "low": 99.75 + minute,
        "close": 100.5 + minute,
        "volume": 100 + minute,
        "completed": completed,
    }


def complete_dependency_states() -> dict[str, dict[str, object]]:
    return {
        "ES": {
            "cumulative_delta": {"status": "available", "value": 1200.0, "source": "fixture"},
            "breadth": {
                "status": "available",
                "source": "fixture",
                "fields": {"current_advancers_pct": 0.61},
            },
        },
        "NQ": {
            "relative_strength_vs_es": {
                "status": "derived_with_source",
                "value": 0.002,
                "source": "fixture_level_one_nq_es",
                "source_status": "derived_with_source",
            },
        },
        "CL": {
            "eia_lockout": {"status": "available", "value": False, "source": "fixture_calendar"},
            "cumulative_delta": {"status": "available", "value": 820.0, "source": "fixture"},
            "current_volume_vs_average": {"status": "available", "value": 1.12, "source": "fixture"},
        },
        "6E": {
            "dxy": {
                "status": "derived_with_source",
                "value": 102.0,
                "source": "fixture_dxy_proxy",
                "source_status": "derived_with_source",
            },
            "session_sequence": {
                "status": "available",
                "source": "fixture_session_clock",
                "fields": {"asia_complete": True, "london_complete": True, "ny_pending": True},
            },
        },
        "MGC": {
            "dxy": {
                "status": "derived_with_source",
                "value": 102.0,
                "source": "fixture_dxy_proxy",
                "source_status": "derived_with_source",
            },
            "cash_10y_yield": {
                "status": "derived_with_source",
                "value": 4.1,
                "source": "fixture_yield_proxy",
                "source_status": "derived_with_source",
            },
            "fear_catalyst_state": {"status": "available", "value": "none", "source": "fixture_macro"},
        },
    }
