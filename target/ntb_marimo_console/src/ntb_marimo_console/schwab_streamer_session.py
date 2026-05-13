"""Production-intended Schwab streamer session adapter.

This module is deliberately inert at import time:

* It does NOT import ``websockets``, ``urllib``, ``os``, or any token/credential
  source at module-top. ``websockets`` is loaded lazily inside
  :func:`DefaultSchwabWebsocketFactory.connect`. Token files are read only
  when :meth:`FileAccessTokenProvider.load_access_token` is invoked.
* Operator credentials (``StreamerCredentials``) are operator-supplied via the
  ``credentials_provider`` parameter — there is no implicit user-preference
  fetch in src/.
* Constructing :class:`OperatorSchwabStreamerSession` does **not** open a
  websocket. The session opens a connection only when :meth:`login` is called,
  which the operator launcher invokes exactly once per explicit
  ``OPERATOR_LIVE_RUNTIME`` startup.

Manual live rehearsal pattern::

    creds = StreamerCredentials(...)  # operator-loaded out-of-band
    captured: list[OperatorSchwabStreamerSession] = []

    def session_factory(config):
        session = OperatorSchwabStreamerSession(
            access_token_provider=FileAccessTokenProvider(token_path),
            credentials_provider=StaticStreamerCredentialsProvider(creds),
            websocket_factory=default_schwab_websocket_factory(),
        )
        captured.append(session)
        return session

    client_factory = build_operator_schwab_stream_client_factory(
        streamer_session_factory=session_factory,
    )
    launch = start_operator_live_runtime(
        client_factory=client_factory,
        config=SchwabStreamManagerConfig(
            provider="schwab",
            services_requested=("LEVELONE_FUTURES",),
            symbols_requested=(...front-month symbols...),
            fields_requested=(0, 1, 2, 3, 4, 5, ...),
            explicit_live_opt_in=True,
            contracts_requested=("ES", "NQ", "CL", "6E", "MGC"),
        ),
    )

    # Operator-driven receive loop (NOT auto-spawned, NOT called from refresh):
    session = captured[-1]
    while True:
        if not session.dispatch_one(handler=launch.manager.ingest_message):
            break
"""

from __future__ import annotations

import importlib
import json
import re
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Protocol
from urllib.parse import urlparse

from .contract_universe import (
    is_excluded_final_target_contract,
    is_final_target_contract,
    is_never_supported_contract,
    normalize_contract_symbol,
)
from .market_data.stream_manager import (
    SchwabStreamManagerConfig,
    StreamClientResult,
    StreamSubscriptionRequest,
)
from .market_data.stream_events import redact_sensitive_text


DEFAULT_LEVELONE_FUTURES_FIELD_IDS: tuple[int, ...] = (0, 1, 2, 3, 4, 5)
DEFAULT_CHART_FUTURES_FIELD_IDS: tuple[int, ...] = (0, 1, 2, 3, 4, 5, 6, 7, 8)
DEFAULT_RECV_TIMEOUT_SECONDS: float = 10.0
DEFAULT_LOGIN_REQUESTID: str = "0"
DEFAULT_SUBSCRIBE_REQUESTID: str = "1"
DEFAULT_LOGOUT_REQUESTID: str = "2"

ADMIN_SERVICE: str = "ADMIN"
LOGIN_COMMAND: str = "LOGIN"
LOGOUT_COMMAND: str = "LOGOUT"
LEVELONE_FUTURES_SERVICE: str = "LEVELONE_FUTURES"
CHART_FUTURES_SERVICE: str = "CHART_FUTURES"
SUPPORTED_FUTURES_SERVICES: tuple[str, ...] = (LEVELONE_FUTURES_SERVICE, CHART_FUTURES_SERVICE)
SUBS_COMMAND: str = "SUBS"
DispatchStatus = Literal[
    "idle",
    "inactive",
    "message",
    "timeout",
    "connection_lost",
    "parse_error",
    "token_refresh_failed",
]

_FUTURES_SYMBOL_PATTERN = re.compile(
    r"^/(?P<root>[A-Z0-9]{1,6})(?P<month>[FGHJKMNQUVXZ])(?P<year>\d{2})$"
)


@dataclass(frozen=True)
class StreamerCredentials:
    streamer_socket_url: str
    streamer_socket_host: str
    schwab_client_customer_id: str
    schwab_client_correl_id: str
    schwab_client_channel: str
    schwab_client_function_id: str


class SchwabAccessTokenProvider(Protocol):
    def load_access_token(self) -> str: ...


class SchwabStreamerCredentialsProvider(Protocol):
    def load_streamer_credentials(self) -> StreamerCredentials: ...


class SchwabWebsocketConnection(Protocol):
    def send(self, payload: str) -> None: ...

    def recv(self, timeout: float) -> str: ...

    def close(self) -> None: ...


class SchwabWebsocketFactory(Protocol):
    def connect(self, url: str, *, timeout_seconds: float) -> SchwabWebsocketConnection: ...


class OperatorSchwabStreamerSessionError(RuntimeError):
    """Raised on internal session contract violations. Reasons are redacted before reaching results."""


# ---------------------------------------------------------------------------
# Pure helpers (deterministic, no I/O).
# ---------------------------------------------------------------------------


def build_login_payload(
    credentials: StreamerCredentials,
    access_token: str,
    *,
    requestid: str = DEFAULT_LOGIN_REQUESTID,
) -> dict[str, object]:
    return {
        "requests": [
            {
                "service": ADMIN_SERVICE,
                "command": LOGIN_COMMAND,
                "requestid": requestid,
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


def build_levelone_futures_subscription_payload(
    credentials: StreamerCredentials,
    *,
    symbols: tuple[str, ...],
    fields: tuple[int, ...],
    requestid: str = DEFAULT_SUBSCRIBE_REQUESTID,
) -> dict[str, object]:
    return {
        "requests": [
            {
                "service": LEVELONE_FUTURES_SERVICE,
                "command": SUBS_COMMAND,
                "requestid": requestid,
                "SchwabClientCustomerId": credentials.schwab_client_customer_id,
                "SchwabClientCorrelId": credentials.schwab_client_correl_id,
                "parameters": {
                    "keys": ",".join(symbol for symbol in symbols),
                    "fields": ",".join(str(field_id) for field_id in fields),
                },
            }
        ]
    }


def build_chart_futures_subscription_payload(
    credentials: StreamerCredentials,
    *,
    symbols: tuple[str, ...],
    fields: tuple[int, ...],
    requestid: str = "2",
) -> dict[str, object]:
    return {
        "requests": [
            {
                "service": CHART_FUTURES_SERVICE,
                "command": SUBS_COMMAND,
                "requestid": requestid,
                "SchwabClientCustomerId": credentials.schwab_client_customer_id,
                "SchwabClientCorrelId": credentials.schwab_client_correl_id,
                "parameters": {
                    "keys": ",".join(symbol for symbol in symbols),
                    "fields": ",".join(str(field_id) for field_id in fields),
                },
            }
        ]
    }


def _subscription_payload_for_service(
    credentials: StreamerCredentials,
    *,
    service: str,
    symbols: tuple[str, ...],
    fields: tuple[int, ...],
    requestid: str,
) -> dict[str, object]:
    if service == CHART_FUTURES_SERVICE:
        return build_chart_futures_subscription_payload(
            credentials,
            symbols=symbols,
            fields=fields,
            requestid=requestid,
        )
    return build_levelone_futures_subscription_payload(
        credentials,
        symbols=symbols,
        fields=fields,
        requestid=requestid,
    )


def build_logout_payload(
    credentials: StreamerCredentials,
    *,
    requestid: str = DEFAULT_LOGOUT_REQUESTID,
) -> dict[str, object]:
    return {
        "requests": [
            {
                "service": ADMIN_SERVICE,
                "command": LOGOUT_COMMAND,
                "requestid": requestid,
                "SchwabClientCustomerId": credentials.schwab_client_customer_id,
                "SchwabClientCorrelId": credentials.schwab_client_correl_id,
                "parameters": {},
            }
        ]
    }


def parse_response_code(
    raw_message: str,
    *,
    service: str,
    command: str,
) -> int | None:
    """Return the response.content.code for the matching service/command, or None."""

    try:
        message = json.loads(raw_message)
    except (TypeError, ValueError):
        raise OperatorSchwabStreamerSessionError("malformed_response_json")
    if not isinstance(message, dict):
        raise OperatorSchwabStreamerSessionError("malformed_response_object")
    responses = message.get("response")
    if responses is None:
        return None
    if not isinstance(responses, list):
        raise OperatorSchwabStreamerSessionError("malformed_response_field")
    for response in responses:
        if not isinstance(response, dict):
            raise OperatorSchwabStreamerSessionError("malformed_response_entry")
        if response.get("service") != service or response.get("command") != command:
            continue
        content = response.get("content")
        if not isinstance(content, dict) or "code" not in content:
            raise OperatorSchwabStreamerSessionError("malformed_response_content")
        try:
            return int(content["code"])
        except (TypeError, ValueError):
            raise OperatorSchwabStreamerSessionError("malformed_response_code")
    return None


def extract_data_entries(
    raw_message: str,
    *,
    service: str = LEVELONE_FUTURES_SERVICE,
) -> list[Mapping[str, object]]:
    """Parse a Schwab streamer data frame and return per-symbol normalized mappings.

    Each returned mapping is shaped to be consumed by
    :meth:`SchwabStreamManager.ingest_message`.
    """

    try:
        message = json.loads(raw_message)
    except (TypeError, ValueError):
        raise OperatorSchwabStreamerSessionError("malformed_data_json")
    if not isinstance(message, dict):
        raise OperatorSchwabStreamerSessionError("malformed_data_object")
    data_items = message.get("data")
    if data_items is None:
        return []
    if not isinstance(data_items, list):
        raise OperatorSchwabStreamerSessionError("malformed_data_field")
    out: list[Mapping[str, object]] = []
    for item in data_items:
        if not isinstance(item, dict) or item.get("service") != service:
            continue
        out.extend(_extract_data_item_entries(item, service=service))
    return out


def extract_supported_data_entries(raw_message: str) -> list[Mapping[str, object]]:
    entries: list[Mapping[str, object]] = []
    for service in SUPPORTED_FUTURES_SERVICES:
        entries.extend(extract_data_entries(raw_message, service=service))
    return entries


def _extract_data_item_entries(
    item: Mapping[str, object],
    *,
    service: str,
) -> tuple[Mapping[str, object], ...]:
    contents = item.get("content")
    if not isinstance(contents, list):
        raise OperatorSchwabStreamerSessionError("malformed_data_content")
    timestamp = item.get("timestamp")
    received_at = _received_at_from_timestamp(timestamp)
    entries: list[Mapping[str, object]] = []
    for content in contents:
        if not isinstance(content, dict):
            raise OperatorSchwabStreamerSessionError("malformed_data_entry")
        symbol_value = content.get("key")
        if not isinstance(symbol_value, str) or not symbol_value.strip():
            continue
        symbol = symbol_value.strip().upper()
        contract = _contract_from_symbol(symbol)
        if contract is None:
            continue
        if service == CHART_FUTURES_SERVICE:
            entries.append(_chart_futures_bar_entry(content, symbol=symbol, contract=contract, received_at=received_at))
            continue
        fields = {
            str(field_key): field_value
            for field_key, field_value in content.items()
            if field_key != "key"
        }
        entries.append(
            {
                "provider": "schwab",
                "service": service,
                "symbol": symbol,
                "contract": contract,
                "message_type": "quote",
                "fields": fields,
                "received_at": received_at,
            }
        )
    return tuple(entries)


def _chart_futures_bar_entry(
    content: Mapping[str, object],
    *,
    symbol: str,
    contract: str,
    received_at: str,
) -> Mapping[str, object]:
    start_time = _timestamp_value(content, "start_time", "start", "chart_time", "time", "0")
    end_time = _timestamp_value(content, "end_time", "end", "1")
    completed = _bool_value(content, "completed", "complete", "is_complete", "closed", "8")
    payload: dict[str, object] = {
        "provider": "schwab",
        "service": CHART_FUTURES_SERVICE,
        "source": "chart_futures",
        "symbol": symbol,
        "contract": contract,
        "message_type": "bar",
        "observed_at": received_at,
        "received_at": received_at,
    }
    if start_time:
        payload["start_time"] = start_time
    if end_time:
        payload["end_time"] = end_time
    for field_name, aliases in {
        "open": ("open", "open_price", "2"),
        "high": ("high", "high_price", "3"),
        "low": ("low", "low_price", "4"),
        "close": ("close", "close_price", "5"),
        "volume": ("volume", "total_volume", "6"),
    }.items():
        value = _number_value(content, *aliases)
        if value is not None:
            payload[field_name] = value
    if completed is not None:
        payload["completed"] = completed
    return payload


def _contract_from_symbol(symbol: str) -> str | None:
    match = _FUTURES_SYMBOL_PATTERN.match(symbol.strip().upper())
    if match is None:
        return None
    return match.group("root")


def _received_at_from_timestamp(timestamp: object) -> str:
    if timestamp is None or isinstance(timestamp, bool):
        return ""
    if isinstance(timestamp, int | float):
        return _epoch_timestamp_to_iso(timestamp)
    text = str(timestamp).strip()
    if not text:
        return ""
    if re.fullmatch(r"\d+(?:\.\d+)?", text):
        try:
            return _epoch_timestamp_to_iso(float(text))
        except (OverflowError, OSError, ValueError):
            return ""
    return text


def _timestamp_value(content: Mapping[str, object], *aliases: str) -> str | None:
    for alias in aliases:
        value = content.get(alias)
        if value is None:
            continue
        rendered = _received_at_from_timestamp(value)
        if rendered:
            return rendered
    return None


def _number_value(content: Mapping[str, object], *aliases: str) -> int | float | None:
    for alias in aliases:
        value = content.get(alias)
        if isinstance(value, bool):
            continue
        if isinstance(value, int | float):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                continue
            try:
                parsed = float(text)
            except ValueError:
                continue
            return int(parsed) if parsed.is_integer() else parsed
    return None


def _bool_value(content: Mapping[str, object], *aliases: str) -> bool | None:
    for alias in aliases:
        value = content.get(alias)
        if isinstance(value, bool):
            return value
        if isinstance(value, int | float) and not isinstance(value, bool):
            if value in {0, 1}:
                return bool(value)
            continue
        if isinstance(value, str):
            text = value.strip().lower()
            if text in {"true", "yes", "1", "complete", "completed", "closed"}:
                return True
            if text in {"false", "no", "0", "building", "partial", "open"}:
                return False
    return None


def _epoch_timestamp_to_iso(timestamp: int | float) -> str:
    seconds = float(timestamp)
    if abs(seconds) >= 1_000_000_000_000:
        seconds = seconds / 1000.0
    try:
        return datetime.fromtimestamp(seconds, tz=timezone.utc).isoformat()
    except (OverflowError, OSError, ValueError):
        return ""


def validate_subscription_contracts(contracts: tuple[str, ...]) -> tuple[str, ...]:
    """Return a tuple of redacted blocking reasons; empty tuple means OK."""

    reasons: list[str] = []
    for raw in contracts:
        contract = normalize_contract_symbol(raw)
        if is_never_supported_contract(contract):
            reasons.append(f"never_supported_contract_in_subscription:{contract}")
        elif is_excluded_final_target_contract(contract):
            reasons.append(f"excluded_contract_in_subscription:{contract}")
        elif not is_final_target_contract(contract):
            reasons.append(f"non_final_target_contract_in_subscription:{contract}")
    return tuple(reasons)


# ---------------------------------------------------------------------------
# Default, lazy production providers.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FileAccessTokenProvider:
    """Lazy ``access_token`` reader.

    Opens the token JSON path only when :meth:`load_access_token` is invoked.
    No file I/O occurs at construction or at module import time.
    """

    token_path: Path

    def load_access_token(self) -> str:
        try:
            with self.token_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except FileNotFoundError as exc:
            raise OperatorSchwabStreamerSessionError("token_file_missing") from exc
        except (OSError, ValueError) as exc:
            raise OperatorSchwabStreamerSessionError("token_file_unreadable") from exc
        if not isinstance(payload, dict):
            raise OperatorSchwabStreamerSessionError("token_payload_not_object")
        access_token = payload.get("access_token")
        if not isinstance(access_token, str) or not access_token.strip():
            raise OperatorSchwabStreamerSessionError("access_token_missing")
        return access_token.strip()


@dataclass(frozen=True)
class StaticStreamerCredentialsProvider:
    """Operator-supplied, immutable streamer credentials provider.

    Operators load ``StreamerCredentials`` out-of-band (e.g., via the existing
    ``scripts/probe_schwab_user_preference.py`` capture), then pass them in.
    """

    credentials: StreamerCredentials

    def load_streamer_credentials(self) -> StreamerCredentials:
        return self.credentials


class DefaultSchwabWebsocketFactory:
    """Lazy-imports ``websockets`` on first :meth:`connect`.

    Uses ``websockets.sync.client.connect`` to avoid asyncio bridges and keep
    the session call sites synchronous.
    """

    def connect(self, url: str, *, timeout_seconds: float) -> SchwabWebsocketConnection:
        try:
            sync_client_module = importlib.import_module("websockets.sync.client")
        except ImportError as exc:
            raise OperatorSchwabStreamerSessionError("websockets_dependency_missing") from exc
        connect_callable = getattr(sync_client_module, "connect", None)
        if not callable(connect_callable):
            raise OperatorSchwabStreamerSessionError("websockets_sync_client_unavailable")
        try:
            connection = connect_callable(url, open_timeout=timeout_seconds)
        except Exception as exc:
            raise OperatorSchwabStreamerSessionError("websocket_connect_failed") from exc
        return _WebsocketsSyncAdapter(connection)


@dataclass
class _WebsocketsSyncAdapter:
    """Adapt the ``websockets.sync`` connection to ``SchwabWebsocketConnection``."""

    _connection: Any

    def send(self, payload: str) -> None:
        self._connection.send(payload)

    def recv(self, timeout: float) -> str:
        message = self._connection.recv(timeout=timeout)
        if isinstance(message, bytes):
            return message.decode("utf-8")
        return str(message)

    def close(self) -> None:
        try:
            self._connection.close()
        except Exception as exc:
            raise OperatorSchwabStreamerSessionError("websocket_close_failed") from exc


def default_schwab_websocket_factory() -> DefaultSchwabWebsocketFactory:
    """Return a lazy default factory. Constructing it does NOT import websockets."""

    return DefaultSchwabWebsocketFactory()


# ---------------------------------------------------------------------------
# Concrete session.
# ---------------------------------------------------------------------------


class OperatorSchwabStreamerSession:
    """Production-intended Schwab streamer session.

    Performs ``ADMIN LOGIN``, futures market-data ``SUBS`` requests, and
    ``LOGOUT`` + close exactly once per explicit operator startup. Provides
    :meth:`dispatch_one` as the receive/dispatch handoff for an
    operator-driven receive loop.

    The session is invoked exclusively from the explicit operator launcher
    path (and the manager's ``start()``); never from Marimo refresh, readiness
    summary, renderer, or any default/CI/import path.
    """

    def __init__(
        self,
        *,
        access_token_provider: SchwabAccessTokenProvider,
        credentials_provider: SchwabStreamerCredentialsProvider,
        websocket_factory: SchwabWebsocketFactory,
        fields_requested: tuple[int, ...] = DEFAULT_LEVELONE_FUTURES_FIELD_IDS,
        timeout_seconds: float = DEFAULT_RECV_TIMEOUT_SECONDS,
    ) -> None:
        self._access_token_provider = access_token_provider
        self._credentials_provider = credentials_provider
        self._websocket_factory = websocket_factory
        self._fields_requested = tuple(int(f) for f in fields_requested)
        self._timeout_seconds = float(timeout_seconds)
        self._credentials: StreamerCredentials | None = None
        self._connection: SchwabWebsocketConnection | None = None
        self._login_attempted = False
        self._login_succeeded = False
        self._subscribe_attempted = False
        self._subscribe_succeeded = False
        self._closed = False
        self._pending_data_frames: deque[tuple[Mapping[str, object], ...]] = deque()
        self._last_token_refresh_error: str | None = None
        self._last_dispatch_status: DispatchStatus = "idle"

    # -- login ---------------------------------------------------------------

    def login(self, config: SchwabStreamManagerConfig) -> StreamClientResult:
        if self._login_attempted:
            return StreamClientResult(succeeded=False, reason="login_already_attempted")
        self._login_attempted = True

        try:
            credentials = self._credentials_provider.load_streamer_credentials()
        except Exception as exc:
            return StreamClientResult(
                succeeded=False,
                reason=f"login_credentials_provider_error:{exc}",
            )
        if not _credentials_look_valid(credentials):
            return StreamClientResult(succeeded=False, reason="login_credentials_invalid")

        try:
            access_token = self._access_token_provider.load_access_token()
        except Exception as exc:
            return StreamClientResult(
                succeeded=False,
                reason=f"login_access_token_provider_error:{exc}",
            )
        if not isinstance(access_token, str) or not access_token.strip():
            return StreamClientResult(succeeded=False, reason="login_access_token_invalid")

        parsed = urlparse(credentials.streamer_socket_url)
        if parsed.scheme not in {"ws", "wss"} or not parsed.netloc:
            return StreamClientResult(succeeded=False, reason="login_streamer_socket_url_invalid")

        try:
            connection = self._websocket_factory.connect(
                credentials.streamer_socket_url,
                timeout_seconds=self._timeout_seconds,
            )
        except OperatorSchwabStreamerSessionError as exc:
            return StreamClientResult(succeeded=False, reason=f"login_connect_failed:{exc}")
        except Exception as exc:
            return StreamClientResult(succeeded=False, reason=f"login_connect_error:{exc}")

        self._credentials = credentials
        self._connection = connection

        login_json = json.dumps(
            build_login_payload(credentials, access_token), separators=(",", ":")
        )
        try:
            connection.send(login_json)
        except Exception as exc:
            self._safe_close()
            return StreamClientResult(succeeded=False, reason=f"login_send_failed:{exc}")

        try:
            raw_response = connection.recv(self._timeout_seconds)
        except TimeoutError:
            self._safe_close()
            return StreamClientResult(succeeded=False, reason="login_timeout")
        except Exception as exc:
            self._safe_close()
            return StreamClientResult(succeeded=False, reason=f"login_recv_failed:{exc}")

        try:
            code = parse_response_code(
                str(raw_response), service=ADMIN_SERVICE, command=LOGIN_COMMAND
            )
        except OperatorSchwabStreamerSessionError as exc:
            self._safe_close()
            return StreamClientResult(succeeded=False, reason=f"login_malformed_response:{exc}")

        if code is None:
            self._safe_close()
            return StreamClientResult(succeeded=False, reason="login_response_missing")
        if code != 0:
            self._safe_close()
            return StreamClientResult(succeeded=False, reason=f"login_denied:code={code}")

        self._login_succeeded = True
        return StreamClientResult(succeeded=True)

    # -- subscribe -----------------------------------------------------------

    def subscribe(self, request: StreamSubscriptionRequest) -> StreamClientResult:
        if not self._login_succeeded:
            return StreamClientResult(succeeded=False, reason="subscribe_requires_login")
        if self._subscribe_attempted:
            return StreamClientResult(succeeded=False, reason="subscribe_already_attempted")
        self._subscribe_attempted = True

        block_reasons = validate_subscription_contracts(request.contracts)
        if block_reasons:
            return StreamClientResult(succeeded=False, reason="; ".join(block_reasons))

        if not request.symbols:
            return StreamClientResult(succeeded=False, reason="subscribe_no_symbols")
        fields = request.fields or self._fields_requested
        if not fields:
            return StreamClientResult(succeeded=False, reason="subscribe_no_fields")

        credentials = self._credentials
        connection = self._connection
        if credentials is None or connection is None:
            return StreamClientResult(succeeded=False, reason="subscribe_session_not_ready")

        services = tuple(dict.fromkeys(service.strip().upper() for service in request.services if service.strip()))
        if not services:
            services = (LEVELONE_FUTURES_SERVICE,)
        unsupported = tuple(service for service in services if service not in SUPPORTED_FUTURES_SERVICES)
        if unsupported:
            return StreamClientResult(succeeded=False, reason="unsupported_subscription_service:" + ",".join(unsupported))

        for index, service in enumerate(services, start=1):
            payload = _subscription_payload_for_service(
                credentials,
                service=service,
                symbols=request.symbols,
                fields=tuple(fields),
                requestid=str(index),
            )
            subscription_json = json.dumps(payload, separators=(",", ":"))
            try:
                connection.send(subscription_json)
            except Exception as exc:
                return StreamClientResult(succeeded=False, reason=f"subscribe_send_failed:{exc}")

            ack_result = self._drain_until_subscription_ack(connection, service=service)
            if not ack_result.succeeded:
                return ack_result

        self._subscribe_succeeded = True
        return StreamClientResult(succeeded=True)

    def _drain_until_subscription_ack(
        self,
        connection: SchwabWebsocketConnection,
        *,
        service: str,
    ) -> StreamClientResult:
        # Drain incoming frames until the SUBS ack appears or we hit timeout.
        # Schwab may deliver data before the SUBS ack frame reaches us; keep
        # those frames for the first dispatch call instead of consuming them.
        deadline_attempts = max(1, int(self._timeout_seconds // 1) or 1) * 4
        for _ in range(deadline_attempts):
            try:
                raw_response = connection.recv(self._timeout_seconds)
            except TimeoutError:
                return StreamClientResult(succeeded=False, reason=f"subscribe_timeout:{service}")
            except Exception as exc:
                return StreamClientResult(succeeded=False, reason=f"subscribe_recv_failed:{exc}")

            try:
                code = parse_response_code(
                    str(raw_response),
                    service=service,
                    command=SUBS_COMMAND,
                )
            except OperatorSchwabStreamerSessionError as exc:
                return StreamClientResult(
                    succeeded=False,
                    reason=f"subscribe_malformed_response:{exc}",
                )
            if code is None:
                # No SUBS ack in this frame; could be a heartbeat or a data
                # frame received pre-ack. Continue draining after preserving
                # any parseable supported data entries.
                try:
                    entries = tuple(extract_supported_data_entries(str(raw_response)))
                except OperatorSchwabStreamerSessionError:
                    entries = ()
                if entries:
                    self._pending_data_frames.append(entries)
                continue
            if code != 0:
                return StreamClientResult(succeeded=False, reason=f"subscribe_denied:{service}:code={code}")
            return StreamClientResult(succeeded=True)

        return StreamClientResult(succeeded=False, reason=f"subscribe_ack_missing:{service}")

    # -- close ---------------------------------------------------------------

    def close(self) -> StreamClientResult:
        if self._closed:
            return StreamClientResult(succeeded=True, reason="already_closed")
        self._closed = True
        connection = self._connection
        credentials = self._credentials
        if connection is None:
            return StreamClientResult(succeeded=True, reason="close_no_open_connection")

        logout_error: str | None = None
        if credentials is not None and self._login_succeeded:
            payload = build_logout_payload(credentials)
            try:
                connection.send(json.dumps(payload, separators=(",", ":")))
            except Exception as exc:
                logout_error = f"logout_send_failed:{exc}"

        try:
            connection.close()
        except Exception as exc:
            return StreamClientResult(
                succeeded=False,
                reason=f"close_failed:{exc}" if logout_error is None else f"{logout_error}; close_failed:{exc}",
            )
        finally:
            self._connection = None

        if logout_error is not None:
            return StreamClientResult(succeeded=False, reason=logout_error)
        return StreamClientResult(succeeded=True)

    def _safe_close(self) -> None:
        connection = self._connection
        if connection is None:
            return
        self._closed = True
        try:
            connection.close()
        except Exception:
            pass
        finally:
            self._connection = None

    # -- receive/dispatch handoff -------------------------------------------

    def dispatch_one(self, handler: Callable[[Mapping[str, object]], None]) -> bool:
        """Drain one websocket message and route data frames to ``handler``.

        Returns ``True`` if a message was received (regardless of whether it
        contained data). Returns ``False`` on timeout, EOF, parse failure, or
        when the session is not active (already closed / never logged in).

        This method is the documented receive/dispatch handoff for an
        operator-driven receive loop. It is **not** invoked from any default,
        refresh, readiness, or renderer code path.
        """

        if self._closed or not self._subscribe_succeeded:
            self._last_dispatch_status = "inactive"
            return False
        connection = self._connection
        if connection is None:
            self._last_dispatch_status = "inactive"
            return False

        if not self._refresh_access_token_if_supported():
            self._last_dispatch_status = "token_refresh_failed"
            return False

        if self._pending_data_frames:
            entries = self._pending_data_frames.popleft()
            for entry in entries:
                try:
                    handler(entry)
                except Exception:
                    continue
            self._last_dispatch_status = "message"
            return True

        try:
            raw_message = connection.recv(self._timeout_seconds)
        except TimeoutError:
            self._last_dispatch_status = "timeout"
            return False
        except Exception:
            self._last_dispatch_status = "connection_lost"
            return False

        try:
            entries = extract_supported_data_entries(str(raw_message))
        except OperatorSchwabStreamerSessionError:
            self._last_dispatch_status = "parse_error"
            return True

        for entry in entries:
            try:
                handler(entry)
            except Exception:
                # Handler exceptions never propagate to the receive loop;
                # the caller should observe via the manager's blocking_reasons.
                continue
        self._last_dispatch_status = "message"
        return True

    def dispatch_status(self) -> DispatchStatus:
        return self._last_dispatch_status

    def token_status(self) -> dict[str, object]:
        status_func = getattr(self._access_token_provider, "token_status", None)
        if callable(status_func):
            try:
                status = status_func()
            except Exception:
                return _empty_token_status()
            if isinstance(status, Mapping):
                return {
                    "valid": bool(status.get("valid", False)),
                    "expires_in_seconds": _optional_int(status.get("expires_in_seconds")),
                    "last_refresh_at": _optional_string(status.get("last_refresh_at")),
                    "refresh_count": int(status.get("refresh_count", 0) or 0),
                }
        return _empty_token_status()

    def token_refresh_blocking_reason(self) -> str | None:
        return self._last_token_refresh_error

    def _refresh_access_token_if_supported(self) -> bool:
        refresh_func = getattr(self._access_token_provider, "refresh_if_needed", None)
        if not callable(refresh_func):
            self._last_token_refresh_error = None
            return True
        try:
            result = refresh_func()
        except Exception as exc:
            self._last_token_refresh_error = f"token_refresh_exception:{type(exc).__name__}"
            return False
        if bool(getattr(result, "succeeded", False)):
            self._last_token_refresh_error = None
            return True
        reason = getattr(result, "reason", None) or "token_refresh_failed"
        self._last_token_refresh_error = redact_sensitive_text(reason)
        return False


def _credentials_look_valid(credentials: StreamerCredentials) -> bool:
    fields = (
        credentials.streamer_socket_url,
        credentials.streamer_socket_host,
        credentials.schwab_client_customer_id,
        credentials.schwab_client_correl_id,
        credentials.schwab_client_channel,
        credentials.schwab_client_function_id,
    )
    return all(isinstance(value, str) and value.strip() for value in fields)


def _empty_token_status() -> dict[str, object]:
    return {
        "valid": False,
        "expires_in_seconds": None,
        "last_refresh_at": None,
        "refresh_count": 0,
    }


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


# ---------------------------------------------------------------------------
# Factory builder.
# ---------------------------------------------------------------------------


def build_operator_schwab_streamer_session_factory(
    *,
    access_token_provider: SchwabAccessTokenProvider,
    credentials_provider: SchwabStreamerCredentialsProvider,
    websocket_factory: SchwabWebsocketFactory,
    fields_requested: tuple[int, ...] = DEFAULT_LEVELONE_FUTURES_FIELD_IDS,
    timeout_seconds: float = DEFAULT_RECV_TIMEOUT_SECONDS,
) -> Callable[[SchwabStreamManagerConfig], OperatorSchwabStreamerSession]:
    """Validate dependencies and return a session factory closure.

    The returned closure is consumable by
    :func:`ntb_marimo_console.schwab_stream_client.build_operator_schwab_stream_client_factory`'s
    ``streamer_session_factory`` parameter. The closure is lazy: it does NOT
    invoke any provider, websocket, env, or token surface until the operator
    launcher invokes it under explicit ``OPERATOR_LIVE_RUNTIME`` opt-in.
    """

    if not callable(getattr(access_token_provider, "load_access_token", None)):
        raise TypeError("access_token_provider_must_expose_callable_load_access_token")
    if not callable(getattr(credentials_provider, "load_streamer_credentials", None)):
        raise TypeError("credentials_provider_must_expose_callable_load_streamer_credentials")
    if not callable(getattr(websocket_factory, "connect", None)):
        raise TypeError("websocket_factory_must_expose_callable_connect")
    fields_tuple = tuple(int(f) for f in fields_requested)
    if not fields_tuple:
        raise TypeError("fields_requested_must_not_be_empty")
    timeout = float(timeout_seconds)
    if timeout <= 0:
        raise TypeError("timeout_seconds_must_be_positive")

    def _session_factory(config: SchwabStreamManagerConfig) -> OperatorSchwabStreamerSession:
        return OperatorSchwabStreamerSession(
            access_token_provider=access_token_provider,
            credentials_provider=credentials_provider,
            websocket_factory=websocket_factory,
            fields_requested=fields_tuple,
            timeout_seconds=timeout,
        )

    return _session_factory
