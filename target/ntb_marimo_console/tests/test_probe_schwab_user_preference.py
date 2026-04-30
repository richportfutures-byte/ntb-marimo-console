from __future__ import annotations

import importlib.util
import json
import sys
import urllib.error
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "probe_schwab_user_preference.py"

spec = importlib.util.spec_from_file_location("probe_schwab_user_preference", SCRIPT_PATH)
probe = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["probe_schwab_user_preference"] = probe
spec.loader.exec_module(probe)


def write_token(path: Path, access_token: str = "secret-access-token-value") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"access_token": access_token, "refresh_token": "secret-refresh"}), encoding="utf-8")


def env_for(token_path: Path, *, live: str = "false") -> dict[str, str]:
    return {
        "SCHWAB_TOKEN_PATH": str(token_path),
        "SCHWAB_USER_PREF_LIVE": live,
    }


@pytest.fixture
def token_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target_root = tmp_path / "target" / "ntb_marimo_console"
    target_root.mkdir(parents=True)
    monkeypatch.setattr(probe, "_target_root", lambda: target_root)
    return target_root / ".state" / "schwab" / "test-token.json"


def test_dry_run_succeeds_without_network(capsys: pytest.CaptureFixture[str], token_path: Path) -> None:
    write_token(token_path)
    called = False

    def fetch_func(config: object, access_token: str) -> dict[str, object]:
        nonlocal called
        called = True
        return {}

    exit_code = probe.run([], env=env_for(token_path), fetch_func=fetch_func)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert called is False
    assert "USER_PREF_DRY_RUN_PASS" in output
    assert "network_activity=SKIPPED_USER_PREF_DRY_RUN" in output
    assert "secret-access-token-value" not in output


def test_unsafe_token_path_fails() -> None:
    with pytest.raises(probe.UserPreferenceProbeError, match="under target/ntb_marimo_console/.state"):
        probe.load_config({"SCHWAB_TOKEN_PATH": "../token.json"})


def test_missing_access_token_fails(token_path: Path) -> None:
    token_path.parent.mkdir(parents=True)
    token_path.write_text(json.dumps({"refresh_token": "refresh"}), encoding="utf-8")

    with pytest.raises(probe.UserPreferenceProbeError, match="access_token"):
        probe.load_access_token(token_path)


def test_live_request_is_gated_by_exact_true(capsys: pytest.CaptureFixture[str], token_path: Path) -> None:
    write_token(token_path)
    called = False

    def fetch_func(config: object, access_token: str) -> dict[str, object]:
        nonlocal called
        called = True
        return {}

    exit_code = probe.run([], env=env_for(token_path, live="TRUE"), fetch_func=fetch_func)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert called is False
    assert "USER_PREF_DRY_RUN_PASS" in output


def test_success_response_prints_only_presence_flags_and_host(
    capsys: pytest.CaptureFixture[str],
    token_path: Path,
) -> None:
    write_token(token_path, access_token="do-not-print-access-token")

    def fetch_func(config: object, access_token: str) -> dict[str, object]:
        assert access_token == "do-not-print-access-token"
        return {
            "streamerInfo": {
                "streamerSocketUrl": "wss://streamer-api.schwab.com/ws?token=secret",
                "schwabClientCustomerId": "raw-customer-id",
                "schwabClientCorrelId": "raw-correl-id",
                "schwabClientChannel": "raw-channel",
                "schwabClientFunctionId": "raw-function",
            }
        }

    exit_code = probe.run([], env=env_for(token_path, live="true"), fetch_func=fetch_func)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "USER_PREF_PASS" in output
    assert "streamer_socket_url_present=yes" in output
    assert "streamer_socket_host=streamer-api.schwab.com" in output
    assert "schwab_client_customer_id_present=yes" in output
    assert "schwab_client_correl_id_present=yes" in output
    assert "schwab_client_channel_present=yes" in output
    assert "schwab_client_function_id_present=yes" in output
    assert "do-not-print-access-token" not in output
    assert "raw-customer-id" not in output
    assert "raw-correl-id" not in output
    assert "raw-channel" not in output
    assert "raw-function" not in output
    assert "token=secret" not in output


def test_observed_live_accounts_offers_streamer_info_shape_succeeds(
    capsys: pytest.CaptureFixture[str],
    token_path: Path,
) -> None:
    write_token(token_path, access_token="raw-access-token")
    full_socket_url = "wss://observed-streamer.schwab.test/ws?credential=hidden"

    def fetch_func(config: object, access_token: str) -> dict[str, object]:
        assert access_token == "raw-access-token"
        return {
            "accounts": [
                {
                    "accountNumber": "123456789",
                    "displayAcctId": "display-987",
                    "description": "masked fixture account",
                }
            ],
            "offers": [{"level": "streamer"}],
            "streamerInfo": {
                "schwabClientChannel": "raw-channel-value",
                "schwabClientCorrelId": "raw-correl-value",
                "schwabClientCustomerId": "raw-customer-value",
                "schwabClientFunctionId": "raw-function-value",
                "streamerSocketUrl": full_socket_url,
            },
        }

    exit_code = probe.run([], env=env_for(token_path, live="true"), fetch_func=fetch_func)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "USER_PREF_PASS" in output
    assert "streamer_socket_url_present=yes" in output
    assert "streamer_socket_host=observed-streamer.schwab.test" in output
    assert "schwab_client_customer_id_present=yes" in output
    assert "schwab_client_correl_id_present=yes" in output
    assert "schwab_client_channel_present=yes" in output
    assert "schwab_client_function_id_present=yes" in output
    assert "123456789" not in output
    assert "display-987" not in output
    assert "raw-customer-value" not in output
    assert "raw-correl-value" not in output
    assert full_socket_url not in output
    assert "raw-access-token" not in output
    assert "secret-refresh" not in output


def test_top_level_snake_case_streamer_info_is_supported(capsys: pytest.CaptureFixture[str], token_path: Path) -> None:
    write_token(token_path)

    def fetch_func(config: object, access_token: str) -> dict[str, object]:
        return {
            "streamer_info": {
                "streamer_socket_url": "wss://snake-streamer.schwab.test/ws?secret=hidden",
                "schwab_client_customer_id": "raw-sensitive-customer",
                "schwab_client_correl_id": "raw-sensitive-correl",
                "schwab_client_channel": "raw-sensitive-channel",
                "schwab_client_function_id": "raw-sensitive-function",
            }
        }

    exit_code = probe.run([], env=env_for(token_path, live="true"), fetch_func=fetch_func)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "USER_PREF_PASS" in output
    assert "streamer_socket_host=snake-streamer.schwab.test" in output
    assert "raw-sensitive-customer" not in output
    assert "raw-sensitive-correl" not in output
    assert "secret=hidden" not in output


def test_list_response_containing_streamer_info_is_supported(capsys: pytest.CaptureFixture[str], token_path: Path) -> None:
    write_token(token_path)

    def fetch_func(config: object, access_token: str) -> list[dict[str, object]]:
        return [
            {"name": "first"},
            {
                "streamerInfo": {
                    "streamerSocketUrl": "wss://list-streamer.schwab.test/ws",
                    "schwabClientCustomerId": "raw-sensitive-customer",
                }
            },
        ]

    exit_code = probe.run([], env=env_for(token_path, live="true"), fetch_func=fetch_func)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "streamer_socket_host=list-streamer.schwab.test" in output
    assert "schwab_client_customer_id_present=yes" in output
    assert "raw-sensitive-customer" not in output


def test_wrapper_object_containing_list_response_is_supported(
    capsys: pytest.CaptureFixture[str],
    token_path: Path,
) -> None:
    write_token(token_path)

    def fetch_func(config: object, access_token: str) -> dict[str, object]:
        return {
            "userPreferences": [
                {
                    "nested": {
                        "streamer_info": {
                            "streamer_socket_url": "wss://wrapped-streamer.schwab.test/ws",
                            "schwab_client_function_id": "raw-sensitive-function",
                        }
                    }
                }
            ]
        }

    exit_code = probe.run([], env=env_for(token_path, live="true"), fetch_func=fetch_func)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "streamer_socket_host=wrapped-streamer.schwab.test" in output
    assert "schwab_client_function_id_present=yes" in output
    assert "raw-sensitive-function" not in output


def test_missing_streamer_info_prints_sanitized_shape_only(
    capsys: pytest.CaptureFixture[str],
    token_path: Path,
) -> None:
    write_token(token_path)

    def fetch_func(config: object, access_token: str) -> dict[str, object]:
        return {
            "accounts": [
                {
                    "accountNumber": "123456789",
                    "customerId": "raw-customer",
                    "authorization": "Bearer secret-access-token-value",
                }
            ],
            "metadata": {
                "nested": {
                    "streamerSocketUrl": "wss://should-not-print.example/ws?token=hidden",
                    "other": "safe-value",
                }
            },
        }

    exit_code = probe.run([], env=env_for(token_path, live="true"), fetch_func=fetch_func)

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "USER_PREF_FAIL" in output
    assert "response_type=object" in output
    assert "top_level_keys=accounts,metadata" in output
    assert "nested_key_paths=" in output
    assert "accounts.accountNumber" in output
    assert "metadata.nested.streamerSocketUrl" in output
    assert "123456789" not in output
    assert "raw-customer" not in output
    assert "secret-access-token-value" not in output
    assert "wss://should-not-print.example" not in output
    assert "safe-value" not in output


def test_http_error_diagnostics_are_sanitized(capsys: pytest.CaptureFixture[str], token_path: Path) -> None:
    write_token(token_path)

    def fetch_func(config: object, access_token: str) -> dict[str, object]:
        raise probe.UserPreferenceEndpointError(
            http_status=403,
            body='{"error":"invalid_token","message":"Bearer secret-access-token-value accountNumber=123456789"}',
            exception_class="HTTPError",
        )

    exit_code = probe.run([], env=env_for(token_path, live="true"), fetch_func=fetch_func)

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "USER_PREF_FAIL" in output
    assert "exception_class=HTTPError" in output
    assert "http_status=403" in output
    assert "invalid_token" in output
    assert "secret-access-token-value" not in output
    assert "123456789" not in output


def test_401_triggers_exactly_one_refresh_and_one_retry(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    token_path: Path,
) -> None:
    write_token(token_path, access_token="old-access")
    calls: list[str] = []

    def refresh_token_file(*args: object, **kwargs: object) -> dict[str, object]:
        calls.append("refresh")
        return {"access_token": "new-access", "refresh_token": "new-refresh"}

    def fetch_func(config: object, access_token: str) -> dict[str, object]:
        calls.append(access_token)
        if access_token == "old-access":
            raise probe.UserPreferenceEndpointError(http_status=401, exception_class="HTTPError")
        assert access_token == "new-access"
        return {
            "streamerInfo": {
                "streamerSocketUrl": "wss://streamer-api.schwab.com/ws",
                "schwabClientCustomerId": "customer",
                "schwabClientCorrelId": "correl",
                "schwabClientChannel": "channel",
                "schwabClientFunctionId": "function",
            }
        }

    monkeypatch.setattr(probe.schwab_token_utils, "refresh_token_file", refresh_token_file)

    exit_code = probe.run([], env=env_for(token_path, live="true"), fetch_func=fetch_func)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert calls == ["old-access", "refresh", "new-access"]
    assert "USER_PREF_PASS" in output
    assert "old-access" not in output
    assert "new-access" not in output


def test_urlerror_diagnostics_are_sanitized(capsys: pytest.CaptureFixture[str], token_path: Path) -> None:
    write_token(token_path)

    def fetch_func(config: object, access_token: str) -> dict[str, object]:
        raise probe.UserPreferenceEndpointError(
            http_status=None,
            exception_class="URLError",
            reason_class="str",
            reason="network failed with Bearer secret-access-token-value",
        )

    exit_code = probe.run([], env=env_for(token_path, live="true"), fetch_func=fetch_func)

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "exception_class=URLError" in output
    assert "reason_class=str" in output
    assert "secret-access-token-value" not in output


def test_fetch_request_uses_bearer_and_accept_json(monkeypatch: pytest.MonkeyPatch, token_path: Path) -> None:
    config = probe.load_config({"SCHWAB_TOKEN_PATH": str(token_path), "SCHWAB_USER_PREF_LIVE": "true"})
    captured: dict[str, object] = {}

    class FakeResponse:
        status = 200

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"streamerInfo": {"streamerSocketUrl": "wss://example.test/ws"}}'

    def fake_urlopen(request: object, timeout: int) -> FakeResponse:
        captured["request"] = request
        return FakeResponse()

    monkeypatch.setattr(probe.urllib.request, "urlopen", fake_urlopen)

    payload = probe.fetch_user_preference(config, "secret-access-token-value")

    request = captured["request"]
    assert payload["streamerInfo"]["streamerSocketUrl"] == "wss://example.test/ws"
    assert request.get_method() == "GET"
    assert request.get_header("Authorization") == "Bearer secret-access-token-value"
    assert request.get_header("Accept") == "application/json"


def test_fetch_http_error_is_sanitized(monkeypatch: pytest.MonkeyPatch, token_path: Path) -> None:
    config = probe.load_config({"SCHWAB_TOKEN_PATH": str(token_path), "SCHWAB_USER_PREF_LIVE": "true"})

    class FakeHTTPError(urllib.error.HTTPError):
        def read(self) -> bytes:
            return b'{"message":"bad access_token=secret-access-token-value refresh_token=secret-refresh"}'

    def fake_urlopen(request: object, timeout: int) -> object:
        raise FakeHTTPError("url", 403, "Forbidden", None, None)

    monkeypatch.setattr(probe.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(probe.UserPreferenceEndpointError) as exc_info:
        probe.fetch_user_preference(config, "secret-access-token-value")

    safe_body = probe._safe_error_body(exc_info.value.body)
    assert exc_info.value.http_status == 403
    assert "secret-access-token-value" not in safe_body
    assert "secret-refresh" not in safe_body


def test_missing_streamer_info_fails() -> None:
    with pytest.raises(probe.MissingStreamerInfoError, match="streamerInfo"):
        probe.summarize_streamer_info({})
