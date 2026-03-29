from __future__ import annotations

import importlib
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ntb_marimo_console.preserved_fixture_artifacts import (
    PreservedFixtureNormalizationError,
    build_preserved_fixture_artifacts,
    refresh_preserved_fixture_artifacts,
    write_preserved_fixture_artifacts,
)
from ntb_marimo_console.runtime_modes import build_app_shell_for_profile_id
from ntb_marimo_console.runtime_profiles import get_runtime_profile


class PreservedFixtureArtifactsTests(unittest.TestCase):
    def test_build_artifacts_returns_engine_compatible_shapes(self) -> None:
        artifacts = build_preserved_fixture_artifacts(
            "fixtures/golden/phase1",
            profile=get_runtime_profile("preserved_es_phase1"),
        )

        self.assertIn("shared", artifacts.packet_bundle)
        self.assertIn("contracts", artifacts.packet_bundle)
        self.assertIn("challenge_state", artifacts.query_packet)
        self.assertIn("market_packet", artifacts.query_packet)
        self.assertEqual(
            artifacts.query_packet["market_packet"]["timestamp"],
            "2026-03-25T09:35:00-04:00",
        )
        self.assertEqual(
            artifacts.query_packet["market_packet"]["prior_day_high"],
            5604.0,
        )

    def test_invalid_overlay_inputs_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_root = Path("fixtures/golden/phase1")
            artifact_root = Path(temp_dir) / "phase1"
            shutil.copytree(source_root, artifact_root)
            bad_snapshot = artifact_root / "observables" / "ES" / "trigger_true.json"
            bad_snapshot.write_text(
                '{"contract":"ES","timestamp_et":"2026-03-25T09:35:00-04:00","market":{},"cross_asset":{"breadth":{"current_advancers_pct":0.61}}}',
                encoding="utf-8",
            )

            with self.assertRaises(PreservedFixtureNormalizationError):
                build_preserved_fixture_artifacts(
                    artifact_root,
                    profile=get_runtime_profile("preserved_es_phase1"),
                )

    def test_refresh_rebuilds_profile_aware_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_root = Path("fixtures/golden/phase1")
            artifact_root = Path(temp_dir) / "phase1"
            shutil.copytree(source_root, artifact_root)

            refreshed = refresh_preserved_fixture_artifacts(artifact_root)

        self.assertIn("preserved_es_phase1", refreshed)
        self.assertIn("preserved_cl_phase1", refreshed)
        self.assertIn("preserved_zn_phase1", refreshed)
        self.assertIn("shared", refreshed["preserved_es_phase1"].packet_bundle)
        self.assertIn("contracts", refreshed["preserved_zn_phase1"].packet_bundle)

    def test_preserved_mode_reaches_ready_state_with_actual_engine(self) -> None:
        engine_src = str((Path("../../source/ntb_engine/src")).resolve())
        with tempfile.TemporaryDirectory() as temp_dir:
            source_root = Path("fixtures/golden/phase1")
            artifact_root = Path(temp_dir) / "phase1"
            shutil.copytree(source_root, artifact_root)
            write_preserved_fixture_artifacts(
                artifact_root,
                profile=get_runtime_profile("preserved_es_phase1"),
            )

            with patch.dict(os.environ, {"NTB_STAGE_E_LOG_ROOT": str(Path(temp_dir) / ".stage_e")}):
                with patch.object(sys, "path", [engine_src, *sys.path]):
                    adapter_module = importlib.import_module("ntb_marimo_console.preserved_fixture_adapter")
                    shell = build_app_shell_for_profile_id(
                        profile_id="preserved_es_phase1",
                        fixtures_root=artifact_root,
                        model_adapter=adapter_module.adapter,
                    )

        self.assertEqual(shell["runtime"]["runtime_mode"], "preserved_engine")
        self.assertEqual(shell["runtime"]["profile_id"], "preserved_es_phase1")
        self.assertEqual(shell["runtime"]["session_state"], "AUDIT_REPLAY_READY")
        self.assertIn("DECISION_REVIEW_READY", shell["runtime"]["state_history"])
        self.assertTrue(shell["surfaces"]["decision_review"]["has_result"])
        self.assertEqual(shell["surfaces"]["decision_review"]["final_decision"], "NO_TRADE")
        self.assertEqual(shell["surfaces"]["run_history"]["source"], "stage_e_jsonl")
        self.assertTrue(shell["surfaces"]["audit_replay"]["stage_e_live_backend"])

    def test_third_preserved_profile_reaches_ready_state_with_actual_engine(self) -> None:
        engine_src = str((Path("../../source/ntb_engine/src")).resolve())
        with tempfile.TemporaryDirectory() as temp_dir:
            source_root = Path("fixtures/golden/phase1")
            artifact_root = Path(temp_dir) / "phase1"
            shutil.copytree(source_root, artifact_root)
            write_preserved_fixture_artifacts(
                artifact_root,
                profile=get_runtime_profile("preserved_cl_phase1"),
            )

            with patch.dict(os.environ, {"NTB_STAGE_E_LOG_ROOT": str(Path(temp_dir) / ".stage_e")}):
                with patch.object(sys, "path", [engine_src, *sys.path]):
                    adapter_module = importlib.import_module("ntb_marimo_console.preserved_fixture_adapter")
                    shell = build_app_shell_for_profile_id(
                        profile_id="preserved_cl_phase1",
                        fixtures_root=artifact_root,
                        model_adapter=adapter_module.adapter_cl,
                    )

        self.assertEqual(shell["runtime"]["runtime_mode"], "preserved_engine")
        self.assertEqual(shell["runtime"]["profile_id"], "preserved_cl_phase1")
        self.assertEqual(shell["runtime"]["session_state"], "AUDIT_REPLAY_READY")
        self.assertIn("DECISION_REVIEW_READY", shell["runtime"]["state_history"])
        self.assertTrue(shell["surfaces"]["decision_review"]["has_result"])
        self.assertEqual(shell["surfaces"]["decision_review"]["final_decision"], "NO_TRADE")
        self.assertEqual(shell["surfaces"]["run_history"]["source"], "stage_e_jsonl")
        self.assertTrue(shell["surfaces"]["audit_replay"]["stage_e_live_backend"])
    def test_second_preserved_profile_reaches_ready_state_with_actual_engine(self) -> None:
        engine_src = str((Path("../../source/ntb_engine/src")).resolve())
        with tempfile.TemporaryDirectory() as temp_dir:
            source_root = Path("fixtures/golden/phase1")
            artifact_root = Path(temp_dir) / "phase1"
            shutil.copytree(source_root, artifact_root)
            write_preserved_fixture_artifacts(
                artifact_root,
                profile=get_runtime_profile("preserved_zn_phase1"),
            )

            with patch.dict(os.environ, {"NTB_STAGE_E_LOG_ROOT": str(Path(temp_dir) / ".stage_e")}):
                with patch.object(sys, "path", [engine_src, *sys.path]):
                    adapter_module = importlib.import_module("ntb_marimo_console.preserved_fixture_adapter")
                    shell = build_app_shell_for_profile_id(
                        profile_id="preserved_zn_phase1",
                        fixtures_root=artifact_root,
                        model_adapter=adapter_module.adapter_zn,
                    )

        self.assertEqual(shell["runtime"]["runtime_mode"], "preserved_engine")
        self.assertEqual(shell["runtime"]["profile_id"], "preserved_zn_phase1")
        self.assertEqual(shell["runtime"]["session_state"], "AUDIT_REPLAY_READY")
        self.assertIn("DECISION_REVIEW_READY", shell["runtime"]["state_history"])
        self.assertTrue(shell["surfaces"]["decision_review"]["has_result"])
        self.assertEqual(shell["surfaces"]["decision_review"]["final_decision"], "NO_TRADE")
        self.assertEqual(shell["surfaces"]["run_history"]["source"], "stage_e_jsonl")
        self.assertTrue(shell["surfaces"]["audit_replay"]["stage_e_live_backend"])


if __name__ == "__main__":
    unittest.main()
