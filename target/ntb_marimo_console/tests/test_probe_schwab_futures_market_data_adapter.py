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


def write_local_env(target_root: Path, content: str) -> None:
    target_root.mkdir(parents=True, exist_ok=True)
    (target_root / ".env").write_text(content, encoding="utf-8")


def test_live_smoke_script_requires_explicit_opt_in(capsys) -> None:
    exit_code = probe.run([], env={})

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "SCHWAB_FUTURES_MARKET_DATA_ADAPTER_FAIL" in output
    assert "live smoke disabled" in output


def test_local_env_values_are_loaded_when_shell_env_is_absent(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    target_root = tmp_path / "target" / "ntb_marimo_console"
    write_local_env(
        target_root,
        "\n".join(
            (
                "# local operator env",
                "SCHWAB_APP_KEY='env-file-key'",
                'SCHWAB_APP_SECRET="env-file-secret"',
                "SCHWAB_TOKEN_PATH=target/ntb_marimo_console/.state/schwab/token.json",
                "",
            )
        ),
    )
    monkeypatch.setattr(probe, "TARGET_ROOT", target_root)
    result = probe.SchwabFuturesMarketDataResult(
        status="timeout",
        symbol="/ESM26",
        field_ids=(0, 1),
        streamer_socket_host=None,
        login_response_code=None,
        subscription_response_code=None,
        market_data_received=False,
        last_quote_snapshot=None,
        received_at=None,
        failure_reason="market_data_not_received",
    )
    seen_configs: list[object] = []

    def adapter_factory(config: object) -> FakeAdapter:
        seen_configs.append(config)
        return FakeAdapter(result)

    exit_code = probe.run(["--live", "--fields", "0,1"], env={}, adapter_factory=adapter_factory)

    output = capsys.readouterr().out
    assert exit_code == 1
    assert len(seen_configs) == 1
    assert seen_configs[0].app_key == "env-file-key"
    assert seen_configs[0].app_secret == "env-file-secret"
    assert seen_configs[0].token_path == target_root / ".state" / "schwab" / "token.json"
    assert "env-file-key" not in output
    assert "env-file-secret" not in output


def test_shell_env_overrides_local_env_values(tmp_path: Path, monkeypatch) -> None:
    target_root = tmp_path / "target" / "ntb_marimo_console"
    write_local_env(
        target_root,
        "\n".join(
            (
                "SCHWAB_APP_KEY=env-file-key",
                "SCHWAB_APP_SECRET=env-file-secret",
            )
        ),
    )
    monkeypatch.setattr(probe, "TARGET_ROOT", target_root)
    args = probe.build_parser().parse_args(["--live"])

    config = probe.load_config(
        args,
        env={"SCHWAB_APP_KEY": "shell-key", "SCHWAB_APP_SECRET": "shell-secret"},
    )

    assert config.app_key == "shell-key"
    assert config.app_secret == "shell-secret"


def test_missing_local_env_preserves_current_missing_credential_behavior(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.setattr(probe, "TARGET_ROOT", tmp_path / "target" / "ntb_marimo_console")

    exit_code = probe.run(["--live"], env={})

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "SCHWAB_FUTURES_MARKET_DATA_ADAPTER_FAIL" in output
    assert "SCHWAB_APP_KEY and SCHWAB_APP_SECRET are required for live smoke" in output


def test_env_example_contains_placeholders_only() -> None:
    example_path = Path(__file__).resolve().parents[1] / ".env.example"
    contents = example_path.read_text(encoding="utf-8")

    assert "SCHWAB_APP_KEY=" in contents
    assert "SCHWAB_APP_SECRET=" in contents
    assert "SCHWAB_CALLBACK_URL=https://127.0.0.1" in contents
    assert "SCHWAB_TOKEN_PATH=target/ntb_marimo_console/.state/schwab/token.json" in contents
    assert "PASTE" not in contents
    assert "secret-" not in contents
    assert "access_token" not in contents
    assert "refresh_token" not in contents


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
