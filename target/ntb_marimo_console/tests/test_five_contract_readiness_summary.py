from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from ntb_marimo_console.contract_universe import final_target_contracts
from ntb_marimo_console.launch_config import build_startup_artifacts_from_env
from ntb_marimo_console.readiness_summary import (
    FIVE_CONTRACT_READINESS_SUMMARY_SCHEMA,
    LIVE_RUNTIME_CACHE_STATUS,
    LIVE_RUNTIME_READINESS_STATUS,
    build_five_contract_readiness_summary,
    build_five_contract_readiness_summary_surface,
)
from ntb_marimo_console.ui.marimo_phase1_renderer import build_phase1_render_plan


EXPECTED_PROFILE_BY_CONTRACT: dict[str, str] = {
    "ES": "preserved_es_phase1",
    "NQ": "preserved_nq_phase1",
    "CL": "preserved_cl_phase1",
    "6E": "preserved_6e_phase1",
    "MGC": "preserved_mgc_phase1",
}


def _engine_src_path() -> str:
    return str(Path("../../source/ntb_engine/src").resolve())


class FiveContractReadinessSummaryTests(unittest.TestCase):
    def test_summary_contains_each_final_target_contract_once(self) -> None:
        summary = build_five_contract_readiness_summary()
        rows = summary.to_dict()["rows"]
        contracts = [row["contract"] for row in rows]

        self.assertEqual(tuple(contracts), final_target_contracts())
        self.assertEqual(tuple(contracts), ("ES", "NQ", "CL", "6E", "MGC"))
        self.assertEqual(len(set(contracts)), 5)

    def test_excluded_contracts_are_not_readiness_rows(self) -> None:
        surface = build_five_contract_readiness_summary_surface()
        rows = surface["rows"]
        contracts = {row["contract"] for row in rows}

        self.assertEqual(surface["excluded_contracts"], ["ZN", "GC"])
        self.assertNotIn("ZN", contracts)
        self.assertNotIn("GC", contracts)

    def test_mgc_is_not_labeled_or_mapped_as_gc(self) -> None:
        surface = build_five_contract_readiness_summary_surface()
        rows = surface["rows"]
        mgc_rows = [row for row in rows if row["contract"] == "MGC"]

        self.assertEqual(len(mgc_rows), 1)
        self.assertEqual(mgc_rows[0]["runtime_profile_id"], "preserved_mgc_phase1")
        self.assertNotEqual(mgc_rows[0]["contract"], "GC")
        self.assertNotIn("preserved_gc_phase1", [row["runtime_profile_id"] for row in rows])

    def test_summary_construction_requires_no_schwab_credentials(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            surface = build_five_contract_readiness_summary_surface()

        self.assertFalse(surface["live_credentials_required"])
        self.assertFalse(surface["default_launch_live"])
        self.assertEqual(surface["mode"], "non_live_fixture_safe")

    def test_default_market_data_state_remains_non_live_unavailable(self) -> None:
        surface = build_five_contract_readiness_summary_surface()

        for row in surface["rows"]:
            with self.subTest(contract=row["contract"]):
                self.assertTrue(row["operator_ready"])
                self.assertTrue(row["non_live_fixture_usable"])
                self.assertEqual(row["market_data_status"], "Market data unavailable")
                self.assertFalse(row["live_data_available"])
                self.assertIn("live_market_data", row["missing_live_fields"])

    def test_rows_expose_blocked_and_query_gate_reasons(self) -> None:
        surface = build_five_contract_readiness_summary_surface()

        for row in surface["rows"]:
            with self.subTest(contract=row["contract"]):
                self.assertIn(
                    "live_data_unavailable_non_live_default",
                    row["primary_blocked_reasons"],
                )
                self.assertIn("query_not_ready_reasons", row)
                self.assertIsInstance(row["query_not_ready_reasons"], list)
                if not row["query_ready"]:
                    self.assertIn("query_not_ready", row["primary_blocked_reasons"])
                    self.assertTrue(row["query_not_ready_reasons"])
                self.assertIn(row["query_gate_status"], {"BLOCKED", "QUERY_BLOCKED", "ELIGIBLE"})
                self.assertIn(
                    row["trigger_state_summary"],
                    {
                        "trigger_true",
                        "query_not_ready_no_declared_trigger_true",
                        "trigger_unavailable",
                    },
                )

    def test_rows_cannot_authorize_trade_execution(self) -> None:
        surface = build_five_contract_readiness_summary_surface()

        self.assertFalse(surface["summary_can_authorize_trades"])
        self.assertTrue(surface["manual_execution_only"])
        for row in surface["rows"]:
            with self.subTest(contract=row["contract"]):
                self.assertFalse(row["trade_execution_authorized"])
                self.assertFalse(row["proof_capture_satisfies_live_readiness"])
                self.assertIn("Manual execution only", row["manual_only_boundary"])

    def test_summary_marks_explicit_opt_in_runtime_cache_not_wired(self) -> None:
        surface = build_five_contract_readiness_summary_surface()

        self.assertEqual(surface["live_runtime_readiness_status"], LIVE_RUNTIME_READINESS_STATUS)
        self.assertEqual(surface["live_runtime_readiness_status"], "NOT_WIRED")
        self.assertTrue(surface["explicit_opt_in_runtime_cache_required"])
        self.assertFalse(surface["runtime_cache_bound_to_operator_launch"])
        self.assertFalse(surface["live_runtime_cache_can_authorize_trades"])
        self.assertIn("explicit_opt_in_live_runtime_cache_not_wired", surface["limitations"])
        self.assertIn(
            "operator_launch_does_not_supply_stream_manager_snapshot",
            surface["live_runtime_readiness_blockers"],
        )

        for row in surface["rows"]:
            with self.subTest(contract=row["contract"]):
                self.assertEqual(row["live_runtime_readiness_state"], LIVE_RUNTIME_READINESS_STATUS)
                self.assertEqual(row["runtime_cache_status"], LIVE_RUNTIME_CACHE_STATUS)
                self.assertFalse(row["runtime_cache_bound"])
                self.assertIn(
                    "explicit_opt_in_runtime_cache_reader_not_bound_to_summary",
                    row["runtime_cache_blocked_reasons"],
                )
                self.assertFalse(row["trade_execution_authorized"])

    def test_preserved_engine_remains_decision_authority(self) -> None:
        surface = build_five_contract_readiness_summary_surface(active_profile_id="preserved_es_phase1")

        self.assertEqual(surface["decision_authority"], "preserved_engine_only")
        self.assertEqual(surface["schema"], FIVE_CONTRACT_READINESS_SUMMARY_SCHEMA)
        for row in surface["rows"]:
            self.assertIn("preserved engine remains the only decision authority", row["preserved_engine_authority"])

    def test_profile_ids_match_final_target_runtime_profiles(self) -> None:
        surface = build_five_contract_readiness_summary_surface()

        actual = {row["contract"]: row["runtime_profile_id"] for row in surface["rows"]}
        self.assertEqual(actual, EXPECTED_PROFILE_BY_CONTRACT)

    def test_operator_console_startup_shell_includes_summary_surface(self) -> None:
        engine_src = _engine_src_path()
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            with patch.object(sys, "path", [engine_src, *sys.path]):
                artifacts = build_startup_artifacts_from_env(query_action_requested=False)

        self.assertTrue(artifacts.ready)
        surfaces = artifacts.shell["surfaces"]
        self.assertIn("five_contract_readiness_summary", surfaces)
        summary = surfaces["five_contract_readiness_summary"]
        self.assertEqual(summary["schema"], FIVE_CONTRACT_READINESS_SUMMARY_SCHEMA)
        self.assertEqual(summary["active_profile_id"], "preserved_es_phase1")
        self.assertEqual(
            [row["contract"] for row in summary["rows"]],
            ["ES", "NQ", "CL", "6E", "MGC"],
        )

    def test_renderer_can_synthesize_summary_after_session_shell_rebuild(self) -> None:
        plan = build_phase1_render_plan(
            {
                "title": "NTB Marimo Console",
                "runtime": {"profile_id": "preserved_es_phase1"},
                "surfaces": {},
            }
        )

        summary_sections = [
            section
            for section in plan["sections"]
            if section["key"] == "five_contract_readiness_summary"
        ]
        self.assertEqual(len(summary_sections), 1)
        self.assertEqual(
            summary_sections[0]["panel"]["schema"],
            FIVE_CONTRACT_READINESS_SUMMARY_SCHEMA,
        )
        self.assertEqual(
            [row["contract"] for row in summary_sections[0]["panel"]["rows"]],
            ["ES", "NQ", "CL", "6E", "MGC"],
        )


if __name__ == "__main__":
    unittest.main()
