from __future__ import annotations

import unittest
from pathlib import Path

from ntb_marimo_console.runtime_modes import build_es_app_shell_for_mode
from ntb_marimo_console.ui.marimo_phase1_renderer import (
    FROZEN_SURFACE_KEYS,
    _flatten_mapping_lines,
    _render_decision_review_engine_reasoning,
    _render_decision_review_invalidation,
    _render_decision_review_replay,
    _render_decision_review_risk_authorization,
    _render_decision_review_trade_thesis,
    build_phase1_render_plan,
    build_profile_operations_markdown,
    build_session_evidence_markdown,
    build_session_lifecycle_markdown,
    build_runtime_identity_markdown,
    build_session_workflow_markdown,
    build_startup_status_markdown,
)


PACKAGE_ROOT = Path(__file__).resolve().parents[1]


class MarimoPhase1RendererTests(unittest.TestCase):
    def test_renderer_smoke_from_fixture_shell(self) -> None:
        shell = build_es_app_shell_for_mode(mode="fixture_demo")
        plan = build_phase1_render_plan(shell)

        section_keys = tuple(item["key"] for item in plan["sections"])
        self.assertEqual(section_keys, FROZEN_SURFACE_KEYS)
        self.assertEqual(plan["warnings"], [])

    def test_renderer_preserves_no_manual_override_and_no_stage_e_surface(self) -> None:
        shell = build_es_app_shell_for_mode(mode="fixture_demo")
        plan = build_phase1_render_plan(shell)

        sections = {item["key"]: item["panel"] for item in plan["sections"]}
        query_panel = sections["query_action"]
        decision_panel = sections["decision_review"]

        self.assertFalse(query_panel["manual_override_available"])
        self.assertNotIn("stage_e", decision_panel)
        self.assertNotIn("audit_log", decision_panel)

    def test_decision_review_marks_narrative_unavailable_under_fixture_envelope(self) -> None:
        """Fixture pipeline_result.*.json files are envelope-only.

        The Decision Review surface must explicitly mark each narrative
        section as unavailable in this run, never as empty success. A future
        sidecar pipeline_result.<variant>.narrative.json would surface
        narrative; absent that, the renderer is honest about what is missing.
        """
        shell = build_es_app_shell_for_mode(mode="fixture_demo")
        decision_panel = shell["surfaces"]["decision_review"]

        self.assertTrue(decision_panel["has_result"])
        self.assertFalse(decision_panel["narrative_available"])
        self.assertIsNotNone(decision_panel["narrative_unavailable_message"])
        self.assertFalse(decision_panel["engine_reasoning"]["available"])
        self.assertFalse(decision_panel["trade_thesis"]["available"])
        self.assertFalse(decision_panel["risk_authorization_detail"]["available"])
        self.assertFalse(decision_panel["invalidation"]["available"])

    def test_decision_review_narrative_section_renderers_emit_unavailable_lines_for_absent_sections(self) -> None:
        """The four section-line builders emit explicit unavailable lines when narrative is absent.

        This locks the contract that the Markdown rendering does not silently
        omit a section when its data is missing - it always prints the heading
        and an explicit '_unavailable_' marker, never empty success.
        """
        engine_lines = _render_decision_review_engine_reasoning(
            {"available": False, "unavailable_message": "Engine narrative unavailable in this run."}
        )
        thesis_lines = _render_decision_review_trade_thesis(
            {"available": False, "unavailable_message": "Engine narrative unavailable in this run."}
        )
        risk_lines = _render_decision_review_risk_authorization(
            {"available": False, "unavailable_message": "Engine narrative unavailable in this run."}
        )
        invalidation_lines = _render_decision_review_invalidation(
            {"available": False, "unavailable_message": "Disqualifiers list is unavailable for this run.", "disqualifiers": []}
        )

        engine_text = "\n".join(engine_lines)
        thesis_text = "\n".join(thesis_lines)
        risk_text = "\n".join(risk_lines)
        invalidation_text = "\n".join(invalidation_lines)

        self.assertIn("### Engine Reasoning", engine_text)
        self.assertIn("unavailable", engine_text.lower())
        self.assertIn("### Trade Thesis", thesis_text)
        self.assertIn("unavailable", thesis_text.lower())
        self.assertIn("### Risk Authorization", risk_text)
        self.assertIn("unavailable", risk_text.lower())
        self.assertIn("### What Would Invalidate This", invalidation_text)
        self.assertIn("unavailable", invalidation_text.lower())

    def test_decision_review_trade_thesis_no_trade_branch_omits_setup_fields(self) -> None:
        no_trade_section = {
            "available": True,
            "is_no_trade": True,
            "outcome": "NO_TRADE",
            "no_trade_reason": "confidence_band_low",
            "rationale": "ES choppy near VWAP; awaiting resolution.",
            "direction": None,
            "setup_class": None,
            "entry_price": None,
            "stop_price": None,
            "target_1": None,
            "target_2": None,
            "position_size": None,
            "risk_dollars": None,
            "reward_risk_ratio": None,
            "hold_time_estimate_minutes": None,
            "sizing_math": None,
        }
        lines = _render_decision_review_trade_thesis(no_trade_section)
        text = "\n".join(lines)

        self.assertIn("NO_TRADE", text)
        self.assertIn("confidence_band_low", text)
        self.assertIn("first-class outcome", text)
        # Setup-only fields must not be rendered when NO_TRADE.
        self.assertNotIn("- Direction:", text)
        self.assertNotIn("- Entry Price:", text)
        self.assertNotIn("- Target 1:", text)
        # No alternate-trade prose.
        self.assertNotIn("take trade", text.lower())
        self.assertNotIn("alternate", text.lower())

    def test_decision_review_replay_renderer_emits_read_only_text_not_raw_json(self) -> None:
        lines = _render_decision_review_replay(
            {
                "available": True,
                "audit_schema": "decision_review_narrative_audit_event_v1",
                "audit_schema_version": 1,
                "created_at": "2026-05-09T12:00:00Z",
                "source": "fixture",
                "contract": "ES",
                "profile_id": "preserved_es_phase1",
                "setup_id": "es_setup_1",
                "trigger_id": "es_trigger_1",
                "trigger_state": "QUERY_READY",
                "pipeline_result_status": "READY",
                "final_decision": "NO_TRADE",
                "termination_stage": "contract_market_read",
                "engine_narrative_available": True,
                "trigger_transition_narrative_available": True,
                "manual_only_execution": True,
                "preserved_engine_authority": True,
                "authority_statement": "The preserved engine remains the decision authority, and execution remains manual.",
                "replay_reference_status": "available",
                "replay_reference_source": "fixture_backed",
                "replay_reference_run_id": "run-1",
                "replay_reference_final_decision": "NO_TRADE",
                "replay_reference_consistent": True,
                "replay_reference_stage_e_live_backend": False,
                "replay_reference_message": "Audit replay source reference is available from existing app-owned replay state.",
                "transition_summary": "setup es_setup_1 / trigger es_trigger_1: deterministic trigger state recorded.",
                "readiness_explanation": "The preserved pipeline must still decide; execution remains manual.",
                "blocking_explanation": "Blocking reasons: quote_stale.",
                "invalidation_explanation": None,
                "missing_data_explanation": "Missing required trigger data: market.current_price.",
                "stale": True,
                "lockout": False,
                "engine_reasoning_summary": {
                    "available": True,
                    "market_regime": "choppy",
                    "directional_bias": "unclear",
                    "confidence_band": "LOW",
                    "outcome": "NO_TRADE",
                },
                "blocking_reasons": ["quote_stale"],
                "invalid_reasons": [],
                "missing_fields": ["market.current_price"],
                "source_fields": ["decision_review", "transition_narrative"],
            }
        )
        text = "\n".join(lines)

        self.assertIn("### Narrative Audit Replay", text)
        self.assertIn("Manual-Only Execution: `True`", text)
        self.assertIn("Preserved Engine Authority: `True`", text)
        self.assertIn("The preserved engine remains the decision authority", text)
        self.assertIn("Replay Reference Status: `available`", text)
        self.assertIn("Replay Reference Run ID: `run-1`", text)
        self.assertIn("Transition Summary:", text)
        self.assertIn("quote_stale", text)
        self.assertIn("market.current_price", text)
        self.assertNotIn("```json", text)
        self.assertNotIn("{", text)
        for phrase in ("take the trade", "enter", "buy", "sell", "short now", "long now"):
            self.assertNotIn(phrase, text.lower())

    def test_raw_json_debug_is_secondary(self) -> None:
        shell = build_es_app_shell_for_mode(mode="fixture_demo")
        plan = build_phase1_render_plan(shell)

        self.assertTrue(plan["debug"]["secondary"])
        self.assertIn('"surfaces"', plan["debug"]["shell_json"])

    def test_runtime_identity_is_available_without_raw_json_primary_surface(self) -> None:
        source = (PACKAGE_ROOT / "src" / "ntb_marimo_console" / "ui" / "marimo_phase1_renderer.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("## Runtime Identity", source)
        self.assertIn("## Startup Status", source)
        self.assertIn("## Supported Profile Operations", source)
        self.assertIn("## Recent Session Evidence", source)
        self.assertIn("## Session Lifecycle", source)
        self.assertIn("## Session Workflow", source)
        self.assertIn("Preflight Status", source)

    def test_five_contract_summary_renderer_exposes_runtime_cache_readiness_fields(self) -> None:
        source = (PACKAGE_ROOT / "src" / "ntb_marimo_console" / "ui" / "marimo_phase1_renderer.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("Readiness Source", source)
        self.assertIn("Live Runtime Readiness", source)
        self.assertIn("Runtime Cache Source", source)
        self.assertIn("Runtime Provider Status", source)
        self.assertIn("Runtime Snapshot Ready", source)
        self.assertIn("Runtime Readiness Blockers", source)
        self.assertIn("Operator Live Runtime Status", source)
        self.assertIn("live_runtime_readiness_state", source)

    def test_primary_surfaces_do_not_use_code_editor_json(self) -> None:
        source = (PACKAGE_ROOT / "src" / "ntb_marimo_console" / "ui" / "marimo_phase1_renderer.py").read_text(
            encoding="utf-8"
        )

        self.assertEqual(source.count("mo.ui.code_editor("), 1)
        self.assertIn('mo.md("## Debug (Secondary)")', source)

    def test_live_observables_renders_readable_fields(self) -> None:
        shell = build_es_app_shell_for_mode(mode="fixture_demo")
        panel = shell["surfaces"]["live_observables"]

        flattened = _flatten_mapping_lines(panel["snapshot"])
        self.assertGreater(len(flattened), 0)
        flattened_dict = dict(flattened)
        self.assertIn("market.current_price", flattened_dict)
        self.assertIn("market.cumulative_delta", flattened_dict)

    def test_run_history_rows_present_for_readable_surface(self) -> None:
        shell = build_es_app_shell_for_mode(mode="fixture_demo")
        panel = shell["surfaces"]["run_history"]

        self.assertIsInstance(panel["rows"], list)
        self.assertGreater(len(panel["rows"]), 0)
        self.assertIn("final_decision", panel["rows"][0])

    def test_missing_or_malformed_sections_fail_closed(self) -> None:
        plan = build_phase1_render_plan({"title": "x", "surfaces": {"session_header": "bad"}})

        self.assertGreaterEqual(len(plan["warnings"]), 1)
        sections = {item["key"]: item["panel"] for item in plan["sections"]}
        self.assertEqual(sections["session_header"]["warning"], "unavailable")
        self.assertEqual(sections["run_history"]["warning"], "unavailable")

    def test_startup_and_runtime_markdown_helpers_are_readable(self) -> None:
        shell = build_es_app_shell_for_mode(mode="fixture_demo")
        shell["startup"] = {
            "app_name": "NTB Marimo Console",
            "selected_profile_id": "fixture_es_demo",
            "supported_profiles": [
                {
                    "profile_id": "fixture_es_demo",
                    "runtime_mode": "fixture_demo",
                    "profile_kind": "Demo",
                    "contract": "ES",
                    "session_date": "2026-03-25",
                    "active": True,
                }
            ],
            "candidate_profiles": [
                {
                    "contract": "NQ",
                    "profile_id": "preserved_nq_phase1",
                    "status": "blocked",
                    "reason_category": "blocked_unsupported_query_observable_contract",
                    "reason_label": "Unsupported query observable contract",
                    "summary": "NQ remains blocked under the current console observable contract.",
                }
            ],
            "candidate_audit_available": True,
            "candidate_audit_summary": "Candidate profile status reflects the current preserved-contract audit.",
            "runtime_mode_label": "Fixture/Demo",
            "running_as": "Fixture/Demo",
            "contract": "ES",
            "session_date": "2026-03-25",
            "preflight_status": "PASS",
            "readiness_state": "OPERATOR_SURFACES_READY",
            "readiness_history": [
                "APP_LOADED",
                "PROFILE_SELECTED",
                "PREFLIGHT_PASSED",
                "RUNTIME_ASSEMBLED",
                "OPERATOR_SURFACES_READY",
            ],
            "operator_ready": True,
            "current_session_state": "LIVE_QUERY_ELIGIBLE",
            "status_summary": "Console ready for operator use.",
            "next_action": "Proceed to the operator surfaces.",
            "blocking_checks": [],
        }
        shell["workflow"] = {
            "current_state": "LIVE_QUERY_ELIGIBLE",
            "state_history": ["BOOTSTRAP", "STARTUP_READY", "LIVE_QUERY_ELIGIBLE"],
            "live_query_status": "ELIGIBLE",
            "query_action_status": "AVAILABLE",
            "query_action_available": True,
            "decision_review_ready": False,
            "audit_replay_ready": False,
            "blocked_reasons": [],
            "status_summary": "The loaded snapshot is eligible for a bounded query action.",
            "next_action": "Use the in-app query action.",
            "bounded_action_description": "Runs the bounded pipeline against the loaded snapshot.",
            "error_message": None,
        }
        shell["lifecycle"] = {
            "current_lifecycle_state": "SESSION_RESET_COMPLETED",
            "current_session_state": "LIVE_QUERY_ELIGIBLE",
            "state_history": [
                "BOOTSTRAP",
                "STARTUP_READY",
                "LIVE_QUERY_ELIGIBLE",
                "QUERY_ACTION_REQUESTED",
                "QUERY_ACTION_COMPLETED",
                "DECISION_REVIEW_READY",
                "AUDIT_REPLAY_READY",
                "SESSION_RESET_REQUESTED",
                "SESSION_RESET_COMPLETED",
                "STARTUP_READY",
                "LIVE_QUERY_ELIGIBLE",
            ],
            "last_action": "RESET_SESSION",
            "preflight_reran": False,
            "reload_result": "NOT_RUN",
            "reload_changed_sources": None,
            "reset_available": True,
            "reload_available": True,
            "profile_switch_available": True,
            "profile_switch_target_id": "fixture_es_demo",
            "profile_switch_result": "NOT_RUN",
            "operator_ready": True,
            "query_action_status": "AVAILABLE",
            "decision_review_ready": False,
            "audit_replay_ready": False,
            "status_summary": "Session reset completed.",
            "next_action": "Use the in-app query action.",
        }
        shell["runtime"].update(
            {
                "runtime_backend": "fixture_demo",
                "artifact_root": "fixtures/golden/phase1",
                "adapter_binding": "not_required",
                "preflight_status": "PASS",
                "startup_readiness_state": "OPERATOR_SURFACES_READY",
                "startup_state_history": shell["startup"]["readiness_history"],
                "operator_ready": True,
                "session_state": "LIVE_QUERY_ELIGIBLE",
                "state_history": ["BOOTSTRAP", "STARTUP_READY", "LIVE_QUERY_ELIGIBLE"],
                "query_action_status": "AVAILABLE",
                "decision_review_ready": False,
                "audit_replay_ready": False,
            }
        )
        shell["evidence"] = {
            "history_scope": "BOUNDED_PERSISTED_RECENT_HISTORY",
            "history_limit": 18,
            "persistence_path": "target/ntb_marimo_console/.state/recent_session_evidence.v1.json",
            "restore_status": "RESTORE_OK",
            "restore_status_summary": "Restored 1 retained recent-session evidence entry from the prior persisted ledger.",
            "persistence_health_status": "HEALTHY",
            "last_persistence_status": "WRITE_OK",
            "last_persistence_at_utc": "2026-03-27T12:00:01Z",
            "last_persistence_summary": "Retained evidence persisted successfully with 2 bounded entries.",
            "active_profile_id": "fixture_es_demo",
            "current_session_record_count": 1,
            "restored_record_count": 1,
            "recent_profiles": ["fixture_es_demo"],
            "recent_activity": [
                {
                    "event_index": 1,
                    "recorded_at_utc": "2026-03-27T12:00:00Z",
                    "source_scope": "CURRENT_SESSION",
                    "source_label": "Current Session",
                    "active_profile_id": "fixture_es_demo",
                    "summary": "Loaded fixture_es_demo with preflight PASS and startup outcome OPERATOR_SURFACES_READY.",
                }
            ],
            "last_known_outcomes": [
                {
                    "profile_id": "fixture_es_demo",
                    "has_recent_evidence": True,
                    "event_index": 1,
                    "recorded_at_utc": "2026-03-27T12:00:00Z",
                    "source_scope": "CURRENT_SESSION",
                    "source_label": "Current Session",
                    "last_action": "INITIAL_LOAD",
                    "preflight_status": "PASS",
                    "startup_outcome": "OPERATOR_SURFACES_READY",
                    "query_eligibility_state": "ELIGIBLE",
                    "query_action_state": "AVAILABLE",
                    "decision_review_state": "NOT_READY",
                    "decision_review_outcome": None,
                    "audit_replay_state": "NOT_READY",
                    "audit_replay_outcome": None,
                },
                {
                    "profile_id": "preserved_es_phase1",
                    "has_recent_evidence": False,
                    "status_summary": "No recent session evidence recorded for this profile in the current console session.",
                },
            ],
            "status_summary": "Recent session evidence is ordered by in-console event markers.",
        }

        startup_markdown = build_startup_status_markdown(shell["startup"])
        profile_markdown = build_profile_operations_markdown(shell["startup"])
        evidence_markdown = build_session_evidence_markdown(shell["evidence"])
        runtime_markdown = build_runtime_identity_markdown(shell["runtime"])
        lifecycle_markdown = build_session_lifecycle_markdown(shell["lifecycle"])
        workflow_markdown = build_session_workflow_markdown(shell["workflow"])

        self.assertIn("Startup Status", startup_markdown)
        self.assertIn("Supported Profiles", startup_markdown)
        self.assertIn("Supported Profile Operations", profile_markdown)
        self.assertIn("Candidate Contract Status", profile_markdown)
        self.assertIn("Recent Session Evidence", evidence_markdown)
        self.assertIn("Restore Status", evidence_markdown)
        self.assertIn("Persistence Health", evidence_markdown)
        self.assertIn("Last Persistence Status", evidence_markdown)
        self.assertIn("Last Known Outcome By Supported Profile", evidence_markdown)
        self.assertIn("Current Session", evidence_markdown)
        self.assertIn("Runtime Identity", runtime_markdown)
        self.assertIn("Operator Live Runtime Status", runtime_markdown)
        self.assertIn("Startup Readiness", runtime_markdown)
        self.assertIn("Session Lifecycle", lifecycle_markdown)
        self.assertIn("Operator Live Runtime Status", lifecycle_markdown)
        self.assertIn("Profile Switch Result", lifecycle_markdown)
        self.assertIn("Reload Result", lifecycle_markdown)
        self.assertIn("Session Workflow", workflow_markdown)
        self.assertIn("Query Action Status", workflow_markdown)


class EntrypointSharedRendererTests(unittest.TestCase):
    def test_operator_console_entrypoint_uses_startup_builder(self) -> None:
        source = (PACKAGE_ROOT / "src" / "ntb_marimo_console" / "operator_console_app.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("load_session_lifecycle_from_env", source)
        self.assertIn("build_operator_runtime_snapshot_producer_from_env", source)
        self.assertIn("get_runtime_snapshot_producer", source)
        self.assertIn("refresh_runtime_snapshot", source)
        self.assertIn("mo.ui.refresh", source)
        self.assertIn('default_interval="15s"', source)
        self.assertIn("mo.ui.run_button", source)
        self.assertIn("mo.ui.dropdown", source)
        self.assertIn("Reset Session", source)
        self.assertIn("Reload Current Profile", source)
        self.assertIn("Clear Retained Evidence", source)
        self.assertIn("Switch To Selected Profile", source)
        self.assertIn("switch_profile", source)

    def test_operator_profile_dropdown_uses_label_value_with_raw_profile_state(self) -> None:
        source = (PACKAGE_ROOT / "src" / "ntb_marimo_console" / "operator_console_app.py").read_text(
            encoding="utf-8"
        )

        self.assertIn("profile_options[label] = _option_profile_id", source)
        self.assertIn("profile_label_by_id[_option_profile_id] = label", source)
        self.assertIn("pending_profile_label = profile_label_by_id.get(pending_profile_id)", source)
        self.assertIn("value=pending_profile_label", source)
        self.assertIn("on_change=set_pending_profile_id", source)
        self.assertIn("switch_target = profile_selector.value", source)
        self.assertNotIn("value=pending_profile_id", source)

    def test_operator_ui_elements_are_not_read_in_creator_cell(self) -> None:
        from ntb_marimo_console import operator_console_app

        cell_codes = [cell._cell.code for _, cell in operator_console_app.app._cell_manager.valid_cells()]
        creator_code = next(code for code in cell_codes if "profile_selector = mo.ui.dropdown(" in code)
        action_code = next(code for code in cell_codes if "switch_target = profile_selector.value" in code)

        self.assertNotIn(".value", creator_code)
        self.assertIn("switch_target = profile_selector.value", action_code)
        self.assertIn("switch_button.value", action_code)
        self.assertIn("clear_retained_button.value", action_code)
        self.assertIn("reload_button.value", action_code)
        self.assertIn("reset_button.value", action_code)
        self.assertIn("query_button.value", action_code)

    def test_marimo_dropdown_accepts_display_label_and_returns_raw_profile_id(self) -> None:
        import marimo as mo

        option_label = "fixture_es_demo | Demo | ES | 2026-03-25"
        options = {option_label: "fixture_es_demo"}

        profile_selector = mo.ui.dropdown(options=options, value=option_label)

        self.assertEqual(profile_selector.value, "fixture_es_demo")
        with self.assertRaises(ValueError):
            mo.ui.dropdown(options=options, value="fixture_es_demo")

    def test_demo_entrypoint_uses_shared_renderer(self) -> None:
        source = (PACKAGE_ROOT / "src" / "ntb_marimo_console" / "demo_fixture_app.py").read_text(encoding="utf-8")
        self.assertIn("render_phase1_console", source)
        self.assertNotIn("mo.ui.code_editor(", source)

    def test_preserved_entrypoint_uses_shared_renderer(self) -> None:
        source = (PACKAGE_ROOT / "src" / "ntb_marimo_console" / "preserved_engine_es_app.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("render_phase1_console", source)
        self.assertNotIn("mo.ui.code_editor(", source)


if __name__ == "__main__":
    unittest.main()
