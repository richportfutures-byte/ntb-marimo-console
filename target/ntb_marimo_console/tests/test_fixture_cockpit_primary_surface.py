"""Tests proving the fixture cockpit is the primary Marimo landing surface.

These tests work entirely at the serialization / plan level (plain Python dicts)
so they do not require a running Marimo runtime.
"""

from __future__ import annotations

import json

from ntb_marimo_console.launch_config import build_startup_artifacts_from_env
from ntb_marimo_console.ui.marimo_phase1_renderer import (
    build_phase1_render_plan,
    build_primary_cockpit_plan,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fixture_shell() -> dict:
    """Return the default fixture launch shell (credential-free, non-live)."""
    return build_startup_artifacts_from_env(default_mode="fixture_demo").shell


def _rows_by_contract(plan: dict) -> dict[str, dict]:
    return {r["contract"]: r for r in plan["rows"] if isinstance(r, dict)}


# ---------------------------------------------------------------------------
# Primary-plan tests
# ---------------------------------------------------------------------------


def test_primary_cockpit_plan_is_present_in_default_fixture_launch() -> None:
    """build_primary_cockpit_plan() returns present=True for fixture launch shell."""
    shell = _fixture_shell()
    plan = build_primary_cockpit_plan(shell)

    assert plan["present"] is True, (
        "fixture cockpit plan must be present on default launch"
    )
    assert plan["position"] == "primary", "fixture cockpit must have position='primary'"
    assert plan["key"] == "fixture_cockpit_overview"


def test_primary_cockpit_plan_mode_is_non_live() -> None:
    """The primary cockpit plan carries non-live mode metadata."""
    shell = _fixture_shell()
    plan = build_primary_cockpit_plan(shell)

    assert plan["mode"] == "fixture_dry_run_non_live"
    assert plan["live_credentials_required"] is False
    assert plan["default_launch_live"] is False
    assert plan["decision_authority"] == "preserved_engine_only"


def test_primary_cockpit_plan_covers_five_final_target_contracts() -> None:
    """The primary cockpit plan has rows for ES, NQ, CL, 6E, MGC — and nothing else."""
    shell = _fixture_shell()
    plan = build_primary_cockpit_plan(shell)
    rows = _rows_by_contract(plan)

    for contract in ("ES", "NQ", "CL", "6E", "MGC"):
        assert contract in rows, (
            f"{contract} must be present in primary cockpit plan rows"
        )

    assert "ZN" not in rows, "ZN must not appear as a supported contract"
    assert "GC" not in rows, "GC must not appear as a supported contract"


def test_primary_cockpit_plan_supported_contracts_excludes_zn_gc() -> None:
    """supported_contracts in the primary plan excludes ZN and GC."""
    shell = _fixture_shell()
    plan = build_primary_cockpit_plan(shell)
    supported = plan["supported_contracts"]

    assert "ZN" not in supported
    assert "GC" not in supported
    assert set(supported) == {"ES", "NQ", "CL", "6E", "MGC"}


def test_primary_cockpit_plan_mgc_label_is_micro_gold() -> None:
    """MGC row has profile_label 'Micro Gold', never 'GC'."""
    shell = _fixture_shell()
    plan = build_primary_cockpit_plan(shell)
    rows = _rows_by_contract(plan)

    mgc = rows["MGC"]
    assert mgc["profile_label"] == "Micro Gold", (
        f"MGC must be labeled 'Micro Gold', got {mgc['profile_label']!r}"
    )
    assert mgc["profile_label"] != "GC"


def test_primary_cockpit_plan_per_contract_block_reasons_visible() -> None:
    """Each blocked contract exposes a plain-text reason in the primary cockpit plan."""
    shell = _fixture_shell()
    plan = build_primary_cockpit_plan(shell)
    rows = _rows_by_contract(plan)

    # NQ: blocked for missing chart bars
    nq = rows["NQ"]
    assert nq["chart_status"] == "chart missing"
    assert nq["query_gate_state"] == "DISABLED"
    assert nq["query_action_state"] == "DISABLED"
    assert nq["query_action_text"] == "Manual query blocked."
    assert str(nq["query_disabled_reason"]).startswith("Manual query blocked:")
    assert nq["query_reason"] is not None and nq["query_reason"] != ""

    # CL: blocked for stale quote/chart
    cl = rows["CL"]
    assert cl["quote_status"] == "quote stale"
    assert cl["chart_status"] == "chart stale"
    assert cl["query_action_state"] == "DISABLED"
    assert cl["query_reason"] is not None and cl["query_reason"] != ""

    # 6E: blocked for dependency unavailable
    sixe = rows["6E"]
    assert sixe["query_enabled"] is False
    assert sixe["query_action_state"] == "DISABLED"
    assert sixe["query_disabled_reason"] == "Manual query blocked: required dependency is unavailable for 6E: dxy."
    assert "required dependency is unavailable for 6E: dxy" in str(sixe["query_reason"])
    assert "dependency_unavailable:6E:dxy" in sixe["blocking_reasons"]

    # ES and MGC: eligible
    assert rows["ES"]["query_enabled"] is True
    assert rows["MGC"]["query_enabled"] is True
    assert rows["ES"]["query_action_state"] == "ENABLED"
    assert rows["ES"]["query_action_text"] == "Manual query available: submit preserved pipeline query manually."
    assert rows["ES"]["query_disabled_reason"] is None
    assert rows["MGC"]["query_action_state"] == "ENABLED"


def test_primary_cockpit_plan_display_cannot_create_query_ready() -> None:
    """QUERY_READY provenance in the primary cockpit plan comes only from the real gate."""
    shell = _fixture_shell()
    plan = build_primary_cockpit_plan(shell)

    for row in plan["rows"]:
        if row["query_enabled"] is True:
            assert (
                row["query_ready_provenance"]
                == "real_trigger_state_result_and_pipeline_gate"
            ), (
                f"{row['contract']}: expected real provenance for query_enabled=True, "
                f"got {row['query_ready_provenance']!r}"
            )
            assert row["query_action_provenance"] == "real_trigger_state_result_and_pipeline_gate"
        else:
            assert row["query_ready_provenance"] == (
                "unavailable_not_inferred_from_display_or_raw_enabled_mapping"
            ), (
                f"{row['contract']}: expected unavailable provenance for query_enabled=False, "
                f"got {row['query_ready_provenance']!r}"
            )
            assert row["query_action_provenance"] == "unavailable_not_inferred_from_display_or_raw_enabled_mapping"


def test_primary_cockpit_plan_excludes_raw_market_values() -> None:
    """The primary cockpit plan JSON does not expose raw bid/ask/OHLC values."""
    shell = _fixture_shell()
    plan = build_primary_cockpit_plan(shell)
    plan_json = json.dumps(plan)

    for raw in ("1.125", "100.0", "OHLC"):
        assert raw not in plan_json, f"primary cockpit plan leaks raw value {raw!r}"

    assert "authorization" not in plan_json.lower()
    assert "client_secret" not in plan_json.lower()
    assert "api_key" not in plan_json.lower()
    assert "token_path" not in plan_json.lower()


def test_primary_cockpit_plan_excludes_raw_values_in_shell_surfaces() -> None:
    """The full shell surfaces dict does not expose raw market values via the cockpit surface."""
    shell = _fixture_shell()
    surfaces = shell.get("surfaces", {})
    cockpit_surface = surfaces.get("fixture_cockpit_overview", {})
    surface_json = json.dumps(cockpit_surface)

    for raw in ("1.125", "100.0", "OHLC"):
        assert raw not in surface_json, f"cockpit surface JSON leaks raw value {raw!r}"

    assert "client_secret" not in surface_json.lower()
    assert "api_key" not in surface_json.lower()


def test_primary_cockpit_plan_default_launch_is_non_live() -> None:
    """default_launch_live is False in the primary cockpit plan."""
    shell = _fixture_shell()
    plan = build_primary_cockpit_plan(shell)

    assert plan["default_launch_live"] is False


def test_primary_cockpit_plan_starts_with_no_manual_query_submitted() -> None:
    shell = _fixture_shell()
    plan = build_primary_cockpit_plan(shell)
    result = plan["last_query_result"]

    assert isinstance(result, dict)
    assert result["request_status"] == "NOT_SUBMITTED"
    assert result["submitted"] is False
    assert result["pipeline_result_status"] == "not_submitted"


def test_primary_cockpit_plan_absent_when_no_surface() -> None:
    """build_primary_cockpit_plan() returns present=False when shell has no surfaces."""
    plan = build_primary_cockpit_plan({})

    assert plan["present"] is False
    assert plan["position"] == "unavailable"
    assert plan["rows"] == []


def test_primary_cockpit_plan_absent_when_surface_missing() -> None:
    """build_primary_cockpit_plan() returns present=False when fixture_cockpit_overview absent."""
    shell = {"surfaces": {"some_other_surface": {}}}
    plan = build_primary_cockpit_plan(shell)

    assert plan["present"] is False
    assert plan["position"] == "unavailable"


# ---------------------------------------------------------------------------
# Render-plan position test
# ---------------------------------------------------------------------------


def test_fixture_cockpit_is_primary_not_in_frozen_surface_keys_loop() -> None:
    """The fixture cockpit is NOT in the FROZEN_SURFACE_KEYS render loop.

    It is rendered separately as the primary surface (position='primary') which
    means it appears before the metadata sections driven by FROZEN_SURFACE_KEYS.
    This verifies the two render paths remain distinct.
    """
    from ntb_marimo_console.ui.marimo_phase1_renderer import FROZEN_SURFACE_KEYS

    assert "fixture_cockpit_overview" not in FROZEN_SURFACE_KEYS, (
        "fixture_cockpit_overview must not be in FROZEN_SURFACE_KEYS — "
        "it is rendered as the primary section separately."
    )


def test_build_phase1_render_plan_does_not_include_fixture_cockpit_in_sections() -> (
    None
):
    """build_phase1_render_plan() sections list does not include fixture_cockpit_overview.

    The cockpit is rendered BEFORE the plan sections loop, so it is the first
    operator-visible element even though it does not appear in the plan sections.
    """
    shell = _fixture_shell()
    plan = build_phase1_render_plan(shell)

    section_keys = [item["key"] for item in plan["sections"]]
    assert "fixture_cockpit_overview" not in section_keys, (
        "fixture_cockpit_overview should not appear in build_phase1_render_plan sections "
        "because it is rendered ahead of the sections loop as the primary surface."
    )


def test_primary_cockpit_present_and_sections_present_together() -> None:
    """Default fixture launch produces both a primary cockpit AND valid render-plan sections."""
    shell = _fixture_shell()
    primary = build_primary_cockpit_plan(shell)
    plan = build_phase1_render_plan(shell)

    # Primary cockpit is present
    assert primary["present"] is True
    assert primary["position"] == "primary"

    # Regular sections are also present (they come after the primary cockpit in render order)
    section_keys = [item["key"] for item in plan["sections"]]
    assert "five_contract_readiness_summary" in section_keys
    assert "query_action" in section_keys
