from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from ntb_marimo_console.contract_universe import (
    excluded_final_target_contracts,
    final_target_contracts,
)
from ntb_marimo_console.launch_config import (
    StartupArtifacts,
    build_startup_artifacts_from_env,
)


FINAL_TARGET_PRESERVED_PROFILE_BY_CONTRACT: dict[str, str] = {
    "ES": "preserved_es_phase1",
    "NQ": "preserved_nq_phase1",
    "CL": "preserved_cl_phase1",
    "6E": "preserved_6e_phase1",
    "MGC": "preserved_mgc_phase1",
}

EXPECTED_COCKPIT_SURFACES: tuple[str, ...] = (
    "session_header",
    "five_contract_readiness_summary",
    "pre_market_brief",
    "readiness_matrix",
    "trigger_table",
    "live_observables",
    "query_action",
)


def _engine_src_path() -> str:
    return str(Path("../../source/ntb_engine/src").resolve())


class FinalTargetWorkstationLaunchSmokeTests(unittest.TestCase):
    def test_final_target_universe_matches_expected_five_contracts(self) -> None:
        self.assertEqual(final_target_contracts(), ("ES", "NQ", "CL", "6E", "MGC"))
        for excluded in ("ZN", "GC"):
            self.assertIn(excluded, excluded_final_target_contracts())
            self.assertNotIn(excluded, final_target_contracts())

    def test_each_final_target_preserved_profile_launches_non_live(self) -> None:
        engine_src = _engine_src_path()
        for contract, profile_id in FINAL_TARGET_PRESERVED_PROFILE_BY_CONTRACT.items():
            with self.subTest(contract=contract, profile=profile_id):
                with patch.dict(
                    os.environ,
                    {"NTB_CONSOLE_PROFILE": profile_id},
                    clear=True,
                ):
                    with patch.object(sys, "path", [engine_src, *sys.path]):
                        artifacts = build_startup_artifacts_from_env()

                self.assertIsInstance(artifacts, StartupArtifacts)
                self.assertTrue(
                    artifacts.ready,
                    f"non-live launch must succeed for {profile_id}",
                )
                self.assertIsNotNone(artifacts.config)
                self.assertEqual(artifacts.config.mode, "preserved_engine")
                self.assertEqual(artifacts.config.profile.profile_id, profile_id)
                self.assertEqual(artifacts.config.profile.contract, contract)

                runtime = artifacts.shell["runtime"]
                self.assertEqual(runtime["profile_id"], profile_id)
                self.assertEqual(runtime["preflight_status"], "PASS")
                self.assertEqual(
                    runtime["startup_readiness_state"], "OPERATOR_SURFACES_READY"
                )
                self.assertTrue(runtime["operator_ready"])

                surfaces = artifacts.shell["surfaces"]
                for surface_name in EXPECTED_COCKPIT_SURFACES:
                    self.assertIn(
                        surface_name,
                        surfaces,
                        f"{profile_id} must expose {surface_name} cockpit surface",
                    )

                live_observables = surfaces["live_observables"]
                market_data = live_observables["market_data"]
                self.assertEqual(
                    market_data["status"],
                    "Market data unavailable",
                    f"{profile_id} default launch must remain non-live (no live quote)",
                )

                query_action = surfaces["query_action"]
                for required_key in (
                    "trigger_gate",
                    "readiness_gate",
                    "watchman_gate_status",
                    "live_query_status",
                    "blocked_reasons",
                ):
                    self.assertIn(required_key, query_action)

    def test_default_launch_with_no_env_remains_non_live_fixture_demo(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            artifacts = build_startup_artifacts_from_env()

        self.assertIsInstance(artifacts, StartupArtifacts)
        self.assertTrue(artifacts.ready)
        self.assertIsNotNone(artifacts.config)
        self.assertEqual(artifacts.config.mode, "fixture_demo")
        self.assertEqual(artifacts.config.profile.profile_id, "fixture_es_demo")
        self.assertEqual(
            artifacts.shell["surfaces"]["live_observables"]["market_data"]["status"],
            "Market data unavailable",
        )

    def test_excluded_contract_profile_remains_unselectable_for_final_target(self) -> None:
        for excluded in ("GC", "GC_phase1", "preserved_gc_phase1"):
            with self.subTest(profile=excluded):
                with patch.dict(
                    os.environ, {"NTB_CONSOLE_PROFILE": excluded}, clear=True
                ):
                    artifacts = build_startup_artifacts_from_env()

                self.assertIsInstance(artifacts, StartupArtifacts)
                self.assertFalse(artifacts.ready)
                self.assertIsNone(artifacts.config)
                self.assertEqual(
                    artifacts.shell["startup"]["readiness_state"], "BLOCKED"
                )


if __name__ == "__main__":
    unittest.main()
