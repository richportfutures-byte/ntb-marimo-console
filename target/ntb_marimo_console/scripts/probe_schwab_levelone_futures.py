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

LEVELONE_FUTURES_FIELDS: dict[int, str] = {
    0: "Symbol",
    1: "Bid Price",
    2: "Ask Price",
    3: "Last Price",
    4: "Bid Size",
    5: "Ask Size",
    8: "Total Volume",
    9: "Last Size",
    10: "Quote Time",
    11: "Trade Time",
    12: "High Price",
    13: "Low Price",
    14: "Close Price",
    18: "Open Price",
    19: "Net Change",
    20: "Future Percent Change",
    22: "Security Status",
    23: "Open Interest",
    24: "Mark",
    25: "Tick",
    26: "Tick Amount",
    27: "Product",
    28: "Future Price Format",
    29: "Future Trading Hours",
    30: "Future Is Tradable",
    31: "Future Multiplier",
    32: "Future Is Active",
    33: "Future Settlement Price",
    34: "Future Active Symbol",
    35: "Future Expiration Date",
    37: "Ask Time",
    38: "Bid Time",
    39: "Quoted In Session",
}

FUTURES_MONTH_CODES: dict[str, str] = {
    "F": "January",
    "G": "February",
    "H": "March",
    "J": "April",
    "K": "May",
    "M": "June",
    "N": "July",
    "Q": "August",
    "U": "September",
    "V": "October",
    "X": "November",
    "Z": "December",
}

SYMBOL_PATTERN = re.compile(r"^/(?P<root>[A-Z0-9]{1,6})(?P<month>[FGHJKMNQUVXZ])(?P<year>\d{2})$")


@dataclass(frozen=True)
class ProbeConfig:
    app_key_present: bool
    app_secret_present: bool
    app_key: str
    app_secret: str
    callback_url: str
    token_path: Path
    token_path_display: str
    futures_symbol: str
    futures_root: str
    futures_month_code: str
    futures_month_name: str
    futures_year: str
    stream_fields: tuple[int, ...]
    timeout_seconds: float
    dry_run: bool
    token_url: str
    repo_root: Path
    target_root: Path


class ValidationError(RuntimeError):
    pass


class LiveProbeError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        exception_class: str | None = None,
        reason: object | None = None,
        http_status: int | None = None,
        streamer_socket_host: str = "",
        login_response_code: int | None = None,
        subscription_response_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.exception_class = exception_class
        self.reason = reason
        self.http_status = http_status
        self.streamer_socket_host = streamer_socket_host
        self.login_response_code = login_response_code
        self.subscription_response_code = subscription_response_code


@dataclass(frozen=True)
class StreamerCredentials:
    streamer_socket_url: str
    streamer_socket_host: str
    schwab_client_customer_id: str
    schwab_client_correl_id: str
    schwab_client_channel: str
    schwab_client_function_id: str


@dataclass(frozen=True)
class LiveProbeResult:
    streamer_socket_host: str
    login_response_code: int
    subscription_response_code: int
    market_data: dict[int, object]


def _target_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _repo_root(target_root: Path) -> Path:
    return target_root.parents[1]


def _parse_bool(value: str | None, *, default: bool) -> bool:
    if value is None or not value.strip():
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValidationError("SCHWAB_PROBE_DRY_RUN must be true or false.")


def _resolve_token_path(raw_value: str, *, target_root: Path) -> Path:
    return schwab_token_utils.resolve_token_path(raw_value, target_root=target_root)


def _require_under_state(token_path: Path, *, target_root: Path) -> None:
    try:
        schwab_token_utils.require_under_state(token_path, target_root=target_root)
    except schwab_token_utils.SchwabTokenError as exc:
        raise ValidationError(
            "SCHWAB_TOKEN_PATH must resolve under target/ntb_marimo_console/.state/."
        ) from exc


def _parse_symbol(raw_value: str) -> tuple[str, str, str, str]:
    symbol = raw_value.strip().upper()
    match = SYMBOL_PATTERN.fullmatch(symbol)
    if not match:
        raise ValidationError(
            "SCHWAB_FUTURES_SYMBOL must use an explicit futures contract like /ESM26, not a root-only symbol like /ES."
        )
    month_code = match.group("month")
    return (
        match.group("root"),
        month_code,
        FUTURES_MONTH_CODES[month_code],
        match.group("year"),
    )


def _parse_fields(raw_value: str) -> tuple[int, ...]:
    parts = [part.strip() for part in raw_value.split(",")]
    if not parts or any(not part for part in parts):
        raise ValidationError("SCHWAB_STREAM_FIELDS must be a comma-separated list of numeric field IDs.")
    fields: list[int] = []
    for part in parts:
        if not part.isdigit():
            raise ValidationError("SCHWAB_STREAM_FIELDS must contain only numeric Schwab field IDs.")
        field_id = int(part)
        if field_id not in LEVELONE_FUTURES_FIELDS:
            raise ValidationError(f"Unsupported LEVELONE_FUTURES field ID: {field_id}.")
        fields.append(field_id)
    return tuple(fields)


def _parse_timeout(raw_value: str) -> float:
    try:
        timeout = float(raw_value)
    except ValueError as exc:
        raise ValidationError("SCHWAB_PROBE_TIMEOUT_SECONDS must be numeric.") from exc
    if timeout <= 0:
        raise ValidationError("SCHWAB_PROBE_TIMEOUT_SECONDS must be positive.")
    return timeout


def _sanitize_diagnostic_text(value: object) -> str:
    text = str(value)
    text = re.sub(r"(?i)(access_token|refresh_token|accountNumber|account_number)=([^&\s,}]+)", r"\1=[REDACTED]", text)
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", text)
    text = re.sub(r"\b[A-Za-z0-9._~+/=-]{24,}\b", "[REDACTED_TOKEN_LIKE]", text)
    return text


def load_config(env: dict[str, str] | None = None, *, force_dry_run: bool = False) -> ProbeConfig:
    values = os.environ if env is None else env
    target_root = _target_root()
    repo_root = _repo_root(target_root)

    required = {
        "SCHWAB_APP_KEY": values.get("SCHWAB_APP_KEY", ""),
        "SCHWAB_APP_SECRET": values.get("SCHWAB_APP_SECRET", ""),
        "SCHWAB_CALLBACK_URL": values.get("SCHWAB_CALLBACK_URL", ""),
        "SCHWAB_TOKEN_PATH": values.get("SCHWAB_TOKEN_PATH", ""),
        "SCHWAB_FUTURES_SYMBOL": values.get("SCHWAB_FUTURES_SYMBOL", ""),
        "SCHWAB_STREAM_FIELDS": values.get("SCHWAB_STREAM_FIELDS", ""),
        "SCHWAB_PROBE_TIMEOUT_SECONDS": values.get("SCHWAB_PROBE_TIMEOUT_SECONDS", ""),
    }
    missing = tuple(name for name, value in required.items() if not value.strip())
    if missing:
        raise ValidationError(f"Missing required environment variables: {', '.join(missing)}.")

    token_path = _resolve_token_path(required["SCHWAB_TOKEN_PATH"], target_root=target_root)
    _require_under_state(token_path, target_root=target_root)

    root, month_code, month_name, year = _parse_symbol(required["SCHWAB_FUTURES_SYMBOL"])
    fields = _parse_fields(required["SCHWAB_STREAM_FIELDS"])
    timeout = _parse_timeout(required["SCHWAB_PROBE_TIMEOUT_SECONDS"])
    dry_run = True if force_dry_run else _parse_bool(values.get("SCHWAB_PROBE_DRY_RUN"), default=True)

    return ProbeConfig(
        app_key_present=True,
        app_secret_present=True,
        app_key=required["SCHWAB_APP_KEY"].strip(),
        app_secret=required["SCHWAB_APP_SECRET"].strip(),
        callback_url=required["SCHWAB_CALLBACK_URL"].strip(),
        token_path=token_path,
        token_path_display=_repo_relative(token_path, repo_root=repo_root),
        futures_symbol=required["SCHWAB_FUTURES_SYMBOL"].strip().upper(),
        futures_root=root,
        futures_month_code=month_code,
        futures_month_name=month_name,
        futures_year=year,
        stream_fields=fields,
        timeout_seconds=timeout,
        dry_run=dry_run,
        token_url=values.get("SCHWAB_OAUTH_TOKEN_URL", schwab_token_utils.DEFAULT_TOKEN_URL).strip()
        or schwab_token_utils.DEFAULT_TOKEN_URL,
        repo_root=repo_root,
        target_root=target_root,
    )


def load_access_token(token_path: Path) -> str:
    try:
        token_data = schwab_token_utils.load_token_json(token_path, target_root=_target_root())
        return schwab_token_utils.access_token_from(token_data)
    except schwab_token_utils.SchwabTokenError as exc:
        raise LiveProbeError(str(exc)) from exc


def load_live_token(config: ProbeConfig) -> dict[str, Any]:
    try:
        return schwab_token_utils.load_token_with_refresh_if_needed(
            config.token_path,
            target_root=config.target_root,
            app_key=config.app_key,
            app_secret=config.app_secret,
            token_url=config.token_url,
        )
    except schwab_token_utils.SchwabTokenError as exc:
        raise LiveProbeError(f"{exc} Fresh OAuth is required if refresh cannot complete.") from exc


def refresh_live_token(config: ProbeConfig) -> dict[str, Any]:
    try:
        return schwab_token_utils.refresh_token_file(
            config.token_path,
            target_root=config.target_root,
            app_key=config.app_key,
            app_secret=config.app_secret,
            token_url=config.token_url,
        )
    except schwab_token_utils.SchwabTokenError as exc:
        raise LiveProbeError(f"{exc} Fresh OAuth is required if refresh cannot complete.") from exc


def fetch_user_preference(access_token: str) -> object:
    request = urllib.request.Request(
        DEFAULT_USER_PREF_URL,
        method="GET",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            status = getattr(response, "status", 200)
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise LiveProbeError(
            "User Preference request failed.",
            exception_class=exc.__class__.__name__,
            http_status=exc.code,
        ) from exc
    except urllib.error.URLError as exc:
        raise LiveProbeError(
            "User Preference request failed.",
            exception_class=exc.__class__.__name__,
            reason=getattr(exc, "reason", None),
        ) from exc
    if status != 200:
        raise LiveProbeError("User Preference request returned non-200.", exception_class="HTTPStatusError")
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise LiveProbeError("User Preference response JSON is malformed.") from exc


def fetch_user_preference_with_refresh_retry(
    config: ProbeConfig,
    *,
    fetch_func=fetch_user_preference,
) -> tuple[object, str]:
    token_data = load_live_token(config)
    access_token = schwab_token_utils.access_token_from(token_data)
    try:
        return fetch_func(access_token), access_token
    except LiveProbeError as exc:
        if exc.http_status != 401:
            raise
    token_data = refresh_live_token(config)
    access_token = schwab_token_utils.access_token_from(token_data)
    return fetch_func(access_token), access_token


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
        raise LiveProbeError("User Preference response missing streamerInfo.")
    socket_url = _first_field(streamer_info, "streamerSocketUrl", "streamer_socket_url")
    customer_id = _first_field(streamer_info, "schwabClientCustomerId", "schwab_client_customer_id")
    correl_id = _first_field(streamer_info, "schwabClientCorrelId", "schwab_client_correl_id")
    channel = _first_field(streamer_info, "schwabClientChannel", "schwab_client_channel")
    function_id = _first_field(streamer_info, "schwabClientFunctionId", "schwab_client_function_id")
    values = (socket_url, customer_id, correl_id, channel, function_id)
    if not all(isinstance(value, str) and value.strip() for value in values):
        raise LiveProbeError("User Preference response missing required streamer metadata.")
    parsed = urllib.parse.urlparse(str(socket_url).strip())
    if parsed.scheme not in {"ws", "wss"} or not parsed.netloc:
        raise LiveProbeError("User Preference streamerSocketUrl is invalid.")
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


def build_levelone_futures_subscription(
    credentials: StreamerCredentials,
    *,
    symbol: str,
    fields: tuple[int, ...],
) -> dict[str, object]:
    return {
        "requests": [
            {
                "service": "LEVELONE_FUTURES",
                "command": "SUBS",
                "requestid": "1",
                "SchwabClientCustomerId": credentials.schwab_client_customer_id,
                "SchwabClientCorrelId": credentials.schwab_client_correl_id,
                "parameters": {
                    "keys": symbol,
                    "fields": ",".join(str(field_id) for field_id in fields),
                },
            }
        ]
    }


def parse_response_code(raw_message: str, *, service: str, command: str) -> int | None:
    try:
        message = json.loads(raw_message)
    except json.JSONDecodeError as exc:
        raise LiveProbeError("Streamer response JSON is malformed.") from exc
    if not isinstance(message, dict):
        raise LiveProbeError("Streamer response JSON must be an object.")
    responses = message.get("response")
    if responses is None:
        return None
    if not isinstance(responses, list):
        raise LiveProbeError("Streamer response field is malformed.")
    for response in responses:
        if not isinstance(response, dict):
            raise LiveProbeError("Streamer response entry is malformed.")
        if response.get("service") != service or response.get("command") != command:
            continue
        content = response.get("content")
        if not isinstance(content, dict) or "code" not in content:
            raise LiveProbeError("Streamer response missing content.code.")
        try:
            return int(content["code"])
        except (TypeError, ValueError) as exc:
            raise LiveProbeError("Streamer response code is not numeric.") from exc
    return None


def extract_market_data(raw_message: str, *, fields: tuple[int, ...]) -> dict[int, object] | None:
    try:
        message = json.loads(raw_message)
    except json.JSONDecodeError as exc:
        raise LiveProbeError("Streamer data JSON is malformed.") from exc
    if not isinstance(message, dict):
        raise LiveProbeError("Streamer data JSON must be an object.")
    data_items = message.get("data")
    if data_items is None:
        return None
    if not isinstance(data_items, list):
        raise LiveProbeError("Streamer data field is malformed.")
    requested = {str(field_id): field_id for field_id in fields}
    for item in data_items:
        if not isinstance(item, dict) or item.get("service") != "LEVELONE_FUTURES":
            continue
        contents = item.get("content")
        if not isinstance(contents, list):
            raise LiveProbeError("LEVELONE_FUTURES data content is malformed.")
        for content in contents:
            if not isinstance(content, dict):
                raise LiveProbeError("LEVELONE_FUTURES data entry is malformed.")
            market_data = {
                field_id: content[field_key]
                for field_key, field_id in requested.items()
                if field_key in content
            }
            if market_data:
                return market_data
    return None


async def perform_live_probe(
    config: ProbeConfig,
    credentials: StreamerCredentials,
    access_token: str,
    *,
    websockets_module: object | None = None,
) -> LiveProbeResult:
    if websockets_module is None:
        try:
            websockets_module = importlib.import_module("websockets")
        except ImportError as exc:
            raise LiveProbeError("websockets dependency is missing.", exception_class="ImportError") from exc
    login_json = json.dumps(build_login_request(credentials, access_token), separators=(",", ":"))
    subscription_json = json.dumps(
        build_levelone_futures_subscription(
            credentials,
            symbol=config.futures_symbol,
            fields=config.stream_fields,
        ),
        separators=(",", ":"),
    )
    try:
        async with websockets_module.connect(credentials.streamer_socket_url) as websocket:
            await asyncio.wait_for(websocket.send(login_json), timeout=config.timeout_seconds)
            login_raw = await asyncio.wait_for(websocket.recv(), timeout=config.timeout_seconds)
            login_code = parse_response_code(str(login_raw), service="ADMIN", command="LOGIN")
            if login_code is None:
                raise LiveProbeError("Streamer LOGIN response missing.")
            if login_code != 0:
                raise LiveProbeError(
                    "Streamer LOGIN failed.",
                    streamer_socket_host=credentials.streamer_socket_host,
                    login_response_code=login_code,
                )

            await asyncio.wait_for(websocket.send(subscription_json), timeout=config.timeout_seconds)
            subscription_code: int | None = None
            market_data: dict[int, object] | None = None
            while market_data is None:
                raw_message = await asyncio.wait_for(websocket.recv(), timeout=config.timeout_seconds)
                if subscription_code is None:
                    maybe_code = parse_response_code(
                        str(raw_message),
                        service="LEVELONE_FUTURES",
                        command="SUBS",
                    )
                    if maybe_code is not None:
                        subscription_code = maybe_code
                        if subscription_code != 0:
                            raise LiveProbeError(
                                "LEVELONE_FUTURES subscription failed.",
                                streamer_socket_host=credentials.streamer_socket_host,
                                login_response_code=login_code,
                                subscription_response_code=subscription_code,
                            )
                market_data = extract_market_data(str(raw_message), fields=config.stream_fields)
            if subscription_code is None:
                raise LiveProbeError("LEVELONE_FUTURES subscription acknowledgement missing.")
            return LiveProbeResult(
                streamer_socket_host=credentials.streamer_socket_host,
                login_response_code=login_code,
                subscription_response_code=subscription_code,
                market_data=market_data,
            )
    except TimeoutError as exc:
        raise LiveProbeError(
            "LEVELONE_FUTURES probe timed out.",
            exception_class=exc.__class__.__name__,
            streamer_socket_host=credentials.streamer_socket_host,
        ) from exc
    except LiveProbeError:
        raise
    except Exception as exc:
        raise LiveProbeError(
            "LEVELONE_FUTURES WebSocket probe failed.",
            exception_class=exc.__class__.__name__,
            reason=exc,
            streamer_socket_host=credentials.streamer_socket_host,
        ) from exc


def _repo_relative(path: Path, *, repo_root: Path) -> str:
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def print_summary(config: ProbeConfig) -> None:
    print("SCHWAB_LEVELONE_FUTURES_PROBE_CONFIG")
    print(f"repo_root={config.repo_root}")
    print(f"target_root={_repo_relative(config.target_root, repo_root=config.repo_root)}")
    print(f"dry_run={config.dry_run}")
    print("credentials=SCHWAB_APP_KEY present: yes; SCHWAB_APP_SECRET present: yes")
    print("callback_url=present")
    print(f"token_path={config.token_path_display}")
    print("token_path_safety=UNDER_TARGET_STATE")
    print(
        "futures_symbol="
        f"{config.futures_symbol} root={config.futures_root} "
        f"month={config.futures_month_code}({config.futures_month_name}) year={config.futures_year}"
    )
    print(f"timeout_seconds={config.timeout_seconds:g}")
    print("stream_fields=")
    for field_id in config.stream_fields:
        print(f"  {field_id}: {LEVELONE_FUTURES_FIELDS[field_id]}")


def print_live_pass(config: ProbeConfig, result: LiveProbeResult) -> None:
    print("LEVELONE_FUTURES_PASS")
    print(f"streamer_socket_host={result.streamer_socket_host}")
    print(f"futures_symbol={config.futures_symbol}")
    print(f"selected_field_ids={','.join(str(field_id) for field_id in config.stream_fields)}")
    print(f"login_response_code={result.login_response_code}")
    print(f"subscription_response_code={result.subscription_response_code}")
    print("market_data_received=yes")
    for field_id in config.stream_fields:
        if field_id in result.market_data:
            print(f"field_{field_id}_{LEVELONE_FUTURES_FIELDS[field_id]}={result.market_data[field_id]}")


def print_live_fail(exc: LiveProbeError) -> None:
    print("LEVELONE_FUTURES_FAIL")
    if exc.streamer_socket_host:
        print(f"streamer_socket_host={exc.streamer_socket_host}")
    if exc.exception_class:
        print(f"exception_class={exc.exception_class}")
    if exc.reason is not None:
        print(f"reason={_sanitize_diagnostic_text(exc.reason)}")
    if exc.login_response_code is not None:
        print(f"login_response_code={exc.login_response_code}")
    if exc.subscription_response_code is not None:
        print(f"subscription_response_code={exc.subscription_response_code}")
    if str(exc):
        print(f"error={_sanitize_diagnostic_text(exc)}")


def run(
    argv: list[str] | None = None,
    *,
    env: dict[str, str] | None = None,
    fetch_func=fetch_user_preference,
    live_probe_func=perform_live_probe,
) -> int:
    parser = argparse.ArgumentParser(
        description="Validate local configuration for a future Schwab LEVELONE_FUTURES probe."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Force dry-run validation even if SCHWAB_PROBE_DRY_RUN=false is set.",
    )
    args = parser.parse_args(argv)

    try:
        config = load_config(env, force_dry_run=args.dry_run)
        print_summary(config)
        if not config.dry_run:
            payload, access_token = fetch_user_preference_with_refresh_retry(config, fetch_func=fetch_func)
            credentials = extract_streamer_credentials(payload)
            result = asyncio.run(live_probe_func(config, credentials, access_token))
            print_live_pass(config, result)
            return 0
        print("network_activity=SKIPPED_DRY_RUN")
        print("DRY_RUN_PASS")
        return 0
    except LiveProbeError as exc:
        print_live_fail(exc)
        return 1
    except ValidationError as exc:
        print("DRY_RUN_FAIL")
        print(f"validation_error={exc}")
        return 1


if __name__ == "__main__":
    sys.exit(run())
