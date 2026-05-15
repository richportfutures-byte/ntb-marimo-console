"""Regression tests: --live cockpit stream freshness classification.

These tests pin the live cockpit's contradiction fix:

- When the Schwab stream manager reports ``state="active"`` for the explicit
  --live session, the readiness summary's provider/stream classification follows
  the live runtime cache (active/connected) — historical transient reasons such
  as ``stream_not_active`` and ``provider_disconnected`` left over from before
  subscription completed must not flip identity to inactive/disconnected.
- Quote/chart freshness remains independently fail-closed: stale chart bars and
  missing normalized required fields keep blocking ``query_ready`` and the
  per-row chart/quote status, but never downgrade the overall live runtime
  identity.
- The launch metadata overlay rewrites the secondary-section labels under
  OPERATOR_LIVE_RUNTIME so the operator never sees fixture framing
  (``Runtime Mode Fixture/Demo``, ``PROVIDER fixture``, ``STREAM fixture``)
  alongside the live-observation cockpit.
- The display/view-model code never invents ``QUERY_READY``: per-row
  ``query_ready`` only mirrors the upstream gate, and stays ``False`` whenever
  chart freshness or required-field fail-closed checks are active.
"""

from __future__ import annotations

import unittest
from copy import deepcopy

from ntb_marimo_console.contract_universe import final_target_contracts
from ntb_marimo_console.launch_config import attach_launch_metadata
from ntb_marimo_console.market_data.stream_cache import StreamCacheRecord, StreamCacheSnapshot
from ntb_marimo_console.market_data.stream_manager import (
    SchwabStreamManagerConfig,
    StreamManagerSnapshot,
)
from ntb_marimo_console.operator_live_runtime import (
    OPERATOR_LIVE_RUNTIME,
    StaticRuntimeSnapshotProducer,
    resolve_operator_runtime_snapshot,
)
from ntb_marimo_console.primary_cockpit import (
    LIVE_OBSERVATION_COCKPIT_SURFACE_KEY,
    PRIMARY_COCKPIT_SURFACE_KEY_FIELD,
)
from ntb_marimo_console.readiness_summary import (
    LIVE_RUNTIME_CONNECTED,
    READINESS_SOURCE_RUNTIME_CACHE,
    build_five_contract_readiness_summary,
    build_five_contract_readiness_summary_surface,
)
from ntb_marimo_console.runtime_diagnostics import LaunchRequest, build_preflight_report
from ntb_marimo_console.runtime_profiles import get_runtime_profile


NOW = "2026-05-14T14:00:00+00:00"

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
    blocking_reasons: tuple[str, ...] = (),
    contracts: tuple[str, ...] = ("ES", "NQ", "CL", "6E", "MGC"),
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


def _stream_manager_snapshot(
    *,
    state: str = "active",
    cache: StreamCacheSnapshot | None = None,
    blocking_reasons: tuple[str, ...] = (),
) -> StreamManagerSnapshot:
    contracts = final_target_contracts()
    return StreamManagerSnapshot(
        state=state,  # type: ignore[arg-type]
        config=SchwabStreamManagerConfig(
            provider="schwab",
            explicit_live_opt_in=True,
            contracts_requested=contracts,
        ),
        cache=cache if cache is not None else _cache_snapshot(),
        events=(),
        blocking_reasons=blocking_reasons,
        login_count=1,
        subscription_count=1,
        last_heartbeat_at=NOW,
        heartbeat_age_seconds=0.0,
        contract_heartbeat_status=_active_heartbeats(contracts),
    )


class StreamFreshnessClassificationTests(unittest.TestCase):
    def test_stream_manager_snapshot_drives_runtime_cache_source_type(self) -> None:
        summary = build_five_contract_readiness_summary(
            runtime_snapshot=_stream_manager_snapshot(),
        )

        self.assertEqual(summary.runtime_cache_source_type, "stream_manager_snapshot")
        self.assertEqual(summary.readiness_source, READINESS_SOURCE_RUNTIME_CACHE)
        self.assertTrue(summary.runtime_stream_active)
        self.assertEqual(summary.runtime_stream_state, "active")
        self.assertEqual(
            tuple(summary.runtime_stream_active_contracts),
            final_target_contracts(),
        )

    def test_active_stream_classifies_as_connected_with_active_heartbeats(self) -> None:
        surface = build_five_contract_readiness_summary_surface(
            runtime_snapshot=_stream_manager_snapshot(),
        )

        self.assertEqual(surface["live_runtime_readiness_status"], LIVE_RUNTIME_CONNECTED)
        self.assertEqual(surface["runtime_cache_provider_status"], "connected")
        self.assertTrue(surface["runtime_stream_active"])
        for row in surface["rows"]:
            with self.subTest(contract=row["contract"]):
                self.assertEqual(
                    row["live_runtime_readiness_state"], LIVE_RUNTIME_CONNECTED
                )
                self.assertEqual(row["runtime_provider_status"], "connected")

    def test_historical_stream_not_active_reason_does_not_flip_identity(self) -> None:
        # Cache holds a transient ``stream_not_active`` reason from before
        # subscription completed; the manager is now active with green
        # heartbeats. The classification must follow the active manager.
        cache = _cache_snapshot(
            provider_status="active",
            blocking_reasons=("stream_not_active", "provider_disconnected"),
        )
        manager_snapshot = _stream_manager_snapshot(
            cache=cache,
            blocking_reasons=("stream_not_active",),
        )

        surface = build_five_contract_readiness_summary_surface(
            runtime_snapshot=manager_snapshot,
        )

        self.assertEqual(surface["live_runtime_readiness_status"], LIVE_RUNTIME_CONNECTED)
        self.assertEqual(surface["runtime_cache_provider_status"], "connected")
        self.assertTrue(surface["runtime_stream_active"])
        self.assertNotIn("stream_not_active", surface["live_runtime_readiness_blockers"])
        self.assertNotIn("provider_disconnected", surface["live_runtime_readiness_blockers"])
        for row in surface["rows"]:
            with self.subTest(contract=row["contract"]):
                self.assertEqual(
                    row["live_runtime_readiness_state"], LIVE_RUNTIME_CONNECTED
                )
                self.assertNotIn("stream_not_active", row["primary_blocked_reasons"])
                self.assertNotIn("provider_disconnected", row["primary_blocked_reasons"])
                self.assertNotIn("stream_not_active", row["runtime_cache_blocked_reasons"])
                self.assertNotIn("provider_disconnected", row["runtime_cache_blocked_reasons"])

    def test_residual_blocked_provider_status_does_not_override_active_manager(self) -> None:
        # Cache provider_status was last set to ``blocked`` by a transient
        # malformed message; the manager is now active. The active manager
        # must drive the classification, not the residual cache provider_status.
        cache = _cache_snapshot(provider_status="blocked")
        manager_snapshot = _stream_manager_snapshot(cache=cache)

        surface = build_five_contract_readiness_summary_surface(
            runtime_snapshot=manager_snapshot,
        )

        self.assertEqual(surface["live_runtime_readiness_status"], LIVE_RUNTIME_CONNECTED)
        self.assertEqual(surface["runtime_cache_provider_status"], "connected")
        for row in surface["rows"]:
            with self.subTest(contract=row["contract"]):
                self.assertEqual(
                    row["live_runtime_readiness_state"], LIVE_RUNTIME_CONNECTED
                )

    def test_missing_required_fields_still_block_per_row_but_not_identity(self) -> None:
        partial_record = _quote_record("CL", fields=(("quote_time", NOW),))
        manager_snapshot = _stream_manager_snapshot(
            cache=_cache_snapshot(
                provider_status="active",
                replacement_records=(partial_record,),
            ),
        )

        surface = build_five_contract_readiness_summary_surface(
            runtime_snapshot=manager_snapshot,
        )

        # Stream identity stays active even though one contract has
        # incomplete normalized fields.
        self.assertTrue(surface["runtime_stream_active"])
        self.assertEqual(surface["runtime_cache_provider_status"], "connected")

        rows = {row["contract"]: row for row in surface["rows"]}
        cl_row = rows["CL"]
        self.assertIn("bid", cl_row["missing_live_fields"])
        self.assertFalse(cl_row["query_ready"])
        # Other contracts remain healthy.
        self.assertEqual(rows["ES"]["live_runtime_readiness_state"], LIVE_RUNTIME_CONNECTED)
        self.assertTrue(rows["ES"]["query_ready"] is False or rows["ES"]["query_ready"] is True)


class LaunchMetadataLabelOverlayTests(unittest.TestCase):
    def test_live_observation_overlay_overrides_fixture_labels(self) -> None:
        request = LaunchRequest(
            mode="preserved_engine",
            profile=get_runtime_profile("preserved_es_phase1"),
            lockout=False,
            fixtures_root=None,
            adapter_binding=None,
        )
        report = build_preflight_report(request)
        operator_runtime = resolve_operator_runtime_snapshot(
            mode=OPERATOR_LIVE_RUNTIME,
            producer=StaticRuntimeSnapshotProducer(_stream_manager_snapshot()),
        )

        shell: dict[str, object] = {"surfaces": {}}
        # Seed the r14 cockpit with fixture-derived runtime_status to mirror
        # the real shell built by app.build_phase1_shell_from_artifacts.
        shell["r14_cockpit"] = {
            "runtime_status": {
                "provider_status": "fixture",
                "stream_status": "fixture",
            },
        }

        attach_launch_metadata(shell, report, operator_runtime=operator_runtime)

        startup = shell["startup"]
        self.assertIsInstance(startup, dict)
        self.assertEqual(startup["runtime_mode_label"], "Live-Observation")
        self.assertEqual(startup["running_as"], "Live-Observation")
        self.assertEqual(startup["runtime_mode"], "operator_live_runtime")

        runtime = shell["runtime"]
        self.assertIsInstance(runtime, dict)
        self.assertEqual(runtime["runtime_mode"], "operator_live_runtime")
        self.assertEqual(runtime["operator_live_runtime_mode"], OPERATOR_LIVE_RUNTIME)

        cockpit_runtime_status = shell["r14_cockpit"]["runtime_status"]
        self.assertNotEqual(cockpit_runtime_status["provider_status"], "fixture")
        self.assertNotEqual(cockpit_runtime_status["stream_status"], "fixture")
        self.assertEqual(cockpit_runtime_status["provider_status"], "operator_live_runtime")
        self.assertEqual(cockpit_runtime_status["stream_status"], "operator_live_runtime_active")

        # The primary cockpit surface is the live-observation cockpit.
        self.assertEqual(
            shell[PRIMARY_COCKPIT_SURFACE_KEY_FIELD],
            LIVE_OBSERVATION_COCKPIT_SURFACE_KEY,
        )

    def test_safe_non_live_overlay_preserves_fixture_labels(self) -> None:
        request = LaunchRequest(
            mode="preserved_engine",
            profile=get_runtime_profile("preserved_es_phase1"),
            lockout=False,
            fixtures_root=None,
            adapter_binding=None,
        )
        report = build_preflight_report(request)
        operator_runtime = resolve_operator_runtime_snapshot(mode="SAFE_NON_LIVE")

        shell: dict[str, object] = {"surfaces": {}}
        shell["r14_cockpit"] = {
            "runtime_status": {
                "provider_status": "fixture",
                "stream_status": "fixture",
            },
        }
        attach_launch_metadata(shell, report, operator_runtime=operator_runtime)

        cockpit_runtime_status = shell["r14_cockpit"]["runtime_status"]
        self.assertEqual(cockpit_runtime_status["provider_status"], "fixture")
        self.assertEqual(cockpit_runtime_status["stream_status"], "fixture")

        startup = shell["startup"]
        self.assertNotEqual(startup["runtime_mode_label"], "Live-Observation")


class DisplayDoesNotCreateQueryReadyTests(unittest.TestCase):
    def test_query_ready_false_when_chart_blocking_or_fields_missing(self) -> None:
        # Active stream + complete quote fields, but chart bars are missing
        # for every contract (default observable behavior). Display/view-model
        # cannot invent QUERY_READY from active stream identity alone.
        surface = build_five_contract_readiness_summary_surface(
            runtime_snapshot=_stream_manager_snapshot(),
        )
        for row in surface["rows"]:
            with self.subTest(contract=row["contract"]):
                self.assertFalse(row["query_ready"])
                self.assertTrue(row["query_not_ready_reasons"])

    def test_live_observation_cockpit_surface_does_not_invent_query_ready(self) -> None:
        from ntb_marimo_console.primary_cockpit import build_live_observation_cockpit_surface

        readiness_summary = build_five_contract_readiness_summary_surface(
            runtime_snapshot=_stream_manager_snapshot(),
        )
        operator_runtime = resolve_operator_runtime_snapshot(
            mode=OPERATOR_LIVE_RUNTIME,
            producer=StaticRuntimeSnapshotProducer(_stream_manager_snapshot()),
        )

        cockpit = build_live_observation_cockpit_surface(
            readiness_summary=readiness_summary,
            operator_live_runtime=operator_runtime.to_dict(),
        )

        for row in cockpit["rows"]:
            with self.subTest(contract=row["contract"]):
                self.assertFalse(row["query_enabled"])
                self.assertEqual(row["query_action_state"], "DISABLED")
                self.assertEqual(
                    row["query_action_provenance"],
                    "unavailable_not_inferred_from_display_or_raw_enabled_mapping",
                )
                self.assertIn(row["live_runtime_readiness_state"], {LIVE_RUNTIME_CONNECTED})


class FixtureLabelLeakageTests(unittest.TestCase):
    def test_runtime_stream_state_field_exposes_manager_state(self) -> None:
        for state in ("active", "stale", "blocked"):
            with self.subTest(state=state):
                summary = build_five_contract_readiness_summary(
                    runtime_snapshot=_stream_manager_snapshot(state=state),
                )
                self.assertEqual(summary.runtime_stream_state, state)
                self.assertEqual(summary.runtime_stream_active, state == "active")

    def test_live_observation_overlay_does_not_leak_fixture_when_runtime_unavailable(self) -> None:
        # Even when the live runtime is unavailable, the labels should not
        # claim "Fixture/Demo" identity under explicit live opt-in — they
        # frame the session as live-observation (fail-closed).
        request = LaunchRequest(
            mode="preserved_engine",
            profile=get_runtime_profile("preserved_es_phase1"),
            lockout=False,
            fixtures_root=None,
            adapter_binding=None,
        )
        report = build_preflight_report(request)
        operator_runtime = resolve_operator_runtime_snapshot(mode=OPERATOR_LIVE_RUNTIME)

        shell: dict[str, object] = {"surfaces": {}}
        shell["r14_cockpit"] = {
            "runtime_status": {
                "provider_status": "fixture",
                "stream_status": "fixture",
            },
        }
        attach_launch_metadata(shell, report, operator_runtime=operator_runtime)

        startup = shell["startup"]
        self.assertEqual(startup["runtime_mode_label"], "Live-Observation")
        self.assertEqual(startup["running_as"], "Live-Observation")
        cockpit_runtime_status = shell["r14_cockpit"]["runtime_status"]
        self.assertNotEqual(cockpit_runtime_status["provider_status"], "fixture")
        self.assertNotEqual(cockpit_runtime_status["stream_status"], "fixture")


if __name__ == "__main__":
    unittest.main()
