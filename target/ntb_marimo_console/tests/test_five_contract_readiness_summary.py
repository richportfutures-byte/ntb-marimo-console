from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from ntb_marimo_console.contract_universe import final_target_contracts
from ntb_marimo_console.launch_config import build_startup_artifacts_from_env
from ntb_marimo_console.market_data.stream_cache import StreamCacheRecord, StreamCacheSnapshot
from ntb_marimo_console.readiness_summary import (
    FIVE_CONTRACT_READINESS_SUMMARY_SCHEMA,
    LIVE_RUNTIME_CONNECTED,
    LIVE_RUNTIME_DISABLED,
    LIVE_RUNTIME_ERROR,
    LIVE_RUNTIME_EXCLUDED_CONTRACT_BLOCKED,
    LIVE_RUNTIME_MISSING_CONTRACT,
    LIVE_RUNTIME_MISSING_REQUIRED_FIELDS,
    LIVE_RUNTIME_NOT_REQUESTED,
    LIVE_RUNTIME_STALE,
    READINESS_SOURCE_FIXTURE_PRESERVED,
    READINESS_SOURCE_RUNTIME_CACHE,
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
RUNTIME_SYMBOL_BY_CONTRACT: dict[str, str] = {
    "ES": "/ESM26",
    "NQ": "/NQM26",
    "CL": "/CLM26",
    "6E": "/6EM26",
    "MGC": "/MGCM26",
    "ZN": "/ZNM26",
    "GC": "/GCM26",
}
NOW = "2026-05-06T14:00:00+00:00"


def _engine_src_path() -> str:
    return str(Path("../../source/ntb_engine/src").resolve())


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


def _runtime_record(
    contract: str,
    *,
    fields: tuple[tuple[str, object], ...] | None = None,
    fresh: bool = True,
) -> StreamCacheRecord:
    symbol = RUNTIME_SYMBOL_BY_CONTRACT[contract]
    return StreamCacheRecord(
        provider="schwab",
        service="LEVELONE_FUTURES",
        symbol=symbol,
        contract=contract,
        message_type="quote",
        fields=fields or _complete_levelone_fields(),
        updated_at=NOW,
        age_seconds=0.0 if fresh else 30.0,
        fresh=fresh,
        blocking_reasons=(),
    )


def _runtime_cache_snapshot(
    *,
    provider_status: str = "active",
    contracts: tuple[str, ...] = ("ES", "NQ", "CL", "6E", "MGC"),
    replacement_records: tuple[StreamCacheRecord, ...] = (),
    extra_records: tuple[StreamCacheRecord, ...] = (),
    blocking_reasons: tuple[str, ...] = (),
    stale_symbols: tuple[str, ...] = (),
) -> StreamCacheSnapshot:
    replacements = {record.contract: record for record in replacement_records}
    records = tuple(replacements.get(contract, _runtime_record(contract)) for contract in contracts)
    return StreamCacheSnapshot(
        generated_at=NOW,
        provider="schwab",
        provider_status=provider_status,  # type: ignore[arg-type]
        cache_max_age_seconds=15.0,
        records=records + extra_records,
        blocking_reasons=blocking_reasons,
        stale_symbols=stale_symbols,
    )


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

    def test_summary_marks_missing_runtime_snapshot_as_safe_non_live_not_requested(self) -> None:
        surface = build_five_contract_readiness_summary_surface()

        self.assertEqual(surface["live_runtime_readiness_status"], LIVE_RUNTIME_NOT_REQUESTED)
        self.assertEqual(surface["readiness_source"], READINESS_SOURCE_FIXTURE_PRESERVED)
        self.assertTrue(surface["explicit_opt_in_runtime_cache_required"])
        self.assertFalse(surface["runtime_cache_bound_to_operator_launch"])
        self.assertFalse(surface["live_runtime_cache_can_authorize_trades"])
        self.assertIn("live_runtime_snapshot_not_requested", surface["limitations"])
        self.assertNotEqual(surface["live_runtime_readiness_status"], "LIVE_RUNTIME_NOT_WIRED")

        for row in surface["rows"]:
            with self.subTest(contract=row["contract"]):
                self.assertEqual(row["readiness_source"], READINESS_SOURCE_FIXTURE_PRESERVED)
                self.assertEqual(row["live_runtime_readiness_state"], LIVE_RUNTIME_NOT_REQUESTED)
                self.assertEqual(row["runtime_cache_status"], "runtime_cache_not_requested")
                self.assertFalse(row["runtime_cache_bound"])
                self.assertIn(
                    "live_runtime_snapshot_not_requested",
                    row["runtime_cache_blocked_reasons"],
                )
                self.assertFalse(row["trade_execution_authorized"])

    def test_summary_consumes_connected_runtime_cache_snapshot(self) -> None:
        surface = build_five_contract_readiness_summary_surface(
            runtime_snapshot=_runtime_cache_snapshot(),
        )

        self.assertEqual(surface["mode"], "runtime_cache_derived")
        self.assertEqual(surface["readiness_source"], READINESS_SOURCE_RUNTIME_CACHE)
        self.assertEqual(surface["live_runtime_readiness_status"], LIVE_RUNTIME_CONNECTED)
        self.assertTrue(surface["runtime_cache_bound_to_operator_launch"])
        self.assertTrue(surface["runtime_cache_snapshot_ready"])
        self.assertEqual(surface["runtime_cache_provider_status"], "connected")
        self.assertEqual([row["contract"] for row in surface["rows"]], ["ES", "NQ", "CL", "6E", "MGC"])

        for row in surface["rows"]:
            with self.subTest(contract=row["contract"]):
                self.assertEqual(row["readiness_source"], READINESS_SOURCE_RUNTIME_CACHE)
                self.assertEqual(row["live_runtime_readiness_state"], LIVE_RUNTIME_CONNECTED)
                self.assertEqual(row["runtime_cache_status"], "runtime_cache_connected")
                self.assertTrue(row["runtime_cache_bound"])
                self.assertTrue(row["live_data_available"])
                self.assertFalse(row["runtime_cache_blocked_reasons"])
                self.assertFalse(row["trade_execution_authorized"])

        mgc = next(row for row in surface["rows"] if row["contract"] == "MGC")
        self.assertEqual(mgc["contract_label"], "Micro Gold")
        self.assertNotEqual(mgc["contract_label"], "GC")

    def test_disabled_stale_and_error_runtime_cache_snapshots_block_readiness(self) -> None:
        cases = (
            ("disabled", LIVE_RUNTIME_DISABLED, "runtime_cache_disabled"),
            ("stale", LIVE_RUNTIME_STALE, "runtime_cache_stale"),
            ("error", LIVE_RUNTIME_ERROR, "runtime_cache_error"),
        )

        for provider_status, expected_state, expected_cache_status in cases:
            with self.subTest(provider_status=provider_status):
                surface = build_five_contract_readiness_summary_surface(
                    runtime_snapshot=_runtime_cache_snapshot(provider_status=provider_status),
                )

                self.assertEqual(surface["readiness_source"], READINESS_SOURCE_RUNTIME_CACHE)
                self.assertEqual(surface["live_runtime_readiness_status"], expected_state)
                for row in surface["rows"]:
                    self.assertEqual(row["live_runtime_readiness_state"], expected_state)
                    self.assertEqual(row["runtime_cache_status"], expected_cache_status)
                    self.assertFalse(row["query_ready"])
                    self.assertFalse(row["non_live_fixture_usable"])
                    self.assertTrue(row["runtime_cache_blocked_reasons"])

    def test_missing_runtime_contract_blocks_affected_contract(self) -> None:
        surface = build_five_contract_readiness_summary_surface(
            runtime_snapshot=_runtime_cache_snapshot(contracts=("ES", "CL", "6E", "MGC")),
        )
        rows = {row["contract"]: row for row in surface["rows"]}

        self.assertEqual(surface["live_runtime_readiness_status"], LIVE_RUNTIME_MISSING_CONTRACT)
        self.assertEqual(rows["NQ"]["live_runtime_readiness_state"], LIVE_RUNTIME_MISSING_CONTRACT)
        self.assertEqual(rows["NQ"]["runtime_cache_status"], "runtime_cache_missing_contract")
        self.assertIn("runtime_cache_record", rows["NQ"]["missing_live_fields"])
        self.assertFalse(rows["NQ"]["query_ready"])
        self.assertEqual(rows["ES"]["live_runtime_readiness_state"], LIVE_RUNTIME_CONNECTED)

    def test_missing_runtime_required_fields_blocks_affected_contract(self) -> None:
        surface = build_five_contract_readiness_summary_surface(
            runtime_snapshot=_runtime_cache_snapshot(
                replacement_records=(
                    _runtime_record("CL", fields=(("quote_time", NOW),)),
                )
            ),
        )
        rows = {row["contract"]: row for row in surface["rows"]}

        self.assertEqual(surface["live_runtime_readiness_status"], LIVE_RUNTIME_MISSING_REQUIRED_FIELDS)
        self.assertEqual(rows["CL"]["live_runtime_readiness_state"], LIVE_RUNTIME_MISSING_REQUIRED_FIELDS)
        self.assertEqual(rows["CL"]["runtime_cache_status"], "runtime_cache_missing_required_fields")
        self.assertIn("bid", rows["CL"]["missing_live_fields"])
        self.assertIn("ask", rows["CL"]["missing_live_fields"])
        self.assertIn("last", rows["CL"]["missing_live_fields"])
        self.assertFalse(rows["CL"]["query_ready"])

    def test_excluded_runtime_records_block_without_adding_zn_or_gc_rows(self) -> None:
        surface = build_five_contract_readiness_summary_surface(
            runtime_snapshot=_runtime_cache_snapshot(
                extra_records=(_runtime_record("ZN"), _runtime_record("GC")),
            ),
        )
        contracts = [row["contract"] for row in surface["rows"]]

        self.assertEqual(contracts, ["ES", "NQ", "CL", "6E", "MGC"])
        self.assertNotIn("ZN", contracts)
        self.assertNotIn("GC", contracts)
        self.assertEqual(surface["excluded_contracts"], ["ZN", "GC"])
        self.assertEqual(surface["live_runtime_readiness_status"], LIVE_RUNTIME_EXCLUDED_CONTRACT_BLOCKED)
        self.assertIn(
            "excluded_contract_in_runtime_snapshot:ZN",
            surface["live_runtime_readiness_blockers"],
        )
        self.assertIn(
            "excluded_contract_in_runtime_snapshot:GC",
            surface["live_runtime_readiness_blockers"],
        )
        for row in surface["rows"]:
            self.assertFalse(row["query_ready"])

    def test_runtime_cache_failure_does_not_fall_back_to_fixture_readiness(self) -> None:
        surface = build_five_contract_readiness_summary_surface(
            runtime_snapshot=_runtime_cache_snapshot(provider_status="disabled"),
        )

        self.assertEqual(surface["readiness_source"], READINESS_SOURCE_RUNTIME_CACHE)
        for row in surface["rows"]:
            self.assertFalse(row["non_live_fixture_usable"])
            self.assertNotEqual(row["market_data_status"], "Market data unavailable")
            self.assertEqual(row["runtime_cache_status"], "runtime_cache_disabled")
            self.assertFalse(row["query_ready"])

    def test_runtime_cache_summary_requires_no_credentials_or_network_calls(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            surface = build_five_contract_readiness_summary_surface(
                runtime_snapshot=_runtime_cache_snapshot(),
            )

        self.assertFalse(surface["live_credentials_required"])
        self.assertEqual(surface["readiness_source"], READINESS_SOURCE_RUNTIME_CACHE)

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

    def test_operator_console_startup_can_pass_runtime_cache_snapshot_to_summary(self) -> None:
        engine_src = _engine_src_path()
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            with patch.object(sys, "path", [engine_src, *sys.path]):
                artifacts = build_startup_artifacts_from_env(
                    query_action_requested=False,
                    runtime_snapshot=_runtime_cache_snapshot(),
                )

        summary = artifacts.shell["surfaces"]["five_contract_readiness_summary"]
        self.assertEqual(summary["readiness_source"], READINESS_SOURCE_RUNTIME_CACHE)
        self.assertEqual(summary["live_runtime_readiness_status"], LIVE_RUNTIME_CONNECTED)
        self.assertTrue(summary["runtime_cache_bound_to_operator_launch"])
        self.assertTrue(summary["runtime_cache_snapshot_ready"])

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
