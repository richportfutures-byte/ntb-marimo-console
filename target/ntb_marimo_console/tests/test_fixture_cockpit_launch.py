from __future__ import annotations

import json

from ntb_marimo_console.fixture_operator_session import (
    build_fixture_cockpit_shell_surface,
    build_fixture_operator_session_summary,
    render_fixture_operator_session_text,
)
from ntb_marimo_console.launch_config import build_startup_artifacts_from_env

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _rows_by_contract(surface: dict) -> dict[str, dict]:
    rows = surface.get("rows", [])
    return {row["contract"]: row for row in rows if isinstance(row, dict)}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_fixture_cockpit_launch_credential_free() -> None:
    """build_fixture_cockpit_shell_surface() works with no live credentials."""
    surface = build_fixture_cockpit_shell_surface()

    assert surface["live_credentials_required"] is False
    assert surface["network_required"] is False
    assert surface["mode"] == "fixture_dry_run_non_live"
    assert surface["surface"] == "fixture_cockpit_overview"


def test_fixture_cockpit_launch_five_contracts_in_surface() -> None:
    """Surface rows cover exactly the five final-target contracts."""
    surface = build_fixture_cockpit_shell_surface()
    rows = _rows_by_contract(surface)

    for contract in ("ES", "NQ", "CL", "6E", "MGC"):
        assert contract in rows, f"Expected {contract} in surface rows"

    assert "ZN" not in rows
    assert "GC" not in rows


def test_fixture_cockpit_launch_zn_gc_not_supported() -> None:
    """ZN and GC are absent from both supported_contracts and rows."""
    surface = build_fixture_cockpit_shell_surface()
    supported = surface.get("supported_contracts", [])

    assert "ZN" not in supported
    assert "GC" not in supported

    rows = _rows_by_contract(surface)
    assert "ZN" not in rows
    assert "GC" not in rows


def test_fixture_cockpit_launch_mgc_not_mapped_to_gc() -> None:
    """MGC row has profile_label 'Micro Gold', not 'GC'."""
    surface = build_fixture_cockpit_shell_surface()
    rows = _rows_by_contract(surface)

    mgc_row = rows["MGC"]
    assert mgc_row["profile_label"] == "Micro Gold"
    assert mgc_row["profile_label"] != "GC"


def test_fixture_cockpit_display_cannot_create_query_ready() -> None:
    """query_ready_provenance reflects the real gate, not display inference."""
    surface = build_fixture_cockpit_shell_surface()

    for row in surface["rows"]:
        if row["query_enabled"] is True:
            assert (
                row["query_ready_provenance"]
                == "real_trigger_state_result_and_pipeline_gate"
            ), (
                f"{row['contract']}: expected real provenance for query_enabled=True, "
                f"got {row['query_ready_provenance']!r}"
            )
        else:
            assert row["query_ready_provenance"] == (
                "unavailable_not_inferred_from_display_or_raw_enabled_mapping"
            ), (
                f"{row['contract']}: expected unavailable provenance for query_enabled=False, "
                f"got {row['query_ready_provenance']!r}"
            )


def test_fixture_cockpit_output_excludes_raw_values() -> None:
    """Neither the surface JSON nor the rendered text expose raw market values."""
    surface = build_fixture_cockpit_shell_surface()
    summary = build_fixture_operator_session_summary()
    text = render_fixture_operator_session_text(summary)

    surface_json = json.dumps(surface)

    # Raw quote values must not leak into surface or text
    for raw_value in ("1.125", "100.0", "OHLC"):
        assert raw_value not in surface_json, f"surface JSON leaks {raw_value!r}"
        assert raw_value not in text, f"rendered text leaks {raw_value!r}"

    # "1.25" appears as a close value in bar fixture data; must not be in either output
    assert "1.25" not in text, "rendered text leaks raw quote value 1.25"

    # Raw account / authorization material must not appear in text.
    # Note: "live_credentials_required=no" is an expected mode-indicator label,
    # so we check for raw-credential strings, not the sanitization flag itself.
    assert "authorization" not in text.lower()
    assert "account" not in text.lower()
    # Actual raw credential strings (API keys, secrets, token paths) must be absent
    assert "client_secret" not in text.lower()
    assert "api_key" not in text.lower()
    assert "token_path" not in text.lower()


def test_fixture_cockpit_launch_default_non_live() -> None:
    """default_launch_live is False in the fixture cockpit surface."""
    surface = build_fixture_cockpit_shell_surface()

    assert surface["default_launch_live"] is False


def test_fixture_cockpit_marimo_shell_has_surface() -> None:
    """The Marimo startup shell always carries fixture_cockpit_overview."""
    artifacts = build_startup_artifacts_from_env(default_mode="fixture_demo")
    shell = artifacts.shell

    surfaces = shell.get("surfaces")
    assert isinstance(surfaces, dict), "shell.surfaces should be a dict"

    overview = surfaces.get("fixture_cockpit_overview")
    assert overview is not None, "fixture_cockpit_overview not present in surfaces"
    assert isinstance(overview, dict), "fixture_cockpit_overview should be a dict"
    assert overview.get("mode") == "fixture_dry_run_non_live", (
        f"Expected mode='fixture_dry_run_non_live', got {overview.get('mode')!r}"
    )


def test_fixture_cockpit_launch_contract_states_match_expected() -> None:
    """Per-contract gate/query states match the known fixture scenario."""
    surface = build_fixture_cockpit_shell_surface()
    rows = _rows_by_contract(surface)

    # ES: quote + chart both available → gate ENABLED, query allowed
    assert rows["ES"]["query_gate_state"] == "ENABLED"
    assert rows["ES"]["query_enabled"] is True
    assert rows["ES"]["query_action_state"] == "ENABLED"
    assert rows["ES"]["query_action_text"] == "Manual query available: submit preserved pipeline query manually."
    assert rows["ES"]["query_disabled_reason"] is None
    assert rows["ES"]["query_action_source"] == "existing_pipeline_gate_provenance"

    # MGC: all dependencies available → gate ENABLED, query allowed
    assert rows["MGC"]["query_gate_state"] == "ENABLED"
    assert rows["MGC"]["query_enabled"] is True
    assert rows["MGC"]["query_action_state"] == "ENABLED"

    # NQ: no chart bars ingested → chart missing → gate DISABLED
    assert rows["NQ"]["chart_status"] == "chart missing"
    assert rows["NQ"]["query_gate_state"] == "DISABLED"
    assert rows["NQ"]["query_action_state"] == "DISABLED"
    assert rows["NQ"]["query_action_text"] == "Manual query blocked."
    assert str(rows["NQ"]["query_disabled_reason"]).startswith("Manual query blocked:")

    # CL: quote stale (age>60s) and bar blocking reason → both stale
    assert rows["CL"]["quote_status"] == "quote stale"
    assert rows["CL"]["chart_status"] == "chart stale"
    assert rows["CL"]["query_action_state"] == "DISABLED"

    # 6E: dxy dependency unavailable → trigger BLOCKED → query disabled
    assert rows["6E"]["query_enabled"] is False
    assert rows["6E"]["query_action_state"] == "DISABLED"
    assert "required dependency is unavailable for 6E: dxy" in str(rows["6E"]["query_reason"])
    assert "dependency_unavailable:6E:dxy" in rows["6E"]["blocking_reasons"]
    assert rows["6E"]["query_disabled_reason"] == "Manual query blocked: required dependency is unavailable for 6E: dxy."
