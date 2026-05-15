"""Tests for live cockpit status coherence.

Pins the contract that the live-observation cockpit header, mode line,
current-state summary, and contract rows tell one coherent story:

- ``LIVE_RUNTIME_CONNECTED`` never produces an "Operator Runtime Cache
  Unavailable" headline.
- Runtime connected with a downstream query/trigger blocker renders a
  "Query Gate Blocked" headline rather than a runtime-cache-unavailable
  headline.
- Runtime not connected continues to render the runtime-level headline so
  the operator sees why the cache is unusable.
- Provider status displayed in the header is the quote-path-corrected
  value: "stale" is only the headline when the quote path is not active.
- Display/view-model rendering never creates QUERY_READY.
- Manual query remains blocked without preserved-engine ``QUERY_READY``
  provenance.
- Default launch remains non-live; ES/NQ/CL/6E/MGC remain the only
  final-target contracts; ZN/GC remain excluded; MGC remains Micro Gold.
"""

from __future__ import annotations

from ntb_marimo_console.contract_universe import final_target_contracts
from ntb_marimo_console.primary_cockpit import (
    FAIL_CLOSED_REASON_QUERY_GATE_BLOCKED,
    FAIL_CLOSED_REASON_RUNTIME_CACHE_UNAVAILABLE,
    FAIL_CLOSED_REASON_RUNTIME_STALE,
    LIVE_OBSERVATION_MODE_CONNECTED,
    LIVE_OBSERVATION_MODE_FAIL_CLOSED,
    build_live_observation_cockpit_surface,
)
from ntb_marimo_console.ui.marimo_phase1_renderer import (
    _render_fixture_cockpit_primary,
)


def render_primary_cockpit_html(surface: dict) -> str:
    return _render_fixture_cockpit_primary(surface).text


# -----------------------------------------------------------------------
# Helper builders
# -----------------------------------------------------------------------


def _readiness_summary(
    *,
    runtime_status: str = "LIVE_RUNTIME_CONNECTED",
    quote_path_active: bool = True,
    rows: list[dict] | None = None,
) -> dict:
    return {
        "live_runtime_readiness_status": runtime_status,
        "runtime_quote_path_active": quote_path_active,
        "rows": rows or [_row(contract) for contract in final_target_contracts()],
    }


def _runtime_payload(
    *,
    cache_provider_status: str = "active",
    cache_snapshot_ready: bool = True,
    blocking_reasons: list[str] | None = None,
) -> dict:
    return {
        "cache_provider_status": cache_provider_status,
        "cache_snapshot_ready": cache_snapshot_ready,
        "cache_generated_at": "2026-05-15T14:00:00+00:00",
        "blocking_reasons": blocking_reasons or [],
    }


def _row(contract: str, *, query_ready: bool = False) -> dict:
    return {
        "contract": contract,
        "quote_status": "quote available",
        "chart_status": "chart available",
        "quote_freshness_state": "fresh",
        "chart_freshness_state": "fresh",
        "live_runtime_readiness_state": "LIVE_RUNTIME_CONNECTED",
        "query_ready": query_ready,
        "query_gate_status": "ELIGIBLE" if query_ready else "BLOCKED",
        "query_not_ready_reasons": (
            [] if query_ready else ["trigger_state_not_query_ready:TOUCHED"]
        ),
        "primary_blocked_reasons": (
            [] if query_ready else ["trigger_state_not_query_ready:TOUCHED"]
        ),
        "missing_live_fields": [],
        "runtime_provider_status": "active",
        "runtime_cache_status": "runtime_cache_connected",
        "runtime_symbol": f"/{contract}M26",
    }


# -----------------------------------------------------------------------
# fail_closed_reason_text coherence tests
# -----------------------------------------------------------------------


def test_live_runtime_connected_with_snapshot_ready_has_no_fail_closed_reason() -> None:
    """LIVE_RUNTIME_CONNECTED + snapshot ready: not fail-closed."""
    surface = build_live_observation_cockpit_surface(
        readiness_summary=_readiness_summary(),
        operator_live_runtime=_runtime_payload(),
    )
    assert surface["runtime_connected"] is True
    assert surface["fail_closed_reason_text"] == ""
    assert surface["mode"] == LIVE_OBSERVATION_MODE_CONNECTED


def test_live_runtime_connected_with_snapshot_not_ready_renders_query_gate_blocked() -> None:
    """LIVE_RUNTIME_CONNECTED + snapshot not ready: query gate blocker headline,
    NEVER "Operator Runtime Cache Unavailable"."""
    surface = build_live_observation_cockpit_surface(
        readiness_summary=_readiness_summary(runtime_status="LIVE_RUNTIME_CONNECTED"),
        operator_live_runtime=_runtime_payload(cache_snapshot_ready=False),
    )
    assert surface["runtime_connected"] is True
    assert (
        surface["fail_closed_reason_text"] == FAIL_CLOSED_REASON_QUERY_GATE_BLOCKED
    )
    assert (
        surface["fail_closed_reason_text"]
        != FAIL_CLOSED_REASON_RUNTIME_CACHE_UNAVAILABLE
    )


def test_runtime_unavailable_renders_runtime_cache_unavailable_headline() -> None:
    """LIVE_RUNTIME_UNAVAILABLE: runtime-level headline, since runtime is not
    actually connected."""
    surface = build_live_observation_cockpit_surface(
        readiness_summary=_readiness_summary(
            runtime_status="LIVE_RUNTIME_UNAVAILABLE",
            quote_path_active=False,
        ),
        operator_live_runtime=_runtime_payload(
            cache_provider_status="blocked",
            cache_snapshot_ready=False,
        ),
    )
    assert surface["runtime_connected"] is False
    assert (
        surface["fail_closed_reason_text"]
        == FAIL_CLOSED_REASON_RUNTIME_CACHE_UNAVAILABLE
    )


def test_runtime_stale_renders_runtime_stale_headline() -> None:
    surface = build_live_observation_cockpit_surface(
        readiness_summary=_readiness_summary(
            runtime_status="LIVE_RUNTIME_STALE",
            quote_path_active=False,
        ),
        operator_live_runtime=_runtime_payload(
            cache_provider_status="stale",
            cache_snapshot_ready=False,
        ),
    )
    assert surface["runtime_connected"] is False
    assert surface["fail_closed_reason_text"] == FAIL_CLOSED_REASON_RUNTIME_STALE


# -----------------------------------------------------------------------
# Provider status quote-path correction tests
# -----------------------------------------------------------------------


def test_provider_status_corrected_when_quote_path_active() -> None:
    """Raw 'stale' becomes 'active' on the cockpit surface when the quote path
    is active. The per-row data is built from the corrected snapshot, so the
    header must agree."""
    surface = build_live_observation_cockpit_surface(
        readiness_summary=_readiness_summary(quote_path_active=True),
        operator_live_runtime=_runtime_payload(cache_provider_status="stale"),
    )
    assert surface["runtime_provider_status"] == "active"
    assert surface["runtime_provider_status_raw"] == "stale"


def test_provider_status_not_corrected_when_quote_path_inactive() -> None:
    """When quote path is NOT active, raw stale flows through — the header
    correctly shows stale because provider really is stale on the quote path."""
    surface = build_live_observation_cockpit_surface(
        readiness_summary=_readiness_summary(
            runtime_status="LIVE_RUNTIME_STALE",
            quote_path_active=False,
        ),
        operator_live_runtime=_runtime_payload(
            cache_provider_status="stale",
            cache_snapshot_ready=False,
        ),
    )
    assert surface["runtime_provider_status"] == "stale"
    assert surface["runtime_provider_status_raw"] == "stale"


def test_provider_status_active_passes_through_unchanged() -> None:
    surface = build_live_observation_cockpit_surface(
        readiness_summary=_readiness_summary(quote_path_active=True),
        operator_live_runtime=_runtime_payload(cache_provider_status="active"),
    )
    assert surface["runtime_provider_status"] == "active"


# -----------------------------------------------------------------------
# Renderer header coherence tests
# -----------------------------------------------------------------------


def test_renderer_runtime_connected_query_blocked_does_not_say_runtime_cache_unavailable() -> None:
    """Renderer: with LIVE_RUNTIME_CONNECTED, the header subtitle must not say
    'Operator Runtime Cache Unavailable'."""
    surface = build_live_observation_cockpit_surface(
        readiness_summary=_readiness_summary(),
        operator_live_runtime=_runtime_payload(cache_snapshot_ready=False),
    )
    html = render_primary_cockpit_html(surface)
    assert "Operator Runtime Cache Unavailable" not in html
    assert FAIL_CLOSED_REASON_QUERY_GATE_BLOCKED in html


def test_renderer_runtime_unavailable_says_runtime_cache_unavailable() -> None:
    surface = build_live_observation_cockpit_surface(
        readiness_summary=_readiness_summary(
            runtime_status="LIVE_RUNTIME_UNAVAILABLE",
            quote_path_active=False,
        ),
        operator_live_runtime=_runtime_payload(
            cache_provider_status="blocked",
            cache_snapshot_ready=False,
        ),
    )
    html = render_primary_cockpit_html(surface)
    assert FAIL_CLOSED_REASON_RUNTIME_CACHE_UNAVAILABLE in html


def test_renderer_runtime_connected_fully_ready_renders_live_badge() -> None:
    surface = build_live_observation_cockpit_surface(
        readiness_summary=_readiness_summary(),
        operator_live_runtime=_runtime_payload(),
    )
    html = render_primary_cockpit_html(surface)
    assert "LIVE FAIL-CLOSED" not in html
    assert "Operator Runtime Cache Unavailable" not in html


def test_renderer_shows_corrected_provider_status_when_quote_path_active() -> None:
    """Renderer header must not say 'Provider: stale' when quote path is active.
    The raw cache provider_status is 'stale' but the displayed value must be
    'active' to agree with the per-row quote_status."""
    surface = build_live_observation_cockpit_surface(
        readiness_summary=_readiness_summary(quote_path_active=True),
        operator_live_runtime=_runtime_payload(
            cache_provider_status="stale",
            cache_snapshot_ready=False,
        ),
    )
    html = render_primary_cockpit_html(surface)
    assert "Provider: stale" not in html
    assert "Provider: active" in html


# -----------------------------------------------------------------------
# Manual query / fail-closed semantics preserved
# -----------------------------------------------------------------------


def test_runtime_connected_query_blocked_rows_remain_fail_closed() -> None:
    """Even when runtime is connected and provider corrected to active, rows
    where query_ready=False must remain query-disabled. Display cannot create
    QUERY_READY."""
    surface = build_live_observation_cockpit_surface(
        readiness_summary=_readiness_summary(),
        operator_live_runtime=_runtime_payload(cache_snapshot_ready=False),
    )
    for row in surface["rows"]:
        assert row["query_enabled"] is False, (
            f"{row['contract']}: query must remain disabled without QUERY_READY"
        )
        assert row["query_action_state"] == "DISABLED"


def test_default_launch_remains_non_live() -> None:
    surface = build_live_observation_cockpit_surface(
        readiness_summary=_readiness_summary(),
        operator_live_runtime=_runtime_payload(),
    )
    assert surface["default_launch_live"] is False
    assert surface["fixture_fallback_after_live_failure"] is False


def test_final_target_universe_preserved() -> None:
    surface = build_live_observation_cockpit_surface(
        readiness_summary=_readiness_summary(),
        operator_live_runtime=_runtime_payload(),
    )
    contracts = [row["contract"] for row in surface["rows"]]
    assert contracts == ["ES", "NQ", "CL", "6E", "MGC"]
    assert "ZN" not in contracts
    assert "GC" not in contracts


def test_mgc_label_remains_micro_gold() -> None:
    surface = build_live_observation_cockpit_surface(
        readiness_summary=_readiness_summary(),
        operator_live_runtime=_runtime_payload(),
    )
    mgc = next(row for row in surface["rows"] if row["contract"] == "MGC")
    assert mgc["profile_label"] == "Micro Gold"


def test_raw_values_never_included_in_surface() -> None:
    surface = build_live_observation_cockpit_surface(
        readiness_summary=_readiness_summary(),
        operator_live_runtime=_runtime_payload(cache_snapshot_ready=False),
    )
    assert surface["raw_quote_values_included"] is False
    assert surface["raw_bar_values_included"] is False
    assert surface["raw_streamer_payloads_included"] is False
