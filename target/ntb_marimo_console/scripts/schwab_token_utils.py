from __future__ import annotations

import base64
import json
import os
import stat
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_TOKEN_URL = "https://api.schwabapi.com/v1/oauth/token"


class SchwabTokenError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        exception_class: str | None = None,
        reason: object | None = None,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.exception_class = exception_class
        self.reason = reason


@dataclass(frozen=True)
class TokenContractReport:
    token_file_present: bool
    token_file_parseable: bool
    token_contract_valid: bool
    access_token_present: bool
    refresh_token_present: bool
    token_fresh: str
    blocking_reason: str

    def status_fields(self) -> dict[str, str]:
        return {
            "token_file_present": _yes_no(self.token_file_present),
            "token_file_parseable": _yes_no(self.token_file_parseable),
            "token_contract_valid": _yes_no(self.token_contract_valid),
            "access_token_present": _yes_no(self.access_token_present),
            "refresh_token_present": _yes_no(self.refresh_token_present),
            "token_fresh": self.token_fresh,
            "blocking_reason": self.blocking_reason,
        }


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def resolve_token_path(raw_value: str, *, target_root: Path) -> Path:
    token_path = Path(raw_value).expanduser()
    if not token_path.is_absolute():
        token_path = target_root / token_path
    return token_path.resolve(strict=False)


def require_under_state(token_path: Path, *, target_root: Path) -> None:
    state_root = (target_root / ".state").resolve(strict=False)
    try:
        token_path.relative_to(state_root)
    except ValueError as exc:
        raise SchwabTokenError("SCHWAB_TOKEN_PATH must resolve under target/ntb_marimo_console/.state/.") from exc


def load_token_json(token_path: Path, *, target_root: Path) -> dict[str, Any]:
    require_under_state(token_path, target_root=target_root)
    if not token_path.exists():
        raise SchwabTokenError("Token file is missing.")
    try:
        token_data = json.loads(token_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SchwabTokenError("Token file JSON is malformed.") from exc
    if not isinstance(token_data, dict):
        raise SchwabTokenError("Token file JSON must be an object.")
    return token_data


def access_token_from(token_data: dict[str, Any]) -> str:
    access_token = token_data.get("access_token")
    if not isinstance(access_token, str) or not access_token.strip():
        raise SchwabTokenError("Token file must contain access_token.")
    return access_token.strip()


def refresh_token_from(token_data: dict[str, Any]) -> str:
    refresh_token = token_data.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token.strip():
        raise SchwabTokenError("Token file must contain refresh_token.")
    return refresh_token.strip()


def _token_string_present(token_data: dict[str, Any], key: str) -> bool:
    value = token_data.get(key)
    return isinstance(value, str) and bool(value.strip())


def _numeric_token_value(token_data: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = token_data.get(key)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                continue
    return None


def _has_freshness_metadata(token_data: dict[str, Any]) -> bool:
    explicit_expiry = _numeric_token_value(
        token_data,
        "expires_at",
        "expires_at_epoch",
        "expires_at_epoch_seconds",
        "_ntb_expires_at_epoch",
    )
    issued_at = _numeric_token_value(token_data, "issued_at", "obtained_at", "_ntb_obtained_at_epoch")
    expires_in = _numeric_token_value(token_data, "expires_in")
    return explicit_expiry is not None or (issued_at is not None and expires_in is not None)


def token_is_expired_or_near_expiry(
    token_data: dict[str, Any],
    *,
    now_epoch: float | None = None,
    skew_seconds: float = 120,
) -> bool:
    now = time.time() if now_epoch is None else now_epoch
    explicit_expiry = _numeric_token_value(
        token_data,
        "expires_at",
        "expires_at_epoch",
        "expires_at_epoch_seconds",
        "_ntb_expires_at_epoch",
    )
    if explicit_expiry is not None:
        return explicit_expiry <= now + skew_seconds

    issued_at = _numeric_token_value(token_data, "issued_at", "obtained_at", "_ntb_obtained_at_epoch")
    expires_in = _numeric_token_value(token_data, "expires_in")
    if issued_at is not None and expires_in is not None:
        return issued_at + expires_in <= now + skew_seconds
    return False


def token_freshness_status(
    token_data: dict[str, Any],
    *,
    now_epoch: float | None = None,
    skew_seconds: float = 120,
) -> str:
    if not _has_freshness_metadata(token_data):
        return "unknown"
    return "no" if token_is_expired_or_near_expiry(token_data, now_epoch=now_epoch, skew_seconds=skew_seconds) else "yes"


def validate_token_contract(
    token_path: Path,
    *,
    target_root: Path,
    now_epoch: float | None = None,
) -> TokenContractReport:
    try:
        require_under_state(token_path, target_root=target_root)
    except SchwabTokenError:
        return TokenContractReport(
            token_file_present=False,
            token_file_parseable=False,
            token_contract_valid=False,
            access_token_present=False,
            refresh_token_present=False,
            token_fresh="unknown",
            blocking_reason="token_path_outside_target_state",
        )

    if not token_path.exists():
        return TokenContractReport(
            token_file_present=False,
            token_file_parseable=False,
            token_contract_valid=False,
            access_token_present=False,
            refresh_token_present=False,
            token_fresh="unknown",
            blocking_reason="token_file_missing",
        )

    try:
        token_data = json.loads(token_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return TokenContractReport(
            token_file_present=True,
            token_file_parseable=False,
            token_contract_valid=False,
            access_token_present=False,
            refresh_token_present=False,
            token_fresh="unknown",
            blocking_reason="token_file_unparseable",
        )
    if not isinstance(token_data, dict):
        return TokenContractReport(
            token_file_present=True,
            token_file_parseable=False,
            token_contract_valid=False,
            access_token_present=False,
            refresh_token_present=False,
            token_fresh="unknown",
            blocking_reason="token_file_not_object",
        )

    access_token_present = _token_string_present(token_data, "access_token")
    refresh_token_present = _token_string_present(token_data, "refresh_token")
    if not access_token_present:
        return TokenContractReport(
            token_file_present=True,
            token_file_parseable=True,
            token_contract_valid=False,
            access_token_present=False,
            refresh_token_present=refresh_token_present,
            token_fresh="unknown",
            blocking_reason="access_token_missing",
        )
    if not refresh_token_present:
        return TokenContractReport(
            token_file_present=True,
            token_file_parseable=True,
            token_contract_valid=False,
            access_token_present=True,
            refresh_token_present=False,
            token_fresh="unknown",
            blocking_reason="refresh_token_missing",
        )

    return TokenContractReport(
        token_file_present=True,
        token_file_parseable=True,
        token_contract_valid=True,
        access_token_present=True,
        refresh_token_present=True,
        token_fresh=token_freshness_status(token_data, now_epoch=now_epoch),
        blocking_reason="none",
    )


def build_refresh_request(
    *,
    token_url: str,
    app_key: str,
    app_secret: str,
    refresh_token: str,
) -> urllib.request.Request:
    payload = urllib.parse.urlencode(
        {"grant_type": "refresh_token", "refresh_token": refresh_token}
    ).encode("utf-8")
    credentials = f"{app_key}:{app_secret}".encode("utf-8")
    basic_auth = base64.b64encode(credentials).decode("ascii")
    return urllib.request.Request(
        token_url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Basic {basic_auth}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "Content-Length": str(len(payload)),
        },
    )


def _merged_refresh_response(old_token: dict[str, Any], refreshed: dict[str, Any]) -> dict[str, Any]:
    access_token = refreshed.get("access_token")
    if not isinstance(access_token, str) or not access_token.strip():
        raise SchwabTokenError("Refresh response must contain access_token.")
    merged = {**old_token, **refreshed}
    if not isinstance(merged.get("refresh_token"), str) or not str(merged["refresh_token"]).strip():
        merged["refresh_token"] = refresh_token_from(old_token)
    now = time.time()
    merged["_ntb_obtained_at_epoch"] = now
    expires_in = _numeric_token_value(merged, "expires_in")
    if expires_in is not None:
        merged["_ntb_expires_at_epoch"] = now + expires_in
    return merged


def write_token_json_atomic(token_path: Path, token_data: dict[str, Any]) -> None:
    token_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=".token.", suffix=".tmp", dir=token_path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(token_data, handle, indent=2, sort_keys=True)
            handle.write("\n")
        try:
            os.chmod(temp_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
        temp_path.replace(token_path)
        try:
            os.chmod(token_path, stat.S_IRUSR | stat.S_IWUSR)
        except OSError:
            pass
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def refresh_token_file(
    token_path: Path,
    *,
    target_root: Path,
    app_key: str,
    app_secret: str,
    token_url: str = DEFAULT_TOKEN_URL,
    urlopen_func=urllib.request.urlopen,
) -> dict[str, Any]:
    if not app_key.strip() or not app_secret.strip():
        raise SchwabTokenError("SCHWAB_APP_KEY and SCHWAB_APP_SECRET are required for token refresh.")
    token_data = load_token_json(token_path, target_root=target_root)
    refresh_token = refresh_token_from(token_data)
    request = build_refresh_request(
        token_url=token_url,
        app_key=app_key.strip(),
        app_secret=app_secret.strip(),
        refresh_token=refresh_token,
    )
    try:
        with urlopen_func(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise SchwabTokenError(
            "Token refresh failed.",
            http_status=exc.code,
            exception_class=exc.__class__.__name__,
        ) from exc
    except urllib.error.URLError as exc:
        raise SchwabTokenError(
            "Token refresh failed.",
            exception_class=exc.__class__.__name__,
            reason=getattr(exc, "reason", None),
        ) from exc
    try:
        refreshed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise SchwabTokenError("Token refresh response JSON is malformed.") from exc
    if not isinstance(refreshed, dict):
        raise SchwabTokenError("Token refresh response JSON must be an object.")
    merged = _merged_refresh_response(token_data, refreshed)
    write_token_json_atomic(token_path, merged)
    return merged


def load_token_with_refresh_if_needed(
    token_path: Path,
    *,
    target_root: Path,
    app_key: str,
    app_secret: str,
    token_url: str = DEFAULT_TOKEN_URL,
    urlopen_func=urllib.request.urlopen,
) -> dict[str, Any]:
    token_data = load_token_json(token_path, target_root=target_root)
    access_token_from(token_data)
    refresh_token_from(token_data)
    if token_is_expired_or_near_expiry(token_data):
        return refresh_token_file(
            token_path,
            target_root=target_root,
            app_key=app_key,
            app_secret=app_secret,
            token_url=token_url,
            urlopen_func=urlopen_func,
        )
    return token_data
