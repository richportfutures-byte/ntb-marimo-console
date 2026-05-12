from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ntb_marimo_console.session_lifecycle import (
    load_session_lifecycle_from_env,
    reload_current_profile,
    request_query_action,
    reset_session,
    switch_profile,
)
from ntb_marimo_console.ui.marimo_phase1_renderer import build_session_evidence_markdown


FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "golden" / "phase1"


class SessionEvidenceTests(unittest.TestCase):
    @staticmethod
    def _outcomes_by_profile(evidence_panel: dict[str, object]) -> dict[str, dict[str, object]]:
        outcomes = evidence_panel["last_known_outcomes"]
        assert isinstance(outcomes, list)
        return {
            str(item["profile_id"]): item
            for item in outcomes
            if isinstance(item, dict)
        }

    def test_recent_session_evidence_recording_for_es(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()

        evidence = lifecycle.shell["evidence"]
        outcomes = self._outcomes_by_profile(evidence)
        es = outcomes["preserved_es_phase1"]

        self.assertEqual(lifecycle.evidence_history[-1].active_profile_id, "preserved_es_phase1")
        self.assertTrue(lifecycle.evidence_history[-1].app_session_id)
        self.assertTrue(lifecycle.evidence_history[-1].recorded_at_utc)
        self.assertEqual(es["preflight_status"], "PASS")
        self.assertEqual(es["startup_outcome"], "OPERATOR_SURFACES_READY")
        # R13: default trigger state is TOUCHED; the gate stays fail-closed.
        self.assertEqual(es["query_eligibility_state"], "BLOCKED")
        self.assertEqual(es["query_action_state"], "BLOCKED")

    def test_recent_session_evidence_recording_for_nq(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_nq_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()

        evidence = lifecycle.shell["evidence"]
        outcomes = self._outcomes_by_profile(evidence)
        nq = outcomes["preserved_nq_phase1"]

        self.assertEqual(lifecycle.evidence_history[-1].active_profile_id, "preserved_nq_phase1")
        self.assertEqual(nq["preflight_status"], "PASS")
        self.assertEqual(nq["startup_outcome"], "OPERATOR_SURFACES_READY")
        # R13: default trigger state is TOUCHED; the gate stays fail-closed.
        self.assertEqual(nq["query_action_state"], "BLOCKED")

    def test_recent_session_evidence_recording_for_cl(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_cl_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()

        evidence = lifecycle.shell["evidence"]
        outcomes = self._outcomes_by_profile(evidence)
        cl = outcomes["preserved_cl_phase1"]

        self.assertEqual(lifecycle.evidence_history[-1].active_profile_id, "preserved_cl_phase1")
        self.assertEqual(cl["preflight_status"], "PASS")
        self.assertEqual(cl["startup_outcome"], "OPERATOR_SURFACES_READY")
        # R13: default trigger state is TOUCHED; the gate stays fail-closed.
        self.assertEqual(cl["query_action_state"], "BLOCKED")

    def test_profile_switch_event_attribution_integrity(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            queried = request_query_action(lifecycle)
            switched = switch_profile(queried, "preserved_nq_phase1")

        latest_record = switched.evidence_history[-1]
        self.assertEqual(latest_record.active_profile_id, "preserved_nq_phase1")
        self.assertEqual(latest_record.originating_profile_id, "preserved_es_phase1")
        self.assertEqual(latest_record.requested_profile_id, "preserved_nq_phase1")
        self.assertEqual(switched.shell["evidence"]["recent_profiles"], ["preserved_nq_phase1", "preserved_es_phase1"])

        outcomes = self._outcomes_by_profile(switched.shell["evidence"])
        es = outcomes["preserved_es_phase1"]
        nq = outcomes["preserved_nq_phase1"]

        self.assertEqual(es["last_action"], "RUN_BOUNDED_QUERY")
        # R13: default trigger state is TOUCHED, so the requested query fails closed
        # at the gate. The attribution chain still records the RUN_BOUNDED_QUERY action
        # for ES; Decision Review stays NOT_READY because no pipeline was executed.
        self.assertEqual(es["query_action_state"], "FAILED")
        self.assertEqual(es["decision_review_state"], "NOT_READY")
        self.assertEqual(nq["last_action"], "SWITCH_PROFILE")
        self.assertEqual(nq["profile_switch_result"], "SWITCH_COMPLETED")
        self.assertEqual(nq["query_action_state"], "BLOCKED")
        self.assertEqual(nq["decision_review_state"], "NOT_READY")

    def test_reset_reload_event_attribution_integrity(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_cl_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            queried = request_query_action(lifecycle)
            reset = reset_session(queried)
            reloaded = reload_current_profile(reset)

        self.assertEqual(reloaded.evidence_history[-1].active_profile_id, "preserved_cl_phase1")
        self.assertEqual(reloaded.evidence_history[-1].lifecycle_action, "RELOAD_CURRENT_PROFILE")
        self.assertEqual(reloaded.evidence_history[-2].active_profile_id, "preserved_cl_phase1")
        self.assertEqual(reloaded.evidence_history[-2].lifecycle_action, "RESET_SESSION")

        outcomes = self._outcomes_by_profile(reloaded.shell["evidence"])
        cl = outcomes["preserved_cl_phase1"]
        self.assertEqual(cl["last_action"], "RELOAD_CURRENT_PROFILE")
        self.assertEqual(cl["reload_result"], "RELOADED_UNCHANGED")
        # R13: default trigger state is TOUCHED; reload leaves the gate fail-closed.
        self.assertEqual(cl["query_action_state"], "BLOCKED")
        self.assertEqual(cl["decision_review_state"], "NOT_READY")

    def test_blocked_outcome_attribution_integrity(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            switched = switch_profile(lifecycle, "preserved_zn_phase1")

        latest_record = switched.evidence_history[-1]
        self.assertEqual(latest_record.active_profile_id, "preserved_es_phase1")
        self.assertEqual(latest_record.originating_profile_id, "preserved_es_phase1")
        self.assertEqual(latest_record.requested_profile_id, "preserved_zn_phase1")
        self.assertEqual(latest_record.profile_switch_result, "SWITCH_BLOCKED")

        outcomes = self._outcomes_by_profile(switched.shell["evidence"])
        self.assertNotIn("preserved_zn_phase1", outcomes)
        self.assertEqual(outcomes["preserved_es_phase1"]["last_action"], "SWITCH_PROFILE")
        self.assertEqual(outcomes["preserved_es_phase1"]["profile_switch_result"], "SWITCH_BLOCKED")

    def test_failure_outcome_attribution_integrity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_root = FIXTURES_ROOT
            artifact_root = Path(temp_dir) / "phase1"
            shutil.copytree(source_root, artifact_root)

            with patch.dict(
                os.environ,
                {
                    "NTB_CONSOLE_PROFILE": "fixture_es_demo",
                    "NTB_FIXTURES_ROOT": str(artifact_root),
                },
                clear=True,
            ):
                lifecycle = load_session_lifecycle_from_env()
                (artifact_root / "premarket" / "ES" / "2026-03-25" / "premarket_packet.json").unlink()
                refreshed = reload_current_profile(lifecycle)

        latest_record = refreshed.evidence_history[-1]
        self.assertEqual(latest_record.active_profile_id, "fixture_es_demo")
        self.assertEqual(latest_record.lifecycle_action, "RELOAD_CURRENT_PROFILE")
        self.assertEqual(latest_record.preflight_status, "FAIL")
        self.assertEqual(latest_record.startup_outcome, "BLOCKED")

        outcomes = self._outcomes_by_profile(refreshed.shell["evidence"])
        fixture = outcomes["fixture_es_demo"]
        self.assertEqual(fixture["last_action"], "RELOAD_CURRENT_PROFILE")
        self.assertEqual(fixture["preflight_status"], "FAIL")
        self.assertEqual(fixture["startup_outcome"], "BLOCKED")
        self.assertEqual(fixture["reload_result"], "RELOAD_FAILED")

    def test_readable_recent_history_rendering(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            queried = request_query_action(lifecycle)
            switched = switch_profile(queried, "preserved_nq_phase1")

        markdown = build_session_evidence_markdown(switched.shell["evidence"])
        self.assertIn("## Recent Session Evidence", markdown)
        self.assertIn("Last Known Outcome By Supported Profile", markdown)
        self.assertIn("Recent Activity", markdown)
        self.assertIn("preserved_es_phase1", markdown)
        self.assertIn("preserved_nq_phase1", markdown)
        self.assertIn("No retained recent-session evidence recorded", markdown)


if __name__ == "__main__":
    unittest.main()
