from __future__ import annotations

import json
import os
import urllib.error
from pathlib import Path

import pytest

from ntb_marimo_console.schwab_token_lifecycle import (
    RefreshableAccessTokenProvider,
    SchwabTokenError,
    TokenRefreshResult,
)


def token_path_for(tmp_path: Path) -> Path:
    target_root = tmp_path / "target" / "ntb_marimo_console"
    return target_root / ".state" / "schwab" / "token.json"


def target_root_for(token_path: Path) -> Path:
    return token_path.parents[2]


def write_token(path: Path, token_data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(token_data), encoding="utf-8")


def read_token(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def make_provider(
    token_path: Path,
    *,
    clock_value: float,
    refresh_func=None,
    urlopen_func=None,
) -> RefreshableAccessTokenProvider:
    return RefreshableAccessTokenProvider(
        token_path=token_path,
        target_root=target_root_for(token_path),
        app_key="dummy-app-key",
        app_secret="dummy-app-secret",
        token_url="https://example.invalid/token",
        clock=lambda: clock_value,
        refresh_func=refresh_func,
        urlopen_func=urlopen_func or (lambda request, timeout: None),
    )


def test_fresh_token_is_returned_without_refresh(tmp_path: Path) -> None:
    token_path = token_path_for(tmp_path)
    write_token(
        token_path,
        {
            "access_token": "fresh-access",
            "refresh_token": "refresh",
            "_ntb_obtained_at_epoch": 1000,
            "expires_in": 3600,
        },
    )

    def refresh_func(*args, **kwargs):
        raise AssertionError("refresh_must_not_run_for_fresh_token")

    provider = make_provider(token_path, clock_value=1100, refresh_func=refresh_func)

    assert provider.load_access_token() == "fresh-access"
    write_token(
        token_path,
        {
            "access_token": "changed-on-disk",
            "refresh_token": "refresh",
            "_ntb_obtained_at_epoch": 1000,
            "expires_in": 3600,
        },
    )
    assert provider.load_access_token() == "fresh-access"
    assert provider.token_status() == {
        "valid": True,
        "expires_in_seconds": 3500,
        "last_refresh_at": None,
        "refresh_count": 0,
    }


def test_near_expiry_token_triggers_refresh_and_returns_new_token(tmp_path: Path) -> None:
    token_path = token_path_for(tmp_path)
    write_token(
        token_path,
        {
            "access_token": "old-access",
            "refresh_token": "old-refresh",
            "_ntb_expires_at_epoch": 1250,
        },
    )
    calls = {"count": 0}

    def refresh_func(*args, **kwargs):
        calls["count"] += 1
        return {
            "access_token": "new-access",
            "refresh_token": "old-refresh",
            "_ntb_expires_at_epoch": 4000,
        }

    provider = make_provider(token_path, clock_value=1000, refresh_func=refresh_func)

    assert provider.load_access_token() == "new-access"
    assert calls["count"] == 1
    assert provider.token_status()["refresh_count"] == 1


def test_expired_token_triggers_refresh_and_returns_new_token(tmp_path: Path) -> None:
    token_path = token_path_for(tmp_path)
    write_token(
        token_path,
        {
            "access_token": "old-access",
            "refresh_token": "old-refresh",
            "_ntb_expires_at_epoch": 900,
        },
    )

    provider = make_provider(
        token_path,
        clock_value=1000,
        refresh_func=lambda *args, **kwargs: {
            "access_token": "new-access",
            "refresh_token": "old-refresh",
            "_ntb_expires_at_epoch": 5000,
        },
    )

    assert provider.load_access_token() == "new-access"
    assert provider.token_status()["expires_in_seconds"] == 4000


def test_refresh_failure_returns_clear_error_and_does_not_crash(tmp_path: Path) -> None:
    token_path = token_path_for(tmp_path)
    write_token(
        token_path,
        {
            "access_token": "old-access",
            "refresh_token": "old-refresh",
            "_ntb_expires_at_epoch": 900,
        },
    )

    def refresh_func(*args, **kwargs):
        raise SchwabTokenError("Token refresh failed.", exception_class="HTTPError")

    provider = make_provider(token_path, clock_value=1000, refresh_func=refresh_func)

    result = provider.refresh_if_needed()

    assert result == TokenRefreshResult(
        succeeded=False,
        refreshed=False,
        reason="token_refresh_failed:HTTPError",
    )
    assert provider.token_status() == {
        "valid": False,
        "expires_in_seconds": 0,
        "last_refresh_at": None,
        "refresh_count": 0,
    }


def test_refresh_failure_from_load_access_token_is_clear(tmp_path: Path) -> None:
    token_path = token_path_for(tmp_path)
    write_token(
        token_path,
        {
            "access_token": "old-access",
            "refresh_token": "old-refresh",
            "_ntb_expires_at_epoch": 900,
        },
    )
    provider = make_provider(
        token_path,
        clock_value=1000,
        refresh_func=lambda *args, **kwargs: (_ for _ in ()).throw(
            SchwabTokenError("Token refresh failed.", exception_class="HTTPError")
        ),
    )

    with pytest.raises(SchwabTokenError, match="token_refresh_failed:HTTPError"):
        provider.load_access_token()


def test_refresh_writes_updated_token_back_to_file(tmp_path: Path) -> None:
    token_path = token_path_for(tmp_path)
    write_token(
        token_path,
        {
            "access_token": "old-access",
            "refresh_token": "old-refresh",
            "_ntb_expires_at_epoch": 900,
        },
    )

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"access_token":"new-access","expires_in":1800}'

    provider = make_provider(
        token_path,
        clock_value=1000,
        urlopen_func=lambda request, timeout: Response(),
    )

    assert provider.load_access_token() == "new-access"
    on_disk = read_token(token_path)
    assert on_disk["access_token"] == "new-access"
    assert on_disk["refresh_token"] == "old-refresh"
    assert "_ntb_expires_at_epoch" in on_disk


def test_token_status_returns_safe_structure(tmp_path: Path) -> None:
    token_path = token_path_for(tmp_path)
    write_token(
        token_path,
        {
            "access_token": "access",
            "refresh_token": "status-refresh-token-value",
            "created_at": 1000,
            "expires_in": 3600,
        },
    )
    provider = make_provider(token_path, clock_value=1200)

    assert provider.load_access_token() == "access"
    status = provider.token_status()

    assert set(status) == {
        "valid",
        "expires_in_seconds",
        "last_refresh_at",
        "refresh_count",
    }
    assert status["valid"] is True
    assert status["expires_in_seconds"] == 3400
    assert status["last_refresh_at"] is None
    assert status["refresh_count"] == 0
    assert "access" not in str(status)
    assert "status-refresh-token-value" not in str(status)


def test_expires_in_without_created_at_uses_token_file_timestamp(tmp_path: Path) -> None:
    token_path = token_path_for(tmp_path)
    write_token(
        token_path,
        {
            "access_token": "access",
            "refresh_token": "refresh",
            "expires_in": 3600,
        },
    )
    os.utime(token_path, (1000, 1000))
    provider = make_provider(token_path, clock_value=1100)

    assert provider.load_access_token() == "access"
    assert provider.token_status()["expires_in_seconds"] == 3500


def test_no_io_at_construction_time(tmp_path: Path) -> None:
    token_path = token_path_for(tmp_path)
    provider = make_provider(
        token_path,
        clock_value=1000,
        urlopen_func=lambda request, timeout: (_ for _ in ()).throw(
            urllib.error.URLError("must_not_call_network")
        ),
    )

    assert provider.token_status() == {
        "valid": False,
        "expires_in_seconds": None,
        "last_refresh_at": None,
        "refresh_count": 0,
    }
    assert not token_path.exists()
