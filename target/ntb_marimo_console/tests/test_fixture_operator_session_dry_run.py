from __future__ import annotations

import builtins
import importlib.util
import os
import subprocess
import sys
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_fixture_operator_session.py"
_spec = importlib.util.spec_from_file_location("run_fixture_operator_session", SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
fixture_session = importlib.util.module_from_spec(_spec)
sys.modules["run_fixture_operator_session"] = fixture_session
_spec.loader.exec_module(fixture_session)


def test_fixture_operator_session_command_runs_without_schwab_credentials() -> None:
    env = {
        key: value
        for key, value in os.environ.items()
        if "SCHWAB" not in key.upper() and "TOKEN" not in key.upper()
    }
    env["PYTHONPATH"] = "src:../../source/ntb_engine/src:."

    result = subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        cwd=SCRIPT_PATH.parents[1],
        env=env,
        check=True,
        text=True,
        capture_output=True,
    )

    assert "mode=fixture_dry_run_non_live" in result.stdout
    assert "live_credentials_required=no" in result.stdout
    assert "network_required=no" in result.stdout


def test_fixture_operator_session_does_not_read_secret_or_token_paths(monkeypatch) -> None:
    original_open = builtins.open
    original_read_text = Path.read_text

    def guarded_open(file, *args, **kwargs):  # type: ignore[no-untyped-def]
        text = str(file)
        assert ".state" not in text
        assert "secret" not in text.lower()
        assert "token" not in text.lower()
        assert "schwab_live.env" not in text
        return original_open(file, *args, **kwargs)

    def guarded_read_text(self: Path, *args, **kwargs):  # type: ignore[no-untyped-def]
        text = str(self)
        assert ".state" not in text
        assert "secret" not in text.lower()
        assert "token" not in text.lower()
        assert "schwab_live.env" not in text
        return original_read_text(self, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(Path, "read_text", guarded_read_text)

    summary = fixture_session.build_fixture_operator_session_summary()

    assert summary["mode"] == "fixture_dry_run_non_live"


def test_fixture_operator_session_summary_covers_final_targets_only() -> None:
    summary = fixture_session.build_fixture_operator_session_summary()
    rows = {row["contract"]: row for row in summary["rows"]}

    assert tuple(rows) == ("ES", "NQ", "CL", "6E", "MGC")
    assert "ZN" not in rows
    assert "GC" not in rows
    assert rows["MGC"]["profile_label"] == "Micro Gold"
    assert rows["MGC"]["profile_label"] != "GC"


def test_fixture_operator_session_mixed_states_and_query_reasons_are_visible() -> None:
    summary = fixture_session.build_fixture_operator_session_summary()
    rows = {row["contract"]: row for row in summary["rows"]}

    assert rows["ES"]["quote_status"] == "quote available"
    assert rows["ES"]["chart_status"] == "chart available"
    assert rows["ES"]["query_gate_state"] == "ENABLED"
    assert rows["ES"]["query_enabled"] is True
    assert rows["NQ"]["chart_status"] == "chart missing"
    assert rows["NQ"]["query_gate_state"] == "DISABLED"
    assert "bars_missing" in rows["NQ"]["query_reason"]
    assert rows["CL"]["quote_status"] == "quote stale"
    assert rows["CL"]["chart_status"] == "chart stale"
    assert "quote_stale" in rows["CL"]["query_reason"]
    assert rows["6E"]["query_enabled"] is False
    assert "dependency_unavailable:6E:dxy" in rows["6E"]["query_reason"]


def test_fixture_operator_session_display_does_not_create_query_ready() -> None:
    summary = fixture_session.build_fixture_operator_session_summary()

    for row in summary["rows"]:
        if row["query_enabled"] is True:
            assert row["query_ready_provenance"] == "real_trigger_state_result_and_pipeline_gate"
        else:
            assert row["query_ready_provenance"] == "unavailable_not_inferred_from_display_or_raw_enabled_mapping"


def test_fixture_operator_session_text_is_sanitized() -> None:
    text = fixture_session.render_fixture_operator_session_text(
        fixture_session.build_fixture_operator_session_summary()
    )

    for contract in ("ES", "NQ", "CL", "6E", "MGC"):
        assert contract in text
    assert "\nZN |" not in text
    assert "\nGC |" not in text
    assert "quote available" in text
    assert "chart missing" in text
    assert "chart stale" in text
    assert "fixture" in text
    assert "1.125" not in text
    assert "1.25" not in text
    assert "OHLC" not in text
    assert "raw streamer payload" not in text.lower()
    assert "authorization" not in text.lower()
    assert "account" not in text.lower()
    assert "best trade" not in text.lower()
    assert "recommend" not in text.lower()
    assert "raw_quote_values_printed=no" in text
    assert "raw_bar_values_printed=no" in text
