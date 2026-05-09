from __future__ import annotations

import importlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ntb_marimo_console.launch_config import (
    build_launch_artifacts_from_env,
    build_preflight_report_from_env,
)
from ntb_marimo_console.runtime_diagnostics import (
    DIAG_ADAPTER_RESOLUTION_FAILURE,
    DIAG_INVALID_ARTIFACT_CONTRACT,
    DIAG_MISSING_ARTIFACT_FILES,
    DIAG_MISSING_DEPENDENCY,
    DIAG_UNSUPPORTED_PROFILE,
    LaunchRequest,
    build_preflight_report,
    render_preflight_report,
)
from ntb_marimo_console.runtime_profiles import get_runtime_profile


class RuntimePreflightTests(unittest.TestCase):
    def test_fixture_profile_preflight_passes(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            report = build_preflight_report_from_env()

        self.assertTrue(report.passed)
        self.assertEqual(report.requested_profile_id, "fixture_es_demo")
        self.assertEqual(report.request.mode, "fixture_demo")

    def test_preserved_profile_preflight_passes(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            report = build_preflight_report_from_env()

        self.assertTrue(report.passed)
        self.assertEqual(report.requested_profile_id, "preserved_es_phase1")
        self.assertEqual(report.request.mode, "preserved_engine")

    def test_second_preserved_profile_preflight_passes(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_zn_phase1"}, clear=True):
            report = build_preflight_report_from_env()

        self.assertTrue(report.passed)
        self.assertEqual(report.requested_profile_id, "preserved_zn_phase1")
        self.assertEqual(report.request.mode, "preserved_engine")

    def test_third_preserved_profile_preflight_passes(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_cl_phase1"}, clear=True):
            report = build_preflight_report_from_env()

        self.assertTrue(report.passed)
        self.assertEqual(report.requested_profile_id, "preserved_cl_phase1")
        self.assertEqual(report.request.mode, "preserved_engine")

    def test_6e_preserved_profile_preflight_passes_fixture_safe(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_6e_phase1"}, clear=True):
            report = build_preflight_report_from_env()

        self.assertTrue(report.passed)
        self.assertEqual(report.requested_profile_id, "preserved_6e_phase1")
        self.assertEqual(report.request.mode, "preserved_engine")

    def test_mgc_preserved_profile_preflight_passes_fixture_safe(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_mgc_phase1"}, clear=True):
            report = build_preflight_report_from_env()

        self.assertTrue(report.passed)
        self.assertEqual(report.requested_profile_id, "preserved_mgc_phase1")
        self.assertEqual(report.request.mode, "preserved_engine")

    def test_unsupported_profile_reports_fail_closed_diagnosis(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "unknown_profile"}, clear=True):
            report = build_preflight_report_from_env()

        categories = {check.category for check in report.checks}
        self.assertFalse(report.passed)
        self.assertIn(DIAG_UNSUPPORTED_PROFILE, categories)

    def test_missing_artifact_reports_fail_closed_diagnosis(self) -> None:
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
                report = build_preflight_report_from_env()

        categories = {check.category for check in report.checks}
        self.assertFalse(report.passed)
        self.assertIn(DIAG_MISSING_ARTIFACT_FILES, categories)

    def test_invalid_artifact_reports_fail_closed_diagnosis(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_root = Path("fixtures/golden/phase1")
            artifact_root = Path(temp_dir) / "phase1"
            shutil.copytree(source_root, artifact_root)
            legacy_bundle = {
                "session_date": "2026-03-25",
                "packets": {"ES": {"contract": "ES"}},
                "extensions": {"ES": {}},
            }
            legacy_query = {"market_packet": {"contract": "ES"}}
            (artifact_root / "pipeline" / "ES" / "packet_bundle.watchman.json").write_text(
                json.dumps(legacy_bundle, indent=2),
                encoding="utf-8",
            )
            (artifact_root / "pipeline" / "ES" / "historical_packet.query.json").write_text(
                json.dumps(legacy_query, indent=2),
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {
                    "NTB_CONSOLE_PROFILE": "preserved_es_phase1",
                    "NTB_FIXTURES_ROOT": str(artifact_root),
                },
                clear=True,
            ):
                report = build_preflight_report_from_env()

        categories = {check.category for check in report.checks}
        self.assertFalse(report.passed)
        self.assertIn(DIAG_INVALID_ARTIFACT_CONTRACT, categories)

    def test_second_preserved_profile_invalid_artifact_reports_fail_closed_diagnosis(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_root = Path("fixtures/golden/phase1")
            artifact_root = Path(temp_dir) / "phase1"
            shutil.copytree(source_root, artifact_root)
            legacy_bundle = {
                "session_date": "2026-01-14",
                "packets": {"ZN": {"contract": "ZN"}},
                "extensions": {"ZN": {}},
            }
            legacy_query = {"market_packet": {"contract": "ZN"}}
            (artifact_root / "pipeline" / "ZN" / "packet_bundle.watchman.json").write_text(
                json.dumps(legacy_bundle, indent=2),
                encoding="utf-8",
            )
            (artifact_root / "pipeline" / "ZN" / "historical_packet.query.json").write_text(
                json.dumps(legacy_query, indent=2),
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {
                    "NTB_CONSOLE_PROFILE": "preserved_zn_phase1",
                    "NTB_FIXTURES_ROOT": str(artifact_root),
                },
                clear=True,
            ):
                report = build_preflight_report_from_env()

        categories = {check.category for check in report.checks}
        self.assertFalse(report.passed)
        self.assertIn(DIAG_INVALID_ARTIFACT_CONTRACT, categories)

    def test_missing_adapter_resolution_reports_fail_closed_diagnosis(self) -> None:
        with patch.dict(
            os.environ,
            {
                "NTB_CONSOLE_PROFILE": "preserved_es_phase1",
                "NTB_MODEL_ADAPTER_REF": "missing.module:adapter",
            },
            clear=True,
        ):
            report = build_preflight_report_from_env()

        categories = {check.category for check in report.checks}
        self.assertFalse(report.passed)
        self.assertIn(DIAG_ADAPTER_RESOLUTION_FAILURE, categories)

    def test_missing_dependency_reports_fail_closed_diagnosis(self) -> None:
        profile = get_runtime_profile("preserved_es_phase1")
        request = LaunchRequest(
            mode="preserved_engine",
            profile=profile,
            lockout=False,
            fixtures_root=None,
            adapter_binding=profile.default_model_adapter_ref,
        )
        real_import_module = importlib.import_module

        def fake_import_module(name: str, package: str | None = None):
            if name == "ninjatradebuilder":
                raise ImportError("missing for test")
            return real_import_module(name, package)

        with patch("ntb_marimo_console.runtime_diagnostics.importlib.import_module", side_effect=fake_import_module):
            report = build_preflight_report(request)

        categories = {check.category for check in report.checks}
        self.assertFalse(report.passed)
        self.assertIn(DIAG_MISSING_DEPENDENCY, categories)

    def test_runtime_identity_report_is_explicit_and_readable(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            artifacts = build_launch_artifacts_from_env()
            report_text = render_preflight_report(artifacts.config.preflight)

        runtime = artifacts.shell["runtime"]
        self.assertEqual(runtime["profile_id"], "fixture_es_demo")
        self.assertEqual(runtime["runtime_backend"], "fixture_demo")
        self.assertEqual(runtime["adapter_binding"], "not_required")
        self.assertEqual(runtime["preflight_status"], "PASS")
        self.assertIn("Runtime Preflight: PASS", report_text)
        self.assertIn("Artifact Root", report_text)


if __name__ == "__main__":
    unittest.main()
