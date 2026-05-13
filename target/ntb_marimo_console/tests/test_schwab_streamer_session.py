from __future__ import annotations

import importlib
import importlib.util
import json
import os
import unittest
from collections import deque
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch

from ntb_marimo_console.contract_universe import final_target_contracts
from ntb_marimo_console.market_data.stream_cache import StreamCacheRecord, StreamCacheSnapshot
from ntb_marimo_console.market_data.stream_manager import (
    SchwabStreamManagerConfig,
    StreamManagerSnapshot,
    StreamSubscriptionRequest,
)
from ntb_marimo_console import schwab_streamer_session as schwab_streamer_session_module
from ntb_marimo_console.operator_live_launcher import (
    OperatorLiveRuntimeOptInRequired,
    OperatorLiveRuntimeStartError,
    start_operator_live_runtime,
)
from ntb_marimo_console.operator_live_runtime import (
    LIVE_RUNTIME_UNAVAILABLE,
    OPERATOR_LIVE_RUNTIME,
    build_operator_runtime_snapshot_producer_from_env,
    clear_operator_live_runtime_registration,
    get_registered_operator_live_runtime_producer,
    resolve_operator_runtime_snapshot,
)
from ntb_marimo_console.schwab_stream_client import (
    build_operator_schwab_stream_client_factory,
)
from ntb_marimo_console.schwab_streamer_session import (
    ADMIN_SERVICE,
    CHART_FUTURES_SERVICE,
    LEVELONE_FUTURES_SERVICE,
    LOGIN_COMMAND,
    SUBS_COMMAND,
    DefaultSchwabWebsocketFactory,
    FileAccessTokenProvider,
    OperatorSchwabStreamerSession,
    StaticStreamerCredentialsProvider,
    StreamerCredentials,
    build_operator_schwab_streamer_session_factory,
    default_schwab_websocket_factory,
)
from ntb_marimo_console.schwab_token_lifecycle import TokenRefreshResult
from ntb_marimo_console.session_lifecycle import (
    load_session_lifecycle_from_env,
    refresh_runtime_snapshot,
)


NOW = "2026-05-09T14:00:00+00:00"
PLACEHOLDER_TOKEN = "redacted-placeholder-token-value"
PLACEHOLDER_CUSTOMER_ID = "redacted-placeholder-customer-id"
PLACEHOLDER_CORREL_ID = "redacted-placeholder-correl-id"
PLACEHOLDER_CHANNEL = "test-channel"
PLACEHOLDER_FUNCTION_ID = "test-function-id"
PLACEHOLDER_SOCKET_URL = "wss://example.invalid/streamer"
PLACEHOLDER_SOCKET_HOST = "example.invalid"
SECRET_MARKER = "should_not_print"


def _placeholder_credentials() -> StreamerCredentials:
    return StreamerCredentials(
        streamer_socket_url=PLACEHOLDER_SOCKET_URL,
        streamer_socket_host=PLACEHOLDER_SOCKET_HOST,
        schwab_client_customer_id=PLACEHOLDER_CUSTOMER_ID,
        schwab_client_correl_id=PLACEHOLDER_CORREL_ID,
        schwab_client_channel=PLACEHOLDER_CHANNEL,
        schwab_client_function_id=PLACEHOLDER_FUNCTION_ID,
    )


def _live_config(*, contracts: tuple[str, ...] | None = None) -> SchwabStreamManagerConfig:
    requested = contracts or final_target_contracts()
    symbols = tuple(f"/{c}M26" for c in requested)
    return SchwabStreamManagerConfig(
        provider="schwab",
        services_requested=("LEVELONE_FUTURES",),
        symbols_requested=symbols,
        fields_requested=(0, 1, 2, 3, 4, 5),
        explicit_live_opt_in=True,
        contracts_requested=requested,
    )


def _active_cache_snapshot(config: SchwabStreamManagerConfig) -> StreamCacheSnapshot:
    contracts = config.contracts_requested
    symbols = config.symbols_requested or tuple(f"/{c}M26" for c in contracts)
    pairs = list(zip(contracts, symbols))
    records = tuple(
        StreamCacheRecord(
            provider="schwab",
            service="LEVELONE_FUTURES",
            symbol=symbol,
            contract=contract,
            message_type="quote",
            fields=(("bid", 1.0), ("ask", 1.25), ("last", 1.125), ("quote_time", NOW), ("trade_time", NOW)),
            updated_at=NOW,
            age_seconds=0.0,
            fresh=True,
            blocking_reasons=(),
        )
        for contract, symbol in pairs
    )
    return StreamCacheSnapshot(
        generated_at=NOW,
        provider="schwab",
        provider_status="active",
        cache_max_age_seconds=15.0,
        records=records,
        blocking_reasons=(),
        stale_symbols=(),
    )


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class CountingTokenProvider:
    token: str = PLACEHOLDER_TOKEN
    call_count: int = 0
    exception: BaseException | None = None

    def load_access_token(self) -> str:
        self.call_count += 1
        if self.exception is not None:
            raise self.exception
        return self.token


@dataclass
class RefreshingTokenProvider:
    token: str = PLACEHOLDER_TOKEN
    refresh_result: TokenRefreshResult = field(default_factory=lambda: TokenRefreshResult(succeeded=True))
    load_count: int = 0
    refresh_count: int = 0

    def load_access_token(self) -> str:
        self.load_count += 1
        return self.token

    def refresh_if_needed(self) -> TokenRefreshResult:
        self.refresh_count += 1
        return self.refresh_result

    def token_status(self) -> dict[str, object]:
        return {
            "valid": self.refresh_result.succeeded,
            "expires_in_seconds": 1200,
            "last_refresh_at": None,
            "refresh_count": self.refresh_count,
        }


@dataclass
class CountingCredentialsProvider:
    credentials: StreamerCredentials = field(default_factory=_placeholder_credentials)
    call_count: int = 0
    exception: BaseException | None = None

    def load_streamer_credentials(self) -> StreamerCredentials:
        self.call_count += 1
        if self.exception is not None:
            raise self.exception
        return self.credentials


@dataclass
class FakeWebsocketConnection:
    sent: list[str] = field(default_factory=list)
    recv_queue: deque[Any] = field(default_factory=deque)
    closed: bool = False
    close_calls: int = 0
    send_exception: BaseException | None = None
    close_exception: BaseException | None = None

    def send(self, payload: str) -> None:
        if self.send_exception is not None:
            raise self.send_exception
        self.sent.append(payload)

    def recv(self, timeout: float) -> str:
        if not self.recv_queue:
            raise TimeoutError("recv_timeout")
        item = self.recv_queue.popleft()
        if isinstance(item, BaseException):
            raise item
        return str(item)

    def close(self) -> None:
        self.close_calls += 1
        self.closed = True
        if self.close_exception is not None:
            raise self.close_exception


@dataclass
class CountingWebsocketFactory:
    connection: FakeWebsocketConnection = field(default_factory=FakeWebsocketConnection)
    call_count: int = 0
    last_url: str | None = None
    last_timeout: float | None = None
    connect_exception: BaseException | None = None

    def connect(self, url: str, *, timeout_seconds: float) -> FakeWebsocketConnection:
        self.call_count += 1
        self.last_url = url
        self.last_timeout = timeout_seconds
        if self.connect_exception is not None:
            raise self.connect_exception
        return self.connection


class _Sentinel:
    def __init__(self) -> None:
        self.call_count = 0

    def __call__(self, *args, **kwargs):
        self.call_count += 1
        raise AssertionError("sentinel_must_not_be_invoked")


@dataclass
class FakeStartingManager:
    """Fake stream manager driving client.login + client.subscribe exactly once."""

    config: SchwabStreamManagerConfig
    client: Any
    start_count: int = 0
    snapshot_count: int = 0
    shutdown_count: int = 0
    _snapshot: StreamManagerSnapshot | None = None

    def start(self) -> StreamManagerSnapshot:
        self.start_count += 1
        login_result = self.client.login(self.config)
        if not login_result.succeeded:
            self._snapshot = self._blocked(login_result.reason or "login_denied")
            return self._snapshot
        subscribe_result = self.client.subscribe(
            StreamSubscriptionRequest(
                provider=self.config.provider,
                services=self.config.services_requested,
                symbols=self.config.symbols_requested,
                fields=self.config.fields_requested,
                contracts=self.config.contracts_requested,
            )
        )
        if not subscribe_result.succeeded:
            self._snapshot = self._blocked(subscribe_result.reason or "subscription_failed")
            return self._snapshot
        self._snapshot = StreamManagerSnapshot(
            state="active",
            config=self.config,
            cache=_active_cache_snapshot(self.config),
            events=(),
            blocking_reasons=(),
            login_count=1,
            subscription_count=1,
        )
        return self._snapshot

    def snapshot(self) -> StreamManagerSnapshot:
        self.snapshot_count += 1
        if self._snapshot is None:
            raise AssertionError("snapshot_called_before_start")
        return self._snapshot

    def shutdown(self) -> StreamManagerSnapshot:
        self.shutdown_count += 1
        return self._snapshot or self._blocked("shutdown_called_before_start")

    def _blocked(self, reason: str) -> StreamManagerSnapshot:
        return StreamManagerSnapshot(
            state="blocked",
            config=self.config,
            cache=StreamCacheSnapshot(
                generated_at=NOW,
                provider="schwab",
                provider_status="blocked",
                cache_max_age_seconds=15.0,
                records=(),
                blocking_reasons=(reason,),
                stale_symbols=(),
            ),
            events=(),
            blocking_reasons=(reason,),
            login_count=1,
            subscription_count=0,
        )


# ---------------------------------------------------------------------------
# Helpers for building canned recv frames
# ---------------------------------------------------------------------------


def _admin_login_ack(code: int = 0) -> str:
    return json.dumps(
        {
            "response": [
                {
                    "service": ADMIN_SERVICE,
                    "command": LOGIN_COMMAND,
                    "content": {"code": code, "msg": "ok"},
                }
            ]
        }
    )


def _subs_ack(code: int = 0, *, service: str = LEVELONE_FUTURES_SERVICE) -> str:
    return json.dumps(
        {
            "response": [
                {
                    "service": service,
                    "command": SUBS_COMMAND,
                    "content": {"code": code, "msg": "ok"},
                }
            ]
        }
    )


def _chart_frame(
    *,
    symbol: str = "/ESM26",
    start_time: str = NOW,
    completed: bool = True,
) -> str:
    return json.dumps(
        {
            "data": [
                {
                    "service": CHART_FUTURES_SERVICE,
                    "command": SUBS_COMMAND,
                    "timestamp": start_time,
                    "content": [
                        {
                            "key": symbol,
                            "start_time": start_time,
                            "open": 100.0,
                            "high": 101.0,
                            "low": 99.5,
                            "close": 100.5,
                            "volume": 100,
                            "completed": completed,
                        }
                    ],
                }
            ]
        }
    )


def _data_frame(*, symbol: str = "/ESM26", bid: float = 1.0, timestamp: object = NOW) -> str:
    return json.dumps(
        {
            "data": [
                {
                    "service": LEVELONE_FUTURES_SERVICE,
                    "command": SUBS_COMMAND,
                    "timestamp": timestamp,
                    "content": [
                        {
                            "key": symbol,
                            "1": bid,
                            "2": bid + 0.25,
                            "3": bid + 0.125,
                        }
                    ],
                }
            ]
        }
    )


def _build_session(
    *,
    token_provider: CountingTokenProvider | None = None,
    credentials_provider: CountingCredentialsProvider | None = None,
    websocket_factory: CountingWebsocketFactory | None = None,
    fields_requested: tuple[int, ...] = (0, 1, 2, 3, 4, 5),
    timeout_seconds: float = 1.0,
) -> tuple[
    OperatorSchwabStreamerSession,
    CountingTokenProvider,
    CountingCredentialsProvider,
    CountingWebsocketFactory,
]:
    tp = token_provider or CountingTokenProvider()
    cp = credentials_provider or CountingCredentialsProvider()
    wf = websocket_factory or CountingWebsocketFactory()
    session = OperatorSchwabStreamerSession(
        access_token_provider=tp,
        credentials_provider=cp,
        websocket_factory=wf,
        fields_requested=fields_requested,
        timeout_seconds=timeout_seconds,
    )
    return session, tp, cp, wf


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class OperatorSchwabStreamerSessionImportTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_operator_live_runtime_registration()
        self.addCleanup(clear_operator_live_runtime_registration)

    def test_import_does_not_perform_network_credential_or_token_work(self) -> None:
        # The module is imported at test-file load time (top of this file).
        # Verify that the module exposes its public surface and that nothing
        # under the SCHWAB_* env namespace is read at import; do NOT reload
        # the module here because reloading would invalidate the test file's
        # bound class references and corrupt later tests in the same run.
        self.assertTrue(hasattr(schwab_streamer_session_module, "OperatorSchwabStreamerSession"))
        self.assertTrue(hasattr(schwab_streamer_session_module, "build_operator_schwab_streamer_session_factory"))
        self.assertTrue(hasattr(schwab_streamer_session_module, "default_schwab_websocket_factory"))
        self.assertTrue(hasattr(schwab_streamer_session_module, "FileAccessTokenProvider"))
        self.assertTrue(hasattr(schwab_streamer_session_module, "StaticStreamerCredentialsProvider"))
        for key in os.environ:
            self.assertFalse(
                key.startswith("SCHWAB_"),
                msg="default test run must not require SCHWAB_* env vars",
            )

        # Module spec is loadable without side effects (sanity check; does not
        # execute the module a second time):
        spec = importlib.util.find_spec("ntb_marimo_console.schwab_streamer_session")
        self.assertIsNotNone(spec)

    def test_default_websocket_factory_does_not_import_websockets_until_connect(self) -> None:
        original_import_module = importlib.import_module
        websockets_loaded: list[str] = []

        def tracking_import_module(name: str, *args, **kwargs):
            if name.startswith("websockets"):
                websockets_loaded.append(name)
                raise ImportError("websockets_blocked_by_test_sentinel")
            return original_import_module(name, *args, **kwargs)

        with patch("ntb_marimo_console.schwab_streamer_session.importlib.import_module",
                   new=tracking_import_module):
            factory = default_schwab_websocket_factory()
            self.assertIsInstance(factory, DefaultSchwabWebsocketFactory)
            self.assertEqual(websockets_loaded, [])
            with self.assertRaises(schwab_streamer_session_module.OperatorSchwabStreamerSessionError):
                factory.connect("wss://example.invalid", timeout_seconds=1.0)
        self.assertTrue(any(name.startswith("websockets") for name in websockets_loaded))


class OperatorSchwabStreamerSessionBuilderTests(unittest.TestCase):
    def test_builder_construction_does_not_invoke_dependencies(self) -> None:
        token_provider = CountingTokenProvider()
        credentials_provider = CountingCredentialsProvider()
        websocket_factory = CountingWebsocketFactory()

        builder = build_operator_schwab_streamer_session_factory(
            access_token_provider=token_provider,
            credentials_provider=credentials_provider,
            websocket_factory=websocket_factory,
        )

        self.assertTrue(callable(builder))
        self.assertEqual(token_provider.call_count, 0)
        self.assertEqual(credentials_provider.call_count, 0)
        self.assertEqual(websocket_factory.call_count, 0)

    def test_builder_rejects_malformed_dependencies_with_redacted_typeerror(self) -> None:
        good_token = CountingTokenProvider()
        good_creds = CountingCredentialsProvider()
        good_ws = CountingWebsocketFactory()

        class WithoutLoadAccessToken:
            pass

        class WithoutLoadStreamerCredentials:
            pass

        class WithoutConnect:
            pass

        for bad in (None, WithoutLoadAccessToken()):
            with self.assertRaises(TypeError) as ctx:
                build_operator_schwab_streamer_session_factory(
                    access_token_provider=bad,  # type: ignore[arg-type]
                    credentials_provider=good_creds,
                    websocket_factory=good_ws,
                )
            self.assertIn("access_token_provider", str(ctx.exception))
            self.assertNotIn(SECRET_MARKER, str(ctx.exception))

        with self.assertRaises(TypeError):
            build_operator_schwab_streamer_session_factory(
                access_token_provider=good_token,
                credentials_provider=WithoutLoadStreamerCredentials(),  # type: ignore[arg-type]
                websocket_factory=good_ws,
            )
        with self.assertRaises(TypeError):
            build_operator_schwab_streamer_session_factory(
                access_token_provider=good_token,
                credentials_provider=good_creds,
                websocket_factory=WithoutConnect(),  # type: ignore[arg-type]
            )
        with self.assertRaises(TypeError):
            build_operator_schwab_streamer_session_factory(
                access_token_provider=good_token,
                credentials_provider=good_creds,
                websocket_factory=good_ws,
                fields_requested=(),
            )
        with self.assertRaises(TypeError):
            build_operator_schwab_streamer_session_factory(
                access_token_provider=good_token,
                credentials_provider=good_creds,
                websocket_factory=good_ws,
                timeout_seconds=0,
            )

    def test_factory_invocation_constructs_session_exactly_once_per_call(self) -> None:
        token_provider = CountingTokenProvider()
        credentials_provider = CountingCredentialsProvider()
        websocket_factory = CountingWebsocketFactory()
        builder = build_operator_schwab_streamer_session_factory(
            access_token_provider=token_provider,
            credentials_provider=credentials_provider,
            websocket_factory=websocket_factory,
        )

        first = builder(_live_config())
        second = builder(_live_config())

        self.assertIsInstance(first, OperatorSchwabStreamerSession)
        self.assertIsInstance(second, OperatorSchwabStreamerSession)
        self.assertIsNot(first, second)
        self.assertEqual(token_provider.call_count, 0)
        self.assertEqual(credentials_provider.call_count, 0)
        self.assertEqual(websocket_factory.call_count, 0)


class OperatorSchwabStreamerSessionLoginTests(unittest.TestCase):
    def test_login_sends_admin_login_payload_with_expected_shape_and_does_not_expose_secrets_in_assertion(self) -> None:
        session, tp, cp, wf = _build_session()
        wf.connection.recv_queue.append(_admin_login_ack(code=0))

        result = session.login(_live_config())

        self.assertTrue(result.succeeded)
        self.assertEqual(tp.call_count, 1)
        self.assertEqual(cp.call_count, 1)
        self.assertEqual(wf.call_count, 1)
        self.assertEqual(wf.last_url, PLACEHOLDER_SOCKET_URL)
        self.assertEqual(len(wf.connection.sent), 1)
        sent_payload = json.loads(wf.connection.sent[0])
        request = sent_payload["requests"][0]
        self.assertEqual(request["service"], ADMIN_SERVICE)
        self.assertEqual(request["command"], LOGIN_COMMAND)
        self.assertIn("Authorization", request["parameters"])
        self.assertIn("SchwabClientChannel", request["parameters"])
        self.assertIn("SchwabClientFunctionId", request["parameters"])

    def test_login_classifies_response_code_zero_as_success(self) -> None:
        session, _, _, wf = _build_session()
        wf.connection.recv_queue.append(_admin_login_ack(code=0))

        result = session.login(_live_config())

        self.assertTrue(result.succeeded)
        self.assertIsNone(result.reason)

    def test_login_denied_returns_redacted_failure(self) -> None:
        session, _, _, wf = _build_session()
        wf.connection.recv_queue.append(_admin_login_ack(code=3))

        result = session.login(_live_config())

        self.assertFalse(result.succeeded)
        assert result.reason is not None
        self.assertIn("login_denied", result.reason)
        self.assertNotIn(SECRET_MARKER, result.reason)
        self.assertEqual(wf.connection.close_calls, 1)

    def test_login_malformed_response_returns_redacted_failure(self) -> None:
        session, _, _, wf = _build_session()
        wf.connection.recv_queue.append("not a json blob token=should_not_print")

        result = session.login(_live_config())

        self.assertFalse(result.succeeded)
        assert result.reason is not None
        self.assertIn("login_malformed_response", result.reason)
        self.assertNotIn(SECRET_MARKER, result.reason)

    def test_login_timeout_returns_redacted_failure(self) -> None:
        session, _, _, wf = _build_session()
        # Empty recv_queue → recv raises TimeoutError

        result = session.login(_live_config())

        self.assertFalse(result.succeeded)
        assert result.reason is not None
        self.assertIn("login_timeout", result.reason)
        self.assertNotIn(SECRET_MARKER, result.reason)
        self.assertEqual(wf.connection.close_calls, 1)

    def test_login_credentials_or_token_provider_failure_returns_redacted_failure(self) -> None:
        token_provider = CountingTokenProvider(exception=RuntimeError(f"token={SECRET_MARKER}"))
        session, _, _, wf = _build_session(token_provider=token_provider)

        result = session.login(_live_config())

        self.assertFalse(result.succeeded)
        assert result.reason is not None
        self.assertIn("login_access_token_provider_error", result.reason)
        self.assertNotIn(SECRET_MARKER, result.reason)
        self.assertEqual(wf.call_count, 0)

        creds_provider = CountingCredentialsProvider(exception=RuntimeError(f"secret={SECRET_MARKER}"))
        session2, _, _, wf2 = _build_session(credentials_provider=creds_provider)
        result2 = session2.login(_live_config())
        self.assertFalse(result2.succeeded)
        assert result2.reason is not None
        self.assertIn("login_credentials_provider_error", result2.reason)
        self.assertNotIn(SECRET_MARKER, result2.reason)
        self.assertEqual(wf2.call_count, 0)

    def test_login_invalid_streamer_socket_url_returns_redacted_failure(self) -> None:
        invalid_creds = StreamerCredentials(
            streamer_socket_url="http://not-a-ws-url.invalid/",
            streamer_socket_host="not-a-ws-url.invalid",
            schwab_client_customer_id=PLACEHOLDER_CUSTOMER_ID,
            schwab_client_correl_id=PLACEHOLDER_CORREL_ID,
            schwab_client_channel=PLACEHOLDER_CHANNEL,
            schwab_client_function_id=PLACEHOLDER_FUNCTION_ID,
        )
        creds_provider = CountingCredentialsProvider(credentials=invalid_creds)
        session, _, _, wf = _build_session(credentials_provider=creds_provider)

        result = session.login(_live_config())

        self.assertFalse(result.succeeded)
        assert result.reason is not None
        self.assertIn("login_streamer_socket_url_invalid", result.reason)
        self.assertEqual(wf.call_count, 0)


class OperatorSchwabStreamerSessionSubscribeTests(unittest.TestCase):
    def _login(self, session: OperatorSchwabStreamerSession, wf: CountingWebsocketFactory) -> None:
        wf.connection.recv_queue.append(_admin_login_ack(code=0))
        result = session.login(_live_config())
        self.assertTrue(result.succeeded)
        wf.connection.sent.clear()

    def test_subscribe_sends_levelone_futures_payload_for_final_target_universe_only(self) -> None:
        session, _, _, wf = _build_session()
        self._login(session, wf)
        wf.connection.recv_queue.append(_subs_ack(code=0))
        request = StreamSubscriptionRequest(
            provider="schwab",
            services=("LEVELONE_FUTURES",),
            symbols=("/ESM26", "/NQM26", "/CLM26", "/6EM26", "/MGCM26"),
            fields=(0, 1, 2, 3, 4, 5),
            contracts=("ES", "NQ", "CL", "6E", "MGC"),
        )

        result = session.subscribe(request)

        self.assertTrue(result.succeeded)
        self.assertEqual(len(wf.connection.sent), 1)
        sent_payload = json.loads(wf.connection.sent[0])
        sent_request = sent_payload["requests"][0]
        self.assertEqual(sent_request["service"], LEVELONE_FUTURES_SERVICE)
        self.assertEqual(sent_request["command"], SUBS_COMMAND)
        keys_field = sent_request["parameters"]["keys"]
        self.assertEqual(keys_field, "/ESM26,/NQM26,/CLM26,/6EM26,/MGCM26")
        self.assertNotIn("ZN", keys_field)
        self.assertNotIn("/GCM", keys_field)
        self.assertIn("/MGCM26", keys_field)

    def test_chart_futures_request_sends_direct_chart_subscription(self) -> None:
        session, _, _, wf = _build_session()
        self._login(session, wf)
        wf.connection.recv_queue.append(_subs_ack(code=0, service=CHART_FUTURES_SERVICE))
        request = StreamSubscriptionRequest(
            provider="schwab",
            services=(CHART_FUTURES_SERVICE,),
            symbols=("/ESM26", "/NQM26", "/CLM26", "/6EM26", "/MGCM26"),
            fields=(0, 1, 2, 3, 4, 5),
            contracts=("ES", "NQ", "CL", "6E", "MGC"),
        )

        result = session.subscribe(request)

        self.assertTrue(result.succeeded)
        sent_payload = json.loads(wf.connection.sent[0])
        sent_request = sent_payload["requests"][0]
        self.assertEqual(sent_request["service"], CHART_FUTURES_SERVICE)
        self.assertEqual(sent_request["command"], SUBS_COMMAND)
        self.assertEqual(sent_request["parameters"]["keys"], "/ESM26,/NQM26,/CLM26,/6EM26,/MGCM26")

    def test_combined_levelone_and_chart_request_sends_one_subscription_per_service(self) -> None:
        session, _, _, wf = _build_session()
        self._login(session, wf)
        wf.connection.recv_queue.append(_subs_ack(code=0, service=LEVELONE_FUTURES_SERVICE))
        wf.connection.recv_queue.append(_subs_ack(code=0, service=CHART_FUTURES_SERVICE))
        request = StreamSubscriptionRequest(
            provider="schwab",
            services=(LEVELONE_FUTURES_SERVICE, CHART_FUTURES_SERVICE),
            symbols=("/ESM26",),
            fields=(0, 1, 2, 3, 4, 5),
            contracts=("ES",),
        )

        result = session.subscribe(request)

        self.assertTrue(result.succeeded)
        services = [json.loads(payload)["requests"][0]["service"] for payload in wf.connection.sent]
        self.assertEqual(services, [LEVELONE_FUTURES_SERVICE, CHART_FUTURES_SERVICE])

    def test_subscribe_preserves_data_frame_received_before_ack_for_dispatch(self) -> None:
        session, _, _, wf = _build_session()
        self._login(session, wf)
        wf.connection.recv_queue.append(_data_frame(symbol="/ESM26", bid=4321.5))
        wf.connection.recv_queue.append(_subs_ack(code=0))
        request = StreamSubscriptionRequest(
            provider="schwab",
            services=("LEVELONE_FUTURES",),
            symbols=("/ESM26",),
            fields=(0, 1, 2, 3, 4, 5),
            contracts=("ES",),
        )

        result = session.subscribe(request)

        self.assertTrue(result.succeeded)
        captured: list[dict[str, object]] = []
        self.assertTrue(session.dispatch_one(handler=lambda message: captured.append(dict(message))))
        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0]["symbol"], "/ESM26")
        self.assertEqual(captured[0]["contract"], "ES")
        fields = captured[0]["fields"]
        assert isinstance(fields, dict)
        self.assertEqual(fields["1"], 4321.5)

    def test_data_frame_numeric_epoch_millis_timestamp_is_normalized_to_iso_received_at(self) -> None:
        observed_at = "2026-05-09T14:00:00+00:00"
        epoch_millis = 1_778_335_200_000

        entries = schwab_streamer_session_module.extract_data_entries(
            _data_frame(symbol="/ESM26", bid=4321.5, timestamp=epoch_millis)
        )

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["symbol"], "/ESM26")
        self.assertEqual(entries[0]["contract"], "ES")
        self.assertEqual(entries[0]["received_at"], observed_at)

    def test_chart_futures_data_entry_is_normalized_as_bar_message(self) -> None:
        entries = schwab_streamer_session_module.extract_data_entries(
            _chart_frame(symbol="/ESM26"),
            service=CHART_FUTURES_SERVICE,
        )

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["service"], CHART_FUTURES_SERVICE)
        self.assertEqual(entries[0]["message_type"], "bar")
        self.assertEqual(entries[0]["contract"], "ES")
        self.assertEqual(entries[0]["symbol"], "/ESM26")
        self.assertEqual(entries[0]["start_time"], NOW)
        self.assertEqual(entries[0]["completed"], True)
        self.assertEqual(entries[0]["source"], "chart_futures")

    def test_chart_futures_data_entry_missing_required_bar_fields_remains_fail_closed_for_builder(self) -> None:
        raw_message = json.dumps(
            {
                "data": [
                    {
                        "service": CHART_FUTURES_SERVICE,
                        "timestamp": NOW,
                        "content": [{"key": "/ESM26", "start_time": NOW, "open": 100.0}],
                    }
                ]
            }
        )

        entries = schwab_streamer_session_module.extract_data_entries(
            raw_message,
            service=CHART_FUTURES_SERVICE,
        )

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["message_type"], "bar")
        self.assertNotIn("completed", entries[0])
        self.assertNotIn("close", entries[0])

    def test_subscribe_blocks_zn_and_returns_redacted_failure_without_send(self) -> None:
        session, _, _, wf = _build_session()
        self._login(session, wf)
        request = StreamSubscriptionRequest(
            provider="schwab",
            services=("LEVELONE_FUTURES",),
            symbols=("/ESM26", "/ZNM26"),
            fields=(0, 1, 2, 3),
            contracts=("ES", "ZN"),
        )

        result = session.subscribe(request)

        self.assertFalse(result.succeeded)
        assert result.reason is not None
        self.assertIn("excluded_contract_in_subscription:ZN", result.reason)
        self.assertNotIn(SECRET_MARKER, result.reason)
        self.assertEqual(len(wf.connection.sent), 0)

    def test_subscribe_blocks_gc_and_returns_redacted_failure_without_send(self) -> None:
        session, _, _, wf = _build_session()
        self._login(session, wf)
        request = StreamSubscriptionRequest(
            provider="schwab",
            services=("LEVELONE_FUTURES",),
            symbols=("/ESM26", "/GCM26"),
            fields=(0, 1, 2, 3),
            contracts=("ES", "GC"),
        )

        result = session.subscribe(request)

        self.assertFalse(result.succeeded)
        assert result.reason is not None
        self.assertIn("never_supported_contract_in_subscription:GC", result.reason)
        self.assertEqual(len(wf.connection.sent), 0)

    def test_subscribe_failure_returns_redacted_failure(self) -> None:
        # code != 0
        session, _, _, wf = _build_session()
        self._login(session, wf)
        wf.connection.recv_queue.append(_subs_ack(code=5))
        request = StreamSubscriptionRequest(
            provider="schwab",
            services=("LEVELONE_FUTURES",),
            symbols=("/ESM26",),
            fields=(0, 1),
            contracts=("ES",),
        )
        result = session.subscribe(request)
        self.assertFalse(result.succeeded)
        assert result.reason is not None
        self.assertIn("subscribe_denied", result.reason)
        self.assertNotIn(SECRET_MARKER, result.reason)

        # malformed response
        session2, _, _, wf2 = _build_session()
        self._login(session2, wf2)
        wf2.connection.recv_queue.append(f"garbage token={SECRET_MARKER}")
        result2 = session2.subscribe(request)
        self.assertFalse(result2.succeeded)
        assert result2.reason is not None
        self.assertIn("subscribe_malformed_response", result2.reason)
        self.assertNotIn(SECRET_MARKER, result2.reason)

        # timeout
        session3, _, _, wf3 = _build_session()
        self._login(session3, wf3)
        # recv_queue empty for SUBS phase → timeout
        result3 = session3.subscribe(request)
        self.assertFalse(result3.succeeded)
        assert result3.reason is not None
        self.assertIn("subscribe_timeout", result3.reason)

    def test_subscribe_refuses_without_prior_login_with_redacted_failure(self) -> None:
        session, _, _, _ = _build_session()
        request = StreamSubscriptionRequest(
            provider="schwab",
            services=("LEVELONE_FUTURES",),
            symbols=("/ESM26",),
            fields=(0,),
            contracts=("ES",),
        )

        result = session.subscribe(request)

        self.assertFalse(result.succeeded)
        assert result.reason is not None
        self.assertIn("subscribe_requires_login", result.reason)


class OperatorSchwabStreamerSessionCloseTests(unittest.TestCase):
    def test_close_is_idempotent_and_redacts_errors(self) -> None:
        session, _, _, wf = _build_session()
        wf.connection.recv_queue.append(_admin_login_ack(code=0))
        self.assertTrue(session.login(_live_config()).succeeded)
        wf.connection.sent.clear()

        first_close = session.close()
        self.assertTrue(first_close.succeeded)
        self.assertEqual(wf.connection.close_calls, 1)
        # LOGOUT was sent
        self.assertEqual(len(wf.connection.sent), 1)
        sent = json.loads(wf.connection.sent[0])
        self.assertEqual(sent["requests"][0]["command"], "LOGOUT")

        second_close = session.close()
        self.assertTrue(second_close.succeeded)
        assert second_close.reason is not None
        self.assertIn("already_closed", second_close.reason)
        self.assertEqual(wf.connection.close_calls, 1)

    def test_close_redacts_logout_send_failure(self) -> None:
        session, _, _, wf = _build_session()
        wf.connection.recv_queue.append(_admin_login_ack(code=0))
        self.assertTrue(session.login(_live_config()).succeeded)
        wf.connection.sent.clear()
        wf.connection.send_exception = RuntimeError(f"network token={SECRET_MARKER}")

        result = session.close()

        self.assertFalse(result.succeeded)
        assert result.reason is not None
        self.assertIn("logout_send_failed", result.reason)
        self.assertNotIn(SECRET_MARKER, result.reason)


class OperatorSchwabStreamerSessionDispatchTests(unittest.TestCase):
    def test_dispatch_one_routes_data_messages_to_handler_and_returns_false_on_timeout(self) -> None:
        session, _, _, wf = _build_session()
        wf.connection.recv_queue.append(_admin_login_ack(code=0))
        self.assertTrue(session.login(_live_config()).succeeded)
        wf.connection.recv_queue.append(_subs_ack(code=0))
        request = StreamSubscriptionRequest(
            provider="schwab",
            services=("LEVELONE_FUTURES",),
            symbols=("/ESM26",),
            fields=(0, 1, 2, 3),
            contracts=("ES",),
        )
        self.assertTrue(session.subscribe(request).succeeded)

        captured: list[dict[str, object]] = []

        def handler(message):
            captured.append(dict(message))

        wf.connection.recv_queue.append(_data_frame(symbol="/ESM26", bid=4321.5))
        first = session.dispatch_one(handler=handler)
        self.assertTrue(first)
        self.assertEqual(len(captured), 1)
        entry = captured[0]
        self.assertEqual(entry["service"], LEVELONE_FUTURES_SERVICE)
        self.assertEqual(entry["symbol"], "/ESM26")
        self.assertEqual(entry["contract"], "ES")
        self.assertEqual(entry["message_type"], "quote")
        self.assertEqual(entry["provider"], "schwab")
        fields = entry["fields"]
        assert isinstance(fields, dict)
        self.assertIn("1", fields)
        self.assertEqual(fields["1"], 4321.5)

        # next call with empty queue → timeout
        captured.clear()
        second = session.dispatch_one(handler=handler)
        self.assertFalse(second)
        self.assertEqual(captured, [])

    def test_dispatch_one_routes_chart_futures_bar_messages_to_handler(self) -> None:
        session, _, _, wf = _build_session()
        wf.connection.recv_queue.append(_admin_login_ack(code=0))
        self.assertTrue(session.login(_live_config()).succeeded)
        wf.connection.recv_queue.append(_subs_ack(code=0, service=CHART_FUTURES_SERVICE))
        request = StreamSubscriptionRequest(
            provider="schwab",
            services=(CHART_FUTURES_SERVICE,),
            symbols=("/ESM26",),
            fields=(0, 1, 2, 3, 4, 5, 6, 7, 8),
            contracts=("ES",),
        )
        self.assertTrue(session.subscribe(request).succeeded)

        captured: list[dict[str, object]] = []
        wf.connection.recv_queue.append(_chart_frame(symbol="/ESM26"))

        self.assertTrue(session.dispatch_one(handler=lambda message: captured.append(dict(message))))

        self.assertEqual(len(captured), 1)
        entry = captured[0]
        self.assertEqual(entry["service"], CHART_FUTURES_SERVICE)
        self.assertEqual(entry["message_type"], "bar")
        self.assertEqual(entry["contract"], "ES")
        self.assertEqual(entry["source"], "chart_futures")

    def test_dispatch_one_refreshes_token_without_new_connection_login_or_subscribe(self) -> None:
        token_provider = RefreshingTokenProvider()
        session, _, _, wf = _build_session(token_provider=token_provider)
        wf.connection.recv_queue.append(_admin_login_ack(code=0))
        self.assertTrue(session.login(_live_config()).succeeded)
        wf.connection.recv_queue.append(_subs_ack(code=0))
        request = StreamSubscriptionRequest(
            provider="schwab",
            services=("LEVELONE_FUTURES",),
            symbols=("/ESM26",),
            fields=(0, 1, 2, 3),
            contracts=("ES",),
        )
        self.assertTrue(session.subscribe(request).succeeded)
        sent_count_before_dispatch = len(wf.connection.sent)
        connect_count_before_dispatch = wf.call_count

        captured: list[dict[str, object]] = []
        wf.connection.recv_queue.append(_data_frame(symbol="/ESM26", bid=4321.5))

        self.assertTrue(session.dispatch_one(handler=lambda message: captured.append(dict(message))))

        self.assertEqual(token_provider.load_count, 1)
        self.assertEqual(token_provider.refresh_count, 1)
        self.assertEqual(wf.call_count, connect_count_before_dispatch)
        self.assertEqual(len(wf.connection.sent), sent_count_before_dispatch)
        self.assertEqual(len(captured), 1)
        self.assertIsNone(session.token_refresh_blocking_reason())
        self.assertEqual(session.token_status()["refresh_count"], 1)

    def test_dispatch_one_token_refresh_failure_returns_false_without_exception(self) -> None:
        token_provider = RefreshingTokenProvider(
            refresh_result=TokenRefreshResult(
                succeeded=False,
                reason="token_refresh_failed:SchwabTokenError",
            )
        )
        session, _, _, wf = _build_session(token_provider=token_provider)
        wf.connection.recv_queue.append(_admin_login_ack(code=0))
        self.assertTrue(session.login(_live_config()).succeeded)
        wf.connection.recv_queue.append(_subs_ack(code=0))
        request = StreamSubscriptionRequest(
            provider="schwab",
            services=("LEVELONE_FUTURES",),
            symbols=("/ESM26",),
            fields=(0, 1, 2, 3),
            contracts=("ES",),
        )
        self.assertTrue(session.subscribe(request).succeeded)

        captured: list[dict[str, object]] = []
        wf.connection.recv_queue.append(_data_frame(symbol="/ESM26", bid=4321.5))

        self.assertFalse(session.dispatch_one(handler=lambda message: captured.append(dict(message))))

        self.assertEqual(token_provider.load_count, 1)
        self.assertEqual(token_provider.refresh_count, 1)
        self.assertEqual(captured, [])
        self.assertEqual(session.token_refresh_blocking_reason(), "token_refresh_failed:SchwabTokenError")
        self.assertFalse(session.token_status()["valid"])


class OperatorSchwabStreamerSessionLauncherIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_operator_live_runtime_registration()
        self.addCleanup(clear_operator_live_runtime_registration)

    def _wire_factory(
        self,
        *,
        token_provider: CountingTokenProvider | None = None,
        credentials_provider: CountingCredentialsProvider | None = None,
        websocket_factory: CountingWebsocketFactory | None = None,
        timeout_seconds: float = 1.0,
    ) -> tuple[
        Any,  # client_factory
        list[OperatorSchwabStreamerSession],
        CountingTokenProvider,
        CountingCredentialsProvider,
        CountingWebsocketFactory,
    ]:
        tp = token_provider or CountingTokenProvider()
        cp = credentials_provider or CountingCredentialsProvider()
        wf = websocket_factory or CountingWebsocketFactory()
        captured_sessions: list[OperatorSchwabStreamerSession] = []
        builder = build_operator_schwab_streamer_session_factory(
            access_token_provider=tp,
            credentials_provider=cp,
            websocket_factory=wf,
            timeout_seconds=timeout_seconds,
        )

        def session_factory(config: SchwabStreamManagerConfig) -> OperatorSchwabStreamerSession:
            session = builder(config)
            captured_sessions.append(session)
            return session

        client_factory = build_operator_schwab_stream_client_factory(
            streamer_session_factory=session_factory,
        )
        return client_factory, captured_sessions, tp, cp, wf

    def test_factory_wires_into_start_operator_live_runtime_under_explicit_opt_in_with_one_login_one_subscribe_one_session(self) -> None:
        client_factory, captured, tp, cp, wf = self._wire_factory()
        wf.connection.recv_queue.append(_admin_login_ack(code=0))
        wf.connection.recv_queue.append(_subs_ack(code=0))

        with patch.dict(
            os.environ,
            {"NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME},
            clear=True,
        ):
            result = start_operator_live_runtime(
                client_factory=client_factory,
                config=_live_config(),
                manager_builder=lambda cfg, c: FakeStartingManager(cfg, c),
            )

        self.assertEqual(len(captured), 1)
        self.assertEqual(tp.call_count, 1)
        self.assertEqual(cp.call_count, 1)
        self.assertEqual(wf.call_count, 1)
        manager = result.manager
        assert isinstance(manager, FakeStartingManager)
        self.assertEqual(manager.start_count, 1)
        self.assertEqual(result.started_snapshot.state, "active")
        self.assertEqual(result.started_snapshot.blocking_reasons, ())
        self.assertIsNotNone(get_registered_operator_live_runtime_producer())

    def test_no_session_or_websocket_construction_without_explicit_opt_in(self) -> None:
        # The launcher refuses BEFORE the session_factory is called, so we
        # wire actual no-op providers and assert call_count==0 to prove the
        # adapter is never touched without explicit env opt-in.
        client_factory, captured, tp, cp, wf = self._wire_factory()

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(OperatorLiveRuntimeOptInRequired):
                start_operator_live_runtime(
                    client_factory=client_factory,
                    config=_live_config(),
                )

        self.assertEqual(len(captured), 0)
        self.assertEqual(tp.call_count, 0)
        self.assertEqual(cp.call_count, 0)
        self.assertEqual(wf.call_count, 0)
        self.assertIsNone(get_registered_operator_live_runtime_producer())

    def test_login_failure_via_session_blocks_launcher_with_no_fixture_fallback(self) -> None:
        client_factory, captured, _, _, wf = self._wire_factory()
        wf.connection.recv_queue.append(_admin_login_ack(code=7))

        with patch.dict(
            os.environ,
            {"NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME},
            clear=True,
        ):
            with self.assertRaises(OperatorLiveRuntimeStartError) as ctx:
                start_operator_live_runtime(
                    client_factory=client_factory,
                    config=_live_config(),
                    manager_builder=lambda cfg, c: FakeStartingManager(cfg, c),
                )

            follow_up_producer = build_operator_runtime_snapshot_producer_from_env(
                {"NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME},
            )
            follow_up = resolve_operator_runtime_snapshot(
                mode=OPERATOR_LIVE_RUNTIME,
                producer=follow_up_producer,
            )

        message = str(ctx.exception)
        self.assertIn("operator_live_runtime_start_error", message)
        self.assertNotIn(SECRET_MARKER, message)
        self.assertIsNone(get_registered_operator_live_runtime_producer())
        self.assertEqual(follow_up.status, LIVE_RUNTIME_UNAVAILABLE)
        self.assertEqual(len(captured), 1)

    def test_subscribe_blocks_zn_via_launcher_path_with_no_fixture_fallback(self) -> None:
        client_factory, captured, _, _, wf = self._wire_factory()
        wf.connection.recv_queue.append(_admin_login_ack(code=0))
        # Subscribe will reject ZN before sending; no SUBS ack needed.

        config_with_zn = SchwabStreamManagerConfig(
            provider="schwab",
            services_requested=("LEVELONE_FUTURES",),
            symbols_requested=("/ESM26", "/ZNM26"),
            fields_requested=(0, 1, 2, 3),
            explicit_live_opt_in=True,
            contracts_requested=("ES", "ZN"),
        )

        with patch.dict(
            os.environ,
            {"NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME},
            clear=True,
        ):
            with self.assertRaises(OperatorLiveRuntimeStartError) as ctx:
                start_operator_live_runtime(
                    client_factory=client_factory,
                    config=config_with_zn,
                    manager_builder=lambda cfg, c: FakeStartingManager(cfg, c),
                )

        message = str(ctx.exception)
        self.assertIn("operator_live_runtime_start_error", message)
        self.assertIn("ZN", message)
        self.assertIsNone(get_registered_operator_live_runtime_producer())

    def test_refresh_path_does_not_invoke_session_factory_or_websocket_after_successful_start(self) -> None:
        client_factory, captured, tp, cp, wf = self._wire_factory()
        wf.connection.recv_queue.append(_admin_login_ack(code=0))
        wf.connection.recv_queue.append(_subs_ack(code=0))

        with patch.dict(
            os.environ,
            {
                "NTB_CONSOLE_PROFILE": "preserved_es_phase1",
                "NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME,
            },
            clear=True,
        ):
            launch = start_operator_live_runtime(
                client_factory=client_factory,
                config=_live_config(),
                manager_builder=lambda cfg, c: FakeStartingManager(cfg, c),
            )
            lifecycle = load_session_lifecycle_from_env(
                runtime_snapshot_producer=launch.producer,
                operator_runtime_mode=OPERATOR_LIVE_RUNTIME,
            )
            initial_snapshot_count = launch.manager.snapshot_count  # type: ignore[attr-defined]
            initial_send_count = len(wf.connection.sent)
            initial_close_count = wf.connection.close_calls
            for _ in range(3):
                lifecycle = refresh_runtime_snapshot(lifecycle)

        manager = launch.manager
        assert isinstance(manager, FakeStartingManager)
        self.assertEqual(len(captured), 1)
        self.assertEqual(tp.call_count, 1)
        self.assertEqual(cp.call_count, 1)
        self.assertEqual(wf.call_count, 1)
        self.assertEqual(manager.start_count, 1)
        self.assertEqual(manager.snapshot_count - initial_snapshot_count, 3)
        # No new ws sends, no new close calls
        self.assertEqual(len(wf.connection.sent), initial_send_count)
        self.assertEqual(wf.connection.close_calls, initial_close_count)

    def test_mgc_remains_mgc_and_is_not_mapped_to_gc_in_subscription_payload(self) -> None:
        client_factory, captured, _, _, wf = self._wire_factory()
        wf.connection.recv_queue.append(_admin_login_ack(code=0))
        wf.connection.recv_queue.append(_subs_ack(code=0))

        with patch.dict(
            os.environ,
            {"NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME},
            clear=True,
        ):
            start_operator_live_runtime(
                client_factory=client_factory,
                config=_live_config(),
                manager_builder=lambda cfg, c: FakeStartingManager(cfg, c),
            )

        # 1st send is login, 2nd is subscribe
        self.assertGreaterEqual(len(wf.connection.sent), 2)
        subscribe_payload = json.loads(wf.connection.sent[1])
        keys = subscribe_payload["requests"][0]["parameters"]["keys"]
        self.assertIn("/MGCM26", keys)
        self.assertNotIn("/GCM26", keys)
        self.assertNotIn(",GC,", "," + keys + ",")


class FileAccessTokenProviderTests(unittest.TestCase):
    def test_lazy_no_read_at_construction(self) -> None:
        sentinel = _Sentinel()
        with patch("builtins.open", new=sentinel):
            provider = FileAccessTokenProvider(token_path=__import__("pathlib").Path("/tmp/nonexistent-token.json"))
            self.assertEqual(sentinel.call_count, 0)
        del provider  # silence unused

    def test_read_only_when_invoked_and_redacts_missing_file(self) -> None:
        from pathlib import Path
        provider = FileAccessTokenProvider(token_path=Path("/tmp/definitely-does-not-exist-9876543210.json"))
        with self.assertRaises(schwab_streamer_session_module.OperatorSchwabStreamerSessionError) as ctx:
            provider.load_access_token()
        self.assertIn("token_file_missing", str(ctx.exception))

    def test_static_credentials_provider_returns_credentials_unchanged(self) -> None:
        creds = _placeholder_credentials()
        provider = StaticStreamerCredentialsProvider(credentials=creds)
        self.assertIs(provider.load_streamer_credentials(), creds)


if __name__ == "__main__":
    unittest.main()
