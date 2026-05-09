from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from ninjatradebuilder.logging_record import RunHistoryRecord, append_log_record

from ntb_marimo_console.adapters.audit_replay_store import JsonlAuditReplayStore
from ntb_marimo_console.adapters.run_history_store import JsonlRunHistoryStore
from ntb_marimo_console.adapters.stage_e_log import resolve_stage_e_log_path
from ntb_marimo_console.adapters.contracts import SessionTarget


def _record(*, contract: str, evaluation_timestamp_iso: str, run_id: str, final_decision: str | None) -> RunHistoryRecord:
    return RunHistoryRecord(
        run_id=run_id,
        logged_at=datetime.now(tz=timezone.utc),
        contract=contract,
        evaluation_timestamp_iso=evaluation_timestamp_iso,
        run_type="full_pipeline",
        trigger_family="price_level_touch",
        watchman_status="ready",
        watchman_hard_lockouts=[],
        watchman_awareness_flags=[],
        watchman_missing_inputs=[],
        vwap_posture="price_above_vwap",
        value_location="inside_value",
        level_proximity="clear_of_structure",
        event_risk="clear",
        trigger_state="trigger_true",
        final_decision=final_decision,
        termination_stage="contract_market_read",
        sufficiency_gate_status="READY",
        contract_analysis_outcome="NO_TRADE",
        proposed_setup_outcome=None,
        risk_authorization_decision=None,
        notes="test record",
    )


class StageEJsonlStoreTests(unittest.TestCase):
    def test_run_history_reads_only_matching_contract_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict("os.environ", {"NTB_STAGE_E_LOG_ROOT": temp_dir}):
                append_log_record(
                    _record(
                        contract="ES",
                        evaluation_timestamp_iso="2026-03-25T13:35:00Z",
                        run_id="es-1",
                        final_decision="NO_TRADE",
                    ),
                    resolve_stage_e_log_path("ES"),
                )
                append_log_record(
                    _record(
                        contract="ES",
                        evaluation_timestamp_iso="2026-03-26T13:35:00Z",
                        run_id="es-2",
                        final_decision="NO_TRADE",
                    ),
                    resolve_stage_e_log_path("ES"),
                )
                append_log_record(
                    _record(
                        contract="NQ",
                        evaluation_timestamp_iso="2026-01-14T15:05:00Z",
                        run_id="nq-1",
                        final_decision="NO_TRADE",
                    ),
                    resolve_stage_e_log_path("NQ"),
                )

                store = JsonlRunHistoryStore()
                rows = store.list_rows(SessionTarget(contract="ES", session_date="2026-03-25"))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["run_id"], "es-1")
        self.assertEqual(rows[0]["session_date"], "2026-03-25")
        self.assertEqual(store.source_label(SessionTarget(contract="ES", session_date="2026-03-25")), "stage_e_jsonl")

    def test_audit_replay_reports_latest_matching_record(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict("os.environ", {"NTB_STAGE_E_LOG_ROOT": temp_dir}):
                append_log_record(
                    _record(
                        contract="CL",
                        evaluation_timestamp_iso="2026-01-14T14:05:00Z",
                        run_id="cl-1",
                        final_decision="NO_TRADE",
                    ),
                    resolve_stage_e_log_path("CL"),
                )
                append_log_record(
                    _record(
                        contract="CL",
                        evaluation_timestamp_iso="2026-01-14T14:06:00Z",
                        run_id="cl-2",
                        final_decision="TRADE_APPROVED",
                    ),
                    resolve_stage_e_log_path("CL"),
                )

                replay = JsonlAuditReplayStore().load_replay(
                    SessionTarget(contract="CL", session_date="2026-01-14")
                )

        self.assertEqual(replay["source"], "stage_e_jsonl")
        self.assertTrue(replay["stage_e_live_backend"])
        self.assertTrue(replay["replay_available"])
        self.assertEqual(replay["last_run_id"], "cl-2")
        self.assertEqual(replay["last_final_decision"], "TRADE_APPROVED")

    def test_missing_jsonl_history_is_empty_and_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict("os.environ", {"NTB_STAGE_E_LOG_ROOT": temp_dir}):
                rows = JsonlRunHistoryStore().list_rows(
                    SessionTarget(contract="MGC", session_date="2026-01-14")
                )
                replay = JsonlAuditReplayStore().load_replay(
                    SessionTarget(contract="MGC", session_date="2026-01-14")
                )

        self.assertEqual(rows, [])
        self.assertFalse(replay["replay_available"])
        self.assertTrue(replay["stage_e_live_backend"])


if __name__ == "__main__":
    unittest.main()
