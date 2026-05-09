from __future__ import annotations

import base64
import importlib.util
import json
import stat
import sys
import urllib.error
import urllib.parse
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "schwab_token_utils.py"

spec = importlib.util.spec_from_file_location("schwab_token_utils", SCRIPT_PATH)
tokens = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["schwab_token_utils"] = tokens
spec.loader.exec_module(tokens)


@pytest.fixture
def token_path(tmp_path: Path) -> Path:
    target_root = tmp_path / "target" / "ntb_marimo_console"
    target_root.mkdir(parents=True)
    return target_root / ".state" / "schwab" / "token.json"


def target_root_for(token_path: Path) -> Path:
    return token_path.parents[2]


def write_token(path: Path, token_data: dict[str, object]) -> None:
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(token_data), encoding="utf-8")


def test_refresh_request_body_and_basic_auth_are_constructed() -> None:
    request = tokens.build_refresh_request(
        token_url="https://api.schwabapi.com/v1/oauth/token",
        app_key="dummy-app-key",
        app_secret="dummy-app-secret",
        refresh_token="dummy-refresh-token",
    )

    body = request.data.decode("utf-8")
    parsed = urllib.parse.parse_qs(body)
    auth_header = request.get_header("Authorization")
    decoded = base64.b64decode(auth_header.removeprefix("Basic ")).decode("utf-8")
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/x-www-form-urlencoded"
    assert request.get_header("Accept") == "application/json"
    assert request.get_header("Accept-encoding") == "identity"
    assert parsed == {"grant_type": ["refresh_token"], "refresh_token": ["dummy-refresh-token"]}
    assert decoded == "dummy-app-key:dummy-app-secret"
    assert "dummy-app-secret" not in str(request.headers)
    assert "dummy-refresh-token" not in str(request.headers)


def test_unsafe_token_path_fails_closed(tmp_path: Path) -> None:
    target_root = tmp_path / "target" / "ntb_marimo_console"
    target_root.mkdir(parents=True)
    unsafe = tmp_path / "token.json"

    with pytest.raises(tokens.SchwabTokenError, match="under target/ntb_marimo_console/.state"):
        tokens.load_token_json(unsafe, target_root=target_root)


def test_missing_refresh_token_fails_closed(token_path: Path) -> None:
    write_token(token_path, {"access_token": "access"})

    with pytest.raises(tokens.SchwabTokenError, match="refresh_token"):
        tokens.refresh_token_file(
            token_path,
            target_root=target_root_for(token_path),
            app_key="key",
            app_secret="secret",
        )


def test_malformed_token_file_fails_closed(token_path: Path) -> None:
    token_path.parent.mkdir(parents=True)
    token_path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(tokens.SchwabTokenError, match="malformed"):
        tokens.load_token_json(token_path, target_root=target_root_for(token_path))


def test_validate_token_contract_reports_missing_refresh_without_values(token_path: Path) -> None:
    write_token(token_path, {"access_token": "secret-access-token-value"})

    report = tokens.validate_token_contract(token_path, target_root=target_root_for(token_path))

    assert report.status_fields() == {
        "token_file_present": "yes",
        "token_file_parseable": "yes",
        "token_contract_valid": "no",
        "access_token_present": "yes",
        "refresh_token_present": "no",
        "token_fresh": "unknown",
        "blocking_reason": "refresh_token_missing",
    }
    assert "secret-access-token-value" not in str(report.status_fields())


def test_validate_token_contract_reports_malformed_file_without_contents(token_path: Path) -> None:
    token_path.parent.mkdir(parents=True)
    token_path.write_text("{not-json", encoding="utf-8")

    report = tokens.validate_token_contract(token_path, target_root=target_root_for(token_path))

    assert report.token_file_present is True
    assert report.token_file_parseable is False
    assert report.token_contract_valid is False
    assert report.blocking_reason == "token_file_unparseable"
    assert "{not-json" not in str(report.status_fields())


def test_validate_token_contract_reports_refresh_capable_unknown_freshness(token_path: Path) -> None:
    write_token(token_path, {"access_token": "access", "refresh_token": "refresh"})

    report = tokens.validate_token_contract(token_path, target_root=target_root_for(token_path))

    assert report.token_contract_valid is True
    assert report.access_token_present is True
    assert report.refresh_token_present is True
    assert report.token_fresh == "unknown"
    assert report.blocking_reason == "none"


def test_validate_token_contract_reports_expired_refresh_capable_token(token_path: Path) -> None:
    write_token(
        token_path,
        {
            "access_token": "access",
            "refresh_token": "refresh",
            "_ntb_expires_at_epoch": 1000,
        },
    )

    report = tokens.validate_token_contract(token_path, target_root=target_root_for(token_path), now_epoch=2000)

    assert report.token_contract_valid is True
    assert report.token_fresh == "no"
    assert report.blocking_reason == "none"


def test_successful_refresh_atomically_updates_token_file(token_path: Path) -> None:
    write_token(token_path, {"access_token": "old-access", "refresh_token": "old-refresh"})

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"access_token":"new-access","expires_in":1800}'

    refreshed = tokens.refresh_token_file(
        token_path,
        target_root=target_root_for(token_path),
        app_key="key",
        app_secret="secret",
        urlopen_func=lambda request, timeout: Response(),
    )

    on_disk = json.loads(token_path.read_text(encoding="utf-8"))
    assert refreshed["access_token"] == "new-access"
    assert refreshed["refresh_token"] == "old-refresh"
    assert on_disk["access_token"] == "new-access"
    assert on_disk["refresh_token"] == "old-refresh"
    assert "_ntb_expires_at_epoch" in on_disk
    if hasattr(stat, "S_IMODE"):
        assert stat.S_IMODE(token_path.stat().st_mode) & 0o077 == 0


def test_refresh_response_with_new_refresh_token_rotates_persisted_refresh_token(token_path: Path) -> None:
    write_token(token_path, {"access_token": "old-access", "refresh_token": "old-refresh"})

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"access_token":"new-access","refresh_token":"new-refresh","expires_in":1800}'

    refreshed = tokens.refresh_token_file(
        token_path,
        target_root=target_root_for(token_path),
        app_key="key",
        app_secret="secret",
        urlopen_func=lambda request, timeout: Response(),
    )

    on_disk = json.loads(token_path.read_text(encoding="utf-8"))
    assert refreshed["refresh_token"] == "new-refresh"
    assert on_disk["refresh_token"] == "new-refresh"


def test_refresh_response_with_blank_refresh_token_preserves_existing_refresh_token(token_path: Path) -> None:
    write_token(token_path, {"access_token": "old-access", "refresh_token": "old-refresh"})

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"access_token":"new-access","refresh_token":"   ","expires_in":1800}'

    refreshed = tokens.refresh_token_file(
        token_path,
        target_root=target_root_for(token_path),
        app_key="key",
        app_secret="secret",
        urlopen_func=lambda request, timeout: Response(),
    )

    on_disk = json.loads(token_path.read_text(encoding="utf-8"))
    assert refreshed["access_token"] == "new-access"
    assert refreshed["refresh_token"] == "old-refresh"
    assert on_disk["refresh_token"] == "old-refresh"


def test_failed_refresh_does_not_corrupt_token_file(token_path: Path) -> None:
    original = {"access_token": "old-access", "refresh_token": "old-refresh"}
    write_token(token_path, original)

    def failing_urlopen(request: object, timeout: int) -> object:
        raise urllib.error.HTTPError("url", 401, "Unauthorized", None, None)

    with pytest.raises(tokens.SchwabTokenError):
        tokens.refresh_token_file(
            token_path,
            target_root=target_root_for(token_path),
            app_key="key",
            app_secret="secret",
            urlopen_func=failing_urlopen,
        )

    assert json.loads(token_path.read_text(encoding="utf-8")) == original


def test_refresh_response_without_access_token_does_not_create_partial_artifact(token_path: Path) -> None:
    original = {"access_token": "old-access", "refresh_token": "old-refresh"}
    write_token(token_path, original)

    class Response:
        def __enter__(self) -> "Response":
            return self

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"refresh_token":"new-refresh"}'

    with pytest.raises(tokens.SchwabTokenError, match="access_token"):
        tokens.refresh_token_file(
            token_path,
            target_root=target_root_for(token_path),
            app_key="key",
            app_secret="secret",
            urlopen_func=lambda request, timeout: Response(),
        )

    assert json.loads(token_path.read_text(encoding="utf-8")) == original
