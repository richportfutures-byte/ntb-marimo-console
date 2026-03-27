from __future__ import annotations

import unittest
from pathlib import Path

from ntb_marimo_console.runtime_modes import build_es_app_shell_for_mode
from ntb_marimo_console.ui.marimo_phase1_renderer import (
    FROZEN_SURFACE_KEYS,
    _flatten_mapping_lines,
    build_phase1_render_plan,
    build_session_lifecycle_markdown,
    build_runtime_identity_markdown,
    build_session_workflow_markdown,
    build_startup_status_markdown,
)


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

    def test_raw_json_debug_is_secondary(self) -> None:
        shell = build_es_app_shell_for_mode(mode="fixture_demo")
        plan = build_phase1_render_plan(shell)

        self.assertTrue(plan["debug"]["secondary"])
        self.assertIn('"surfaces"', plan["debug"]["shell_json"])

    def test_runtime_identity_is_available_without_raw_json_primary_surface(self) -> None:
        source = Path("src/ntb_marimo_console/ui/marimo_phase1_renderer.py").read_text(encoding="utf-8")

        self.assertIn("## Runtime Identity", source)
        self.assertIn("## Startup Status", source)
        self.assertIn("## Session Lifecycle", source)
        self.assertIn("## Session Workflow", source)
        self.assertIn("Preflight Status", source)

    def test_primary_surfaces_do_not_use_code_editor_json(self) -> None:
        source = Path("src/ntb_marimo_console/ui/marimo_phase1_renderer.py").read_text(encoding="utf-8")

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
                    "contract": "ES",
                    "session_date": "2026-03-25",
                }
            ],
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

        startup_markdown = build_startup_status_markdown(shell["startup"])
        runtime_markdown = build_runtime_identity_markdown(shell["runtime"])
        lifecycle_markdown = build_session_lifecycle_markdown(shell["lifecycle"])
        workflow_markdown = build_session_workflow_markdown(shell["workflow"])

        self.assertIn("Startup Status", startup_markdown)
        self.assertIn("Supported Profiles", startup_markdown)
        self.assertIn("Runtime Identity", runtime_markdown)
        self.assertIn("Startup Readiness", runtime_markdown)
        self.assertIn("Session Lifecycle", lifecycle_markdown)
        self.assertIn("Reload Result", lifecycle_markdown)
        self.assertIn("Session Workflow", workflow_markdown)
        self.assertIn("Query Action Status", workflow_markdown)


class EntrypointSharedRendererTests(unittest.TestCase):
    def test_operator_console_entrypoint_uses_startup_builder(self) -> None:
        source = Path("src/ntb_marimo_console/operator_console_app.py").read_text(encoding="utf-8")
        self.assertIn("load_session_lifecycle_from_env", source)
        self.assertIn("mo.ui.run_button", source)
        self.assertIn("Reset Session", source)
        self.assertIn("Reload Current Profile", source)

    def test_demo_entrypoint_uses_shared_renderer(self) -> None:
        source = Path("src/ntb_marimo_console/demo_fixture_app.py").read_text(encoding="utf-8")
        self.assertIn("render_phase1_console", source)
        self.assertNotIn("mo.ui.code_editor(", source)

    def test_preserved_entrypoint_uses_shared_renderer(self) -> None:
        source = Path("src/ntb_marimo_console/preserved_engine_es_app.py").read_text(encoding="utf-8")
        self.assertIn("render_phase1_console", source)
        self.assertNotIn("mo.ui.code_editor(", source)


if __name__ == "__main__":
    unittest.main()
