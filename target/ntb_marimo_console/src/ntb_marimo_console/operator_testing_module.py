"""Operator Testing Module V0 surface.

The V0 surface is the top operator-facing status board: a 10-second read of
whether the live Marimo cockpit is usable for operator testing. It distills
the readiness summary, the primary cockpit surface, and the operator live
runtime metadata into a single view-model with:

- a coherent title (``NTB Live Observation Testing Module``),
- a binary status (``READY_FOR_OPERATOR_TESTING`` or ``NOT_READY_FOR_OPERATOR_TESTING``),
- runtime, provider, and manual-query state strings,
- exactly one top-level blocker,
- exactly one next safe action,
- five per-contract rows (ES, NQ, CL, 6E, MGC) with provider, quote, chart,
  trigger, query gate, blocker, and next safe action.

This module is a pure view-model. It performs no I/O, never reads fixture
data, and never creates ``QUERY_READY``. Each row reflects the upstream
preserved-engine pipeline gate (and per-row ``query_ready`` boolean from
the readiness summary) — no QUERY_READY can be invented here.

Engine source profile (e.g. ``fixture_es_demo``) is exposed only as
secondary/debug metadata, never as the primary live-screen identity.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final

from .contract_universe import final_target_contracts


OPERATOR_TESTING_MODULE_SCHEMA: Final[str] = "operator_testing_module_v0"
OPERATOR_TESTING_MODULE_TITLE: Final[str] = "NTB Live Observation Testing Module"

OPERATOR_TESTING_STATUS_READY: Final[str] = "READY_FOR_OPERATOR_TESTING"
OPERATOR_TESTING_STATUS_NOT_READY: Final[str] = "NOT_READY_FOR_OPERATOR_TESTING"


_CONTRACT_LABELS: Final[dict[str, str]] = {
    "ES": "E-mini S&P 500",
    "NQ": "E-mini Nasdaq-100",
    "CL": "Crude Oil",
    "6E": "Euro FX",
    "MGC": "Micro Gold",
}


_TRIGGER_DISPLAY: Final[dict[str, str]] = {
    "trigger_true": "trigger true",
    "trigger_unavailable": "trigger unavailable",
    "query_not_ready_no_declared_trigger_true": "trigger not query-ready",
}


def build_operator_testing_module_surface(
    *,
    readiness_summary: Mapping[str, object] | None,
    primary_cockpit_surface: Mapping[str, object] | None,
    operator_live_runtime: Mapping[str, object] | None,
    engine_source_profile_id: str | None = None,
) -> dict[str, object]:
    """Build the V0 operator-facing status board.

    Always returns a usable surface with all expected fields, including in
    fixture (non-live) mode — in that case the surface remains
    ``NOT_READY_FOR_OPERATOR_TESTING`` with a top blocker explaining how to
    enable the live runtime, so the operator screen does not lie about being
    ready when default launch is non-live.
    """

    summary = readiness_summary if isinstance(readiness_summary, Mapping) else {}
    cockpit = primary_cockpit_surface if isinstance(primary_cockpit_surface, Mapping) else {}
    runtime = operator_live_runtime if isinstance(operator_live_runtime, Mapping) else {}

    mode = str(runtime.get("mode") or "SAFE_NON_LIVE")
    live_mode = mode == "OPERATOR_LIVE_RUNTIME"
    runtime_status = str(
        summary.get("live_runtime_readiness_status")
        or cockpit.get("live_runtime_readiness_status")
        or ("LIVE_RUNTIME_NOT_REQUESTED" if not live_mode else "LIVE_RUNTIME_UNAVAILABLE")
    )
    runtime_connected = runtime_status == "LIVE_RUNTIME_CONNECTED"
    provider_state = _provider_state(summary=summary, cockpit=cockpit, runtime=runtime)
    quote_path_active = bool(summary.get("runtime_quote_path_active"))

    readiness_rows = _readiness_rows_by_contract(summary)
    cockpit_rows = _cockpit_rows_by_contract(cockpit)

    rows = [
        _build_row(
            contract=contract,
            readiness_row=readiness_rows.get(contract),
            cockpit_row=cockpit_rows.get(contract),
            mode=mode,
            runtime_status=runtime_status,
        )
        for contract in final_target_contracts()
    ]

    manual_query_enabled_count = sum(1 for row in rows if row["query_gate"] == "ELIGIBLE")
    manual_query_state = "ENABLED" if manual_query_enabled_count == len(rows) and rows else "DISABLED"

    top_blocker = _top_blocker(
        mode=mode,
        runtime_status=runtime_status,
        runtime_connected=runtime_connected,
        provider_state=provider_state,
        rows=rows,
        cockpit=cockpit,
    )

    operator_testing_status = _operator_testing_status(
        mode=mode,
        runtime_connected=runtime_connected,
        provider_state=provider_state,
        rows=rows,
    )

    next_safe_action = _next_safe_action(
        mode=mode,
        runtime_status=runtime_status,
        runtime_connected=runtime_connected,
        provider_state=provider_state,
        operator_testing_status=operator_testing_status,
        rows=rows,
    )

    runtime_state_text = _runtime_state_text(
        mode=mode, runtime_status=runtime_status, runtime_connected=runtime_connected
    )
    provider_state_text = _provider_state_text(
        provider_state=provider_state, quote_path_active=quote_path_active
    )
    manual_query_state_text = _manual_query_state_text(
        manual_query_state=manual_query_state,
        enabled_count=manual_query_enabled_count,
        total=len(rows),
    )

    return {
        "schema": OPERATOR_TESTING_MODULE_SCHEMA,
        "title": OPERATOR_TESTING_MODULE_TITLE,
        "operator_testing_status": operator_testing_status,
        "mode": mode,
        "live_mode": live_mode,
        "runtime_state": runtime_status,
        "runtime_state_text": runtime_state_text,
        "runtime_connected": runtime_connected,
        "provider_state": provider_state,
        "provider_state_text": provider_state_text,
        "manual_query_state": manual_query_state,
        "manual_query_state_text": manual_query_state_text,
        "manual_query_enabled_count": manual_query_enabled_count,
        "top_blocker": top_blocker,
        "next_safe_action": next_safe_action,
        "engine_source_profile_id": _safe_str(engine_source_profile_id) or "",
        "supported_contracts": list(final_target_contracts()),
        "excluded_contracts": ["ZN", "GC"],
        "rows": rows,
        "decision_authority": "preserved_engine_only",
        "manual_query_only": True,
        "manual_execution_only": True,
        "default_launch_live": False,
        "fixture_fallback_after_live_failure": False,
        "creates_query_ready": False,
        "raw_quote_values_included": False,
        "raw_bar_values_included": False,
        "raw_streamer_payloads_included": False,
    }


def _readiness_rows_by_contract(summary: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    rows = summary.get("rows")
    result: dict[str, Mapping[str, object]] = {}
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, Mapping):
                contract = str(row.get("contract") or "").strip().upper()
                if contract:
                    result[contract] = row
    return result


def _cockpit_rows_by_contract(cockpit: Mapping[str, object]) -> dict[str, Mapping[str, object]]:
    rows = cockpit.get("rows")
    result: dict[str, Mapping[str, object]] = {}
    if isinstance(rows, list):
        for row in rows:
            if isinstance(row, Mapping):
                contract = str(row.get("contract") or "").strip().upper()
                if contract:
                    result[contract] = row
    return result


def _provider_state(
    *,
    summary: Mapping[str, object],
    cockpit: Mapping[str, object],
    runtime: Mapping[str, object],
) -> str:
    # Prefer the cockpit's quote-path-corrected provider_status (see
    # ``primary_cockpit.build_live_observation_cockpit_surface``). Fall back to
    # the readiness summary's runtime_cache_provider_status, then to the raw
    # runtime metadata.
    for source, key in (
        (cockpit, "runtime_provider_status"),
        (summary, "runtime_cache_provider_status"),
        (runtime, "cache_provider_status"),
    ):
        value = source.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "unavailable"


def _build_row(
    *,
    contract: str,
    readiness_row: Mapping[str, object] | None,
    cockpit_row: Mapping[str, object] | None,
    mode: str,
    runtime_status: str,
) -> dict[str, object]:
    rr = readiness_row if isinstance(readiness_row, Mapping) else {}
    cr = cockpit_row if isinstance(cockpit_row, Mapping) else {}

    profile_label = _CONTRACT_LABELS.get(contract, contract)
    provider = str(rr.get("runtime_provider_status") or "unavailable")
    quote = str(rr.get("quote_status") or "quote missing")
    chart = str(rr.get("chart_status") or "chart missing")
    trigger_raw = str(rr.get("trigger_state_summary") or "trigger_unavailable")
    trigger = _TRIGGER_DISPLAY.get(trigger_raw, trigger_raw.replace("_", " "))
    query_gate = str(rr.get("query_gate_status") or "BLOCKED")
    query_ready = rr.get("query_ready") is True

    runtime_state = str(rr.get("live_runtime_readiness_state") or "LIVE_RUNTIME_UNAVAILABLE")
    runtime_connected = runtime_state == "LIVE_RUNTIME_CONNECTED"

    blocker, next_safe_action = _row_blocker_and_action(
        mode=mode,
        runtime_status=runtime_status,
        runtime_connected=runtime_connected,
        provider=provider,
        quote=quote,
        chart=chart,
        trigger=trigger,
        query_ready=query_ready,
    )

    return {
        "contract": contract,
        "profile_label": profile_label,
        "provider": provider,
        "quote": quote,
        "chart": chart,
        "trigger": trigger,
        "trigger_raw": trigger_raw,
        "query_gate": query_gate,
        "query_ready": query_ready,
        "blocker": blocker,
        "next_safe_action": next_safe_action,
        "runtime_state": runtime_state,
        # Operator-visible row safety attestation; display can never invent
        # this. ``query_ready`` is sourced from the readiness summary row,
        # which derives it from the preserved-engine pipeline gate.
        "query_ready_provenance": (
            "real_trigger_state_result_and_pipeline_gate"
            if query_ready
            else "unavailable_not_inferred_from_display"
        ),
    }


def _row_blocker_and_action(
    *,
    mode: str,
    runtime_status: str,
    runtime_connected: bool,
    provider: str,
    quote: str,
    chart: str,
    trigger: str,
    query_ready: bool,
) -> tuple[str, str]:
    if mode != "OPERATOR_LIVE_RUNTIME":
        return (
            "Live runtime not requested.",
            "Relaunch with OPERATOR_LIVE_RUNTIME=1.",
        )
    if not runtime_connected:
        return (
            f"Live runtime not connected ({runtime_status}).",
            "Confirm OPERATOR_LIVE_RUNTIME=1 and Schwab credentials; relaunch.",
        )
    if provider in {"stale", "blocked", "disconnected", "shutdown", "error"}:
        return (
            f"Provider {provider}.",
            "Wait for live provider to recover or relaunch the live runtime.",
        )
    if quote != "quote available":
        return (
            f"Quote not available ({quote}).",
            "Wait for live quote data on this contract.",
        )
    if chart != "chart available":
        return (
            f"Chart not available ({chart}).",
            "Wait for live chart data on this contract.",
        )
    if query_ready:
        return (
            "Ready for live observation.",
            "Operator may manually query under preserved-engine gate.",
        )
    return (
        "Trigger state not query-ready (preserved-engine gate).",
        "Observe; manual query stays disabled until preserved-engine QUERY_READY.",
    )


def _top_blocker(
    *,
    mode: str,
    runtime_status: str,
    runtime_connected: bool,
    provider_state: str,
    rows: Sequence[Mapping[str, object]],
    cockpit: Mapping[str, object],
) -> str:
    if mode != "OPERATOR_LIVE_RUNTIME":
        return "Live runtime not requested. Default launch is non-live."
    if not runtime_connected:
        fail_closed = cockpit.get("fail_closed_reason_text")
        if isinstance(fail_closed, str) and fail_closed.strip():
            return f"Live runtime not connected: {fail_closed.strip()}."
        return f"Live runtime not connected ({runtime_status})."
    if provider_state in {"stale", "blocked", "disconnected", "shutdown", "error"}:
        return f"Provider {provider_state}."
    quote_missing = [str(row["contract"]) for row in rows if row.get("quote") != "quote available"]
    if quote_missing:
        return f"Quote not available for {', '.join(quote_missing)}."
    chart_missing = [str(row["contract"]) for row in rows if row.get("chart") != "chart available"]
    if chart_missing:
        return f"Chart not available for {', '.join(chart_missing)}."
    if not any(row.get("query_ready") is True for row in rows):
        return (
            "Manual query blocked: preserved-engine trigger state not query-ready "
            "for any contract."
        )
    return ""


def _operator_testing_status(
    *,
    mode: str,
    runtime_connected: bool,
    provider_state: str,
    rows: Sequence[Mapping[str, object]],
) -> str:
    if mode != "OPERATOR_LIVE_RUNTIME":
        return OPERATOR_TESTING_STATUS_NOT_READY
    if not runtime_connected:
        return OPERATOR_TESTING_STATUS_NOT_READY
    if provider_state not in {"active", "connected"}:
        return OPERATOR_TESTING_STATUS_NOT_READY
    if not rows:
        return OPERATOR_TESTING_STATUS_NOT_READY
    for row in rows:
        if row.get("quote") != "quote available":
            return OPERATOR_TESTING_STATUS_NOT_READY
        if row.get("chart") != "chart available":
            return OPERATOR_TESTING_STATUS_NOT_READY
    # All five contracts have provider active + quote available + chart
    # available, with the runtime cache connected. The cockpit is ready for
    # operator testing. Manual query may still remain disabled because
    # preserved-engine QUERY_READY provenance is the gate — that is by design
    # and is part of the V0 product surface, not a NOT_READY condition.
    return OPERATOR_TESTING_STATUS_READY


def _next_safe_action(
    *,
    mode: str,
    runtime_status: str,
    runtime_connected: bool,
    provider_state: str,
    operator_testing_status: str,
    rows: Sequence[Mapping[str, object]],
) -> str:
    if mode != "OPERATOR_LIVE_RUNTIME":
        return (
            "Relaunch with NTB_OPERATOR_RUNTIME_MODE=OPERATOR_LIVE_RUNTIME to "
            "enable the live runtime."
        )
    if not runtime_connected:
        return (
            "Confirm OPERATOR_LIVE_RUNTIME=1 and Schwab live credentials, then "
            "relaunch the operator console."
        )
    if provider_state in {"stale", "blocked", "disconnected", "shutdown", "error"}:
        return "Wait for the live provider to recover or relaunch the live runtime."
    quote_missing = [row for row in rows if row.get("quote") != "quote available"]
    if quote_missing:
        return "Wait for live quote data on the contracts marked not available."
    chart_missing = [row for row in rows if row.get("chart") != "chart available"]
    if chart_missing:
        return "Wait for live chart data on the contracts marked not available."
    if operator_testing_status == OPERATOR_TESTING_STATUS_READY:
        return (
            "Begin live observation. Manual query stays disabled until "
            "preserved-engine QUERY_READY provenance."
        )
    return (
        "Observe live data. Manual query stays disabled until preserved-engine "
        "QUERY_READY provenance."
    )


def _runtime_state_text(*, mode: str, runtime_status: str, runtime_connected: bool) -> str:
    if mode != "OPERATOR_LIVE_RUNTIME":
        return "Live runtime not requested (default non-live launch)."
    if runtime_connected:
        return "Live runtime connected."
    return f"Live runtime not connected: {runtime_status}."


def _provider_state_text(*, provider_state: str, quote_path_active: bool) -> str:
    if provider_state in {"active", "connected"}:
        return "Provider active."
    if provider_state == "stale" and quote_path_active:
        # Should not normally happen because the cockpit quote-path correction
        # rewrites "stale" to "active" when quote path is active. Keep the
        # honest label if it ever reaches here.
        return "Provider stale (quote path active)."
    return f"Provider {provider_state}."


def _manual_query_state_text(*, manual_query_state: str, enabled_count: int, total: int) -> str:
    if manual_query_state == "ENABLED" and enabled_count == total and total > 0:
        return (
            f"Manual query enabled for all {total} contracts under the "
            "preserved-engine gate."
        )
    if enabled_count > 0:
        return (
            f"Manual query enabled for {enabled_count} of {total} contracts; "
            "remaining contracts disabled until preserved-engine QUERY_READY."
        )
    return (
        "Manual query disabled. Manual query stays disabled until preserved-engine "
        "QUERY_READY provenance."
    )


def _safe_str(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text
