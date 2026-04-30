from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from ntb_marimo_console.adapters.schwab_futures_market_data import (
    SchwabFuturesMarketDataResult,
    SchwabFuturesQuoteSnapshot,
)
from ntb_marimo_console.demo_fixture_runtime import build_phase1_dependencies, default_fixtures_root
from ntb_marimo_console.launch_config import build_startup_artifacts_from_env
from ntb_marimo_console.market_data.config import resolve_futures_quote_service_config
from ntb_marimo_console.market_data.futures_quote_service import NullFuturesQuoteProvider
from ntb_marimo_console.runtime_modes import build_es_app_shell_for_mode


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "run_schwab_market_data_live_harness.py"
)

spec = importlib.util.spec_from_file_location("run_schwab_market_data_live_harness", SCRIPT_PATH)
harness = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["run_schwab_market_data_live_harness"] = harness
spec.loader.exec_module(harness)


class FakeSchwabAdapter:
    def __init__(self, result: SchwabFuturesMarketDataResult) -> None:
        self.result = result
        self.requests: list[object] = []

    def fetch_once(self, request: object) -> SchwabFuturesMarketDataResult:
        self.requests.append(request)
        return self.result


def adapter_result() -> SchwabFuturesMarketDataResult:
    return SchwabFuturesMarketDataResult(
        status="success",
        symbol="/ESM26",
        field_ids=(0, 1, 2, 3, 4, 5),
        streamer_socket_host="streamer-api.schwab.com",
        login_response_code=0,
        subscription_response_code=0,
        market_data_received=True,
        last_quote_snapshot=SchwabFuturesQuoteSnapshot(
            raw_fields=((0, "/ESM26"), (1, 7175), (2, 7175.5), (3, 7175.25), (4, 19), (5, 14)),
            symbol="/ESM26",
            bid_price=7175,
            ask_price=7175.5,
            last_price=7175.25,
            bid_size=19,
            ask_size=14,
        ),
        received_at="2026-04-30T11:59:58+00:00",
        failure_reason=None,
    )


def target_root(tmp_path: Path) -> Path:
    root = tmp_path / "target" / "ntb_marimo_console"
    (root / ".state" / "schwab").mkdir(parents=True)
    return root


def test_harness_refuses_without_explicit_live_and_does_not_build_adapter(capsys: pytest.CaptureFixture[str]) -> None:
    def adapter_factory(config: object) -> FakeSchwabAdapter:
        raise AssertionError("adapter_factory must not be called without --live")

    exit_code = harness.run([], env={}, adapter_factory=adapter_factory)

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "SCHWAB_MARKET_DATA_LIVE_HARNESS_FAIL" in output
    assert "live_harness_disabled_pass_--live" in output
    assert "market_data_received=no" in output


def test_harness_token_path_must_stay_under_target_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = target_root(tmp_path)
    monkeypatch.setattr(harness, "TARGET_ROOT", root)

    unsafe_args = harness.build_parser().parse_args(
        ["--live", "--token-path", str((tmp_path / "outside-token.json").resolve())]
    )
    with pytest.raises(harness.LiveHarnessConfigError, match="token_path_outside_target_state"):
        harness.load_config(
            unsafe_args,
            env={"SCHWAB_APP_KEY": "dummy-key", "SCHWAB_APP_SECRET": "dummy-secret"},
        )

    safe_args = harness.build_parser().parse_args(
        ["--live", "--token-path", "target/ntb_marimo_console/.state/schwab/token.json"]
    )
    config = harness.load_config(
        safe_args,
        env={"SCHWAB_APP_KEY": "dummy-key", "SCHWAB_APP_SECRET": "dummy-secret"},
    )

    assert config.token_path == (root / ".state" / "schwab" / "token.json").resolve()


def test_harness_output_sanitizer_removes_sensitive_values(capsys: pytest.CaptureFixture[str]) -> None:
    harness.print_display_result(
        config=None,
        panel=None,
        market_data_received=False,
        failure_reason=(
            "access_token=secret-access-token refresh_token=secret-refresh-token "
            "Authorization: Bearer very-secret-token-value-1234567890 "
            "customerId=raw-customer correlId=raw-correl accountNumber=12345678 "
            "wss://streamer-api.schwab.com/ws?credential=hidden "
            "https://api.schwabapi.com/trader/v1/userPreference "
            '{"customerId":"raw-json-customer","correlId":"raw-json-correl"}'
        ),
    )

    output = capsys.readouterr().out
    assert "secret-access-token" not in output
    assert "secret-refresh-token" not in output
    assert "very-secret-token-value" not in output
    assert "raw-customer" not in output
    assert "raw-correl" not in output
    assert "12345678" not in output
    assert "wss://" not in output
    assert "https://" not in output
    assert "raw-json-customer" not in output
    assert "raw-json-correl" not in output


def test_harness_uses_fake_schwab_adapter_for_display_level_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = target_root(tmp_path)
    monkeypatch.setattr(harness, "TARGET_ROOT", root)
    adapter = FakeSchwabAdapter(adapter_result())
    seen_configs: list[object] = []

    def adapter_factory(config: object) -> FakeSchwabAdapter:
        seen_configs.append(config)
        return adapter

    exit_code = harness.run(
        [
            "--live",
            "--symbol",
            "/ESM26",
            "--fields",
            "0,1,2,3,4,5",
            "--timeout-seconds",
            "10",
            "--token-path",
            "target/ntb_marimo_console/.state/schwab/token.json",
        ],
        env={"SCHWAB_APP_KEY": "dummy-key", "SCHWAB_APP_SECRET": "dummy-secret"},
        adapter_factory=adapter_factory,
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert len(seen_configs) == 1
    assert len(adapter.requests) == 1
    assert "SCHWAB_MARKET_DATA_LIVE_HARNESS_PASS" in output
    assert "provider=schwab" in output
    assert "symbol=/ESM26" in output
    assert "status=Schwab quote" in output
    assert "bid=7175" in output
    assert "ask=7175.5" in output
    assert "last=7175.25" in output
    assert "quote_time=2026-04-30T11:59:58+00:00" in output
    assert "market_data_received=yes" in output
    assert "streamer-api.schwab.com" not in output
    assert "dummy-key" not in output
    assert "dummy-secret" not in output


def test_harness_failure_output_is_display_safe_with_fake_adapter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = target_root(tmp_path)
    monkeypatch.setattr(harness, "TARGET_ROOT", root)
    adapter = FakeSchwabAdapter(
        SchwabFuturesMarketDataResult(
            status="error",
            symbol="/ESM26",
            field_ids=(0, 1, 2),
            streamer_socket_host="streamer-api.schwab.com",
            login_response_code=None,
            subscription_response_code=None,
            market_data_received=False,
            last_quote_snapshot=None,
            received_at=None,
            failure_reason="subscription_error access_token=hidden customerId=raw-customer wss://streamer.example/ws",
        )
    )

    exit_code = harness.run(
        ["--live", "--fields", "0,1,2"],
        env={"SCHWAB_APP_KEY": "dummy-key", "SCHWAB_APP_SECRET": "dummy-secret"},
        adapter_factory=lambda config: adapter,
    )

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "SCHWAB_MARKET_DATA_LIVE_HARNESS_FAIL" in output
    assert "status=Market data unavailable" in output
    assert "market_data_received=no" in output
    assert "provider_returned_no_quote" in output
    assert "subscription_error" not in output
    assert "hidden" not in output
    assert "raw-customer" not in output
    assert "wss://" not in output


def test_pytest_path_does_not_call_live_adapter_factory(capsys: pytest.CaptureFixture[str]) -> None:
    calls: list[object] = []

    def adapter_factory(config: object) -> FakeSchwabAdapter:
        calls.append(config)
        return FakeSchwabAdapter(adapter_result())

    exit_code = harness.run([], env={}, adapter_factory=adapter_factory)

    assert exit_code == 1
    assert calls == []
    assert "market_data_received=no" in capsys.readouterr().out


def test_app_code_does_not_import_manual_harness_or_adapter_probe() -> None:
    source_root = Path(__file__).resolve().parents[1] / "src" / "ntb_marimo_console"
    for relative_path in (
        "runtime_modes.py",
        "demo_fixture_runtime.py",
        "launch_config.py",
        "app.py",
    ):
        source = (source_root / relative_path).read_text(encoding="utf-8")
        assert "run_schwab_market_data_live_harness" not in source
        assert "probe_schwab_futures_market_data_adapter" not in source


def test_normal_startup_remains_disabled_null_and_unavailable() -> None:
    with patch.dict(os.environ, {}, clear=True):
        artifacts = build_startup_artifacts_from_env()

    assert artifacts.ready
    assert artifacts.config is not None
    assert artifacts.config.market_data_config.provider == "disabled"
    market_data = artifacts.shell["surfaces"]["live_observables"]["market_data"]
    assert market_data["status"] == "Market data unavailable"
    assert market_data["bid"] == "N/A"


def test_schwab_provider_without_explicit_adapter_remains_inert() -> None:
    market_data_config = resolve_futures_quote_service_config(
        {
            "NTB_MARKET_DATA_PROVIDER": "schwab",
            "NTB_MARKET_DATA_SYMBOL": "ES",
        },
        target_root=Path(__file__).resolve().parents[1],
    )

    dependencies = build_phase1_dependencies(
        default_fixtures_root(),
        market_data_config=market_data_config,
    )
    provider = getattr(dependencies.market_data_service, "_provider", None)
    result = dependencies.market_data_service.get_quote("ES")

    assert isinstance(provider, NullFuturesQuoteProvider)
    assert result.status == "disabled"


def test_mocked_fixture_activation_and_query_action_availability_remain_unchanged() -> None:
    market_data_config = resolve_futures_quote_service_config(
        {
            "NTB_MARKET_DATA_PROVIDER": "fixture",
            "NTB_MARKET_DATA_SYMBOL": "ES",
        },
        target_root=Path(__file__).resolve().parents[1],
    )

    baseline_shell = build_es_app_shell_for_mode(mode="fixture_demo")
    fixture_shell = build_es_app_shell_for_mode(
        mode="fixture_demo",
        market_data_config=market_data_config,
    )

    assert fixture_shell["surfaces"]["live_observables"]["market_data"]["status"] == "Market data unavailable"
    assert fixture_shell["surfaces"]["query_action"] == baseline_shell["surfaces"]["query_action"]
    assert fixture_shell["workflow"] == baseline_shell["workflow"]
    assert fixture_shell["runtime"] == baseline_shell["runtime"]
