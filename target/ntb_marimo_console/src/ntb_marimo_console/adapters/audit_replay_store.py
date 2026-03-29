from __future__ import annotations

from pathlib import Path

from ninjatradebuilder.logging_record import read_log_records

from .contracts import AuditReplayRecord, RunHistoryStore, SessionTarget
from .stage_e_log import resolve_stage_e_log_path


class FixtureAuditReplayStore:
    """Fixture-backed audit/replay source for Phase 1 surfaces.

    This is intentionally bounded and never reads live Stage E storage.
    """

    def __init__(self, run_history_store: RunHistoryStore) -> None:
        self._run_history_store = run_history_store

    def load_replay(self, session: SessionTarget) -> AuditReplayRecord:
        rows = self._run_history_store.list_rows(session)
        if not rows:
            return {
                "source": "fixture_backed",
                "stage_e_live_backend": False,
                "replay_available": False,
                "last_run_id": None,
                "last_final_decision": None,
            }

        latest = rows[-1]
        return {
            "source": "fixture_backed",
            "stage_e_live_backend": False,
            "replay_available": True,
            "last_run_id": str(latest.get("run_id")),
            "last_final_decision": str(latest.get("final_decision")),
        }


class JsonlAuditReplayStore:
    """Read bounded audit/replay state from engine-owned JSONL records."""

    def __init__(self, log_root: str | Path | None = None) -> None:
        self._root = log_root

    def load_replay(self, session: SessionTarget) -> AuditReplayRecord:
        path = resolve_stage_e_log_path(session.contract, root=self._root)
        latest = None
        for record in read_log_records(path):
            if record.contract != session.contract:
                continue
            session_date = record.evaluation_timestamp_iso.split("T", 1)[0]
            if session_date != session.session_date:
                continue
            latest = record

        if latest is None:
            return {
                "source": "stage_e_jsonl",
                "stage_e_live_backend": True,
                "replay_available": False,
                "last_run_id": None,
                "last_final_decision": None,
            }

        return {
            "source": "stage_e_jsonl",
            "stage_e_live_backend": True,
            "replay_available": True,
            "last_run_id": latest.run_id,
            "last_final_decision": latest.final_decision,
        }
