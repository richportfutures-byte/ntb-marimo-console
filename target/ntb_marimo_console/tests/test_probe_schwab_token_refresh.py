from __future__ import annotations

import importlib.util
import json
import sys
import urllib.error
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "probe_schwab_token_refresh.py"

spec = importlib.util.spec_from_file_location("probe_schwab_token_refresh", SCRIPT_PATH)
probe = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["probe_schwab_token_refresh"] = probe
spec.loader.exec_module(probe)


@pytest.fixture
def token_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target_root = tmp_path / "target" / "ntb_marimo_console"
    target_root.mkdir(parents=True)
    monkeypatch.setattr(probe, "_target_root", lambda: target_root)
    return target_root / ".state" / "schwab" / "token.json"


def write_token(path: Path, token_data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(token_data), encoding="utf-8")


def env_for(token_path: Path) -> dict[str, str]:
    return {
        "SCHWAB_APP_KEY": "dummy-app-key",
        "SCHWAB_APP_SECRET": "dummy-app-secret",
        "SCHWAB_TOKEN_PATH": str(token_path),
    }


def live_env_for(token_path: Path) -> dict[str, str]:
    env = env_for(token_path)
    env["SCHWAB_TOKEN_REFRESH_LIVE"] = "true"
    return env


def test_dry_run_is_default_and_does_not_refresh(capsys: pytest.CaptureFixture[str], token_path: Path) -> None:
    write_token(token_path, {"access_token": "old-access-token-value", "refresh_token": "old-refresh-token-value"})
    called = False

    def refresh_func(path: Path, **kwargs: object) -> dict[str, object]:
        nonlocal called
        called = True
        return {"access_token": "new-access-token-value", "refresh_token": "new-refresh-token-value"}

    exit_code = probe.run([], env=env_for(token_path), refresh_func=refresh_func)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert called is False
    assert "TOKEN_REFRESH_PASS" in output
    assert "refreshed_access_token=no" in output
    assert "token_file_rewritten=no" in output
    assert "old-access-token-value" not in output
    assert "old-refresh-token-value" not in output


def test_missing_credentials_fails_closed(capsys: pytest.CaptureFixture[str], token_path: Path) -> None:
    env = env_for(token_path)
    del env["SCHWAB_APP_SECRET"]

    exit_code = probe.run([], env=env)

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "TOKEN_REFRESH_FAIL" in output
    assert "dummy-app-secret" not in output


def test_unsafe_token_path_fails_closed(capsys: pytest.CaptureFixture[str], token_path: Path) -> None:
    env = env_for(token_path)
    env["SCHWAB_TOKEN_PATH"] = "../token.json"

    exit_code = probe.run([], env=env)

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "TOKEN_REFRESH_FAIL" in output
    assert "token_path_safety=UNDER_TARGET_STATE" not in output


def test_malformed_token_file_fails_closed(capsys: pytest.CaptureFixture[str], token_path: Path) -> None:
    token_path.parent.mkdir(parents=True)
    token_path.write_text("{not-json", encoding="utf-8")

    exit_code = probe.run([], env=env_for(token_path))

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "TOKEN_REFRESH_FAIL" in output
    assert "token_file_rewritten=no" in output


def test_missing_refresh_token_fails_closed(capsys: pytest.CaptureFixture[str], token_path: Path) -> None:
    write_token(token_path, {"access_token": "old-access"})

    exit_code = probe.run([], env=env_for(token_path))

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "refresh_token_present=no" in output
    assert "TOKEN_REFRESH_FAIL" in output


def test_successful_mocked_refresh_prints_pass(capsys: pytest.CaptureFixture[str], token_path: Path) -> None:
    write_token(token_path, {"access_token": "old-access-token-value", "refresh_token": "old-refresh-token-value"})

    def refresh_func(path: Path, **kwargs: object) -> dict[str, object]:
        assert path == token_path
        return {"access_token": "new-access-token-value", "refresh_token": "new-refresh-token-value"}

    exit_code = probe.run([], env=live_env_for(token_path), refresh_func=refresh_func)

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "SCHWAB_TOKEN_REFRESH_PROBE" in output
    assert "token_path_safety=UNDER_TARGET_STATE" in output
    assert "refresh_token_present=yes" in output
    assert "TOKEN_REFRESH_PASS" in output
    assert "refreshed_access_token=yes" in output
    assert "token_file_rewritten=yes" in output
    assert "old-access-token-value" not in output
    assert "old-refresh-token-value" not in output
    assert "new-access-token-value" not in output
    assert "new-refresh-token-value" not in output
    assert "dummy-app-secret" not in output


def test_failed_http_refresh_does_not_corrupt_existing_token_file(
    capsys: pytest.CaptureFixture[str],
    token_path: Path,
) -> None:
    original = {"access_token": "old-access-token-value", "refresh_token": "old-refresh-token-value"}
    write_token(token_path, original)

    def refresh_func(path: Path, **kwargs: object) -> dict[str, object]:
        raise probe.schwab_token_utils.SchwabTokenError(
            "Token refresh failed.",
            http_status=401,
            exception_class="HTTPError",
        )

    exit_code = probe.run([], env=live_env_for(token_path), refresh_func=refresh_func)

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "TOKEN_REFRESH_FAIL" in output
    assert "exception_class=HTTPError" in output
    assert "http_status=401" in output
    assert json.loads(token_path.read_text(encoding="utf-8")) == original
    assert "old-access-token-value" not in output
    assert "old-refresh-token-value" not in output


def test_output_never_contains_token_like_values_from_mocked_failure(
    capsys: pytest.CaptureFixture[str],
    token_path: Path,
) -> None:
    write_token(token_path, {"access_token": "secret-access-token-value", "refresh_token": "secret-refresh-token-value"})

    def refresh_func(path: Path, **kwargs: object) -> dict[str, object]:
        raise urllib.error.HTTPError("url", 500, "server leaked secret-refresh-token-value", None, None)

    exit_code = probe.run([], env=live_env_for(token_path), refresh_func=refresh_func)

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "secret-access-token-value" not in output
    assert "secret-refresh-token-value" not in output
    assert "dummy-app-secret" not in output
