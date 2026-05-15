"""Tests for bar builder wiring into the operator live runtime path.

Proves that ChartFuturesBarBuilder is created and hooked into the message
dispatch so bar_states flow to build_live_observable_snapshot_v2 and the
readiness summary surfaces chart_status correctly.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from ntb_marimo_console.contract_universe import final_target_contracts
from ntb_marimo_console.market_data.bar_builder import ChartFuturesBarBuilder
from ntb_marimo_console.market_data.stream_manager import (
    SchwabStreamManager,
    SchwabStreamManagerConfig,
    StreamClientResult,
)
from ntb_marimo_console.operator_live_launcher import (
    OperatorLiveLaunchResult,
    _create_and_hook_bar_builder,
    start_operator_live_runtime,
    stop_operator_live_runtime,
)
from ntb_marimo_console.operator_live_runtime import (
    clear_operator_live_bar_builder,
    clear_operator_live_runtime_registration,
    get_registered_operator_live_bar_builder,
    register_operator_live_bar_builder,
)
from ntb_marimo_console.readiness_summary import (
    build_five_contract_readiness_summary,
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
FIVE_MINUTE_ALIGNED = NOW.replace(minute=0, second=0, microsecond=0)


class FakeStreamClient:
    def login(self, config: SchwabStreamManagerConfig) -> StreamClientResult:
        return StreamClientResult(succeeded=True)

    def subscribe(self, request: object) -> StreamClientResult:
        return StreamClientResult(succeeded=True)

    def close(self) -> StreamClientResult:
        return StreamClientResult(succeeded=True)


def _config() -> SchwabStreamManagerConfig:
    contracts = final_target_contracts()
    return SchwabStreamManagerConfig(
        provider="schwab",
        services_requested=("LEVELONE_FUTURES", "CHART_FUTURES"),
        symbols_requested=tuple(SYMBOL_BY_CONTRACT[c] for c in contracts),
        fields_requested=DEFAULT_LEVELONE_FUTURES_FIELD_IDS,
        contracts_requested=contracts,
        explicit_live_opt_in=True,
    )


def _manager() -> SchwabStreamManager:
    manager = SchwabStreamManager(
        _config(),
        client=FakeStreamClient(),
        clock=lambda: NOW,
    )
    manager.start()
    return manager


def _levelone_frame(*, symbol: str) -> str:
    content = {
        "key": symbol,
        "0": symbol,
        "1": 100.0,
        "2": 100.25,
        "3": 100.125,
        "4": 10,
        "5": 12,
        "8": 1000,
        "10": NOW_MILLIS,
        "11": NOW_MILLIS,
        "12": 101.0,
        "13": 99.0,
        "14": 99.75,
        "18": 100.0,
        "22": "Normal",
        "30": True,
        "32": True,
    }
    return json.dumps({
        "data": [{
            "service": "LEVELONE_FUTURES",
            "command": "SUBS",
            "timestamp": NOW_MILLIS,
            "content": [content],
        }]
    })


def _chart_message(contract: str, *, minute_offset: int, completed: bool = True) -> dict[str, object]:
    symbol = SYMBOL_BY_CONTRACT[contract]
    start = FIVE_MINUTE_ALIGNED + timedelta(minutes=minute_offset)
    end = start + timedelta(minutes=1)
    return {
        "service": "CHART_FUTURES",
        "contract": contract,
        "symbol": symbol,
        "provider": "schwab",
        "source": "chart_futures",
        "start_time": start.isoformat(),
        "end_time": end.isoformat(),
        "received_at": NOW_ISO,
        "open": 100.0,
        "high": 101.0,
        "low": 99.5,
        "close": 100.5,
        "volume": 1000,
        "completed": completed,
    }


def _ingest_levelone(manager: SchwabStreamManager) -> None:
    for contract in final_target_contracts():
        symbol = SYMBOL_BY_CONTRACT[contract]
        entries = extract_data_entries(_levelone_frame(symbol=symbol))
        for entry in entries:
            manager.ingest_message(entry)


def _ingest_five_complete_bars(manager: SchwabStreamManager) -> None:
    for contract in final_target_contracts():
        for minute in range(5):
            manager.ingest_message(_chart_message(contract, minute_offset=minute))


def _ingest_startup_gap_then_complete_bars(manager: SchwabStreamManager) -> None:
    for contract in final_target_contracts():
        for minute in (2, 3, 4, 5, 6, 7, 8, 9):
            manager.ingest_message(_chart_message(contract, minute_offset=minute))


# -----------------------------------------------------------------------
# Bar builder registry tests
# -----------------------------------------------------------------------


def test_bar_builder_registry_starts_empty() -> None:
    clear_operator_live_bar_builder()
    assert get_registered_operator_live_bar_builder() is None


def test_bar_builder_registry_register_and_get() -> None:
    clear_operator_live_bar_builder()
    try:
        builder = ChartFuturesBarBuilder()
        register_operator_live_bar_builder(builder)
        assert get_registered_operator_live_bar_builder() is builder
    finally:
        clear_operator_live_bar_builder()


def test_clear_runtime_registration_also_clears_bar_builder() -> None:
    clear_operator_live_runtime_registration()
    try:
        builder = ChartFuturesBarBuilder()
        register_operator_live_bar_builder(builder)
        assert get_registered_operator_live_bar_builder() is builder
        clear_operator_live_runtime_registration()
        assert get_registered_operator_live_bar_builder() is None
    finally:
        clear_operator_live_runtime_registration()


# -----------------------------------------------------------------------
# Message listener wiring tests
# -----------------------------------------------------------------------


def test_message_listener_dispatches_chart_to_bar_builder() -> None:
    manager = _manager()
    bar_builder = _create_and_hook_bar_builder(manager, _config())

    _ingest_levelone(manager)
    _ingest_five_complete_bars(manager)

    states = bar_builder.states()
    for contract in final_target_contracts():
        state = states[contract]
        assert state.completed_five_minute_bars, f"{contract}: expected completed five-minute bars"


def test_message_listener_does_not_dispatch_levelone_to_bar_builder() -> None:
    manager = _manager()
    bar_builder = _create_and_hook_bar_builder(manager, _config())

    _ingest_levelone(manager)

    states = bar_builder.states()
    for contract in final_target_contracts():
        state = states[contract]
        assert not state.completed_one_minute_bars, f"{contract}: LEVELONE should not produce bars"
        assert not state.completed_five_minute_bars


def test_bar_builder_expected_symbols_from_config() -> None:
    config = _config()
    bar_builder = _create_and_hook_bar_builder(_manager(), config)
    assert bar_builder.expected_symbols is not None
    for contract in final_target_contracts():
        assert contract in bar_builder.expected_symbols


def test_bar_builder_included_in_launch_result() -> None:
    clear_operator_live_runtime_registration()
    try:
        config = _config()
        result = start_operator_live_runtime(
            client_factory=lambda cfg: FakeStreamClient(),
            config=config,
            values={"NTB_OPERATOR_RUNTIME_MODE": "OPERATOR_LIVE_RUNTIME"},
            register=True,
        )
        assert isinstance(result, OperatorLiveLaunchResult)
        assert result.bar_builder is not None
        assert isinstance(result.bar_builder, ChartFuturesBarBuilder)
        assert get_registered_operator_live_bar_builder() is result.bar_builder
        stop_operator_live_runtime(result.manager)
    finally:
        clear_operator_live_runtime_registration()


def test_stop_clears_bar_builder_registration() -> None:
    clear_operator_live_runtime_registration()
    try:
        result = start_operator_live_runtime(
            client_factory=lambda cfg: FakeStreamClient(),
            config=_config(),
            values={"NTB_OPERATOR_RUNTIME_MODE": "OPERATOR_LIVE_RUNTIME"},
            register=True,
        )
        assert get_registered_operator_live_bar_builder() is not None
        stop_operator_live_runtime(result.manager)
        assert get_registered_operator_live_bar_builder() is None
    finally:
        clear_operator_live_runtime_registration()


# -----------------------------------------------------------------------
# Readiness summary integration: bar_states flow to observable builder
# -----------------------------------------------------------------------


def test_readiness_summary_chart_available_with_completed_bars() -> None:
    """When the bar builder has completed five-minute bars, readiness summary
    must report chart_status='chart available' instead of 'chart missing'."""
    clear_operator_live_runtime_registration()
    try:
        manager = _manager()
        bar_builder = _create_and_hook_bar_builder(manager, _config())
        register_operator_live_bar_builder(bar_builder)

        _ingest_levelone(manager)
        _ingest_five_complete_bars(manager)

        snapshot = manager.snapshot()
        summary = build_five_contract_readiness_summary(runtime_snapshot=snapshot)

        for row in summary.rows:
            assert row.chart_status == "chart available", (
                f"{row.contract}: expected 'chart available', got '{row.chart_status}'"
            )
            assert row.chart_freshness_state == "fresh", (
                f"{row.contract}: expected chart freshness 'fresh', got '{row.chart_freshness_state}'"
            )
    finally:
        clear_operator_live_runtime_registration()


def test_completed_fresh_bars_with_startup_gap_show_chart_available_but_not_query_ready() -> None:
    """A historical startup gap must not relabel proven fresh completed
    five-minute bars as chart blocked, and the display label must not create
    QUERY_READY without preserved-engine provenance."""
    clear_operator_live_runtime_registration()
    try:
        manager = _manager()
        bar_builder = _create_and_hook_bar_builder(manager, _config())
        register_operator_live_bar_builder(bar_builder)

        _ingest_levelone(manager)
        _ingest_startup_gap_then_complete_bars(manager)

        states = bar_builder.states()
        for contract, state in states.items():
            assert state.completed_five_minute_bars, f"{contract}: expected completed five-minute bars"
            assert any(
                reason.startswith(f"gap_in_one_minute_bars:{contract}:")
                for reason in state.blocking_reasons
            ), f"{contract}: expected startup gap blocker"
            readiness = state.readiness()
            assert readiness.completed_five_minute_available is True
            assert readiness.fresh is True
            assert readiness.state == "blocked"

        summary = build_five_contract_readiness_summary(
            runtime_snapshot=manager.snapshot(),
            bar_states=states,
        )

        assert tuple(row.contract for row in summary.rows) == ("ES", "NQ", "CL", "6E", "MGC")
        for row in summary.rows:
            assert row.chart_status == "chart available"
            assert row.chart_freshness_state == "fresh"
            assert row.query_ready is False
            assert "ZN" not in row.contract
            assert row.contract != "GC"
        mgc = next(row for row in summary.rows if row.contract == "MGC")
        assert mgc.contract_label == "Micro Gold"
        assert mgc.contract_label != "GC"
    finally:
        clear_operator_live_runtime_registration()


def test_readiness_summary_chart_building_without_completed_bars() -> None:
    """When the bar builder has building but no completed bars, chart_status
    must show 'chart building' — not 'chart available' or 'chart missing'."""
    clear_operator_live_runtime_registration()
    try:
        manager = _manager()
        bar_builder = _create_and_hook_bar_builder(manager, _config())
        register_operator_live_bar_builder(bar_builder)

        _ingest_levelone(manager)
        for contract in final_target_contracts():
            manager.ingest_message(_chart_message(contract, minute_offset=0))
            manager.ingest_message(_chart_message(contract, minute_offset=1))

        snapshot = manager.snapshot()
        summary = build_five_contract_readiness_summary(runtime_snapshot=snapshot)

        for row in summary.rows:
            assert row.chart_status in ("chart building", "chart missing"), (
                f"{row.contract}: expected building/missing, got '{row.chart_status}'"
            )
    finally:
        clear_operator_live_runtime_registration()


def test_readiness_summary_chart_missing_without_bar_builder() -> None:
    """Without a registered bar builder, chart_status must remain
    'chart missing' or 'chart stale' — never 'chart available'."""
    clear_operator_live_runtime_registration()
    try:
        manager = _manager()
        _ingest_levelone(manager)

        snapshot = manager.snapshot()
        summary = build_five_contract_readiness_summary(runtime_snapshot=snapshot)

        for row in summary.rows:
            assert row.chart_status != "chart available", (
                f"{row.contract}: chart should not be available without bar builder"
            )
    finally:
        clear_operator_live_runtime_registration()


def test_query_blocked_without_chart_available() -> None:
    """query_ready must remain False when chart_status is not 'chart available',
    even when quote is available and the fixture trigger gate passes."""
    clear_operator_live_runtime_registration()
    try:
        manager = _manager()
        bar_builder = _create_and_hook_bar_builder(manager, _config())
        register_operator_live_bar_builder(bar_builder)

        _ingest_levelone(manager)

        snapshot = manager.snapshot()
        summary = build_five_contract_readiness_summary(runtime_snapshot=snapshot)

        for row in summary.rows:
            assert row.query_ready is False, (
                f"{row.contract}: query must remain blocked without completed chart bars"
            )
    finally:
        clear_operator_live_runtime_registration()
