"""Primary operator cockpit surface resolution and the live-observation cockpit.

The Marimo console renders exactly one *primary* cockpit landing surface. In the
default credential-free path it is the fixture cockpit overview. Under the
explicit ``OPERATOR_LIVE_RUNTIME`` opt-in it is the live-observation cockpit,
built read-only from the operator runtime cache snapshot — never from fixture
data.

This module is the single source of truth for *which* surface key is primary
(``primary_cockpit_surface_key``) and for building the live-observation cockpit
surface (``build_live_observation_cockpit_surface``). Keeping the resolution in
one leaf module lets the launch-metadata builder, the session lifecycle, the
renderer, and the Marimo app agree without each hard-coding a surface key.

Import-time inert: this module performs no env reads, file opens, or network
calls. ``build_live_observation_cockpit_surface`` is a pure view-model transform
over plain dicts — it reflects an already-computed pipeline gate and never
creates ``QUERY_READY`` itself.
"""

from __future__ import annotations

from collections.abc import Mapping

from .contract_universe import final_target_contracts

FIXTURE_COCKPIT_SURFACE_KEY = "fixture_cockpit_overview"
LIVE_OBSERVATION_COCKPIT_SURFACE_KEY = "live_observation_cockpit_overview"
PRIMARY_COCKPIT_SURFACE_KEY_FIELD = "primary_cockpit_surface_key"

FIXTURE_COCKPIT_IDENTITY = "fixture_demo"
LIVE_OBSERVATION_COCKPIT_IDENTITY = "live_observation"

LIVE_OBSERVATION_COCKPIT_TITLE = "FIVE-CONTRACT LIVE-OBSERVATION COCKPIT"
LIVE_OBSERVATION_MODE_CONNECTED = "live_observation_runtime_cache"
LIVE_OBSERVATION_MODE_FAIL_CLOSED = "live_observation_fail_closed"

LIVE_OBSERVATION_CONSOLE_MODE_LABEL = "Live-Observation"
LIVE_OBSERVATION_CONSOLE_RUNNING_AS = "Live-Observation"

# Provenance strings mirror the fixture cockpit contract: a row may only claim
# the real-gate provenance when the upstream pipeline gate already marked it
# query-ready. Display/view-model code must never invent QUERY_READY.
_REAL_GATE_PROVENANCE = "real_trigger_state_result_and_pipeline_gate"
_UNAVAILABLE_PROVENANCE = "unavailable_not_inferred_from_display_or_raw_enabled_mapping"

_CONTRACT_LABELS = {
    "ES": "E-mini S&P 500",
    "NQ": "E-mini Nasdaq-100",
    "CL": "Crude Oil",
    "6E": "Euro FX",
    "MGC": "Micro Gold",
}


def primary_cockpit_surface_key(shell: Mapping[str, object] | None) -> str:
    """Return the surface key for the primary cockpit landing surface.

    Falls back to the fixture cockpit key when the shell does not declare a
    primary key, so non-live callers and legacy shells behave unchanged.
    """

    if isinstance(shell, Mapping):
        declared = shell.get(PRIMARY_COCKPIT_SURFACE_KEY_FIELD)
        if isinstance(declared, str) and declared.strip():
            return declared.strip()
    return FIXTURE_COCKPIT_SURFACE_KEY


def primary_cockpit_surface(shell: Mapping[str, object] | None) -> Mapping[str, object]:
    """Return the primary cockpit surface mapping, or an empty mapping."""

    if not isinstance(shell, Mapping):
        return {}
    surfaces = shell.get("surfaces")
    if not isinstance(surfaces, Mapping):
        return {}
    surface = surfaces.get(primary_cockpit_surface_key(shell))
    return surface if isinstance(surface, Mapping) else {}


def primary_cockpit_surface_mutable(shell: Mapping[str, object] | None) -> dict | None:
    """Return the mutable primary cockpit surface dict, or ``None``.

    Used by the launch-metadata and session-lifecycle attach helpers that write
    operator action status, notes, timeline, and event-replay back onto the
    primary cockpit surface regardless of whether it is fixture or live.
    """

    if not isinstance(shell, Mapping):
        return None
    surfaces = shell.get("surfaces")
    if not isinstance(surfaces, dict):
        return None
    surface = surfaces.get(primary_cockpit_surface_key(shell))
    return surface if isinstance(surface, dict) else None


def is_live_observation_cockpit(shell: Mapping[str, object] | None) -> bool:
    """True when the shell's primary cockpit is the live-observation surface."""

    return primary_cockpit_surface_key(shell) == LIVE_OBSERVATION_COCKPIT_SURFACE_KEY


def _contract_label(contract: str) -> str:
    return _CONTRACT_LABELS.get(contract, contract)


def _reasons_for_row(row: Mapping[str, object]) -> tuple[str, ...]:
    for field in (
        "query_not_ready_reasons",
        "primary_blocked_reasons",
        "runtime_cache_blocked_reasons",
        "missing_live_fields",
    ):
        value = row.get(field)
        if isinstance(value, (list, tuple)) and value:
            return tuple(str(item) for item in value if str(item).strip())
    return ()


def _humanize_reason(reason: str) -> str:
    return reason.replace("_", " ").replace(":", ": ").strip()


def _live_observation_row(
    contract: str,
    readiness_row: Mapping[str, object] | None,
) -> dict[str, object]:
    row = readiness_row if isinstance(readiness_row, Mapping) else {}
    # query_ready is sourced strictly from the upstream readiness summary, which
    # derives it from the real preflight + pipeline gate against the operator
    # runtime cache. This view-model only reflects it.
    query_ready = row.get("query_ready") is True
    gate_state = str(row.get("query_gate_status") or "DISABLED")
    reasons = _reasons_for_row(row)
    runtime_state = str(row.get("live_runtime_readiness_state") or "LIVE_RUNTIME_UNAVAILABLE")

    if query_ready:
        query_reason = (
            f"Manual query available for {contract}: live runtime cache and the "
            "preserved pipeline gate are satisfied."
        )
        query_disabled_reason = None
        query_action_text = (
            "Manual query available: submit preserved pipeline query manually."
        )
    else:
        if reasons:
            query_reason = (
                f"Live runtime cache is not query-ready for {contract}: "
                + _humanize_reason(reasons[0])
            )
        else:
            query_reason = (
                f"Live runtime cache is not query-ready for {contract} "
                f"(runtime readiness: {runtime_state})."
            )
        query_disabled_reason = f"Manual query blocked: {query_reason}"
        query_action_text = "Manual query blocked."

    return {
        "contract": contract,
        "profile_label": _contract_label(contract),
        "support_state": "final_target",
        "runtime_state": "live_observation",
        "quote_status": str(row.get("quote_status") or "quote missing"),
        "chart_status": str(row.get("chart_status") or "chart missing"),
        "quote_freshness_state": str(row.get("quote_freshness_state") or "missing"),
        "chart_freshness_state": str(row.get("chart_freshness_state") or "missing"),
        "blocking_reasons": list(reasons),
        "query_gate_state": gate_state,
        "query_gate_contract": contract,
        "query_enabled": query_ready,
        "query_action_state": "ENABLED" if query_ready else "DISABLED",
        "query_action_text": query_action_text,
        "query_reason": query_reason,
        "query_disabled_reason": query_disabled_reason,
        "query_ready_provenance": (
            _REAL_GATE_PROVENANCE if query_ready else _UNAVAILABLE_PROVENANCE
        ),
        "query_action_provenance": (
            _REAL_GATE_PROVENANCE if query_ready else _UNAVAILABLE_PROVENANCE
        ),
        "query_action_source": "operator_live_runtime_cache_and_existing_pipeline_gate",
        "live_runtime_readiness_state": runtime_state,
        "runtime_cache_status": str(row.get("runtime_cache_status") or "runtime_cache_unavailable"),
        "runtime_provider_status": row.get("runtime_provider_status"),
        "runtime_symbol": row.get("runtime_symbol"),
        "status_text": (
            f"{contract} live runtime readiness: {runtime_state}; "
            f"quote {row.get('quote_status') or 'quote missing'}, "
            f"chart {row.get('chart_status') or 'chart missing'}."
        ),
    }


def build_live_observation_cockpit_surface(
    *,
    readiness_summary: Mapping[str, object] | None,
    operator_live_runtime: Mapping[str, object] | None,
) -> dict[str, object]:
    """Build the live-observation primary cockpit surface from the runtime cache.

    The surface is a read-only view-model derived from the already-built
    five-contract readiness summary (per-contract live runtime cache state) and
    the operator live runtime metadata. It never reads fixture data and never
    creates ``QUERY_READY``: each row reflects the upstream pipeline gate only.

    When the live runtime is unavailable/error/stale the readiness summary rows
    are themselves fail-closed, so every cockpit row is fail-closed too — there
    is no fixture fallback.
    """

    from .cockpit_manual_query import no_cockpit_manual_query_result

    summary = readiness_summary if isinstance(readiness_summary, Mapping) else {}
    runtime = operator_live_runtime if isinstance(operator_live_runtime, Mapping) else {}

    readiness_rows: dict[str, Mapping[str, object]] = {}
    raw_rows = summary.get("rows")
    if isinstance(raw_rows, list):
        for entry in raw_rows:
            if isinstance(entry, Mapping):
                contract = entry.get("contract")
                if isinstance(contract, str):
                    readiness_rows[contract] = entry

    runtime_status = str(
        summary.get("live_runtime_readiness_status") or "LIVE_RUNTIME_UNAVAILABLE"
    )
    provider_status = runtime.get("cache_provider_status")
    snapshot_ready = runtime.get("cache_snapshot_ready") is True
    generated_at = runtime.get("cache_generated_at")
    global_blockers = runtime.get("blocking_reasons")
    blocking_reasons = (
        [str(item) for item in global_blockers]
        if isinstance(global_blockers, (list, tuple))
        else []
    )

    live_connected = runtime_status == "LIVE_RUNTIME_CONNECTED" and snapshot_ready
    mode = (
        LIVE_OBSERVATION_MODE_CONNECTED
        if live_connected
        else LIVE_OBSERVATION_MODE_FAIL_CLOSED
    )

    # Iterate the canonical five contracts only — ZN/GC are structurally
    # excluded and can never appear in the live-observation cockpit.
    rows = [
        _live_observation_row(contract, readiness_rows.get(contract))
        for contract in final_target_contracts()
    ]

    return {
        "surface": LIVE_OBSERVATION_COCKPIT_SURFACE_KEY,
        "cockpit_identity": LIVE_OBSERVATION_COCKPIT_IDENTITY,
        "cockpit_title": LIVE_OBSERVATION_COCKPIT_TITLE,
        "mode": mode,
        "decision_authority": "preserved_engine_only",
        "live_credentials_required": True,
        "network_required": True,
        "default_launch_live": False,
        "fixture_fallback_after_live_failure": False,
        "supported_contracts": list(final_target_contracts()),
        "live_runtime_readiness_status": runtime_status,
        "runtime_provider_status": provider_status,
        "runtime_snapshot_ready": snapshot_ready,
        "runtime_cache_generated_at": generated_at,
        "generated_at": generated_at,
        "live_runtime_blocking_reasons": blocking_reasons,
        "rows": rows,
        "last_query_result": no_cockpit_manual_query_result(),
        "raw_quote_values_included": False,
        "raw_bar_values_included": False,
        "raw_streamer_payloads_included": False,
    }
