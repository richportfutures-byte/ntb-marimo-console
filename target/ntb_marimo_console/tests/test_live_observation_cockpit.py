"""Tests for the explicit-opt-in live-observation primary cockpit.

These prove that under ``OPERATOR_LIVE_RUNTIME`` the Marimo console renders a
live-observation cockpit driven by the operator runtime cache — never the
fixture cockpit — and that the default launch path is completely unchanged.

All assertions work at the plan / surface / shell level (plain dicts) plus a
thin render-text check, so no running Marimo kernel is required.
"""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from ntb_marimo_console.contract_universe import (
    excluded_final_target_contracts,
    final_target_contracts,
)
from ntb_marimo_console.launch_config import build_startup_artifacts_from_env
from ntb_marimo_console.market_data.stream_cache import (
    StreamCacheRecord,
    StreamCacheSnapshot,
)
from ntb_marimo_console.market_data.stream_manager import MIN_STREAM_REFRESH_FLOOR_SECONDS
from ntb_marimo_console.primary_cockpit import (
    FIXTURE_COCKPIT_SURFACE_KEY,
    LIVE_OBSERVATION_COCKPIT_SURFACE_KEY,
    build_live_observation_cockpit_surface,
    primary_cockpit_surface,
    primary_cockpit_surface_key,
)
from ntb_marimo_console.ui.marimo_phase1_renderer import (
    _render_console_header,
    _render_fixture_cockpit_primary,
    build_primary_cockpit_plan,
)

NOW = "2026-05-14T14:00:00+00:00"
RUNTIME_SYMBOL_BY_CONTRACT = {
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


def _runtime_record(contract: str, index: int = 0) -> StreamCacheRecord:
    return StreamCacheRecord(
        provider="schwab",
        service="LEVELONE_FUTURES",
        symbol=RUNTIME_SYMBOL_BY_CONTRACT[contract],
        contract=contract,
        message_type="quote",
        fields=_complete_levelone_fields(index),
        updated_at=NOW,
        age_seconds=0.0,
        fresh=True,
        blocking_reasons=(),
    )


def _populated_runtime_cache_snapshot() -> StreamCacheSnapshot:
    """A live runtime cache snapshot with quote records for all five contracts."""
    return StreamCacheSnapshot(
        generated_at=NOW,
        provider="schwab",
        provider_status="active",
        cache_max_age_seconds=15.0,
        records=tuple(
            _runtime_record(contract, index)
            for index, contract in enumerate(final_target_contracts())
        ),
        blocking_reasons=(),
        stale_symbols=(),
    )


def _live_shell_with_cache() -> dict:
    """Build a launch shell under the explicit live runtime opt-in (cache populated)."""
    with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
        return build_startup_artifacts_from_env(
            default_mode="fixture_demo",
            runtime_snapshot=_populated_runtime_cache_snapshot(),
        ).shell


def _live_shell_fail_closed() -> dict:
    """Build a launch shell under the explicit live opt-in with NO runtime cache.

    No producer and no runtime snapshot are supplied, so the operator runtime
    resolves fail-closed (live unavailable) — the live-observation cockpit must
    surface that, never fixture data.
    """
    with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
        return build_startup_artifacts_from_env(
            default_mode="fixture_demo",
            operator_runtime_mode="OPERATOR_LIVE_RUNTIME",
        ).shell


def _default_shell() -> dict:
    with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
        return build_startup_artifacts_from_env(default_mode="fixture_demo").shell


# ---------------------------------------------------------------------------
# build_live_observation_cockpit_surface — unit
# ---------------------------------------------------------------------------


class LiveObservationCockpitSurfaceUnitTests(unittest.TestCase):
    def test_surface_has_live_identity_and_five_contracts_only(self) -> None:
        readiness = {
            "live_runtime_readiness_status": "LIVE_RUNTIME_CONNECTED",
            "rows": [
                {
                    "contract": c,
                    "quote_status": "quote available",
                    "chart_status": "chart available",
                    "query_gate_status": "ENABLED",
                    "query_ready": True,
                    "live_runtime_readiness_state": "LIVE_RUNTIME_CONNECTED",
                    "runtime_cache_status": "runtime_cache_connected",
                }
                for c in final_target_contracts()
            ],
        }
        runtime = {
            "cache_provider_status": "connected",
            "cache_snapshot_ready": True,
            "cache_generated_at": NOW,
            "blocking_reasons": [],
        }
        surface = build_live_observation_cockpit_surface(
            readiness_summary=readiness, operator_live_runtime=runtime
        )
        self.assertEqual(surface["surface"], LIVE_OBSERVATION_COCKPIT_SURFACE_KEY)
        self.assertEqual(surface["cockpit_identity"], "live_observation")
        self.assertEqual(surface["mode"], "live_observation_runtime_cache")
        self.assertFalse(surface["default_launch_live"])
        self.assertTrue(surface["live_credentials_required"])
        self.assertEqual(
            [r["contract"] for r in surface["rows"]],
            ["ES", "NQ", "CL", "6E", "MGC"],
        )
        contracts = {r["contract"] for r in surface["rows"]}
        self.assertNotIn("ZN", contracts)
        self.assertNotIn("GC", contracts)
        mgc = next(r for r in surface["rows"] if r["contract"] == "MGC")
        self.assertEqual(mgc["profile_label"], "Micro Gold")
        self.assertNotEqual(mgc["profile_label"], "GC")

    def test_surface_reflects_pipeline_gate_and_never_creates_query_ready(self) -> None:
        # query_ready False upstream -> the cockpit row must stay fail-closed and
        # must not claim real-gate provenance.
        readiness = {
            "live_runtime_readiness_status": "LIVE_RUNTIME_ERROR",
            "rows": [
                {
                    "contract": c,
                    "quote_status": "quote missing",
                    "chart_status": "chart missing",
                    "query_gate_status": "BLOCKED",
                    "query_ready": False,
                    "query_not_ready_reasons": [f"missing_cache_record:{c}"],
                    "live_runtime_readiness_state": "LIVE_RUNTIME_ERROR",
                    "runtime_cache_status": "runtime_cache_error",
                }
                for c in final_target_contracts()
            ],
        }
        runtime = {
            "cache_provider_status": "disconnected",
            "cache_snapshot_ready": False,
            "cache_generated_at": None,
            "blocking_reasons": ["operator_live_runtime_snapshot_unavailable"],
        }
        surface = build_live_observation_cockpit_surface(
            readiness_summary=readiness, operator_live_runtime=runtime
        )
        self.assertEqual(surface["mode"], "live_observation_fail_closed")
        for row in surface["rows"]:
            self.assertFalse(row["query_enabled"])
            self.assertEqual(row["query_action_state"], "DISABLED")
            self.assertEqual(
                row["query_ready_provenance"],
                "unavailable_not_inferred_from_display_or_raw_enabled_mapping",
            )
            self.assertIsNotNone(row["query_disabled_reason"])

    def test_surface_with_empty_inputs_is_fail_closed_five_contracts(self) -> None:
        surface = build_live_observation_cockpit_surface(
            readiness_summary=None, operator_live_runtime=None
        )
        self.assertEqual(surface["mode"], "live_observation_fail_closed")
        self.assertEqual(
            [r["contract"] for r in surface["rows"]],
            ["ES", "NQ", "CL", "6E", "MGC"],
        )
        for row in surface["rows"]:
            self.assertEqual(row["query_action_state"], "DISABLED")


# ---------------------------------------------------------------------------
# Live launch shell — integration
# ---------------------------------------------------------------------------


class LiveObservationCockpitLaunchTests(unittest.TestCase):
    def test_live_launch_uses_live_observation_primary_surface_not_fixture(self) -> None:
        shell = _live_shell_with_cache()
        self.assertEqual(
            shell["primary_cockpit_surface_key"], LIVE_OBSERVATION_COCKPIT_SURFACE_KEY
        )
        self.assertEqual(
            primary_cockpit_surface_key(shell), LIVE_OBSERVATION_COCKPIT_SURFACE_KEY
        )
        # No fixture fallback: the fixture cockpit surface is not even attached.
        self.assertNotIn(FIXTURE_COCKPIT_SURFACE_KEY, shell["surfaces"])
        surface = primary_cockpit_surface(shell)
        self.assertEqual(surface["cockpit_identity"], "live_observation")

    def test_live_launch_header_identity_is_live_observation_not_fixture(self) -> None:
        shell = _live_shell_with_cache()
        runtime = shell["runtime"]
        self.assertEqual(runtime["console_identity_kind"], "live_observation")
        self.assertEqual(runtime["console_identity_mode_label"], "Live-Observation")
        self.assertEqual(runtime["console_identity_running_as"], "Live-Observation")
        header_html = _render_console_header(
            shell, heading="NTB Marimo Operator Console", mode_summary="x"
        ).text
        self.assertIn("Running as Live-Observation", header_html)
        self.assertNotIn("Fixture/Demo", header_html)

    def test_live_launch_consumes_runtime_cache_rows_for_five_contracts(self) -> None:
        shell = _live_shell_with_cache()
        surface = primary_cockpit_surface(shell)
        rows = {r["contract"]: r for r in surface["rows"]}
        self.assertEqual(set(rows), set(final_target_contracts()))
        # The rows reflect the live runtime cache (quotes present from the
        # populated snapshot), not fixture data.
        for contract, row in rows.items():
            self.assertEqual(row["runtime_state"], "live_observation")
            self.assertIn("quote", row["quote_status"])
        # Live status is surfaced on the cockpit, not hidden behind fixture framing.
        self.assertIn(
            surface["live_runtime_readiness_status"],
            {
                "LIVE_RUNTIME_CONNECTED",
                "LIVE_RUNTIME_STALE",
                "LIVE_RUNTIME_ERROR",
                "LIVE_RUNTIME_MISSING_REQUIRED_FIELDS",
                "LIVE_RUNTIME_MISSING_CONTRACT",
            },
        )

    def test_live_runtime_unavailable_is_fail_closed_with_live_specific_blocker(self) -> None:
        shell = _live_shell_fail_closed()
        self.assertEqual(
            shell["primary_cockpit_surface_key"], LIVE_OBSERVATION_COCKPIT_SURFACE_KEY
        )
        self.assertNotIn(FIXTURE_COCKPIT_SURFACE_KEY, shell["surfaces"])
        surface = primary_cockpit_surface(shell)
        self.assertEqual(surface["cockpit_identity"], "live_observation")
        self.assertEqual(surface["mode"], "live_observation_fail_closed")
        self.assertFalse(surface["fixture_fallback_after_live_failure"])
        # A real live blocker is surfaced — not a fixture/credential-free framing.
        blockers = surface["live_runtime_blocking_reasons"]
        self.assertTrue(blockers)
        self.assertTrue(
            any("operator_live_runtime" in str(b) for b in blockers),
            blockers,
        )
        for row in surface["rows"]:
            self.assertEqual(row["query_action_state"], "DISABLED")
            self.assertFalse(row["query_enabled"])

    def test_default_launch_is_unchanged_fixture_identity(self) -> None:
        shell = _default_shell()
        self.assertEqual(
            shell["primary_cockpit_surface_key"], FIXTURE_COCKPIT_SURFACE_KEY
        )
        self.assertIn(FIXTURE_COCKPIT_SURFACE_KEY, shell["surfaces"])
        self.assertNotIn(LIVE_OBSERVATION_COCKPIT_SURFACE_KEY, shell["surfaces"])
        surface = primary_cockpit_surface(shell)
        self.assertEqual(surface["cockpit_identity"], "fixture_demo")
        self.assertEqual(surface["mode"], "fixture_dry_run_non_live")
        # Header identity stays Fixture/Demo for the default launch.
        runtime = shell["runtime"]
        self.assertNotIn("console_identity_kind", runtime)
        header_html = _render_console_header(
            shell, heading="NTB Marimo Operator Console", mode_summary="x"
        ).text
        self.assertIn("Fixture/Demo", header_html)
        self.assertNotIn("Live-Observation", header_html)

    def test_primary_cockpit_plan_resolves_live_surface(self) -> None:
        plan = build_primary_cockpit_plan(_live_shell_with_cache())
        self.assertTrue(plan["present"])
        self.assertEqual(plan["key"], LIVE_OBSERVATION_COCKPIT_SURFACE_KEY)
        self.assertEqual(plan["cockpit_identity"], "live_observation")
        self.assertEqual(
            [r["contract"] for r in plan["rows"]],
            ["ES", "NQ", "CL", "6E", "MGC"],
        )
        self.assertFalse(plan["default_launch_live"])

    def test_rendered_live_cockpit_shows_live_divider_not_fixture(self) -> None:
        shell = _live_shell_fail_closed()
        rendered = _render_fixture_cockpit_primary(primary_cockpit_surface(shell))
        html = rendered.text
        self.assertIn("FIVE-CONTRACT LIVE-OBSERVATION COCKPIT", html)
        self.assertNotIn("FIVE-CONTRACT FIXTURE COCKPIT", html)
        self.assertIn("No fixture fallback after live failure", html)

    def test_rendered_default_cockpit_still_shows_fixture_divider(self) -> None:
        rendered = _render_fixture_cockpit_primary(primary_cockpit_surface(_default_shell()))
        html = rendered.text
        self.assertIn("FIVE-CONTRACT FIXTURE COCKPIT", html)
        self.assertNotIn("LIVE-OBSERVATION", html)

    def test_15_second_refresh_floor_preserved_in_live_mode(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            artifacts = build_startup_artifacts_from_env(
                default_mode="fixture_demo",
                operator_runtime_mode="OPERATOR_LIVE_RUNTIME",
            )
        self.assertGreaterEqual(
            artifacts.operator_runtime.refresh_floor_seconds,
            MIN_STREAM_REFRESH_FLOOR_SECONDS,
        )
        self.assertGreaterEqual(MIN_STREAM_REFRESH_FLOOR_SECONDS, 15.0)

    def test_live_cockpit_surface_has_no_execution_or_pnl_automation(self) -> None:
        surface = primary_cockpit_surface(_live_shell_with_cache())

        def _all_keys(obj) -> set[str]:
            keys: set[str] = set()
            if isinstance(obj, dict):
                for key, value in obj.items():
                    keys.add(str(key).lower())
                    keys |= _all_keys(value)
            elif isinstance(obj, (list, tuple)):
                for item in obj:
                    keys |= _all_keys(item)
            return keys

        keys = _all_keys(surface)
        # No broker/order/execution/account/fill/P&L automation field was added.
        for forbidden in (
            "order_id",
            "broker_order",
            "broker",
            "fill_price",
            "fill_id",
            "pnl",
            "position_size",
            "routing",
            "account_id",
            "trade_execution",
        ):
            self.assertNotIn(forbidden, keys, f"unexpected automation key {forbidden!r}")
        # Positive safety posture: observation-only, preserved engine authority.
        self.assertEqual(surface["decision_authority"], "preserved_engine_only")
        self.assertEqual(
            surface["last_query_result"]["decision_authority"], "preserved_engine_only"
        )
        self.assertTrue(surface["last_query_result"]["manual_execution_only"])

    def test_live_cockpit_surface_carries_no_secrets_or_raw_values(self) -> None:
        shell = _live_shell_with_cache()
        rendered = json.dumps(primary_cockpit_surface(shell))
        # Raw quote values from the populated snapshot must not leak.
        for raw in ("100.125", "100.25", "99.25", "25000"):
            self.assertNotIn(raw, rendered)
        for secret in (
            "Bearer",
            "access_token",
            "refresh_token",
            "client_secret",
            "app_key",
            "wss://",
            "schwab_live.env",
        ):
            self.assertNotIn(secret, rendered)
        self.assertFalse(primary_cockpit_surface(shell)["raw_quote_values_included"])
        self.assertFalse(primary_cockpit_surface(shell)["raw_bar_values_included"])

    def test_zn_and_gc_excluded_and_mgc_is_micro_gold_in_live_cockpit(self) -> None:
        self.assertEqual(excluded_final_target_contracts(), ("ZN", "GC"))
        surface = primary_cockpit_surface(_live_shell_with_cache())
        contracts = [r["contract"] for r in surface["rows"]]
        self.assertNotIn("ZN", contracts)
        self.assertNotIn("GC", contracts)
        mgc = next(r for r in surface["rows"] if r["contract"] == "MGC")
        self.assertEqual(mgc["profile_label"], "Micro Gold")
        self.assertNotEqual(mgc["profile_label"], "GC")

    def test_repeated_metadata_attach_does_not_restart_or_relogin(self) -> None:
        # The Marimo refresh path re-runs attach_launch_metadata against the
        # already-resolved operator runtime; it must only re-read the cache and
        # never re-start a runtime or re-login. Re-resolving the same shell
        # twice must be stable and stay live-observation.
        from ntb_marimo_console.launch_config import attach_launch_metadata

        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            artifacts = build_startup_artifacts_from_env(
                default_mode="fixture_demo",
                runtime_snapshot=_populated_runtime_cache_snapshot(),
            )
        shell = dict(artifacts.shell)
        attach_launch_metadata(
            shell, artifacts.report, operator_runtime=artifacts.operator_runtime
        )
        self.assertEqual(
            shell["primary_cockpit_surface_key"], LIVE_OBSERVATION_COCKPIT_SURFACE_KEY
        )
        self.assertNotIn(FIXTURE_COCKPIT_SURFACE_KEY, shell["surfaces"])


if __name__ == "__main__":
    unittest.main()
