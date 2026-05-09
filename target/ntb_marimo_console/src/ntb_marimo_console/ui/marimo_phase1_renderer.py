from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import marimo as mo

from ..session_evidence import NO_RECENT_SESSION_EVIDENCE
from ..watchman_gate import build_watchman_gate_markdown, watchman_gate_requires_stop

FROZEN_SURFACE_KEYS: tuple[str, ...] = (
    "session_header",
    "five_contract_readiness_summary",
    "pre_market_brief",
    "readiness_matrix",
    "live_observables",
    "trigger_table",
    "query_action",
    "decision_review",
    "audit_replay",
    "run_history",
)

_CONSOLE_STACK_STYLE = {
    "gap": "14px",
    "padding": "12px",
    "background": "var(--md-sys-color-surface, #f8fafc)",
}

_HEADER_STYLE = {
    "border": "1px solid var(--md-sys-color-outline-variant, #d5dbe3)",
    "borderRadius": "8px",
    "padding": "14px 16px",
    "background": "var(--md-sys-color-surface-container-low, #ffffff)",
    "boxShadow": "0 1px 2px rgba(15, 23, 42, 0.04)",
}

_CARD_STYLE = {
    "border": "1px solid var(--md-sys-color-outline-variant, #d5dbe3)",
    "borderRadius": "8px",
    "padding": "12px 14px",
    "background": "var(--md-sys-color-surface-container-lowest, #ffffff)",
    "boxShadow": "0 1px 2px rgba(15, 23, 42, 0.035)",
}

_CONTROL_CARD_STYLE = {
    "border": "1px solid var(--md-sys-color-outline-variant, #d5dbe3)",
    "borderRadius": "8px",
    "padding": "12px",
    "background": "var(--md-sys-color-surface-container-low, #f8fafc)",
}

_DEBUG_CARD_STYLE = {
    "border": "1px dashed var(--md-sys-color-outline-variant, #d5dbe3)",
    "borderRadius": "8px",
    "padding": "10px 12px",
    "background": "var(--md-sys-color-surface-container-lowest, #ffffff)",
    "opacity": "0.86",
}


def build_phase1_render_plan(shell: Mapping[str, object]) -> dict[str, object]:
    warnings: list[str] = []

    title = _as_str(shell.get("title"), default="NTB Marimo Console")
    surfaces_raw = shell.get("surfaces")
    surfaces: dict[str, object] = {}
    if isinstance(surfaces_raw, Mapping):
        surfaces = dict(surfaces_raw)
    else:
        warnings.append("Missing or invalid shell.surfaces; rendering fail-closed placeholders.")

    rendered_sections: list[dict[str, object]] = []
    for key in FROZEN_SURFACE_KEYS:
        value = surfaces.get(key)
        if key == "five_contract_readiness_summary" and not isinstance(value, Mapping):
            value = _build_five_contract_readiness_summary_fallback(shell)
        if not isinstance(value, Mapping):
            warnings.append(f"Missing or invalid surface: {key}")
            rendered_sections.append({"key": key, "panel": {"surface": key, "warning": "unavailable"}})
            continue
        rendered_sections.append({"key": key, "panel": dict(value)})

    return {
        "title": title,
        "sections": rendered_sections,
        "warnings": warnings,
        "debug": {
            "secondary": True,
            "shell_json": json.dumps(dict(shell), indent=2),
        },
    }


def render_phase1_console(
    shell: Mapping[str, object],
    *,
    heading: str,
    mode_summary: str,
    query_action_control: Any | None = None,
    lifecycle_control_panel: Any | None = None,
    profile_control_panel: Any | None = None,
    evidence_control_panel: Any | None = None,
) -> Any:
    plan = build_phase1_render_plan(shell)

    elements: list[Any] = [
        _render_console_header(shell, heading=heading, mode_summary=mode_summary),
    ]

    startup = shell.get("startup")
    operator_ready = True
    if isinstance(startup, Mapping):
        operator_ready = startup.get("operator_ready") is True
        elements.append(_render_markdown_card(build_startup_status_markdown(startup)))
        elements.append(_render_markdown_card(build_profile_operations_markdown(startup)))
        if profile_control_panel is not None:
            elements.append(_render_control_card(profile_control_panel))

    runtime = shell.get("runtime")
    if isinstance(runtime, Mapping):
        elements.append(_render_markdown_card(build_runtime_identity_markdown(runtime)))

    lifecycle = shell.get("lifecycle")
    if isinstance(lifecycle, Mapping):
        elements.append(_render_markdown_card(build_session_lifecycle_markdown(lifecycle)))
        if lifecycle_control_panel is not None:
            elements.append(_render_control_card(lifecycle_control_panel))

    evidence = shell.get("evidence")
    if isinstance(evidence, Mapping):
        elements.append(_render_markdown_card(build_session_evidence_markdown(evidence)))
        if evidence_control_panel is not None:
            elements.append(_render_control_card(evidence_control_panel))

    workflow = shell.get("workflow")
    if isinstance(workflow, Mapping):
        elements.append(_render_markdown_card(build_session_workflow_markdown(workflow)))

    if operator_ready:
        for warning in plan["warnings"]:
            elements.append(_render_markdown_card(f"**Warning:** {warning}"))

        for section in plan["sections"]:
            key = _as_str(section.get("key"), default="unknown")
            panel_raw = section.get("panel")
            panel = panel_raw if isinstance(panel_raw, Mapping) else {"warning": "unavailable"}
            elements.append(_render_surface_section(key, panel, query_action_control=query_action_control))
    else:
        elements.append(
            _render_markdown_card(
                "\n".join(
                    [
                        "## Operator Surfaces",
                        "- Blocked until startup preflight passes and runtime assembly completes.",
                        "- Fix the reported startup diagnostics, then relaunch the console.",
                    ]
                )
            )
        )

    elements.append(_render_debug_secondary(_as_str(plan["debug"].get("shell_json"), default="{}")))
    return mo.vstack(elements, gap=0.75).style(_CONSOLE_STACK_STYLE)


def render_watchman_gate_stop_output(
    shell: Mapping[str, object],
    *,
    heading: str,
    mode_summary: str,
    lifecycle_control_panel: Any | None = None,
    profile_control_panel: Any | None = None,
    evidence_control_panel: Any | None = None,
) -> Any | None:
    if not watchman_gate_requires_stop(shell):
        return None

    elements: list[Any] = [
        _render_console_header(shell, heading=heading, mode_summary=mode_summary),
    ]

    startup = shell.get("startup")
    if isinstance(startup, Mapping):
        elements.append(_render_markdown_card(build_startup_status_markdown(startup)))
        elements.append(_render_markdown_card(build_profile_operations_markdown(startup)))
        if profile_control_panel is not None:
            elements.append(_render_control_card(profile_control_panel))

    runtime = shell.get("runtime")
    if isinstance(runtime, Mapping):
        elements.append(_render_markdown_card(build_runtime_identity_markdown(runtime)))

    lifecycle = shell.get("lifecycle")
    if isinstance(lifecycle, Mapping):
        elements.append(_render_markdown_card(build_session_lifecycle_markdown(lifecycle)))
        if lifecycle_control_panel is not None:
            elements.append(_render_control_card(lifecycle_control_panel))

    evidence = shell.get("evidence")
    if isinstance(evidence, Mapping):
        elements.append(_render_markdown_card(build_session_evidence_markdown(evidence)))
        if evidence_control_panel is not None:
            elements.append(_render_control_card(evidence_control_panel))

    workflow = shell.get("workflow")
    if isinstance(workflow, Mapping):
        elements.append(_render_markdown_card(build_session_workflow_markdown(workflow)))

    surfaces = shell.get("surfaces")
    if isinstance(surfaces, Mapping):
        session_header = surfaces.get("session_header")
        if isinstance(session_header, Mapping):
            elements.append(_render_surface_section("session_header", session_header))
        readiness_matrix = surfaces.get("readiness_matrix")
        if isinstance(readiness_matrix, Mapping):
            elements.append(_render_surface_section("readiness_matrix", readiness_matrix))

    gate = shell.get("watchman_gate")
    if isinstance(gate, Mapping):
        elements.append(_render_markdown_card(build_watchman_gate_markdown(gate)))

    elements.append(_render_debug_secondary(json.dumps(dict(shell), indent=2)))
    return mo.vstack(elements, gap=0.75).style(_CONSOLE_STACK_STYLE)


def build_startup_status_markdown(startup: Mapping[str, object]) -> str:
    profile_lines = _supported_profile_lines(startup.get("supported_profiles"))
    readiness_history = startup.get("readiness_history")
    readiness_path = "<unavailable>"
    if isinstance(readiness_history, list):
        readiness_path = " -> ".join(_as_str(item) for item in readiness_history) if readiness_history else "<none>"

    lines = [
        "## Startup Status",
        f"- App Identity: `{_as_str(startup.get('app_name'), default='NTB Marimo Console')}`",
        f"- Selected Profile: `{_as_str(startup.get('selected_profile_id'), default='<unresolved>')}`",
        "- Supported Profiles:",
        profile_lines,
        f"- Runtime Mode: `{_as_str(startup.get('runtime_mode_label'), default='<unavailable>')}`",
        f"- Running As: `{_as_str(startup.get('running_as'), default='<unavailable>')}`",
        f"- Contract: `{_as_str(startup.get('contract'), default='<unresolved>')}`",
        f"- Session Date: `{_as_str(startup.get('session_date'), default='<unresolved>')}`",
        f"- Preflight Status: `{_as_str(startup.get('preflight_status'), default='<unavailable>')}`",
        f"- Readiness State: `{_as_str(startup.get('readiness_state'), default='<unavailable>')}`",
        f"- Startup Path: `{readiness_path}`",
        f"- Operator Ready: `{_as_str(startup.get('operator_ready'), default=False)}`",
        f"- Session Workflow State: `{_as_str(startup.get('current_session_state'), default='NOT_ASSEMBLED')}`",
        f"- Status Summary: {_as_str(startup.get('status_summary'), default='<unavailable>')}",
        f"- Next Action: {_as_str(startup.get('next_action'), default='<unavailable>')}",
    ]

    blocking_checks = startup.get("blocking_checks")
    if isinstance(blocking_checks, list) and blocking_checks:
        lines.append("- Blocking Diagnostics:")
        for check in blocking_checks:
            if not isinstance(check, Mapping):
                continue
            lines.append(
                "  - "
                + f"[{_as_str(check.get('category'), default='unknown')}] "
                + _as_str(check.get("summary"), default="<unavailable>")
            )
            lines.append(
                "    Remedy: "
                + _as_str(check.get("remedy"), default="<unavailable>")
            )

    return "\n".join(lines)


def build_profile_operations_markdown(startup: Mapping[str, object]) -> str:
    supported_lines = _supported_profile_lines(startup.get("supported_profiles"))
    legacy_lines = _supported_profile_lines(startup.get("legacy_historical_profiles"))
    candidate_lines = _candidate_profile_lines(startup.get("candidate_profiles"))
    return "\n".join(
        [
            "## Supported Profile Operations",
            f"- Active Profile: `{_as_str(startup.get('selected_profile_id'), default='<unresolved>')}`",
            "- Final-Target Selectable Profiles:",
            supported_lines,
            "- Legacy/Historical Runtime Profiles:",
            legacy_lines,
            "- Candidate Contract Status:",
            candidate_lines,
            f"- Candidate Audit Available: `{_as_str(startup.get('candidate_audit_available'), default=False)}`",
            f"- Candidate Audit Summary: {_as_str(startup.get('candidate_audit_summary'), default='<unavailable>')}",
            "- Profile Switch Behavior: switching to another supported profile reruns preflight, reloads the declared artifacts for that profile, and clears session-specific query/review/replay state.",
            "- Blocked candidate contracts remain visible here for operator awareness, but they do not become selectable until the audit no longer reports them as blocked.",
        ]
    )


def build_runtime_identity_markdown(runtime: Mapping[str, object]) -> str:
    state = _as_str(runtime.get("session_state"), default="<unavailable>")
    state_history = runtime.get("state_history")
    history_text = "<unavailable>"
    if isinstance(state_history, list):
        history_text = " -> ".join(_as_str(item) for item in state_history) if state_history else "<none>"

    startup_history = runtime.get("startup_state_history")
    startup_text = "<unavailable>"
    if isinstance(startup_history, list):
        startup_text = " -> ".join(_as_str(item) for item in startup_history) if startup_history else "<none>"

    preflight_status = _as_str(runtime.get("preflight_status"), default="<unavailable>")
    return "\n".join(
        [
            "## Runtime Identity",
            f"- Profile ID: `{_as_str(runtime.get('profile_id'), default='<unavailable>')}`",
            f"- Runtime Mode: `{_as_str(runtime.get('runtime_mode'), default='<unavailable>')}`",
            f"- Runtime Backend: `{_as_str(runtime.get('runtime_backend'), default='<unavailable>')}`",
            f"- Contract: `{_as_str(runtime.get('contract'), default='<unavailable>')}`",
            f"- Session Date: `{_as_str(runtime.get('session_date'), default='<unavailable>')}`",
            f"- Artifact Root: `{_as_str(runtime.get('artifact_root'), default='<unavailable>')}`",
            f"- Adapter Binding: `{_as_str(runtime.get('adapter_binding'), default='<unavailable>')}`",
            f"- Preflight Status: `{preflight_status}`",
            f"- Startup Readiness: `{_as_str(runtime.get('startup_readiness_state'), default='<unavailable>')}`",
            f"- Startup State History: `{startup_text}`",
            f"- Operator Ready: `{_as_str(runtime.get('operator_ready'), default=False)}`",
            f"- Live Query Status: `{_as_str(runtime.get('live_query_status'), default='<unavailable>')}`",
            f"- Query Action Status: `{_as_str(runtime.get('query_action_status'), default='<unavailable>')}`",
            f"- Decision Review Ready: `{_as_str(runtime.get('decision_review_ready'), default=False)}`",
            f"- Audit / Replay Ready: `{_as_str(runtime.get('audit_replay_ready'), default=False)}`",
            f"- Current State: `{state}`",
            f"- State History: `{history_text}`",
        ]
    )


def build_session_workflow_markdown(workflow: Mapping[str, object]) -> str:
    history = workflow.get("state_history")
    history_text = "<unavailable>"
    if isinstance(history, list):
        history_text = " -> ".join(_as_str(item) for item in history) if history else "<none>"

    lines = [
        "## Session Workflow",
        f"- Current State: `{_as_str(workflow.get('current_state'), default='<unavailable>')}`",
        f"- Watchman Gate Status: `{_as_str(workflow.get('watchman_gate_status'), default='<unavailable>')}`",
        f"- Live Query Status: `{_as_str(workflow.get('live_query_status'), default='<unavailable>')}`",
        f"- Query Action Status: `{_as_str(workflow.get('query_action_status'), default='<unavailable>')}`",
        f"- Query Action Available: `{_as_str(workflow.get('query_action_available'), default=False)}`",
        f"- Decision Review Ready: `{_as_str(workflow.get('decision_review_ready'), default=False)}`",
        f"- Audit / Replay Ready: `{_as_str(workflow.get('audit_replay_ready'), default=False)}`",
        f"- Workflow History: `{history_text}`",
        f"- Status Summary: {_as_str(workflow.get('status_summary'), default='<unavailable>')}",
        f"- Next Action: {_as_str(workflow.get('next_action'), default='<unavailable>')}",
    ]

    blocked_reasons = workflow.get("blocked_reasons")
    if isinstance(blocked_reasons, list) and blocked_reasons:
        lines.append("- Blocked Reasons:")
        for reason in blocked_reasons:
            lines.append(f"  - {_as_str(reason)}")

    error_message = workflow.get("error_message")
    if error_message is not None:
        lines.append(f"- Error: {_as_str(error_message)}")

    return "\n".join(lines)


def build_session_lifecycle_markdown(lifecycle: Mapping[str, object]) -> str:
    history = lifecycle.get("state_history")
    history_text = "<unavailable>"
    if isinstance(history, list):
        history_text = " -> ".join(_as_str(item) for item in history) if history else "<none>"

    reload_changed_sources = lifecycle.get("reload_changed_sources")
    reload_source_text = "<not_checked>"
    if reload_changed_sources is True:
        reload_source_text = "CHANGED"
    elif reload_changed_sources is False:
        reload_source_text = "UNCHANGED"

    return "\n".join(
        [
            "## Session Lifecycle",
            f"- Lifecycle State: `{_as_str(lifecycle.get('current_lifecycle_state'), default='<unavailable>')}`",
            f"- Current Session State: `{_as_str(lifecycle.get('current_session_state'), default='<unavailable>')}`",
            f"- Last Action: `{_as_str(lifecycle.get('last_action'), default='<unavailable>')}`",
            f"- Reload Result: `{_as_str(lifecycle.get('reload_result'), default='<unavailable>')}`",
            f"- Reload Source Change: `{reload_source_text}`",
            f"- Preflight Reran: `{_as_str(lifecycle.get('preflight_reran'), default=False)}`",
            f"- Reset Available: `{_as_str(lifecycle.get('reset_available'), default=False)}`",
            f"- Reload Available: `{_as_str(lifecycle.get('reload_available'), default=False)}`",
            f"- Profile Switch Available: `{_as_str(lifecycle.get('profile_switch_available'), default=False)}`",
            f"- Profile Switch Target: `{_as_str(lifecycle.get('profile_switch_target_id'), default='<none>')}`",
            f"- Profile Switch Result: `{_as_str(lifecycle.get('profile_switch_result'), default='NOT_RUN')}`",
            f"- Operator Ready: `{_as_str(lifecycle.get('operator_ready'), default=False)}`",
            f"- Query Action Status: `{_as_str(lifecycle.get('query_action_status'), default='<unavailable>')}`",
            f"- Decision Review Ready: `{_as_str(lifecycle.get('decision_review_ready'), default=False)}`",
            f"- Audit / Replay Ready: `{_as_str(lifecycle.get('audit_replay_ready'), default=False)}`",
            f"- Lifecycle History: `{history_text}`",
            f"- Status Summary: {_as_str(lifecycle.get('status_summary'), default='<unavailable>')}",
            f"- Next Action: {_as_str(lifecycle.get('next_action'), default='<unavailable>')}",
        ]
    )


def build_session_evidence_markdown(evidence: Mapping[str, object]) -> str:
    recent_profiles = evidence.get("recent_profiles")
    recent_profiles_text = "<none>"
    if isinstance(recent_profiles, list):
        recent_profiles_text = ", ".join(_as_str(item) for item in recent_profiles) if recent_profiles else "<none>"

    lines = [
        "## Recent Session Evidence",
        f"- History Scope: `{_as_str(evidence.get('history_scope'), default='<unavailable>')}`",
        f"- History Limit: `{_as_str(evidence.get('history_limit'), default='<unavailable>')}`",
        f"- Persistence Path: `{_as_str(evidence.get('persistence_path'), default='<unavailable>')}`",
        f"- Restore Status: `{_as_str(evidence.get('restore_status'), default='<unavailable>')}`",
        f"- Restore Summary: {_as_str(evidence.get('restore_status_summary'), default='<unavailable>')}",
        f"- Persistence Health: `{_as_str(evidence.get('persistence_health_status'), default='<unavailable>')}`",
        f"- Last Persistence Status: `{_as_str(evidence.get('last_persistence_status'), default='<unavailable>')}`",
        f"- Last Persistence At UTC: `{_as_str(evidence.get('last_persistence_at_utc'), default='<none>')}`",
        f"- Last Persistence Summary: {_as_str(evidence.get('last_persistence_summary'), default='<unavailable>')}",
        f"- Active Profile Now: `{_as_str(evidence.get('active_profile_id'), default='<unavailable>')}`",
        f"- Current Session Events: `{_as_str(evidence.get('current_session_record_count'), default=0)}`",
        f"- Restored Prior-Run Events: `{_as_str(evidence.get('restored_record_count'), default=0)}`",
        f"- Recent Profiles: `{recent_profiles_text}`",
        f"- Status Summary: {_as_str(evidence.get('status_summary'), default='<unavailable>')}",
        "- Last Known Outcome By Supported Profile:",
    ]

    last_known_outcomes = evidence.get("last_known_outcomes")
    if isinstance(last_known_outcomes, list) and last_known_outcomes:
        for outcome in last_known_outcomes:
            if not isinstance(outcome, Mapping):
                continue
            if outcome.get("has_recent_evidence") is not True:
                lines.append(
                    "  - "
                    + f"{_as_str(outcome.get('profile_id'))}: "
                    + _as_str(outcome.get("status_summary"), default=NO_RECENT_SESSION_EVIDENCE)
                )
                continue

            decision_suffix = _ready_outcome_suffix(
                outcome.get("decision_review_state"),
                outcome.get("decision_review_outcome"),
            )
            audit_suffix = _ready_outcome_suffix(
                outcome.get("audit_replay_state"),
                outcome.get("audit_replay_outcome"),
            )
            lines.append(
                "  - "
                + f"{_as_str(outcome.get('profile_id'))}: "
                + f"event=#{_as_str(outcome.get('event_index'))}, "
                + f"source={_as_str(outcome.get('source_label'), default=outcome.get('source_scope'))}, "
                + f"at={_as_str(outcome.get('recorded_at_utc'))}, "
                + f"action={_as_str(outcome.get('last_action'))}, "
                + f"preflight={_as_str(outcome.get('preflight_status'))}, "
                + f"startup={_as_str(outcome.get('startup_outcome'))}, "
                + f"live_query={_as_str(outcome.get('query_eligibility_state'))}, "
                + f"query_action={_as_str(outcome.get('query_action_state'))}, "
                + f"decision_review={decision_suffix}, "
                + f"audit_replay={audit_suffix}"
            )
    else:
        lines.append(f"  - {NO_RECENT_SESSION_EVIDENCE}")

    lines.append("- Recent Activity:")
    recent_activity = evidence.get("recent_activity")
    if isinstance(recent_activity, list) and recent_activity:
        for item in recent_activity:
            if not isinstance(item, Mapping):
                continue
            lines.append(
                "  - "
                + f"#{_as_str(item.get('event_index'))} "
                + f"[{_as_str(item.get('source_label'), default=item.get('source_scope'))}] "
                + f"at `{_as_str(item.get('recorded_at_utc'))}` "
                + f"{_as_str(item.get('active_profile_id'))}: "
                + _as_str(item.get("summary"), default="<unavailable>")
            )
    else:
        lines.append(f"  - {NO_RECENT_SESSION_EVIDENCE}")
    return "\n".join(lines)


def _render_surface_section(
    key: str,
    panel: Mapping[str, object],
    *,
    query_action_control: Any | None = None,
) -> Any:
    if key == "session_header":
        contract = _as_str(panel.get("contract"))
        session_date = _as_str(panel.get("session_date"))
        return _render_surface_card(mo.md(f"## Session Header\n- Contract: `{contract}`\n- Session Date: `{session_date}`"))

    if key == "pre_market_brief":
        setup_lines = _bullet_lines(panel.get("setup_summaries"))
        warning_lines = _bullet_lines(panel.get("warnings"))
        return _render_surface_card(
            mo.md(
                "\n".join(
                    [
                        "## Pre-Market Brief",
                        f"- Contract: `{_as_str(panel.get('contract'))}`",
                        f"- Session Date: `{_as_str(panel.get('session_date'))}`",
                        f"- Status: `{_as_str(panel.get('status'))}`",
                        "- Setup Summaries:",
                        setup_lines,
                        "- Warnings:",
                        warning_lines,
                    ]
                )
            )
        )

    if key == "readiness_matrix":
        rows = panel.get("rows")
        row_lines: list[str] = []
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, Mapping):
                    row_lines.append(
                        "- "
                        + f"{_as_str(row.get('contract'))}: status={_as_str(row.get('status'))}, "
                        + f"event_risk={_as_str(row.get('event_risk'))}, "
                        + f"hard_lockouts={_safe_json(row.get('hard_lockouts'))}"
                    )
        return _render_surface_card(mo.md("## Readiness Matrix\n" + ("\n".join(row_lines) if row_lines else "- unavailable")))

    if key == "five_contract_readiness_summary":
        rows = panel.get("rows")
        lines = [
            "## Five-Contract Readiness Summary",
            f"- Mode: `{_as_str(panel.get('mode'), default='<unavailable>')}`",
            f"- Active Profile: `{_as_str(panel.get('active_profile_id'), default='<none>')}`",
            f"- Default Launch Live: `{_as_str(panel.get('default_launch_live'), default=False)}`",
            f"- Live Credentials Required: `{_as_str(panel.get('live_credentials_required'), default=False)}`",
            f"- Decision Authority: `{_as_str(panel.get('decision_authority'), default='<unavailable>')}`",
            f"- Manual Execution Only: `{_as_str(panel.get('manual_execution_only'), default=True)}`",
            f"- Summary Can Authorize Trades: `{_as_str(panel.get('summary_can_authorize_trades'), default=False)}`",
            f"- Live Runtime Readiness: `{_as_str(panel.get('live_runtime_readiness_status'), default='<unavailable>')}`",
            f"- Runtime Cache Bound To Operator Launch: `{_as_str(panel.get('runtime_cache_bound_to_operator_launch'), default=False)}`",
            "- Rows:",
        ]
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, Mapping):
                    continue
                lines.append(
                    "  - "
                    + f"{_as_str(row.get('contract'))}: "
                    + f"profile={_as_str(row.get('runtime_profile_id'))}, "
                    + f"preflight={_as_str(row.get('preflight_status'))}, "
                    + f"startup={_as_str(row.get('startup_readiness_state'))}, "
                    + f"operator_ready={_as_str(row.get('operator_ready'))}, "
                    + f"market_data={_as_str(row.get('market_data_status'))}, "
                    + f"runtime_cache={_as_str(row.get('runtime_cache_status'), default='<unavailable>')}, "
                    + f"trigger={_as_str(row.get('trigger_state_summary'))}, "
                    + f"query={_as_str(row.get('query_gate_status'))}"
                )
                blocked = row.get("primary_blocked_reasons")
                if isinstance(blocked, list) and blocked:
                    lines.append("    Blocked: " + ", ".join(_as_str(item) for item in blocked))
                query_not_ready = row.get("query_not_ready_reasons")
                if isinstance(query_not_ready, list) and query_not_ready:
                    lines.append("    Query Not Ready: " + ", ".join(_as_str(item) for item in query_not_ready))
        else:
            lines.append("  - <unavailable>")
        return _render_surface_card(mo.md("\n".join(lines)))

    if key == "live_observables":
        snapshot = panel.get("snapshot")
        lines = [
            "## Live Observables",
            f"- Contract: `{_as_str(panel.get('contract'))}`",
            f"- Timestamp ET: `{_as_str(panel.get('timestamp_et'))}`",
            "- Snapshot Fields:",
        ]
        if not isinstance(snapshot, Mapping):
            lines.append("  - <unavailable>")
            return _render_surface_card(mo.md("\n".join(lines)))

        flattened = _flatten_mapping_lines(snapshot)
        if flattened:
            lines.extend([f"  - `{field}`: `{value}`" for field, value in flattened])
        else:
            lines.append("  - <unavailable>")
        return _render_surface_card(mo.md("\n".join(lines)))

    if key == "trigger_table":
        rows = panel.get("rows")
        row_lines: list[str] = []
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, Mapping):
                    row_lines.append(
                        "- "
                        + f"{_as_str(row.get('trigger_id'))}: valid={_as_str(row.get('is_valid'))}, "
                        + f"true={_as_str(row.get('is_true'))}, "
                        + f"missing={_safe_json(row.get('missing_fields'))}"
                    )
        return _render_surface_card(mo.md("## Trigger Table\n" + ("\n".join(row_lines) if row_lines else "- unavailable")))

    if key == "query_action":
        lines = [
            "## Live Query",
            f"- Watchman Gate Status: `{_as_str(panel.get('watchman_gate_status'), default='<unavailable>')}`",
            f"- Trigger Gate: `{_as_str(panel.get('trigger_gate'))}`",
            f"- Readiness Gate: `{_as_str(panel.get('readiness_gate'))}`",
            f"- Query Enabled: `{_as_str(panel.get('query_enabled'))}`",
            f"- Live Query Status: `{_as_str(panel.get('live_query_status'), default='<unavailable>')}`",
            f"- Query Action Status: `{_as_str(panel.get('query_action_status'), default='<unavailable>')}`",
            f"- Action Available: `{_as_str(panel.get('action_available'), default=False)}`",
            f"- Manual Override Available: `{_as_str(panel.get('manual_override_available'))}`",
            f"- Action Scope: {_as_str(panel.get('bounded_action_description'), default='<unavailable>')}",
            f"- Status Summary: {_as_str(panel.get('status_summary'), default='<unavailable>')}",
            f"- Next Action: {_as_str(panel.get('next_action'), default='<unavailable>')}",
        ]
        blocked_reasons = panel.get("blocked_reasons")
        if isinstance(blocked_reasons, list) and blocked_reasons:
            lines.append("- Blocked Reasons:")
            for reason in blocked_reasons:
                lines.append(f"  - {_as_str(reason)}")

        failure_message = panel.get("failure_message")
        content: list[Any] = [mo.md("\n".join(lines))]
        if failure_message is not None:
            content.append(mo.md(f"**Failure:** {_as_str(failure_message)}"))
        if panel.get("action_available") is True and query_action_control is not None:
            content.append(query_action_control)
        return _render_surface_card(mo.vstack(content, gap=0.5))

    if key == "decision_review":
        if panel.get("has_result") is True:
            return _render_surface_card(
                mo.md(
                    "\n".join(
                        [
                            "## Decision Review",
                            f"- Ready: `{_as_str(panel.get('ready'), default=True)}`",
                            f"- Status: `{_as_str(panel.get('status'), default='READY')}`",
                            f"- Message: {_as_str(panel.get('message'), default='Decision Review is ready.')}",
                            f"- Contract: `{_as_str(panel.get('contract'))}`",
                            f"- Termination Stage: `{_as_str(panel.get('termination_stage'))}`",
                            f"- Final Decision: `{_as_str(panel.get('final_decision'))}`",
                            f"- Stage A: `{_as_str(panel.get('stage_a_status'))}`",
                            f"- Stage B: `{_as_str(panel.get('stage_b_outcome'))}`",
                            f"- Stage C: `{_as_str(panel.get('stage_c_outcome'))}`",
                            f"- Stage D: `{_as_str(panel.get('stage_d_decision'))}`",
                        ]
                    )
                )
            )
        return _render_surface_card(
            mo.md(
                "\n".join(
                    [
                        "## Decision Review",
                        f"- Ready: `{_as_str(panel.get('ready'), default=False)}`",
                        f"- Status: `{_as_str(panel.get('status'), default='NOT_READY')}`",
                        f"- Message: {_as_str(panel.get('message'), default='Decision Review is not ready yet.')}",
                    ]
                )
            )
        )

    if key == "run_history":
        rows = panel.get("rows")
        lines = [
            "## Run History",
            f"- Source: `{_as_str(panel.get('source'))}`",
            "- Entries:",
        ]
        if not isinstance(rows, list):
            lines.append("  - <unavailable>")
            return _render_surface_card(mo.md("\n".join(lines)))

        rendered_rows = 0
        preferred_fields = (
            "contract",
            "session_date",
            "run_timestamp_et",
            "termination_stage",
            "final_decision",
            "stage_d_decision",
        )
        for index, row in enumerate(rows, start=1):
            if not isinstance(row, Mapping):
                continue
            row_parts: list[str] = []
            for field in preferred_fields:
                if field in row:
                    row_parts.append(f"{field}={_inline_value(row.get(field))}")
            if not row_parts:
                for field, value in row.items():
                    row_parts.append(f"{field}={_inline_value(value)}")
                    if len(row_parts) >= 4:
                        break
            lines.append(f"  - [{index}] " + "; ".join(row_parts) if row_parts else f"  - [{index}] <unavailable>")
            rendered_rows += 1

        if rendered_rows == 0:
            lines.append("  - <unavailable>")
        return _render_surface_card(mo.md("\n".join(lines)))

    if key == "audit_replay":
        lines = [
            "## Audit / Replay",
            f"- Ready: `{_as_str(panel.get('ready'), default=False)}`",
            f"- Status: `{_as_str(panel.get('status'), default='NOT_READY')}`",
            f"- Message: {_as_str(panel.get('message'), default='Audit / Replay is not ready yet.')}",
            f"- Mode: `{_as_str(panel.get('mode'))}`",
            f"- Stage E Live Backend: `{_as_str(panel.get('stage_e_live_backend'))}`",
        ]
        trace_summary = panel.get("trace_summary")
        if isinstance(trace_summary, Mapping):
            lines.extend(
                [
                    f"- Contract: `{_as_str(trace_summary.get('contract'))}`",
                    f"- Termination Stage: `{_as_str(trace_summary.get('termination_stage'))}`",
                    f"- Final Decision: `{_as_str(trace_summary.get('final_decision'))}`",
                ]
            )
        else:
            lines.append("- Trace Summary: `<unavailable>`")
        return _render_surface_card(mo.md("\n".join(lines)))

    return _render_surface_card(mo.md(f"## {key}\n- unavailable"))


def _render_console_header(shell: Mapping[str, object], *, heading: str, mode_summary: str) -> Any:
    return mo.vstack(
        [
            mo.md(f"# {heading}"),
            mo.md(_build_context_summary_markdown(shell)),
            mo.md(mode_summary),
        ],
        gap=0.45,
    ).style(_HEADER_STYLE)


def _build_context_summary_markdown(shell: Mapping[str, object]) -> str:
    startup = shell.get("startup")
    runtime = shell.get("runtime")
    startup_map = startup if isinstance(startup, Mapping) else {}
    runtime_map = runtime if isinstance(runtime, Mapping) else {}

    mode = _first_value(startup_map, runtime_map, "runtime_mode_label", "runtime_mode")
    profile_id = _first_value(startup_map, runtime_map, "selected_profile_id", "profile_id")
    contract = _first_value(startup_map, runtime_map, "contract")
    readiness = _first_value(startup_map, runtime_map, "readiness_state", "startup_readiness_state")
    session_state = _first_value(startup_map, runtime_map, "current_session_state", "session_state")
    running_as = _first_value(startup_map, runtime_map, "running_as", "runtime_backend")

    return "\n".join(
        [
            "### Operating Context",
            "",
            "| Mode | Profile | Contract | Readiness | Session | Running As |",
            "| --- | --- | --- | --- | --- | --- |",
            (
                f"| `{_table_value(mode)}` | `{_table_value(profile_id)}` | `{_table_value(contract)}` | "
                f"`{_table_value(readiness)}` | `{_table_value(session_state)}` | `{_table_value(running_as)}` |"
            ),
        ]
    )


def _render_markdown_card(markdown: str) -> Any:
    return mo.md(markdown).style(_CARD_STYLE)


def _render_control_card(control_panel: Any) -> Any:
    return mo.vstack([control_panel], gap=0.35).style(_CONTROL_CARD_STYLE)


def _render_surface_card(element: Any) -> Any:
    return element.style(_CARD_STYLE)


def _first_value(primary: Mapping[str, object], secondary: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        value = primary.get(key)
        if value is not None:
            return _as_str(value, default="<unavailable>")
        value = secondary.get(key)
        if value is not None:
            return _as_str(value, default="<unavailable>")
    return "<unavailable>"


def _build_five_contract_readiness_summary_fallback(shell: Mapping[str, object]) -> dict[str, object]:
    from ..readiness_summary import build_five_contract_readiness_summary_surface

    startup = shell.get("startup")
    runtime = shell.get("runtime")
    startup_map = startup if isinstance(startup, Mapping) else {}
    runtime_map = runtime if isinstance(runtime, Mapping) else {}
    active_profile_id = _first_value(startup_map, runtime_map, "selected_profile_id", "profile_id")
    if active_profile_id == "<unavailable>":
        active_profile_id = None
    return build_five_contract_readiness_summary_surface(active_profile_id=active_profile_id)


def _table_value(value: object) -> str:
    return _as_str(value, default="<unavailable>").replace("|", "\\|")


def _as_str(value: object, *, default: str = "<missing>") -> str:
    if value is None:
        return default
    return str(value)


def _render_debug_secondary(shell_json: str) -> Any:
    return mo.vstack(
        [
            mo.md("## Debug (Secondary)"),
            mo.ui.code_editor(
                value=shell_json,
                language="json",
                disabled=True,
            ),
        ],
        gap=0.4,
    ).style(_DEBUG_CARD_STYLE)


def _safe_json(value: object) -> str:
    return json.dumps(value, indent=2)


def _inline_value(value: object) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"))
    return _as_str(value)


def _flatten_mapping_lines(
    mapping: Mapping[str, object],
    *,
    prefix: str = "",
) -> list[tuple[str, str]]:
    lines: list[tuple[str, str]] = []
    for key, value in mapping.items():
        field_path = f"{prefix}.{key}" if prefix else key
        if isinstance(value, Mapping):
            lines.extend(_flatten_mapping_lines(value, prefix=field_path))
            continue
        if isinstance(value, list):
            lines.append((field_path, json.dumps(value, separators=(",", ":"))))
            continue
        lines.append((field_path, _as_str(value)))
    return lines


def _bullet_lines(value: object) -> str:
    if isinstance(value, list):
        lines = [f"  - {_as_str(item)}" for item in value]
        return "\n".join(lines) if lines else "  - <none>"
    return "  - <missing>"


def _supported_profile_lines(value: object) -> str:
    if not isinstance(value, list):
        return "  - <missing>"

    lines: list[str] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        lines.append(
            "  - "
            + f"{_as_str(item.get('profile_id'))}: "
            + f"kind={_as_str(item.get('profile_kind'), default=_as_str(item.get('runtime_mode')))}, "
            + f"contract={_as_str(item.get('contract'))}, "
            + f"session_date={_as_str(item.get('session_date'))}, "
            + f"active={_as_str(item.get('active'), default=False)}"
        )
    return "\n".join(lines) if lines else "  - <none>"


def _candidate_profile_lines(value: object) -> str:
    if not isinstance(value, list):
        return "  - <missing>"

    lines: list[str] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        lines.append(
            "  - "
            + f"{_as_str(item.get('contract'))} -> {_as_str(item.get('profile_id'))}: "
            + f"status={_as_str(item.get('status'))}, "
            + f"reason={_as_str(item.get('reason_label'), default=_as_str(item.get('reason_category')))}"
        )
        lines.append("    Summary: " + _as_str(item.get("summary"), default="<unavailable>"))
    return "\n".join(lines) if lines else "  - <none>"


def _ready_outcome_suffix(state: object, outcome: object) -> str:
    state_text = _as_str(state, default="<unavailable>")
    if outcome is None:
        return state_text
    return f"{state_text} ({_as_str(outcome)})"
