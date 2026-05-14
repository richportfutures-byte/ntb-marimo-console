"""Tests for the bounded cockpit operator action timeline."""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from ntb_marimo_console.cockpit_manual_query import (
    COCKPIT_OPERATOR_ACTION_TIMELINE_MAX_ENTRIES,
    append_operator_action_timeline_entry,
    operator_action_status_for_lifecycle_action,
)
from ntb_marimo_console.contract_universe import (
    excluded_final_target_contracts,
    final_target_contracts,
)
from ntb_marimo_console.market_data.stream_cache import (
    StreamCacheRecord,
    StreamCacheSnapshot,
)
from ntb_marimo_console.session_lifecycle import (
    load_session_lifecycle_from_env,
    refresh_runtime_snapshot,
    reload_current_profile,
    request_cockpit_manual_query,
    request_query_action,
    reset_session,
)
from ntb_marimo_console.ui.marimo_phase1_renderer import build_primary_cockpit_plan


NOW = "2026-05-06T14:00:00+00:00"
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


def _runtime_record(contract: str) -> StreamCacheRecord:
    return StreamCacheRecord(
        provider="schwab",
        service="LEVELONE_FUTURES",
        symbol=RUNTIME_SYMBOL_BY_CONTRACT[contract],
        contract=contract,
        message_type="quote",
        fields=_complete_levelone_fields(),
        updated_at=NOW,
        age_seconds=0.0,
        fresh=True,
        blocking_reasons=(),
    )


def _runtime_cache_snapshot() -> StreamCacheSnapshot:
    return StreamCacheSnapshot(
        generated_at=NOW,
        provider="schwab",
        provider_status="active",
        cache_max_age_seconds=15.0,
        records=tuple(_runtime_record(c) for c in final_target_contracts()),
        blocking_reasons=(),
        stale_symbols=(),
    )


def _cockpit_timeline(lifecycle) -> dict:
    surface = lifecycle.shell["surfaces"]["fixture_cockpit_overview"]
    return surface["operator_action_timeline"]


class CockpitOperatorActionTimelineTests(unittest.TestCase):
    def test_submitted_manual_query_appends_visible_timeline_entry(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            submitted = request_cockpit_manual_query(lifecycle, "ES")

        timeline = _cockpit_timeline(submitted)
        entries = timeline["entries"]
        self.assertEqual(timeline["schema"], "cockpit_operator_action_timeline_v1")
        self.assertEqual(timeline["max_entries"], COCKPIT_OPERATOR_ACTION_TIMELINE_MAX_ENTRIES)
        self.assertEqual(timeline["entry_count"], 1)
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry["action_kind"], "MANUAL_QUERY")
        self.assertEqual(entry["action_status"], "SUBMITTED")
        self.assertEqual(entry["contract"], "ES")
        self.assertIn("preserved pipeline returned a bounded result", entry["action_text"])
        self.assertIsNone(entry["blocked_reason"])
        self.assertIn(
            "Preserved pipeline completed",
            entry["bounded_result_summary"],
        )
        self.assertEqual(entry["sequence"], 1)
        self.assertEqual(submitted.operator_action_timeline[0].action_status, "SUBMITTED")

    def test_blocked_manual_query_appends_blocked_timeline_entry_with_plain_reason(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            blocked = request_cockpit_manual_query(lifecycle, "NQ")

        timeline = _cockpit_timeline(blocked)
        self.assertEqual(timeline["entry_count"], 1)
        entry = timeline["entries"][0]
        self.assertEqual(entry["action_kind"], "MANUAL_QUERY")
        self.assertEqual(entry["action_status"], "BLOCKED")
        self.assertEqual(entry["contract"], "NQ")
        self.assertIsNotNone(entry["blocked_reason"])
        self.assertIn("Manual query blocked", entry["blocked_reason"])
        self.assertEqual(
            entry["bounded_result_summary"],
            "No bounded pipeline result is available because the query was not submitted.",
        )

    def test_blocked_manual_query_does_not_call_pipeline_backend(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            blocked = request_cockpit_manual_query(lifecycle, "NQ")

        result = blocked.shell["surfaces"]["fixture_cockpit_overview"]["last_query_result"]
        self.assertEqual(result["request_status"], "BLOCKED")
        self.assertFalse(result["submitted"])
        self.assertEqual(result["pipeline_result_status"], "not_submitted")

    def test_refresh_appends_visible_timeline_entry_without_creating_query_ready(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            refreshed_runtime = refresh_runtime_snapshot(lifecycle)
            reloaded = reload_current_profile(lifecycle)

        runtime_timeline = _cockpit_timeline(refreshed_runtime)
        self.assertEqual(runtime_timeline["entry_count"], 1)
        runtime_entry = runtime_timeline["entries"][0]
        self.assertEqual(runtime_entry["action_kind"], "RUNTIME_REFRESH")
        self.assertEqual(runtime_entry["action_status"], "REFRESHED")
        self.assertEqual(
            runtime_entry["next_operator_state"],
            "Review the refreshed cockpit gate states before any manual query.",
        )

        reload_timeline = _cockpit_timeline(reloaded)
        self.assertEqual(reload_timeline["entry_count"], 1)
        reload_entry = reload_timeline["entries"][0]
        self.assertEqual(reload_entry["action_kind"], "PROFILE_REFRESH")
        self.assertEqual(reload_entry["action_status"], "REFRESHED")

        for surface_dict in (refreshed_runtime.shell, reloaded.shell):
            row = next(
                row
                for row in surface_dict["surfaces"]["fixture_cockpit_overview"]["rows"]
                if row["contract"] == "NQ"
            )
            self.assertNotEqual(row["query_action_state"], "ENABLED")

    def test_reset_appends_visible_timeline_entry_without_creating_query_ready(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            reset = reset_session(lifecycle)

        timeline = _cockpit_timeline(reset)
        self.assertEqual(timeline["entry_count"], 1)
        entry = timeline["entries"][0]
        self.assertEqual(entry["action_kind"], "SESSION_RESET")
        self.assertEqual(entry["action_status"], "RESET")
        self.assertEqual(reset.shell["workflow"]["query_action_status"], "BLOCKED")

    def test_timeline_length_is_bounded(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            current = lifecycle
            for _ in range(COCKPIT_OPERATOR_ACTION_TIMELINE_MAX_ENTRIES + 5):
                current = refresh_runtime_snapshot(current)

        timeline = _cockpit_timeline(current)
        self.assertLessEqual(
            len(timeline["entries"]),
            COCKPIT_OPERATOR_ACTION_TIMELINE_MAX_ENTRIES,
        )
        self.assertEqual(timeline["entry_count"], len(timeline["entries"]))
        self.assertEqual(timeline["max_entries"], COCKPIT_OPERATOR_ACTION_TIMELINE_MAX_ENTRIES)

        sequences = [entry["sequence"] for entry in timeline["entries"]]
        self.assertEqual(sequences, sorted(sequences))
        self.assertGreater(sequences[0], 1, "earliest entries should have been pruned")

    def test_timeline_carries_across_mixed_action_sequence(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            after_blocked = request_cockpit_manual_query(lifecycle, "NQ")
            after_submitted = request_cockpit_manual_query(after_blocked, "ES")
            after_refresh = refresh_runtime_snapshot(after_submitted)
            after_reset = reset_session(after_refresh)

        timeline = _cockpit_timeline(after_reset)
        kinds = [entry["action_kind"] for entry in timeline["entries"]]
        statuses = [entry["action_status"] for entry in timeline["entries"]]
        self.assertEqual(
            kinds,
            ["MANUAL_QUERY", "MANUAL_QUERY", "RUNTIME_REFRESH", "SESSION_RESET"],
        )
        self.assertEqual(
            statuses,
            ["BLOCKED", "SUBMITTED", "REFRESHED", "RESET"],
        )

    def test_timeline_remains_sanitized_and_excludes_raw_values(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            submitted = request_cockpit_manual_query(lifecycle, "ES")

        timeline = _cockpit_timeline(submitted)
        rendered = json.dumps(timeline, sort_keys=True).lower()
        for forbidden in ("client_secret", "api_key", "token_path", "authorization", "customer", "correl"):
            self.assertNotIn(forbidden, rendered)
        for raw in ("1.125", "100.0", "7175.25"):
            self.assertNotIn(raw, rendered)
        for entry in timeline["entries"]:
            self.assertFalse(entry["raw_quote_values_included"])
            self.assertFalse(entry["raw_bar_values_included"])
            self.assertFalse(entry["raw_streamer_payloads_included"])

    def test_runtime_cache_derived_readiness_preserved_across_actions(self) -> None:
        snapshot = _runtime_cache_snapshot()
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env(runtime_snapshot=snapshot)
            submitted = request_cockpit_manual_query(lifecycle, "ES")
            blocked = request_cockpit_manual_query(submitted, "NQ")
            refreshed = refresh_runtime_snapshot(blocked)
            reset = reset_session(refreshed)

        for item in (submitted, blocked, refreshed, reset):
            with self.subTest(action=item.last_action):
                timeline = _cockpit_timeline(item)
                self.assertGreaterEqual(timeline["entry_count"], 1)
                last_entry = timeline["entries"][-1]
                self.assertEqual(
                    last_entry["runtime_readiness_status"],
                    "LIVE_RUNTIME_CONNECTED",
                )
                self.assertTrue(last_entry["runtime_readiness_preserved"])

        # The last entry of reset is the SESSION_RESET event
        reset_entry = _cockpit_timeline(reset)["entries"][-1]
        self.assertEqual(reset_entry["action_kind"], "SESSION_RESET")

    def test_display_or_view_model_cannot_create_query_ready(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            blocked = request_cockpit_manual_query(lifecycle, "NQ")
            refreshed = refresh_runtime_snapshot(blocked)

        for surface_holder in (blocked.shell, refreshed.shell):
            cockpit = surface_holder["surfaces"]["fixture_cockpit_overview"]
            timeline = cockpit["operator_action_timeline"]
            for entry in timeline["entries"]:
                # No timeline entry must imply query-ready provenance for a blocked path
                if entry["action_status"] in {"BLOCKED", "REFRESHED", "RESET"}:
                    self.assertNotEqual(
                        entry.get("gate_provenance_basis"),
                        "real_trigger_state_result_and_pipeline_gate",
                    )
            rows = {row["contract"]: row for row in cockpit["rows"]}
            self.assertEqual(rows["NQ"]["query_action_state"], "DISABLED")

    def test_missing_chart_bars_still_block_with_otherwise_valid_runtime_summary(self) -> None:
        snapshot = _runtime_cache_snapshot()
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_nq_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env(runtime_snapshot=snapshot)
            blocked = request_cockpit_manual_query(lifecycle, "NQ")

        rows = blocked.shell["surfaces"]["fixture_cockpit_overview"]["rows"]
        nq_row = next(row for row in rows if row["contract"] == "NQ")
        self.assertEqual(nq_row["chart_status"], "chart missing")
        self.assertEqual(nq_row["query_action_state"], "DISABLED")
        self.assertEqual(nq_row["last_query_status"], "BLOCKED")

        timeline = _cockpit_timeline(blocked)
        self.assertEqual(timeline["entries"][-1]["action_status"], "BLOCKED")
        self.assertEqual(timeline["entries"][-1]["contract"], "NQ")

    def test_missing_required_quote_or_cache_fields_still_fail_closed(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            # CL fixture has stale quote/bar; treat as failed-closed via existing gate.
            blocked = request_cockpit_manual_query(lifecycle, "CL")

        rows = blocked.shell["surfaces"]["fixture_cockpit_overview"]["rows"]
        cl_row = next(row for row in rows if row["contract"] == "CL")
        self.assertEqual(cl_row["query_action_state"], "DISABLED")
        timeline = _cockpit_timeline(blocked)
        entry = timeline["entries"][-1]
        self.assertEqual(entry["action_status"], "BLOCKED")
        self.assertEqual(entry["contract"], "CL")

    def test_zn_and_gc_remain_excluded_from_supported_cockpit_contracts(self) -> None:
        self.assertEqual(excluded_final_target_contracts(), ("ZN", "GC"))
        for excluded in excluded_final_target_contracts():
            self.assertNotIn(excluded, final_target_contracts())

        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            for contract in ("ZN", "GC"):
                blocked = request_cockpit_manual_query(lifecycle, contract)
                timeline = _cockpit_timeline(blocked)
                entry = timeline["entries"][-1]
                self.assertEqual(entry["action_status"], "BLOCKED")
                self.assertIn(
                    "not a supported cockpit query contract",
                    entry["blocked_reason"] or "",
                )

    def test_mgc_remains_micro_gold_in_timeline(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            submitted = request_cockpit_manual_query(lifecycle, "MGC")

        timeline = _cockpit_timeline(submitted)
        entry = timeline["entries"][-1]
        self.assertEqual(entry["contract"], "MGC")
        rendered = json.dumps(timeline, sort_keys=True)
        self.assertNotIn('"GC"', rendered.replace('"MGC"', ""))

    def test_default_launch_remains_non_live_with_empty_timeline(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()

        cockpit = lifecycle.shell["surfaces"]["fixture_cockpit_overview"]
        self.assertEqual(cockpit["mode"], "fixture_dry_run_non_live")
        self.assertFalse(cockpit["default_launch_live"])
        timeline = cockpit["operator_action_timeline"]
        self.assertEqual(timeline["entry_count"], 0)
        self.assertEqual(timeline["entries"], [])

    def test_primary_cockpit_plan_exposes_timeline(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            submitted = request_cockpit_manual_query(lifecycle, "ES")

        plan = build_primary_cockpit_plan(submitted.shell)
        timeline = plan["operator_action_timeline"]
        self.assertIsInstance(timeline, dict)
        self.assertEqual(timeline["entry_count"], 1)
        self.assertEqual(timeline["entries"][0]["action_kind"], "MANUAL_QUERY")

    def test_bounded_query_action_does_not_pollute_timeline(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            queried = request_query_action(lifecycle)

        timeline = _cockpit_timeline(queried)
        self.assertEqual(timeline["entry_count"], 0)
        self.assertEqual(timeline["entries"], [])

    def test_lifecycle_state_does_not_authorize_trade_execution(self) -> None:
        # Sanity guardrail: no broker/order/execution surface ever appears.
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            submitted = request_cockpit_manual_query(lifecycle, "ES")

        rendered = json.dumps(submitted.shell["surfaces"]["fixture_cockpit_overview"], sort_keys=True)
        for forbidden in ("broker", "order", "fill", "pnl", "p_and_l", "execution_authorized"):
            self.assertNotIn(forbidden, rendered.lower())


class CockpitOperatorActionTimelineUnitTests(unittest.TestCase):
    def test_append_increments_sequence_and_bounds_length(self) -> None:
        history: tuple = ()
        status = operator_action_status_for_lifecycle_action(
            action_kind="RUNTIME_REFRESH",
            action_status="REFRESHED",
            action_text="refresh",
            runtime_readiness_status="LIVE_RUNTIME_NOT_REQUESTED",
            runtime_readiness_preserved=False,
            next_operator_state="next",
        )
        for _ in range(COCKPIT_OPERATOR_ACTION_TIMELINE_MAX_ENTRIES + 3):
            history = append_operator_action_timeline_entry(
                history, status=status, recorded_at=NOW,
            )

        self.assertEqual(len(history), COCKPIT_OPERATOR_ACTION_TIMELINE_MAX_ENTRIES)
        sequences = [entry.sequence for entry in history]
        self.assertEqual(sequences, sorted(sequences))
        self.assertGreater(sequences[0], 1)


if __name__ == "__main__":
    unittest.main()
