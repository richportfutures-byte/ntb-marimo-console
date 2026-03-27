from __future__ import annotations

import json
from pathlib import Path

from .contracts import RunHistoryRowRecord, RunHistoryStore, SessionTarget


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
