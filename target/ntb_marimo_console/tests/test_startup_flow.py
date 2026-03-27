from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ntb_marimo_console.launch_config import build_startup_artifacts_from_env
from ntb_marimo_console.ui.marimo_phase1_renderer import build_startup_status_markdown


class StartupFlowTests(unittest.TestCase):
    def test_startup_flow_fixture_profile_is_operator_ready(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            startup = build_startup_artifacts_from_env()

        self.assertTrue(startup.ready)
        self.assertEqual(startup.shell["startup"]["selected_profile_id"], "fixture_es_demo")
        self.assertEqual(startup.shell["startup"]["running_as"], "Fixture/Demo")
        self.assertEqual(startup.shell["startup"]["readiness_state"], "OPERATOR_SURFACES_READY")
        self.assertEqual(
            startup.shell["startup"]["readiness_history"],
            [
                "APP_LOADED",
                "PROFILE_SELECTED",
                "PREFLIGHT_PASSED",
                "RUNTIME_ASSEMBLED",
                "OPERATOR_SURFACES_READY",
            ],
        )
        self.assertEqual(startup.shell["startup"]["current_session_state"], "LIVE_QUERY_ELIGIBLE")

    def test_startup_flow_preserved_profile_is_operator_ready(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            startup = build_startup_artifacts_from_env()

        self.assertTrue(startup.ready)
        self.assertEqual(startup.shell["startup"]["selected_profile_id"], "preserved_es_phase1")
        self.assertEqual(startup.shell["startup"]["running_as"], "Preserved-Engine-Backed")
        self.assertEqual(startup.shell["startup"]["readiness_state"], "OPERATOR_SURFACES_READY")
        self.assertEqual(startup.shell["startup"]["current_session_state"], "LIVE_QUERY_ELIGIBLE")

    def test_startup_flow_second_preserved_profile_is_operator_ready(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_zn_phase1"}, clear=True):
            startup = build_startup_artifacts_from_env()

        self.assertTrue(startup.ready)
        self.assertEqual(startup.shell["startup"]["selected_profile_id"], "preserved_zn_phase1")
        self.assertEqual(startup.shell["startup"]["running_as"], "Preserved-Engine-Backed")
        self.assertEqual(startup.shell["startup"]["readiness_state"], "OPERATOR_SURFACES_READY")
        self.assertEqual(startup.shell["startup"]["current_session_state"], "LIVE_QUERY_ELIGIBLE")

    def test_fixture_profile_query_action_completion_reaches_decision_and_audit_ready(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            startup = build_startup_artifacts_from_env(query_action_requested=True)

        self.assertTrue(startup.ready)
        self.assertEqual(startup.shell["workflow"]["query_action_status"], "COMPLETED")
        self.assertTrue(startup.shell["workflow"]["decision_review_ready"])
        self.assertTrue(startup.shell["workflow"]["audit_replay_ready"])
        self.assertEqual(startup.shell["runtime"]["session_state"], "AUDIT_REPLAY_READY")

    def test_preserved_profile_query_action_completion_reaches_decision_and_audit_ready(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            startup = build_startup_artifacts_from_env(query_action_requested=True)

        self.assertTrue(startup.ready)
        self.assertEqual(startup.shell["workflow"]["query_action_status"], "COMPLETED")
        self.assertTrue(startup.shell["workflow"]["decision_review_ready"])
        self.assertTrue(startup.shell["workflow"]["audit_replay_ready"])
        self.assertEqual(startup.shell["runtime"]["session_state"], "AUDIT_REPLAY_READY")

    def test_second_preserved_profile_query_action_completion_reaches_decision_and_audit_ready(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_zn_phase1"}, clear=True):
            startup = build_startup_artifacts_from_env(query_action_requested=True)

        self.assertTrue(startup.ready)
        self.assertEqual(startup.shell["workflow"]["query_action_status"], "COMPLETED")
        self.assertTrue(startup.shell["workflow"]["decision_review_ready"])
        self.assertTrue(startup.shell["workflow"]["audit_replay_ready"])
        self.assertEqual(startup.shell["runtime"]["session_state"], "AUDIT_REPLAY_READY")

    def test_blocked_startup_on_failed_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_root = Path("fixtures/golden/phase1")
            artifact_root = Path(temp_dir) / "phase1"
            shutil.copytree(source_root, artifact_root)
            (artifact_root / "premarket" / "ES" / "2026-03-25" / "premarket_packet.json").unlink()

            with patch.dict(
                os.environ,
                {
                    "NTB_CONSOLE_PROFILE": "fixture_es_demo",
                    "NTB_FIXTURES_ROOT": str(artifact_root),
                },
                clear=True,
            ):
                startup = build_startup_artifacts_from_env()

        self.assertFalse(startup.ready)
        self.assertEqual(startup.shell["startup"]["readiness_state"], "BLOCKED")
        self.assertEqual(
            startup.shell["startup"]["readiness_history"],
            ["APP_LOADED", "PROFILE_SELECTED", "BLOCKED"],
        )
        self.assertFalse(startup.shell["startup"]["operator_ready"])
        self.assertEqual(startup.shell["startup"]["current_session_state"], "STARTUP_BLOCKED")
        categories = {check["category"] for check in startup.shell["startup"]["blocking_checks"]}
        self.assertIn("missing_artifact_files", categories)

    def test_unsupported_profile_blocks_startup_with_clear_next_action(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "unsupported_demo"}, clear=True):
            startup = build_startup_artifacts_from_env()

        self.assertFalse(startup.ready)
        self.assertEqual(startup.shell["startup"]["selected_profile_id"], "unsupported_demo")
        self.assertEqual(startup.shell["startup"]["readiness_state"], "BLOCKED")
        self.assertIn("supported profile ids", startup.shell["startup"]["next_action"])

    def test_operator_facing_startup_markdown_is_readable(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            startup = build_startup_artifacts_from_env()

        markdown = build_startup_status_markdown(startup.shell["startup"])
        self.assertIn("## Startup Status", markdown)
        self.assertIn("Supported Profiles", markdown)
        self.assertIn("Operator Ready", markdown)
        self.assertIn("Next Action", markdown)


if __name__ == "__main__":
    unittest.main()
