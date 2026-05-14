"""Tests for the bounded cockpit operator notes surface."""

from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from ntb_marimo_console.cockpit_manual_query import (
    COCKPIT_OPERATOR_NOTE_MAX_TEXT_LENGTH,
    COCKPIT_OPERATOR_NOTES_MAX_ENTRIES,
    append_cockpit_operator_note,
    sanitize_cockpit_operator_note_text,
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
    add_cockpit_operator_note,
    load_session_lifecycle_from_env,
    refresh_runtime_snapshot,
    reload_current_profile,
    request_cockpit_manual_query,
    request_query_action,
    reset_session,
)
from ntb_marimo_console.ui.marimo_phase1_renderer import (
    _fixture_cockpit_operator_notes_html,
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


def _cockpit_notes(lifecycle) -> dict:
    surface = lifecycle.shell["surfaces"]["fixture_cockpit_overview"]
    return surface["operator_notes"]


class CockpitOperatorNotesUnitTests(unittest.TestCase):
    def test_sanitize_rejects_empty_and_whitespace(self) -> None:
        self.assertIsNone(sanitize_cockpit_operator_note_text(""))
        self.assertIsNone(sanitize_cockpit_operator_note_text("   \t\n  "))
        self.assertIsNone(sanitize_cockpit_operator_note_text(None))
        self.assertIsNone(sanitize_cockpit_operator_note_text(123))

    def test_sanitize_trims_and_strips_control_chars(self) -> None:
        cleaned = sanitize_cockpit_operator_note_text("  watch ES open\x00\x07  ")
        self.assertEqual(cleaned, "watch ES open")

    def test_sanitize_bounds_text_length(self) -> None:
        long_text = "x" * (COCKPIT_OPERATOR_NOTE_MAX_TEXT_LENGTH + 250)
        cleaned = sanitize_cockpit_operator_note_text(long_text)
        assert cleaned is not None
        self.assertEqual(len(cleaned), COCKPIT_OPERATOR_NOTE_MAX_TEXT_LENGTH)

    def test_append_bounds_count_and_increments_sequence(self) -> None:
        notes: tuple = ()
        for i in range(COCKPIT_OPERATOR_NOTES_MAX_ENTRIES + 4):
            notes, added = append_cockpit_operator_note(
                notes, text=f"note {i}", recorded_at=NOW,
            )
            self.assertIsNotNone(added)
        self.assertEqual(len(notes), COCKPIT_OPERATOR_NOTES_MAX_ENTRIES)
        sequences = [n.sequence for n in notes]
        self.assertEqual(sequences, sorted(sequences))
        self.assertGreater(sequences[0], 1)

    def test_append_rejects_empty_note_without_changing_history(self) -> None:
        notes, added = append_cockpit_operator_note((), text="first", recorded_at=NOW)
        self.assertIsNotNone(added)
        same, rejected = append_cockpit_operator_note(notes, text="   ", recorded_at=NOW)
        self.assertIsNone(rejected)
        self.assertEqual(same, notes)


class CockpitOperatorNotesLifecycleTests(unittest.TestCase):
    def test_initial_fixture_cockpit_has_empty_notes_surface(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()

        notes = _cockpit_notes(lifecycle)
        self.assertEqual(notes["schema"], "cockpit_operator_notes_v1")
        self.assertEqual(notes["entry_count"], 0)
        self.assertEqual(notes["entries"], [])
        self.assertEqual(notes["max_entries"], COCKPIT_OPERATOR_NOTES_MAX_ENTRIES)
        self.assertEqual(notes["max_text_length"], COCKPIT_OPERATOR_NOTE_MAX_TEXT_LENGTH)
        self.assertEqual(lifecycle.cockpit_operator_notes, ())

    def test_adding_valid_note_stores_it_in_lifecycle_and_surface(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            noted = add_cockpit_operator_note(lifecycle, "watch ES range break", contract="ES")

        self.assertEqual(len(noted.cockpit_operator_notes), 1)
        stored = noted.cockpit_operator_notes[0]
        self.assertEqual(stored.text, "watch ES range break")
        self.assertEqual(stored.contract, "ES")
        self.assertEqual(stored.sequence, 1)
        self.assertEqual(stored.source, "OPERATOR_NOTE")

        notes = _cockpit_notes(noted)
        self.assertEqual(notes["entry_count"], 1)
        self.assertEqual(notes["entries"][0]["text"], "watch ES range break")
        self.assertEqual(notes["entries"][0]["contract"], "ES")
        self.assertEqual(
            noted.shell["lifecycle"]["last_action"], "ADD_COCKPIT_OPERATOR_NOTE"
        )

    def test_added_note_renders_in_primary_cockpit(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            noted = add_cockpit_operator_note(lifecycle, "MGC dependency looks fresh")

        plan = build_primary_cockpit_plan(noted.shell)
        notes_surface = plan["operator_notes"]
        self.assertIsInstance(notes_surface, dict)
        self.assertEqual(notes_surface["entry_count"], 1)

        html = _fixture_cockpit_operator_notes_html(notes_surface)
        self.assertIn("MGC dependency looks fresh", html)
        self.assertIn("Operator Notes", html)

    def test_empty_or_whitespace_note_is_rejected_deterministically(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            rejected_empty = add_cockpit_operator_note(lifecycle, "")
            rejected_ws = add_cockpit_operator_note(lifecycle, "   \t \n ")

        self.assertEqual(rejected_empty.cockpit_operator_notes, ())
        self.assertEqual(rejected_ws.cockpit_operator_notes, ())
        self.assertEqual(_cockpit_notes(rejected_empty)["entry_count"], 0)
        self.assertIn("rejected", rejected_empty.status_summary.lower())

    def test_note_text_length_is_bounded(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            noted = add_cockpit_operator_note(
                lifecycle, "y" * (COCKPIT_OPERATOR_NOTE_MAX_TEXT_LENGTH + 100)
            )

        stored = noted.cockpit_operator_notes[0]
        self.assertEqual(len(stored.text), COCKPIT_OPERATOR_NOTE_MAX_TEXT_LENGTH)

    def test_notes_list_length_is_bounded_and_oldest_pruned(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            current = lifecycle
            for i in range(COCKPIT_OPERATOR_NOTES_MAX_ENTRIES + 5):
                current = add_cockpit_operator_note(current, f"note {i}")

        notes = _cockpit_notes(current)
        self.assertEqual(notes["entry_count"], COCKPIT_OPERATOR_NOTES_MAX_ENTRIES)
        self.assertEqual(len(notes["entries"]), COCKPIT_OPERATOR_NOTES_MAX_ENTRIES)
        sequences = [e["sequence"] for e in notes["entries"]]
        self.assertEqual(sequences, sorted(sequences))
        self.assertGreater(sequences[0], 1, "oldest notes should be pruned")
        # The most recent note text is retained
        self.assertEqual(notes["entries"][-1]["text"], f"note {COCKPIT_OPERATOR_NOTES_MAX_ENTRIES + 4}")

    def test_notes_are_sanitized_in_rendered_html(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            noted = add_cockpit_operator_note(
                lifecycle, "<script>alert('x')</script> & risky \"quote\""
            )

        notes_surface = _cockpit_notes(noted)
        html = _fixture_cockpit_operator_notes_html(notes_surface)
        self.assertNotIn("<script>", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&amp;", html)

    def test_adding_note_does_not_call_pipeline_or_create_query_ready(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            noted = add_cockpit_operator_note(lifecycle, "no pipeline call here")

        before = lifecycle.shell["surfaces"]["fixture_cockpit_overview"]
        after = noted.shell["surfaces"]["fixture_cockpit_overview"]
        # Last query result unchanged (still NOT_SUBMITTED)
        self.assertEqual(after["last_query_result"]["request_status"], "NOT_SUBMITTED")
        self.assertEqual(
            before["last_query_result"]["request_status"],
            after["last_query_result"]["request_status"],
        )
        # Per-contract rows unchanged: no QUERY_READY synthesized
        before_rows = {r["contract"]: r for r in before["rows"]}
        after_rows = {r["contract"]: r for r in after["rows"]}
        for contract, row in after_rows.items():
            self.assertEqual(
                row["query_action_state"],
                before_rows[contract]["query_action_state"],
            )
            self.assertEqual(
                row["query_ready_provenance"],
                before_rows[contract]["query_ready_provenance"],
            )

    def test_adding_note_does_not_alter_readiness_or_provenance(self) -> None:
        snapshot = _runtime_cache_snapshot()
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env(runtime_snapshot=snapshot)
            noted = add_cockpit_operator_note(lifecycle, "readiness must be untouched")

        before = lifecycle.shell["surfaces"]["five_contract_readiness_summary"]
        after = noted.shell["surfaces"]["five_contract_readiness_summary"]
        self.assertEqual(after["readiness_source"], before["readiness_source"])
        self.assertEqual(
            after["live_runtime_readiness_status"],
            before["live_runtime_readiness_status"],
        )
        self.assertEqual(
            after["runtime_cache_bound_to_operator_launch"],
            before["runtime_cache_bound_to_operator_launch"],
        )
        self.assertIs(noted.runtime_snapshot, snapshot)
        action = noted.shell["surfaces"]["fixture_cockpit_overview"]["operator_action_status"]
        # Operator action status (timeline-driven) is untouched by a note
        self.assertEqual(action["action_kind"], "IDLE")

    def test_notes_survive_refresh_and_reset(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            noted = add_cockpit_operator_note(lifecycle, "persist me across refresh")
            refreshed_runtime = refresh_runtime_snapshot(noted)
            reloaded = reload_current_profile(noted)
            reset = reset_session(noted)

        for item in (refreshed_runtime, reloaded, reset):
            with self.subTest(action=item.last_action):
                notes = _cockpit_notes(item)
                self.assertEqual(notes["entry_count"], 1)
                self.assertEqual(notes["entries"][0]["text"], "persist me across refresh")
                self.assertEqual(len(item.cockpit_operator_notes), 1)

    def test_notes_coexist_with_manual_query_timeline(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            noted = add_cockpit_operator_note(lifecycle, "before the query")
            submitted = request_cockpit_manual_query(noted, "ES")
            blocked = request_cockpit_manual_query(submitted, "NQ")

        # Timeline still records the manual query events (PROMPT 102 intact)
        timeline = blocked.shell["surfaces"]["fixture_cockpit_overview"][
            "operator_action_timeline"
        ]
        statuses = [e["action_status"] for e in timeline["entries"]]
        self.assertEqual(statuses, ["SUBMITTED", "BLOCKED"])
        # Notes survive the manual query actions
        notes = _cockpit_notes(blocked)
        self.assertEqual(notes["entry_count"], 1)
        self.assertEqual(notes["entries"][0]["text"], "before the query")

    def test_runtime_cache_derived_readiness_preserved_across_actions_with_notes(self) -> None:
        snapshot = _runtime_cache_snapshot()
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env(runtime_snapshot=snapshot)
            noted = add_cockpit_operator_note(lifecycle, "context note")
            submitted = request_cockpit_manual_query(noted, "ES")
            blocked = request_cockpit_manual_query(noted, "NQ")
            refreshed = refresh_runtime_snapshot(noted)
            reset = reset_session(noted)

        for item in (noted, submitted, blocked, refreshed, reset):
            with self.subTest(action=item.last_action):
                summary = item.shell["surfaces"]["five_contract_readiness_summary"]
                self.assertEqual(summary["readiness_source"], "runtime_cache_derived")
                self.assertEqual(
                    summary["live_runtime_readiness_status"], "LIVE_RUNTIME_CONNECTED"
                )
                self.assertTrue(summary["runtime_cache_bound_to_operator_launch"])
                self.assertIs(item.runtime_snapshot, snapshot)

    def test_missing_chart_bars_still_block_with_note_present(self) -> None:
        snapshot = _runtime_cache_snapshot()
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_nq_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env(runtime_snapshot=snapshot)
            noted = add_cockpit_operator_note(lifecycle, "NQ note")
            blocked = request_cockpit_manual_query(noted, "NQ")

        rows = blocked.shell["surfaces"]["fixture_cockpit_overview"]["rows"]
        nq_row = next(r for r in rows if r["contract"] == "NQ")
        self.assertEqual(nq_row["chart_status"], "chart missing")
        self.assertEqual(nq_row["query_action_state"], "DISABLED")
        self.assertEqual(nq_row["last_query_status"], "BLOCKED")
        # Note still present
        self.assertEqual(_cockpit_notes(blocked)["entry_count"], 1)

    def test_missing_required_quote_fields_still_fail_closed_with_note(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            noted = add_cockpit_operator_note(lifecycle, "CL note")
            blocked = request_cockpit_manual_query(noted, "CL")

        rows = blocked.shell["surfaces"]["fixture_cockpit_overview"]["rows"]
        cl_row = next(r for r in rows if r["contract"] == "CL")
        self.assertEqual(cl_row["query_action_state"], "DISABLED")
        self.assertEqual(_cockpit_notes(blocked)["entry_count"], 1)

    def test_display_cannot_create_query_ready_via_notes_surface(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            noted = add_cockpit_operator_note(lifecycle, "display-only note")

        notes_surface = _cockpit_notes(noted)
        rendered = json.dumps(notes_surface, sort_keys=True)
        self.assertNotIn("QUERY_READY", rendered)
        self.assertNotIn("real_trigger_state_result_and_pipeline_gate", rendered)

    def test_zn_and_gc_remain_excluded_and_notes_do_not_promote_them(self) -> None:
        self.assertEqual(excluded_final_target_contracts(), ("ZN", "GC"))
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            noted = add_cockpit_operator_note(lifecycle, "ZN thoughts", contract="ZN")

        # Note records the operator's free-text contract context but does not
        # add ZN to the supported cockpit universe.
        surface = noted.shell["surfaces"]["fixture_cockpit_overview"]
        row_contracts = {r["contract"] for r in surface["rows"]}
        self.assertNotIn("ZN", row_contracts)
        self.assertNotIn("GC", row_contracts)
        self.assertNotIn("ZN", surface["supported_contracts"])
        self.assertEqual(
            tuple(surface["supported_contracts"]), final_target_contracts()
        )

    def test_mgc_remains_micro_gold_with_notes(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            noted = add_cockpit_operator_note(lifecycle, "MGC watch", contract="MGC")

        surface = noted.shell["surfaces"]["fixture_cockpit_overview"]
        mgc_row = next(r for r in surface["rows"] if r["contract"] == "MGC")
        self.assertEqual(mgc_row["profile_label"], "Micro Gold")
        note = _cockpit_notes(noted)["entries"][0]
        self.assertEqual(note["contract"], "MGC")

    def test_default_launch_remains_non_live_with_notes_surface(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()

        cockpit = lifecycle.shell["surfaces"]["fixture_cockpit_overview"]
        self.assertEqual(cockpit["mode"], "fixture_dry_run_non_live")
        self.assertFalse(cockpit["default_launch_live"])
        self.assertEqual(cockpit["operator_notes"]["entry_count"], 0)

    def test_notes_surface_excludes_raw_and_credential_values(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            noted = add_cockpit_operator_note(lifecycle, "1.125 looks like a quote but is text")

        notes_surface = _cockpit_notes(noted)
        rendered = json.dumps(notes_surface, sort_keys=True).lower()
        for forbidden in (
            "client_secret",
            "api_key",
            "token_path",
            "authorization",
            "customer_id",
            "correl",
            "account_id",
        ):
            self.assertNotIn(forbidden, rendered)
        for entry in notes_surface["entries"]:
            self.assertFalse(entry["raw_quote_values_included"])
            self.assertFalse(entry["raw_bar_values_included"])
            self.assertFalse(entry["raw_streamer_payloads_included"])

    def test_bounded_query_action_does_not_clear_notes(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            noted = add_cockpit_operator_note(lifecycle, "keep me through bounded query")
            queried = request_query_action(noted)

        self.assertEqual(_cockpit_notes(queried)["entry_count"], 1)

    def test_no_broker_or_pnl_fields_in_notes_surface(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            noted = add_cockpit_operator_note(lifecycle, "annotation only")

        rendered = json.dumps(_cockpit_notes(noted), sort_keys=True).lower()
        for forbidden in ("broker", "order", "fill", "pnl", "p_and_l", "position", "balance"):
            self.assertNotIn(forbidden, rendered)


if __name__ == "__main__":
    unittest.main()
