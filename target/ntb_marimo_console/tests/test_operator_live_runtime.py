from __future__ import annotations

import os
import unittest
from dataclasses import dataclass
from unittest.mock import patch

from ntb_marimo_console.contract_universe import final_target_contracts
from ntb_marimo_console.launch_config import build_startup_artifacts_from_env
from ntb_marimo_console.market_data.stream_cache import StreamCacheRecord, StreamCacheSnapshot
from ntb_marimo_console.market_data.stream_manager import (
    MIN_STREAM_REFRESH_FLOOR_SECONDS,
    SchwabStreamManagerConfig,
    StreamManagerSnapshot,
)
from ntb_marimo_console.operator_live_runtime import (
    LIVE_RUNTIME_DISABLED,
    LIVE_RUNTIME_ERROR,
    LIVE_RUNTIME_STALE,
    LIVE_RUNTIME_UNAVAILABLE,
    OPERATOR_LIVE_RUNTIME,
    SAFE_NON_LIVE,
    StreamManagerRuntimeSnapshotProducer,
    UnavailableRuntimeSnapshotProducer,
    build_operator_runtime_snapshot_producer_from_env,
    clear_operator_live_runtime_registration,
    get_registered_operator_live_runtime_producer,
    register_operator_live_runtime_manager,
    register_operator_live_runtime_producer,
    resolve_operator_runtime_snapshot,
)
from ntb_marimo_console.readiness_summary import (
    LIVE_RUNTIME_CONNECTED,
    READINESS_SOURCE_FIXTURE_PRESERVED,
    READINESS_SOURCE_RUNTIME_CACHE,
)
from ntb_marimo_console.session_lifecycle import (
    load_session_lifecycle_from_env,
    refresh_runtime_snapshot,
    reload_current_profile,
    request_query_action,
    reset_session,
)


NOW = "2026-05-06T14:00:00+00:00"
RUNTIME_SYMBOL_BY_CONTRACT = {
    "ES": "/ESM26",
    "NQ": "/NQM26",
    "CL": "/CLM26",
    "6E": "/6EM26",
    "MGC": "/MGCM26",
    "ZN": "/ZNM26",
    "GC": "/GCM26",
}


def runtime_record(
    contract: str,
    *,
    fields: tuple[tuple[str, object], ...] | None = None,
    fresh: bool = True,
) -> StreamCacheRecord:
    return StreamCacheRecord(
        provider="schwab",
        service="LEVELONE_FUTURES",
        symbol=RUNTIME_SYMBOL_BY_CONTRACT[contract],
        contract=contract,
        message_type="quote",
        fields=fields
        or (
            ("bid", 100.0),
            ("ask", 100.25),
            ("last", 100.125),
            ("bid_size", 10),
            ("ask_size", 12),
            ("quote_time", NOW),
            ("trade_time", NOW),
            ("volume", 25000),
            ("open", 99.5),
            ("high", 101.0),
            ("low", 98.75),
            ("prior_close", 99.25),
            ("tradable", True),
            ("active", True),
            ("security_status", "Normal"),
        ),
        updated_at=NOW,
        age_seconds=0.0 if fresh else 30.0,
        fresh=fresh,
        blocking_reasons=(),
    )


def runtime_cache_snapshot(
    *,
    provider_status: str = "active",
    contracts: tuple[str, ...] = ("ES", "NQ", "CL", "6E", "MGC"),
    replacement_records: tuple[StreamCacheRecord, ...] = (),
    extra_records: tuple[StreamCacheRecord, ...] = (),
    blocking_reasons: tuple[str, ...] = (),
    stale_symbols: tuple[str, ...] = (),
) -> StreamCacheSnapshot:
    replacements = {record.contract: record for record in replacement_records}
    records = tuple(replacements.get(contract, runtime_record(contract)) for contract in contracts)
    return StreamCacheSnapshot(
        generated_at=NOW,
        provider="schwab",
        provider_status=provider_status,  # type: ignore[arg-type]
        cache_max_age_seconds=15.0,
        records=records + extra_records,
        blocking_reasons=blocking_reasons,
        stale_symbols=stale_symbols,
    )


@dataclass
class CountingProducer:
    snapshots: list[StreamCacheSnapshot | None]
    read_count: int = 0

    def read_snapshot(self) -> StreamCacheSnapshot | None:
        self.read_count += 1
        if not self.snapshots:
            return None
        if len(self.snapshots) == 1:
            return self.snapshots[0]
        return self.snapshots.pop(0)


class FailingProducer:
    def read_snapshot(self) -> StreamCacheSnapshot | None:
        raise RuntimeError("token=should_not_print")


class FakeStartedManager:
    def __init__(self, snapshot: StreamManagerSnapshot) -> None:
        self._snapshot = snapshot
        self.snapshot_count = 0
        self.start_count = 0

    def start(self) -> StreamManagerSnapshot:
        self.start_count += 1
        raise AssertionError("start_must_not_be_called_from_marimo_refresh")

    def snapshot(self) -> StreamManagerSnapshot:
        self.snapshot_count += 1
        return self._snapshot


class OperatorLiveRuntimeTests(unittest.TestCase):
    def test_safe_non_live_mode_does_not_request_runtime_snapshot(self) -> None:
        result = resolve_operator_runtime_snapshot(mode=SAFE_NON_LIVE)

        self.assertEqual(result.mode, SAFE_NON_LIVE)
        self.assertEqual(result.status, SAFE_NON_LIVE)
        self.assertFalse(result.requested_live_runtime)
        self.assertFalse(result.runtime_cache_derived)
        self.assertIsNone(result.snapshot)
        self.assertEqual(result.refresh_floor_seconds, MIN_STREAM_REFRESH_FLOOR_SECONDS)

    def test_operator_live_runtime_reads_connected_producer_snapshot(self) -> None:
        snapshot = runtime_cache_snapshot()
        producer = CountingProducer([snapshot])

        result = resolve_operator_runtime_snapshot(
            mode=OPERATOR_LIVE_RUNTIME,
            producer=producer,
        )

        self.assertEqual(producer.read_count, 1)
        self.assertEqual(result.status, OPERATOR_LIVE_RUNTIME)
        self.assertIs(result.snapshot, snapshot)
        self.assertTrue(result.runtime_cache_derived)
        self.assertEqual(result.cache_provider_status, "active")

    def test_stream_manager_producer_reads_snapshot_without_starting_manager(self) -> None:
        snapshot = StreamManagerSnapshot(
            state="active",
            config=SchwabStreamManagerConfig(
                provider="schwab",
                explicit_live_opt_in=True,
                contracts_requested=final_target_contracts(),
            ),
            cache=runtime_cache_snapshot(),
            events=(),
            blocking_reasons=(),
            login_count=1,
            subscription_count=1,
        )
        manager = FakeStartedManager(snapshot)

        result = resolve_operator_runtime_snapshot(
            mode=OPERATOR_LIVE_RUNTIME,
            producer=StreamManagerRuntimeSnapshotProducer(manager),
        )

        self.assertEqual(manager.snapshot_count, 1)
        self.assertEqual(manager.start_count, 0)
        self.assertIs(result.snapshot, snapshot)
        self.assertEqual(result.status, OPERATOR_LIVE_RUNTIME)

    def test_operator_live_runtime_unavailable_blocks_without_fixture_fallback(self) -> None:
        result = resolve_operator_runtime_snapshot(mode=OPERATOR_LIVE_RUNTIME)

        self.assertEqual(result.status, LIVE_RUNTIME_UNAVAILABLE)
        self.assertTrue(result.requested_live_runtime)
        self.assertIsNotNone(result.snapshot)
        self.assertIn("operator_live_runtime_snapshot_unavailable", result.blocking_reasons)

    def test_operator_live_runtime_disabled_stale_and_error_states_block(self) -> None:
        cases = (
            ("disabled", LIVE_RUNTIME_DISABLED),
            ("stale", LIVE_RUNTIME_STALE),
            ("error", LIVE_RUNTIME_ERROR),
        )

        for provider_status, expected_status in cases:
            with self.subTest(provider_status=provider_status):
                result = resolve_operator_runtime_snapshot(
                    mode=OPERATOR_LIVE_RUNTIME,
                    producer=CountingProducer([runtime_cache_snapshot(provider_status=provider_status)]),
                )

                self.assertEqual(result.status, expected_status)
                self.assertTrue(result.runtime_cache_derived)
                self.assertIsNotNone(result.snapshot)

    def test_operator_live_runtime_producer_error_is_sanitized_and_blocks(self) -> None:
        result = resolve_operator_runtime_snapshot(
            mode=OPERATOR_LIVE_RUNTIME,
            producer=FailingProducer(),
        )

        self.assertEqual(result.status, LIVE_RUNTIME_ERROR)
        self.assertIn("operator_live_runtime_producer_error:RuntimeError", result.blocking_reasons)
        self.assertNotIn("should_not_print", result.producer_error or "")
        self.assertIn("[REDACTED]", result.producer_error or "")

    def test_startup_artifacts_inject_runtime_producer_into_readiness_summary(self) -> None:
        producer = CountingProducer([runtime_cache_snapshot()])

        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            artifacts = build_startup_artifacts_from_env(
                runtime_snapshot_producer=producer,
                operator_runtime_mode=OPERATOR_LIVE_RUNTIME,
            )

        summary = artifacts.shell["surfaces"]["five_contract_readiness_summary"]
        runtime = artifacts.shell["runtime"]
        self.assertEqual(producer.read_count, 1)
        self.assertEqual(artifacts.operator_runtime.status, OPERATOR_LIVE_RUNTIME)
        self.assertEqual(summary["readiness_source"], READINESS_SOURCE_RUNTIME_CACHE)
        self.assertEqual(summary["live_runtime_readiness_status"], LIVE_RUNTIME_CONNECTED)
        self.assertEqual(runtime["operator_live_runtime_status"], OPERATOR_LIVE_RUNTIME)
        self.assertTrue(runtime["operator_live_runtime_cache_derived"])
        self.assertEqual(summary["rows"][0]["runtime_cache_status"], "runtime_cache_connected")
        self.assertEqual(summary["rows"][0]["quote_status"], "quote available")
        self.assertEqual(summary["rows"][0]["chart_status"], "chart missing")
        self.assertFalse(summary["rows"][0]["query_ready"])

    def test_missing_live_snapshot_does_not_imply_live_readiness_or_fixture_fallback(self) -> None:
        with patch.dict(os.environ, {"NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME}, clear=True):
            artifacts = build_startup_artifacts_from_env()

        summary = artifacts.shell["surfaces"]["five_contract_readiness_summary"]
        self.assertEqual(artifacts.operator_runtime.status, LIVE_RUNTIME_UNAVAILABLE)
        self.assertEqual(summary["readiness_source"], READINESS_SOURCE_RUNTIME_CACHE)
        self.assertTrue(summary["runtime_cache_bound_to_operator_launch"])
        self.assertFalse(summary["runtime_cache_snapshot_ready"])
        self.assertNotEqual(summary["readiness_source"], READINESS_SOURCE_FIXTURE_PRESERVED)
        for row in summary["rows"]:
            self.assertFalse(row["non_live_fixture_usable"])
            self.assertFalse(row["query_ready"])

    def test_safe_non_live_startup_remains_fixture_preserved_shell(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            artifacts = build_startup_artifacts_from_env()

        summary = artifacts.shell["surfaces"]["five_contract_readiness_summary"]
        self.assertEqual(artifacts.operator_runtime.status, SAFE_NON_LIVE)
        self.assertEqual(summary["readiness_source"], READINESS_SOURCE_FIXTURE_PRESERVED)
        self.assertFalse(summary["runtime_cache_bound_to_operator_launch"])
        self.assertFalse(artifacts.shell["runtime"]["operator_live_runtime_requested"])

    def test_lifecycle_refreshes_runtime_snapshot_from_same_producer_without_fallback(self) -> None:
        producer = CountingProducer(
            [
                runtime_cache_snapshot(),
                runtime_cache_snapshot(provider_status="disabled"),
                runtime_cache_snapshot(provider_status="stale"),
            ]
        )

        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env(
                runtime_snapshot_producer=producer,
                operator_runtime_mode=OPERATOR_LIVE_RUNTIME,
            )
            queried = request_query_action(lifecycle)
            refreshed = reload_current_profile(queried)

        self.assertEqual(producer.read_count, 3)
        self.assertIs(lifecycle.runtime_snapshot_producer, producer)
        self.assertIs(queried.runtime_snapshot_producer, producer)
        self.assertIs(refreshed.runtime_snapshot_producer, producer)
        self.assertEqual(
            lifecycle.shell["surfaces"]["five_contract_readiness_summary"]["live_runtime_readiness_status"],
            LIVE_RUNTIME_CONNECTED,
        )
        self.assertEqual(
            queried.shell["surfaces"]["five_contract_readiness_summary"]["readiness_source"],
            READINESS_SOURCE_RUNTIME_CACHE,
        )
        self.assertFalse(
            queried.shell["surfaces"]["five_contract_readiness_summary"]["rows"][0]["non_live_fixture_usable"]
        )
        self.assertEqual(
            refreshed.shell["runtime"]["operator_live_runtime_status"],
            LIVE_RUNTIME_STALE,
        )

    def test_reset_reads_latest_runtime_snapshot_without_creating_second_producer(self) -> None:
        producer = CountingProducer([runtime_cache_snapshot(), runtime_cache_snapshot(provider_status="disabled")])

        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env(
                runtime_snapshot_producer=producer,
                operator_runtime_mode=OPERATOR_LIVE_RUNTIME,
            )
            reset = reset_session(lifecycle)

        self.assertEqual(producer.read_count, 2)
        self.assertIs(reset.runtime_snapshot_producer, producer)
        self.assertEqual(reset.shell["runtime"]["operator_live_runtime_status"], LIVE_RUNTIME_DISABLED)
        self.assertEqual(
            reset.shell["surfaces"]["five_contract_readiness_summary"]["readiness_source"],
            READINESS_SOURCE_RUNTIME_CACHE,
        )

    def test_marimo_refresh_reads_latest_snapshot_without_recording_evidence(self) -> None:
        producer = CountingProducer([runtime_cache_snapshot(), runtime_cache_snapshot(provider_status="disabled")])

        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env(
                runtime_snapshot_producer=producer,
                operator_runtime_mode=OPERATOR_LIVE_RUNTIME,
            )
            refreshed = refresh_runtime_snapshot(lifecycle)

        self.assertEqual(producer.read_count, 2)
        self.assertIs(refreshed.runtime_snapshot_producer, producer)
        self.assertEqual(refreshed.shell["runtime"]["operator_live_runtime_status"], LIVE_RUNTIME_DISABLED)
        self.assertEqual(
            refreshed.shell["surfaces"]["five_contract_readiness_summary"]["readiness_source"],
            READINESS_SOURCE_RUNTIME_CACHE,
        )
        self.assertEqual(len(refreshed.evidence_history), len(lifecycle.evidence_history))

    def test_final_targets_and_exclusions_are_preserved_for_runtime_producer_input(self) -> None:
        snapshot = runtime_cache_snapshot(extra_records=(runtime_record("ZN"), runtime_record("GC")))
        producer = CountingProducer([snapshot])

        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            artifacts = build_startup_artifacts_from_env(
                runtime_snapshot_producer=producer,
                operator_runtime_mode=OPERATOR_LIVE_RUNTIME,
            )

        summary = artifacts.shell["surfaces"]["five_contract_readiness_summary"]
        rows = summary["rows"]
        self.assertEqual(tuple(row["contract"] for row in rows), final_target_contracts())
        self.assertEqual(tuple(row["contract"] for row in rows), ("ES", "NQ", "CL", "6E", "MGC"))
        self.assertNotIn("ZN", [row["contract"] for row in rows])
        self.assertNotIn("GC", [row["contract"] for row in rows])
        mgc = next(row for row in rows if row["contract"] == "MGC")
        self.assertEqual(mgc["contract_label"], "Micro Gold")
        self.assertNotEqual(mgc["contract_label"], "GC")


class CountingFactory:
    def __init__(self, manager: object) -> None:
        self._manager = manager
        self.call_count = 0

    def __call__(self) -> object:
        self.call_count += 1
        return self._manager


def _active_manager_snapshot() -> StreamManagerSnapshot:
    return StreamManagerSnapshot(
        state="active",
        config=SchwabStreamManagerConfig(
            provider="schwab",
            explicit_live_opt_in=True,
            contracts_requested=final_target_contracts(),
        ),
        cache=runtime_cache_snapshot(),
        events=(),
        blocking_reasons=(),
        login_count=1,
        subscription_count=1,
    )


class BuilderInjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        clear_operator_live_runtime_registration()
        self.addCleanup(clear_operator_live_runtime_registration)

    def test_builder_kwarg_manager_returns_stream_manager_producer_in_live_mode(self) -> None:
        manager = FakeStartedManager(_active_manager_snapshot())
        env = {"NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME}

        producer = build_operator_runtime_snapshot_producer_from_env(env, manager=manager)

        self.assertIsInstance(producer, StreamManagerRuntimeSnapshotProducer)
        self.assertIs(producer.manager, manager)
        self.assertEqual(manager.start_count, 0)
        self.assertEqual(manager.snapshot_count, 0)

    def test_builder_kwarg_manager_factory_called_exactly_once(self) -> None:
        manager = FakeStartedManager(_active_manager_snapshot())
        factory = CountingFactory(manager)
        env = {"NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME}

        producer = build_operator_runtime_snapshot_producer_from_env(env, manager_factory=factory)

        self.assertEqual(factory.call_count, 1)
        self.assertIsInstance(producer, StreamManagerRuntimeSnapshotProducer)
        self.assertIs(producer.manager, manager)
        self.assertEqual(manager.start_count, 0)

    def test_builder_kwarg_producer_takes_precedence_over_manager_and_factory(self) -> None:
        manager = FakeStartedManager(_active_manager_snapshot())
        factory = CountingFactory(FakeStartedManager(_active_manager_snapshot()))
        explicit = CountingProducer([runtime_cache_snapshot()])
        env = {"NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME}

        producer = build_operator_runtime_snapshot_producer_from_env(
            env,
            producer=explicit,
            manager=manager,
            manager_factory=factory,
        )

        self.assertIs(producer, explicit)
        self.assertEqual(factory.call_count, 0)
        self.assertEqual(manager.snapshot_count, 0)

    def test_builder_kwargs_ignored_in_safe_non_live_mode(self) -> None:
        manager = FakeStartedManager(_active_manager_snapshot())
        factory = CountingFactory(FakeStartedManager(_active_manager_snapshot()))

        producer = build_operator_runtime_snapshot_producer_from_env(
            {},
            manager=manager,
            manager_factory=factory,
        )

        self.assertIsNone(producer)
        self.assertEqual(factory.call_count, 0)
        self.assertEqual(manager.snapshot_count, 0)
        self.assertEqual(manager.start_count, 0)

    def test_registered_manager_is_consulted_when_no_kwargs(self) -> None:
        manager = FakeStartedManager(_active_manager_snapshot())
        register_operator_live_runtime_manager(manager)
        env = {"NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME}

        producer = build_operator_runtime_snapshot_producer_from_env(env)

        self.assertIsInstance(producer, StreamManagerRuntimeSnapshotProducer)
        self.assertIs(producer.manager, manager)
        self.assertEqual(manager.start_count, 0)

    def test_registered_producer_overrides_default_unavailable(self) -> None:
        explicit = CountingProducer([runtime_cache_snapshot()])
        register_operator_live_runtime_producer(explicit)
        env = {"NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME}

        producer = build_operator_runtime_snapshot_producer_from_env(env)

        self.assertIs(producer, explicit)
        self.assertIs(get_registered_operator_live_runtime_producer(), explicit)

    def test_kwarg_overrides_registry(self) -> None:
        registered_manager = FakeStartedManager(_active_manager_snapshot())
        register_operator_live_runtime_manager(registered_manager)
        kwarg_manager = FakeStartedManager(_active_manager_snapshot())
        env = {"NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME}

        producer = build_operator_runtime_snapshot_producer_from_env(env, manager=kwarg_manager)

        self.assertIsInstance(producer, StreamManagerRuntimeSnapshotProducer)
        self.assertIs(producer.manager, kwarg_manager)
        self.assertIsNot(producer.manager, registered_manager)
        self.assertEqual(registered_manager.snapshot_count, 0)

    def test_clear_operator_live_runtime_registration_restores_unavailable_default(self) -> None:
        register_operator_live_runtime_manager(FakeStartedManager(_active_manager_snapshot()))
        clear_operator_live_runtime_registration()
        env = {"NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME}

        producer = build_operator_runtime_snapshot_producer_from_env(env)

        self.assertIsInstance(producer, UnavailableRuntimeSnapshotProducer)
        self.assertIsNone(get_registered_operator_live_runtime_producer())

        producer_default = build_operator_runtime_snapshot_producer_from_env({})
        self.assertIsNone(producer_default)

    def test_refresh_path_with_registered_manager_does_not_call_start_login_subscribe(self) -> None:
        manager = FakeStartedManager(_active_manager_snapshot())
        register_operator_live_runtime_manager(manager)

        with patch.dict(
            os.environ,
            {
                "NTB_CONSOLE_PROFILE": "preserved_es_phase1",
                "NTB_OPERATOR_RUNTIME_MODE": OPERATOR_LIVE_RUNTIME,
            },
            clear=True,
        ):
            producer = build_operator_runtime_snapshot_producer_from_env()
            lifecycle = load_session_lifecycle_from_env(
                runtime_snapshot_producer=producer,
                operator_runtime_mode=OPERATOR_LIVE_RUNTIME,
            )
            initial_snapshot_count = manager.snapshot_count
            for _ in range(3):
                lifecycle = refresh_runtime_snapshot(lifecycle)

        self.assertEqual(manager.start_count, 0)
        self.assertEqual(manager.snapshot_count - initial_snapshot_count, 3)
        self.assertEqual(
            lifecycle.shell["runtime"]["operator_live_runtime_status"],
            OPERATOR_LIVE_RUNTIME,
        )

    def test_final_target_contracts_literal_unchanged(self) -> None:
        self.assertEqual(final_target_contracts(), ("ES", "NQ", "CL", "6E", "MGC"))
        self.assertNotIn("ZN", final_target_contracts())
        self.assertNotIn("GC", final_target_contracts())


if __name__ == "__main__":
    unittest.main()
