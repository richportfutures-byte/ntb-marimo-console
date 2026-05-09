from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ntb_marimo_console.session_evidence import (
    SESSION_EVIDENCE_LIMIT,
    SESSION_EVIDENCE_SCHEMA_VERSION,
)
from ntb_marimo_console.session_evidence_store import (
    clear_session_evidence_history,
    persist_session_evidence_history,
    restore_session_evidence_history,
)
from ntb_marimo_console.session_lifecycle import (
    clear_retained_evidence,
    load_session_lifecycle_from_env,
    reload_current_profile,
    request_query_action,
    reset_session,
    switch_profile,
)
from ntb_marimo_console.ui.marimo_phase1_renderer import build_session_evidence_markdown


FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "golden" / "phase1"


class SessionEvidenceStoreTests(unittest.TestCase):
    def test_persistence_round_trip_for_evidence_records(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / ".state" / "recent_session_evidence.v1.json"
            lifecycle = self._load_profile("preserved_es_phase1", store_path=store_path)
            lifecycle = request_query_action(lifecycle)
            lifecycle = switch_profile(lifecycle, "preserved_nq_phase1")

            restored = restore_session_evidence_history(path=store_path)

        self.assertEqual(restored.restore_status, "RESTORE_OK")
        self.assertEqual(len(restored.history), 3)
        self.assertEqual(restored.history[0].active_profile_id, "preserved_es_phase1")
        self.assertEqual(restored.history[1].lifecycle_action, "RUN_BOUNDED_QUERY")
        self.assertEqual(restored.history[2].active_profile_id, "preserved_nq_phase1")
        self.assertEqual(restored.history[2].originating_profile_id, "preserved_es_phase1")

    def test_bounded_retention_across_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / ".state" / "recent_session_evidence.v1.json"
            lifecycle = self._load_profile("preserved_es_phase1", store_path=store_path)
            targets = (
                "preserved_nq_phase1",
                "preserved_cl_phase1",
                "preserved_es_phase1",
            )
            total_events = 1
            for index in range(24):
                lifecycle = switch_profile(lifecycle, targets[index % len(targets)])
                total_events += 1

            restored = restore_session_evidence_history(path=store_path)

        self.assertEqual(restored.restore_status, "RESTORE_OK")
        self.assertEqual(len(restored.history), SESSION_EVIDENCE_LIMIT)
        self.assertEqual(restored.history[0].event_index, total_events - SESSION_EVIDENCE_LIMIT + 1)
        self.assertEqual(restored.history[-1].event_index, total_events)

    def test_schema_version_handling_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / ".state" / "recent_session_evidence.v1.json"
            store_path.parent.mkdir(parents=True, exist_ok=True)
            store_path.write_text(
                json.dumps(
                    {
                        "payload_type": "ntb_marimo_console.session_evidence",
                        "schema_version": SESSION_EVIDENCE_SCHEMA_VERSION + 1,
                        "history_limit": SESSION_EVIDENCE_LIMIT,
                        "saved_at_utc": "2026-03-27T12:00:00Z",
                        "records": [],
                    }
                ),
                encoding="utf-8",
            )

            restored = restore_session_evidence_history(path=store_path)
            lifecycle = self._load_profile("preserved_es_phase1", store_path=store_path)

        self.assertEqual(restored.restore_status, "RESTORE_BLOCKED")
        self.assertEqual(restored.history, tuple())
        self.assertEqual(lifecycle.shell["evidence"]["restore_status"], "RESTORE_BLOCKED")
        self.assertEqual(lifecycle.shell["evidence"]["restored_record_count"], 0)
        self.assertEqual(lifecycle.shell["evidence"]["current_session_record_count"], 1)

    def test_corrupt_or_malformed_persistence_file_is_ignored_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / ".state" / "recent_session_evidence.v1.json"
            store_path.parent.mkdir(parents=True, exist_ok=True)
            store_path.write_text("{ bad json", encoding="utf-8")

            lifecycle = self._load_profile("preserved_es_phase1", store_path=store_path)
            restored = restore_session_evidence_history(path=store_path)

        self.assertTrue(lifecycle.ready)
        self.assertEqual(lifecycle.shell["evidence"]["restore_status"], "RESTORE_BLOCKED")
        self.assertIn("could not be restored", lifecycle.shell["evidence"]["restore_status_summary"])
        self.assertEqual(restored.restore_status, "RESTORE_OK")
        self.assertEqual(len(restored.history), 1)

    def test_restore_prior_evidence_for_preserved_es_nq_and_cl(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / ".state" / "recent_session_evidence.v1.json"
            lifecycle = self._load_profile("preserved_es_phase1", store_path=store_path)
            lifecycle = request_query_action(lifecycle)
            lifecycle = switch_profile(lifecycle, "preserved_nq_phase1")
            lifecycle = switch_profile(lifecycle, "preserved_cl_phase1")

            restarted = self._load_profile("preserved_es_phase1", store_path=store_path)
            outcomes = self._outcomes_by_profile(restarted.shell["evidence"])

        self.assertEqual(restarted.shell["evidence"]["restore_status"], "RESTORE_OK")
        self.assertEqual(outcomes["preserved_es_phase1"]["source_scope"], "CURRENT_SESSION")
        self.assertEqual(outcomes["preserved_nq_phase1"]["source_scope"], "RESTORED_PRIOR_RUN")
        self.assertEqual(outcomes["preserved_cl_phase1"]["source_scope"], "RESTORED_PRIOR_RUN")
        self.assertEqual(outcomes["preserved_nq_phase1"]["last_action"], "SWITCH_PROFILE")
        self.assertEqual(outcomes["preserved_cl_phase1"]["last_action"], "SWITCH_PROFILE")

    def test_explicit_clear_removes_retained_durable_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / ".state" / "recent_session_evidence.v1.json"
            lifecycle = self._load_profile("preserved_es_phase1", store_path=store_path)
            lifecycle = request_query_action(lifecycle)
            lifecycle = switch_profile(lifecycle, "preserved_nq_phase1")
            cleared = clear_retained_evidence(lifecycle)
            restored = restore_session_evidence_history(path=store_path)

        self.assertEqual(cleared.shell["evidence"]["restore_status"], "RESTORE_CLEARED")
        self.assertEqual(cleared.shell["evidence"]["restored_record_count"], 0)
        self.assertEqual(cleared.shell["evidence"]["last_persistence_status"], "CLEAR_OK")
        self.assertEqual(restored.restore_status, "RESTORE_MISSING")
        self.assertEqual(restored.history, tuple())

    def test_after_clear_next_launch_has_no_restored_prior_run_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / ".state" / "recent_session_evidence.v1.json"
            lifecycle = self._load_profile("preserved_es_phase1", store_path=store_path)
            lifecycle = request_query_action(lifecycle)
            lifecycle = switch_profile(lifecycle, "preserved_nq_phase1")
            lifecycle = clear_retained_evidence(lifecycle)

            restarted = self._load_profile("preserved_cl_phase1", store_path=store_path)

        self.assertEqual(restarted.shell["evidence"]["restore_status"], "RESTORE_MISSING")
        self.assertEqual(restarted.shell["evidence"]["restored_record_count"], 0)
        self.assertEqual(restarted.shell["evidence"]["current_session_record_count"], 1)

    def test_clear_does_not_cause_cross_profile_bleed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / ".state" / "recent_session_evidence.v1.json"
            lifecycle = self._load_profile("preserved_es_phase1", store_path=store_path)
            lifecycle = request_query_action(lifecycle)
            lifecycle = switch_profile(lifecycle, "preserved_nq_phase1")
            lifecycle = clear_retained_evidence(lifecycle)
            lifecycle = switch_profile(lifecycle, "preserved_cl_phase1")

            restarted = self._load_profile("preserved_es_phase1", store_path=store_path)
            outcomes = self._outcomes_by_profile(restarted.shell["evidence"])

        self.assertEqual(outcomes["preserved_es_phase1"]["source_scope"], "CURRENT_SESSION")
        self.assertEqual(outcomes["preserved_cl_phase1"]["source_scope"], "RESTORED_PRIOR_RUN")
        self.assertNotIn("preserved_nq_phase1", {
            key: value for key, value in outcomes.items() if value.get("source_scope") == "RESTORED_PRIOR_RUN"
        })

    def test_clear_twice_is_readable_in_lifecycle_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / ".state" / "recent_session_evidence.v1.json"
            lifecycle = self._load_profile("preserved_es_phase1", store_path=store_path)
            lifecycle = clear_retained_evidence(lifecycle)
            lifecycle = clear_retained_evidence(lifecycle)

        self.assertEqual(lifecycle.shell["evidence"]["last_persistence_status"], "CLEAR_MISSING")
        self.assertEqual(lifecycle.shell["evidence"]["persistence_health_status"], "HEALTHY")
        self.assertIn("nothing to clear", lifecycle.shell["evidence"]["last_persistence_summary"])

    def test_clear_is_readable_when_no_retained_file_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / ".state" / "recent_session_evidence.v1.json"
            status = clear_session_evidence_history(path=store_path)

        self.assertEqual(status.health_status, "HEALTHY")
        self.assertEqual(status.last_status, "CLEAR_MISSING")
        self.assertIn("nothing to clear", status.last_message)

    def test_persistence_health_and_last_write_status_are_grounded(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / ".state" / "recent_session_evidence.v1.json"
            lifecycle = self._load_profile("preserved_es_phase1", store_path=store_path)
            evidence = lifecycle.shell["evidence"]

        self.assertEqual(evidence["persistence_health_status"], "HEALTHY")
        self.assertEqual(evidence["last_persistence_status"], "WRITE_OK")
        self.assertTrue(evidence["last_persistence_at_utc"])
        self.assertIn("persisted successfully", evidence["last_persistence_summary"])

    def test_persistence_failure_paths_remain_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / ".state" / "recent_session_evidence.v1.json"
            lifecycle = self._load_profile("preserved_es_phase1", store_path=store_path)
            with patch("ntb_marimo_console.session_evidence_store.os.replace", side_effect=OSError("disk blocked")):
                queried = request_query_action(lifecycle)

        self.assertEqual(queried.shell["evidence"]["persistence_health_status"], "BLOCKED")
        self.assertEqual(queried.shell["evidence"]["last_persistence_status"], "WRITE_FAILED")
        self.assertIn("could not be written", queried.shell["evidence"]["last_persistence_summary"])

    def test_clear_failure_path_remains_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / ".state" / "recent_session_evidence.v1.json"
            lifecycle = self._load_profile("preserved_es_phase1", store_path=store_path)
            with patch("pathlib.Path.unlink", side_effect=OSError("clear blocked")):
                cleared = clear_retained_evidence(lifecycle)

        self.assertEqual(cleared.shell["evidence"]["persistence_health_status"], "BLOCKED")
        self.assertEqual(cleared.shell["evidence"]["last_persistence_status"], "CLEAR_FAILED")
        self.assertIn("could not be cleared", cleared.shell["evidence"]["last_persistence_summary"])

    def test_profile_switch_attribution_integrity_after_restore(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / ".state" / "recent_session_evidence.v1.json"
            lifecycle = self._load_profile("preserved_es_phase1", store_path=store_path)
            lifecycle = request_query_action(lifecycle)
            lifecycle = switch_profile(lifecycle, "preserved_nq_phase1")

            restarted = self._load_profile("preserved_es_phase1", store_path=store_path)
            switched = switch_profile(restarted, "preserved_cl_phase1")
            outcomes = self._outcomes_by_profile(switched.shell["evidence"])

        self.assertEqual(outcomes["preserved_es_phase1"]["query_action_state"], "AVAILABLE")
        self.assertEqual(outcomes["preserved_es_phase1"]["source_scope"], "CURRENT_SESSION")
        self.assertEqual(outcomes["preserved_nq_phase1"]["source_scope"], "RESTORED_PRIOR_RUN")
        self.assertEqual(outcomes["preserved_cl_phase1"]["source_scope"], "CURRENT_SESSION")
        self.assertEqual(switched.evidence_history[-1].originating_profile_id, "preserved_es_phase1")
        self.assertEqual(switched.evidence_history[-1].requested_profile_id, "preserved_cl_phase1")

    def test_reset_attribution_persists_across_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / ".state" / "recent_session_evidence.v1.json"
            lifecycle = self._load_profile("preserved_cl_phase1", store_path=store_path)
            lifecycle = request_query_action(lifecycle)
            lifecycle = reset_session(lifecycle)

            restarted = self._load_profile("preserved_es_phase1", store_path=store_path)
            outcomes = self._outcomes_by_profile(restarted.shell["evidence"])

        self.assertEqual(outcomes["preserved_cl_phase1"]["source_scope"], "RESTORED_PRIOR_RUN")
        self.assertEqual(outcomes["preserved_cl_phase1"]["last_action"], "RESET_SESSION")
        self.assertEqual(outcomes["preserved_cl_phase1"]["query_action_state"], "AVAILABLE")

    def test_reload_attribution_persists_across_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / ".state" / "recent_session_evidence.v1.json"
            lifecycle = self._load_profile("preserved_cl_phase1", store_path=store_path)
            lifecycle = request_query_action(lifecycle)
            lifecycle = reload_current_profile(lifecycle)

            restarted = self._load_profile("preserved_nq_phase1", store_path=store_path)
            outcomes = self._outcomes_by_profile(restarted.shell["evidence"])

        self.assertEqual(outcomes["preserved_cl_phase1"]["source_scope"], "RESTORED_PRIOR_RUN")
        self.assertEqual(outcomes["preserved_cl_phase1"]["last_action"], "RELOAD_CURRENT_PROFILE")
        self.assertEqual(outcomes["preserved_cl_phase1"]["reload_result"], "RELOADED_UNCHANGED")

    def test_blocked_and_failure_attribution_persist_across_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / ".state" / "recent_session_evidence.v1.json"
            lifecycle = self._load_profile("preserved_es_phase1", store_path=store_path)
            lifecycle = switch_profile(lifecycle, "preserved_zn_phase1")

            source_root = FIXTURES_ROOT
            artifact_root = Path(temp_dir) / "phase1"
            shutil.copytree(source_root, artifact_root)
            fixture_lifecycle = self._load_profile(
                "fixture_es_demo",
                store_path=store_path,
                extra_env={"NTB_FIXTURES_ROOT": str(artifact_root)},
            )
            (artifact_root / "premarket" / "ES" / "2026-03-25" / "premarket_packet.json").unlink()
            fixture_lifecycle = reload_current_profile(fixture_lifecycle)

            restarted = self._load_profile("preserved_cl_phase1", store_path=store_path)
            outcomes = self._outcomes_by_profile(restarted.shell["evidence"])

        self.assertEqual(outcomes["preserved_es_phase1"]["source_scope"], "RESTORED_PRIOR_RUN")
        self.assertEqual(outcomes["preserved_es_phase1"]["profile_switch_result"], "SWITCH_BLOCKED")
        self.assertEqual(outcomes["fixture_es_demo"]["source_scope"], "RESTORED_PRIOR_RUN")
        self.assertEqual(outcomes["fixture_es_demo"]["reload_result"], "RELOAD_FAILED")
        self.assertEqual(outcomes["fixture_es_demo"]["startup_outcome"], "BLOCKED")

    def test_renderer_output_shows_current_session_vs_restored_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / ".state" / "recent_session_evidence.v1.json"
            lifecycle = self._load_profile("preserved_es_phase1", store_path=store_path)
            lifecycle = request_query_action(lifecycle)
            lifecycle = switch_profile(lifecycle, "preserved_nq_phase1")

            restarted = self._load_profile("preserved_es_phase1", store_path=store_path)
            markdown = build_session_evidence_markdown(restarted.shell["evidence"])

        self.assertIn("Restore Status", markdown)
        self.assertIn("Persistence Health", markdown)
        self.assertIn("Current Session Events", markdown)
        self.assertIn("Restored Prior-Run Events", markdown)
        self.assertIn("Current Session", markdown)
        self.assertIn("Restored Prior Run", markdown)

    def test_persist_helper_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store_path = Path(temp_dir) / ".state" / "recent_session_evidence.v1.json"
            lifecycle = self._load_profile("preserved_es_phase1", store_path=store_path)
            persistence_status = persist_session_evidence_history(lifecycle.evidence_history, path=store_path)
            restored = restore_session_evidence_history(path=persistence_status.persistence_path)

        self.assertEqual(restored.restore_status, "RESTORE_OK")
        self.assertEqual(persistence_status.last_status, "WRITE_OK")
        self.assertEqual(len(restored.history), 1)
        self.assertEqual(restored.history[0].active_profile_id, "preserved_es_phase1")

    @staticmethod
    def _outcomes_by_profile(evidence_panel: dict[str, object]) -> dict[str, dict[str, object]]:
        outcomes = evidence_panel["last_known_outcomes"]
        assert isinstance(outcomes, list)
        return {
            str(item["profile_id"]): item
            for item in outcomes
            if isinstance(item, dict)
        }

    @staticmethod
    def _load_profile(
        profile_id: str,
        *,
        store_path: Path,
        extra_env: dict[str, str] | None = None,
    ):
        env = {"NTB_CONSOLE_PROFILE": profile_id}
        if extra_env is not None:
            env.update(extra_env)
        with patch.dict(os.environ, env, clear=True):
            return load_session_lifecycle_from_env(evidence_store_path=store_path)


if __name__ == "__main__":
    unittest.main()
