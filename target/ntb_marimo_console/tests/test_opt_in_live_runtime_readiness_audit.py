from __future__ import annotations

from pathlib import Path


DOC_PATH = Path(__file__).resolve().parents[1] / "docs" / "opt_in_live_runtime_readiness_audit.md"


def test_opt_in_live_runtime_readiness_audit_records_r26_producer_update() -> None:
    text = DOC_PATH.read_text(encoding="utf-8")

    assert "R24 verdict at the time of the audit" in text
    assert "R26 update" in text
    assert "can pass a supplied `StreamManagerSnapshot` or `StreamCacheSnapshot`" in text
    assert "reports `LIVE_RUNTIME_UNAVAILABLE`" in text
    assert "no longer uses a `NOT_WIRED` state" in text
    assert "ES`, `NQ`, `CL`, `6E`, and `MGC" in text
    assert "excluded contracts are `ZN` and `GC`" in text
    assert "`MGC` remains Micro Gold" in text
    assert "`MIN_STREAM_REFRESH_FLOOR_SECONDS` remains 15 seconds" in text
    assert "Default launch remains non-live" in text
    assert "require no Schwab credentials" in text
