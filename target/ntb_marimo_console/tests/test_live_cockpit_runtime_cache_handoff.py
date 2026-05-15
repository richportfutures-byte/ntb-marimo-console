"""Regression tests: live cockpit runtime cache handoff.

These tests pin the contract that under explicit ``OPERATOR_LIVE_RUNTIME``
opt-in:

- A valid runtime/cache/snapshot makes the live-observation cockpit consume
  the runtime cache (mode=``live_observation_runtime_cache``) instead of
  rendering ``live_observation_fail_closed``.
- A missing/failed live runtime surfaces a CONCRETE sanitized lifecycle
  blocker (``operator_live_runtime_not_started``,
  ``operator_live_runtime_opt_in_required``,
  ``live_cockpit_client_factory_unavailable``,
  ``live_cockpit_runtime_start_failed:...``,
  ``operator_live_runtime_producer_error:...``) rather than a generic
  unavailable placeholder; that lifecycle blocker takes precedence over the
  underlying fixture trigger reason in per-row ``query_reason`` and is
  surfaced in the live-observation cockpit banner subtitle.
- ``refresh_runtime_snapshot`` honestly reports unavailable/error/degraded
  instead of always claiming ``REFRESHED`` when no cache is observable.
- Live runtime started but data stale/missing remains blocked on freshness,
  not on runtime-cache-unavailable.
- Display/view-model code does not invent ``QUERY_READY`` from active
  identity alone — chart/quote freshness gates remain fail-closed.
- The 474dfb7 fixture-leakage fix is preserved (no PROVIDER fixture / STREAM
  fixture / Runtime Mode Fixture/Demo under OPERATOR_LIVE_RUNTIME).
"""

from __future__ import annotations

import unittest

from ntb_marimo_console.contract_universe import final_target_contracts
from ntb_marimo_console.launch_config import attach_launch_metadata
from ntb_marimo_console.market_data.stream_cache import StreamCacheRecord, StreamCacheSnapshot
from ntb_marimo_console.market_data.stream_manager import (
    SchwabStreamManagerConfig,
    StreamManagerSnapshot,
)
from ntb_marimo_console.operator_live_runtime import (
    OPERATOR_LIVE_RUNTIME,
    LIVE_RUNTIME_ERROR,
    LIVE_RUNTIME_UNAVAILABLE,
    StaticRuntimeSnapshotProducer,
    UnavailableRuntimeSnapshotProducer,
    resolve_operator_runtime_snapshot,
)
from ntb_marimo_console.primary_cockpit import (
    LIVE_OBSERVATION_COCKPIT_SURFACE_KEY,
    LIVE_OBSERVATION_MODE_CONNECTED,
    LIVE_OBSERVATION_MODE_FAIL_CLOSED,
    PRIMARY_COCKPIT_SURFACE_KEY_FIELD,
    build_live_observation_cockpit_surface,
)
from ntb_marimo_console.readiness_summary import (
    LIVE_RUNTIME_CONNECTED,
    build_five_contract_readiness_summary_surface,
)
from ntb_marimo_console.runtime_diagnostics import LaunchRequest, build_preflight_report
from ntb_marimo_console.runtime_profiles import get_runtime_profile
from ntb_marimo_console.session_lifecycle import (
    SessionLifecycle,
    refresh_runtime_snapshot,
)
from ntb_marimo_console.session_lifecycle import (
    load_session_lifecycle_from_env,
)


NOW = "2026-05-15T14:00:00+00:00"

RUNTIME_SYMBOL_BY_CONTRACT: dict[str, str] = {
    "ES": "/ESM26",
    "NQ": "/NQM26",
    "CL": "/CLM26",
    "6E": "/6EM26",
    "MGC": "/MGCM26",
}


def _complete_levelone_fields(index: int = 0) -> tuple[tuple[str, object], ...]:
    return (
        ("bid", 100.0 + index),
        ("ask", 100.25 + index),
        ("last", 100.125 + index),
        ("bid_size", 10 + index),
        ("ask_size", 12 + index),
        ("quote_time", NOW),
        ("trade_time", NOW),
        ("volume", 25_000 + index),
        ("open", 99.5 + index),
        ("high", 101.0 + index),
        ("low", 98.75 + index),
        ("prior_close", 99.25 + index),
        ("tradable", True),
        ("active", True),
        ("security_status", "Normal"),
    )


def _quote_record(
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
        fields=fields or _complete_levelone_fields(),
        updated_at=NOW,
        age_seconds=0.0 if fresh else 30.0,
        fresh=fresh,
        blocking_reasons=(),
    )


def _cache_snapshot(
    *,
    provider_status: str = "active",
    contracts: tuple[str, ...] = ("ES", "NQ", "CL", "6E", "MGC"),
    blocking_reasons: tuple[str, ...] = (),
    replacement_records: tuple[StreamCacheRecord, ...] = (),
) -> StreamCacheSnapshot:
    replacements = {record.contract: record for record in replacement_records}
    records = tuple(
        replacements.get(contract, _quote_record(contract)) for contract in contracts
    )
    return StreamCacheSnapshot(
        generated_at=NOW,
        provider="schwab",
        provider_status=provider_status,  # type: ignore[arg-type]
        cache_max_age_seconds=15.0,
        records=records,
        blocking_reasons=blocking_reasons,
        stale_symbols=(),
    )


def _active_heartbeats(contracts: tuple[str, ...]) -> dict:
    return {
        contract: {"last_seen": NOW, "age_seconds": 0.0, "status": "active"}
        for contract in contracts
    }


def _active_service_status(
    contracts: tuple[str, ...],
    services: tuple[str, ...] = ("LEVELONE_FUTURES", "CHART_FUTURES"),
) -> dict:
    return {
        contract: {
            service: {"last_seen": NOW, "age_seconds": 0.0, "status": "active"}
            for service in services
        }
        for contract in contracts
    }


def _stream_manager_snapshot(
    *,
    state: str = "active",
    cache: StreamCacheSnapshot | None = None,
    services: tuple[str, ...] = ("LEVELONE_FUTURES", "CHART_FUTURES"),
) -> StreamManagerSnapshot:
    contracts = final_target_contracts()
    return StreamManagerSnapshot(
        state=state,  # type: ignore[arg-type]
        config=SchwabStreamManagerConfig(
            provider="schwab",
            explicit_live_opt_in=True,
            contracts_requested=contracts,
            services_requested=services,
        ),
        cache=cache if cache is not None else _cache_snapshot(),
        events=(),
        blocking_reasons=(),
        login_count=1,
        subscription_count=1,
        last_heartbeat_at=NOW,
        heartbeat_age_seconds=0.0,
        contract_heartbeat_status=_active_heartbeats(contracts),
        contract_service_status=_active_service_status(contracts, services),
    )


class _FailingProducer:
    reason = "live_cockpit_runtime_start_failed:ConnectionError"

    def read_snapshot(self):  # noqa: ANN201 - matches Protocol
        return None


def _preflight_report():
    request = LaunchRequest(
        mode="preserved_engine",
        profile=get_runtime_profile("preserved_es_phase1"),
        lockout=False,
        fixtures_root=None,
        adapter_binding=None,
    )
    return build_preflight_report(request)


def _attach(shell, operator_runtime):
    return attach_launch_metadata(shell, _preflight_report(), operator_runtime=operator_runtime)


class ProducerReasonPropagationTests(unittest.TestCase):
    def test_unavailable_producer_propagates_concrete_lifecycle_reason(self) -> None:
        for producer_reason in (
            "operator_live_runtime_opt_in_required",
            "live_cockpit_client_factory_unavailable",
            "live_cockpit_client_factory_error:KeyError",
            "live_cockpit_runtime_start_failed:OperatorLiveRuntimeStartError",
        ):
            with self.subTest(producer_reason=producer_reason):
                producer = UnavailableRuntimeSnapshotProducer(reason=producer_reason)
                result = resolve_operator_runtime_snapshot(
                    mode=OPERATOR_LIVE_RUNTIME, producer=producer
                )

                self.assertEqual(result.status, LIVE_RUNTIME_UNAVAILABLE)
                self.assertIn(producer_reason, result.blocking_reasons)
                # Generic placeholder must not be the only reason surfaced.
                self.assertNotEqual(
                    result.blocking_reasons,
                    ("operator_live_runtime_snapshot_unavailable",),
                )

    def test_no_producer_returns_concrete_not_started_reason(self) -> None:
        result = resolve_operator_runtime_snapshot(mode=OPERATOR_LIVE_RUNTIME)
        self.assertIn("operator_live_runtime_not_started", result.blocking_reasons)


class LiveObservationCockpitConsumesActiveCacheTests(unittest.TestCase):
    def test_active_runtime_cache_renders_live_mode_not_fail_closed(self) -> None:
        operator_runtime = resolve_operator_runtime_snapshot(
            mode=OPERATOR_LIVE_RUNTIME,
            producer=StaticRuntimeSnapshotProducer(_stream_manager_snapshot()),
        )
        readiness_surface = build_five_contract_readiness_summary_surface(
            runtime_snapshot=operator_runtime.snapshot,
        )
        cockpit = build_live_observation_cockpit_surface(
            readiness_summary=readiness_surface,
            operator_live_runtime=operator_runtime.to_dict(),
        )

        self.assertEqual(readiness_surface["live_runtime_readiness_status"], LIVE_RUNTIME_CONNECTED)
        self.assertEqual(cockpit["mode"], LIVE_OBSERVATION_MODE_CONNECTED)
        # cockpit reads the raw operator_runtime.cache_provider_status which
        # is the manager's "active" label (normalised separately by the
        # readiness summary as "connected" via observable_snapshot).
        self.assertEqual(cockpit["runtime_provider_status"], "active")
        self.assertEqual(readiness_surface["runtime_cache_provider_status"], "connected")
        for row in cockpit["rows"]:
            with self.subTest(contract=row["contract"]):
                self.assertEqual(row["live_runtime_readiness_state"], LIVE_RUNTIME_CONNECTED)


class LifecycleBlockerSurfacedTests(unittest.TestCase):
    def test_unavailable_runtime_surfaces_lifecycle_blocker_in_cockpit(self) -> None:
        producer = UnavailableRuntimeSnapshotProducer(
            reason="live_cockpit_client_factory_unavailable"
        )
        operator_runtime = resolve_operator_runtime_snapshot(
            mode=OPERATOR_LIVE_RUNTIME, producer=producer
        )
        readiness_surface = build_five_contract_readiness_summary_surface(
            runtime_snapshot=operator_runtime.snapshot,
        )
        cockpit = build_live_observation_cockpit_surface(
            readiness_summary=readiness_surface,
            operator_live_runtime=operator_runtime.to_dict(),
        )

        self.assertEqual(cockpit["mode"], LIVE_OBSERVATION_MODE_FAIL_CLOSED)
        # Lifecycle blocker is surfaced in the cockpit-level field.
        self.assertIn(
            "live_cockpit_client_factory_unavailable",
            cockpit["live_runtime_blocking_reasons"],
        )
        # Per-row query_reason prioritizes the lifecycle blocker over residual
        # fixture/trigger reasons.
        for row in cockpit["rows"]:
            with self.subTest(contract=row["contract"]):
                self.assertIn(
                    "live_cockpit_client_factory_unavailable",
                    row["blocking_reasons"],
                )
                self.assertIn(
                    "live cockpit client factory unavailable",
                    row["query_reason"],
                )
                # No display/view-model invention of QUERY_READY.
                self.assertFalse(row["query_enabled"])
                self.assertEqual(row["query_action_state"], "DISABLED")

    def test_producer_error_surfaces_concrete_error_reason_in_cockpit(self) -> None:
        class _RaisingProducer:
            def read_snapshot(self):  # noqa: ANN201 - matches Protocol
                raise RuntimeError("subscription_not_confirmed")

        operator_runtime = resolve_operator_runtime_snapshot(
            mode=OPERATOR_LIVE_RUNTIME, producer=_RaisingProducer()
        )
        readiness_surface = build_five_contract_readiness_summary_surface(
            runtime_snapshot=operator_runtime.snapshot,
        )
        cockpit = build_live_observation_cockpit_surface(
            readiness_summary=readiness_surface,
            operator_live_runtime=operator_runtime.to_dict(),
        )

        self.assertEqual(operator_runtime.status, LIVE_RUNTIME_ERROR)
        self.assertIn(
            "operator_live_runtime_producer_error:RuntimeError",
            cockpit["live_runtime_blocking_reasons"],
        )
        for row in cockpit["rows"]:
            with self.subTest(contract=row["contract"]):
                self.assertIn(
                    "operator_live_runtime_producer_error:RuntimeError",
                    row["blocking_reasons"],
                )


class StaleDataKeepsRowFreshnessBlockerTests(unittest.TestCase):
    def test_partial_quote_blocks_per_row_not_runtime_unavailable(self) -> None:
        partial = _quote_record("CL", fields=(("quote_time", NOW),))
        snapshot = _stream_manager_snapshot(
            cache=_cache_snapshot(replacement_records=(partial,)),
        )
        operator_runtime = resolve_operator_runtime_snapshot(
            mode=OPERATOR_LIVE_RUNTIME,
            producer=StaticRuntimeSnapshotProducer(snapshot),
        )
        readiness_surface = build_five_contract_readiness_summary_surface(
            runtime_snapshot=operator_runtime.snapshot,
        )
        cockpit = build_live_observation_cockpit_surface(
            readiness_summary=readiness_surface,
            operator_live_runtime=operator_runtime.to_dict(),
        )

        # Stream identity remains active; CL is the only blocked row.
        self.assertTrue(readiness_surface["runtime_stream_active"])
        cl_row = next(row for row in cockpit["rows"] if row["contract"] == "CL")
        es_row = next(row for row in cockpit["rows"] if row["contract"] == "ES")
        # CL row reasons reference required-field-missing, NOT a runtime
        # unavailable lifecycle blocker.
        self.assertTrue(
            any("missing_required_fields" in reason for reason in cl_row["blocking_reasons"])
            or "bid" in (cl_row.get("blocking_reasons") or [])
        )
        self.assertNotIn(
            "operator_live_runtime_not_started", cl_row["blocking_reasons"]
        )
        # ES (with full quote) shows no stream lifecycle blocker either.
        self.assertNotIn(
            "operator_live_runtime_not_started", es_row["blocking_reasons"]
        )


class RuntimeRefreshHonestReportingTests(unittest.TestCase):
    def _live_lifecycle(self, *, producer) -> SessionLifecycle:
        # Build a session lifecycle wired to the supplied producer in the
        # explicit OPERATOR_LIVE_RUNTIME mode.
        return load_session_lifecycle_from_env(
            default_mode="fixture_demo",
            runtime_snapshot_producer=producer,
            operator_runtime_mode=OPERATOR_LIVE_RUNTIME,
        )

    def test_refresh_with_active_runtime_reports_refreshed(self) -> None:
        lifecycle = self._live_lifecycle(
            producer=StaticRuntimeSnapshotProducer(_stream_manager_snapshot())
        )
        refreshed = refresh_runtime_snapshot(lifecycle)
        latest = refreshed.operator_action_timeline[-1]
        self.assertEqual(latest.action_kind, "RUNTIME_REFRESH")
        self.assertEqual(latest.action_status, "REFRESHED")

    def test_refresh_with_unavailable_runtime_reports_blocked(self) -> None:
        producer = UnavailableRuntimeSnapshotProducer(
            reason="live_cockpit_runtime_start_failed:ConnectionError"
        )
        lifecycle = self._live_lifecycle(producer=producer)
        refreshed = refresh_runtime_snapshot(lifecycle)
        latest = refreshed.operator_action_timeline[-1]
        self.assertEqual(latest.action_status, "REFRESH_BLOCKED")
        self.assertIn("live_cockpit_runtime_start_failed:ConnectionError", latest.action_text)
        self.assertEqual(
            latest.blocked_reason, "live_cockpit_runtime_start_failed:ConnectionError"
        )

    def test_refresh_with_producer_raising_reports_blocked_error(self) -> None:
        class _RaisingProducer:
            def read_snapshot(self):  # noqa: ANN201
                raise RuntimeError("receive_worker_not_running")

        lifecycle = self._live_lifecycle(producer=_RaisingProducer())
        refreshed = refresh_runtime_snapshot(lifecycle)
        latest = refreshed.operator_action_timeline[-1]
        self.assertEqual(latest.action_status, "REFRESH_BLOCKED")
        self.assertIn(
            "operator_live_runtime_producer_error:RuntimeError", latest.action_text
        )

    def test_safe_non_live_refresh_remains_unchanged(self) -> None:
        lifecycle = load_session_lifecycle_from_env(
            default_mode="fixture_demo",
        )
        refreshed = refresh_runtime_snapshot(lifecycle)
        latest = refreshed.operator_action_timeline[-1]
        self.assertEqual(latest.action_status, "REFRESHED")
        self.assertIsNone(latest.blocked_reason)


class ManualQueryBlockerPriorityTests(unittest.TestCase):
    def test_runtime_lifecycle_reason_outranks_trigger_state_in_per_row(self) -> None:
        producer = UnavailableRuntimeSnapshotProducer(
            reason="operator_live_runtime_not_started"
        )
        operator_runtime = resolve_operator_runtime_snapshot(
            mode=OPERATOR_LIVE_RUNTIME, producer=producer
        )
        readiness_surface = build_five_contract_readiness_summary_surface(
            runtime_snapshot=operator_runtime.snapshot,
        )
        # The first per-row blocked reason must be the runtime lifecycle one,
        # not the underlying fixture trigger reason.
        for row in readiness_surface["rows"]:
            with self.subTest(contract=row["contract"]):
                self.assertTrue(row["primary_blocked_reasons"])
                first = row["primary_blocked_reasons"][0]
                self.assertNotIn("trigger_state_not_query_ready", first)


class FixtureLeakageStillFixedUnderLiveTests(unittest.TestCase):
    def test_no_fixture_provider_or_stream_labels_under_operator_live_runtime(self) -> None:
        operator_runtime = resolve_operator_runtime_snapshot(
            mode=OPERATOR_LIVE_RUNTIME,
            producer=StaticRuntimeSnapshotProducer(_stream_manager_snapshot()),
        )
        shell: dict[str, object] = {
            "surfaces": {},
            "r14_cockpit": {
                "runtime_status": {"provider_status": "fixture", "stream_status": "fixture"}
            },
        }
        _attach(shell, operator_runtime)
        startup = shell["startup"]
        runtime_status = shell["r14_cockpit"]["runtime_status"]
        self.assertEqual(startup["runtime_mode_label"], "Live-Observation")
        self.assertEqual(startup["running_as"], "Live-Observation")
        self.assertNotEqual(runtime_status["provider_status"], "fixture")
        self.assertNotEqual(runtime_status["stream_status"], "fixture")
        # Primary cockpit is the live-observation surface.
        self.assertEqual(
            shell[PRIMARY_COCKPIT_SURFACE_KEY_FIELD],
            LIVE_OBSERVATION_COCKPIT_SURFACE_KEY,
        )


if __name__ == "__main__":
    unittest.main()
