from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ntb_marimo_console.launch_config import (
    LaunchArtifacts,
    StartupArtifacts,
    build_launch_artifacts_from_env,
    build_startup_artifacts_from_env,
    load_launch_config_from_env,
    resolve_launch_request_for_profile_id,
)


class LaunchConfigTests(unittest.TestCase):
    def test_defaults_to_fixture_profile(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = load_launch_config_from_env()

        self.assertEqual(config.mode, "fixture_demo")
        self.assertEqual(config.profile.profile_id, "fixture_es_demo")
        self.assertFalse(config.lockout)
        self.assertIsNone(config.fixtures_root)
        self.assertEqual(config.adapter_binding, None)
        self.assertIsNone(config.model_adapter)
        self.assertEqual(config.market_data_config.provider, "disabled")
        self.assertEqual(config.market_data_config.symbol, "")
        self.assertIsNone(config.market_data_config.failure_reason)
        self.assertTrue(config.preflight.passed)

    def test_fixture_market_data_launch_settings_are_carried_as_safe_config_only(self) -> None:
        with patch.dict(
            os.environ,
            {
                "NTB_MARKET_DATA_PROVIDER": "fixture",
                "NTB_MARKET_DATA_SYMBOL": "ES",
            },
            clear=True,
        ):
            config = load_launch_config_from_env()

        self.assertEqual(config.market_data_config.provider, "fixture")
        self.assertEqual(config.market_data_config.symbol, "ES")
        self.assertIsNone(config.market_data_config.failure_reason)

    def test_profile_only_selection_is_sufficient_for_supported_preserved_profile(self) -> None:
        engine_src = str((Path("../../source/ntb_engine/src")).resolve())
        with patch.dict(
            os.environ,
            {
                "NTB_CONSOLE_PROFILE": "preserved_es_phase1",
            },
            clear=True,
        ):
            with patch.object(sys, "path", [engine_src, *sys.path]):
                config = load_launch_config_from_env()

        self.assertEqual(config.mode, "preserved_engine")
        self.assertEqual(config.profile.profile_id, "preserved_es_phase1")
        self.assertEqual(
            config.adapter_binding,
            "ntb_marimo_console.preserved_fixture_adapter:adapter",
        )
        self.assertTrue(callable(getattr(config.model_adapter, "generate_structured", None)))
        self.assertTrue(config.preflight.passed)

    def test_profile_only_selection_is_sufficient_for_second_preserved_profile(self) -> None:
        engine_src = str((Path("../../source/ntb_engine/src")).resolve())
        with patch.dict(
            os.environ,
            {
                "NTB_CONSOLE_PROFILE": "preserved_zn_phase1",
            },
            clear=True,
        ):
            with patch.object(sys, "path", [engine_src, *sys.path]):
                config = load_launch_config_from_env()

        self.assertEqual(config.mode, "preserved_engine")
        self.assertEqual(config.profile.profile_id, "preserved_zn_phase1")
        self.assertEqual(
            config.adapter_binding,
            "ntb_marimo_console.preserved_fixture_adapter:adapter_zn",
        )
        self.assertTrue(callable(getattr(config.model_adapter, "generate_structured", None)))
        self.assertTrue(config.preflight.passed)

    def test_profile_only_selection_is_sufficient_for_third_preserved_profile(self) -> None:
        engine_src = str((Path("../../source/ntb_engine/src")).resolve())
        with patch.dict(
            os.environ,
            {
                "NTB_CONSOLE_PROFILE": "preserved_cl_phase1",
            },
            clear=True,
        ):
            with patch.object(sys, "path", [engine_src, *sys.path]):
                config = load_launch_config_from_env()

        self.assertEqual(config.mode, "preserved_engine")
        self.assertEqual(config.profile.profile_id, "preserved_cl_phase1")
        self.assertEqual(
            config.adapter_binding,
            "ntb_marimo_console.preserved_fixture_adapter:adapter_cl",
        )
        self.assertTrue(callable(getattr(config.model_adapter, "generate_structured", None)))
        self.assertTrue(config.preflight.passed)

    def test_explicit_mode_mismatch_fails_closed(self) -> None:
        with patch.dict(
            os.environ,
            {
                "NTB_CONSOLE_MODE": "fixture_demo",
                "NTB_CONSOLE_PROFILE": "preserved_es_phase1",
            },
            clear=True,
        ):
            with self.assertRaises(RuntimeError):
                load_launch_config_from_env()

    def test_explicit_profile_request_uses_profile_defaults(self) -> None:
        request = resolve_launch_request_for_profile_id("preserved_zn_phase1", use_env_defaults=False)

        self.assertEqual(request.mode, "preserved_engine")
        self.assertEqual(request.profile.profile_id, "preserved_zn_phase1")
        self.assertEqual(
            request.adapter_binding,
            "ntb_marimo_console.preserved_fixture_adapter:adapter_zn",
        )
        self.assertFalse(request.lockout)

    def test_preserved_profile_loads_model_adapter_override_from_env(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            module_dir = Path(temp_dir)
            module_path = module_dir / "fake_adapter_module.py"
            module_path.write_text(
                "\n".join(
                    [
                        "class Adapter:",
                        "    def generate_structured(self, request):",
                        "        return {'ok': True}",
                        "",
                        "adapter = Adapter()",
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {
                    "NTB_CONSOLE_PROFILE": "preserved_es_phase1",
                    "NTB_MODEL_ADAPTER_REF": "fake_adapter_module:adapter",
                },
                clear=True,
            ):
                with patch.object(sys, "path", [temp_dir, *sys.path]):
                    config = load_launch_config_from_env()

        self.assertEqual(config.mode, "preserved_engine")
        self.assertEqual(config.profile.profile_id, "preserved_es_phase1")
        self.assertEqual(config.adapter_binding, "fake_adapter_module:adapter")
        self.assertTrue(callable(getattr(config.model_adapter, "generate_structured", None)))
        self.assertTrue(config.preflight.passed)

    def test_build_launch_artifacts_returns_named_object_not_tuple(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            artifacts = build_launch_artifacts_from_env()

        self.assertIsInstance(artifacts, LaunchArtifacts)
        self.assertEqual(artifacts.config.mode, "fixture_demo")
        self.assertEqual(artifacts.config.profile.profile_id, "fixture_es_demo")
        self.assertEqual(artifacts.shell["runtime"]["runtime_mode"], "fixture_demo")
        self.assertEqual(artifacts.shell["runtime"]["profile_id"], "fixture_es_demo")
        self.assertEqual(artifacts.shell["runtime"]["preflight_status"], "PASS")
        self.assertEqual(artifacts.shell["runtime"]["startup_readiness_state"], "OPERATOR_SURFACES_READY")
        self.assertTrue(artifacts.shell["runtime"]["operator_ready"])

    def test_build_startup_artifacts_returns_ready_fixture_shell(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            artifacts = build_startup_artifacts_from_env()

        self.assertIsInstance(artifacts, StartupArtifacts)
        self.assertTrue(artifacts.ready)
        self.assertIsNotNone(artifacts.config)
        self.assertEqual(artifacts.shell["startup"]["selected_profile_id"], "fixture_es_demo")
        self.assertEqual(artifacts.shell["startup"]["readiness_state"], "OPERATOR_SURFACES_READY")
        self.assertEqual(artifacts.shell["surfaces"]["live_observables"]["market_data"]["status"], "Market data unavailable")

    def test_fixture_market_data_provider_without_quote_injection_stays_safe_and_unavailable(self) -> None:
        with patch.dict(
            os.environ,
            {
                "NTB_MARKET_DATA_PROVIDER": "fixture",
                "NTB_MARKET_DATA_SYMBOL": "ES",
            },
            clear=True,
        ):
            artifacts = build_startup_artifacts_from_env()

        self.assertIsInstance(artifacts, StartupArtifacts)
        self.assertTrue(artifacts.ready)
        self.assertIsNotNone(artifacts.config)
        self.assertEqual(artifacts.config.market_data_config.provider, "fixture")
        self.assertEqual(artifacts.shell["surfaces"]["live_observables"]["market_data"]["status"], "Market data unavailable")
        self.assertEqual(artifacts.shell["runtime"]["runtime_mode"], "fixture_demo")
        self.assertEqual(artifacts.shell["runtime"]["session_state"], "LIVE_QUERY_ELIGIBLE")

    def test_build_startup_artifacts_blocks_unsupported_profile_without_crashing(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "unknown_profile"}, clear=True):
            artifacts = build_startup_artifacts_from_env()

        self.assertIsInstance(artifacts, StartupArtifacts)
        self.assertFalse(artifacts.ready)
        self.assertIsNone(artifacts.config)
        self.assertEqual(artifacts.shell["startup"]["readiness_state"], "BLOCKED")
        self.assertFalse(artifacts.shell["startup"]["operator_ready"])
        self.assertEqual(artifacts.shell["runtime"]["preflight_status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
