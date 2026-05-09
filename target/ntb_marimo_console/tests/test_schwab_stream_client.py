from __future__ import annotations

import importlib
import os
import unittest
from dataclasses import dataclass
from unittest.mock import patch

from ntb_marimo_console.contract_universe import final_target_contracts
from ntb_marimo_console.market_data.stream_cache import StreamCacheSnapshot
from ntb_marimo_console.market_data.stream_manager import (
    SchwabStreamManagerConfig,
    StreamClientResult,
    StreamManagerSnapshot,
    StreamSubscriptionRequest,
)
from ntb_marimo_console import schwab_stream_client as schwab_stream_client_module
from ntb_marimo_console.operator_live_launcher import (
    OperatorLiveRuntimeFactoryError,
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
    OperatorSchwabStreamClient,
    build_operator_schwab_stream_client_factory,
)
from ntb_marimo_console.session_lifecycle import (
    load_session_lifecycle_from_env,
    refresh_runtime_snapshot,
)


NOW = "2026-05-09T14:00:00+00:00"


def _live_config() -> SchwabStreamManagerConfig:
    return SchwabStreamManagerConfig(
        provider="schwab",
        services_requested=("LEVELONE_FUTURES",),
        symbols_requested=("/ESM26", "/NQM26", "/CLM26", "/6EM26", "/MGCM26"),
        fields_requested=(0, 1, 2, 3),
        explicit_live_opt_in=True,
        contracts_requested=final_target_contracts(),
    )


def _active_cache_snapshot(config: SchwabStreamManagerConfig) -> StreamCacheSnapshot:
    contracts = config.contracts_requested
    symbols = config.symbols_requested or tuple(f"/{c}M26" for c in contracts)
    pairs = list(zip(contracts, symbols))
    from ntb_marimo_console.market_data.stream_cache import StreamCacheRecord

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


@dataclass
class CountingSession:
    login_result: StreamClientResult = StreamClientResult(succeeded=True)
    subscribe_result: StreamClientResult = StreamClientResult(succeeded=True)
    close_result: StreamClientResult = StreamClientResult(succeeded=True)
    login_calls: int = 0
    subscribe_calls: int = 0
    close_calls: int = 0
    login_exception: BaseException | None = None
    subscribe_exception: BaseException | None = None
    close_exception: BaseException | None = None

    def login(self, config: SchwabStreamManagerConfig) -> StreamClientResult:
        self.login_calls += 1
        if self.login_exception is not None:
            raise self.login_exception
        return self.login_result

    def subscribe(self, request: StreamSubscriptionRequest) -> StreamClientResult:
        self.subscribe_calls += 1
        if self.subscribe_exception is not None:
            raise self.subscribe_exception
        return self.subscribe_result

    def close(self) -> StreamClientResult:
        self.close_calls += 1
        if self.close_exception is not None:
            raise self.close_exception
        return self.close_result


class CountingSessionFactory:
    def __init__(self, session: CountingSession) -> None:
        self._session = session
        self.call_count = 0
        self.last_config: SchwabStreamManagerConfig | None = None

    def __call__(self, config: SchwabStreamManagerConfig) -> CountingSession:
        self.call_count += 1
        self.last_config = config
        return self._session


class _Sentinel:
    def __init__(self) -> None:
        self.call_count = 0

    def __call__(self, *args, **kwargs):
        self.call_count += 1
        raise AssertionError("sentinel_must_not_be_invoked")


class FakeStartingManager:
    """Fake stream manager that drives client.login + client.subscribe exactly once.

    Mirrors the real ``SchwabStreamManager.start()`` happy path enough to verify
    one-start / one-login / one-subscribe discipline through the factory boundary
    without needing real Schwab work.
    """

    def __init__(self, config: SchwabStreamManagerConfig, client: object) -> None:
        self.config = config
        self.client = client
        self.start_count = 0
        self.shutdown_count = 0
        self.snapshot_count = 0
        self._snapshot: StreamManagerSnapshot | None = None

    def start(self) -> StreamManagerSnapshot:
        self.start_count += 1
        login_result = self.client.login(self.config)
        if not login_result.succeeded:
            self._snapshot = StreamManagerSnapshot(
                state="blocked",
                config=self.config,
                cache=StreamCacheSnapshot(
                    generated_at=NOW,
                    provider="schwab",
                    provider_status="blocked",
                    cache_max_age_seconds=15.0,
                    records=(),
                    blocking_reasons=(login_result.reason or "login_denied",),
                    stale_symbols=(),
                ),
                events=(),
                blocking_reasons=(login_result.reason or "login_denied",),
                login_count=1,
                subscription_count=0,
            )
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
            self._snapshot = StreamManagerSnapshot(
                state="blocked",
                config=self.config,
                cache=StreamCacheSnapshot(
                    generated_at=NOW,
                    provider="schwab",
                    provider_status="blocked",
                    cache_max_age_seconds=15.0,
                    records=(),
                    blocking_reasons=(subscribe_result.reason or "subscription_failed",),
                    stale_symbols=(),
                ),
                events=(),
                blocking_reasons=(subscribe_result.reason or "subscription_failed",),
                login_count=1,
                subscription_count=1,
            )
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
        return self._snapshot or StreamManagerSnapshot(
            state="shutdown",
            config=self.config,
            cache=StreamCacheSnapshot(
                generated_at=NOW,
                provider="schwab",
                provider_status="shutdown",
                cache_max_age_seconds=15.0,
                records=(),
                blocking_reasons=("shutdown_completed",),
                stale_symbols=(),
            ),
            events=(),
            blocking_reasons=(),
            login_count=1,
            subscription_count=1,
        )


class OperatorSchwabStreamClientTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_operator_live_runtime_registration()
        self.addCleanup(clear_operator_live_runtime_registration)

    # -- Import / lazy guarantees ---------------------------------------------------

    def test_import_does_not_perform_network_credential_or_token_work(self) -> None:
        self.assertTrue(hasattr(schwab_stream_client_module, "OperatorSchwabStreamClient"))
        self.assertTrue(hasattr(schwab_stream_client_module, "build_operator_schwab_stream_client_factory"))
        self.assertTrue(hasattr(schwab_stream_client_module, "StreamerSession"))

        sentinel_open = _Sentinel()
        sentinel_urlopen = _Sentinel()

        with patch.dict(os.environ, {}, clear=True), \
                patch("builtins.open", new=sentinel_open), \
                patch("urllib.request.urlopen", new=sentinel_urlopen):
            importlib.reload(schwab_stream_client_module)
            self.assertTrue(hasattr(schwab_stream_client_module, "OperatorSchwabStreamClient"))

        self.assertEqual(sentinel_open.call_count, 0)
        self.assertEqual(sentinel_urlopen.call_count, 0)
        for key in os.environ:
            self.assertFalse(
                key.startswith("SCHWAB_"),
                msg="default test run must not set Schwab credential env vars",
            )

    # -- Factory builder semantics --------------------------------------------------

    def test_factory_construction_does_not_invoke_streamer_session_factory(self) -> None:
        sentinel = _Sentinel()
        client_factory = build_operator_schwab_stream_client_factory(streamer_session_factory=sentinel)
        self.assertEqual(sentinel.call_count, 0)
        self.assertTrue(callable(client_factory))

    def test_factory_invocation_constructs_concrete_client_via_session_factory_once(self) -> None:
        session = CountingSession()
        session_factory = CountingSessionFactory(session)
        client_factory = build_operator_schwab_stream_client_factory(streamer_session_factory=session_factory)
        config = _live_config()

        client = client_factory(config)
        self.assertIsInstance(client, OperatorSchwabStreamClient)
        self.assertEqual(session_factory.call_count, 1)
        self.assertIs(session_factory.last_config, config)
        self.assertEqual(session.login_calls, 0)
        self.assertEqual(session.subscribe_calls, 0)
        self.assertEqual(session.close_calls, 0)

        client_factory(config)
        self.assertEqual(session_factory.call_count, 2)

    def test_factory_rejects_noncallable_streamer_session_factory(self) -> None:
        with self.assertRaises(TypeError):
            build_operator_schwab_stream_client_factory(streamer_session_factory=None)  # type: ignore[arg-type]
        with self.assertRaises(TypeError):
            build_operator_schwab_stream_client_factory(streamer_session_factory="not_callable")  # type: ignore[arg-type]

    # -- Wrapper delegation and redaction -------------------------------------------

    def test_login_delegates_session_success_unchanged(self) -> None:
        session = CountingSession(login_result=StreamClientResult(succeeded=True))
        client = OperatorSchwabStreamClient(session)
        result = client.login(_live_config())
        self.assertTrue(result.succeeded)
        self.assertIsNone(result.reason)
        self.assertEqual(session.login_calls, 1)

    def test_login_returns_session_failure_with_reason_redacted_by_post_init(self) -> None:
        session = CountingSession(
            login_result=StreamClientResult(succeeded=False, reason="token=should_not_print"),
        )
        client = OperatorSchwabStreamClient(session)
        result = client.login(_live_config())
        self.assertFalse(result.succeeded)
        self.assertIsNotNone(result.reason)
        assert result.reason is not None
        self.assertIn("[REDACTED]", result.reason)
        self.assertNotIn("should_not_print", result.reason)

    def test_login_redacts_session_exception_messages(self) -> None:
        session = CountingSession(login_exception=RuntimeError("token=should_not_print"))
        client = OperatorSchwabStreamClient(session)
        result = client.login(_live_config())
        self.assertFalse(result.succeeded)
        assert result.reason is not None
        self.assertIn("login_exception", result.reason)
        self.assertIn("[REDACTED]", result.reason)
        self.assertNotIn("should_not_print", result.reason)

    def test_subscribe_redacts_session_exception_messages(self) -> None:
        session = CountingSession(subscribe_exception=RuntimeError("token=should_not_print"))
        client = OperatorSchwabStreamClient(session)
        request = StreamSubscriptionRequest(
            provider="schwab",
            services=("LEVELONE_FUTURES",),
            symbols=("/ESM26",),
            fields=(0,),
            contracts=("ES",),
        )
        result = client.subscribe(request)
        self.assertFalse(result.succeeded)
        assert result.reason is not None
        self.assertIn("subscribe_exception", result.reason)
        self.assertIn("[REDACTED]", result.reason)
        self.assertNotIn("should_not_print", result.reason)

    def test_close_redacts_session_exception_messages(self) -> None:
        session = CountingSession(close_exception=RuntimeError("token=should_not_print"))
        client = OperatorSchwabStreamClient(session)
        result = client.close()
        self.assertFalse(result.succeeded)
        assert result.reason is not None
        self.assertIn("close_exception", result.reason)
        self.assertIn("[REDACTED]", result.reason)
        self.assertNotIn("should_not_print", result.reason)

    # -- Launcher integration -------------------------------------------------------

    def test_factory_wires_into_start_operator_live_runtime_under_explicit_opt_in(self) -> None:
        session = CountingSession()
        session_factory = CountingSessionFactory(session)
        client_factory = build_operator_schwab_stream_client_factory(
            streamer_session_factory=session_factory,
        )

        with patch.dict(
            os.environ,
            {"NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME},
            clear=True,
        ):
            result = start_operator_live_runtime(
                client_factory=client_factory,
                config=_live_config(),
                manager_builder=lambda cfg, client: FakeStartingManager(cfg, client),
            )

        self.assertEqual(session_factory.call_count, 1)
        self.assertEqual(session.login_calls, 1)
        self.assertEqual(session.subscribe_calls, 1)
        manager = result.manager
        assert isinstance(manager, FakeStartingManager)
        self.assertEqual(manager.start_count, 1)
        self.assertEqual(result.started_snapshot.state, "active")
        self.assertEqual(result.started_snapshot.blocking_reasons, ())
        self.assertIsNotNone(get_registered_operator_live_runtime_producer())

    def test_factory_does_not_run_without_explicit_opt_in(self) -> None:
        session = CountingSession()
        session_factory = CountingSessionFactory(session)
        client_factory = build_operator_schwab_stream_client_factory(
            streamer_session_factory=session_factory,
        )

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(OperatorLiveRuntimeOptInRequired):
                start_operator_live_runtime(
                    client_factory=client_factory,
                    config=_live_config(),
                )

        self.assertEqual(session_factory.call_count, 0)
        self.assertEqual(session.login_calls, 0)
        self.assertEqual(session.subscribe_calls, 0)
        self.assertIsNone(get_registered_operator_live_runtime_producer())

    def test_session_login_failure_blocks_launcher_with_no_fixture_fallback(self) -> None:
        session = CountingSession(
            login_result=StreamClientResult(succeeded=False, reason="token=should_not_print"),
        )
        session_factory = CountingSessionFactory(session)
        client_factory = build_operator_schwab_stream_client_factory(
            streamer_session_factory=session_factory,
        )

        with patch.dict(
            os.environ,
            {"NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME},
            clear=True,
        ):
            with self.assertRaises(OperatorLiveRuntimeStartError) as ctx:
                start_operator_live_runtime(
                    client_factory=client_factory,
                    config=_live_config(),
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
        self.assertNotIn("should_not_print", message)
        self.assertIsNone(get_registered_operator_live_runtime_producer())
        self.assertEqual(follow_up.status, LIVE_RUNTIME_UNAVAILABLE)

    def test_streamer_session_factory_failure_propagates_redacted_via_launcher_factory_error(self) -> None:
        def failing_factory(config: SchwabStreamManagerConfig):
            raise RuntimeError("token=should_not_print")

        client_factory = build_operator_schwab_stream_client_factory(
            streamer_session_factory=failing_factory,
        )

        with patch.dict(
            os.environ,
            {"NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME},
            clear=True,
        ):
            with self.assertRaises(OperatorLiveRuntimeFactoryError) as ctx:
                start_operator_live_runtime(
                    client_factory=client_factory,
                    config=_live_config(),
                )

        message = str(ctx.exception)
        self.assertIn("operator_live_runtime_factory_error", message)
        self.assertNotIn("should_not_print", message)
        self.assertIsNone(get_registered_operator_live_runtime_producer())

    # -- Refresh path invariants ----------------------------------------------------

    def test_refresh_path_does_not_invoke_session_factory_or_client_methods(self) -> None:
        session = CountingSession()
        session_factory = CountingSessionFactory(session)
        client_factory = build_operator_schwab_stream_client_factory(
            streamer_session_factory=session_factory,
        )

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
                manager_builder=lambda cfg, client: FakeStartingManager(cfg, client),
            )
            lifecycle = load_session_lifecycle_from_env(
                runtime_snapshot_producer=launch.producer,
                operator_runtime_mode=OPERATOR_LIVE_RUNTIME,
            )
            initial_snapshot_count = launch.manager.snapshot_count  # type: ignore[attr-defined]
            for _ in range(3):
                lifecycle = refresh_runtime_snapshot(lifecycle)

        manager = launch.manager
        assert isinstance(manager, FakeStartingManager)
        self.assertEqual(session_factory.call_count, 1)
        self.assertEqual(session.login_calls, 1)
        self.assertEqual(session.subscribe_calls, 1)
        self.assertEqual(session.close_calls, 0)
        self.assertEqual(manager.start_count, 1)
        self.assertEqual(manager.snapshot_count - initial_snapshot_count, 3)

    # -- Universe invariant ---------------------------------------------------------

    def test_factory_default_config_preserves_final_target_universe_and_excludes_zn_and_gc(self) -> None:
        session = CountingSession()
        session_factory = CountingSessionFactory(session)
        client_factory = build_operator_schwab_stream_client_factory(
            streamer_session_factory=session_factory,
        )

        with patch.dict(
            os.environ,
            {"NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME},
            clear=True,
        ):
            result = start_operator_live_runtime(
                client_factory=client_factory,
                config=_live_config(),
                manager_builder=lambda cfg, client: FakeStartingManager(cfg, client),
            )

        contracts = result.started_snapshot.config.contracts_requested
        self.assertEqual(contracts, ("ES", "NQ", "CL", "6E", "MGC"))
        self.assertNotIn("ZN", contracts)
        self.assertNotIn("GC", contracts)
        self.assertIn("MGC", contracts)
        # MGC must remain MGC; never silently mapped to GC.
        self.assertNotEqual("GC", "MGC")


if __name__ == "__main__":
    unittest.main()
