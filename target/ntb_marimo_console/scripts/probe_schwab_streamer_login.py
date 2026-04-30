#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import importlib
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


class StreamLoginProbeError(RuntimeError):
    pass


class StreamLoginFailure(StreamLoginProbeError):
    def __init__(
        self,
        message: str,
        *,
        exception_class: str | None = None,
        reason: object | None = None,
        http_status: int | None = None,
        login_response_code: int | None = None,
        streamer_socket_host: str = "",
    ) -> None:
        super().__init__(message)
        self.exception_class = exception_class
        self.reason = reason
        self.http_status = http_status
        self.login_response_code = login_response_code
        self.streamer_socket_host = streamer_socket_host


@dataclass(frozen=True)
class StreamLoginConfig:
    token_path: Path
    token_path_display: str
    live: bool
    timeout_seconds: float
    user_pref_url: str
    app_key: str
    app_secret: str
    token_url: str
    target_root: Path
    repo_root: Path


@dataclass(frozen=True)
class StreamerCredentials:
    streamer_socket_url: str
    streamer_socket_host: str
    schwab_client_customer_id: str
    schwab_client_correl_id: str
    schwab_client_channel: str
    schwab_client_function_id: str


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
        raise StreamLoginProbeError("SCHWAB_TOKEN_PATH must resolve under target/ntb_marimo_console/.state/.") from exc


def _parse_timeout(raw_value: str) -> float:
    try:
        timeout = float(raw_value)
    except ValueError as exc:
        raise StreamLoginProbeError("SCHWAB_STREAM_LOGIN_TIMEOUT_SECONDS must be numeric.") from exc
    if timeout <= 0:
        raise StreamLoginProbeError("SCHWAB_STREAM_LOGIN_TIMEOUT_SECONDS must be positive.")
    return timeout


def _sanitize_diagnostic_text(value: object) -> str:
    text = str(value)
    text = re.sub(r"(?i)(access_token|refresh_token|accountNumber|account_number)=([^&\s,}]+)", r"\1=[REDACTED]", text)
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", text)
    text = re.sub(r"\b[A-Za-z0-9._~+/=-]{24,}\b", "[REDACTED_TOKEN_LIKE]", text)
    return text


def load_config(env: dict[str, str] | None = None) -> StreamLoginConfig:
    values = os.environ if env is None else env
    target_root = _target_root()
    repo_root = _repo_root(target_root)
    raw_token_path = values.get("SCHWAB_TOKEN_PATH", ".state/schwab/token.json").strip()
    if not raw_token_path:
        raw_token_path = ".state/schwab/token.json"
    token_path = _resolve_token_path(raw_token_path, target_root=target_root)
    _require_under_state(token_path, target_root=target_root)

    timeout = _parse_timeout(values.get("SCHWAB_STREAM_LOGIN_TIMEOUT_SECONDS", "10").strip() or "10")
    return StreamLoginConfig(
        token_path=token_path,
        token_path_display=_repo_relative(token_path, repo_root=repo_root),
        live=values.get("SCHWAB_STREAM_LOGIN_LIVE", "").strip() == "true",
        timeout_seconds=timeout,
        user_pref_url=values.get("SCHWAB_USER_PREF_URL", DEFAULT_USER_PREF_URL).strip() or DEFAULT_USER_PREF_URL,
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
        raise StreamLoginProbeError(str(exc)) from exc


def fetch_user_preference(config: StreamLoginConfig, access_token: str) -> object:
    request = urllib.request.Request(
        config.user_pref_url,
        method="GET",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = getattr(response, "status", 200)
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise StreamLoginFailure(
            "User Preference request failed.",
            exception_class=exc.__class__.__name__,
            http_status=exc.code,
        ) from exc
    except urllib.error.URLError as exc:
        raise StreamLoginFailure(
            "User Preference request failed.",
            exception_class=exc.__class__.__name__,
            reason=getattr(exc, "reason", None),
        ) from exc
    if status != 200:
        raise StreamLoginFailure("User Preference request returned non-200.", exception_class="HTTPStatusError")
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise StreamLoginProbeError("User Preference response JSON is malformed.") from exc


def load_live_token(config: StreamLoginConfig) -> dict[str, Any]:
    try:
        return schwab_token_utils.load_token_with_refresh_if_needed(
            config.token_path,
            target_root=config.target_root,
            app_key=config.app_key,
            app_secret=config.app_secret,
            token_url=config.token_url,
        )
    except schwab_token_utils.SchwabTokenError as exc:
        raise StreamLoginProbeError(f"{exc} Fresh OAuth is required if refresh cannot complete.") from exc


def refresh_live_token(config: StreamLoginConfig) -> dict[str, Any]:
    try:
        return schwab_token_utils.refresh_token_file(
            config.token_path,
            target_root=config.target_root,
            app_key=config.app_key,
            app_secret=config.app_secret,
            token_url=config.token_url,
        )
    except schwab_token_utils.SchwabTokenError as exc:
        raise StreamLoginProbeError(f"{exc} Fresh OAuth is required if refresh cannot complete.") from exc


def fetch_user_preference_with_refresh_retry(
    config: StreamLoginConfig,
    *,
    fetch_func=fetch_user_preference,
) -> tuple[object, str]:
    token_data = load_live_token(config)
    access_token = schwab_token_utils.access_token_from(token_data)
    try:
        return fetch_func(config, access_token), access_token
    except StreamLoginFailure as exc:
        if getattr(exc, "http_status", None) != 401:
            raise
    token_data = refresh_live_token(config)
    access_token = schwab_token_utils.access_token_from(token_data)
    return fetch_func(config, access_token), access_token


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
    return isinstance(value, dict) and sum(1 for key in STREAMER_INFO_FIELD_KEYS if key in value) >= 2


def find_streamer_info(payload: object) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        if _looks_like_streamer_info(payload):
            return payload
        for key in ("streamerInfo", "streamer_info"):
            streamer_info = payload.get(key)
            if isinstance(streamer_info, dict):
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


def extract_streamer_credentials(payload: object) -> StreamerCredentials:
    streamer_info = find_streamer_info(payload)
    if not isinstance(streamer_info, dict):
        raise StreamLoginProbeError("User Preference response missing streamerInfo.")

    socket_url = _first_field(streamer_info, "streamerSocketUrl", "streamer_socket_url")
    customer_id = _first_field(streamer_info, "schwabClientCustomerId", "schwab_client_customer_id")
    correl_id = _first_field(streamer_info, "schwabClientCorrelId", "schwab_client_correl_id")
    channel = _first_field(streamer_info, "schwabClientChannel", "schwab_client_channel")
    function_id = _first_field(streamer_info, "schwabClientFunctionId", "schwab_client_function_id")
    values = (socket_url, customer_id, correl_id, channel, function_id)
    if not all(isinstance(value, str) and value.strip() for value in values):
        raise StreamLoginProbeError("User Preference response missing required streamer metadata.")

    parsed = urllib.parse.urlparse(str(socket_url).strip())
    if parsed.scheme not in {"ws", "wss"} or not parsed.netloc:
        raise StreamLoginProbeError("User Preference streamerSocketUrl is invalid.")
    return StreamerCredentials(
        streamer_socket_url=str(socket_url).strip(),
        streamer_socket_host=parsed.netloc,
        schwab_client_customer_id=str(customer_id).strip(),
        schwab_client_correl_id=str(correl_id).strip(),
        schwab_client_channel=str(channel).strip(),
        schwab_client_function_id=str(function_id).strip(),
    )


def build_login_request(credentials: StreamerCredentials, access_token: str) -> dict[str, object]:
    return {
        "requests": [
            {
                "service": "ADMIN",
                "command": "LOGIN",
                "requestid": "0",
                "SchwabClientCustomerId": credentials.schwab_client_customer_id,
                "SchwabClientCorrelId": credentials.schwab_client_correl_id,
                "parameters": {
                    "Authorization": access_token,
                    "SchwabClientChannel": credentials.schwab_client_channel,
                    "SchwabClientFunctionId": credentials.schwab_client_function_id,
                },
            }
        ]
    }


def parse_login_response_code(raw_message: str) -> int:
    try:
        message = json.loads(raw_message)
    except json.JSONDecodeError as exc:
        raise StreamLoginProbeError("Streamer LOGIN response JSON is malformed.") from exc
    if not isinstance(message, dict):
        raise StreamLoginProbeError("Streamer LOGIN response JSON must be an object.")
    responses = message.get("response")
    if not isinstance(responses, list) or not responses:
        raise StreamLoginProbeError("Streamer LOGIN response missing response list.")
    first = responses[0]
    if not isinstance(first, dict):
        raise StreamLoginProbeError("Streamer LOGIN response entry is malformed.")
    content = first.get("content")
    if not isinstance(content, dict) or "code" not in content:
        raise StreamLoginProbeError("Streamer LOGIN response missing content.code.")
    try:
        return int(content["code"])
    except (TypeError, ValueError) as exc:
        raise StreamLoginProbeError("Streamer LOGIN response code is not numeric.") from exc


async def perform_streamer_login(
    credentials: StreamerCredentials,
    access_token: str,
    *,
    timeout_seconds: float,
    websockets_module: object | None = None,
) -> int:
    if websockets_module is None:
        try:
            websockets_module = importlib.import_module("websockets")
        except ImportError as exc:
            raise StreamLoginFailure("websockets dependency is missing.", exception_class="ImportError") from exc
    request_json = json.dumps(build_login_request(credentials, access_token), separators=(",", ":"))
    try:
        async with websockets_module.connect(credentials.streamer_socket_url) as websocket:
            await asyncio.wait_for(websocket.send(request_json), timeout=timeout_seconds)
            raw_response = await asyncio.wait_for(websocket.recv(), timeout=timeout_seconds)
    except TimeoutError as exc:
        raise StreamLoginFailure(
            "Streamer LOGIN timed out.",
            exception_class=exc.__class__.__name__,
            streamer_socket_host=credentials.streamer_socket_host,
        ) from exc
    except Exception as exc:
        raise StreamLoginFailure(
            "Streamer WebSocket LOGIN failed.",
            exception_class=exc.__class__.__name__,
            reason=exc,
            streamer_socket_host=credentials.streamer_socket_host,
        ) from exc
    return parse_login_response_code(str(raw_response))


def print_config_summary(config: StreamLoginConfig) -> None:
    print("SCHWAB_STREAMER_LOGIN_PROBE")
    print(f"repo_root={config.repo_root}")
    print(f"target_root={_repo_relative(config.target_root, repo_root=config.repo_root)}")
    print(f"stream_login_live={config.live}")
    print(f"token_path={config.token_path_display}")
    print("token_path_safety=UNDER_TARGET_STATE")
    print("access_token=present")


def print_login_failure(exc: StreamLoginFailure) -> None:
    print("LOGIN_FAIL")
    if exc.streamer_socket_host:
        print(f"streamer_socket_host={exc.streamer_socket_host}")
    if exc.exception_class:
        print(f"exception_class={exc.exception_class}")
    if exc.reason is not None:
        print(f"reason={_sanitize_diagnostic_text(exc.reason)}")
    if exc.login_response_code is not None:
        print(f"login_response_code={exc.login_response_code}")


def run(
    argv: list[str] | None = None,
    *,
    env: dict[str, str] | None = None,
    fetch_func=fetch_user_preference,
    login_func=perform_streamer_login,
) -> int:
    parser = argparse.ArgumentParser(description="Probe Schwab Streamer ADMIN LOGIN only.")
    parser.parse_args(argv)

    try:
        config = load_config(env)
        access_token = load_access_token(config.token_path)
        print_config_summary(config)
        if not config.live:
            print("network_activity=SKIPPED_STREAM_LOGIN_DRY_RUN")
            print("STREAM_LOGIN_DRY_RUN_PASS")
            return 0

        payload, access_token = fetch_user_preference_with_refresh_retry(config, fetch_func=fetch_func)
        credentials = extract_streamer_credentials(payload)
        code = asyncio.run(login_func(credentials, access_token, timeout_seconds=config.timeout_seconds))
        if code != 0:
            raise StreamLoginFailure(
                "Streamer LOGIN was denied.",
                login_response_code=code,
                streamer_socket_host=credentials.streamer_socket_host,
            )
        print("LOGIN_PASS")
        print(f"streamer_socket_host={credentials.streamer_socket_host}")
        print("login_response_code=0")
        return 0
    except StreamLoginFailure as exc:
        print_login_failure(exc)
        return 1
    except StreamLoginProbeError as exc:
        print("LOGIN_FAIL")
        print(f"reason={_sanitize_diagnostic_text(exc)}")
        return 1


if __name__ == "__main__":
    sys.exit(run())
