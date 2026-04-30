#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


SCRIPT_DIR = Path(__file__).resolve().parent
TARGET_ROOT = SCRIPT_DIR.parent
SRC_ROOT = TARGET_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import probe_schwab_levelone_futures as levelone_probe
import schwab_token_utils
from ntb_marimo_console.adapters.schwab_futures_market_data import (
    DEFAULT_LEVELONE_FUTURES_FIELD_IDS,
    LEVELONE_FUTURES_FIELD_NAMES,
    SchwabAdapterTimeoutError,
    SchwabFuturesMarketDataAdapter,
    SchwabFuturesMarketDataRequest,
    SchwabFuturesMarketDataResult,
    SchwabFuturesQuoteSnapshot,
    SchwabLevelOneFuturesSubscription,
    SchwabStreamerMetadata,
)


DEFAULT_TOKEN_PATH = ".state/schwab/token.json"
DEFAULT_SYMBOL = "/ESM26"
DEFAULT_TIMEOUT_SECONDS = 10.0
LIVE_ENV_VAR = "SCHWAB_ADAPTER_SMOKE_LIVE"
LOCAL_ENV_FILE_NAME = ".env"


class SmokeConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class AdapterSmokeConfig:
    symbol: str
    field_ids: tuple[int, ...]
    timeout_seconds: float
    token_path: Path
    app_key: str
    app_secret: str
    token_url: str
    live: bool
    target_root: Path


class LiveUserPreferenceProvider:
    def __init__(self, config: AdapterSmokeConfig) -> None:
        self._config = config
        self.access_token: str | None = None

    def load_streamer_metadata(self, token_path: Path) -> SchwabStreamerMetadata:
        if token_path != self._config.token_path:
            raise SmokeConfigError("adapter token path mismatch")
        token_data = schwab_token_utils.load_token_with_refresh_if_needed(
            self._config.token_path,
            target_root=self._config.target_root,
            app_key=self._config.app_key,
            app_secret=self._config.app_secret,
            token_url=self._config.token_url,
        )
        access_token = schwab_token_utils.access_token_from(token_data)
        try:
            payload = levelone_probe.fetch_user_preference(access_token)
        except levelone_probe.LiveProbeError as exc:
            if getattr(exc, "http_status", None) != 401:
                raise
            token_data = schwab_token_utils.refresh_token_file(
                self._config.token_path,
                target_root=self._config.target_root,
                app_key=self._config.app_key,
                app_secret=self._config.app_secret,
                token_url=self._config.token_url,
            )
            access_token = schwab_token_utils.access_token_from(token_data)
            payload = levelone_probe.fetch_user_preference(access_token)
        credentials = levelone_probe.extract_streamer_credentials(payload)
        self.access_token = access_token
        return SchwabStreamerMetadata(
            streamer_socket_url=credentials.streamer_socket_url,
            schwab_client_customer_id=credentials.schwab_client_customer_id,
            schwab_client_correl_id=credentials.schwab_client_correl_id,
            schwab_client_channel=credentials.schwab_client_channel,
            schwab_client_function_id=credentials.schwab_client_function_id,
        )


class LiveFuturesStreamerClient:
    def __init__(self, access_token_provider: Callable[[], str | None]) -> None:
        self._access_token_provider = access_token_provider
        self._loop = asyncio.new_event_loop()
        self._websocket: object | None = None
        self._credentials: levelone_probe.StreamerCredentials | None = None
        self._login_response_code: int | None = None

    def login(self, metadata: SchwabStreamerMetadata, *, timeout_seconds: float) -> int:
        return self._loop.run_until_complete(self._login(metadata, timeout_seconds=timeout_seconds))

    def subscribe_levelone_futures(
        self,
        metadata: SchwabStreamerMetadata,
        *,
        symbol: str,
        field_ids: tuple[int, ...],
        timeout_seconds: float,
    ) -> SchwabLevelOneFuturesSubscription:
        try:
            return self._loop.run_until_complete(
                self._subscribe(symbol=symbol, field_ids=field_ids, timeout_seconds=timeout_seconds)
            )
        finally:
            self._loop.run_until_complete(self._close())
            self._loop.close()

    async def _login(self, metadata: SchwabStreamerMetadata, *, timeout_seconds: float) -> int:
        access_token = self._access_token_provider()
        if not access_token:
            raise SmokeConfigError("access token unavailable")
        credentials = _to_probe_credentials(metadata)
        websockets_module = _import_websockets()
        try:
            self._websocket = await asyncio.wait_for(
                websockets_module.connect(credentials.streamer_socket_url),
                timeout=timeout_seconds,
            )
            login_json = json.dumps(
                levelone_probe.build_login_request(credentials, access_token),
                separators=(",", ":"),
            )
            await asyncio.wait_for(self._websocket.send(login_json), timeout=timeout_seconds)
            raw_response = await asyncio.wait_for(self._websocket.recv(), timeout=timeout_seconds)
            login_code = levelone_probe.parse_response_code(
                str(raw_response),
                service="ADMIN",
                command="LOGIN",
            )
        except TimeoutError as exc:
            raise SchwabAdapterTimeoutError("login_timeout") from exc
        if login_code is None:
            raise SmokeConfigError("login_response_missing")
        self._credentials = credentials
        self._login_response_code = login_code
        if login_code != 0:
            await self._close()
        return login_code

    async def _subscribe(
        self,
        *,
        symbol: str,
        field_ids: tuple[int, ...],
        timeout_seconds: float,
    ) -> SchwabLevelOneFuturesSubscription:
        if self._websocket is None or self._credentials is None or self._login_response_code != 0:
            raise SmokeConfigError("streamer_not_logged_in")
        subscription_json = json.dumps(
            levelone_probe.build_levelone_futures_subscription(
                self._credentials,
                symbol=symbol,
                fields=field_ids,
            ),
            separators=(",", ":"),
        )
        try:
            await asyncio.wait_for(self._websocket.send(subscription_json), timeout=timeout_seconds)
            subscription_code: int | None = None
            market_data: dict[int, object] | None = None
            while market_data is None:
                raw_message = await asyncio.wait_for(self._websocket.recv(), timeout=timeout_seconds)
                if subscription_code is None:
                    maybe_code = levelone_probe.parse_response_code(
                        str(raw_message),
                        service="LEVELONE_FUTURES",
                        command="SUBS",
                    )
                    if maybe_code is not None:
                        subscription_code = maybe_code
                        if subscription_code != 0:
                            return SchwabLevelOneFuturesSubscription(response_code=subscription_code)
                market_data = levelone_probe.extract_market_data(str(raw_message), fields=field_ids)
        except TimeoutError as exc:
            raise SchwabAdapterTimeoutError("levelone_futures_timeout") from exc
        if subscription_code is None:
            raise SmokeConfigError("subscription_ack_missing")
        return SchwabLevelOneFuturesSubscription(
            response_code=subscription_code,
            market_data=market_data,
        )

    async def _close(self) -> None:
        if self._websocket is None:
            return
        close = getattr(self._websocket, "close", None)
        if close is not None:
            await close()
        self._websocket = None


def _to_probe_credentials(metadata: SchwabStreamerMetadata) -> levelone_probe.StreamerCredentials:
    return levelone_probe.StreamerCredentials(
        streamer_socket_url=metadata.streamer_socket_url,
        streamer_socket_host="",
        schwab_client_customer_id=metadata.schwab_client_customer_id,
        schwab_client_correl_id=metadata.schwab_client_correl_id,
        schwab_client_channel=metadata.schwab_client_channel,
        schwab_client_function_id=metadata.schwab_client_function_id,
    )


def _import_websockets() -> object:
    try:
        return importlib.import_module("websockets")
    except ImportError as exc:
        raise SmokeConfigError("websockets dependency is missing") from exc


def _parse_field_ids(raw_value: str) -> tuple[int, ...]:
    parts = tuple(part.strip() for part in raw_value.split(","))
    if not parts or any(not part for part in parts):
        raise SmokeConfigError("field IDs must be a comma-separated list")
    field_ids: list[int] = []
    for part in parts:
        if not part.isdigit():
            raise SmokeConfigError("field IDs must be numeric")
        field_id = int(part)
        if field_id not in LEVELONE_FUTURES_FIELD_NAMES:
            raise SmokeConfigError(f"unsupported LEVELONE_FUTURES field ID: {field_id}")
        field_ids.append(field_id)
    return tuple(field_ids)


def _parse_timeout(raw_value: str) -> float:
    try:
        timeout = float(raw_value)
    except ValueError as exc:
        raise SmokeConfigError("timeout seconds must be numeric") from exc
    if timeout <= 0:
        raise SmokeConfigError("timeout seconds must be positive")
    return timeout


def _resolve_safe_token_path(raw_value: str, *, target_root: Path) -> Path:
    raw_path = Path(raw_value).expanduser()
    if not raw_path.is_absolute() and raw_path.parts[:2] == ("target", "ntb_marimo_console"):
        raw_value = str(target_root.parents[1] / raw_path)
    token_path = schwab_token_utils.resolve_token_path(raw_value, target_root=target_root)
    schwab_token_utils.require_under_state(token_path, target_root=target_root)
    return token_path


def _unquote_env_value(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return stripped[1:-1]
    return stripped


def _load_local_env_file(target_root: Path) -> dict[str, str]:
    env_path = target_root / LOCAL_ENV_FILE_NAME
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = _unquote_env_value(value)
    return values


def _effective_env(*, target_root: Path, env: dict[str, str] | None) -> dict[str, str]:
    values = _load_local_env_file(target_root)
    shell_values = os.environ if env is None else env
    for key, value in shell_values.items():
        values[key] = value
    return values


def load_config(args: argparse.Namespace, *, env: dict[str, str] | None = None) -> AdapterSmokeConfig:
    target_root = TARGET_ROOT
    values = _effective_env(target_root=target_root, env=env)
    token_path = _resolve_safe_token_path(args.token_path, target_root=target_root)
    env_token_path = values.get("SCHWAB_TOKEN_PATH", "").strip()
    if env_token_path:
        token_path = _resolve_safe_token_path(env_token_path, target_root=target_root)
    field_ids = _parse_field_ids(args.fields)
    timeout_seconds = _parse_timeout(args.timeout_seconds)
    live = args.live or values.get(LIVE_ENV_VAR, "").strip() == "true"
    app_key = values.get("SCHWAB_APP_KEY", "").strip()
    app_secret = values.get("SCHWAB_APP_SECRET", "").strip()
    if live and (not app_key or not app_secret):
        raise SmokeConfigError("SCHWAB_APP_KEY and SCHWAB_APP_SECRET are required for live smoke")
    return AdapterSmokeConfig(
        symbol=args.symbol.strip().upper(),
        field_ids=field_ids,
        timeout_seconds=timeout_seconds,
        token_path=token_path,
        app_key=app_key,
        app_secret=app_secret,
        token_url=values.get("SCHWAB_OAUTH_TOKEN_URL", schwab_token_utils.DEFAULT_TOKEN_URL).strip()
        or schwab_token_utils.DEFAULT_TOKEN_URL,
        live=live,
        target_root=target_root,
    )


def build_live_adapter(config: AdapterSmokeConfig) -> SchwabFuturesMarketDataAdapter:
    provider = LiveUserPreferenceProvider(config)
    client = LiveFuturesStreamerClient(lambda: provider.access_token)
    return SchwabFuturesMarketDataAdapter(
        user_preference_provider=provider,
        streamer_client=client,
        target_root=config.target_root,
    )


def _sanitize_failure_reason(value: object) -> str:
    text = str(value)
    text = re.sub(r"(?i)(access_token|refresh_token|authorization|secret)=([^&\s,}]+)", r"\1=[REDACTED]", text)
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", text)
    text = re.sub(r"(?=\b[A-Za-z0-9._~+/=-]{24,}\b)(?=\S*\d)[A-Za-z0-9._~+/=-]+", "[REDACTED_TOKEN_LIKE]", text)
    return text


def print_result(result: SchwabFuturesMarketDataResult) -> None:
    marker = (
        "SCHWAB_FUTURES_MARKET_DATA_ADAPTER_PASS"
        if result.status == "success" and result.market_data_received
        else "SCHWAB_FUTURES_MARKET_DATA_ADAPTER_FAIL"
    )
    print(marker)
    print(f"requested_symbol={result.symbol}")
    print(f"effective_field_ids={','.join(str(field_id) for field_id in result.field_ids)}")
    if result.streamer_socket_host:
        print(f"streamer_socket_host={result.streamer_socket_host}")
    if result.login_response_code is not None:
        print(f"login_response_code={result.login_response_code}")
    if result.subscription_response_code is not None:
        print(f"subscription_response_code={result.subscription_response_code}")
    print(f"market_data_received={'yes' if result.market_data_received else 'no'}")
    if result.received_at is not None:
        print(f"received_at={result.received_at}")
    if result.last_quote_snapshot is not None:
        snapshot = result.last_quote_snapshot
        for name in ("symbol", "bid_price", "ask_price", "last_price", "bid_size", "ask_size"):
            value = getattr(snapshot, name)
            if value is not None:
                print(f"{name}={value}")
    if result.failure_reason:
        print(f"failure_reason={_sanitize_failure_reason(result.failure_reason)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Opt-in live smoke probe for the Schwab futures market-data adapter."
    )
    parser.add_argument("--live", action="store_true", help=f"Enable live smoke; alternatively set {LIVE_ENV_VAR}=true.")
    parser.add_argument("--symbol", default=DEFAULT_SYMBOL, help="Explicit Schwab futures contract symbol.")
    parser.add_argument(
        "--fields",
        default=",".join(str(field_id) for field_id in DEFAULT_LEVELONE_FUTURES_FIELD_IDS),
        help="Comma-separated LEVELONE_FUTURES field IDs.",
    )
    parser.add_argument("--timeout-seconds", default=str(DEFAULT_TIMEOUT_SECONDS), help="Positive timeout in seconds.")
    parser.add_argument("--token-path", default=DEFAULT_TOKEN_PATH, help="Token path under target/ntb_marimo_console/.state/.")
    return parser


def run(
    argv: list[str] | None = None,
    *,
    env: dict[str, str] | None = None,
    adapter_factory: Callable[[AdapterSmokeConfig], SchwabFuturesMarketDataAdapter] = build_live_adapter,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        config = load_config(args, env=env)
        if not config.live:
            result = SchwabFuturesMarketDataResult(
                status="error",
                symbol=config.symbol,
                field_ids=config.field_ids,
                streamer_socket_host=None,
                login_response_code=None,
                subscription_response_code=None,
                market_data_received=False,
                last_quote_snapshot=None,
                received_at=None,
                failure_reason=f"live smoke disabled; pass --live or set {LIVE_ENV_VAR}=true",
            )
            print_result(result)
            return 1
        adapter = adapter_factory(config)
        result = adapter.fetch_once(
            SchwabFuturesMarketDataRequest(
                symbol=config.symbol,
                token_path=config.token_path,
                field_ids=config.field_ids,
                timeout_seconds=config.timeout_seconds,
            )
        )
        print_result(result)
        return 0 if result.status == "success" and result.market_data_received else 1
    except (SmokeConfigError, schwab_token_utils.SchwabTokenError, levelone_probe.LiveProbeError) as exc:
        print("SCHWAB_FUTURES_MARKET_DATA_ADAPTER_FAIL")
        print(f"failure_reason={_sanitize_failure_reason(exc)}")
        return 1


if __name__ == "__main__":
    sys.exit(run())
