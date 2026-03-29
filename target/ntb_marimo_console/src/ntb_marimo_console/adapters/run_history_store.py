from __future__ import annotations

import json
from pathlib import Path

from ninjatradebuilder.logging_record import read_log_records

from .contracts import RunHistoryRowRecord, RunHistoryStore, SessionTarget
from .stage_e_log import resolve_stage_e_log_path


class FixtureRunHistoryStore(RunHistoryStore):
    """Fixture-backed run history source.

    Phase 1 freeze forbids live-backed Stage E ingestion in the console.
    """

    def __init__(self, fixtures_root: str | Path) -> None:
        self._root = Path(fixtures_root)

    def list_rows(self, session: SessionTarget) -> list[RunHistoryRowRecord]:
        path = (
            self._root
            / "history"
            / session.contract
            / f"run_history.{session.session_date}.fixture.json"
        )
        if not path.exists():
            fallback = self._root / "history" / session.contract / "run_history.fixture.json"
            path = fallback
        with path.open("r", encoding="utf-8") as handle:
            parsed = json.load(handle)
        if not isinstance(parsed, list):
            raise ValueError(f"Expected array JSON at {path}.")
        rows: list[RunHistoryRowRecord] = []
        for item in parsed:
            if not isinstance(item, dict):
                raise ValueError(f"Expected object rows in {path}.")
            rows.append(item)
        return rows

    def source_label(self, session: SessionTarget) -> str:
        return "fixture_backed"


class JsonlRunHistoryStore(RunHistoryStore):
    """Read bounded run history from engine-owned JSONL records."""

    def __init__(self, log_root: str | Path | None = None) -> None:
        self._root = log_root

    def list_rows(self, session: SessionTarget) -> list[RunHistoryRowRecord]:
        path = resolve_stage_e_log_path(session.contract, root=self._root)
        records = read_log_records(path)
        rows: list[RunHistoryRowRecord] = []
        for record in records:
            if record.contract != session.contract:
                continue
            session_date = record.evaluation_timestamp_iso.split("T", 1)[0]
            if session_date != session.session_date:
                continue
            rows.append(
                {
                    "run_id": record.run_id,
                    "logged_at": record.logged_at.isoformat().replace("+00:00", "Z"),
                    "contract": record.contract,
                    "session_date": session_date,
                    "run_type": record.run_type,
                    "final_decision": record.final_decision,
                    "termination_stage": record.termination_stage,
                    "stage_d_decision": record.risk_authorization_decision,
                    "notes": record.notes or "",
                }
            )
        return rows

    def source_label(self, session: SessionTarget) -> str:
        return "stage_e_jsonl"
