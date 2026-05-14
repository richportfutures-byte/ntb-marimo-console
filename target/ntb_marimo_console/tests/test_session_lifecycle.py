from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ntb_marimo_console.adapters.contracts import TriggerEvaluation
from ntb_marimo_console.contract_universe import (
    excluded_final_target_contracts,
    final_target_contracts,
)
from ntb_marimo_console.evidence_replay import EVIDENCE_REPLAY_SCHEMA
from ntb_marimo_console.market_data.stream_cache import StreamCacheRecord, StreamCacheSnapshot
from ntb_marimo_console.primary_cockpit import primary_cockpit_surface
from ntb_marimo_console.session_lifecycle import (
    load_session_lifecycle_from_env,
    observe_phase1_trigger_state_results,
    request_cockpit_manual_query,
    reload_current_profile,
    request_query_action,
    reset_session,
    refresh_runtime_snapshot,
    switch_profile,
)
from ntb_marimo_console.trigger_state import TriggerState, TriggerStateResult
from ntb_marimo_console.viewmodels.models import TriggerStatusVM


FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "golden" / "phase1"
FINAL_TARGET_PRESERVED_PROFILE_BY_CONTRACT = {
    "ES": "preserved_es_phase1",
    "NQ": "preserved_nq_phase1",
    "CL": "preserved_cl_phase1",
    "6E": "preserved_6e_phase1",
    "MGC": "preserved_mgc_phase1",
}
NOW = "2026-05-06T14:00:00+00:00"
RUNTIME_SYMBOL_BY_CONTRACT = {
    "ES": "/ESM26",
    "NQ": "/NQM26",
    "CL": "/CLM26",
    "6E": "/6EM26",
    "MGC": "/MGCM26",
}


def complete_levelone_fields(index: int = 0) -> tuple[tuple[str, object], ...]:
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


def runtime_record(contract: str) -> StreamCacheRecord:
    return StreamCacheRecord(
        provider="schwab",
        service="LEVELONE_FUTURES",
        symbol=RUNTIME_SYMBOL_BY_CONTRACT[contract],
        contract=contract,
        message_type="quote",
        fields=complete_levelone_fields(),
        updated_at=NOW,
        age_seconds=0.0,
        fresh=True,
        blocking_reasons=(),
    )


def runtime_cache_snapshot() -> StreamCacheSnapshot:
    return StreamCacheSnapshot(
        generated_at=NOW,
        provider="schwab",
        provider_status="active",
        cache_max_age_seconds=15.0,
        records=tuple(runtime_record(contract) for contract in final_target_contracts()),
        blocking_reasons=(),
        stale_symbols=(),
    )


def trigger_result(
    contract: str,
    state: TriggerState,
    *,
    setup_id: str | None = None,
    trigger_id: str | None = None,
    last_updated: str = NOW,
) -> TriggerStateResult:
    return TriggerStateResult(
        contract=contract,
        setup_id=setup_id or f"{contract.lower()}_setup_1",
        trigger_id=trigger_id or f"{contract.lower()}_trigger_1",
        state=state,
        distance_to_trigger_ticks=0.0 if state == TriggerState.QUERY_READY else None,
        required_fields=("market.current_price",),
        missing_fields=(),
        invalid_reasons=(),
        blocking_reasons=(),
        last_updated=last_updated,
    )


class SessionLifecycleTests(unittest.TestCase):
    def test_session_reset_success_path_in_fixture_mode(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            queried = request_query_action(lifecycle)
            reset = reset_session(queried)

        self.assertTrue(reset.ready)
        self.assertEqual(reset.shell["lifecycle"]["current_lifecycle_state"], "SESSION_RESET_COMPLETED")
        self.assertEqual(reset.shell["runtime"]["session_state"], "LIVE_QUERY_BLOCKED")
        self.assertEqual(reset.shell["workflow"]["query_action_status"], "BLOCKED")
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
        self.assertEqual(reset.shell["runtime"]["session_state"], "LIVE_QUERY_BLOCKED")
        self.assertEqual(reset.shell["workflow"]["query_action_status"], "BLOCKED")
        self.assertFalse(reset.shell["workflow"]["decision_review_ready"])
        self.assertFalse(reset.shell["workflow"]["audit_replay_ready"])

    def test_session_reset_success_path_in_second_preserved_mode(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_nq_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            queried = request_query_action(lifecycle)
            reset = reset_session(queried)

        self.assertTrue(reset.ready)
        self.assertEqual(reset.shell["lifecycle"]["current_lifecycle_state"], "SESSION_RESET_COMPLETED")
        self.assertEqual(reset.shell["runtime"]["profile_id"], "preserved_nq_phase1")
        self.assertEqual(reset.shell["surfaces"]["session_header"]["contract"], "NQ")
        self.assertEqual(reset.shell["runtime"]["session_state"], "LIVE_QUERY_BLOCKED")
        self.assertEqual(reset.shell["workflow"]["query_action_status"], "BLOCKED")
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
        self.assertEqual(refreshed.shell["runtime"]["session_state"], "LIVE_QUERY_BLOCKED")
        self.assertEqual(refreshed.shell["workflow"]["query_action_status"], "BLOCKED")
        self.assertFalse(refreshed.shell["workflow"]["decision_review_ready"])
        self.assertFalse(refreshed.shell["workflow"]["audit_replay_ready"])

    def test_lifecycle_does_not_synthesize_trigger_transition_replay_from_shell_state(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            refreshed = refresh_runtime_snapshot(lifecycle)
            reloaded = reload_current_profile(refreshed)

        for item in (lifecycle, refreshed, reloaded):
            with self.subTest(action=item.last_action):
                trigger_table = item.shell["surfaces"]["trigger_table"]
                self.assertTrue(trigger_table["rows"])
                rendered = json.dumps(item.shell, sort_keys=True)
                self.assertNotIn("trigger_transition_log", rendered)
                self.assertIsNone(item.trigger_transition_log(contract="ES"))

    def test_cockpit_manual_query_is_not_auto_submitted_on_load_or_refresh(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            refreshed = refresh_runtime_snapshot(lifecycle)

        for item in (lifecycle, refreshed):
            result = item.shell["surfaces"]["fixture_cockpit_overview"]["last_query_result"]
            self.assertEqual(result["request_status"], "NOT_SUBMITTED")
            self.assertFalse(result["submitted"])

    def test_cockpit_manual_query_submits_eligible_contract_and_renders_last_result(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            queried = request_cockpit_manual_query(lifecycle, "ES")

        result = queried.shell["surfaces"]["fixture_cockpit_overview"]["last_query_result"]
        action = queried.shell["surfaces"]["fixture_cockpit_overview"]["operator_action_status"]
        rows = {
            row["contract"]: row
            for row in queried.shell["surfaces"]["fixture_cockpit_overview"]["rows"]
        }
        self.assertEqual(result["request_status"], "SUBMITTED")
        self.assertTrue(result["submitted"])
        self.assertEqual(result["contract"], "ES")
        self.assertEqual(result["pipeline_result_status"], "completed")
        self.assertEqual(result["terminal_summary"], "NO_TRADE")
        self.assertEqual(result["gate_provenance_basis"], "real_trigger_state_result_and_pipeline_gate")
        self.assertEqual(result["operator_feedback_text"], "Manual query submitted for ES; preserved pipeline returned a bounded result.")
        self.assertEqual(action["action_kind"], "MANUAL_QUERY")
        self.assertEqual(action["action_status"], "SUBMITTED")
        self.assertEqual(action["action_text"], result["operator_feedback_text"])
        self.assertEqual(action["bounded_result_summary"], result["bounded_result_summary"])
        self.assertEqual(action["next_operator_state"], result["next_operator_state"])
        self.assertEqual(rows["ES"]["last_query_status"], "SUBMITTED")
        self.assertEqual(queried.shell["workflow"]["cockpit_manual_query_status"], "SUBMITTED")

    def test_cockpit_manual_query_blocks_ineligible_contract_without_submission(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            queried = request_cockpit_manual_query(lifecycle, "NQ")

        result = queried.shell["surfaces"]["fixture_cockpit_overview"]["last_query_result"]
        action = queried.shell["surfaces"]["fixture_cockpit_overview"]["operator_action_status"]
        detail = queried.shell["surfaces"]["fixture_cockpit_overview"]["contract_readiness_detail"]
        rows = {
            row["contract"]: row
            for row in queried.shell["surfaces"]["fixture_cockpit_overview"]["rows"]
        }
        self.assertEqual(result["request_status"], "BLOCKED")
        self.assertFalse(result["submitted"])
        self.assertEqual(result["pipeline_result_status"], "not_submitted")
        self.assertIn("Manual query blocked", result["blocked_reason"])
        self.assertEqual(action["action_kind"], "MANUAL_QUERY")
        self.assertEqual(action["action_status"], "BLOCKED")
        self.assertEqual(action["blocked_reason"], result["blocked_reason"])
        self.assertEqual(
            action["bounded_result_summary"],
            "No bounded pipeline result is available because the query was not submitted.",
        )
        self.assertEqual(rows["NQ"]["last_query_status"], "BLOCKED")
        detail_rows = {row["contract"]: row for row in detail["rows"]}
        self.assertEqual(detail_rows["NQ"]["latest_operator_action_state"], "BLOCKED")
        self.assertEqual(
            detail_rows["NQ"]["latest_operator_action_blocked_reason"],
            result["blocked_reason"],
        )
        self.assertIn("Wait", detail_rows["NQ"]["next_safe_operator_action"])

    def test_lifecycle_observes_produced_trigger_state_results_without_first_replay(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()

        self.assertTrue(lifecycle.ready)
        self.assertEqual(lifecycle.trigger_transition_replay_source.events, ())
        self.assertIsNone(lifecycle.trigger_transition_log(contract="ES"))
        rendered = json.dumps(lifecycle.shell, sort_keys=True)
        self.assertNotIn("trigger_transition_log", rendered)

    def test_lifecycle_refresh_observes_real_produced_transition_evidence(self) -> None:
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
                self.assertIsNone(lifecycle.trigger_transition_log(contract="ES"))

                observable_path = artifact_root / "observables" / "ES" / "trigger_true.json"
                observable = json.loads(observable_path.read_text(encoding="utf-8"))
                observable["market"]["current_price"] = 5603.5
                observable_path.write_text(json.dumps(observable), encoding="utf-8")
                refreshed = reload_current_profile(lifecycle)

        log = refreshed.trigger_transition_log(contract="ES")

        self.assertIsNotNone(log)
        assert log is not None
        self.assertEqual(log["schema"], EVIDENCE_REPLAY_SCHEMA)
        self.assertEqual(log["contract"], "ES")
        self.assertEqual(log["trigger_transitions"][0]["event_type"], "trigger_approaching")
        self.assertEqual(log["trigger_transitions"][0]["trigger_state"], "APPROACHING")
        self.assertEqual(log["trigger_transitions"][0]["setup_id"], "es_setup_1")
        self.assertEqual(log["trigger_transitions"][0]["trigger_id"], "es_trigger_acceptance")

    def test_lifecycle_trigger_observation_first_and_identical_states_expose_no_log(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()

        first = lifecycle.observe_trigger_state_result(
            trigger_result("ES", TriggerState.DORMANT),
            timestamp="2026-05-06T14:00:00+00:00",
        )
        identical = lifecycle.observe_trigger_state_result(
            trigger_result("ES", TriggerState.DORMANT),
            timestamp="2026-05-06T14:00:01+00:00",
        )

        self.assertEqual(first, ())
        self.assertEqual(identical, ())
        self.assertEqual(lifecycle.trigger_transition_replay_source.events, ())
        self.assertIsNone(lifecycle.trigger_transition_log(contract="ES"))
        rendered = json.dumps(lifecycle.shell, sort_keys=True)
        self.assertNotIn("trigger_transition_log", rendered)

    def test_lifecycle_trigger_observation_material_transition_exposes_evidence_replay(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()

        lifecycle.observe_trigger_state_result(
            trigger_result("ES", TriggerState.DORMANT),
            timestamp="2026-05-06T14:00:00+00:00",
        )
        emitted = lifecycle.observe_trigger_state_result(
            trigger_result("ES", TriggerState.APPROACHING),
            timestamp="2026-05-06T14:00:01+00:00",
            premarket_brief_ref="premarket/ES/2026-05-06/brief.json",
        )
        log = lifecycle.trigger_transition_log(contract="ES")

        self.assertEqual(len(emitted), 1)
        self.assertIsNotNone(log)
        assert log is not None
        self.assertEqual(log["schema"], EVIDENCE_REPLAY_SCHEMA)
        self.assertEqual(log["contract"], "ES")
        self.assertEqual(log["trigger_transitions"][0]["event_type"], "trigger_approaching")
        self.assertEqual(log["trigger_transitions"][0]["trigger_state"], "APPROACHING")

    def test_lifecycle_trigger_observation_keeps_contract_keys_separate(self) -> None:
        shared_setup = "shared_setup"
        shared_trigger = "shared_trigger"
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()

        lifecycle.observe_trigger_state_result(
            trigger_result("ES", TriggerState.DORMANT, setup_id=shared_setup, trigger_id=shared_trigger),
            timestamp="2026-05-06T14:00:00+00:00",
            profile_id="preserved_es_phase1",
        )
        cross_contract_first = lifecycle.observe_trigger_state_result(
            trigger_result("NQ", TriggerState.APPROACHING, setup_id=shared_setup, trigger_id=shared_trigger),
            timestamp="2026-05-06T14:00:01+00:00",
            profile_id="preserved_nq_phase1",
        )
        es_transition = lifecycle.observe_trigger_state_result(
            trigger_result("ES", TriggerState.APPROACHING, setup_id=shared_setup, trigger_id=shared_trigger),
            timestamp="2026-05-06T14:00:02+00:00",
            profile_id="preserved_es_phase1",
        )
        nq_transition = lifecycle.observe_trigger_state_result(
            trigger_result("NQ", TriggerState.TOUCHED, setup_id=shared_setup, trigger_id=shared_trigger),
            timestamp="2026-05-06T14:00:03+00:00",
            profile_id="preserved_nq_phase1",
        )

        es_log = lifecycle.trigger_transition_log(contract="ES", profile_id="preserved_es_phase1")
        nq_log = lifecycle.trigger_transition_log(contract="NQ", profile_id="preserved_nq_phase1")

        self.assertEqual(cross_contract_first, ())
        self.assertEqual(len(es_transition), 1)
        self.assertEqual(len(nq_transition), 1)
        self.assertIsNotNone(es_log)
        self.assertIsNotNone(nq_log)
        assert es_log is not None
        assert nq_log is not None
        self.assertEqual([item["event_type"] for item in es_log["trigger_transitions"]], ["trigger_approaching"])
        self.assertEqual([item["event_type"] for item in nq_log["trigger_transitions"]], ["trigger_touched"])

    def test_lifecycle_trigger_observation_source_is_carried_across_session_actions(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()

        lifecycle.observe_trigger_state_result(
            trigger_result("ES", TriggerState.DORMANT),
            timestamp="2026-05-06T14:00:00+00:00",
        )
        queried = request_query_action(lifecycle)
        emitted = queried.observe_trigger_state_result(
            trigger_result("ES", TriggerState.APPROACHING),
            timestamp="2026-05-06T14:00:01+00:00",
        )

        self.assertIs(queried.trigger_transition_replay_source, lifecycle.trigger_transition_replay_source)
        self.assertEqual(len(emitted), 1)
        self.assertIsNotNone(queried.trigger_transition_log(contract="ES"))
        self.assertNotIn("trigger_transition_log", json.dumps(queried.shell, sort_keys=True))

    def test_lifecycle_trigger_observation_rejects_non_trigger_state_result_input(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()

        display_only_inputs = (
            {"contract": "ES", "state": "APPROACHING"},
            TriggerEvaluation(
                trigger_id="es_trigger_1",
                is_valid=True,
                is_true=True,
                missing_fields=(),
                invalid_reasons=(),
            ),
            TriggerStatusVM(
                trigger_id="es_trigger_1",
                is_valid=True,
                is_true=True,
                missing_fields=(),
                invalid_reasons=(),
            ),
        )
        for display_only_input in display_only_inputs:
            with self.subTest(input_type=type(display_only_input).__name__):
                with self.assertRaises(TypeError):
                    lifecycle.observe_trigger_state_result(
                        display_only_input,  # type: ignore[arg-type]
                        timestamp="2026-05-06T14:00:00+00:00",
                    )
                with self.assertRaises(TypeError):
                    observe_phase1_trigger_state_results(
                        lifecycle,
                        (display_only_input,),  # type: ignore[arg-type]
                    )

        app_path = Path(__file__).resolve().parents[1] / "src" / "ntb_marimo_console" / "app.py"
        app_source = app_path.read_text(encoding="utf-8")
        self.assertIn(
            "eval_bundle = dependencies.trigger_evaluator.evaluate(trigger_specs, inputs.live_snapshot)",
            app_source,
        )
        self.assertIn(
            "trigger_vms = tuple(trigger_status_vm_from_eval(item) for item in eval_bundle.evaluations)",
            app_source,
        )
        self.assertIn("trigger_rows=trigger_vms", app_source)
        self.assertIn("build_trigger_state_results(", app_source)
        self.assertLess(
            app_source.index("build_trigger_state_results("),
            app_source.index("eval_bundle = dependencies.trigger_evaluator.evaluate"),
        )
        self.assertNotIn("observe_trigger_state_result", app_source)
        self.assertNotIn("trigger_transition_log", app_source)

        console_app_path = Path(__file__).resolve().parents[1] / "src" / "ntb_marimo_console" / "operator_console_app.py"
        console_app_source = console_app_path.read_text(encoding="utf-8")
        self.assertNotIn("observe_trigger_state_result", console_app_source)
        self.assertNotIn(
            "trigger_transition_log",
            console_app_source,
            "Renderer/app code must not derive replay logs from trigger rows or shell state.",
        )

        self.assertIsNone(lifecycle.trigger_transition_log(contract="ES"))

    def test_refresh_success_path_in_preserved_mode(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            queried = request_query_action(lifecycle)
            refreshed = reload_current_profile(queried)

        self.assertTrue(refreshed.ready)
        self.assertEqual(refreshed.shell["lifecycle"]["current_lifecycle_state"], "REFRESH_COMPLETED")
        self.assertEqual(refreshed.shell["lifecycle"]["reload_result"], "RELOADED_UNCHANGED")
        self.assertEqual(refreshed.shell["runtime"]["session_state"], "LIVE_QUERY_BLOCKED")
        self.assertEqual(refreshed.shell["workflow"]["query_action_status"], "BLOCKED")

    def test_lifecycle_preserves_runtime_cache_derived_summary_across_operator_actions(self) -> None:
        snapshot = runtime_cache_snapshot()
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env(runtime_snapshot=snapshot)
            queried = request_query_action(lifecycle)
            es_manual_query = request_cockpit_manual_query(lifecycle, "ES")
            nq_manual_query = request_cockpit_manual_query(lifecycle, "NQ")
            refreshed = reload_current_profile(queried)
            reset = reset_session(queried)

        for item in (lifecycle, queried, es_manual_query, nq_manual_query, refreshed, reset):
            with self.subTest(action=item.last_action):
                summary = item.shell["surfaces"]["five_contract_readiness_summary"]
                self.assertEqual(summary["readiness_source"], "runtime_cache_derived")
                self.assertEqual(summary["live_runtime_readiness_status"], "LIVE_RUNTIME_CONNECTED")
                self.assertTrue(summary["runtime_cache_bound_to_operator_launch"])
                self.assertTrue(summary["runtime_cache_snapshot_ready"])
                self.assertIs(item.runtime_snapshot, snapshot)
                self.assertFalse(summary["rows"][0]["query_ready"])
                # Under a live runtime snapshot the primary cockpit is the
                # live-observation cockpit, not the fixture cockpit.
                action = primary_cockpit_surface(item.shell)["operator_action_status"]
                self.assertEqual(action["runtime_readiness_status"], "LIVE_RUNTIME_CONNECTED")
                self.assertTrue(action["runtime_readiness_preserved"])

        # The runtime cache here has live quotes but no completed chart bars, so
        # the live-observation cockpit fail-closes every contract — including ES.
        # There is no fixture fallback: the fixture cockpit would have shown ES
        # query-ready, but the live cockpit reflects the real live gate only.
        self.assertEqual(
            primary_cockpit_surface(es_manual_query.shell)["last_query_result"][
                "request_status"
            ],
            "BLOCKED",
        )
        self.assertEqual(
            primary_cockpit_surface(nq_manual_query.shell)["last_query_result"][
                "request_status"
            ],
            "BLOCKED",
        )
        self.assertEqual(
            primary_cockpit_surface(refreshed.shell)["operator_action_status"]["action_status"],
            "REFRESHED",
        )
        self.assertEqual(
            primary_cockpit_surface(reset.shell)["operator_action_status"]["action_status"],
            "RESET",
        )

    def test_refresh_success_path_in_second_preserved_mode(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_nq_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            queried = request_query_action(lifecycle)
            refreshed = reload_current_profile(queried)

        self.assertTrue(refreshed.ready)
        self.assertEqual(refreshed.shell["lifecycle"]["current_lifecycle_state"], "REFRESH_COMPLETED")
        self.assertEqual(refreshed.shell["lifecycle"]["reload_result"], "RELOADED_UNCHANGED")
        self.assertEqual(refreshed.shell["runtime"]["profile_id"], "preserved_nq_phase1")
        self.assertEqual(refreshed.shell["surfaces"]["session_header"]["contract"], "NQ")
        self.assertEqual(refreshed.shell["runtime"]["session_state"], "LIVE_QUERY_BLOCKED")
        self.assertEqual(refreshed.shell["workflow"]["query_action_status"], "BLOCKED")

    def test_refresh_fail_closed_on_invalid_reloaded_artifacts(self) -> None:
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

        self.assertEqual(queried.shell["runtime"]["session_state"], "QUERY_ACTION_FAILED")
        self.assertFalse(queried.shell["workflow"]["decision_review_ready"])
        self.assertFalse(queried.shell["workflow"]["audit_replay_ready"])
        self.assertEqual(reset.shell["runtime"]["session_state"], "LIVE_QUERY_BLOCKED")
        self.assertFalse(reset.shell["workflow"]["decision_review_ready"])
        self.assertFalse(reset.shell["workflow"]["audit_replay_ready"])

    def test_query_decision_and_audit_state_after_refresh(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "fixture_es_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            queried = request_query_action(lifecycle)
            refreshed = reload_current_profile(queried)

        self.assertEqual(queried.shell["runtime"]["session_state"], "QUERY_ACTION_FAILED")
        self.assertEqual(refreshed.shell["runtime"]["session_state"], "LIVE_QUERY_BLOCKED")
        self.assertFalse(refreshed.shell["workflow"]["decision_review_ready"])
        self.assertFalse(refreshed.shell["workflow"]["audit_replay_ready"])

    def test_profile_switch_to_zn_profile_fails_closed(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            queried = request_query_action(lifecycle)
            switched = switch_profile(queried, "preserved_zn_phase1")

        self.assertTrue(switched.ready)
        self.assertEqual(switched.shell["startup"]["selected_profile_id"], "preserved_es_phase1")
        self.assertEqual(switched.shell["runtime"]["profile_id"], "preserved_es_phase1")
        self.assertEqual(switched.shell["surfaces"]["session_header"]["contract"], "ES")
        self.assertEqual(switched.shell["runtime"]["session_state"], "QUERY_ACTION_FAILED")
        self.assertEqual(switched.shell["workflow"]["query_action_status"], "FAILED")
        self.assertEqual(switched.shell["lifecycle"]["current_lifecycle_state"], "PROFILE_SWITCH_BLOCKED")
        self.assertEqual(switched.shell["lifecycle"]["profile_switch_result"], "SWITCH_BLOCKED")
        self.assertEqual(switched.shell["lifecycle"]["profile_switch_target_id"], "preserved_zn_phase1")
        self.assertIn("supported profile registry", switched.shell["lifecycle"]["status_summary"])
        self.assertNotIn("preserved_zn_phase1", switched.shell["startup"]["supported_profile_ids"])
        self.assertNotIn("preserved_zn_phase1", switched.shell["startup"]["legacy_historical_profile_ids"])
        self.assertNotIn("ZN", final_target_contracts())

    def test_profile_switch_block_does_not_clear_existing_query_state(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            queried = request_query_action(lifecycle)
            switched = switch_profile(queried, "preserved_zn_phase1")

        self.assertTrue(switched.ready)
        self.assertFalse(switched.shell["workflow"]["decision_review_ready"])
        self.assertFalse(switched.shell["workflow"]["audit_replay_ready"])
        self.assertEqual(switched.shell["runtime"]["profile_id"], "preserved_es_phase1")
        self.assertIn("PROFILE_SWITCH_REQUESTED", switched.shell["lifecycle"]["state_history"])
        self.assertIn("PROFILE_SWITCH_VALIDATING", switched.shell["lifecycle"]["state_history"])
        self.assertIn("PROFILE_SWITCH_BLOCKED", switched.shell["lifecycle"]["state_history"])

    def test_profile_switch_success_path_nq_to_cl(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_nq_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            switched = switch_profile(lifecycle, "preserved_cl_phase1")

        self.assertTrue(switched.ready)
        self.assertEqual(switched.shell["startup"]["selected_profile_id"], "preserved_cl_phase1")
        self.assertEqual(switched.shell["runtime"]["profile_id"], "preserved_cl_phase1")
        self.assertEqual(switched.shell["surfaces"]["session_header"]["contract"], "CL")
        self.assertEqual(switched.shell["workflow"]["query_action_status"], "BLOCKED")
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

    def test_profile_switch_to_nq_final_target_completes(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            switched = switch_profile(lifecycle, "preserved_nq_phase1")

        self.assertTrue(switched.ready)
        self.assertEqual(switched.shell["startup"]["selected_profile_id"], "preserved_nq_phase1")
        self.assertEqual(switched.shell["runtime"]["profile_id"], "preserved_nq_phase1")
        self.assertEqual(switched.shell["surfaces"]["session_header"]["contract"], "NQ")
        self.assertEqual(switched.shell["workflow"]["query_action_status"], "BLOCKED")
        self.assertEqual(switched.shell["lifecycle"]["current_lifecycle_state"], "PROFILE_SWITCH_COMPLETED")
        self.assertEqual(switched.shell["lifecycle"]["profile_switch_result"], "SWITCH_COMPLETED")
        self.assertEqual(switched.shell["lifecycle"]["profile_switch_target_id"], "preserved_nq_phase1")

    def test_profile_switch_to_unknown_profile_fails_closed(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            switched = switch_profile(lifecycle, "unsupported_profile")

        self.assertTrue(switched.ready)
        self.assertEqual(switched.shell["startup"]["selected_profile_id"], "preserved_es_phase1")
        self.assertEqual(switched.shell["lifecycle"]["current_lifecycle_state"], "PROFILE_SWITCH_BLOCKED")
        self.assertEqual(switched.shell["lifecycle"]["profile_switch_target_id"], "unsupported_profile")
        self.assertIn("supported profile registry", switched.shell["lifecycle"]["status_summary"])

    def test_profile_switch_to_gc_profile_fails_closed(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            switched = switch_profile(lifecycle, "preserved_gc_phase1")

        self.assertTrue(switched.ready)
        self.assertEqual(switched.shell["startup"]["selected_profile_id"], "preserved_es_phase1")
        self.assertEqual(switched.shell["runtime"]["profile_id"], "preserved_es_phase1")
        self.assertEqual(switched.shell["lifecycle"]["current_lifecycle_state"], "PROFILE_SWITCH_BLOCKED")
        self.assertEqual(switched.shell["lifecycle"]["profile_switch_result"], "SWITCH_BLOCKED")
        self.assertEqual(switched.shell["lifecycle"]["profile_switch_target_id"], "preserved_gc_phase1")
        self.assertIn("supported profile registry", switched.shell["lifecycle"]["status_summary"])

    def test_profile_switch_from_blocked_startup_can_load_supported_profile(self) -> None:
        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "unsupported_demo"}, clear=True):
            lifecycle = load_session_lifecycle_from_env()
            switched = switch_profile(lifecycle, "preserved_cl_phase1")

        self.assertTrue(switched.ready)
        self.assertEqual(switched.shell["startup"]["selected_profile_id"], "preserved_cl_phase1")
        self.assertEqual(switched.shell["runtime"]["profile_id"], "preserved_cl_phase1")
        self.assertEqual(switched.shell["surfaces"]["session_header"]["contract"], "CL")

    def test_final_target_profiles_load_refresh_reset_and_switch_non_live(self) -> None:
        self.assertEqual(final_target_contracts(), ("ES", "NQ", "CL", "6E", "MGC"))
        self.assertEqual(set(FINAL_TARGET_PRESERVED_PROFILE_BY_CONTRACT), set(final_target_contracts()))

        for contract, profile_id in FINAL_TARGET_PRESERVED_PROFILE_BY_CONTRACT.items():
            with self.subTest(contract=contract, profile_id=profile_id):
                with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": profile_id}, clear=True):
                    lifecycle = load_session_lifecycle_from_env()
                    queried = request_query_action(lifecycle)
                    refreshed = reload_current_profile(queried)
                    reset = reset_session(queried)

                self.assertTrue(lifecycle.ready)
                self.assertEqual(lifecycle.shell["runtime"]["profile_id"], profile_id)
                self.assertEqual(lifecycle.shell["surfaces"]["session_header"]["contract"], contract)
                self.assertEqual(lifecycle.shell["runtime"]["session_state"], "LIVE_QUERY_BLOCKED")
                self.assertEqual(lifecycle.shell["workflow"]["query_action_status"], "BLOCKED")
                self.assertEqual(refreshed.shell["lifecycle"]["current_lifecycle_state"], "REFRESH_COMPLETED")
                self.assertEqual(refreshed.shell["runtime"]["profile_id"], profile_id)
                self.assertEqual(refreshed.shell["runtime"]["session_state"], "LIVE_QUERY_BLOCKED")
                self.assertEqual(reset.shell["lifecycle"]["current_lifecycle_state"], "SESSION_RESET_COMPLETED")
                self.assertEqual(reset.shell["runtime"]["profile_id"], profile_id)
                self.assertEqual(reset.shell["runtime"]["session_state"], "LIVE_QUERY_BLOCKED")

                with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_es_phase1"}, clear=True):
                    starting = load_session_lifecycle_from_env()
                    switched = switch_profile(starting, profile_id)
                if profile_id == "preserved_es_phase1":
                    self.assertEqual(switched.shell["lifecycle"]["current_lifecycle_state"], "PROFILE_SWITCH_BLOCKED")
                    self.assertEqual(switched.shell["lifecycle"]["profile_switch_result"], "SWITCH_BLOCKED")
                else:
                    self.assertEqual(switched.shell["lifecycle"]["current_lifecycle_state"], "PROFILE_SWITCH_COMPLETED")
                    self.assertEqual(switched.shell["lifecycle"]["profile_switch_result"], "SWITCH_COMPLETED")
                    self.assertEqual(switched.shell["runtime"]["profile_id"], profile_id)

    def test_zn_and_gc_remain_excluded_from_final_target_lifecycle_readiness(self) -> None:
        self.assertEqual(excluded_final_target_contracts(), ("ZN", "GC"))
        for excluded in excluded_final_target_contracts():
            self.assertNotIn(excluded, final_target_contracts())

        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_zn_phase1"}, clear=True):
            zn_lifecycle = load_session_lifecycle_from_env()

        self.assertFalse(zn_lifecycle.ready)
        self.assertIsNone(zn_lifecycle.config)
        self.assertEqual(zn_lifecycle.shell["startup"]["selected_profile_id"], "preserved_zn_phase1")
        self.assertEqual(zn_lifecycle.shell["startup"]["readiness_state"], "BLOCKED")

        with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": "preserved_gc_phase1"}, clear=True):
            gc_lifecycle = load_session_lifecycle_from_env()

        self.assertFalse(gc_lifecycle.ready)
        self.assertIsNone(gc_lifecycle.config)
        self.assertEqual(gc_lifecycle.shell["startup"]["readiness_state"], "BLOCKED")

    def test_lifecycle_state_does_not_authorize_trade_execution(self) -> None:
        for profile_id in FINAL_TARGET_PRESERVED_PROFILE_BY_CONTRACT.values():
            with self.subTest(profile_id=profile_id):
                with patch.dict(os.environ, {"NTB_CONSOLE_PROFILE": profile_id}, clear=True):
                    lifecycle = load_session_lifecycle_from_env()
                    queried = request_query_action(lifecycle)
                    reset = reset_session(queried)

                summary = reset.shell["surfaces"]["five_contract_readiness_summary"]
                self.assertEqual(summary["decision_authority"], "preserved_engine_only")
                self.assertTrue(summary["manual_execution_only"])
                self.assertFalse(summary["summary_can_authorize_trades"])
                for row in summary["rows"]:
                    self.assertFalse(row["trade_execution_authorized"])
                    self.assertIn(
                        "preserved engine remains the only decision authority",
                        row["preserved_engine_authority"],
                    )


if __name__ == "__main__":
    unittest.main()
