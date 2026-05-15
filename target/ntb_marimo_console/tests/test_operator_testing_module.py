"""Tests for the Operator Testing Module V0 surface.

Pins the top operator-facing status board contract: title, status
(READY/NOT_READY), runtime/provider/manual-query state, exactly one top
blocker, exactly one next safe action, five per-contract rows
(ES, NQ, CL, 6E, MGC) — no fixture-demo identity as primary, no
QUERY_READY ever invented by display.
"""

from __future__ import annotations

from ntb_marimo_console.contract_universe import final_target_contracts
from ntb_marimo_console.operator_testing_module import (
    OPERATOR_TESTING_MODULE_SCHEMA,
    OPERATOR_TESTING_MODULE_TITLE,
    OPERATOR_TESTING_STATUS_NOT_READY,
    OPERATOR_TESTING_STATUS_READY,
    build_operator_testing_module_surface,
)
from ntb_marimo_console.primary_cockpit import (
    build_live_observation_cockpit_surface,
)
from ntb_marimo_console.ui.marimo_phase1_renderer import (
    _render_operator_testing_module,
)


def _readiness_row(
    contract: str,
    *,
    quote: str = "quote available",
    chart: str = "chart available",
    trigger: str = "query_not_ready_no_declared_trigger_true",
    query_ready: bool = False,
    runtime_state: str = "LIVE_RUNTIME_CONNECTED",
    provider: str = "active",
) -> dict:
    return {
        "contract": contract,
        "quote_status": quote,
        "chart_status": chart,
        "live_runtime_readiness_state": runtime_state,
        "runtime_provider_status": provider,
        "trigger_state_summary": trigger,
        "query_gate_status": "ELIGIBLE" if query_ready else "BLOCKED",
        "query_ready": query_ready,
        "query_not_ready_reasons": (
            [] if query_ready else ["trigger_state_not_query_ready:TOUCHED"]
        ),
        "missing_live_fields": [],
    }


def _readiness_summary(
    *,
    runtime_status: str = "LIVE_RUNTIME_CONNECTED",
    quote_path_active: bool = True,
    provider_status: str = "active",
    rows: list[dict] | None = None,
) -> dict:
    return {
        "live_runtime_readiness_status": runtime_status,
        "runtime_quote_path_active": quote_path_active,
        "runtime_cache_provider_status": provider_status,
        "rows": rows or [_readiness_row(c) for c in final_target_contracts()],
    }


def _operator_runtime(
    *,
    mode: str = "OPERATOR_LIVE_RUNTIME",
    cache_provider_status: str = "active",
    cache_snapshot_ready: bool = False,
    blocking_reasons: list[str] | None = None,
) -> dict:
    return {
        "mode": mode,
        "cache_provider_status": cache_provider_status,
        "cache_snapshot_ready": cache_snapshot_ready,
        "cache_generated_at": "2026-05-15T14:00:00+00:00",
        "blocking_reasons": blocking_reasons or [],
    }


def _build_v0(
    *,
    readiness_kwargs: dict | None = None,
    runtime_kwargs: dict | None = None,
    engine_profile_id: str | None = "fixture_es_demo",
) -> dict:
    readiness = _readiness_summary(**(readiness_kwargs or {}))
    runtime = _operator_runtime(**(runtime_kwargs or {}))
    cockpit = build_live_observation_cockpit_surface(
        readiness_summary=readiness,
        operator_live_runtime=runtime,
    )
    return build_operator_testing_module_surface(
        readiness_summary=readiness,
        primary_cockpit_surface=cockpit,
        operator_live_runtime=runtime,
        engine_source_profile_id=engine_profile_id,
    )


# -----------------------------------------------------------------------
# V0 surface shape and contract
# -----------------------------------------------------------------------


def test_v0_surface_schema_and_title() -> None:
    surface = _build_v0()
    assert surface["schema"] == OPERATOR_TESTING_MODULE_SCHEMA
    assert surface["title"] == OPERATOR_TESTING_MODULE_TITLE
    assert "Live Observation" in surface["title"]


def test_v0_surface_exposes_required_top_fields() -> None:
    surface = _build_v0()
    for key in (
        "operator_testing_status",
        "runtime_state",
        "runtime_state_text",
        "provider_state",
        "provider_state_text",
        "manual_query_state",
        "manual_query_state_text",
        "top_blocker",
        "next_safe_action",
        "supported_contracts",
        "rows",
    ):
        assert key in surface, f"missing required V0 field: {key}"


def test_v0_supported_contracts_are_five_canonical_only() -> None:
    surface = _build_v0()
    assert surface["supported_contracts"] == ["ES", "NQ", "CL", "6E", "MGC"]
    assert "ZN" not in surface["supported_contracts"]
    assert "GC" not in surface["supported_contracts"]
    assert "ZN" in surface["excluded_contracts"]
    assert "GC" in surface["excluded_contracts"]


def test_v0_rows_are_five_canonical_only() -> None:
    surface = _build_v0()
    row_contracts = [row["contract"] for row in surface["rows"]]
    assert row_contracts == ["ES", "NQ", "CL", "6E", "MGC"]


def test_v0_mgc_label_is_micro_gold_not_gc() -> None:
    surface = _build_v0()
    mgc = next(row for row in surface["rows"] if row["contract"] == "MGC")
    assert mgc["profile_label"] == "Micro Gold"
    assert "GC" not in mgc["profile_label"].upper().split()


def test_v0_each_row_has_required_fields() -> None:
    surface = _build_v0()
    for row in surface["rows"]:
        for key in (
            "contract",
            "profile_label",
            "provider",
            "quote",
            "chart",
            "trigger",
            "query_gate",
            "blocker",
            "next_safe_action",
        ):
            assert key in row, f"{row.get('contract')}: missing row field {key}"


# -----------------------------------------------------------------------
# READY / NOT_READY classification
# -----------------------------------------------------------------------


def test_ready_when_runtime_connected_provider_active_quote_chart_available() -> None:
    """READY_FOR_OPERATOR_TESTING when the runtime/provider/quote/chart are
    coherent and only the query gate remains blocked (which is the V0 product
    state — preserved-engine QUERY_READY is the gate)."""
    surface = _build_v0()
    assert surface["operator_testing_status"] == OPERATOR_TESTING_STATUS_READY


def test_not_ready_when_default_launch_non_live() -> None:
    surface = _build_v0(
        readiness_kwargs={"runtime_status": "LIVE_RUNTIME_NOT_REQUESTED"},
        runtime_kwargs={"mode": "SAFE_NON_LIVE"},
    )
    assert (
        surface["operator_testing_status"]
        == OPERATOR_TESTING_STATUS_NOT_READY
    )
    assert "OPERATOR_LIVE_RUNTIME" in surface["next_safe_action"]


def test_not_ready_when_runtime_unavailable() -> None:
    surface = _build_v0(
        readiness_kwargs={
            "runtime_status": "LIVE_RUNTIME_UNAVAILABLE",
            "quote_path_active": False,
        },
        runtime_kwargs={"cache_provider_status": "blocked"},
    )
    assert (
        surface["operator_testing_status"]
        == OPERATOR_TESTING_STATUS_NOT_READY
    )


def test_not_ready_when_provider_genuinely_stale() -> None:
    rows = [
        _readiness_row(c, runtime_state="LIVE_RUNTIME_STALE", provider="stale")
        for c in final_target_contracts()
    ]
    surface = _build_v0(
        readiness_kwargs={
            "runtime_status": "LIVE_RUNTIME_STALE",
            "quote_path_active": False,
            "provider_status": "stale",
            "rows": rows,
        },
        runtime_kwargs={
            "cache_provider_status": "stale",
            "cache_snapshot_ready": False,
        },
    )
    assert (
        surface["operator_testing_status"]
        == OPERATOR_TESTING_STATUS_NOT_READY
    )
    assert "stale" in surface["top_blocker"].lower()


def test_not_ready_when_quote_missing_for_any_contract() -> None:
    rows = [_readiness_row(c) for c in final_target_contracts()]
    rows[0]["quote_status"] = "quote missing"
    surface = _build_v0(readiness_kwargs={"rows": rows})
    assert (
        surface["operator_testing_status"]
        == OPERATOR_TESTING_STATUS_NOT_READY
    )
    assert "ES" in surface["top_blocker"]
    assert "Quote" in surface["top_blocker"]


def test_not_ready_when_chart_missing_for_any_contract() -> None:
    rows = [_readiness_row(c) for c in final_target_contracts()]
    rows[2]["chart_status"] = "chart stale"
    surface = _build_v0(readiness_kwargs={"rows": rows})
    assert (
        surface["operator_testing_status"]
        == OPERATOR_TESTING_STATUS_NOT_READY
    )
    assert "CL" in surface["top_blocker"]
    assert "Chart" in surface["top_blocker"]


# -----------------------------------------------------------------------
# Top blocker / next safe action coherence
# -----------------------------------------------------------------------


def test_exactly_one_top_blocker_string() -> None:
    surface = _build_v0()
    assert isinstance(surface["top_blocker"], str)


def test_exactly_one_next_safe_action_string() -> None:
    surface = _build_v0()
    assert isinstance(surface["next_safe_action"], str)
    assert len(surface["next_safe_action"]) > 0


def test_ready_state_yields_observation_action() -> None:
    surface = _build_v0()
    assert surface["operator_testing_status"] == OPERATOR_TESTING_STATUS_READY
    # Even in READY state, manual query stays disabled until preserved-engine
    # QUERY_READY provenance. Next safe action must communicate that.
    assert "preserved-engine QUERY_READY" in surface["next_safe_action"]


# -----------------------------------------------------------------------
# Engine source profile is secondary, not primary identity
# -----------------------------------------------------------------------


def test_fixture_es_demo_is_not_primary_identity() -> None:
    surface = _build_v0(engine_profile_id="fixture_es_demo")
    # The primary identity is the V0 title, not the engine profile id.
    assert surface["title"] == OPERATOR_TESTING_MODULE_TITLE
    assert "fixture" not in surface["title"].lower()
    assert "demo" not in surface["title"].lower()
    # But the engine source profile is exposed as secondary metadata.
    assert surface["engine_source_profile_id"] == "fixture_es_demo"


def test_renderer_shows_v0_title_and_engine_profile_as_secondary() -> None:
    surface = _build_v0(engine_profile_id="fixture_es_demo")
    html = _render_operator_testing_module(surface).text
    # Primary identity uses V0 title.
    assert OPERATOR_TESTING_MODULE_TITLE in html
    # Engine profile appears only as secondary/debug metadata.
    assert "Engine source profile: fixture_es_demo" in html
    # The V0 title must NOT be displaced by fixture_es_demo as the primary
    # identity in any heading position.
    assert html.find(OPERATOR_TESTING_MODULE_TITLE) < html.find("fixture_es_demo")


def test_renderer_shows_ready_when_coherent() -> None:
    surface = _build_v0()
    html = _render_operator_testing_module(surface).text
    assert OPERATOR_TESTING_STATUS_READY in html


def test_renderer_shows_not_ready_when_non_live() -> None:
    surface = _build_v0(
        readiness_kwargs={"runtime_status": "LIVE_RUNTIME_NOT_REQUESTED"},
        runtime_kwargs={"mode": "SAFE_NON_LIVE"},
    )
    html = _render_operator_testing_module(surface).text
    assert OPERATOR_TESTING_STATUS_NOT_READY in html


def test_renderer_table_includes_all_five_contracts_and_excludes_zn_gc() -> None:
    surface = _build_v0()
    html = _render_operator_testing_module(surface).text
    for contract in ("ES", "NQ", "CL", "6E", "MGC"):
        assert f"<strong>{contract}</strong>" in html
    # Excluded contracts must not appear as rows.
    assert "<strong>ZN</strong>" not in html
    assert "<strong>GC</strong>" not in html
    assert "Micro Gold" in html


def test_renderer_includes_row_columns() -> None:
    surface = _build_v0()
    html = _render_operator_testing_module(surface).text
    for header in ("Provider", "Quote", "Chart", "Trigger", "Query gate", "Blocker", "Next safe action"):
        assert f">{header}<" in html


# -----------------------------------------------------------------------
# Safety attestations
# -----------------------------------------------------------------------


def test_default_launch_remains_non_live() -> None:
    surface = _build_v0()
    assert surface["default_launch_live"] is False


def test_no_fixture_fallback_after_live_failure() -> None:
    surface = _build_v0()
    assert surface["fixture_fallback_after_live_failure"] is False


def test_manual_query_disabled_without_query_ready_provenance() -> None:
    surface = _build_v0()
    # All readiness rows in _build_v0 have query_ready=False.
    assert surface["manual_query_state"] == "DISABLED"
    for row in surface["rows"]:
        assert row["query_ready"] is False
        # Display-derived provenance must never claim the real preserved-engine
        # provenance unless the upstream row says query_ready is True.
        assert (
            row["query_ready_provenance"]
            == "unavailable_not_inferred_from_display"
        )


def test_display_cannot_invent_query_ready() -> None:
    """The V0 surface mirrors row.query_ready exactly; it never invents True
    from display/view-model state."""
    rows = [_readiness_row(c, query_ready=False) for c in final_target_contracts()]
    surface = _build_v0(readiness_kwargs={"rows": rows})
    for row in surface["rows"]:
        assert row["query_ready"] is False
    assert surface["manual_query_state"] == "DISABLED"
    assert surface["creates_query_ready"] is False


def test_v0_attestations_include_no_raw_values() -> None:
    surface = _build_v0()
    assert surface["raw_quote_values_included"] is False
    assert surface["raw_bar_values_included"] is False
    assert surface["raw_streamer_payloads_included"] is False


def test_decision_authority_remains_preserved_engine_only() -> None:
    surface = _build_v0()
    assert surface["decision_authority"] == "preserved_engine_only"
    assert surface["manual_query_only"] is True
    assert surface["manual_execution_only"] is True


# -----------------------------------------------------------------------
# Per-row blocker semantics
# -----------------------------------------------------------------------


def test_row_blocker_when_only_trigger_blocks() -> None:
    """When runtime/provider/quote/chart are all healthy and only the trigger
    gate keeps query disabled, the row blocker text reflects the trigger
    state, NOT a runtime/provider/chart message."""
    surface = _build_v0()
    for row in surface["rows"]:
        assert "trigger" in row["blocker"].lower()
        assert "preserved-engine" in row["next_safe_action"].lower()


def test_row_blocker_when_quote_missing() -> None:
    rows = [_readiness_row(c) for c in final_target_contracts()]
    rows[0]["quote_status"] = "quote missing"
    surface = _build_v0(readiness_kwargs={"rows": rows})
    es_row = next(r for r in surface["rows"] if r["contract"] == "ES")
    assert "quote" in es_row["blocker"].lower()


def test_row_blocker_when_runtime_not_connected() -> None:
    rows = [
        _readiness_row(c, runtime_state="LIVE_RUNTIME_UNAVAILABLE")
        for c in final_target_contracts()
    ]
    surface = _build_v0(
        readiness_kwargs={
            "runtime_status": "LIVE_RUNTIME_UNAVAILABLE",
            "quote_path_active": False,
            "rows": rows,
        },
        runtime_kwargs={"cache_provider_status": "blocked"},
    )
    for row in surface["rows"]:
        assert "not connected" in row["blocker"].lower()
