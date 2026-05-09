from __future__ import annotations

import argparse
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from collections import deque
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import patch


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_operator_live_runtime_rehearsal.py"
_spec = importlib.util.spec_from_file_location("run_operator_live_runtime_rehearsal", SCRIPT_PATH)
rehearsal = importlib.util.module_from_spec(_spec)
assert _spec is not None and _spec.loader is not None
sys.modules["run_operator_live_runtime_rehearsal"] = rehearsal
_spec.loader.exec_module(rehearsal)


from ntb_marimo_console.market_data.stream_cache import StreamCacheRecord, StreamCacheSnapshot  # noqa: E402
from ntb_marimo_console.market_data.stream_manager import (  # noqa: E402
    SchwabStreamManagerConfig,
    StreamManagerSnapshot,
    StreamSubscriptionRequest,
)
from ntb_marimo_console.operator_live_runtime import (  # noqa: E402
    LIVE_RUNTIME_UNAVAILABLE,
    OPERATOR_LIVE_RUNTIME,
    build_operator_runtime_snapshot_producer_from_env,
    clear_operator_live_runtime_registration,
    get_registered_operator_live_runtime_producer,
    operator_runtime_mode_from_env,
    resolve_operator_runtime_snapshot,
)
from ntb_marimo_console.schwab_streamer_session import (  # noqa: E402
    StreamerCredentials,
)


PLACEHOLDER_TOKEN = "redacted-placeholder-token-value"
PLACEHOLDER_CUSTOMER_ID = "redacted-placeholder-customer-id"
PLACEHOLDER_CORREL_ID = "redacted-placeholder-correl-id"
PLACEHOLDER_CHANNEL = "test-channel"
PLACEHOLDER_FUNCTION_ID = "test-function-id"
PLACEHOLDER_SOCKET_URL = "wss://example.invalid/streamer"
PLACEHOLDER_SOCKET_HOST = "example.invalid"
SECRET_MARKER = "should_not_print"

NOW = "2026-05-09T14:00:00+00:00"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


@dataclass
class FakeTokenProvider:
    token: str = PLACEHOLDER_TOKEN
    call_count: int = 0
    exception: BaseException | None = None

    def load_access_token(self) -> str:
        self.call_count += 1
        if self.exception is not None:
            raise self.exception
        return self.token


@dataclass
class FakeCredentialsProvider:
    credentials: StreamerCredentials = field(
        default_factory=lambda: StreamerCredentials(
            streamer_socket_url=PLACEHOLDER_SOCKET_URL,
            streamer_socket_host=PLACEHOLDER_SOCKET_HOST,
            schwab_client_customer_id=PLACEHOLDER_CUSTOMER_ID,
            schwab_client_correl_id=PLACEHOLDER_CORREL_ID,
            schwab_client_channel=PLACEHOLDER_CHANNEL,
            schwab_client_function_id=PLACEHOLDER_FUNCTION_ID,
        )
    )
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
    recv_queue: deque = field(default_factory=deque)
    closed: bool = False
    close_calls: int = 0
    send_exception: BaseException | None = None

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


@dataclass
class FakeWebsocketFactory:
    connection: FakeWebsocketConnection = field(default_factory=FakeWebsocketConnection)
    call_count: int = 0
    last_url: str | None = None
    connect_exception: BaseException | None = None

    def connect(self, url: str, *, timeout_seconds: float) -> FakeWebsocketConnection:
        self.call_count += 1
        self.last_url = url
        if self.connect_exception is not None:
            raise self.connect_exception
        return self.connection


@dataclass
class FakeStartingManager:
    config: SchwabStreamManagerConfig
    client: Any
    start_count: int = 0
    snapshot_count: int = 0
    shutdown_count: int = 0
    _snapshot: StreamManagerSnapshot | None = None
    _ingested: int = 0

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
        self._snapshot = self._active_snapshot(record_count=0)
        return self._snapshot

    def snapshot(self) -> StreamManagerSnapshot:
        self.snapshot_count += 1
        if self._snapshot is None:
            raise AssertionError("snapshot_called_before_start")
        return self._snapshot

    def shutdown(self) -> StreamManagerSnapshot:
        self.shutdown_count += 1
        return self._snapshot or self._blocked("shutdown_called_before_start")

    def ingest_message(self, message):
        self._ingested += 1
        # Build a snapshot whose cache has one fresh record per ingest.
        contract = str(message.get("contract", "ES"))
        symbol = str(message.get("symbol", "/ESM26"))
        record = StreamCacheRecord(
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
        existing = list(self._snapshot.cache.records) if self._snapshot else []
        # Replace any existing record with the same contract; otherwise append.
        replaced = False
        for idx, prior in enumerate(existing):
            if prior.contract == contract:
                existing[idx] = record
                replaced = True
                break
        if not replaced:
            existing.append(record)
        self._snapshot = self._active_snapshot(record_count=len(existing), records=tuple(existing))
        return self._snapshot

    def _active_snapshot(self, *, record_count: int, records: tuple[StreamCacheRecord, ...] = ()) -> StreamManagerSnapshot:
        cache_records = records or tuple()
        return StreamManagerSnapshot(
            state="active",
            config=self.config,
            cache=StreamCacheSnapshot(
                generated_at=NOW,
                provider="schwab",
                provider_status="active",
                cache_max_age_seconds=15.0,
                records=cache_records,
                blocking_reasons=(),
                stale_symbols=(),
            ),
            events=(),
            blocking_reasons=(),
            login_count=1,
            subscription_count=1,
        )

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


def _admin_login_ack(code: int = 0) -> str:
    return json.dumps(
        {
            "response": [
                {
                    "service": "ADMIN",
                    "command": "LOGIN",
                    "content": {"code": code, "msg": "ok"},
                }
            ]
        }
    )


def _subs_ack(code: int = 0) -> str:
    return json.dumps(
        {
            "response": [
                {
                    "service": "LEVELONE_FUTURES",
                    "command": "SUBS",
                    "content": {"code": code, "msg": "ok"},
                }
            ]
        }
    )


def _data_frame(symbol: str = "/ESM26", bid: float = 1.0) -> str:
    return json.dumps(
        {
            "data": [
                {
                    "service": "LEVELONE_FUTURES",
                    "command": "SUBS",
                    "timestamp": NOW,
                    "content": [
                        {"key": symbol, "1": bid, "2": bid + 0.25, "3": bid + 0.125}
                    ],
                }
            ]
        }
    )


def _make_args(*, live: bool = True, duration: int = 1, json_mode: bool = False, symbol_overrides: dict[str, str] | None = None) -> argparse.Namespace:
    return argparse.Namespace(
        live=live,
        duration=duration,
        symbol=symbol_overrides or {},
        json=json_mode,
    )


def _make_clock(duration: float = 0.5) -> Any:
    """Monotonic clock that exits the dispatch loop after the given duration."""
    state = {"now": 0.0}

    def _clock() -> float:
        current = state["now"]
        state["now"] += 0.2
        return current

    return _clock


def _full_env(target_root: Path, *, override: dict[str, str] | None = None) -> dict[str, str]:
    state_token_path = target_root / ".state" / "schwab" / "token.json"
    base = {
        "NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME,
        "SCHWAB_APP_KEY": "placeholder-app-key",
        "SCHWAB_APP_SECRET": "placeholder-app-secret",
        "SCHWAB_TOKEN_PATH": str(state_token_path),
    }
    if override:
        base.update(override)
    return base


def _full_env_without_runtime_mode(target_root: Path, *, override: dict[str, str] | None = None) -> dict[str, str]:
    env = _full_env(target_root, override=override)
    env.pop("NTB_OPERATOR_RUNTIME_MODE", None)
    return env


def _ensure_token_file(target_root: Path) -> Path:
    """Create a placeholder token file under target/.state/ for tests that need token_file_present=yes."""
    token_path = target_root / ".state" / "schwab" / "token.json"
    token_path.parent.mkdir(parents=True, exist_ok=True)
    if not token_path.exists():
        token_path.write_text(
            json.dumps({"access_token": PLACEHOLDER_TOKEN, "refresh_token": "placeholder-refresh-token"}),
            encoding="utf-8",
        )
    return token_path


def _make_isolated_target_root(test_case: unittest.TestCase) -> Path:
    tmpdir = tempfile.TemporaryDirectory()
    test_case.addCleanup(tmpdir.cleanup)
    target_root = Path(tmpdir.name) / "target" / "ntb_marimo_console"
    (target_root / "src" / "ntb_marimo_console").mkdir(parents=True)
    return target_root


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class RehearsalCliBlockingTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_operator_live_runtime_registration()
        self.addCleanup(clear_operator_live_runtime_registration)
        self.target_root = _make_isolated_target_root(self)

    def test_import_does_not_perform_network_credential_or_token_work(self) -> None:
        self.assertTrue(hasattr(rehearsal, "run"))
        self.assertTrue(hasattr(rehearsal, "build_parser"))
        self.assertTrue(hasattr(rehearsal, "RehearsalReport"))
        self.assertTrue(hasattr(rehearsal, "run_with_dependencies"))
        self.assertTrue(hasattr(rehearsal, "default_front_month_symbols"))
        for key in os.environ:
            self.assertFalse(
                key.startswith("SCHWAB_") and "SCHWAB_LIVE_REHEARSAL_FORCE" not in key,
                msg="default test run must not require SCHWAB_* env vars",
            )

    def test_no_live_flag_blocks_before_env_or_token_access(self) -> None:
        sentinel_open = unittest.mock.MagicMock(side_effect=AssertionError("open_must_not_be_called"))
        with patch("builtins.open", new=sentinel_open):
            report = rehearsal.run_with_dependencies(
                args=_make_args(live=False),
                env={},
                target_root=self.target_root,
            )
        self.assertEqual(report.mode, "blocked")
        self.assertEqual(report.status, "blocked")
        self.assertFalse(report.live_flag)
        self.assertFalse(report.runtime_start_attempted)
        self.assertEqual(report.blocking_reason, "live_flag_required")

    def test_missing_operator_live_runtime_env_blocks_before_token_access(self) -> None:
        report = rehearsal.run_with_dependencies(
            args=_make_args(live=True),
            env={
                "SCHWAB_APP_KEY": "x",
                "SCHWAB_APP_SECRET": "y",
                "SCHWAB_TOKEN_PATH": str(self.target_root / ".state" / "schwab" / "token.json"),
            },
            target_root=self.target_root,
        )
        self.assertEqual(report.mode, "blocked")
        self.assertFalse(report.operator_live_runtime_env)
        self.assertFalse(report.runtime_start_attempted)
        self.assertEqual(report.blocking_reason, "operator_live_runtime_opt_in_required")

    def test_canonical_operator_live_runtime_opt_in_is_honored_without_aliases(self) -> None:
        _ensure_token_file(self.target_root)
        report = rehearsal.run_with_dependencies(
            args=_make_args(live=True),
            env=_full_env(self.target_root),
            target_root=self.target_root,
            deps=rehearsal.RehearsalDependencies(
                token_provider=FakeTokenProvider(),
                credentials_provider=FakeCredentialsProvider(exception=RuntimeError("stop before runtime start")),
                websocket_factory=FakeWebsocketFactory(),
            ),
        )

        self.assertTrue(report.operator_live_runtime_env)
        self.assertEqual(report.blocking_reason, "streamer_credentials_unavailable")
        self.assertFalse(report.runtime_start_attempted)

    def test_unsupported_or_misspelled_rehearsal_opt_in_does_not_pass(self) -> None:
        _ensure_token_file(self.target_root)
        for value in ("OPERATOR_LIVE_RUNTME", "true", "1", "LIVE_RUNTIME_ENABLED"):
            with self.subTest(value=value):
                report = rehearsal.run_with_dependencies(
                    args=_make_args(live=True),
                    env=_full_env(self.target_root, override={"NTB_OPERATOR_RUNTIME_MODE": value}),
                    target_root=self.target_root,
                )
                self.assertFalse(report.operator_live_runtime_env)
                self.assertEqual(report.blocking_reason, "operator_live_runtime_opt_in_required")
                self.assertFalse(report.runtime_start_attempted)

    def test_lower_level_runtime_compatibility_opt_ins_are_not_rehearsal_command_contract(self) -> None:
        self.assertEqual(
            operator_runtime_mode_from_env({"NTB_OPERATOR_RUNTIME_MODE": "OPERATOR_LIVE_RUNTIME"}),
            OPERATOR_LIVE_RUNTIME,
        )
        self.assertEqual(
            operator_runtime_mode_from_env({"NTB_OPERATOR_RUNTIME_MODE": "LIVE_RUNTIME"}),
            OPERATOR_LIVE_RUNTIME,
        )
        self.assertEqual(
            operator_runtime_mode_from_env({"NTB_OPERATOR_RUNTIME_MODE": "LIVE"}),
            OPERATOR_LIVE_RUNTIME,
        )
        self.assertEqual(
            operator_runtime_mode_from_env({"NTB_OPERATOR_LIVE_RUNTIME": "1"}),
            OPERATOR_LIVE_RUNTIME,
        )
        self.assertEqual(
            operator_runtime_mode_from_env({"OPERATOR_LIVE_RUNTIME": "true"}),
            "SAFE_NON_LIVE",
        )

        _ensure_token_file(self.target_root)
        for env in (
            _full_env(self.target_root, override={"NTB_OPERATOR_RUNTIME_MODE": "LIVE_RUNTIME"}),
            _full_env(self.target_root, override={"NTB_OPERATOR_RUNTIME_MODE": "LIVE"}),
            _full_env_without_runtime_mode(self.target_root, override={"NTB_OPERATOR_LIVE_RUNTIME": "1"}),
            _full_env_without_runtime_mode(self.target_root, override={"OPERATOR_LIVE_RUNTIME": "true"}),
        ):
            with self.subTest(env=env):
                report = rehearsal.run_with_dependencies(
                    args=_make_args(live=True),
                    env=env,
                    target_root=self.target_root,
                )
                self.assertFalse(report.operator_live_runtime_env)
                self.assertEqual(report.blocking_reason, "operator_live_runtime_opt_in_required")
                self.assertFalse(report.runtime_start_attempted)

    def test_missing_required_env_keys_blocks_before_token_access(self) -> None:
        env = {"NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME}
        report = rehearsal.run_with_dependencies(
            args=_make_args(live=True),
            env=env,
            target_root=self.target_root,
        )
        self.assertEqual(report.mode, "blocked")
        self.assertFalse(report.env_keys_present)
        self.assertEqual(report.blocking_reason, "required_env_keys_missing")
        self.assertFalse(report.runtime_start_attempted)

    def test_token_path_outside_target_state_blocks(self) -> None:
        env = {
            "NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME,
            "SCHWAB_APP_KEY": "x",
            "SCHWAB_APP_SECRET": "y",
            "SCHWAB_TOKEN_PATH": "/tmp/not-under-state/token.json",
        }
        report = rehearsal.run_with_dependencies(
            args=_make_args(live=True),
            env=env,
            target_root=self.target_root,
        )
        self.assertEqual(report.mode, "blocked")
        self.assertFalse(report.token_path_under_target_state)
        self.assertEqual(report.blocking_reason, "token_path_outside_target_state")
        self.assertFalse(report.runtime_start_attempted)

    def test_target_relative_token_path_resolves_under_target_state_without_reading_contents(self) -> None:
        ok, token_path = rehearsal._validate_token_path_under_target_state(
            {"SCHWAB_TOKEN_PATH": ".state/schwab/token.json"},
            self.target_root,
        )

        self.assertTrue(ok)
        self.assertEqual(token_path, (self.target_root / ".state" / "schwab" / "token.json").resolve())

    def test_double_nested_relative_token_path_is_rejected_without_reading_contents(self) -> None:
        ok, token_path = rehearsal._validate_token_path_under_target_state(
            {"SCHWAB_TOKEN_PATH": "target/ntb_marimo_console/.state/schwab/token.json"},
            self.target_root,
        )

        self.assertFalse(ok)
        self.assertEqual(
            token_path,
            (self.target_root / "target" / "ntb_marimo_console" / ".state" / "schwab" / "token.json").resolve(),
        )

    def test_absolute_token_path_outside_target_state_is_rejected_without_reading_contents(self) -> None:
        sentinel_open = unittest.mock.MagicMock(side_effect=AssertionError("token_contents_must_not_be_read"))
        with patch("builtins.open", new=sentinel_open):
            ok, token_path = rehearsal._validate_token_path_under_target_state(
                {"SCHWAB_TOKEN_PATH": "/tmp/not-under-target-state/token.json"},
                self.target_root,
            )

        self.assertFalse(ok)
        self.assertEqual(token_path, Path("/tmp/not-under-target-state/token.json").resolve())
        sentinel_open.assert_not_called()

    def test_does_not_open_secrets_env_file(self) -> None:
        _ensure_token_file(self.target_root)
        deps = rehearsal.RehearsalDependencies(
            token_provider=FakeTokenProvider(),
            credentials_provider=FakeCredentialsProvider(),
            websocket_factory=FakeWebsocketFactory(),
            manager_builder=lambda cfg, c: FakeStartingManager(cfg, c),
            clock=_make_clock(),
        )
        # Wrap builtins.open and assert no path matches schwab_live.env.
        opened_paths: list[str] = []
        original_open = open

        def tracking_open(file, *args, **kwargs):
            opened_paths.append(str(file))
            return original_open(file, *args, **kwargs)

        with patch("builtins.open", new=tracking_open):
            rehearsal.run_with_dependencies(
                args=_make_args(live=True, duration=1),
                env=_full_env(self.target_root),
                target_root=self.target_root,
                deps=deps,
            )
        for path in opened_paths:
            self.assertNotIn("schwab_live.env", path)
            self.assertNotIn(".state/secrets", path)


class RehearsalDependencyWiringTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_operator_live_runtime_registration()
        self.addCleanup(clear_operator_live_runtime_registration)
        self.target_root = _make_isolated_target_root(self)
        _ensure_token_file(self.target_root)

    def test_full_path_invokes_factory_login_subscribe_dispatch_close_each_once_with_one_session(self) -> None:
        token_provider = FakeTokenProvider()
        credentials_provider = FakeCredentialsProvider()
        websocket_factory = FakeWebsocketFactory()
        websocket_factory.connection.recv_queue.append(_admin_login_ack(code=0))
        websocket_factory.connection.recv_queue.append(_subs_ack(code=0))
        managers: list[FakeStartingManager] = []

        def manager_builder(cfg, c):
            mgr = FakeStartingManager(cfg, c)
            managers.append(mgr)
            return mgr

        deps = rehearsal.RehearsalDependencies(
            token_provider=token_provider,
            credentials_provider=credentials_provider,
            websocket_factory=websocket_factory,
            manager_builder=manager_builder,
            clock=_make_clock(),
        )
        report = rehearsal.run_with_dependencies(
            args=_make_args(live=True, duration=1),
            env=_full_env(self.target_root),
            target_root=self.target_root,
            deps=deps,
        )

        self.assertEqual(report.mode, "live")
        self.assertEqual(report.status, "ok")
        self.assertTrue(report.runtime_start_attempted)
        self.assertTrue(report.live_login_succeeded)
        self.assertTrue(report.live_subscribe_succeeded)
        self.assertEqual(report.subscribed_contracts_count, 5)
        self.assertEqual(credentials_provider.call_count, 1)
        self.assertEqual(websocket_factory.call_count, 1)
        self.assertEqual(len(managers), 1)
        self.assertEqual(managers[0].start_count, 1)
        self.assertEqual(managers[0].shutdown_count, 1)
        self.assertEqual(report.cleanup_status, "ok")

    def test_dispatch_records_market_data_received_without_printing_values(self) -> None:
        token_provider = FakeTokenProvider()
        credentials_provider = FakeCredentialsProvider()
        websocket_factory = FakeWebsocketFactory()
        websocket_factory.connection.recv_queue.append(_admin_login_ack(code=0))
        websocket_factory.connection.recv_queue.append(_subs_ack(code=0))
        websocket_factory.connection.recv_queue.append(_data_frame("/ESM26", 4321.5))
        websocket_factory.connection.recv_queue.append(_data_frame("/NQM26", 17890.25))
        websocket_factory.connection.recv_queue.append(_data_frame("/MGCM26", 2110.0))

        deps = rehearsal.RehearsalDependencies(
            token_provider=token_provider,
            credentials_provider=credentials_provider,
            websocket_factory=websocket_factory,
            manager_builder=lambda cfg, c: FakeStartingManager(cfg, c),
            clock=_make_clock(),
        )
        report = rehearsal.run_with_dependencies(
            args=_make_args(live=True, duration=2),
            env=_full_env(self.target_root),
            target_root=self.target_root,
            deps=deps,
        )

        self.assertEqual(report.mode, "live")
        self.assertTrue(report.market_data_received)
        self.assertGreaterEqual(report.received_contracts_count, 3)

        text_output = rehearsal.render_text(report)
        json_output = rehearsal.render_json(report)
        forbidden_substrings = (
            PLACEHOLDER_SOCKET_URL,
            PLACEHOLDER_SOCKET_HOST,
            PLACEHOLDER_CUSTOMER_ID,
            PLACEHOLDER_CORREL_ID,
            PLACEHOLDER_TOKEN,
            "schwab_live.env",
            ".state/secrets",
            "streamer-api",
            "wss://",
            "https://",
        )
        for substring in forbidden_substrings:
            self.assertNotIn(substring, text_output)
            self.assertNotIn(substring, json_output)
        # Sanity: prices not present in output (we never emit field values).
        self.assertNotIn("4321.5", text_output)
        self.assertNotIn("4321.5", json_output)

    def test_repeated_dispatch_does_not_repeat_login_subscribe_or_start(self) -> None:
        token_provider = FakeTokenProvider()
        credentials_provider = FakeCredentialsProvider()
        websocket_factory = FakeWebsocketFactory()
        ws_conn = websocket_factory.connection
        ws_conn.recv_queue.append(_admin_login_ack(code=0))
        ws_conn.recv_queue.append(_subs_ack(code=0))
        for idx in range(8):
            ws_conn.recv_queue.append(_data_frame("/ESM26", 4321.5 + idx))

        managers: list[FakeStartingManager] = []

        def manager_builder(cfg, c):
            mgr = FakeStartingManager(cfg, c)
            managers.append(mgr)
            return mgr

        deps = rehearsal.RehearsalDependencies(
            token_provider=token_provider,
            credentials_provider=credentials_provider,
            websocket_factory=websocket_factory,
            manager_builder=manager_builder,
            clock=_make_clock(),
        )
        report = rehearsal.run_with_dependencies(
            args=_make_args(live=True, duration=2),
            env=_full_env(self.target_root),
            target_root=self.target_root,
            deps=deps,
        )

        manager = managers[-1]
        self.assertEqual(manager.start_count, 1)
        self.assertEqual(websocket_factory.call_count, 1)
        # Login frame sent once, subscribe frame sent once, then logout on shutdown
        # is sent in the close path (the FakeStartingManager.shutdown returns its
        # own snapshot but the OperatorSchwabStreamerSession.close still fires
        # LOGOUT on the underlying websocket). So sent = login + subscribe + logout.
        self.assertEqual(ws_conn.sent[0].count("\"command\":\"LOGIN\""), 1)
        self.assertEqual(ws_conn.sent[1].count("\"command\":\"SUBS\""), 1)
        # The dispatch loop must NOT have sent additional LOGIN or SUBS frames.
        for payload in ws_conn.sent[2:]:
            self.assertNotIn("\"command\":\"LOGIN\"", payload)
            self.assertNotIn("\"command\":\"SUBS\"", payload)
        # Final report pin
        self.assertEqual(report.repeated_login_on_refresh, False)
        text = rehearsal.render_text(report)
        self.assertIn("repeated_login_on_refresh=no", text)

    def test_cleanup_runs_on_exit_path(self) -> None:
        token_provider = FakeTokenProvider()
        credentials_provider = FakeCredentialsProvider()
        websocket_factory = FakeWebsocketFactory()
        websocket_factory.connection.recv_queue.append(_admin_login_ack(code=0))
        websocket_factory.connection.recv_queue.append(_subs_ack(code=0))
        websocket_factory.connection.recv_queue.append(_data_frame("/ESM26", 4321.5))

        managers: list[FakeStartingManager] = []
        original_ingest = FakeStartingManager.ingest_message

        def raising_ingest(self, message):
            raise RuntimeError("simulated_ingest_error")

        def manager_builder(cfg, c):
            mgr = FakeStartingManager(cfg, c)
            mgr.ingest_message = raising_ingest.__get__(mgr, FakeStartingManager)  # type: ignore[method-assign]
            managers.append(mgr)
            return mgr

        deps = rehearsal.RehearsalDependencies(
            token_provider=token_provider,
            credentials_provider=credentials_provider,
            websocket_factory=websocket_factory,
            manager_builder=manager_builder,
            clock=_make_clock(),
        )
        report = rehearsal.run_with_dependencies(
            args=_make_args(live=True, duration=1),
            env=_full_env(self.target_root),
            target_root=self.target_root,
            deps=deps,
        )

        manager = managers[-1]
        self.assertEqual(manager.shutdown_count, 1)
        self.assertEqual(report.cleanup_status, "ok")
        # Restore original (defensive, though FakeStartingManager is per-test).
        del original_ingest


class RehearsalFailureTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_operator_live_runtime_registration()
        self.addCleanup(clear_operator_live_runtime_registration)
        self.target_root = _make_isolated_target_root(self)
        _ensure_token_file(self.target_root)

    def test_login_failure_yields_blocked_report_without_fixture_fallback(self) -> None:
        websocket_factory = FakeWebsocketFactory()
        websocket_factory.connection.recv_queue.append(_admin_login_ack(code=7))

        deps = rehearsal.RehearsalDependencies(
            token_provider=FakeTokenProvider(),
            credentials_provider=FakeCredentialsProvider(),
            websocket_factory=websocket_factory,
            manager_builder=lambda cfg, c: FakeStartingManager(cfg, c),
            clock=_make_clock(),
        )
        report = rehearsal.run_with_dependencies(
            args=_make_args(live=True, duration=1),
            env=_full_env(self.target_root),
            target_root=self.target_root,
            deps=deps,
        )
        self.assertEqual(report.mode, "blocked")
        self.assertFalse(report.live_login_succeeded)
        self.assertEqual(report.blocking_reason, "live_login_or_subscribe_failed")
        # No producer registered
        self.assertIsNone(get_registered_operator_live_runtime_producer())
        # No fixture fallback
        follow_up_producer = build_operator_runtime_snapshot_producer_from_env(
            {"NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME},
        )
        follow_up = resolve_operator_runtime_snapshot(
            mode=OPERATOR_LIVE_RUNTIME,
            producer=follow_up_producer,
        )
        self.assertEqual(follow_up.status, LIVE_RUNTIME_UNAVAILABLE)
        # No sensitive value leakage
        text = rehearsal.render_text(report)
        self.assertNotIn(SECRET_MARKER, text)

    def test_subscribe_failure_yields_blocked_report_without_fixture_fallback(self) -> None:
        websocket_factory = FakeWebsocketFactory()
        websocket_factory.connection.recv_queue.append(_admin_login_ack(code=0))
        websocket_factory.connection.recv_queue.append(_subs_ack(code=5))

        deps = rehearsal.RehearsalDependencies(
            token_provider=FakeTokenProvider(),
            credentials_provider=FakeCredentialsProvider(),
            websocket_factory=websocket_factory,
            manager_builder=lambda cfg, c: FakeStartingManager(cfg, c),
            clock=_make_clock(),
        )
        report = rehearsal.run_with_dependencies(
            args=_make_args(live=True, duration=1),
            env=_full_env(self.target_root),
            target_root=self.target_root,
            deps=deps,
        )
        self.assertEqual(report.mode, "blocked")
        self.assertTrue(report.live_login_succeeded or not report.live_login_succeeded)
        self.assertFalse(report.live_subscribe_succeeded)
        self.assertEqual(report.blocking_reason, "live_login_or_subscribe_failed")

    def test_user_preference_fetch_failure_yields_blocked_report(self) -> None:
        creds_provider = FakeCredentialsProvider(
            exception=RuntimeError(f"user_preference_failure token={SECRET_MARKER}"),
        )
        deps = rehearsal.RehearsalDependencies(
            token_provider=FakeTokenProvider(),
            credentials_provider=creds_provider,
            websocket_factory=FakeWebsocketFactory(),
            manager_builder=lambda cfg, c: FakeStartingManager(cfg, c),
            clock=_make_clock(),
        )
        report = rehearsal.run_with_dependencies(
            args=_make_args(live=True, duration=1),
            env=_full_env(self.target_root),
            target_root=self.target_root,
            deps=deps,
        )
        self.assertEqual(report.mode, "blocked")
        self.assertFalse(report.streamer_credentials_obtained)
        self.assertEqual(report.blocking_reason, "streamer_credentials_unavailable")
        self.assertFalse(report.runtime_start_attempted)
        text = rehearsal.render_text(report)
        self.assertNotIn(SECRET_MARKER, text)

    def test_token_freshness_unknown_when_token_payload_lacks_expiry(self) -> None:
        token_path = self.target_root / ".state" / "schwab" / "token.json"
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(
            json.dumps({"access_token": PLACEHOLDER_TOKEN, "refresh_token": "placeholder-refresh-token"}),
            encoding="utf-8",
        )

        websocket_factory = FakeWebsocketFactory()
        websocket_factory.connection.recv_queue.append(_admin_login_ack(code=0))
        websocket_factory.connection.recv_queue.append(_subs_ack(code=0))

        deps = rehearsal.RehearsalDependencies(
            token_provider=FakeTokenProvider(),
            credentials_provider=FakeCredentialsProvider(),
            websocket_factory=websocket_factory,
            manager_builder=lambda cfg, c: FakeStartingManager(cfg, c),
            clock=_make_clock(),
        )
        report = rehearsal.run_with_dependencies(
            args=_make_args(live=True, duration=1),
            env=_full_env(self.target_root),
            target_root=self.target_root,
            deps=deps,
        )
        self.assertEqual(report.token_fresh, "unknown")
        self.assertTrue(report.token_contract_valid)
        self.assertTrue(report.refresh_token_present)

    def test_missing_refresh_token_blocks_before_streamer_credentials(self) -> None:
        token_path = self.target_root / ".state" / "schwab" / "token.json"
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(json.dumps({"access_token": PLACEHOLDER_TOKEN}), encoding="utf-8")
        credentials_provider = FakeCredentialsProvider()
        deps = rehearsal.RehearsalDependencies(
            token_provider=FakeTokenProvider(),
            credentials_provider=credentials_provider,
            websocket_factory=FakeWebsocketFactory(),
            manager_builder=lambda cfg, c: FakeStartingManager(cfg, c),
            clock=_make_clock(),
        )

        report = rehearsal.run_with_dependencies(
            args=_make_args(live=True, duration=1),
            env=_full_env(self.target_root),
            target_root=self.target_root,
            deps=deps,
        )

        self.assertEqual(report.mode, "blocked")
        self.assertFalse(report.token_contract_valid)
        self.assertTrue(report.access_token_present)
        self.assertFalse(report.refresh_token_present)
        self.assertEqual(report.token_fresh, "unknown")
        self.assertEqual(report.blocking_reason, "refresh_token_missing")
        self.assertFalse(report.streamer_credentials_obtained)
        self.assertFalse(report.runtime_start_attempted)
        self.assertEqual(credentials_provider.call_count, 0)

    def test_websocket_connect_failure_yields_blocked_report(self) -> None:
        websocket_factory = FakeWebsocketFactory(
            connect_exception=RuntimeError("network_unreachable"),
        )
        deps = rehearsal.RehearsalDependencies(
            token_provider=FakeTokenProvider(),
            credentials_provider=FakeCredentialsProvider(),
            websocket_factory=websocket_factory,
            manager_builder=lambda cfg, c: FakeStartingManager(cfg, c),
            clock=_make_clock(),
        )
        report = rehearsal.run_with_dependencies(
            args=_make_args(live=True, duration=1),
            env=_full_env(self.target_root),
            target_root=self.target_root,
            deps=deps,
        )
        self.assertEqual(report.mode, "blocked")
        self.assertFalse(report.live_login_succeeded)


class RehearsalUniverseTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_operator_live_runtime_registration()
        self.addCleanup(clear_operator_live_runtime_registration)
        self.target_root = _make_isolated_target_root(self)
        _ensure_token_file(self.target_root)

    def test_zn_or_gc_in_overrides_is_rejected_at_argparse(self) -> None:
        parser = rehearsal.build_parser()
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(["--live", "--symbol", "ZN=/ZNM26"])
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                parser.parse_args(["--live", "--symbol", "GC=/GCM26"])

    def test_es_nq_cl_6e_mgc_only_subscribed_payload_excludes_zn_and_gc(self) -> None:
        token_provider = FakeTokenProvider()
        credentials_provider = FakeCredentialsProvider()
        websocket_factory = FakeWebsocketFactory()
        ws = websocket_factory.connection
        ws.recv_queue.append(_admin_login_ack(code=0))
        ws.recv_queue.append(_subs_ack(code=0))

        deps = rehearsal.RehearsalDependencies(
            token_provider=token_provider,
            credentials_provider=credentials_provider,
            websocket_factory=websocket_factory,
            manager_builder=lambda cfg, c: FakeStartingManager(cfg, c),
            clock=_make_clock(),
        )
        report = rehearsal.run_with_dependencies(
            args=_make_args(live=True, duration=1),
            env=_full_env(self.target_root),
            target_root=self.target_root,
            deps=deps,
        )
        self.assertEqual(report.subscribed_contracts_count, 5)
        # subscribe payload is the second send
        self.assertGreaterEqual(len(ws.sent), 2)
        sub_payload = json.loads(ws.sent[1])
        keys = sub_payload["requests"][0]["parameters"]["keys"]
        self.assertIn("/MGCM26", keys)
        self.assertNotIn("/ZNM26", keys)
        self.assertNotIn("/GCM26", keys)
        self.assertEqual(keys, "/ESM26,/NQM26,/CLM26,/6EM26,/MGCM26")

    def test_mgc_remains_mgc_and_is_not_mapped_to_gc(self) -> None:
        defaults = rehearsal.default_front_month_symbols()
        self.assertIn("MGC", defaults)
        self.assertNotIn("GC", defaults)
        self.assertNotIn("ZN", defaults)
        # MGC's value must reference MGC, not GC
        self.assertIn("MGC", defaults["MGC"])
        self.assertNotEqual(defaults.get("MGC"), defaults.get("GC"))

    def test_help_text_warns_explicit_live_only_and_prints_no_secrets(self) -> None:
        parser = rehearsal.build_parser()
        help_text = parser.format_help()
        self.assertIn("Explicit live only", help_text)
        forbidden = (
            PLACEHOLDER_SOCKET_URL,
            PLACEHOLDER_SOCKET_HOST,
            PLACEHOLDER_CUSTOMER_ID,
            "streamer-api",
            "wss://",
            "https://",
            "schwab_live.env",
            ".state/secrets",
        )
        for substring in forbidden:
            self.assertNotIn(substring, help_text)

    def test_no_fixture_fallback_when_runtime_fails_and_query_gate_remains_blocked(self) -> None:
        # Subscribe failure → blocked report; follow-up resolver returns UNAVAILABLE.
        websocket_factory = FakeWebsocketFactory()
        websocket_factory.connection.recv_queue.append(_admin_login_ack(code=0))
        websocket_factory.connection.recv_queue.append(_subs_ack(code=5))
        deps = rehearsal.RehearsalDependencies(
            token_provider=FakeTokenProvider(),
            credentials_provider=FakeCredentialsProvider(),
            websocket_factory=websocket_factory,
            manager_builder=lambda cfg, c: FakeStartingManager(cfg, c),
            clock=_make_clock(),
        )
        report = rehearsal.run_with_dependencies(
            args=_make_args(live=True, duration=1),
            env=_full_env(self.target_root),
            target_root=self.target_root,
            deps=deps,
        )
        self.assertEqual(report.mode, "blocked")
        self.assertIsNone(get_registered_operator_live_runtime_producer())
        producer = build_operator_runtime_snapshot_producer_from_env(
            {"NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME},
        )
        snapshot_result = resolve_operator_runtime_snapshot(
            mode=OPERATOR_LIVE_RUNTIME,
            producer=producer,
        )
        self.assertEqual(snapshot_result.status, LIVE_RUNTIME_UNAVAILABLE)


class RehearsalCliExitCodeTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_operator_live_runtime_registration()
        self.addCleanup(clear_operator_live_runtime_registration)
        self.target_root = _make_isolated_target_root(self)
        _ensure_token_file(self.target_root)

    def test_cli_run_without_live_returns_2(self) -> None:
        argv = []
        with redirect_stdout(io.StringIO()) as buf, patch.dict(os.environ, {}, clear=True):
            code = rehearsal.run(argv=argv)
        self.assertEqual(code, 2)
        out = buf.getvalue()
        self.assertIn("mode=blocked", out)
        self.assertIn("live_flag=no", out)
        self.assertIn("values_printed=no", out)


if __name__ == "__main__":
    unittest.main()
