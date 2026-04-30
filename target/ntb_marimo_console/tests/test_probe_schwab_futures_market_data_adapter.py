from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "probe_schwab_futures_market_data_adapter.py"
)

spec = importlib.util.spec_from_file_location("probe_schwab_futures_market_data_adapter", SCRIPT_PATH)
probe = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["probe_schwab_futures_market_data_adapter"] = probe
spec.loader.exec_module(probe)


class FakeAdapter:
    def __init__(self, result: object) -> None:
        self.result = result
        self.requests: list[object] = []

    def fetch_once(self, request: object) -> object:
        self.requests.append(request)
        return self.result


def test_live_smoke_script_requires_explicit_opt_in(capsys) -> None:
    exit_code = probe.run([], env={})

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "SCHWAB_FUTURES_MARKET_DATA_ADAPTER_FAIL" in output
    assert "live smoke disabled" in output


def test_live_smoke_script_prints_safe_success_only(capsys) -> None:
    snapshot = probe.SchwabFuturesQuoteSnapshot(
        raw_fields=((0, "/ESM26"), (1, 7175), (2, 7175.5), (3, 7175.25), (4, 19), (5, 14)),
        symbol="/ESM26",
        bid_price=7175,
        ask_price=7175.5,
        last_price=7175.25,
        bid_size=19,
        ask_size=14,
    )
    result = probe.SchwabFuturesMarketDataResult(
        status="success",
        symbol="/ESM26",
        field_ids=(0, 1, 2, 3, 4, 5),
        streamer_socket_host="streamer-api.schwab.com",
        login_response_code=0,
        subscription_response_code=0,
        market_data_received=True,
        last_quote_snapshot=snapshot,
        received_at="2026-04-30T12:00:00+00:00",
        failure_reason=None,
    )

    exit_code = probe.run(
        ["--live"],
        env={"SCHWAB_APP_KEY": "dummy-key", "SCHWAB_APP_SECRET": "dummy-secret"},
        adapter_factory=lambda config: FakeAdapter(result),
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "SCHWAB_FUTURES_MARKET_DATA_ADAPTER_PASS" in output
    assert "requested_symbol=/ESM26" in output
    assert "effective_field_ids=0,1,2,3,4,5" in output
    assert "streamer_socket_host=streamer-api.schwab.com" in output
    assert "login_response_code=0" in output
    assert "subscription_response_code=0" in output
    assert "market_data_received=yes" in output
    assert "bid_price=7175" in output
    assert "ask_price=7175.5" in output
    assert "last_price=7175.25" in output
    assert "bid_size=19" in output
    assert "ask_size=14" in output
    assert "dummy-secret" not in output
    assert "access_token" not in output
    assert "refresh_token" not in output
    assert "raw-customer-id" not in output
    assert "raw-correl-id" not in output
    assert "wss://" not in output


def test_live_smoke_script_returns_nonzero_on_adapter_failure(capsys) -> None:
    result = probe.SchwabFuturesMarketDataResult(
        status="timeout",
        symbol="/ESM26",
        field_ids=(0, 1, 2),
        streamer_socket_host="streamer-api.schwab.com",
        login_response_code=0,
        subscription_response_code=0,
        market_data_received=False,
        last_quote_snapshot=None,
        received_at=None,
        failure_reason="market_data_not_received",
    )

    exit_code = probe.run(
        ["--live", "--fields", "0,1,2"],
        env={"SCHWAB_APP_KEY": "dummy-key", "SCHWAB_APP_SECRET": "dummy-secret"},
        adapter_factory=lambda config: FakeAdapter(result),
    )

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "SCHWAB_FUTURES_MARKET_DATA_ADAPTER_FAIL" in output
    assert "market_data_received=no" in output
    assert "failure_reason=market_data_not_received" in output
