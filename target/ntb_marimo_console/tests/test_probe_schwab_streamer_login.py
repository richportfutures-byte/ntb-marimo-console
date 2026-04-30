from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "probe_schwab_streamer_login.py"

spec = importlib.util.spec_from_file_location("probe_schwab_streamer_login", SCRIPT_PATH)
probe = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["probe_schwab_streamer_login"] = probe
spec.loader.exec_module(probe)


def write_token(path: Path, access_token: str = "secret-access-token-value") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"access_token": access_token, "refresh_token": "secret-refresh"}), encoding="utf-8")


def env_for(token_path: Path, *, live: str = "false") -> dict[str, str]:
    return {
        "SCHWAB_TOKEN_PATH": str(token_path),
        "SCHWAB_STREAM_LOGIN_LIVE": live,
        "SCHWAB_STREAM_LOGIN_TIMEOUT_SECONDS": "1",
    }


@pytest.fixture
def token_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target_root = tmp_path / "target" / "ntb_marimo_console"
    target_root.mkdir(parents=True)
    monkeypatch.setattr(probe, "_target_root", lambda: target_root)
    return target_root / ".state" / "schwab" / "test-token.json"


def streamer_payload() -> dict[str, object]:
    return {
        "accounts": [{"accountNumber": "123456789", "displayAcctId": "display-987"}],
        "streamerInfo": {
            "streamerSocketUrl": "wss://streamer-api.schwab.com/ws?credential=hidden",
            "schwabClientCustomerId": "raw-customer-id",
            "schwabClientCorrelId": "raw-correl-id",
            "schwabClientChannel": "raw-channel",
            "schwabClientFunctionId": "raw-function",
        },
    }


def test_dry_run_skips_websocket(capsys: pytest.CaptureFixture[str], token_path: Path) -> None:
    write_token(token_path)
    called = False

    async def login_func(credentials: object, access_token: str, *, timeout_seconds: float) -> int:
        nonlocal called
        called = True
        return 0

    exit_code = probe.run([], env=env_for(token_path), login_func=login_func)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert called is False
    assert "STREAM_LOGIN_DRY_RUN_PASS" in output
    assert "network_activity=SKIPPED_STREAM_LOGIN_DRY_RUN" in output
    assert "secret-access-token-value" not in output


def test_live_mode_gated_by_exact_true(capsys: pytest.CaptureFixture[str], token_path: Path) -> None:
    write_token(token_path)
    called = False

    def fetch_func(config: object, access_token: str) -> dict[str, object]:
        nonlocal called
        called = True
        return streamer_payload()

    exit_code = probe.run([], env=env_for(token_path, live="TRUE"), fetch_func=fetch_func)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert called is False
    assert "STREAM_LOGIN_DRY_RUN_PASS" in output


def test_unsafe_token_path_fails() -> None:
    with pytest.raises(probe.StreamLoginProbeError, match="under target/ntb_marimo_console/.state"):
        probe.load_config({"SCHWAB_TOKEN_PATH": "../token.json"})


def test_missing_access_token_fails(token_path: Path) -> None:
    token_path.parent.mkdir(parents=True)
    token_path.write_text(json.dumps({"refresh_token": "refresh"}), encoding="utf-8")

    with pytest.raises(probe.StreamLoginProbeError, match="access_token"):
        probe.load_access_token(token_path)


def test_missing_streamer_fields_fail() -> None:
    with pytest.raises(probe.StreamLoginProbeError, match="required streamer metadata"):
        probe.extract_streamer_credentials({"streamerInfo": {"streamerSocketUrl": "wss://example.test/ws"}})


def test_login_request_builder_includes_required_fields() -> None:
    credentials = probe.extract_streamer_credentials(streamer_payload())
    request = probe.build_login_request(credentials, "secret-access-token-value")
    login = request["requests"][0]

    assert login["service"] == "ADMIN"
    assert login["command"] == "LOGIN"
    assert login["SchwabClientCustomerId"] == "raw-customer-id"
    assert login["SchwabClientCorrelId"] == "raw-correl-id"
    assert login["parameters"]["Authorization"] == "secret-access-token-value"
    assert login["parameters"]["SchwabClientChannel"] == "raw-channel"
    assert login["parameters"]["SchwabClientFunctionId"] == "raw-function"


def test_success_output_is_safe(capsys: pytest.CaptureFixture[str], token_path: Path) -> None:
    write_token(token_path, access_token="raw-access-token")

    def fetch_func(config: object, access_token: str) -> dict[str, object]:
        assert access_token == "raw-access-token"
        return streamer_payload()

    async def login_func(credentials: object, access_token: str, *, timeout_seconds: float) -> int:
        assert access_token == "raw-access-token"
        return 0

    exit_code = probe.run([], env=env_for(token_path, live="true"), fetch_func=fetch_func, login_func=login_func)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "LOGIN_PASS" in output
    assert "streamer_socket_host=streamer-api.schwab.com" in output
    assert "login_response_code=0" in output
    assert "raw-access-token" not in output
    assert "secret-refresh" not in output
    assert "raw-customer-id" not in output
    assert "raw-correl-id" not in output
    assert "123456789" not in output
    assert "wss://streamer-api.schwab.com/ws?credential=hidden" not in output


def test_nonzero_response_code_fails_closed(capsys: pytest.CaptureFixture[str], token_path: Path) -> None:
    write_token(token_path)

    async def login_func(credentials: object, access_token: str, *, timeout_seconds: float) -> int:
        return 3

    exit_code = probe.run(
        [],
        env=env_for(token_path, live="true"),
        fetch_func=lambda config, access_token: streamer_payload(),
        login_func=login_func,
    )

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "LOGIN_FAIL" in output
    assert "login_response_code=3" in output
    assert "raw-customer-id" not in output


def test_malformed_response_fails() -> None:
    with pytest.raises(probe.StreamLoginProbeError, match="malformed"):
        probe.parse_login_response_code("not-json")
    with pytest.raises(probe.StreamLoginProbeError, match="content.code"):
        probe.parse_login_response_code(json.dumps({"response": [{"content": {}}]}))


def test_response_code_zero_passes() -> None:
    assert probe.parse_login_response_code(json.dumps({"response": [{"content": {"code": 0}}]})) == 0


def test_timeout_fails() -> None:
    credentials = probe.extract_streamer_credentials(streamer_payload())

    class SlowWebSocket:
        async def send(self, message: str) -> None:
            return None

        async def recv(self) -> str:
            await asyncio.sleep(0.05)
            return "{}"

    class Connection:
        async def __aenter__(self) -> SlowWebSocket:
            return SlowWebSocket()

        async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
            return None

    class FakeWebsockets:
        def connect(self, url: str) -> Connection:
            return Connection()

    with pytest.raises(probe.StreamLoginFailure) as exc_info:
        asyncio.run(
            probe.perform_streamer_login(
                credentials,
                "secret-access-token-value",
                timeout_seconds=0.001,
                websockets_module=FakeWebsockets(),
            )
        )

    assert exc_info.value.exception_class == "TimeoutError"


def test_missing_websockets_dependency_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    credentials = probe.extract_streamer_credentials(streamer_payload())

    def fake_import_module(name: str) -> object:
        raise ImportError("missing")

    monkeypatch.setattr(probe.importlib, "import_module", fake_import_module)

    with pytest.raises(probe.StreamLoginFailure) as exc_info:
        asyncio.run(probe.perform_streamer_login(credentials, "secret", timeout_seconds=1))

    assert exc_info.value.exception_class == "ImportError"


def test_websocket_login_sends_only_admin_login() -> None:
    credentials = probe.extract_streamer_credentials(streamer_payload())
    sent_messages: list[str] = []

    class WebSocket:
        async def send(self, message: str) -> None:
            sent_messages.append(message)

        async def recv(self) -> str:
            return json.dumps({"response": [{"content": {"code": 0}}]})

    class Connection:
        async def __aenter__(self) -> WebSocket:
            return WebSocket()

        async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
            return None

    class FakeWebsockets:
        def connect(self, url: str) -> Connection:
            assert url == "wss://streamer-api.schwab.com/ws?credential=hidden"
            return Connection()

    code = asyncio.run(
        probe.perform_streamer_login(
            credentials,
            "secret-access-token-value",
            timeout_seconds=1,
            websockets_module=FakeWebsockets(),
        )
    )

    assert code == 0
    assert len(sent_messages) == 1
    sent = json.loads(sent_messages[0])
    assert sent["requests"][0]["service"] == "ADMIN"
    assert sent["requests"][0]["command"] == "LOGIN"
    assert "LEVELONE_FUTURES" not in sent_messages[0]
