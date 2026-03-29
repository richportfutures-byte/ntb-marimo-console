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


class SessionLifecycleTests(unittest.TestCase):
    def test_session_reset_success_path_in_fixture_mode(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            queried = request_query_action(lifecycle)
            reset = reset_session(queried)

        self.assertTrue(reset.ready)
        self.assertEqual(reset.shell["lifecycle"]["current_lifecycle_state"], "SESSION_RESET_COMPLETED")
        self.assertEqual(reset.shell["runtime"]["session_state"], "LIVE_QUERY_ELIGIBLE")
        self.assertEqual(reset.shell["workflow"]["query_action_status"], "AVAILABLE")
        self.assertFalse(reset.shell["workflow"]["decision_review_ready"])
        self.assertFalse(reset.shell["workflow"]["audit_replay_ready"])
        self.assertIn("SESSION_RESET_REQUESTED", reset.shell["lifecycle"]["state_history"])
        self.assertIn("SESSION_RESET_COMPLETED", reset.shell["lifecycle"]["state_history"])

    def test_session_reset_success_path_in_preserved_mode(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            queried = request_query_action(lifecycle)
            reset = reset_session(queried)

        self.assertTrue(reset.ready)
        self.assertEqual(reset.shell["lifecycle"]["current_lifecycle_state"], "SESSION_RESET_COMPLETED")
        self.assertEqual(reset.shell["runtime"]["session_state"], "LIVE_QUERY_ELIGIBLE")
        self.assertEqual(reset.shell["workflow"]["query_action_status"], "AVAILABLE")
        self.assertFalse(reset.shell["workflow"]["decision_review_ready"])
        self.assertFalse(reset.shell["workflow"]["audit_replay_ready"])

    def test_session_reset_success_path_in_second_preserved_mode(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_zn_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            queried = request_query_action(lifecycle)
            reset = reset_session(queried)

        self.assertTrue(reset.ready)
        self.assertEqual(reset.shell["lifecycle"]["current_lifecycle_state"], "SESSION_RESET_COMPLETED")
        self.assertEqual(reset.shell["runtime"]["session_state"], "LIVE_QUERY_ELIGIBLE")
        self.assertEqual(reset.shell["workflow"]["query_action_status"], "AVAILABLE")
        self.assertFalse(reset.shell["workflow"]["decision_review_ready"])
        self.assertFalse(reset.shell["workflow"]["audit_replay_ready"])

    def test_refresh_success_path_in_fixture_mode(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            queried = request_query_action(lifecycle)
            refreshed = reload_current_profile(queried)

        self.assertTrue(refreshed.ready)
        self.assertEqual(refreshed.shell["lifecycle"]["current_lifecycle_state"], "REFRESH_COMPLETED")
        self.assertEqual(refreshed.shell["lifecycle"]["reload_result"], "RELOADED_UNCHANGED")
        self.assertEqual(refreshed.shell["runtime"]["session_state"], "LIVE_QUERY_ELIGIBLE")
        self.assertEqual(refreshed.shell["workflow"]["query_action_status"], "AVAILABLE")
        self.assertFalse(refreshed.shell["workflow"]["decision_review_ready"])
        self.assertFalse(refreshed.shell["workflow"]["audit_replay_ready"])

    def test_refresh_success_path_in_preserved_mode(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            queried = request_query_action(lifecycle)
            refreshed = reload_current_profile(queried)

        self.assertTrue(refreshed.ready)
        self.assertEqual(refreshed.shell["lifecycle"]["current_lifecycle_state"], "REFRESH_COMPLETED")
        self.assertEqual(refreshed.shell["lifecycle"]["reload_result"], "RELOADED_UNCHANGED")
        self.assertEqual(refreshed.shell["runtime"]["session_state"], "LIVE_QUERY_ELIGIBLE")
        self.assertEqual(refreshed.shell["workflow"]["query_action_status"], "AVAILABLE")

    def test_refresh_success_path_in_second_preserved_mode(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_zn_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            queried = request_query_action(lifecycle)
            refreshed = reload_current_profile(queried)

        self.assertTrue(refreshed.ready)
        self.assertEqual(refreshed.shell["lifecycle"]["current_lifecycle_state"], "REFRESH_COMPLETED")
        self.assertEqual(refreshed.shell["lifecycle"]["reload_result"], "RELOADED_UNCHANGED")
        self.assertEqual(refreshed.shell["runtime"]["session_state"], "LIVE_QUERY_ELIGIBLE")
        self.assertEqual(refreshed.shell["workflow"]["query_action_status"], "AVAILABLE")

    def test_refresh_fail_closed_on_invalid_reloaded_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_root = Path("fixtures/golden/phase1")
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

        self.assertFalse(refreshed.ready)
        self.assertEqual(refreshed.shell["lifecycle"]["current_lifecycle_state"], "REFRESH_FAILED")
        self.assertEqual(refreshed.shell["startup"]["readiness_state"], "BLOCKED")
        self.assertEqual(refreshed.shell["lifecycle"]["reload_result"], "RELOAD_FAILED")
        self.assertFalse(refreshed.shell["startup"]["operator_ready"])

    def test_query_decision_and_audit_state_after_reset(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            queried = request_query_action(lifecycle)
            reset = reset_session(queried)

        self.assertEqual(queried.shell["runtime"]["session_state"], "AUDIT_REPLAY_READY")
        self.assertTrue(queried.shell["workflow"]["decision_review_ready"])
        self.assertTrue(queried.shell["workflow"]["audit_replay_ready"])
        self.assertEqual(reset.shell["runtime"]["session_state"], "LIVE_QUERY_ELIGIBLE")
        self.assertFalse(reset.shell["workflow"]["decision_review_ready"])
        self.assertFalse(reset.shell["workflow"]["audit_replay_ready"])

    def test_query_decision_and_audit_state_after_refresh(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            queried = request_query_action(lifecycle)
            refreshed = reload_current_profile(queried)

        self.assertEqual(queried.shell["runtime"]["session_state"], "AUDIT_REPLAY_READY")
        self.assertEqual(refreshed.shell["runtime"]["session_state"], "LIVE_QUERY_ELIGIBLE")
        self.assertFalse(refreshed.shell["workflow"]["decision_review_ready"])
        self.assertFalse(refreshed.shell["workflow"]["audit_replay_ready"])

    def test_profile_switch_success_path_es_to_zn_clears_stale_state(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            queried = request_query_action(lifecycle)
            switched = switch_profile(queried, "preserved_zn_phase1")

        self.assertTrue(switched.ready)
        self.assertEqual(switched.shell["startup"]["selected_profile_id"], "preserved_zn_phase1")
        self.assertEqual(switched.shell["runtime"]["profile_id"], "preserved_zn_phase1")
        self.assertEqual(switched.shell["surfaces"]["session_header"]["contract"], "ZN")
        self.assertEqual(switched.shell["workflow"]["query_action_status"], "AVAILABLE")
        self.assertFalse(switched.shell["workflow"]["decision_review_ready"])
        self.assertFalse(switched.shell["workflow"]["audit_replay_ready"])
        self.assertEqual(switched.shell["lifecycle"]["current_lifecycle_state"], "PROFILE_SWITCH_COMPLETED")
        self.assertEqual(switched.shell["lifecycle"]["profile_switch_result"], "SWITCH_COMPLETED")
        self.assertIn("PROFILE_SWITCH_REQUESTED", switched.shell["lifecycle"]["state_history"])
        self.assertIn("PROFILE_SWITCH_VALIDATING", switched.shell["lifecycle"]["state_history"])
        self.assertIn("PROFILE_SWITCH_COMPLETED", switched.shell["lifecycle"]["state_history"])

    def test_profile_switch_success_path_zn_to_cl(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_zn_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            switched = switch_profile(lifecycle, "preserved_cl_phase1")

        self.assertTrue(switched.ready)
        self.assertEqual(switched.shell["startup"]["selected_profile_id"], "preserved_cl_phase1")
        self.assertEqual(switched.shell["runtime"]["profile_id"], "preserved_cl_phase1")
        self.assertEqual(switched.shell["surfaces"]["session_header"]["contract"], "CL")
        self.assertEqual(switched.shell["workflow"]["query_action_status"], "AVAILABLE")
        self.assertFalse(switched.shell["workflow"]["decision_review_ready"])
        self.assertFalse(switched.shell["workflow"]["audit_replay_ready"])

    def test_profile_switch_success_path_cl_to_es(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_cl_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            switched = switch_profile(lifecycle, "preserved_es_phase1")

        self.assertTrue(switched.ready)
        self.assertEqual(switched.shell["startup"]["selected_profile_id"], "preserved_es_phase1")
        self.assertEqual(switched.shell["runtime"]["profile_id"], "preserved_es_phase1")
        self.assertEqual(switched.shell["surfaces"]["session_header"]["contract"], "ES")

    def test_profile_switch_to_blocked_candidate_fails_closed(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            switched = switch_profile(lifecycle, "preserved_nq_phase1")

        self.assertTrue(switched.ready)
        self.assertEqual(switched.shell["startup"]["selected_profile_id"], "preserved_es_phase1")
        self.assertEqual(switched.shell["runtime"]["profile_id"], "preserved_es_phase1")
        self.assertEqual(switched.shell["lifecycle"]["current_lifecycle_state"], "PROFILE_SWITCH_BLOCKED")
        self.assertEqual(switched.shell["lifecycle"]["profile_switch_result"], "SWITCH_BLOCKED")
        self.assertEqual(switched.shell["lifecycle"]["profile_switch_target_id"], "preserved_nq_phase1")
        self.assertIn("not currently supported", switched.shell["lifecycle"]["status_summary"])

    def test_profile_switch_to_unknown_profile_fails_closed(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            switched = switch_profile(lifecycle, "unsupported_profile")

        self.assertTrue(switched.ready)
        self.assertEqual(switched.shell["startup"]["selected_profile_id"], "preserved_es_phase1")
        self.assertEqual(switched.shell["lifecycle"]["current_lifecycle_state"], "PROFILE_SWITCH_BLOCKED")
        self.assertEqual(switched.shell["lifecycle"]["profile_switch_target_id"], "unsupported_profile")
        self.assertIn("supported profile registry", switched.shell["lifecycle"]["status_summary"])

    def test_profile_switch_from_blocked_startup_can_load_supported_profile(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "unsupported_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            switched = switch_profile(lifecycle, "preserved_cl_phase1")

        self.assertTrue(switched.ready)
        self.assertEqual(switched.shell["startup"]["selected_profile_id"], "preserved_cl_phase1")
        self.assertEqual(switched.shell["runtime"]["profile_id"], "preserved_cl_phase1")
        self.assertEqual(switched.shell["surfaces"]["session_header"]["contract"], "CL")


if __name__ == "__main__":
    unittest.main()
