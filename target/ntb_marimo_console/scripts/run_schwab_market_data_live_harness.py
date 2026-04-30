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
    SchwabAdapterTimeoutError,
    SchwabFuturesMarketDataAdapter,
    SchwabFuturesMarketDataResult,
    SchwabLevelOneFuturesSubscription,
    SchwabStreamerMetadata,
)
from ntb_marimo_console.market_data import (
    FuturesQuoteServiceConfig,
    FuturesQuoteServiceResult,
    build_futures_quote_service,
    resolve_futures_quote_service_config,
)
from ntb_marimo_console.market_data.config import DEFAULT_MARKET_DATA_SYMBOL, DEFAULT_TIMEOUT_SECONDS
from ntb_marimo_console.ui.surfaces.live_observables import render_live_observables_panel
from ntb_marimo_console.viewmodels.mappers import live_observable_vm_from_snapshot


DEFAULT_TOKEN_PATH = "target/ntb_marimo_console/.state/schwab/token.json"
LOCAL_ENV_FILE_NAME = ".env"


class LiveHarnessConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class LiveHarnessConfig:
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
    def __init__(self, config: LiveHarnessConfig) -> None:
        self._config = config
        self.access_token: str | None = None

    def load_streamer_metadata(self, token_path: Path) -> SchwabStreamerMetadata:
        if token_path != self._config.token_path:
            raise LiveHarnessConfigError("adapter_token_path_mismatch")
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
            raise LiveHarnessConfigError("access_token_unavailable")
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
            raise LiveHarnessConfigError("login_response_missing")
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
            raise LiveHarnessConfigError("streamer_not_logged_in")
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
            raise LiveHarnessConfigError("subscription_ack_missing")
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


class _CachedQuoteService:
    def __init__(self, result: FuturesQuoteServiceResult) -> None:
        self._result = result

    def get_quote(self, requested_symbol: str) -> FuturesQuoteServiceResult:
        return self._result


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
        raise LiveHarnessConfigError("websockets_dependency_missing") from exc


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
        if key:
            values[key] = _unquote_env_value(value)
    return values


def _effective_env(*, target_root: Path, env: dict[str, str] | None) -> dict[str, str]:
    values = _load_local_env_file(target_root)
    shell_values = os.environ if env is None else env
    for key, value in shell_values.items():
        values[key] = value
    return values


def _market_data_config_from_args(args: argparse.Namespace, *, target_root: Path) -> FuturesQuoteServiceConfig:
    config = resolve_futures_quote_service_config(
        {
            "NTB_MARKET_DATA_PROVIDER": "schwab",
            "NTB_MARKET_DATA_SYMBOL": args.symbol,
            "NTB_MARKET_DATA_FIELD_IDS": args.fields,
            "NTB_MARKET_DATA_TIMEOUT_SECONDS": args.timeout_seconds,
            "SCHWAB_TOKEN_PATH": args.token_path,
        },
        target_root=target_root,
    )
    if config.failure_reason is not None or config.provider != "schwab":
        reason = config.failure_reason or "provider_not_schwab"
        raise LiveHarnessConfigError(reason)
    return config


def load_config(args: argparse.Namespace, *, env: dict[str, str] | None = None) -> LiveHarnessConfig:
    target_root = TARGET_ROOT
    values = _effective_env(target_root=target_root, env=env)
    market_data_config = _market_data_config_from_args(args, target_root=target_root)
    app_key = values.get("SCHWAB_APP_KEY", "").strip()
    app_secret = values.get("SCHWAB_APP_SECRET", "").strip()
    if args.live and (not app_key or not app_secret):
        raise LiveHarnessConfigError("schwab_app_credentials_required")
    return LiveHarnessConfig(
        symbol=market_data_config.symbol,
        field_ids=market_data_config.field_ids,
        timeout_seconds=market_data_config.timeout_seconds,
        token_path=market_data_config.token_path,
        app_key=app_key,
        app_secret=app_secret,
        token_url=values.get("SCHWAB_OAUTH_TOKEN_URL", schwab_token_utils.DEFAULT_TOKEN_URL).strip()
        or schwab_token_utils.DEFAULT_TOKEN_URL,
        live=args.live,
        target_root=target_root,
    )


def build_live_adapter(config: LiveHarnessConfig) -> SchwabFuturesMarketDataAdapter:
    provider = LiveUserPreferenceProvider(config)
    client = LiveFuturesStreamerClient(lambda: provider.access_token)
    return SchwabFuturesMarketDataAdapter(
        user_preference_provider=provider,
        streamer_client=client,
        target_root=config.target_root,
    )


def _service_config(config: LiveHarnessConfig) -> FuturesQuoteServiceConfig:
    return FuturesQuoteServiceConfig(
        provider="schwab",
        symbol=config.symbol,
        field_ids=config.field_ids,
        max_quote_age_seconds=5.0,
        token_path=config.token_path,
        timeout_seconds=config.timeout_seconds,
    )


def _display_panel(config: LiveHarnessConfig, result: FuturesQuoteServiceResult) -> dict[str, object]:
    vm = live_observable_vm_from_snapshot(
        {
            "contract": config.symbol,
            "timestamp_et": result.quote.received_at if result.quote is not None else "",
        },
        market_data_service=_CachedQuoteService(result),  # type: ignore[arg-type]
        market_data_symbol=config.symbol,
    )
    return render_live_observables_panel(vm)["market_data"]


def _market_data_received(result: FuturesQuoteServiceResult) -> bool:
    return result.provider_name == "schwab" and result.status in {"connected", "stale"} and result.quote is not None


def _sanitize_text(value: object) -> str:
    text = str(value)
    text = re.sub(r"(?i)(access_token|refresh_token|authorization|secret|app_secret)=([^&\s,}]+)", r"\1=[REDACTED]", text)
    text = re.sub(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", text)
    text = re.sub(r"(?i)(customer|customerId|correl|correlId|account)[A-Za-z_]*=([^&\s,}]+)", r"\1=[REDACTED]", text)
    text = re.sub(r"(?i)\"(customer|customerId|correl|correlId|account)[^\"]*\"\s*:\s*\"[^\"]+\"", r'"\1":"[REDACTED]"', text)
    text = re.sub(r"wss?://[^\s,}]+", "[REDACTED_URL]", text)
    text = re.sub(r"https?://[^\s,}]+", "[REDACTED_URL]", text)
    text = re.sub(r"(?=\b[A-Za-z0-9._~+/=-]{24,}\b)(?=\S*\d)[A-Za-z0-9._~+/=-]+", "[REDACTED_TOKEN_LIKE]", text)
    return text[:240]


def print_display_result(
    *,
    config: LiveHarnessConfig | None,
    panel: dict[str, object] | None,
    market_data_received: bool,
    failure_reason: object | None = None,
) -> None:
    print(
        "SCHWAB_MARKET_DATA_LIVE_HARNESS_PASS"
        if market_data_received
        else "SCHWAB_MARKET_DATA_LIVE_HARNESS_FAIL"
    )
    print("provider=schwab")
    print(f"symbol={config.symbol if config is not None else DEFAULT_MARKET_DATA_SYMBOL}")
    if panel is not None:
        print(f"status={panel['status']}")
        print(f"bid={panel['bid']}")
        print(f"ask={panel['ask']}")
        print(f"last={panel['last']}")
        print(f"quote_time={panel['quote_time']}")
    else:
        print("status=Market data unavailable")
        print("bid=N/A")
        print("ask=N/A")
        print("last=N/A")
        print("quote_time=unknown")
    print(f"market_data_received={'yes' if market_data_received else 'no'}")
    if failure_reason:
        print(f"failure_reason={_sanitize_text(failure_reason)}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Manual opt-in harness for displaying a Schwab futures quote through the market-data service."
    )
    parser.add_argument("--live", action="store_true", help="Required explicit opt-in for live Schwab access.")
    parser.add_argument("--symbol", default=DEFAULT_MARKET_DATA_SYMBOL, help="Schwab futures contract symbol.")
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
    adapter_factory: Callable[[LiveHarnessConfig], SchwabFuturesMarketDataAdapter] = build_live_adapter,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    config: LiveHarnessConfig | None = None
    try:
        config = load_config(args, env=env)
        if not config.live:
            print_display_result(
                config=config,
                panel=None,
                market_data_received=False,
                failure_reason="live_harness_disabled_pass_--live",
            )
            return 1
        service = build_futures_quote_service(
            _service_config(config),
            schwab_adapter_factory=lambda service_config: adapter_factory(config),
        )
        result = service.get_quote(config.symbol)
        panel = _display_panel(config, result)
        received = _market_data_received(result)
        print_display_result(
            config=config,
            panel=panel,
            market_data_received=received,
            failure_reason=result.failure_reason if not received else None,
        )
        return 0 if received else 1
    except (
        LiveHarnessConfigError,
        schwab_token_utils.SchwabTokenError,
        levelone_probe.LiveProbeError,
    ) as exc:
        print_display_result(
            config=config,
            panel=None,
            market_data_received=False,
            failure_reason=exc,
        )
        return 1


if __name__ == "__main__":
    sys.exit(run())
