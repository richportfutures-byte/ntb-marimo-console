from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "probe_schwab_levelone_futures.py"
)

spec = importlib.util.spec_from_file_location("probe_schwab_levelone_futures", SCRIPT_PATH)
probe = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["probe_schwab_levelone_futures"] = probe
spec.loader.exec_module(probe)


def valid_env() -> dict[str, str]:
    return {
        "SCHWAB_APP_KEY": "dummy-app-key",
        "SCHWAB_APP_SECRET": "dummy-app-secret",
        "SCHWAB_CALLBACK_URL": "https://127.0.0.1/callback",
        "SCHWAB_TOKEN_PATH": ".state/schwab/token.json",
        "SCHWAB_FUTURES_SYMBOL": "/ESM26",
        "SCHWAB_STREAM_FIELDS": "0,1,2,3,4,5,8,9,10,11,12,13,14,18,19,20,22,23,24,25,26,27,28,29,30,31,32,33,34,35,37,38,39",
        "SCHWAB_PROBE_TIMEOUT_SECONDS": "5",
        "SCHWAB_PROBE_DRY_RUN": "true",
    }


@pytest.fixture(autouse=True)
def isolated_target_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target_root = tmp_path / "target" / "ntb_marimo_console"
    target_root.mkdir(parents=True)
    monkeypatch.setattr(probe, "_target_root", lambda: target_root)
    return target_root


@pytest.fixture
def token_path(isolated_target_root: Path) -> Path:
    path = isolated_target_root / ".state" / "schwab" / "token.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"access_token": "secret-access-token-value", "refresh_token": "secret-refresh"}),
        encoding="utf-8",
    )
    return path


def live_env(token_path: Path) -> dict[str, str]:
    env = valid_env()
    env["SCHWAB_TOKEN_PATH"] = str(token_path)
    env["SCHWAB_PROBE_DRY_RUN"] = "false"
    env["SCHWAB_STREAM_FIELDS"] = "0,1,2,3"
    env["SCHWAB_PROBE_TIMEOUT_SECONDS"] = "1"
    return env


def streamer_payload() -> dict[str, object]:
    return {
        "streamerInfo": {
            "streamerSocketUrl": "wss://streamer-api.schwab.com/ws?credential=hidden",
            "schwabClientCustomerId": "raw-customer-id",
            "schwabClientCorrelId": "raw-correl-id",
            "schwabClientChannel": "raw-channel",
            "schwabClientFunctionId": "raw-function",
        }
    }


def test_load_config_accepts_explicit_contract_symbol_under_state() -> None:
    config = probe.load_config(valid_env())

    assert config.dry_run is True
    assert config.futures_symbol == "/ESM26"
    assert config.futures_root == "ES"
    assert config.futures_month_code == "M"
    assert config.stream_fields[:3] == (0, 1, 2)
    assert ".state/schwab/token.json" in config.token_path_display


def test_load_config_rejects_root_only_symbol() -> None:
    env = valid_env()
    env["SCHWAB_FUTURES_SYMBOL"] = "/ES"

    with pytest.raises(probe.ValidationError, match="explicit futures contract"):
        probe.load_config(env)


def test_load_config_rejects_token_path_outside_target_state() -> None:
    env = valid_env()
    env["SCHWAB_TOKEN_PATH"] = "../token.json"

    with pytest.raises(probe.ValidationError, match="under target/ntb_marimo_console/.state"):
        probe.load_config(env)


def test_missing_credential_validation_remains_fail_closed() -> None:
    env = valid_env()
    del env["SCHWAB_APP_SECRET"]

    with pytest.raises(probe.ValidationError, match="SCHWAB_APP_SECRET"):
        probe.load_config(env)


def test_unsupported_field_id_fails_closed() -> None:
    env = valid_env()
    env["SCHWAB_STREAM_FIELDS"] = "0,999"

    with pytest.raises(probe.ValidationError, match="Unsupported LEVELONE_FUTURES field ID"):
        probe.load_config(env)


def test_dry_run_still_does_not_perform_network(capsys: pytest.CaptureFixture[str], token_path: Path) -> None:
    called = False

    def fetch_func(access_token: str) -> dict[str, object]:
        nonlocal called
        called = True
        return streamer_payload()

    env = live_env(token_path)
    env["SCHWAB_PROBE_DRY_RUN"] = "true"
    exit_code = probe.run([], env=env, fetch_func=fetch_func)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert called is False
    assert "DRY_RUN_PASS" in output
    assert "network_activity=SKIPPED_DRY_RUN" in output
    assert "dummy-app-secret" not in output


def test_live_path_sends_login_before_levelone_futures(capsys: pytest.CaptureFixture[str], token_path: Path) -> None:
    sent: list[str] = []

    async def live_probe_func(config: object, credentials: object, access_token: str) -> probe.LiveProbeResult:
        sent.append("LOGIN")
        sent.append("LEVELONE_FUTURES")
        return probe.LiveProbeResult(
            streamer_socket_host=credentials.streamer_socket_host,
            login_response_code=0,
            subscription_response_code=0,
            market_data={0: "/ESM26", 1: 5000.25},
        )

    exit_code = probe.run(
        [],
        env=live_env(token_path),
        fetch_func=lambda access_token: streamer_payload(),
        live_probe_func=live_probe_func,
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert sent == ["LOGIN", "LEVELONE_FUTURES"]
    assert "LEVELONE_FUTURES_PASS" in output
    assert "login_response_code=0" in output
    assert "subscription_response_code=0" in output
    assert "market_data_received=yes" in output
    assert "secret-access-token-value" not in output
    assert "secret-refresh" not in output
    assert "raw-customer-id" not in output
    assert "raw-correl-id" not in output
    assert "wss://streamer-api.schwab.com/ws?credential=hidden" not in output


def test_nonzero_login_code_blocks_levelone_futures() -> None:
    credentials = probe.extract_streamer_credentials(streamer_payload())
    sent_messages: list[str] = []

    class WebSocket:
        async def send(self, message: str) -> None:
            sent_messages.append(message)

        async def recv(self) -> str:
            return json.dumps({"response": [{"service": "ADMIN", "command": "LOGIN", "content": {"code": 7}}]})

    class Connection:
        async def __aenter__(self) -> WebSocket:
            return WebSocket()

        async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
            return None

    class FakeWebsockets:
        def connect(self, url: str) -> Connection:
            return Connection()

    config = probe.load_config(live_env(probe._target_root() / ".state" / "schwab" / "token.json"))
    with pytest.raises(probe.LiveProbeError) as exc_info:
        asyncio.run(
            probe.perform_live_probe(
                config,
                credentials,
                "secret-access-token-value",
                websockets_module=FakeWebsockets(),
            )
        )

    assert exc_info.value.login_response_code == 7
    assert len(sent_messages) == 1
    assert "LEVELONE_FUTURES" not in sent_messages[0]


def test_nonzero_subscription_response_fails_closed(token_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    async def live_probe_func(config: object, credentials: object, access_token: str) -> probe.LiveProbeResult:
        raise probe.LiveProbeError(
            "LEVELONE_FUTURES subscription failed.",
            streamer_socket_host=credentials.streamer_socket_host,
            login_response_code=0,
            subscription_response_code=9,
        )

    exit_code = probe.run(
        [],
        env=live_env(token_path),
        fetch_func=lambda access_token: streamer_payload(),
        live_probe_func=live_probe_func,
    )

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "LEVELONE_FUTURES_FAIL" in output
    assert "login_response_code=0" in output
    assert "subscription_response_code=9" in output


def test_user_preference_401_triggers_exactly_one_refresh_and_retry(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    token_path: Path,
) -> None:
    calls: list[str] = []

    def refresh_token_file(*args: object, **kwargs: object) -> dict[str, object]:
        calls.append("refresh")
        return {"access_token": "new-access", "refresh_token": "new-refresh"}

    def fetch_func(access_token: str) -> dict[str, object]:
        calls.append(access_token)
        if access_token == "secret-access-token-value":
            raise probe.LiveProbeError("Unauthorized.", http_status=401, exception_class="HTTPError")
        assert access_token == "new-access"
        return streamer_payload()

    async def live_probe_func(config: object, credentials: object, access_token: str) -> probe.LiveProbeResult:
        assert access_token == "new-access"
        return probe.LiveProbeResult(
            streamer_socket_host=credentials.streamer_socket_host,
            login_response_code=0,
            subscription_response_code=0,
            market_data={0: "/ESM26"},
        )

    monkeypatch.setattr(probe.schwab_token_utils, "refresh_token_file", refresh_token_file)

    exit_code = probe.run(
        [],
        env=live_env(token_path),
        fetch_func=fetch_func,
        live_probe_func=live_probe_func,
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert calls == ["secret-access-token-value", "refresh", "new-access"]
    assert "LEVELONE_FUTURES_PASS" in output
    assert "secret-access-token-value" not in output
    assert "new-access" not in output
    assert "new-refresh" not in output


def test_refresh_failure_produces_safe_output(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    token_path: Path,
) -> None:
    def refresh_token_file(*args: object, **kwargs: object) -> dict[str, object]:
        raise probe.schwab_token_utils.SchwabTokenError(
            "Token refresh failed.",
            http_status=401,
            exception_class="HTTPError",
        )

    def fetch_func(access_token: str) -> dict[str, object]:
        raise probe.LiveProbeError("Unauthorized.", http_status=401, exception_class="HTTPError")

    monkeypatch.setattr(probe.schwab_token_utils, "refresh_token_file", refresh_token_file)

    exit_code = probe.run([], env=live_env(token_path), fetch_func=fetch_func)

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "LEVELONE_FUTURES_FAIL" in output
    assert "Fresh OAuth is required" in output
    assert "secret-access-token-value" not in output
    assert "secret-refresh" not in output


def test_timeout_fails_closed() -> None:
    credentials = probe.extract_streamer_credentials(streamer_payload())

    class WebSocket:
        async def send(self, message: str) -> None:
            return None

        async def recv(self) -> str:
            await asyncio.sleep(0.05)
            return "{}"

    class Connection:
        async def __aenter__(self) -> WebSocket:
            return WebSocket()

        async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
            return None

    class FakeWebsockets:
        def connect(self, url: str) -> Connection:
            return Connection()

    env = valid_env()
    env["SCHWAB_PROBE_DRY_RUN"] = "false"
    env["SCHWAB_PROBE_TIMEOUT_SECONDS"] = "0.001"
    config = probe.load_config(env)

    with pytest.raises(probe.LiveProbeError) as exc_info:
        asyncio.run(
            probe.perform_live_probe(
                config,
                credentials,
                "secret-access-token-value",
                websockets_module=FakeWebsockets(),
            )
        )

    assert exc_info.value.exception_class == "TimeoutError"


def test_successful_mocked_live_sequence_prints_pass_marker(capsys: pytest.CaptureFixture[str], token_path: Path) -> None:
    exit_code = probe.run(
        [],
        env=live_env(token_path),
        fetch_func=lambda access_token: streamer_payload(),
        live_probe_func=lambda config, credentials, access_token: asyncio.sleep(
            0,
            result=probe.LiveProbeResult(
                streamer_socket_host=credentials.streamer_socket_host,
                login_response_code=0,
                subscription_response_code=0,
                market_data={0: "/ESM26", 1: 5000.25, 2: 5000.5},
            ),
        ),
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "LEVELONE_FUTURES_PASS" in output
    assert "login_response_code=0" in output
    assert "subscription_response_code=0" in output
    assert "market_data_received=yes" in output
    assert "field_1_Bid Price=5000.25" in output
