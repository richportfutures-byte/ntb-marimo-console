#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import schwab_token_utils
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import schwab_token_utils


DEFAULT_USER_PREF_URL = "https://api.schwabapi.com/trader/v1/userPreference"


class UserPreferenceProbeError(RuntimeError):
    pass


class UserPreferenceEndpointError(UserPreferenceProbeError):
    def __init__(
        self,
        *,
        http_status: int | None,
        body: str = "",
        exception_class: str | None = None,
        reason_class: str | None = None,
        reason: object | None = None,
    ) -> None:
        super().__init__("USER_PREF_ENDPOINT_FAIL")
        self.http_status = http_status
        self.body = body
        self.exception_class = exception_class
        self.reason_class = reason_class
        self.reason = reason


class MissingStreamerInfoError(UserPreferenceProbeError):
    def __init__(self, payload: object) -> None:
        super().__init__("User Preference response missing streamerInfo.")
        self.payload = payload


@dataclass(frozen=True)
class UserPreferenceConfig:
    token_path: Path
    token_path_display: str
    user_pref_url: str
    live: bool
    app_key: str
    app_secret: str
    token_url: str
    target_root: Path
    repo_root: Path


@dataclass(frozen=True)
class StreamerInfoSummary:
    streamer_socket_url_present: bool
    streamer_socket_host: str
    schwab_client_customer_id_present: bool
    schwab_client_correl_id_present: bool
    schwab_client_channel_present: bool
    schwab_client_function_id_present: bool


def _target_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _repo_root(target_root: Path) -> Path:
    return target_root.parents[1]


def _repo_relative(path: Path, *, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def _resolve_token_path(raw_value: str, *, target_root: Path) -> Path:
    return schwab_token_utils.resolve_token_path(raw_value, target_root=target_root)


def _require_under_state(token_path: Path, *, target_root: Path) -> None:
    try:
        schwab_token_utils.require_under_state(token_path, target_root=target_root)
    except schwab_token_utils.SchwabTokenError as exc:
        raise UserPreferenceProbeError(
            "SCHWAB_TOKEN_PATH must resolve under target/ntb_marimo_console/.state/."
        ) from exc


def _sanitize_diagnostic_text(value: object) -> str:
    text = str(value)
    text = re.sub(r"(?i)(access_token|refresh_token|accountNumber|account_number)=([^&\s,}]+)", r"\1=[REDACTED]", text)
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", text)
    text = re.sub(r"\b[A-Za-z0-9._~+/=-]{24,}\b", "[REDACTED_TOKEN_LIKE]", text)
    return text


def _safe_error_body(raw_body: str) -> str:
    if not raw_body.strip():
        return ""
    try:
        parsed = json.loads(raw_body)
    except json.JSONDecodeError:
        return _sanitize_diagnostic_text(raw_body)
    if not isinstance(parsed, dict):
        return _sanitize_diagnostic_text(raw_body)

    safe_fields: dict[str, str] = {}
    for key in ("error", "error_description", "message"):
        if key in parsed:
            safe_fields[key] = _sanitize_diagnostic_text(parsed[key])
    if safe_fields:
        return json.dumps(safe_fields, sort_keys=True)
    return _sanitize_diagnostic_text(raw_body)


def _safe_reason(reason: object | None) -> str:
    if reason is None:
        return ""
    return _sanitize_diagnostic_text(reason)


def load_config(env: dict[str, str] | None = None) -> UserPreferenceConfig:
    values = os.environ if env is None else env
    target_root = _target_root()
    repo_root = _repo_root(target_root)
    raw_token_path = values.get("SCHWAB_TOKEN_PATH", ".state/schwab/token.json").strip()
    if not raw_token_path:
        raw_token_path = ".state/schwab/token.json"
    token_path = _resolve_token_path(raw_token_path, target_root=target_root)
    _require_under_state(token_path, target_root=target_root)

    user_pref_url = values.get("SCHWAB_USER_PREF_URL", DEFAULT_USER_PREF_URL).strip() or DEFAULT_USER_PREF_URL
    return UserPreferenceConfig(
        token_path=token_path,
        token_path_display=_repo_relative(token_path, repo_root=repo_root),
        user_pref_url=user_pref_url,
        live=values.get("SCHWAB_USER_PREF_LIVE", "").strip() == "true",
        app_key=values.get("SCHWAB_APP_KEY", "").strip(),
        app_secret=values.get("SCHWAB_APP_SECRET", "").strip(),
        token_url=values.get("SCHWAB_OAUTH_TOKEN_URL", schwab_token_utils.DEFAULT_TOKEN_URL).strip()
        or schwab_token_utils.DEFAULT_TOKEN_URL,
        target_root=target_root,
        repo_root=repo_root,
    )


def load_access_token(token_path: Path) -> str:
    try:
        token_data = schwab_token_utils.load_token_json(token_path, target_root=_target_root())
        return schwab_token_utils.access_token_from(token_data)
    except schwab_token_utils.SchwabTokenError as exc:
        raise UserPreferenceProbeError(str(exc)) from exc


def fetch_user_preference(config: UserPreferenceConfig, access_token: str) -> object:
    request = urllib.request.Request(
        config.user_pref_url,
        method="GET",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = getattr(response, "status", 200)
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        raise UserPreferenceEndpointError(
            http_status=exc.code,
            body=body,
            exception_class=exc.__class__.__name__,
        ) from exc
    except urllib.error.URLError as exc:
        reason = getattr(exc, "reason", None)
        raise UserPreferenceEndpointError(
            http_status=None,
            exception_class=exc.__class__.__name__,
            reason_class=reason.__class__.__name__ if reason is not None else None,
            reason=reason,
        ) from exc

    if status != 200:
        raise UserPreferenceEndpointError(http_status=status, body=body, exception_class="HTTPStatusError")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise UserPreferenceProbeError("User Preference response JSON is malformed.") from exc
    return payload


def load_live_token(config: UserPreferenceConfig) -> dict[str, Any]:
    try:
        return schwab_token_utils.load_token_with_refresh_if_needed(
            config.token_path,
            target_root=config.target_root,
            app_key=config.app_key,
            app_secret=config.app_secret,
            token_url=config.token_url,
        )
    except schwab_token_utils.SchwabTokenError as exc:
        raise UserPreferenceProbeError(f"{exc} Fresh OAuth is required if refresh cannot complete.") from exc


def refresh_live_token(config: UserPreferenceConfig) -> dict[str, Any]:
    try:
        return schwab_token_utils.refresh_token_file(
            config.token_path,
            target_root=config.target_root,
            app_key=config.app_key,
            app_secret=config.app_secret,
            token_url=config.token_url,
        )
    except schwab_token_utils.SchwabTokenError as exc:
        raise UserPreferenceProbeError(f"{exc} Fresh OAuth is required if refresh cannot complete.") from exc


def fetch_user_preference_with_refresh_retry(
    config: UserPreferenceConfig,
    *,
    fetch_func=fetch_user_preference,
) -> object:
    token_data = load_live_token(config)
    access_token = schwab_token_utils.access_token_from(token_data)
    try:
        return fetch_func(config, access_token)
    except UserPreferenceEndpointError as exc:
        if exc.http_status != 401:
            raise
    token_data = refresh_live_token(config)
    access_token = schwab_token_utils.access_token_from(token_data)
    return fetch_func(config, access_token)


STREAMER_INFO_FIELD_KEYS: tuple[str, ...] = (
    "streamerSocketUrl",
    "streamer_socket_url",
    "schwabClientCustomerId",
    "schwab_client_customer_id",
    "schwabClientCorrelId",
    "schwab_client_correl_id",
    "schwabClientChannel",
    "schwab_client_channel",
    "schwabClientFunctionId",
    "schwab_client_function_id",
)


def _looks_like_streamer_info(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    recognized_key_count = sum(1 for key in STREAMER_INFO_FIELD_KEYS if key in value)
    return recognized_key_count >= 2


def find_streamer_info(payload: object) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        if _looks_like_streamer_info(payload):
            return payload
        for key in ("streamerInfo", "streamer_info"):
            streamer_info = payload.get(key)
            if _looks_like_streamer_info(streamer_info):
                return streamer_info
            found = find_streamer_info(streamer_info)
            if found is not None:
                return found
        for child in payload.values():
            found = find_streamer_info(child)
            if found is not None:
                return found
    elif isinstance(payload, list):
        for item in payload:
            found = find_streamer_info(item)
            if found is not None:
                return found
    return None


def _first_field(mapping: dict[str, Any], *keys: str) -> object:
    for key in keys:
        if key in mapping:
            return mapping[key]
    return None


def summarize_streamer_info(payload: object) -> StreamerInfoSummary:
    streamer_info = find_streamer_info(payload)
    if not isinstance(streamer_info, dict):
        raise MissingStreamerInfoError(payload)
    socket_url = _first_field(streamer_info, "streamerSocketUrl", "streamer_socket_url")
    socket_url_text = socket_url.strip() if isinstance(socket_url, str) else ""
    parsed_socket_url = urllib.parse.urlparse(socket_url_text) if socket_url_text else None
    return StreamerInfoSummary(
        streamer_socket_url_present=bool(socket_url_text),
        streamer_socket_host=parsed_socket_url.netloc if parsed_socket_url else "",
        schwab_client_customer_id_present=bool(
            _first_field(streamer_info, "schwabClientCustomerId", "schwab_client_customer_id")
        ),
        schwab_client_correl_id_present=bool(
            _first_field(streamer_info, "schwabClientCorrelId", "schwab_client_correl_id")
        ),
        schwab_client_channel_present=bool(
            _first_field(streamer_info, "schwabClientChannel", "schwab_client_channel")
        ),
        schwab_client_function_id_present=bool(
            _first_field(streamer_info, "schwabClientFunctionId", "schwab_client_function_id")
        ),
    )


def _type_name(value: object) -> str:
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "list"
    return type(value).__name__


def _safe_key(key: object) -> str:
    return str(key).replace("\n", " ").replace("\r", " ")


def _top_level_keys(payload: object) -> tuple[str, ...]:
    if isinstance(payload, dict):
        return tuple(sorted(_safe_key(key) for key in payload.keys()))
    if isinstance(payload, list):
        keys: set[str] = set()
        for item in payload:
            if isinstance(item, dict):
                keys.update(_safe_key(key) for key in item.keys())
        return tuple(sorted(keys))
    return ()


def _nested_key_paths(payload: object, *, max_depth: int = 3) -> tuple[str, ...]:
    paths: set[str] = set()

    def visit(value: object, prefix: tuple[str, ...], depth: int) -> None:
        if depth >= max_depth:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                key_text = _safe_key(key)
                path = (*prefix, key_text)
                paths.add(".".join(path))
                visit(child, path, depth + 1)
        elif isinstance(value, list):
            for item in value:
                visit(item, prefix, depth)

    visit(payload, (), 0)
    return tuple(sorted(paths))


def print_missing_streamer_shape(payload: object) -> None:
    print(f"response_type={_type_name(payload)}")
    top_keys = _top_level_keys(payload)
    print(f"top_level_keys={','.join(top_keys) if top_keys else '(none)'}")
    nested_paths = _nested_key_paths(payload, max_depth=3)
    print(f"nested_key_paths={','.join(nested_paths) if nested_paths else '(none)'}")


def print_summary(config: UserPreferenceConfig) -> None:
    print("SCHWAB_USER_PREFERENCE_PROBE")
    print(f"repo_root={config.repo_root}")
    print(f"target_root={_repo_relative(config.target_root, repo_root=config.repo_root)}")
    print(f"user_pref_live={config.live}")
    print(f"token_path={config.token_path_display}")
    print("token_path_safety=UNDER_TARGET_STATE")
    print("access_token=present")


def print_streamer_info(summary: StreamerInfoSummary) -> None:
    print("USER_PREF_PASS")
    print(f"streamer_socket_url_present={'yes' if summary.streamer_socket_url_present else 'no'}")
    print(f"streamer_socket_host={summary.streamer_socket_host}")
    print(
        "schwab_client_customer_id_present="
        f"{'yes' if summary.schwab_client_customer_id_present else 'no'}"
    )
    print(
        "schwab_client_correl_id_present="
        f"{'yes' if summary.schwab_client_correl_id_present else 'no'}"
    )
    print(
        "schwab_client_channel_present="
        f"{'yes' if summary.schwab_client_channel_present else 'no'}"
    )
    print(
        "schwab_client_function_id_present="
        f"{'yes' if summary.schwab_client_function_id_present else 'no'}"
    )


def run(
    argv: list[str] | None = None,
    *,
    env: dict[str, str] | None = None,
    fetch_func=fetch_user_preference,
) -> int:
    parser = argparse.ArgumentParser(description="Probe Schwab User Preference with a local OAuth token file.")
    parser.parse_args(argv)

    try:
        config = load_config(env)
        access_token = load_access_token(config.token_path)
        print_summary(config)
        if not config.live:
            print("network_activity=SKIPPED_USER_PREF_DRY_RUN")
            print("USER_PREF_DRY_RUN_PASS")
            return 0
        payload = fetch_user_preference_with_refresh_retry(config, fetch_func=fetch_func)
        summary = summarize_streamer_info(payload)
        print_streamer_info(summary)
        return 0
    except UserPreferenceEndpointError as exc:
        print("USER_PREF_FAIL")
        if exc.exception_class:
            print(f"exception_class={exc.exception_class}")
        if exc.http_status is not None:
            print(f"http_status={exc.http_status}")
        safe_body = _safe_error_body(exc.body)
        if safe_body:
            print(f"error_body={safe_body}")
        if exc.reason_class:
            print(f"reason_class={exc.reason_class}")
        safe_reason = _safe_reason(exc.reason)
        if safe_reason:
            print(f"reason={safe_reason}")
        return 1
    except MissingStreamerInfoError as exc:
        print("USER_PREF_FAIL")
        print("error=User Preference response missing streamerInfo.")
        print_missing_streamer_shape(exc.payload)
        return 1
    except UserPreferenceProbeError as exc:
        print("USER_PREF_FAIL")
        print(f"error={exc}")
        return 1


if __name__ == "__main__":
    sys.exit(run())
