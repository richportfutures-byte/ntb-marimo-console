from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

from .contract_universe import final_target_contracts
from .cockpit_manual_query import (
    no_cockpit_manual_query_result,
    no_cockpit_operator_action_status,
)
from .live_observables import build_live_observable_snapshot_v2
from .market_data import ChartFuturesBarBuilder
from .market_data.chart_bars import ContractBarState
from .market_data.stream_cache import StreamCacheRecord, StreamCacheSnapshot
from .operator_workspace import OperatorWorkspaceRequest, build_r14_cockpit_view_model
from .pipeline_query_gate import PipelineQueryGateRequest, evaluate_pipeline_query_gate
from .trigger_state import TriggerState, TriggerStateResult

_NOW = datetime(2026, 5, 6, 14, 0, 0, tzinfo=timezone.utc)
_SYMBOL_BY_CONTRACT: dict[str, str] = {
    "ES": "/ESM26",
    "NQ": "/NQM26",
    "CL": "/CLM26",
    "6E": "/6EM26",
    "MGC": "/MGCM26",
}


def build_fixture_operator_session_summary() -> dict[str, object]:
    """Build a five-contract fixture operator cockpit session summary dict.

    Credential-free and network-free.  All quote/bar values are sanitized out
    of the returned dict; only status labels and gate state are present.
    """
    live_snapshot = _fixture_live_snapshot()
    rows: list[dict[str, object]] = []
    for contract in final_target_contracts():
        trigger_state = _trigger_state(contract)
        gate = evaluate_pipeline_query_gate(
            PipelineQueryGateRequest(
                contract=contract,
                profile_id=f"preserved_{contract.lower()}_phase1",
                profile_exists=True,
                profile_preflight_passed=True,
                watchman_validator_status="READY",
                live_snapshot=live_snapshot,
                live_snapshot_fresh=True,
                trigger_state=trigger_state,
                provider_status="fixture",
                stream_status="fixture",
                session_valid=True,
                event_lockout_active=False,
                fixture_mode_accepted=True,
                trigger_state_from_real_producer=True,
                evaluated_at=_NOW.isoformat(),
            )
        )
        cockpit = build_r14_cockpit_view_model(
            OperatorWorkspaceRequest(
                contract=contract,
                profile_id=f"preserved_{contract.lower()}_phase1",
                watchman_validator="READY",
                trigger_state=trigger_state,
                pipeline_query_gate=gate,
                premarket_brief=_premarket_brief(contract),
                live_observable=live_snapshot,
                provider_status="fixture",
                stream_status="fixture",
                evaluated_at=_NOW.isoformat(),
                last_pipeline_result=None,
            )
        ).to_dict()
        rows.append(_session_row(contract, cockpit))
    return {
        "schema": "fixture_operator_session_dry_run_v1",
        "mode": "fixture_dry_run_non_live",
        "live_credentials_required": False,
        "network_required": False,
        "default_launch_live": False,
        "manual_query_only": True,
        "manual_execution_only": True,
        "decision_authority": "preserved_engine_only",
        "generated_at": _NOW.isoformat(),
        "supported_contracts": list(final_target_contracts()),
        "rows": rows,
        "last_query_result": no_cockpit_manual_query_result(),
        "operator_action_status": no_cockpit_operator_action_status(),
        "sanitization": {
            "raw_quote_values_printed": False,
            "raw_bar_values_printed": False,
            "raw_streamer_payloads_printed": False,
            "live_credentials_printed": False,
        },
    }


def render_fixture_operator_session_text(summary: dict[str, object]) -> str:
    """Render a human-readable sanitized text summary of a fixture operator session."""
    rows = summary.get("rows")
    lines = [
        "Fixture Operator Session Dry Run",
        f"mode={summary.get('mode')}",
        "live_credentials_required=no",
        "network_required=no",
        "default_launch_live=no",
        "manual_query_only=yes",
        "manual_execution_only=yes",
        "decision_authority=preserved_engine_only",
        "supported_contracts=ES,NQ,CL,6E,MGC",
        "",
        "contract | label | mode | support | quote | chart | gate | action_state | action | reason",
    ]
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue
            lines.append(
                " | ".join(
                    (
                        str(row.get("contract", "")),
                        str(row.get("profile_label", "")),
                        str(row.get("runtime_state", "")),
                        str(row.get("support_state", "")),
                        str(row.get("quote_status", "")),
                        str(row.get("chart_status", "")),
                        str(row.get("query_gate_state", "")),
                        str(row.get("query_action_state", "")),
                        str(row.get("query_action_text", "")),
                        str(row.get("query_reason", "")),
                    )
                )
            )
    lines.extend(
        (
            "",
            "sanitized=yes",
            "raw_quote_values_printed=no",
            "raw_bar_values_printed=no",
            "raw_streamer_payloads_printed=no",
            "trade_suggestions=no",
        )
    )
    return "\n".join(lines)


def build_fixture_cockpit_shell_surface() -> dict[str, object]:
    """Build the fixture cockpit overview surface dict for injection into the Marimo shell.

    Returns the session summary enriched with a ``surface`` discriminator key.
    The surface is credential-free, network-free, and safe to attach on every
    launch regardless of live-provider status.
    """
    summary = build_fixture_operator_session_summary()
    surface: dict[str, object] = {"surface": "fixture_cockpit_overview"}
    surface.update(summary)
    return surface


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _session_row(contract: str, cockpit: dict[str, object]) -> dict[str, object]:
    status = _selected_contract_status(contract, cockpit)
    query = cockpit.get("query_readiness")
    query_map = query if isinstance(query, dict) else {}
    return {
        "contract": contract,
        "profile_label": status.get("profile_label"),
        "support_state": status.get("support_state"),
        "quote_status": status.get("quote_status"),
        "chart_status": status.get("chart_status"),
        "quote_freshness_state": status.get("quote_freshness_state"),
        "chart_freshness_state": status.get("chart_freshness_state"),
        "blocking_reasons": status.get("blocking_reasons", []),
        "query_gate_state": status.get("query_gate_state")
        or query_map.get("pipeline_gate_state", "DISABLED"),
        "query_enabled": query_map.get("manual_query_allowed") is True,
        "query_action_state": status.get("query_action_state", "DISABLED"),
        "query_action_text": status.get("query_action_text", "Manual query blocked."),
        "query_disabled_reason": status.get("query_disabled_reason"),
        "query_action_provenance": status.get("query_action_provenance")
        or query_map.get("query_ready_provenance"),
        "query_action_source": status.get("query_action_source"),
        "query_gate_contract": status.get("query_gate_contract"),
        "query_reason": query_map.get("query_enabled_reason")
        or status.get("query_disabled_reason")
        or query_map.get("query_disabled_reason"),
        "query_ready_provenance": query_map.get("query_ready_provenance"),
        "runtime_state": status.get("runtime_state"),
        "status_text": status.get("status_text"),
    }


def _selected_contract_status(
    contract: str, cockpit: dict[str, object]
) -> dict[str, object]:
    statuses = cockpit.get("contract_statuses")
    if isinstance(statuses, list):
        for status in statuses:
            if isinstance(status, dict) and status.get("contract") == contract:
                return status
    return {
        "contract": contract,
        "profile_label": contract,
        "support_state": "unavailable",
        "quote_status": "quote missing",
        "chart_status": "chart missing",
        "quote_freshness_state": "missing",
        "chart_freshness_state": "missing",
        "blocking_reasons": ["contract_status_unavailable"],
        "runtime_state": "fixture",
        "status_text": "Contract status is unavailable.",
    }


def _fixture_live_snapshot() -> object:
    cache_snapshot = StreamCacheSnapshot(
        generated_at=_NOW.isoformat(),
        provider="fixture",
        provider_status="active",
        cache_max_age_seconds=15.0,
        records=tuple(_quote_record(contract) for contract in final_target_contracts()),
        blocking_reasons=(),
        stale_symbols=(),
    )
    return build_live_observable_snapshot_v2(
        cache_snapshot,
        expected_symbols=_SYMBOL_BY_CONTRACT,
        bar_states=_bar_states(),
        dependency_states=_dependency_states(),
        clock=lambda: _NOW,
    )


def _quote_record(contract: str) -> StreamCacheRecord:
    fresh = contract != "CL"
    fields = (
        ("bid", 1.0),
        ("ask", 1.25),
        ("last", 1.125),
        ("bid_size", 10),
        ("ask_size", 12),
        ("quote_time", (_NOW if fresh else _NOW - timedelta(seconds=90)).isoformat()),
        ("trade_time", (_NOW if fresh else _NOW - timedelta(seconds=90)).isoformat()),
        ("volume", 1000),
        ("open", 1.0),
        ("high", 1.5),
        ("low", 0.75),
        ("prior_close", 0.9),
        ("tradable", True),
        ("active", True),
        ("security_status", "Normal"),
    )
    return StreamCacheRecord(
        provider="fixture",
        service="LEVELONE_FUTURES",
        symbol=_SYMBOL_BY_CONTRACT[contract],
        contract=contract,
        message_type="quote",
        fields=fields,
        updated_at=(_NOW if fresh else _NOW - timedelta(seconds=90)).isoformat(),
        age_seconds=0.0 if fresh else 90.0,
        fresh=fresh,
        blocking_reasons=(),
    )


def _bar_states() -> dict[str, ContractBarState]:
    states: dict[str, ContractBarState] = {}
    for contract in ("ES", "CL", "6E", "MGC"):
        state = _completed_bar_state(contract)
        if contract == "CL":
            state = replace(state, blocking_reasons=("stale_bar_data:CL",))
        states[contract] = state
    return states


def _completed_bar_state(contract: str) -> ContractBarState:
    builder = ChartFuturesBarBuilder(expected_symbols=_SYMBOL_BY_CONTRACT)
    for minute in range(5):
        start = _NOW - timedelta(minutes=5 - minute)
        builder.ingest(
            {
                "service": "CHART_FUTURES",
                "contract": contract,
                "symbol": _SYMBOL_BY_CONTRACT[contract],
                "start_time": start.isoformat(),
                "end_time": (start + timedelta(minutes=1)).isoformat(),
                "open": 1.0 + minute,
                "high": 1.5 + minute,
                "low": 0.75 + minute,
                "close": 1.25 + minute,
                "volume": 100 + minute,
                "completed": True,
            }
        )
    return builder.state(contract)


def _dependency_states() -> dict[str, dict[str, object]]:
    return {
        "ES": {
            "cumulative_delta": {
                "status": "available",
                "source": "fixture",
                "fresh": True,
            },
            "breadth": {"status": "available", "source": "fixture", "fresh": True},
        },
        "NQ": {
            "relative_strength_vs_es": {
                "status": "available",
                "source": "fixture",
                "fresh": True,
            },
        },
        "CL": {
            "eia_lockout": {"status": "available", "source": "fixture", "fresh": True},
            "cumulative_delta": {
                "status": "available",
                "source": "fixture",
                "fresh": True,
            },
            "current_volume_vs_average": {
                "status": "available",
                "source": "fixture",
                "fresh": True,
            },
        },
        "6E": {
            "dxy": {"status": "unavailable", "source": "fixture", "fresh": False},
            "session_sequence": {
                "status": "available",
                "source": "fixture",
                "fresh": True,
            },
        },
        "MGC": {
            "dxy": {"status": "available", "source": "fixture", "fresh": True},
            "cash_10y_yield": {
                "status": "available",
                "source": "fixture",
                "fresh": True,
            },
            "fear_catalyst_state": {
                "status": "available",
                "source": "fixture",
                "fresh": True,
            },
        },
    }


def _trigger_state(contract: str) -> TriggerStateResult:
    if contract == "6E":
        state = TriggerState.BLOCKED
        missing_fields: tuple[str, ...] = ("cross_asset.dxy",)
        blocking_reasons: tuple[str, ...] = ("dependency_unavailable:6E:dxy",)
    else:
        state = TriggerState.QUERY_READY
        missing_fields = ()
        blocking_reasons = ()
    return TriggerStateResult(
        contract=contract,
        setup_id=f"{contract.lower()}_fixture_setup",
        trigger_id=f"{contract.lower()}_fixture_trigger",
        state=state,
        distance_to_trigger_ticks=0.0 if state == TriggerState.QUERY_READY else None,
        required_fields=("market.current_price", "market.completed_chart_bar"),
        missing_fields=missing_fields,
        invalid_reasons=(),
        blocking_reasons=blocking_reasons,
        last_updated=_NOW.isoformat(),
    )


def _premarket_brief(contract: str) -> dict[str, object]:
    return {
        "contract": contract,
        "session_date": "2026-05-06",
        "status": "READY",
        "source_context": {
            "required_context": [],
            "missing_required_context": [],
            "unavailable_required_context": [],
        },
        "structural_setups": [
            {
                "id": f"{contract.lower()}_fixture_setup",
                "summary": f"{contract} fixture dry-run setup.",
                "required_live_fields": [
                    "market.current_price",
                    "market.completed_chart_bar",
                ],
                "query_triggers": [
                    {
                        "id": f"{contract.lower()}_fixture_trigger",
                        "description": f"{contract} fixture operator-session trigger.",
                        "required_live_fields": [
                            "market.current_price",
                            "market.completed_chart_bar",
                        ],
                        "invalidators": [],
                    }
                ],
            }
        ],
    }
