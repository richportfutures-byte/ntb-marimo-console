from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from ntb_marimo_console.contract_universe import final_target_contracts
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
    _fixture_cockpit_event_replay_html,
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


def _cockpit(lifecycle) -> dict:
    return lifecycle.shell["surfaces"]["fixture_cockpit_overview"]


def _replay(lifecycle) -> dict:
    return _cockpit(lifecycle)["cockpit_event_replay"]


def _event_types(lifecycle) -> list[str]:
    return [record["event_type"] for record in _replay(lifecycle)["records"]]


class CockpitEvidenceReplayTests(unittest.TestCase):
    def test_default_fixture_launch_has_empty_review_only_replay_surface(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()

        replay = _replay(lifecycle)
        self.assertEqual(replay["schema"], "cockpit_event_replay_surface_v1")
        self.assertEqual(replay["event_count"], 0)
        self.assertEqual(tuple(replay["supported_contracts"]), final_target_contracts())
        self.assertEqual(replay["excluded_contracts"], ["ZN", "GC"])
        self.assertFalse(replay["replay_can_authorize_trades"])
        self.assertFalse(replay["evidence_can_create_query_ready"])
        self.assertFalse(_cockpit(lifecycle)["default_launch_live"])

    def test_operator_note_feeds_evidence_without_changing_readiness(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            noted = add_cockpit_operator_note(lifecycle, "watch ES range", contract="ES")

        replay = _replay(noted)
        self.assertEqual(_event_types(noted), ["operator_note_added"])
        record = replay["records"][0]
        self.assertEqual(record["contract"], "ES")
        self.assertEqual(record["operator_note"], "watch ES range")
        self.assertEqual(record["data_quality"]["source_surface"], "operator_notes")
        self.assertEqual(
            record["data_quality"]["replay_safety_classification"],
            "review_only_non_authoritative_non_signal",
        )
        before_rows = {row["contract"]: row for row in _cockpit(lifecycle)["rows"]}
        after_rows = {row["contract"]: row for row in _cockpit(noted)["rows"]}
        self.assertEqual(
            after_rows["NQ"]["query_action_state"],
            before_rows["NQ"]["query_action_state"],
        )
        self.assertEqual(
            after_rows["NQ"]["query_ready_provenance"],
            before_rows["NQ"]["query_ready_provenance"],
        )

    def test_blocked_query_attempt_is_captured_as_blocked_not_submitted(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            blocked = request_cockpit_manual_query(lifecycle, "NQ")

        types = _event_types(blocked)
        self.assertEqual(types, ["query_blocked", "latest_action_state_changed"])
        replay = _replay(blocked)
        blocked_record = replay["records"][0]
        self.assertEqual(blocked_record["contract"], "NQ")
        self.assertEqual(blocked_record["data_quality"]["request_status"], "BLOCKED")
        self.assertIn("Manual query blocked", blocked_record["data_quality"]["reason"])
        self.assertNotIn("query_submitted", types)
        self.assertEqual(_cockpit(blocked)["last_query_result"]["request_status"], "BLOCKED")

    def test_submitted_query_and_bounded_result_feed_replay_redacted(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            submitted = request_cockpit_manual_query(lifecycle, "ES")

        replay = _replay(submitted)
        self.assertEqual(
            _event_types(submitted),
            [
                "readiness_snapshot_observed",
                "query_submitted",
                "pipeline_result",
                "latest_action_state_changed",
            ],
        )
        es_replay = replay["per_contract_replays"]["ES"]
        self.assertEqual(es_replay["query_eligibility_events"][-1]["event_type"], "query_submitted")
        self.assertEqual(es_replay["pipeline_results"][0]["summary"]["final_decision"], "NO_TRADE")
        self.assertFalse(es_replay["replay_can_authorize_trades"])
        rendered = json.dumps(replay, sort_keys=True).lower()
        for raw in ("1.125", "100.0", "7175.25"):
            self.assertNotIn(raw, rendered)
        for forbidden in (
            "client_secret",
            "api_key",
            "auth_header",
            "bearer",
            "access_token",
            "customer",
            "correl",
            "account",
        ):
            self.assertNotIn(forbidden, rendered)

    def test_refresh_and_reset_capture_contract_attributed_cockpit_events(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            refreshed = refresh_runtime_snapshot(lifecycle)
            reset = reset_session(refreshed)

        refreshed_types = _event_types(refreshed)
        self.assertEqual(refreshed_types.count("cockpit_refreshed"), 5)
        self.assertEqual(refreshed_types.count("readiness_snapshot_observed"), 5)
        reset_types = _event_types(reset)
        self.assertEqual(reset_types.count("cockpit_reset"), 5)
        replay = _replay(reset)
        contracts = {record["contract"] for record in replay["records"]}
        self.assertEqual(contracts, {"ES", "NQ", "CL", "6E", "MGC"})
        self.assertNotIn("ZN", contracts)
        self.assertNotIn("GC", contracts)

    def test_contract_replay_does_not_bleed_between_contracts(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            es_note = add_cockpit_operator_note(lifecycle, "ES only", contract="ES")
            nq_blocked = request_cockpit_manual_query(es_note, "NQ")

        per_contract = _replay(nq_blocked)["per_contract_replays"]
        self.assertEqual(len(per_contract["ES"]["operator_notes"]), 1)
        self.assertEqual(per_contract["NQ"]["operator_notes"], [])
        self.assertEqual(per_contract["NQ"]["cockpit_events"][0]["event_type"], "query_blocked")
        self.assertNotIn("cross_contract", json.dumps(per_contract["ES"]).lower())

    def test_runtime_cache_readiness_preserved_across_cockpit_evidence_actions(self) -> None:
        snapshot = _runtime_cache_snapshot()
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env(runtime_snapshot=snapshot)
            noted = add_cockpit_operator_note(lifecycle, "readiness unchanged", contract="ES")
            blocked = request_cockpit_manual_query(noted, "NQ")
            submitted = request_cockpit_manual_query(blocked, "ES")
            refreshed = refresh_runtime_snapshot(submitted)
            reset = reset_session(refreshed)

        for item in (noted, blocked, submitted, refreshed, reset):
            summary = _cockpit(item)["current_state_summary"]
            self.assertEqual(summary["runtime_readiness_status"], "LIVE_RUNTIME_CONNECTED")
            self.assertTrue(summary["runtime_readiness_preserved"])
            self.assertIs(item.runtime_snapshot, snapshot)

    def test_evidence_replay_does_not_create_query_ready_or_trade_automation(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            noted = add_cockpit_operator_note(lifecycle, "context only", contract="MGC")
            blocked = request_cockpit_manual_query(noted, "NQ")

        replay = _replay(blocked)
        rendered = json.dumps(replay, sort_keys=True)
        self.assertNotIn("QUERY_READY", rendered)
        self.assertFalse(replay["evidence_can_create_query_ready"])
        keys = set(_collect_keys(replay))
        for forbidden in (
            "broker",
            "order",
            "account",
            "fill",
            "pnl",
            "position",
            "routing",
        ):
            self.assertNotIn(forbidden, keys)

    def test_missing_required_fields_still_fail_closed_with_evidence_present(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            noted = add_cockpit_operator_note(lifecycle, "review only", contract="ES")

        rows = {row["contract"]: row for row in _cockpit(noted)["rows"]}
        self.assertEqual(rows["NQ"]["query_action_state"], "DISABLED")
        self.assertEqual(rows["CL"]["query_action_state"], "DISABLED")
        self.assertEqual(rows["6E"]["query_action_state"], "DISABLED")
        detail = {row["contract"]: row for row in _cockpit(noted)["contract_readiness_detail"]["rows"]}
        self.assertIn("chart", detail["NQ"]["blocked_reason"])
        self.assertIn("stale", detail["CL"]["blocked_reason"])
        self.assertIn("dependency", detail["6E"]["blocked_reason"])

    def test_mgc_remains_micro_gold_and_rendered_replay_is_plain_html(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            noted = add_cockpit_operator_note(lifecycle, "MGC context", contract="MGC")

        plan = build_primary_cockpit_plan(noted.shell)
        detail_rows = {
            row["contract"]: row
            for row in plan["contract_readiness_detail"]["rows"]
        }
        self.assertEqual(detail_rows["MGC"]["display_name"], "Micro Gold")
        self.assertNotEqual(detail_rows["MGC"]["display_name"], "GC")
        html = _fixture_cockpit_event_replay_html(plan["cockpit_event_replay"])
        self.assertIn("Cockpit Evidence Replay", html)
        self.assertIn("MGC", html)
        self.assertNotIn("<strong>GC</strong>", html)
        self.assertNotIn("{", html)


def _collect_keys(value: object) -> list[str]:
    if isinstance(value, dict):
        keys = list(value)
        for item in value.values():
            keys.extend(_collect_keys(item))
        return keys
    if isinstance(value, list):
        keys: list[str] = []
        for item in value:
            keys.extend(_collect_keys(item))
        return keys
    return []


if __name__ == "__main__":
    unittest.main()
