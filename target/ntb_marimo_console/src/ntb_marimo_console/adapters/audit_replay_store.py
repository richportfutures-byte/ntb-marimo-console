from __future__ import annotations

from .contracts import AuditReplayRecord, RunHistoryStore, SessionTarget


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
