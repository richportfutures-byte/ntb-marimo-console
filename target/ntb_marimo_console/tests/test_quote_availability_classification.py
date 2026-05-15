"""Focused tests for live cockpit quote availability classification.

Proves the classification seam between core quote fields (bid/ask/last/sizes/times)
and session/reference fields (open/high/low/prior_close/tradable/active/security_status)
works correctly: quote availability depends on core fields only, session field gaps
remain visible as explicit blockers without making the whole quote/provider unavailable.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from ntb_marimo_console.contract_universe import final_target_contracts
from ntb_marimo_console.live_observables import build_live_observable_snapshot_v2
from ntb_marimo_console.live_observables.builder import (
    REQUIRED_QUOTE_FIELDS,
    REQUIRED_SESSION_FIELDS,
)
from ntb_marimo_console.market_data.stream_manager import (
    SchwabStreamManager,
    SchwabStreamManagerConfig,
    StreamClientResult,
)
from ntb_marimo_console.primary_cockpit import (
    LIVE_OBSERVATION_MODE_CONNECTED,
    LIVE_OBSERVATION_MODE_FAIL_CLOSED,
    build_live_observation_cockpit_surface,
)
from ntb_marimo_console.readiness_summary import (
    LIVE_RUNTIME_CONNECTED,
    LIVE_RUNTIME_MISSING_REQUIRED_FIELDS,
    build_five_contract_readiness_summary,
    build_five_contract_readiness_summary_surface,
)
from ntb_marimo_console.schwab_streamer_session import (
    DEFAULT_LEVELONE_FUTURES_FIELD_IDS,
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
            symbols_requested=tuple(SYMBOL_BY_CONTRACT[c] for c in final_target_contracts()),
            fields_requested=DEFAULT_LEVELONE_FUTURES_FIELD_IDS,
            contracts_requested=final_target_contracts(),
            explicit_live_opt_in=True,
        ),
        client=FakeStreamClient(),
        clock=lambda: NOW,
    )
    manager.start()
    return manager


def _levelone_frame(fields: dict[str, object], *, symbol: str) -> str:
    content = {"key": symbol, **fields}
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


def _core_quote_only_fields(*, symbol: str) -> dict[str, object]:
    """Core quote fields only — no session/reference fields."""
    return {
        "0": symbol,
        "1": 100.0,       # bid
        "2": 100.25,      # ask
        "3": 100.125,     # last
        "4": 10,          # bid_size
        "5": 12,          # ask_size
        "10": NOW_MILLIS, # quote_time
        "11": NOW_MILLIS, # trade_time
    }


def _core_quote_missing_ask(*, symbol: str) -> dict[str, object]:
    """Core quote fields minus ask — simulates genuinely absent ask."""
    return {
        "0": symbol,
        "1": 100.0,       # bid
        "3": 100.125,     # last
        "4": 10,          # bid_size
        "5": 12,          # ask_size
        "10": NOW_MILLIS, # quote_time
        "11": NOW_MILLIS, # trade_time
    }


def _complete_fields(*, symbol: str) -> dict[str, object]:
    """All required fields — core quote + session/reference."""
    return {
        "0": symbol,
        "1": 100.0,       # bid
        "2": 100.25,      # ask
        "3": 100.125,     # last
        "4": 10,          # bid_size
        "5": 12,          # ask_size
        "8": 25_000,      # volume
        "10": NOW_MILLIS, # quote_time
        "11": NOW_MILLIS, # trade_time
        "12": 101.0,      # high
        "13": 98.75,      # low
        "14": 99.25,      # prior_close
        "18": 99.5,       # open
        "22": "Normal",   # security_status
        "30": "true",     # tradable
        "32": 1,          # active
    }


def _ingest_all_contracts(manager: SchwabStreamManager, field_fn) -> object:
    """Ingest one LEVELONE frame per contract, return last snapshot."""
    snapshot = None
    for contract in final_target_contracts():
        symbol = SYMBOL_BY_CONTRACT[contract]
        entries = extract_data_entries(_levelone_frame(field_fn(symbol=symbol), symbol=symbol))
        for entry in entries:
            snapshot = manager.ingest_message(entry)
    return snapshot


# -----------------------------------------------------------------------
# Core tests: quote availability classification
# -----------------------------------------------------------------------


def test_core_quote_present_session_missing_gives_quote_available() -> None:
    """When core quote fields are present but session fields are missing,
    quote_status must be 'quote available' — not 'quote missing'."""
    manager = _manager()
    snapshot = _ingest_all_contracts(manager, _core_quote_only_fields)

    observable = build_live_observable_snapshot_v2(snapshot.cache).to_dict()
    es = observable["contracts"]["ES"]
    assert es["quality"]["core_quote_fields_present"] is True
    assert es["quality"]["required_fields_present"] is False

    surface = build_five_contract_readiness_summary_surface(runtime_snapshot=snapshot)
    rows = {row["contract"]: row for row in surface["rows"]}
    for contract in final_target_contracts():
        row = rows[contract]
        assert row["quote_status"] == "quote available", f"{contract}: expected quote available"
        assert row["live_runtime_readiness_state"] == LIVE_RUNTIME_CONNECTED, f"{contract}: expected CONNECTED"
        assert row["live_data_available"] is True, f"{contract}: expected live_data_available"
        assert row["quote_freshness_state"] == "fresh", f"{contract}: expected fresh"


def test_core_quote_present_session_missing_blockers_remain_visible() -> None:
    """Session field gaps must remain visible as explicit blockers
    even when quote_status is 'quote available'."""
    manager = _manager()
    snapshot = _ingest_all_contracts(manager, _core_quote_only_fields)

    surface = build_five_contract_readiness_summary_surface(runtime_snapshot=snapshot)
    rows = {row["contract"]: row for row in surface["rows"]}
    for contract in final_target_contracts():
        row = rows[contract]
        missing = set(row["missing_live_fields"])
        assert missing >= set(REQUIRED_SESSION_FIELDS), (
            f"{contract}: session fields must remain in missing_live_fields"
        )
        assert any(
            reason.startswith(f"missing_required_fields:{contract}:")
            for reason in row["runtime_cache_blocked_reasons"]
        ), f"{contract}: missing session field reasons must be in runtime_cache_blocked_reasons"


def test_missing_ask_remains_explicit_blocker() -> None:
    """When ask is genuinely absent, the contract must remain
    LIVE_RUNTIME_MISSING_REQUIRED_FIELDS with 'quote missing'."""
    manager = _manager()

    # Ingest ES with missing ask, all others with full core
    for contract in final_target_contracts():
        symbol = SYMBOL_BY_CONTRACT[contract]
        if contract == "ES":
            fields = _core_quote_missing_ask(symbol=symbol)
        else:
            fields = _core_quote_only_fields(symbol=symbol)
        entries = extract_data_entries(_levelone_frame(fields, symbol=symbol))
        for entry in entries:
            manager.ingest_message(entry)

    snapshot = manager.snapshot()
    surface = build_five_contract_readiness_summary_surface(runtime_snapshot=snapshot)
    rows = {row["contract"]: row for row in surface["rows"]}

    es_row = rows["ES"]
    assert es_row["quote_status"] == "quote missing"
    assert es_row["live_runtime_readiness_state"] == LIVE_RUNTIME_MISSING_REQUIRED_FIELDS
    assert es_row["live_data_available"] is False
    assert "ask" in es_row["missing_live_fields"]

    nq_row = rows["NQ"]
    assert nq_row["quote_status"] == "quote available"
    assert nq_row["live_runtime_readiness_state"] == LIVE_RUNTIME_CONNECTED


def test_mapped_ask_consumed_correctly_when_present() -> None:
    """Field '2' must map to 'ask' and be consumed as a core quote field."""
    entries = extract_data_entries(
        _levelone_frame(_core_quote_only_fields(symbol="/ESM26"), symbol="/ESM26")
    )
    assert len(entries) == 1
    fields = entries[0]["fields"]
    assert fields["2"] == fields["ask"] == 100.25


# -----------------------------------------------------------------------
# Provider / chart / quote independence
# -----------------------------------------------------------------------


def test_provider_active_chart_building_does_not_force_quote_missing() -> None:
    """Provider active + chart building must NOT force quote_status to 'quote missing'.
    Quote and chart are independent classification dimensions."""
    manager = _manager()
    snapshot = _ingest_all_contracts(manager, _core_quote_only_fields)

    surface = build_five_contract_readiness_summary_surface(runtime_snapshot=snapshot)
    rows = {row["contract"]: row for row in surface["rows"]}
    for contract in final_target_contracts():
        row = rows[contract]
        assert row["quote_status"] == "quote available"
        assert row["chart_status"] in {"chart missing", "chart building"}
        assert surface["runtime_cache_provider_status"] in {"connected", "active"}


def test_chart_building_separate_from_quote_freshness() -> None:
    """chart_freshness_state must not affect quote_freshness_state."""
    manager = _manager()
    snapshot = _ingest_all_contracts(manager, _core_quote_only_fields)

    surface = build_five_contract_readiness_summary_surface(runtime_snapshot=snapshot)
    rows = {row["contract"]: row for row in surface["rows"]}
    for contract in final_target_contracts():
        row = rows[contract]
        assert row["quote_freshness_state"] == "fresh"
        assert row["chart_freshness_state"] == "missing"


def test_complete_fields_still_connected_and_quote_available() -> None:
    """Full fields must still produce CONNECTED + quote available (no regression)."""
    manager = _manager()
    snapshot = _ingest_all_contracts(manager, _complete_fields)

    surface = build_five_contract_readiness_summary_surface(runtime_snapshot=snapshot)
    rows = {row["contract"]: row for row in surface["rows"]}
    for contract in final_target_contracts():
        row = rows[contract]
        assert row["live_runtime_readiness_state"] == LIVE_RUNTIME_CONNECTED
        assert row["quote_status"] == "quote available"
        assert row["live_data_available"] is True
        assert not row["missing_live_fields"]


# -----------------------------------------------------------------------
# QUERY_READY boundary enforcement
# -----------------------------------------------------------------------


def test_query_remains_blocked_with_chart_building() -> None:
    """query_ready must remain False when chart is building/missing,
    even if quote is available."""
    manager = _manager()
    snapshot = _ingest_all_contracts(manager, _core_quote_only_fields)

    surface = build_five_contract_readiness_summary_surface(runtime_snapshot=snapshot)
    rows = {row["contract"]: row for row in surface["rows"]}
    for contract in final_target_contracts():
        row = rows[contract]
        assert row["query_ready"] is False
        assert row["query_gate_status"] == "BLOCKED"


def test_display_viewmodel_cannot_create_query_ready() -> None:
    """The cockpit surface must not produce query_enabled=True when the
    readiness summary has query_ready=False."""
    manager = _manager()
    snapshot = _ingest_all_contracts(manager, _core_quote_only_fields)

    summary = build_five_contract_readiness_summary(runtime_snapshot=snapshot)
    surface = build_live_observation_cockpit_surface(
        readiness_summary=summary.to_dict(),
        operator_live_runtime={
            "cache_provider_status": "connected",
            "cache_snapshot_ready": True,
            "cache_generated_at": NOW_ISO,
            "blocking_reasons": [],
        },
    )

    for row in surface["rows"]:
        assert row["query_enabled"] is False
        assert row["query_action_state"] == "DISABLED"
        assert row["query_ready_provenance"] != "real_trigger_state_result_and_pipeline_gate"


def test_stale_state_cannot_produce_query_ready() -> None:
    """A stale cache must not produce query_ready=True."""
    manager = _manager()
    # Don't ingest anything — stale/empty cache
    snapshot = manager.snapshot()

    surface = build_five_contract_readiness_summary_surface(runtime_snapshot=snapshot)
    rows = {row["contract"]: row for row in surface["rows"]}
    for contract in final_target_contracts():
        row = rows[contract]
        assert row["query_ready"] is False


# -----------------------------------------------------------------------
# Cockpit mode classification
# -----------------------------------------------------------------------


def test_cockpit_connected_mode_with_core_quote_present() -> None:
    """Cockpit must show CONNECTED mode when all contracts have core quote fields,
    even if session fields are missing."""
    manager = _manager()
    snapshot = _ingest_all_contracts(manager, _core_quote_only_fields)

    summary = build_five_contract_readiness_summary(runtime_snapshot=snapshot)
    surface = build_live_observation_cockpit_surface(
        readiness_summary=summary.to_dict(),
        operator_live_runtime={
            "cache_provider_status": "connected",
            "cache_snapshot_ready": summary.runtime_cache_snapshot_ready,
            "cache_generated_at": NOW_ISO,
            "blocking_reasons": [],
        },
    )

    assert surface["mode"] == LIVE_OBSERVATION_MODE_CONNECTED


def test_cockpit_fail_closed_mode_with_core_quote_missing() -> None:
    """Cockpit must show FAIL_CLOSED mode when core quote fields are missing."""
    manager = _manager()
    # Ingest ES with missing ask — core fields incomplete
    symbol = SYMBOL_BY_CONTRACT["ES"]
    entries = extract_data_entries(
        _levelone_frame(_core_quote_missing_ask(symbol=symbol), symbol=symbol)
    )
    for entry in entries:
        manager.ingest_message(entry)

    snapshot = manager.snapshot()
    summary = build_five_contract_readiness_summary(runtime_snapshot=snapshot)
    surface = build_live_observation_cockpit_surface(
        readiness_summary=summary.to_dict(),
        operator_live_runtime={
            "cache_provider_status": "connected",
            "cache_snapshot_ready": summary.runtime_cache_snapshot_ready,
            "cache_generated_at": NOW_ISO,
            "blocking_reasons": [],
        },
    )

    assert surface["mode"] == LIVE_OBSERVATION_MODE_FAIL_CLOSED


# -----------------------------------------------------------------------
# Universe integrity
# -----------------------------------------------------------------------


def test_final_target_universe_unchanged() -> None:
    assert final_target_contracts() == ("ES", "NQ", "CL", "6E", "MGC")


def test_mgc_label_is_micro_gold() -> None:
    manager = _manager()
    snapshot = _ingest_all_contracts(manager, _core_quote_only_fields)

    surface = build_five_contract_readiness_summary_surface(runtime_snapshot=snapshot)
    rows = {row["contract"]: row for row in surface["rows"]}
    assert rows["MGC"]["contract_label"] == "Micro Gold"


# -----------------------------------------------------------------------
# Observable quality model
# -----------------------------------------------------------------------


def test_core_quote_fields_present_in_quality_model() -> None:
    """core_quote_fields_present must appear in the quality model and
    reflect only REQUIRED_QUOTE_FIELDS, not REQUIRED_SESSION_FIELDS."""
    manager = _manager()
    snapshot = _ingest_all_contracts(manager, _core_quote_only_fields)

    observable = build_live_observable_snapshot_v2(snapshot.cache)
    for contract in final_target_contracts():
        obs = observable.contracts[contract]
        assert obs.quality.core_quote_fields_present is True
        assert obs.quality.required_fields_present is False
        quality_dict = obs.quality.to_dict()
        assert "core_quote_fields_present" in quality_dict
        assert quality_dict["core_quote_fields_present"] is True


# -----------------------------------------------------------------------
# Delta-merge: successive LEVELONE updates accumulate fields
# -----------------------------------------------------------------------


def test_successive_levelone_updates_merge_fields() -> None:
    """Schwab LEVELONE_FUTURES sends delta updates (only changed fields).
    Successive updates for the same contract must accumulate fields,
    not overwrite the entire record."""
    manager = _manager()
    symbol = "/ESM26"

    # First update: bid only
    frame_1 = _levelone_frame({"0": symbol, "1": 100.0}, symbol=symbol)
    entries_1 = extract_data_entries(frame_1)
    snapshot = manager.ingest_message(entries_1[0])

    # Second update: ask only
    frame_2 = _levelone_frame({"0": symbol, "2": 100.25}, symbol=symbol)
    entries_2 = extract_data_entries(frame_2)
    snapshot = manager.ingest_message(entries_2[0])

    # Third update: last + sizes + times
    frame_3 = _levelone_frame(
        {
            "0": symbol,
            "3": 100.125,
            "4": 10,
            "5": 12,
            "10": NOW_MILLIS,
            "11": NOW_MILLIS,
        },
        symbol=symbol,
    )
    entries_3 = extract_data_entries(frame_3)
    snapshot = manager.ingest_message(entries_3[0])

    # All fields from all three updates must be present
    observable = build_live_observable_snapshot_v2(snapshot.cache)
    es = observable.contracts.get("ES")
    assert es is not None
    assert es.quote.bid == 100.0
    assert es.quote.ask == 100.25
    assert es.quote.last == 100.125
    assert es.quote.bid_size == 10
    assert es.quote.ask_size == 12
    assert es.quote.quote_time is not None
    assert es.quote.trade_time is not None
    assert es.quality.core_quote_fields_present is True


def test_delta_merge_does_not_apply_to_bar_messages() -> None:
    """Bar (CHART_FUTURES) messages must replace, not merge — each bar
    event is a complete bar, not a delta update."""
    from ntb_marimo_console.market_data.stream_cache import (
        NormalizedStreamMessage,
        StreamCache,
    )

    cache = StreamCache(provider="schwab", cache_max_age_seconds=120.0, clock=lambda: NOW)
    cache.set_provider_status("active")

    bar_1 = NormalizedStreamMessage(
        provider="schwab",
        service="CHART_FUTURES",
        symbol="/ESM26",
        contract="ES",
        message_type="bar",
        fields={"open": 100.0, "close": 101.0, "high": 102.0, "low": 99.0},
        received_at=NOW_ISO,
    )
    cache.put_message(bar_1)

    bar_2 = NormalizedStreamMessage(
        provider="schwab",
        service="CHART_FUTURES",
        symbol="/ESM26",
        contract="ES",
        message_type="bar",
        fields={"open": 103.0, "close": 104.0},
        received_at=NOW_ISO,
    )
    cache.put_message(bar_2)

    snapshot = cache.snapshot()
    chart_records = [r for r in snapshot.records if r.message_type == "bar"]
    assert len(chart_records) == 1
    fields = dict(chart_records[0].fields)
    assert fields["open"] == 103.0
    assert fields["close"] == 104.0
    assert "high" not in fields
    assert "low" not in fields
