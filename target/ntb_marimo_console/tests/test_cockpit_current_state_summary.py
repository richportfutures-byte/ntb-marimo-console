"""Tests for the cockpit current-state summary strip."""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from ntb_marimo_console.cockpit_manual_query import (
    COCKPIT_CURRENT_STATE_SUMMARY_MAX_TEXT_LENGTH,
    build_cockpit_contract_readiness_detail,
    build_cockpit_current_state_summary,
)
from ntb_marimo_console.contract_universe import (
    excluded_final_target_contracts,
    final_target_contracts,
)
from ntb_marimo_console.fixture_operator_session import (
    build_fixture_cockpit_shell_surface,
)
from ntb_marimo_console.market_data.stream_cache import (
    StreamCacheRecord,
    StreamCacheSnapshot,
)
from ntb_marimo_console.session_lifecycle import (
    add_cockpit_operator_note,
    load_session_lifecycle_from_env,
    refresh_runtime_snapshot,
    request_cockpit_manual_query,
    reset_session,
)
from ntb_marimo_console.ui.marimo_phase1_renderer import (
    _fixture_cockpit_contract_readiness_detail_html,
    _fixture_cockpit_current_state_strip_html,
    build_primary_cockpit_plan,
)


NOW = "2026-05-06T14:00:00+00:00"
RUNTIME_SYMBOL_BY_CONTRACT = {
    "ES": "/ESM26",
    "NQ": "/NQM26",
    "CL": "/CLM26",
    "6E": "/6EM26",
    "MGC": "/MGCM26",
}

# Plain-English forbidden terms — trade-recommendation / ranking language.
FORBIDDEN_TERMS = (
    "alert",
    "buy",
    "sell",
    "take trade",
    "best setup",
    "strongest",
    "rank",
)


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


def _cockpit_surface(lifecycle) -> dict:
    return lifecycle.shell["surfaces"]["fixture_cockpit_overview"]


def _summary(lifecycle) -> dict:
    return _cockpit_surface(lifecycle)["current_state_summary"]


def _assert_plain_english_and_bounded(self, summary: dict) -> None:
    text_fields = (
        "runtime_state_text",
        "query_state_text",
        "last_action_text",
        "timeline_state_text",
        "notes_state_text",
        "contract_universe_text",
    )
    for field in text_fields:
        value = summary[field]
        self.assertIsInstance(value, str)
        self.assertTrue(value, f"{field} must be non-empty plain English")
        self.assertLessEqual(
            len(value),
            COCKPIT_CURRENT_STATE_SUMMARY_MAX_TEXT_LENGTH,
            f"{field} must be bounded",
        )
        lowered = value.lower()
        for term in FORBIDDEN_TERMS:
            self.assertNotIn(term, lowered, f"{field} must not contain {term!r}")


class CockpitCurrentStateSummaryUnitTests(unittest.TestCase):
    def test_builder_on_empty_surface_is_fail_closed_plain_english(self) -> None:
        summary = build_cockpit_current_state_summary({})
        self.assertEqual(summary["schema"], "cockpit_current_state_summary_v1")
        self.assertEqual(summary["creates_query_ready"], False)
        self.assertEqual(summary["query_enabled_count"], 0)
        self.assertEqual(summary["query_blocked_count"], 0)
        self.assertEqual(summary["decision_authority"], "preserved_engine_only")
        # No rows -> universe falls back to the final target universe.
        self.assertEqual(
            tuple(summary["supported_contracts"]), final_target_contracts()
        )

    def test_builder_bounds_long_block_reason_text(self) -> None:
        long_reason = "x" * (COCKPIT_CURRENT_STATE_SUMMARY_MAX_TEXT_LENGTH + 300)
        surface = {
            "supported_contracts": list(final_target_contracts()),
            "rows": [
                {"contract": "ES", "query_action_state": "ENABLED"},
                {
                    "contract": "NQ",
                    "query_action_state": "DISABLED",
                    "query_disabled_reason": long_reason,
                },
            ],
        }
        summary = build_cockpit_current_state_summary(surface)
        self.assertLessEqual(
            len(summary["query_blocked_reason_text"]),
            COCKPIT_CURRENT_STATE_SUMMARY_MAX_TEXT_LENGTH,
        )
        self.assertEqual(summary["query_enabled_count"], 1)
        self.assertEqual(summary["query_blocked_count"], 1)


class CockpitContractReadinessDetailUnitTests(unittest.TestCase):
    def test_builder_on_empty_surface_is_exact_universe_fail_closed(self) -> None:
        detail = build_cockpit_contract_readiness_detail({})

        self.assertEqual(
            detail["schema"], "cockpit_contract_readiness_detail_v1"
        )
        self.assertEqual(tuple(detail["supported_contracts"]), final_target_contracts())
        self.assertEqual(detail["excluded_contracts"], ["ZN", "GC"])
        self.assertFalse(detail["creates_query_ready"])
        rows = {row["contract"]: row for row in detail["rows"]}
        self.assertEqual(set(rows), {"ES", "NQ", "CL", "6E", "MGC"})
        self.assertNotIn("ZN", rows)
        self.assertNotIn("GC", rows)
        for row in rows.values():
            self.assertFalse(row["query_enabled"])
            self.assertEqual(row["query_action_state"], "DISABLED")
            self.assertIn("blocked", row["query_state_text"].lower())
            self.assertIn("no cockpit gate row", row["blocked_reason"])
            self.assertEqual(row["latest_operator_action_state"], "NOT_SUBMITTED")
            self.assertEqual(
                row["latest_operator_action_text"],
                "No manual query has been submitted from the primary cockpit.",
            )
            self.assertIn("Do not submit", row["next_safe_operator_action"])

    def test_builder_does_not_treat_notes_as_readiness_or_provenance(self) -> None:
        surface = {
            "supported_contracts": list(final_target_contracts()),
            "rows": [
                {
                    "contract": "ES",
                    "profile_label": "ES",
                    "query_action_state": "DISABLED",
                    "query_enabled": False,
                    "query_disabled_reason": "Manual query blocked: chart bars are missing for ES.",
                    "query_ready_provenance": "unavailable_not_inferred_from_display_or_raw_enabled_mapping",
                }
            ],
            "operator_notes": {
                "entries": [
                    {
                        "contract": "ES",
                        "text": "operator thinks this is ready",
                    }
                ]
            },
        }

        detail = build_cockpit_contract_readiness_detail(surface)
        es = next(row for row in detail["rows"] if row["contract"] == "ES")
        self.assertFalse(es["query_enabled"])
        self.assertIn("chart bars are missing", es["blocked_reason"])
        self.assertFalse(detail["creates_query_ready"])
        self.assertNotIn("operator thinks", json.dumps(detail).lower())


class CockpitCurrentStateSummarySurfaceTests(unittest.TestCase):
    def test_fixture_shell_surface_includes_current_state_summary(self) -> None:
        surface = build_fixture_cockpit_shell_surface()
        summary = surface["current_state_summary"]
        self.assertEqual(summary["schema"], "cockpit_current_state_summary_v1")
        _assert_plain_english_and_bounded(self, summary)

    def test_fixture_shell_surface_includes_contract_readiness_detail(self) -> None:
        surface = build_fixture_cockpit_shell_surface()
        detail = surface["contract_readiness_detail"]
        self.assertEqual(
            detail["schema"], "cockpit_contract_readiness_detail_v1"
        )
        rows = {row["contract"]: row for row in detail["rows"]}
        self.assertEqual(tuple(rows), final_target_contracts())
        self.assertEqual(rows["MGC"]["display_name"], "Micro Gold")
        self.assertNotIn("ZN", rows)
        self.assertNotIn("GC", rows)
        for contract, row in rows.items():
            with self.subTest(contract=contract):
                self.assertIsInstance(row["runtime_readiness_text"], str)
                self.assertTrue(row["runtime_readiness_text"])
                self.assertIn("Manual query", row["query_state_text"])
                self.assertIsInstance(row["next_safe_operator_action"], str)
                self.assertTrue(row["next_safe_operator_action"])
        self.assertIsNone(rows["ES"]["blocked_reason"])
        self.assertIn("missing", rows["NQ"]["blocked_reason"])
        self.assertIn("stale", rows["CL"]["blocked_reason"])
        self.assertIn("dependency", rows["6E"]["blocked_reason"])

    def test_initial_lifecycle_summary_present_and_plain_english(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()

        summary = _summary(lifecycle)
        self.assertEqual(summary["schema"], "cockpit_current_state_summary_v1")
        _assert_plain_english_and_bounded(self, summary)
        # Fixture default is non-live.
        self.assertFalse(summary["default_launch_live"])
        self.assertIn("non-live", summary["runtime_state_text"].lower())
        # Default fixture scenario: ES + MGC enabled, NQ/CL/6E blocked.
        self.assertEqual(summary["query_enabled_count"], 2)
        self.assertEqual(summary["query_blocked_count"], 3)
        self.assertEqual(summary["last_action_kind"], "IDLE")
        self.assertEqual(summary["timeline_entry_count"], 0)
        self.assertEqual(summary["notes_entry_count"], 0)

    def test_summary_present_in_primary_cockpit_plan(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()

        plan = build_primary_cockpit_plan(lifecycle.shell)
        summary = plan["current_state_summary"]
        self.assertIsInstance(summary, dict)
        self.assertEqual(summary["schema"], "cockpit_current_state_summary_v1")

    def test_contract_readiness_detail_present_in_primary_cockpit_plan(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()

        plan = build_primary_cockpit_plan(lifecycle.shell)
        detail = plan["contract_readiness_detail"]
        self.assertIsInstance(detail, dict)
        self.assertEqual(
            detail["schema"], "cockpit_contract_readiness_detail_v1"
        )
        self.assertEqual(
            [row["contract"] for row in detail["rows"]],
            ["ES", "NQ", "CL", "6E", "MGC"],
        )

    def test_summary_renders_in_primary_cockpit_strip_html(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()

        html = _fixture_cockpit_current_state_strip_html(_summary(lifecycle))
        self.assertIn("Current-State Summary", html)
        self.assertIn("Runtime", html)
        self.assertIn("Query gate", html)
        self.assertIn("Last operator action", html)
        self.assertIn("Action timeline", html)
        self.assertIn("Operator notes", html)
        self.assertIn("Contract universe", html)
        # No raw JSON braces dumped into the strip.
        self.assertNotIn("{", html)

    def test_contract_readiness_detail_renders_plain_html(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()

        detail = _cockpit_surface(lifecycle)["contract_readiness_detail"]
        html = _fixture_cockpit_contract_readiness_detail_html(detail)
        self.assertIn("Contract Readiness Detail", html)
        for contract in ("ES", "NQ", "CL", "6E", "MGC"):
            self.assertIn(contract, html)
        self.assertIn("Micro Gold", html)
        self.assertNotIn("<strong>ZN</strong>", html)
        self.assertNotIn("<strong>GC</strong>", html)
        self.assertNotIn("{", html)
        self.assertNotIn("1.125", html)
        self.assertNotIn("100.0", html)
        for phrase in ("take trade", "buy", "sell", "strongest", "ranking"):
            self.assertNotIn(phrase, html.lower())

    def test_summary_does_not_create_query_ready(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()

        summary = _summary(lifecycle)
        rendered = json.dumps(summary, sort_keys=True)
        self.assertNotIn("QUERY_READY", rendered)
        self.assertNotIn("real_trigger_state_result_and_pipeline_gate", rendered)
        self.assertIs(summary["creates_query_ready"], False)

        # Adding a row that *says* enabled via display would not flip provenance:
        # the builder only counts existing row states, never invents provenance.
        forged = {
            "supported_contracts": list(final_target_contracts()),
            "rows": [{"contract": "ES", "query_action_state": "ENABLED"}],
        }
        forged_summary = build_cockpit_current_state_summary(forged)
        self.assertIs(forged_summary["creates_query_ready"], False)
        self.assertNotIn("provenance", json.dumps(forged_summary).lower())

    def test_blocked_query_attempt_visible_in_summary_after_action(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            blocked = request_cockpit_manual_query(lifecycle, "NQ")

        summary = _summary(blocked)
        self.assertEqual(summary["last_action_kind"], "MANUAL_QUERY")
        self.assertEqual(summary["last_action_status"], "BLOCKED")
        self.assertIn("blocked", summary["last_action_text"].lower())
        # Timeline reflects the blocked attempt (not silently ignored).
        self.assertEqual(summary["timeline_entry_count"], 1)
        # Per-row block reason is surfaced in plain English.
        self.assertIsNotNone(summary["query_blocked_reason_text"])
        _assert_plain_english_and_bounded(self, summary)

        detail = _cockpit_surface(blocked)["contract_readiness_detail"]
        nq = next(row for row in detail["rows"] if row["contract"] == "NQ")
        self.assertEqual(nq["latest_operator_action_state"], "BLOCKED")
        self.assertIn("blocked", nq["latest_operator_action_text"].lower())
        self.assertIn("blocked", nq["latest_operator_action_blocked_reason"].lower())
        self.assertIn("Wait", nq["next_safe_operator_action"])

    def test_summary_reflects_submitted_action_and_timeline(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            submitted = request_cockpit_manual_query(lifecycle, "ES")

        summary = _summary(submitted)
        self.assertEqual(summary["last_action_kind"], "MANUAL_QUERY")
        self.assertEqual(summary["last_action_status"], "SUBMITTED")
        self.assertEqual(summary["timeline_entry_count"], 1)
        self.assertIn("1 recent operator action", summary["timeline_state_text"])

    def test_summary_reflects_notes_state(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            noted = add_cockpit_operator_note(lifecycle, "watch ES open range")
            noted2 = add_cockpit_operator_note(noted, "MGC dependency fresh")

        summary = _summary(noted2)
        self.assertEqual(summary["notes_entry_count"], 2)
        self.assertIn("2 operator notes", summary["notes_state_text"])
        _assert_plain_english_and_bounded(self, summary)

    def test_manual_query_result_display_remains_bounded_and_sanitized(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            submitted = request_cockpit_manual_query(lifecycle, "ES")

        surface = _cockpit_surface(submitted)
        rendered = json.dumps(surface["current_state_summary"], sort_keys=True).lower()
        for raw in ("1.125", "100.0", "7175.25"):
            self.assertNotIn(raw, rendered)
        for forbidden in ("client_secret", "api_key", "token", "authorization", "correl"):
            self.assertNotIn(forbidden, rendered)

    def test_runtime_cache_derived_readiness_preserved_across_actions(self) -> None:
        snapshot = _runtime_cache_snapshot()
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env(runtime_snapshot=snapshot)
            submitted = request_cockpit_manual_query(lifecycle, "ES")
            blocked = request_cockpit_manual_query(lifecycle, "NQ")
            refreshed = refresh_runtime_snapshot(lifecycle)
            reset = reset_session(lifecycle)

        for item in (lifecycle, submitted, blocked, refreshed, reset):
            with self.subTest(action=item.last_action):
                summary = _summary(item)
                self.assertEqual(
                    summary["runtime_readiness_status"], "LIVE_RUNTIME_CONNECTED"
                )
                self.assertTrue(summary["runtime_readiness_preserved"])
                self.assertIn("preserved", summary["runtime_state_text"].lower())
                self.assertIs(item.runtime_snapshot, snapshot)
                detail = _cockpit_surface(item)["contract_readiness_detail"]
                self.assertEqual(
                    [row["contract"] for row in detail["rows"]],
                    ["ES", "NQ", "CL", "6E", "MGC"],
                )
                self.assertFalse(detail["creates_query_ready"])

    def test_missing_required_fields_still_fail_closed_in_summary(self) -> None:
        # CL fixture has stale quote + stale bar; 6E has a missing dependency;
        # NQ has missing chart bars. All must remain blocked in the summary count.
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()

        summary = _summary(lifecycle)
        rows = {
            r["contract"]: r
            for r in _cockpit_surface(lifecycle)["rows"]
        }
        self.assertEqual(rows["NQ"]["query_action_state"], "DISABLED")
        self.assertEqual(rows["CL"]["query_action_state"], "DISABLED")
        self.assertEqual(rows["6E"]["query_action_state"], "DISABLED")
        self.assertEqual(summary["query_blocked_count"], 3)
        self.assertIn("fail-closed", summary["query_state_text"].lower())
        detail_rows = {
            r["contract"]: r
            for r in _cockpit_surface(lifecycle)["contract_readiness_detail"]["rows"]
        }
        self.assertIn("chart", detail_rows["NQ"]["blocked_reason"])
        self.assertIn("stale", detail_rows["CL"]["blocked_reason"])
        self.assertIn("dependency", detail_rows["6E"]["blocked_reason"])

    def test_zn_and_gc_remain_excluded_from_summary_universe(self) -> None:
        self.assertEqual(excluded_final_target_contracts(), ("ZN", "GC"))
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()

        summary = _summary(lifecycle)
        self.assertEqual(
            tuple(summary["supported_contracts"]), final_target_contracts()
        )
        self.assertNotIn("ZN", summary["supported_contracts"])
        self.assertNotIn("GC", summary["supported_contracts"])
        self.assertIn("ZN and GC remain excluded", summary["contract_universe_text"])

    def test_mgc_is_micro_gold_and_not_mapped_to_gc(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()

        summary = _summary(lifecycle)
        self.assertIn("MGC", summary["supported_contracts"])
        universe = summary["contract_universe_text"]
        self.assertIn("MGC is Micro Gold", universe)
        # The summary universe text must not describe MGC as GC, nor map them.
        self.assertNotIn("MGC is Gold", universe)
        self.assertNotIn("MGC is GC", universe)
        self.assertNotIn("MGC (GC)", universe)
        self.assertNotIn("MGC=GC", universe)
        # GC remains an excluded contract, never a supported one.
        self.assertNotIn("GC", summary["supported_contracts"])
        # MGC is a supported contract and is its own token, not a GC alias.
        self.assertIn("MGC", final_target_contracts())
        self.assertNotIn("GC", final_target_contracts())

    def test_default_launch_remains_non_live_with_summary(self) -> None:
        surface = build_fixture_cockpit_shell_surface()
        summary = surface["current_state_summary"]
        self.assertFalse(summary["default_launch_live"])
        self.assertEqual(surface["mode"], "fixture_dry_run_non_live")

    def test_summary_carries_no_broker_or_pnl_fields(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            submitted = request_cockpit_manual_query(lifecycle, "ES")
            noted = add_cockpit_operator_note(submitted, "context note")

        rendered = json.dumps(_summary(noted), sort_keys=True).lower()
        rendered += json.dumps(
            _cockpit_surface(noted)["contract_readiness_detail"],
            sort_keys=True,
        ).lower()
        for forbidden in (
            "broker",
            "order",
            "fill",
            "pnl",
            "p_and_l",
            "position",
            "balance",
            "routing",
        ):
            self.assertNotIn(forbidden, rendered)

    def test_summary_updates_across_refresh_and_reset(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            noted = add_cockpit_operator_note(lifecycle, "persist across refresh")
            refreshed = refresh_runtime_snapshot(noted)
            reset = reset_session(noted)

        # Notes persist; summary reflects them after refresh and reset.
        self.assertEqual(_summary(refreshed)["notes_entry_count"], 1)
        self.assertEqual(_summary(reset)["notes_entry_count"], 1)
        # Refresh records a timeline action; summary reflects it.
        self.assertGreaterEqual(_summary(refreshed)["timeline_entry_count"], 1)
        self.assertEqual(_summary(refreshed)["last_action_status"], "REFRESHED")
        self.assertEqual(_summary(reset)["last_action_status"], "RESET")


if __name__ == "__main__":
    unittest.main()
