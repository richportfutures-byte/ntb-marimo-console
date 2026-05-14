from __future__ import annotations

import importlib
import importlib.util
import os
import unittest
from dataclasses import dataclass
from unittest.mock import patch

from ntb_marimo_console.contract_universe import final_target_contracts
from ntb_marimo_console.market_data.stream_cache import StreamCacheRecord, StreamCacheSnapshot
from ntb_marimo_console.market_data.stream_manager import (
    SchwabStreamManagerConfig,
    StreamClientResult,
    StreamManagerSnapshot,
    StreamSubscriptionRequest,
)
from ntb_marimo_console import operator_live_launcher
from ntb_marimo_console.operator_live_launcher import (
    OperatorLiveRuntimeFactoryError,
    OperatorLiveRuntimeOptInRequired,
    OperatorLiveRuntimeStartError,
    start_operator_live_runtime,
    stop_operator_live_runtime,
)
from ntb_marimo_console.operator_live_runtime import (
    LIVE_RUNTIME_UNAVAILABLE,
    OPERATOR_LIVE_RUNTIME,
    StreamManagerRuntimeSnapshotProducer,
    build_operator_runtime_snapshot_producer_from_env,
    clear_operator_live_runtime_registration,
    get_registered_operator_live_runtime_producer,
    resolve_operator_runtime_snapshot,
)


NOW = "2026-05-09T14:00:00+00:00"


def _runtime_record(contract: str, *, symbol: str) -> StreamCacheRecord:
    return StreamCacheRecord(
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


def _active_cache_snapshot(config: SchwabStreamManagerConfig) -> StreamCacheSnapshot:
    symbols = config.symbols_requested or ("/ESM26", "/NQM26", "/CLM26", "/6EM26", "/MGCM26")
    contracts = config.contracts_requested
    pairs = list(zip(contracts, symbols))
    return StreamCacheSnapshot(
        generated_at=NOW,
        provider="schwab",
        provider_status="active",
        cache_max_age_seconds=15.0,
        records=tuple(_runtime_record(contract, symbol=symbol) for contract, symbol in pairs),
        blocking_reasons=(),
        stale_symbols=(),
    )


def _live_config() -> SchwabStreamManagerConfig:
    return SchwabStreamManagerConfig(
        provider="schwab",
        services_requested=("LEVELONE_FUTURES",),
        symbols_requested=("/ESM26", "/NQM26", "/CLM26", "/6EM26", "/MGCM26"),
        fields_requested=(0, 1, 2, 3),
        explicit_live_opt_in=True,
        contracts_requested=final_target_contracts(),
    )


@dataclass
class CallTracker:
    call_count: int = 0


class FakeSchwabClient:
    def __init__(
        self,
        *,
        login_result: StreamClientResult | None = None,
        subscribe_result: StreamClientResult | None = None,
    ) -> None:
        self.login_result = login_result or StreamClientResult(succeeded=True)
        self.subscribe_result = subscribe_result or StreamClientResult(succeeded=True)
        self.login_calls = 0
        self.subscribe_calls = 0
        self.close_calls = 0

    def login(self, config: SchwabStreamManagerConfig) -> StreamClientResult:
        self.login_calls += 1
        return self.login_result

    def subscribe(self, request: StreamSubscriptionRequest) -> StreamClientResult:
        self.subscribe_calls += 1
        return self.subscribe_result

    def close(self) -> StreamClientResult:
        self.close_calls += 1
        return StreamClientResult(succeeded=True)


class FakeReceiveSession:
    def __init__(self, messages: tuple[dict[str, object], ...] = ()) -> None:
        self.messages = messages
        self.dispatch_calls = 0
        self.last_status = "idle"

    def dispatch_one(self, handler) -> bool:
        self.dispatch_calls += 1
        if not self.messages:
            self.last_status = "timeout"
            return False
        for message in self.messages:
            handler(message)
        self.last_status = "message"
        return True

    def dispatch_status(self) -> str:
        return self.last_status


class FakeSchwabClientWithReceiveSession(FakeSchwabClient):
    def __init__(self, session: FakeReceiveSession) -> None:
        super().__init__()
        self._receive_session = session

    @property
    def receive_session(self) -> FakeReceiveSession:
        return self._receive_session


class FakeReceiveWorker:
    instances: list["FakeReceiveWorker"] = []

    def __init__(self, *, session: object, manager: object) -> None:
        self.session = session
        self.manager = manager
        self.start_calls = 0
        self.stop_calls = 0
        self.join_calls = 0
        FakeReceiveWorker.instances.append(self)

    def start(self) -> str:
        self.start_calls += 1
        return "started"

    def stop(self) -> str:
        self.stop_calls += 1
        return "stopped"

    def join(self, timeout: float | None = None) -> str:
        self.join_calls += 1
        return "joined"


class PumpOnceReceiveWorker(FakeReceiveWorker):
    def start(self) -> str:
        self.start_calls += 1
        dispatch_one = getattr(self.session, "dispatch_one")
        dispatch_one(self.manager.ingest_message)
        return "started"


class FakeManager:
    def __init__(
        self,
        config: SchwabStreamManagerConfig,
        client: object,
        *,
        start_snapshot: StreamManagerSnapshot | None = None,
        start_error: BaseException | None = None,
    ) -> None:
        self.config = config
        self.client = client
        self._start_snapshot = start_snapshot
        self._start_error = start_error
        self.start_count = 0
        self.shutdown_count = 0
        self.snapshot_count = 0
        self.ingested_messages: list[dict[str, object]] = []

    def _default_active_snapshot(self) -> StreamManagerSnapshot:
        return StreamManagerSnapshot(
            state="active",
            config=self.config,
            cache=_active_cache_snapshot(self.config),
            events=(),
            blocking_reasons=(),
            login_count=1,
            subscription_count=1,
        )

    def start(self) -> StreamManagerSnapshot:
        self.start_count += 1
        if self._start_error is not None:
            raise self._start_error
        if self._start_snapshot is not None:
            return self._start_snapshot
        return self._default_active_snapshot()

    def shutdown(self) -> StreamManagerSnapshot:
        self.shutdown_count += 1
        config = self.config
        return StreamManagerSnapshot(
            state="shutdown",
            config=config,
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

    def snapshot(self) -> StreamManagerSnapshot:
        self.snapshot_count += 1
        return self._start_snapshot or self._default_active_snapshot()

    def ingest_message(self, message: dict[str, object]) -> StreamManagerSnapshot:
        self.ingested_messages.append(dict(message))
        return self.snapshot()


class _Sentinel:
    def __init__(self) -> None:
        self.call_count = 0

    def __call__(self, *args, **kwargs) -> object:
        self.call_count += 1
        raise AssertionError("sentinel_must_not_be_invoked")


class OperatorLiveLauncherTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_operator_live_runtime_registration()
        FakeReceiveWorker.instances.clear()
        self.addCleanup(clear_operator_live_runtime_registration)

    def test_import_does_not_construct_or_start_anything(self) -> None:
        self.assertTrue(hasattr(operator_live_launcher, "start_operator_live_runtime"))
        self.assertTrue(hasattr(operator_live_launcher, "stop_operator_live_runtime"))
        self.assertTrue(hasattr(operator_live_launcher, "OperatorLiveRuntimeOptInRequired"))
        self.assertTrue(hasattr(operator_live_launcher, "OperatorLiveRuntimeFactoryError"))
        self.assertTrue(hasattr(operator_live_launcher, "OperatorLiveRuntimeStartError"))
        self.assertTrue(hasattr(operator_live_launcher, "OperatorLiveLaunchResult"))

        source = importlib.util.find_spec("ntb_marimo_console.operator_live_launcher")
        self.assertIsNotNone(source)

        self.assertIsNone(get_registered_operator_live_runtime_producer())

        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(get_registered_operator_live_runtime_producer())

    def test_launcher_refuses_without_operator_live_runtime_env(self) -> None:
        sentinel = _Sentinel()
        manager_sentinel = _Sentinel()

        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(OperatorLiveRuntimeOptInRequired):
                start_operator_live_runtime(
                    client_factory=sentinel,
                    config=_live_config(),
                    manager_builder=manager_sentinel,
                )

        self.assertEqual(sentinel.call_count, 0)
        self.assertEqual(manager_sentinel.call_count, 0)
        self.assertIsNone(get_registered_operator_live_runtime_producer())

    def test_launcher_constructs_and_starts_manager_via_factory_once(self) -> None:
        client = FakeSchwabClient()
        config = _live_config()
        captured: dict[str, object] = {}

        def client_factory(cfg: SchwabStreamManagerConfig) -> FakeSchwabClient:
            captured["client_calls"] = captured.get("client_calls", 0)
            captured["client_calls"] = int(captured["client_calls"]) + 1  # type: ignore[arg-type]
            captured["config"] = cfg
            return client

        def manager_builder(cfg: SchwabStreamManagerConfig, real_client: object) -> FakeManager:
            return FakeManager(cfg, real_client)

        with patch.dict(
            os.environ,
            {"NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME},
            clear=True,
        ):
            result = start_operator_live_runtime(
                client_factory=client_factory,
                config=config,
                manager_builder=manager_builder,
            )

        manager = result.manager
        assert isinstance(manager, FakeManager)
        self.assertEqual(captured.get("client_calls"), 1)
        self.assertIs(captured.get("config"), config)
        self.assertEqual(manager.start_count, 1)
        self.assertEqual(result.started_snapshot.state, "active")
        self.assertEqual(result.started_snapshot.blocking_reasons, ())
        self.assertIsInstance(result.producer, StreamManagerRuntimeSnapshotProducer)
        self.assertIs(result.producer.manager, manager)

    def test_launcher_starts_receive_worker_for_registered_streamer_session(self) -> None:
        session = FakeReceiveSession()
        client = FakeSchwabClientWithReceiveSession(session)
        config = _live_config()

        def manager_builder(cfg: SchwabStreamManagerConfig, real_client: object) -> FakeManager:
            return FakeManager(cfg, real_client)

        with patch.dict(
            os.environ,
            {"NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME},
            clear=True,
        ):
            result = start_operator_live_runtime(
                client_factory=lambda cfg: client,
                config=config,
                manager_builder=manager_builder,
                receive_thread_builder=FakeReceiveWorker,
            )

        manager = result.manager
        worker = result.receive_worker
        assert isinstance(manager, FakeManager)
        assert isinstance(worker, FakeReceiveWorker)
        self.assertIs(worker.session, session)
        self.assertIs(worker.manager, manager)
        self.assertEqual(worker.start_calls, 1)
        self.assertEqual(result.receive_worker_status, "started")

        stop_operator_live_runtime(manager)
        self.assertEqual(worker.stop_calls, 1)
        self.assertEqual(worker.join_calls, 1)
        self.assertEqual(manager.shutdown_count, 1)

    def test_receive_worker_pumps_live_messages_into_registered_cache_producer(self) -> None:
        messages = tuple(
            {
                "service": "LEVELONE_FUTURES",
                "symbol": symbol,
                "contract": contract,
                "message_type": "quote",
                "fields": {"1": 100.0 + index},
                "received_at": NOW,
            }
            for index, (contract, symbol) in enumerate(
                zip(final_target_contracts(), _live_config().symbols_requested)
            )
        )
        session = FakeReceiveSession(messages)
        client = FakeSchwabClientWithReceiveSession(session)

        with patch.dict(
            os.environ,
            {"NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME},
            clear=True,
        ):
            result = start_operator_live_runtime(
                client_factory=lambda cfg: client,
                config=_live_config(),
                receive_thread_builder=PumpOnceReceiveWorker,
            )

        snapshot = result.producer.read_snapshot()
        assert isinstance(snapshot, StreamManagerSnapshot)
        contracts = {record.contract for record in snapshot.cache.records}
        self.assertEqual(contracts, set(final_target_contracts()))
        self.assertEqual(client.login_calls, 1)
        self.assertEqual(client.subscribe_calls, 1)
        self.assertEqual(session.dispatch_calls, 1)

        stop_operator_live_runtime(result.manager)

    def test_launcher_registers_manager_when_register_true(self) -> None:
        client = FakeSchwabClient()
        config = _live_config()

        def manager_builder(cfg: SchwabStreamManagerConfig, real_client: object) -> FakeManager:
            return FakeManager(cfg, real_client)

        with patch.dict(
            os.environ,
            {"NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME},
            clear=True,
        ):
            result = start_operator_live_runtime(
                client_factory=lambda cfg: client,
                config=config,
                manager_builder=manager_builder,
            )

            registered = get_registered_operator_live_runtime_producer()
            assert isinstance(registered, StreamManagerRuntimeSnapshotProducer)
            self.assertIs(registered.manager, result.manager)

            built = build_operator_runtime_snapshot_producer_from_env()
            assert isinstance(built, StreamManagerRuntimeSnapshotProducer)
            self.assertIs(built.manager, result.manager)

    def test_launcher_does_not_register_when_register_false(self) -> None:
        client = FakeSchwabClient()
        config = _live_config()

        def manager_builder(cfg: SchwabStreamManagerConfig, real_client: object) -> FakeManager:
            return FakeManager(cfg, real_client)

        with patch.dict(
            os.environ,
            {"NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME},
            clear=True,
        ):
            result = start_operator_live_runtime(
                client_factory=lambda cfg: client,
                config=config,
                manager_builder=manager_builder,
                register=False,
            )

        self.assertIsNone(get_registered_operator_live_runtime_producer())
        self.assertIsInstance(result.producer, StreamManagerRuntimeSnapshotProducer)

    def test_launcher_propagates_factory_failure_with_no_fixture_fallback(self) -> None:
        manager_sentinel = _Sentinel()

        def failing_factory(cfg: SchwabStreamManagerConfig) -> object:
            raise RuntimeError("token=should_not_print secret=should_not_print")

        with patch.dict(
            os.environ,
            {"NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME},
            clear=True,
        ):
            with self.assertRaises(OperatorLiveRuntimeFactoryError) as ctx:
                start_operator_live_runtime(
                    client_factory=failing_factory,
                    config=_live_config(),
                    manager_builder=manager_sentinel,
                )

        message = str(ctx.exception)
        self.assertIn("operator_live_runtime_factory_error", message)
        self.assertNotIn("should_not_print", message)
        self.assertIn("[REDACTED]", message)
        self.assertIsInstance(ctx.exception.__cause__, RuntimeError)
        self.assertEqual(manager_sentinel.call_count, 0)
        self.assertIsNone(get_registered_operator_live_runtime_producer())

    def test_launcher_propagates_start_failure_with_no_fixture_fallback(self) -> None:
        client = FakeSchwabClient(
            login_result=StreamClientResult(succeeded=False, reason="token=should_not_print"),
        )
        config = _live_config()

        def manager_builder(cfg: SchwabStreamManagerConfig, real_client: object) -> FakeManager:
            blocked = StreamManagerSnapshot(
                state="blocked",
                config=cfg,
                cache=StreamCacheSnapshot(
                    generated_at=NOW,
                    provider="schwab",
                    provider_status="blocked",
                    cache_max_age_seconds=15.0,
                    records=(),
                    blocking_reasons=("login_denied:token=[REDACTED]",),
                    stale_symbols=(),
                ),
                events=(),
                blocking_reasons=("login_denied:token=[REDACTED]",),
                login_count=1,
                subscription_count=0,
            )
            return FakeManager(cfg, real_client, start_snapshot=blocked)

        with patch.dict(
            os.environ,
            {"NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME},
            clear=True,
        ):
            with self.assertRaises(OperatorLiveRuntimeStartError) as ctx:
                start_operator_live_runtime(
                    client_factory=lambda cfg: client,
                    config=config,
                    manager_builder=manager_builder,
                )

            self.assertIsNone(get_registered_operator_live_runtime_producer())

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
        self.assertEqual(follow_up.status, LIVE_RUNTIME_UNAVAILABLE)

    def test_launcher_propagates_unexpected_start_exception(self) -> None:
        client = FakeSchwabClient()
        config = _live_config()

        def manager_builder(cfg: SchwabStreamManagerConfig, real_client: object) -> FakeManager:
            return FakeManager(
                cfg,
                real_client,
                start_error=RuntimeError("token=should_not_print"),
            )

        with patch.dict(
            os.environ,
            {"NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME},
            clear=True,
        ):
            with self.assertRaises(OperatorLiveRuntimeStartError) as ctx:
                start_operator_live_runtime(
                    client_factory=lambda cfg: client,
                    config=config,
                    manager_builder=manager_builder,
                )

        message = str(ctx.exception)
        self.assertIn("operator_live_runtime_start_error", message)
        self.assertNotIn("should_not_print", message)
        self.assertIsInstance(ctx.exception.__cause__, RuntimeError)
        self.assertIsNone(get_registered_operator_live_runtime_producer())

    def test_stop_operator_live_runtime_calls_shutdown_and_clears_registration(self) -> None:
        client = FakeSchwabClient()
        config = _live_config()

        def manager_builder(cfg: SchwabStreamManagerConfig, real_client: object) -> FakeManager:
            return FakeManager(cfg, real_client)

        with patch.dict(
            os.environ,
            {"NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME},
            clear=True,
        ):
            result = start_operator_live_runtime(
                client_factory=lambda cfg: client,
                config=config,
                manager_builder=manager_builder,
            )

        manager = result.manager
        assert isinstance(manager, FakeManager)
        self.assertIsNotNone(get_registered_operator_live_runtime_producer())

        first = stop_operator_live_runtime(manager)
        self.assertEqual(manager.shutdown_count, 1)
        self.assertEqual(first.state, "shutdown")
        self.assertIsNone(get_registered_operator_live_runtime_producer())

        second = stop_operator_live_runtime(manager)
        self.assertEqual(manager.shutdown_count, 2)
        self.assertEqual(second.state, "shutdown")
        self.assertIsNone(get_registered_operator_live_runtime_producer())

    def test_launcher_uses_final_target_contracts_when_config_omits(self) -> None:
        captured: dict[str, SchwabStreamManagerConfig] = {}

        def manager_builder(cfg: SchwabStreamManagerConfig, real_client: object) -> FakeManager:
            captured["config"] = cfg
            return FakeManager(cfg, real_client)

        with patch.dict(
            os.environ,
            {"NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME},
            clear=True,
        ):
            result = start_operator_live_runtime(
                client_factory=lambda cfg: FakeSchwabClient(),
                manager_builder=manager_builder,
            )

        config = captured["config"]
        self.assertEqual(config.contracts_requested, ("ES", "NQ", "CL", "6E", "MGC"))
        self.assertEqual(result.started_snapshot.config.contracts_requested, ("ES", "NQ", "CL", "6E", "MGC"))
        self.assertNotIn("ZN", config.contracts_requested)
        self.assertNotIn("GC", config.contracts_requested)
        self.assertTrue(config.explicit_live_opt_in)

    def test_default_pytest_run_requires_no_schwab_credentials(self) -> None:
        sentinel = _Sentinel()

        with patch.dict(os.environ, {}, clear=True):
            producer = build_operator_runtime_snapshot_producer_from_env()
            self.assertIsNone(producer)

            with self.assertRaises(OperatorLiveRuntimeOptInRequired):
                start_operator_live_runtime(
                    client_factory=sentinel,
                    config=_live_config(),
                    manager_builder=sentinel,
                )

        self.assertEqual(sentinel.call_count, 0)
        for key in os.environ:
            self.assertFalse(
                key.startswith("SCHWAB_"),
                msg="default test run must not set Schwab credential env vars",
            )


if __name__ == "__main__":
    unittest.main()
