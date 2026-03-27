from __future__ import annotations

import json
from pathlib import Path

from .contracts import PreMarketArtifactStore, PreMarketArtifacts, SessionTarget


class FileSystemPreMarketArtifactStore(PreMarketArtifactStore):
    """Filesystem-backed pre-market store for Phase 1 scaffolding.

    The console treats this as an immutable artifact boundary. If files are
    missing or malformed, callers must fail closed.
    """

    def __init__(self, fixtures_root: str | Path) -> None:
        self._root = Path(fixtures_root)

    def load(self, session: SessionTarget) -> PreMarketArtifacts:
        base = self._root / "premarket" / session.contract / session.session_date
        packet = self._read_json(base / "premarket_packet.json")
        brief = self._read_json(base / "premarket_brief.ready.json")
        return PreMarketArtifacts(packet=packet, brief=brief)

    @staticmethod
    def _read_json(path: Path) -> dict[str, object]:
        with path.open("r", encoding="utf-8") as handle:
            parsed = json.load(handle)
        if not isinstance(parsed, dict):
            raise ValueError(f"Expected object JSON at {path}.")
        return parsed


class FixturePreMarketArtifactStore(FileSystemPreMarketArtifactStore):
    """Backward-compatible fixture artifact store alias."""
