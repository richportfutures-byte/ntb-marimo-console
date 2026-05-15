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
from datetime import datetime, timezone
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
    SchwabStreamManager,
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
NOW_EPOCH_MILLIS = 1_778_335_200_000


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
    connection_lost_reasons: list[str] = field(default_factory=list)

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

    def mark_connection_lost(self, reason: object = "connection_lost") -> StreamManagerSnapshot:
        text = str(reason)
        self.connection_lost_reasons.append(text)
        self._snapshot = self._blocked(text)
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


def _subs_ack(code: int = 0, *, service: str = "LEVELONE_FUTURES") -> str:
    return json.dumps(
        {
            "response": [
                {
                    "service": service,
                    "command": "SUBS",
                    "content": {"code": code, "msg": "ok"},
                }
            ]
        }
    )


def _chart_frame(symbol: str = "/ESM26", *, minute: int = 0, completed: bool = True) -> str:
    start = f"2026-05-09T14:{minute:02d}:00+00:00"
    return json.dumps(
        {
            "data": [
                {
                    "service": "CHART_FUTURES",
                    "command": "SUBS",
                    "timestamp": start,
                    "content": [
                        {
                            "key": symbol,
                            "start_time": start,
                            "open": 100.0 + minute,
                            "high": 100.75 + minute,
                            "low": 99.75 + minute,
                            "close": 100.5 + minute,
                            "volume": 100 + minute,
                            "completed": completed,
                        }
                    ],
                }
            ]
        }
    )


def _chart_numeric_frame(symbol: str = "/ESM26", *, minute: int = 0) -> str:
    start_epoch_millis = NOW_EPOCH_MILLIS + (minute * 60_000)
    observed_epoch_millis = start_epoch_millis + 60_000
    return json.dumps(
        {
            "data": [
                {
                    "service": "CHART_FUTURES",
                    "command": "SUBS",
                    "timestamp": observed_epoch_millis,
                    "content": [
                        {
                            "key": symbol,
                            "0": symbol,
                            "1": start_epoch_millis,
                            "2": 100.0 + minute,
                            "3": 100.75 + minute,
                            "4": 99.75 + minute,
                            "5": 100.5 + minute,
                            "6": 100 + minute,
                        }
                    ],
                }
            ]
        }
    )


def _data_frame(symbol: str = "/ESM26", bid: float = 1.0, *, timestamp: object = NOW) -> str:
    content = {
        "key": symbol,
        "0": symbol,
        "1": bid,
        "2": bid + 0.25,
        "3": bid + 0.125,
        "4": 10,
        "5": 12,
        "8": 25_000,
        "10": timestamp,
        "11": timestamp,
        "12": bid + 1.0,
        "13": bid - 1.0,
        "14": bid - 0.5,
        "18": bid - 0.25,
        "22": "Normal",
        "30": "true",
        "32": 1,
    }
    return json.dumps(
        {
            "data": [
                {
                    "service": "LEVELONE_FUTURES",
                    "command": "SUBS",
                    "timestamp": timestamp,
                    "content": [content],
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


def _make_stepping_clock(step: float) -> Any:
    """Monotonic clock advancing by ``step`` seconds per call.

    Large steps let tests exercise long bounded receive windows without
    incurring real wall-clock sleeps inside the dispatch loop.
    """
    state = {"now": 0.0}

    def _clock() -> float:
        current = state["now"]
        state["now"] += step
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

    def test_dry_run_is_fixture_safe_and_does_not_require_env_or_credentials(self) -> None:
        stdout = io.StringIO()

        with patch.dict(os.environ, {"SCHWAB_APP_KEY": SECRET_MARKER}, clear=True):
            with redirect_stdout(stdout):
                exit_code = rehearsal.run(["--dry-run", "--json"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["mode"], "dry_run")
        self.assertEqual(payload["status"], "review_only_non_live")
        self.assertEqual(payload["readiness_gate"], "READY_TO_RUN_WITH_INTENTIONAL_LIVE_OPT_IN")
        self.assertEqual(payload["rehearsal_ready_to_run"], "yes")
        self.assertEqual(payload["live_behavior_attempted"], "no")
        self.assertEqual(payload["runtime_start_attempted"], "no")
        self.assertEqual(payload["login_attempted"], "no")
        self.assertEqual(payload["subscribe_attempted"], "no")
        self.assertEqual(payload["provider_connection_attempted"], "no")
        self.assertEqual(payload["credentials_required_for_dry_run"], "no")
        self.assertEqual(payload["secrets_or_token_files_read"], "no")
        self.assertIn("--readiness-gate", payload["credential_free_gate_command"])
        self.assertIn("NTB_OPERATOR_RUNTIME_MODE=OPERATOR_LIVE_RUNTIME", payload["intentional_live_command"])
        self.assertIn("--live --duration 10", payload["intentional_live_command"])
        self.assertNotIn(SECRET_MARKER, stdout.getvalue())

    def test_dry_run_final_plan_is_exact_five_contract_services_only(self) -> None:
        report = rehearsal.build_dry_run_report()
        payload = report.to_dict()
        rows = payload["contract_plan"]

        self.assertEqual([row["contract"] for row in rows], ["ES", "NQ", "CL", "6E", "MGC"])
        self.assertEqual(payload["services"], ["LEVELONE_FUTURES", "CHART_FUTURES"])
        for row in rows:
            self.assertEqual(row["services"], ["LEVELONE_FUTURES", "CHART_FUTURES"])
            self.assertEqual(row["final_target_supported"], "yes")
        self.assertNotIn("ZN", [row["contract"] for row in rows])
        self.assertNotIn("GC", [row["contract"] for row in rows])

    def test_live_runtime_stream_config_requests_levelone_and_chart(self) -> None:
        config = rehearsal._build_stream_config(symbol_overrides={})

        self.assertEqual(config.services_requested, ("LEVELONE_FUTURES", "CHART_FUTURES"))
        self.assertEqual(config.contracts_requested, ("ES", "NQ", "CL", "6E", "MGC"))

    def test_dry_run_rejects_excluded_and_unsupported_candidates_without_promoting_them(self) -> None:
        report = rehearsal.build_dry_run_report(candidate_contracts=("ZN", "GC", "YM", "MGC"))
        payload = report.to_dict()

        self.assertEqual(payload["contract_plan"][-1]["contract"], "MGC")
        self.assertEqual(
            payload["rejected_contracts"],
            [
                {"contract": "ZN", "policy": "excluded", "included_in_final_plan": "no"},
                {"contract": "GC", "policy": "never_supported_excluded", "included_in_final_plan": "no"},
                {"contract": "YM", "policy": "unsupported", "included_in_final_plan": "no"},
            ],
        )

    def test_dry_run_labels_mgc_as_micro_gold_and_never_uses_gc_as_substitute(self) -> None:
        report = rehearsal.build_dry_run_report()
        rows = {row["contract"]: row for row in report.to_dict()["contract_plan"]}
        rendered_mgc = json.dumps(rows["MGC"], sort_keys=True)

        self.assertEqual(rows["MGC"]["display_name"], "Micro Gold")
        self.assertEqual(rows["MGC"]["symbol"], "/MGCM26")
        self.assertNotIn("/GCM26", rendered_mgc)
        self.assertNotIn('"GC"', rendered_mgc)

    def test_dry_run_redacts_provider_diagnostics_and_states_live_readiness_unproven(self) -> None:
        report = rehearsal.build_dry_run_report(
            provider_diagnostics=(
                "Authorization: Bearer BEARER_VALUE_PRIVATE_12345678901234567890 "
                "access_token=ACCESS_VALUE_PRIVATE refresh_token=REFRESH_VALUE_PRIVATE "
                "customerId=CUSTOMER_VALUE_PRIVATE correlId=CORREL_VALUE_PRIVATE "
                "accountNumber=ACCOUNT_VALUE_PRIVATE wss://stream-redaction.invalid/ws token.json",
            ),
        )
        rendered = rehearsal.render_dry_run_json(report)

        for fragment in (
            "BEARER_VALUE_PRIVATE",
            "ACCESS_VALUE_PRIVATE",
            "REFRESH_VALUE_PRIVATE",
            "CUSTOMER_VALUE_PRIVATE",
            "CORREL_VALUE_PRIVATE",
            "ACCOUNT_VALUE_PRIVATE",
            "stream-redaction",
            "wss://",
            "token.json",
        ):
            self.assertNotIn(fragment, rendered)
        self.assertIn("[REDACTED]", rendered)
        self.assertIn("schwab_live_readiness_unproven_until_authorized_manual_rehearsal", rendered)
        self.assertIn("symbol_entitlement_and_rollover_proof_beyond_exact_run_not_recorded", rendered)

    def test_dry_run_output_is_text_deterministic_and_review_only(self) -> None:
        first = rehearsal.render_dry_run_text(
            rehearsal.build_dry_run_report(candidate_contracts=("GC", "ZN"))
        )
        second = rehearsal.render_dry_run_text(
            rehearsal.build_dry_run_report(candidate_contracts=("GC", "ZN"))
        )

        self.assertEqual(first, second)
        self.assertIn("plan_contract=MGC|Micro Gold|/MGCM26|LEVELONE_FUTURES,CHART_FUTURES", first)
        self.assertIn("rejected_contract=GC|never_supported_excluded|included=no", first)
        self.assertIn("readiness_gate=READY_TO_RUN_WITH_INTENTIONAL_LIVE_OPT_IN", first)
        self.assertIn(
            "intentional_live_command=NTB_OPERATOR_RUNTIME_MODE=OPERATOR_LIVE_RUNTIME "
            "PYTHONPATH=src:../../source/ntb_engine/src:. "
            "uv run python scripts/run_operator_live_runtime_rehearsal.py --live --duration 10",
            first,
        )
        self.assertIn(
            "production_readiness_blocker="
            "production_release_remains_premature_until_live_session_usability_and_hardening_predicates_are_satisfied",
            first,
        )
        self.assertIn("review_preflight_only_not_subscription_or_login", first)

    def test_dry_run_path_does_not_call_live_dependency_seam(self) -> None:
        with patch.object(rehearsal, "run_with_dependencies", side_effect=AssertionError("live seam called")):
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = rehearsal.run(["--dry-run"])

        self.assertEqual(exit_code, 0)
        self.assertIn("mode=dry_run", stdout.getvalue())

    def test_readiness_gate_alias_is_fixture_safe_and_does_not_call_live_dependency_seam(self) -> None:
        with patch.object(rehearsal, "run_with_dependencies", side_effect=AssertionError("live seam called")):
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                exit_code = rehearsal.run(["--readiness-gate", "--json"])

        payload = json.loads(stdout.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["mode"], "dry_run")
        self.assertEqual(payload["readiness_gate"], "READY_TO_RUN_WITH_INTENTIONAL_LIVE_OPT_IN")
        self.assertEqual(payload["live_behavior_attempted"], "no")
        self.assertEqual(payload["secrets_or_token_files_read"], "no")
        self.assertEqual(
            payload["production_readiness_blockers"],
            [
                "symbol_entitlement_and_rollover_proof_beyond_exact_run_not_recorded",
                "full_live_session_marimo_usability_not_proven",
                "release_hardening_soak_reconnect_and_live_app_launch_not_proven",
                "production_release_remains_premature_until_live_session_usability_and_hardening_predicates_are_satisfied",
            ],
        )

    def test_live_rehearsal_without_market_data_is_partial_and_never_query_ready(self) -> None:
        report = rehearsal.RehearsalReport(
            mode="live",
            status="ok",
            repo_check=True,
            live_flag=True,
            operator_live_runtime_env=True,
            env_keys_present=True,
            token_path_under_target_state=True,
            token_file_present=True,
            token_file_parseable=True,
            token_contract_valid=True,
            access_token_present=True,
            refresh_token_present=True,
            token_fresh="no",
            streamer_credentials_obtained=True,
            runtime_start_attempted=True,
            live_login_succeeded=True,
            live_subscribe_succeeded=True,
            subscribed_contracts_count=5,
            market_data_received=False,
            received_contracts_count=0,
            market_data_diagnostic="no_levelone_futures_updates_received_during_bounded_window",
            repeated_login_on_refresh=False,
            cleanup_status="ok",
            duration_seconds=15.0,
        )

        assessment = rehearsal.assess_rehearsal_readiness(report).to_dict()

        self.assertEqual(assessment["classification"], "partial_live_login_and_subscription_only")
        self.assertEqual(assessment["login_subscription_plumbing_proven"], "yes")
        self.assertEqual(assessment["market_data_delivery_proven"], "no")
        self.assertEqual(assessment["production_live_ready"], "no")
        self.assertEqual(assessment["query_ready_allowed"], "no")
        self.assertIn("market_data_delivery_not_proven", assessment["blocking_reasons"])

    def test_live_rehearsal_with_five_contract_levelone_data_is_not_production_ready(self) -> None:
        report = rehearsal.RehearsalReport(
            mode="live",
            status="ok",
            repo_check=True,
            live_flag=True,
            operator_live_runtime_env=True,
            env_keys_present=True,
            token_path_under_target_state=True,
            token_file_present=True,
            token_file_parseable=True,
            token_contract_valid=True,
            access_token_present=True,
            refresh_token_present=True,
            token_fresh="no",
            streamer_credentials_obtained=True,
            runtime_start_attempted=True,
            live_login_succeeded=True,
            live_subscribe_succeeded=True,
            subscribed_contracts_count=5,
            market_data_received=True,
            received_contracts_count=5,
            market_data_diagnostic="levelone_futures_updates_received",
            repeated_login_on_refresh=False,
            cleanup_status="ok",
            duration_seconds=30.0,
        )

        assessment = rehearsal.assess_rehearsal_readiness(report).to_dict()

        self.assertEqual(assessment["classification"], "live_levelone_market_data_delivery_proven")
        self.assertEqual(assessment["login_subscription_plumbing_proven"], "yes")
        self.assertEqual(assessment["market_data_delivery_proven"], "yes")
        self.assertEqual(assessment["production_live_ready"], "no")
        self.assertEqual(assessment["query_ready_allowed"], "no")
        self.assertIn("chart_futures_delivery_not_proven", assessment["blocking_reasons"])
        self.assertIn("full_live_session_marimo_usability_not_proven", assessment["blocking_reasons"])

    def test_live_rehearsal_with_levelone_and_chart_data_remains_review_only(self) -> None:
        report = rehearsal.RehearsalReport(
            mode="live",
            status="ok",
            repo_check=True,
            live_flag=True,
            operator_live_runtime_env=True,
            env_keys_present=True,
            token_path_under_target_state=True,
            token_file_present=True,
            token_file_parseable=True,
            token_contract_valid=True,
            access_token_present=True,
            refresh_token_present=True,
            token_fresh="yes",
            streamer_credentials_obtained=True,
            runtime_start_attempted=True,
            live_login_succeeded=True,
            live_subscribe_succeeded=True,
            subscribed_contracts_count=5,
            market_data_received=True,
            received_contracts_count=5,
            market_data_diagnostic="levelone_futures_updates_received",
            chart_data_received=True,
            chart_received_contracts_count=5,
            chart_completed_five_minute_contracts_count=5,
            chart_data_diagnostic="chart_futures_completed_five_minute_bars_received",
            repeated_login_on_refresh=False,
            cleanup_status="ok",
            duration_seconds=30.0,
        )

        assessment = rehearsal.assess_rehearsal_readiness(report).to_dict()

        self.assertEqual(
            assessment["classification"],
            "live_levelone_and_chart_market_data_delivery_proven",
        )
        self.assertEqual(assessment["market_data_delivery_proven"], "yes")
        self.assertEqual(assessment["production_live_ready"], "no")
        self.assertEqual(assessment["query_ready_allowed"], "no")
        self.assertNotIn("chart_futures_delivery_not_proven", assessment["blocking_reasons"])
        self.assertIn("rehearsal_result_is_review_only_not_query_authority", assessment["blocking_reasons"])

    def test_receive_pump_continues_after_initial_quiet_dispatch_until_duration(self) -> None:
        config = rehearsal._build_stream_config(symbol_overrides={})
        manager = FakeStartingManager(config=config, client=None)
        manager._snapshot = manager._active_snapshot(record_count=0)

        class QuietThenDataSession:
            def __init__(self) -> None:
                self.calls = 0

            def dispatch_one(self, handler):
                self.calls += 1
                if self.calls == 1:
                    return False
                if self.calls == 2:
                    handler(
                        {
                            "provider": "schwab",
                            "service": "LEVELONE_FUTURES",
                            "symbol": "/ESM26",
                            "contract": "ES",
                            "message_type": "quote",
                            "fields": {"1": 4321.5},
                            "received_at": NOW,
                        }
                    )
                    return True
                return False

        received, distinct_count = rehearsal._pump_receive_loop(
            session=QuietThenDataSession(),
            manager=manager,
            duration_seconds=1.0,
            clock=_make_clock(),
        )

        self.assertTrue(received)
        self.assertEqual(distinct_count, 1)

    def test_receive_pump_routes_chart_futures_bars_into_builder(self) -> None:
        config = rehearsal._build_stream_config(symbol_overrides={})
        manager = FakeStartingManager(config=config, client=None)
        manager._snapshot = manager._active_snapshot(record_count=0)
        chart_builder = rehearsal.ChartFuturesBarBuilder(expected_symbols=rehearsal.DEFAULT_FRONT_MONTH_SYMBOLS)
        chart_messages = [
            {
                "provider": "schwab",
                "service": "CHART_FUTURES",
                "source": "chart_futures",
                "symbol": "/ESM26",
                "contract": "ES",
                "message_type": "bar",
                "start_time": f"2026-05-09T14:{minute:02d}:00+00:00",
                "open": 100.0 + minute,
                "high": 100.75 + minute,
                "low": 99.75 + minute,
                "close": 100.5 + minute,
                "volume": 100 + minute,
                "completed": True,
                "observed_at": f"2026-05-09T14:{minute + 1:02d}:00+00:00",
            }
            for minute in range(5)
        ]

        class ChartOnlySession:
            def __init__(self) -> None:
                self.messages = list(chart_messages)

            def dispatch_one(self, handler):
                if not self.messages:
                    return False
                handler(self.messages.pop(0))
                return True

        observation = rehearsal._pump_receive_loop(
            session=ChartOnlySession(),
            manager=manager,
            duration_seconds=2.0,
            clock=_make_clock(duration=2.0),
            chart_bar_builder=chart_builder,
        )

        self.assertFalse(observation.market_data_received)
        self.assertTrue(observation.chart_data_received)
        self.assertEqual(observation.chart_received_contracts_count, 1)
        self.assertEqual(observation.chart_completed_five_minute_contracts_count, 1)
        self.assertEqual(len(chart_builder.state("ES").completed_five_minute_bars), 1)

    def test_receive_pump_surfaces_token_refresh_failure_as_blocking_reason(self) -> None:
        config = rehearsal._build_stream_config(symbol_overrides={})
        manager = FakeStartingManager(config=config, client=None)
        manager._snapshot = manager._active_snapshot(record_count=0)

        class TokenRefreshFailureSession:
            def dispatch_one(self, handler):
                return False

            def token_refresh_blocking_reason(self) -> str:
                return "token_refresh_failed:SchwabTokenError"

        received, distinct_count = rehearsal._pump_receive_loop(
            session=TokenRefreshFailureSession(),
            manager=manager,
            duration_seconds=1.0,
            clock=_make_clock(),
        )

        self.assertFalse(received)
        self.assertEqual(distinct_count, 0)
        self.assertEqual(manager.connection_lost_reasons, ["token_refresh_failed:SchwabTokenError"])
        assert manager._snapshot is not None
        self.assertEqual(manager._snapshot.state, "blocked")
        self.assertIn("token_refresh_failed:SchwabTokenError", manager._snapshot.blocking_reasons)

    def test_receive_pump_records_early_exit_reason_and_observed_duration(self) -> None:
        config = rehearsal._build_stream_config(symbol_overrides={})
        manager = FakeStartingManager(config=config, client=None)
        manager._snapshot = manager._active_snapshot(record_count=0)

        class TokenRefreshFailureSession:
            def dispatch_one(self, handler):
                return False

            def token_refresh_blocking_reason(self) -> str:
                return "token_refresh_failed:SchwabTokenError"

        observation = rehearsal._pump_receive_loop(
            session=TokenRefreshFailureSession(),
            manager=manager,
            duration_seconds=300.0,
            clock=_make_stepping_clock(step=0.5),
        )

        self.assertEqual(
            observation.early_exit_reason,
            "token_refresh_blocking:token_refresh_failed:SchwabTokenError",
        )
        # The loop broke on the token-refresh signal well before the
        # 300s bounded deadline; observed duration reflects the real
        # (short) wall time, not the requested window.
        self.assertGreater(observation.actual_observed_duration_seconds, 0.0)
        self.assertLess(observation.actual_observed_duration_seconds, 300.0)

    def test_receive_pump_has_empty_early_exit_reason_on_full_window(self) -> None:
        config = rehearsal._build_stream_config(symbol_overrides={})
        manager = FakeStartingManager(config=config, client=None)
        manager._snapshot = manager._active_snapshot(record_count=0)

        class SilentSession:
            def dispatch_one(self, handler):
                return False

        observation = rehearsal._pump_receive_loop(
            session=SilentSession(),
            manager=manager,
            duration_seconds=10.0,
            clock=_make_stepping_clock(step=2.0),
        )

        self.assertEqual(observation.early_exit_reason, "")
        self.assertGreaterEqual(observation.actual_observed_duration_seconds, 10.0)

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
        websocket_factory.connection.recv_queue.append(_subs_ack(code=0, service="CHART_FUTURES"))
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
        with patch.object(
            rehearsal,
            "start_operator_live_runtime",
            wraps=rehearsal.start_operator_live_runtime,
        ) as starter:
            report = rehearsal.run_with_dependencies(
                args=_make_args(live=True, duration=2),
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
        self.assertEqual(
            report.market_data_diagnostic,
            "no_levelone_futures_updates_received_during_bounded_window",
        )
        self.assertEqual(report.chart_data_diagnostic, "no_chart_futures_events_received")
        self.assertEqual(credentials_provider.call_count, 1)
        self.assertEqual(websocket_factory.call_count, 1)
        self.assertEqual(len(managers), 1)
        self.assertEqual(managers[0].start_count, 1)
        self.assertEqual(managers[0].shutdown_count, 1)
        self.assertFalse(starter.call_args.kwargs["start_receive_worker"])
        self.assertEqual(report.cleanup_status, "ok")

    def test_long_duration_request_is_not_clamped_and_reported_transparently(self) -> None:
        websocket_factory = FakeWebsocketFactory()
        websocket_factory.connection.recv_queue.append(_admin_login_ack(code=0))
        websocket_factory.connection.recv_queue.append(_subs_ack(code=0))
        websocket_factory.connection.recv_queue.append(_subs_ack(code=0, service="CHART_FUTURES"))

        deps = rehearsal.RehearsalDependencies(
            token_provider=FakeTokenProvider(),
            credentials_provider=FakeCredentialsProvider(),
            websocket_factory=websocket_factory,
            manager_builder=lambda cfg, c: FakeStartingManager(cfg, c),
            clock=_make_stepping_clock(step=60.0),
        )
        report = rehearsal.run_with_dependencies(
            args=_make_args(live=True, duration=420),
            env=_full_env(self.target_root),
            target_root=self.target_root,
            deps=deps,
        )

        self.assertEqual(report.requested_duration_seconds, 420.0)
        self.assertEqual(report.effective_duration_seconds, 420.0)
        self.assertEqual(report.duration_seconds, 420.0)
        self.assertFalse(report.duration_clamped)
        self.assertGreaterEqual(report.actual_observed_duration_seconds, 420.0)
        self.assertEqual(report.early_exit_reason, "")
        payload = json.loads(rehearsal.render_json(report))
        self.assertEqual(payload["requested_duration_seconds"], 420.0)
        self.assertEqual(payload["effective_duration_seconds"], 420.0)
        self.assertEqual(payload["duration_clamped"], "no")

    def test_oversized_duration_request_is_clamped_to_max_and_flagged(self) -> None:
        websocket_factory = FakeWebsocketFactory()
        websocket_factory.connection.recv_queue.append(_admin_login_ack(code=0))
        websocket_factory.connection.recv_queue.append(_subs_ack(code=0))
        websocket_factory.connection.recv_queue.append(_subs_ack(code=0, service="CHART_FUTURES"))

        deps = rehearsal.RehearsalDependencies(
            token_provider=FakeTokenProvider(),
            credentials_provider=FakeCredentialsProvider(),
            websocket_factory=websocket_factory,
            manager_builder=lambda cfg, c: FakeStartingManager(cfg, c),
            clock=_make_stepping_clock(step=600.0),
        )
        report = rehearsal.run_with_dependencies(
            args=_make_args(live=True, duration=99999),
            env=_full_env(self.target_root),
            target_root=self.target_root,
            deps=deps,
        )

        self.assertEqual(report.requested_duration_seconds, 99999.0)
        self.assertEqual(report.effective_duration_seconds, float(rehearsal.MAX_DURATION_SECONDS))
        self.assertEqual(report.duration_seconds, float(rehearsal.MAX_DURATION_SECONDS))
        self.assertTrue(report.duration_clamped)
        payload = json.loads(rehearsal.render_json(report))
        self.assertEqual(payload["duration_clamped"], "yes")

    def test_chart_subscription_denial_is_provider_or_entitlement_diagnostic(self) -> None:
        websocket_factory = FakeWebsocketFactory()
        websocket_factory.connection.recv_queue.append(_admin_login_ack(code=0))
        websocket_factory.connection.recv_queue.append(_subs_ack(code=0))
        websocket_factory.connection.recv_queue.append(_subs_ack(code=5, service="CHART_FUTURES"))

        deps = rehearsal.RehearsalDependencies(
            token_provider=FakeTokenProvider(),
            credentials_provider=FakeCredentialsProvider(),
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

        self.assertEqual(report.mode, "blocked")
        self.assertEqual(report.status, "blocked")
        self.assertEqual(report.chart_data_diagnostic, "chart_futures_provider_or_entitlement_block")
        self.assertTrue(report.chart_blocking_reasons)
        self.assertNotIn(SECRET_MARKER, rehearsal.render_json(report))

    def test_chart_parse_error_is_malformed_or_unparseable_diagnostic(self) -> None:
        websocket_factory = FakeWebsocketFactory()
        websocket_factory.connection.recv_queue.append(_admin_login_ack(code=0))
        websocket_factory.connection.recv_queue.append(_subs_ack(code=0))
        websocket_factory.connection.recv_queue.append(_subs_ack(code=0, service="CHART_FUTURES"))
        websocket_factory.connection.recv_queue.append("{not-json")

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

        self.assertEqual(report.chart_data_diagnostic, "chart_futures_malformed_or_unparseable_events")
        self.assertEqual(report.chart_dispatch_parse_error_count, 1)

    def test_unsupported_chart_response_is_separate_diagnostic(self) -> None:
        websocket_factory = FakeWebsocketFactory()
        websocket_factory.connection.recv_queue.append(_admin_login_ack(code=0))
        websocket_factory.connection.recv_queue.append(_subs_ack(code=0))
        websocket_factory.connection.recv_queue.append(_subs_ack(code=0, service="CHART_FUTURES"))
        websocket_factory.connection.recv_queue.append(
            json.dumps(
                {
                    "data": [
                        {
                            "service": "UNSUPPORTED_FUTURES",
                            "content": [{"key": "/ESM26", "1": 4321.5}],
                        }
                    ]
                }
            )
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

        self.assertEqual(report.chart_data_diagnostic, "chart_futures_unsupported_response")
        self.assertEqual(report.chart_unsupported_response_count, 1)

    def test_partial_chart_bars_are_not_completed_five_minute_proof(self) -> None:
        websocket_factory = FakeWebsocketFactory()
        websocket_factory.connection.recv_queue.append(_admin_login_ack(code=0))
        websocket_factory.connection.recv_queue.append(_subs_ack(code=0))
        websocket_factory.connection.recv_queue.append(_subs_ack(code=0, service="CHART_FUTURES"))
        websocket_factory.connection.recv_queue.append(_chart_frame("/ESM26", minute=0))

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

        self.assertEqual(report.chart_data_diagnostic, "chart_futures_partial_only_bars_received")
        self.assertEqual(report.chart_received_contracts_count, 1)
        self.assertEqual(report.chart_completed_five_minute_contracts_count, 0)

    def test_all_contract_chart_events_without_five_minute_completion_are_separate_diagnostic(self) -> None:
        websocket_factory = FakeWebsocketFactory()
        websocket_factory.connection.recv_queue.append(_admin_login_ack(code=0))
        websocket_factory.connection.recv_queue.append(_subs_ack(code=0))
        websocket_factory.connection.recv_queue.append(_subs_ack(code=0, service="CHART_FUTURES"))
        for symbol in ("/ESM26", "/NQM26", "/CLM26", "/6EM26", "/MGCM26"):
            websocket_factory.connection.recv_queue.append(_chart_frame(symbol, minute=0))

        deps = rehearsal.RehearsalDependencies(
            token_provider=FakeTokenProvider(),
            credentials_provider=FakeCredentialsProvider(),
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

        self.assertEqual(report.chart_data_diagnostic, "chart_futures_no_completed_five_minute_bars")
        self.assertEqual(report.chart_received_contracts_count, 5)
        self.assertEqual(report.chart_completed_five_minute_contracts_count, 0)

    def test_dispatch_records_market_data_received_without_printing_values(self) -> None:
        token_provider = FakeTokenProvider()
        credentials_provider = FakeCredentialsProvider()
        websocket_factory = FakeWebsocketFactory()
        websocket_factory.connection.recv_queue.append(_admin_login_ack(code=0))
        websocket_factory.connection.recv_queue.append(_subs_ack(code=0))
        websocket_factory.connection.recv_queue.append(_subs_ack(code=0, service="CHART_FUTURES"))
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
        self.assertEqual(report.market_data_diagnostic, "levelone_futures_updates_received")

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

    def test_dispatch_records_chart_futures_completed_bars_without_printing_values(self) -> None:
        token_provider = FakeTokenProvider()
        credentials_provider = FakeCredentialsProvider()
        websocket_factory = FakeWebsocketFactory()
        websocket_factory.connection.recv_queue.append(_admin_login_ack(code=0))
        websocket_factory.connection.recv_queue.append(_subs_ack(code=0))
        websocket_factory.connection.recv_queue.append(_subs_ack(code=0, service="CHART_FUTURES"))
        for symbol in ("/ESM26", "/NQM26", "/CLM26", "/6EM26", "/MGCM26"):
            for minute in range(5):
                websocket_factory.connection.recv_queue.append(_chart_frame(symbol, minute=minute))

        deps = rehearsal.RehearsalDependencies(
            token_provider=token_provider,
            credentials_provider=credentials_provider,
            websocket_factory=websocket_factory,
            manager_builder=lambda cfg, c: FakeStartingManager(cfg, c),
            clock=_make_clock(),
        )
        report = rehearsal.run_with_dependencies(
            args=_make_args(live=True, duration=10),
            env=_full_env(self.target_root),
            target_root=self.target_root,
            deps=deps,
        )

        self.assertEqual(report.mode, "live")
        self.assertFalse(report.market_data_received)
        self.assertTrue(report.chart_data_received)
        self.assertEqual(report.chart_received_contracts_count, 5)
        self.assertEqual(report.chart_completed_five_minute_contracts_count, 5)
        self.assertEqual(report.chart_data_diagnostic, "chart_futures_completed_five_minute_bars_received")
        self.assertEqual(
            report.per_contract_status["ES"]["chart_status"],
            "completed_five_minute_bar_available",
        )
        self.assertEqual(report.per_contract_status["ES"]["quote_status"], "no_quote_event_received")
        text_output = rehearsal.render_text(report)
        json_output = rehearsal.render_json(report)
        self.assertIn("chart_data_received=yes", text_output)
        self.assertNotIn("100.5", text_output)
        self.assertNotIn("100.5", json_output)

    def test_dispatch_accepts_numeric_chart_futures_bars_without_provider_completed_flag(self) -> None:
        token_provider = FakeTokenProvider()
        credentials_provider = FakeCredentialsProvider()
        websocket_factory = FakeWebsocketFactory()
        websocket_factory.connection.recv_queue.append(_admin_login_ack(code=0))
        websocket_factory.connection.recv_queue.append(_subs_ack(code=0))
        websocket_factory.connection.recv_queue.append(_subs_ack(code=0, service="CHART_FUTURES"))
        for symbol in ("/ESM26", "/NQM26", "/CLM26", "/6EM26", "/MGCM26"):
            for minute in range(5):
                websocket_factory.connection.recv_queue.append(_chart_numeric_frame(symbol, minute=minute))

        deps = rehearsal.RehearsalDependencies(
            token_provider=token_provider,
            credentials_provider=credentials_provider,
            websocket_factory=websocket_factory,
            manager_builder=lambda cfg, c: FakeStartingManager(cfg, c),
            clock=_make_clock(),
        )
        report = rehearsal.run_with_dependencies(
            args=_make_args(live=True, duration=10),
            env=_full_env(self.target_root),
            target_root=self.target_root,
            deps=deps,
        )

        self.assertTrue(report.chart_data_received)
        self.assertEqual(report.chart_received_contracts_count, 5)
        self.assertEqual(report.chart_completed_five_minute_contracts_count, 5)
        self.assertEqual(report.chart_blocking_reasons, ())
        self.assertEqual(report.chart_data_diagnostic, "chart_futures_completed_five_minute_bars_received")

    def test_dispatch_counts_numeric_schwab_epoch_millis_timestamps_with_real_manager(self) -> None:
        token_provider = FakeTokenProvider()
        credentials_provider = FakeCredentialsProvider()
        websocket_factory = FakeWebsocketFactory()
        observed_at = datetime(2026, 5, 9, 14, 0, 0, tzinfo=timezone.utc)
        epoch_millis = int(observed_at.timestamp() * 1000)
        websocket_factory.connection.recv_queue.append(_admin_login_ack(code=0))
        websocket_factory.connection.recv_queue.append(_subs_ack(code=0))
        websocket_factory.connection.recv_queue.append(_subs_ack(code=0, service="CHART_FUTURES"))
        websocket_factory.connection.recv_queue.append(_data_frame("/ESM26", 4321.5, timestamp=epoch_millis))
        websocket_factory.connection.recv_queue.append(_data_frame("/NQM26", 17890.25, timestamp=epoch_millis))
        websocket_factory.connection.recv_queue.append(_data_frame("/MGCM26", 2110.0, timestamp=epoch_millis))

        deps = rehearsal.RehearsalDependencies(
            token_provider=token_provider,
            credentials_provider=credentials_provider,
            websocket_factory=websocket_factory,
            manager_builder=lambda cfg, c: SchwabStreamManager(cfg, client=c, clock=lambda: observed_at),
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
        self.assertEqual(report.market_data_diagnostic, "levelone_futures_updates_received")
        self.assertEqual(
            report.per_contract_status["ES"]["readiness_provider_status"],
            "connected",
        )
        self.assertEqual(
            report.per_contract_status["ES"]["readiness_state"],
            "LIVE_RUNTIME_CONNECTED",
        )
        self.assertEqual(
            report.per_contract_status["ES"]["readiness_quote_status"],
            "quote available",
        )
        self.assertEqual(
            report.per_contract_status["ES"]["readiness_chart_status"],
            "chart missing",
        )
        self.assertEqual(report.per_contract_status["ES"]["missing_live_fields"], "none")
        self.assertEqual(report.per_contract_status["ES"]["query_ready"], "no")

        text_output = rehearsal.render_text(report)
        self.assertIn(
            "contract_status=ES|quote_event=fresh_quote_update_received",
            text_output,
        )
        self.assertIn("|quote=quote available|chart=chart missing", text_output)
        self.assertIn("|missing_fields=none|query_ready=no", text_output)
        self.assertNotIn("4321.5", text_output)

    def test_repeated_dispatch_does_not_repeat_login_subscribe_or_start(self) -> None:
        token_provider = FakeTokenProvider()
        credentials_provider = FakeCredentialsProvider()
        websocket_factory = FakeWebsocketFactory()
        ws_conn = websocket_factory.connection
        ws_conn.recv_queue.append(_admin_login_ack(code=0))
        ws_conn.recv_queue.append(_subs_ack(code=0))
        ws_conn.recv_queue.append(_subs_ack(code=0, service="CHART_FUTURES"))
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
        # Login frame sent once, one subscribe frame per requested service,
        # then logout on shutdown is sent in the close path.
        self.assertEqual(ws_conn.sent[0].count("\"command\":\"LOGIN\""), 1)
        self.assertEqual(ws_conn.sent[1].count("\"command\":\"SUBS\""), 1)
        self.assertEqual(ws_conn.sent[2].count("\"command\":\"SUBS\""), 1)
        # The dispatch loop must NOT have sent additional LOGIN or SUBS frames.
        for payload in ws_conn.sent[3:]:
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
        websocket_factory.connection.recv_queue.append(_subs_ack(code=0, service="CHART_FUTURES"))
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
        websocket_factory.connection.recv_queue.append(_subs_ack(code=0, service="CHART_FUTURES"))

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
        ws.recv_queue.append(_subs_ack(code=0, service="CHART_FUTURES"))

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
