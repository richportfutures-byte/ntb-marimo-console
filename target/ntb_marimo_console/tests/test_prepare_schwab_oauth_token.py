from __future__ import annotations

import importlib.util
import sys
import urllib.error
import urllib.parse
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "prepare_schwab_oauth_token.py"

spec = importlib.util.spec_from_file_location("prepare_schwab_oauth_token", SCRIPT_PATH)
oauth = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["prepare_schwab_oauth_token"] = oauth
spec.loader.exec_module(oauth)


def valid_env() -> dict[str, str]:
    return {
        "SCHWAB_APP_KEY": "dummy-app-key",
        "SCHWAB_APP_SECRET": "dummy-app-secret",
        "SCHWAB_CALLBACK_URL": "https://127.0.0.1:8182",
        "SCHWAB_TOKEN_PATH": ".state/schwab/token.json",
        "SCHWAB_OAUTH_LIVE": "false",
    }


@pytest.fixture(autouse=True)
def isolated_target_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target_root = tmp_path / "target" / "ntb_marimo_console"
    target_root.mkdir(parents=True)
    monkeypatch.setattr(oauth, "_target_root", lambda: target_root)
    return target_root


def test_dry_run_succeeds_with_dummy_values(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = oauth.run([], env=valid_env())

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "OAUTH_DRY_RUN_PASS" in output
    assert "network_activity=SKIPPED_OAUTH_DRY_RUN" in output
    assert "dummy-app-secret" not in output


def test_authorization_url_contains_expected_query_parameters() -> None:
    config = oauth.load_config(valid_env())
    parsed = urlparse(oauth.build_authorization_url(config))
    query = parse_qs(parsed.query)

    assert parsed.scheme == "https"
    assert parsed.netloc == "api.schwabapi.com"
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["dummy-app-key"]
    assert query["redirect_uri"] == ["https://127.0.0.1:8182"]
    assert query["scope"] == ["readonly"]


def test_authorization_url_scope_override_works() -> None:
    env = valid_env()
    env["SCHWAB_OAUTH_SCOPE"] = "readonly offline"
    config = oauth.load_config(env)
    parsed = urlparse(oauth.build_authorization_url(config))
    query = parse_qs(parsed.query)

    assert query["scope"] == ["readonly offline"]


def test_missing_env_vars_fail() -> None:
    env = valid_env()
    del env["SCHWAB_APP_SECRET"]

    with pytest.raises(oauth.OAuthPrepError, match="Missing required environment variables"):
        oauth.load_config(env)


def test_unsafe_token_path_fails() -> None:
    env = valid_env()
    env["SCHWAB_TOKEN_PATH"] = "../token.json"

    with pytest.raises(oauth.OAuthPrepError, match="under target/ntb_marimo_console/.state"):
        oauth.load_config(env)


def test_live_mode_without_exact_true_does_not_call_network(capsys: pytest.CaptureFixture[str]) -> None:
    called = False

    def exchange_func(config: object, code: str) -> dict[str, str]:
        nonlocal called
        called = True
        return {"access_token": "access", "refresh_token": "refresh"}

    env = valid_env()
    env["SCHWAB_OAUTH_LIVE"] = "TRUE"

    exit_code = oauth.run([], env=env, exchange_func=exchange_func)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert called is False
    assert "OAUTH_DRY_RUN_PASS" in output


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    (
        ("CO.raw-code-value", "CO.raw-code-value"),
        ("https://127.0.0.1:8182/?code=CO.abc%40x&state=ignored", "CO.abc@x"),
        ("https://127.0.0.1/?code=C0.xxx%40&session=abc", "C0.xxx@"),
    ),
)
def test_callback_url_code_extraction_works(raw_value: str, expected: str) -> None:
    assert oauth.extract_authorization_code(raw_value) == expected


def test_secret_and_tokens_are_not_printed(capsys: pytest.CaptureFixture[str]) -> None:
    env = valid_env()
    env["SCHWAB_OAUTH_LIVE"] = "true"

    def secret_input_func(prompt: str) -> str:
        return "CO.safe-code"

    def exchange_func(config: object, code: str) -> dict[str, str]:
        return {"access_token": "super-secret-access", "refresh_token": "super-secret-refresh"}

    def write_func(path: Path, token_response: dict[str, str]) -> None:
        return None

    exit_code = oauth.run(
        [],
        env=env,
        secret_input_func=secret_input_func,
        exchange_func=exchange_func,
        write_func=write_func,
    )

    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert exit_code == 0
    assert "TOKEN_WRITE_PASS" in output
    assert "code_present=yes code_shape=OTHER_PREFIX code_length=12" in output
    assert "dummy-app-secret" not in output
    assert "super-secret-access" not in output
    assert "super-secret-refresh" not in output
    assert "CO.safe-code" not in output


def test_callback_url_with_code_is_not_emitted_to_stdout_or_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    env = valid_env()
    env["SCHWAB_OAUTH_LIVE"] = "true"
    pasted_callback = "https://127.0.0.1:8182/?code=C0.callback-secret-code&state=ignored"

    def secret_input_func(prompt: str) -> str:
        return pasted_callback

    def exchange_func(config: object, code: str) -> dict[str, str]:
        assert code == "C0.callback-secret-code"
        return {"access_token": "access-token-value", "refresh_token": "refresh-token-value"}

    def write_func(path: Path, token_response: dict[str, str]) -> None:
        return None

    exit_code = oauth.run(
        [],
        env=env,
        secret_input_func=secret_input_func,
        exchange_func=exchange_func,
        write_func=write_func,
    )

    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert exit_code == 0
    assert "code_present=yes code_shape=C0_PREFIX code_length=23" in output
    assert pasted_callback not in output
    assert "CO.callback-secret-code" not in output
    assert "access-token-value" not in output
    assert "refresh-token-value" not in output


def test_existing_token_overwrite_requires_confirmation_logic(tmp_path: Path) -> None:
    token_path = tmp_path / "token.json"
    token_path.write_text("{}", encoding="utf-8")

    with pytest.raises(oauth.OAuthPrepError, match="overwrite was not confirmed"):
        oauth.confirm_overwrite(token_path, input_func=lambda prompt: "no")

    oauth.confirm_overwrite(token_path, input_func=lambda prompt: "OVERWRITE")


def test_http_error_diagnostics_are_safe(capsys: pytest.CaptureFixture[str]) -> None:
    env = valid_env()
    env["SCHWAB_OAUTH_LIVE"] = "true"

    def secret_input_func(prompt: str) -> str:
        return "CO.sensitive-auth-code"

    def exchange_func(config: object, code: str) -> dict[str, str]:
        raise oauth.TokenEndpointError(
            http_status=400,
            body=(
                '{"error":"invalid_grant",'
                '"error_description":"bad code=CO.sensitive-auth-code '
                'access_token=secret-access refresh_token=secret-refresh"}'
            ),
            exception_class="HTTPError",
        )

    exit_code = oauth.run([], env=env, secret_input_func=secret_input_func, exchange_func=exchange_func)

    captured = capsys.readouterr()
    output = captured.out + captured.err
    assert exit_code == 1
    assert "TOKEN_ENDPOINT_FAIL" in output
    assert "http_status=400" in output
    assert "exception_class=HTTPError" in output
    assert "invalid_grant" in output
    assert "CO.sensitive-auth-code" not in output
    assert "secret-access" not in output
    assert "secret-refresh" not in output


def test_token_endpoint_failure_without_status_reports_exception_class(
    capsys: pytest.CaptureFixture[str],
) -> None:
    env = valid_env()
    env["SCHWAB_OAUTH_LIVE"] = "true"

    def secret_input_func(prompt: str) -> str:
        return "C0.short"

    def exchange_func(config: object, code: str) -> dict[str, str]:
        raise oauth.TokenEndpointError(
            http_status=None,
            exception_class="URLError",
            reason_class="OSError",
            reason="connection failed with code=C0.secret-code and access_token=secret-access",
        )

    exit_code = oauth.run([], env=env, secret_input_func=secret_input_func, exchange_func=exchange_func)

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "TOKEN_ENDPOINT_FAIL" in output
    assert "exception_class=URLError" in output
    assert "reason_class=OSError" in output
    assert "reason=connection failed" in output
    assert "http_status=" not in output
    assert "C0.short" not in output
    assert "C0.secret-code" not in output
    assert "secret-access" not in output


def test_exchange_http_error_body_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    env = valid_env()
    config = oauth.load_config(env)

    class FakeHTTPError(urllib.error.HTTPError):
        def read(self) -> bytes:
            return (
                b'{"error":"invalid_client",'
                b'"error_description":"callback https://127.0.0.1/?code=CO.hidden-code '
                b'access_token=hidden-access refresh_token=hidden-refresh"}'
            )

    def fake_urlopen(request: object, timeout: int) -> object:
        raise FakeHTTPError(
            url="https://api.schwabapi.com/v1/oauth/token",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(oauth.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(oauth.TokenEndpointError) as exc_info:
        oauth.exchange_authorization_code(config, "CO.hidden-code")

    safe_body = oauth._safe_error_body(exc_info.value.body)
    assert exc_info.value.http_status == 401
    assert exc_info.value.exception_class == "FakeHTTPError"
    assert "invalid_client" in safe_body
    assert "CO.hidden-code" not in safe_body
    assert "hidden-access" not in safe_body
    assert "hidden-refresh" not in safe_body
    assert "https://127.0.0.1/?code=" not in safe_body


def test_http_error_is_caught_before_urlerror_and_reports_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = oauth.load_config(valid_env())

    class FakeHTTPError(urllib.error.HTTPError):
        def read(self) -> bytes:
            return b'{"error":"invalid_request","error_description":"bad code=C0.hidden"}'

    def fake_urlopen(request: object, timeout: int) -> object:
        raise FakeHTTPError(
            url="https://api.schwabapi.com/v1/oauth/token",
            code=411,
            msg="Length Required",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(oauth.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(oauth.TokenEndpointError) as exc_info:
        oauth.exchange_authorization_code(config, "C0.hidden")

    assert exc_info.value.exception_class == "FakeHTTPError"
    assert exc_info.value.http_status == 411
    assert exc_info.value.reason_class is None


def test_urlerror_reason_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    config = oauth.load_config(valid_env())

    def fake_urlopen(request: object, timeout: int) -> object:
        raise urllib.error.URLError("network code=C0.hidden access_token=secret-access")

    monkeypatch.setattr(oauth.urllib.request, "urlopen", fake_urlopen)

    with pytest.raises(oauth.TokenEndpointError) as exc_info:
        oauth.exchange_authorization_code(config, "C0.hidden")

    assert exc_info.value.exception_class == "URLError"
    assert exc_info.value.http_status is None
    assert exc_info.value.reason_class == "str"
    safe_reason = oauth._safe_reason(exc_info.value.reason)
    assert "C0.hidden" not in safe_reason
    assert "secret-access" not in safe_reason


def test_token_request_headers_and_body_are_form_encoded(monkeypatch: pytest.MonkeyPatch) -> None:
    config = oauth.load_config(valid_env())
    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"access_token":"access","refresh_token":"refresh"}'

    def fake_urlopen(request: object, timeout: int) -> FakeResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(oauth.urllib.request, "urlopen", fake_urlopen)

    token_response = oauth.exchange_authorization_code(config, "C0.decoded@code")

    request = captured["request"]
    body = request.data.decode("utf-8")
    parsed_body = urllib.parse.parse_qs(body)
    assert token_response == {"access_token": "access", "refresh_token": "refresh"}
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/x-www-form-urlencoded"
    assert request.get_header("Accept") == "application/json"
    assert request.get_header("Accept-encoding") == "identity"
    assert request.get_header("Content-length") == str(len(request.data))
    assert request.get_header("Authorization").startswith("Basic ")
    assert parsed_body == {
        "grant_type": ["authorization_code"],
        "code": ["C0.decoded@code"],
        "redirect_uri": ["https://127.0.0.1:8182"],
    }
    assert not body.strip().startswith("{")
