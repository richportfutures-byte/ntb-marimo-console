from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import marimo as mo

FROZEN_SURFACE_KEYS: tuple[str, ...] = (
    "session_header",
    "pre_market_brief",
    "readiness_matrix",
    "live_observables",
    "trigger_table",
    "query_action",
    "decision_review",
    "audit_replay",
    "run_history",
)


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
) -> Any:
    plan = build_phase1_render_plan(shell)

    elements: list[Any] = [
        mo.md(f"# {heading}"),
        mo.md(mode_summary),
    ]

    startup = shell.get("startup")
    operator_ready = True
    if isinstance(startup, Mapping):
        operator_ready = startup.get("operator_ready") is True
        elements.append(mo.md(build_startup_status_markdown(startup)))

    runtime = shell.get("runtime")
    if isinstance(runtime, Mapping):
        elements.append(mo.md(build_runtime_identity_markdown(runtime)))

    lifecycle = shell.get("lifecycle")
    if isinstance(lifecycle, Mapping):
        elements.append(mo.md(build_session_lifecycle_markdown(lifecycle)))
        if lifecycle_control_panel is not None:
            elements.append(lifecycle_control_panel)

    workflow = shell.get("workflow")
    if isinstance(workflow, Mapping):
        elements.append(mo.md(build_session_workflow_markdown(workflow)))

    if operator_ready:
        for warning in plan["warnings"]:
            elements.append(mo.md(f"**Warning:** {warning}"))

        for section in plan["sections"]:
            key = _as_str(section.get("key"), default="unknown")
            panel_raw = section.get("panel")
            panel = panel_raw if isinstance(panel_raw, Mapping) else {"warning": "unavailable"}
            elements.append(_render_surface_section(key, panel, query_action_control=query_action_control))
    else:
        elements.append(
            mo.md(
                "\n".join(
                    [
                        "## Operator Surfaces",
                        "- Blocked until startup preflight passes and runtime assembly completes.",
                        "- Fix the reported startup diagnostics, then relaunch the console.",
                    ]
                )
            )
        )

    elements.append(
        mo.vstack(
            [
                mo.md("## Debug (Secondary)"),
                mo.ui.code_editor(
                    value=_as_str(plan["debug"].get("shell_json"), default="{}"),
                    language="json",
                    disabled=True,
                ),
            ]
        )
    )
    return mo.vstack(elements)


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
            f"- Operator Ready: `{_as_str(lifecycle.get('operator_ready'), default=False)}`",
            f"- Query Action Status: `{_as_str(lifecycle.get('query_action_status'), default='<unavailable>')}`",
            f"- Decision Review Ready: `{_as_str(lifecycle.get('decision_review_ready'), default=False)}`",
            f"- Audit / Replay Ready: `{_as_str(lifecycle.get('audit_replay_ready'), default=False)}`",
            f"- Lifecycle History: `{history_text}`",
            f"- Status Summary: {_as_str(lifecycle.get('status_summary'), default='<unavailable>')}",
            f"- Next Action: {_as_str(lifecycle.get('next_action'), default='<unavailable>')}",
        ]
    )


def _render_surface_section(
    key: str,
    panel: Mapping[str, object],
    *,
    query_action_control: Any | None = None,
) -> Any:
    if key == "session_header":
        contract = _as_str(panel.get("contract"))
        session_date = _as_str(panel.get("session_date"))
        return mo.md(f"## Session Header\n- Contract: `{contract}`\n- Session Date: `{session_date}`")

    if key == "pre_market_brief":
        setup_lines = _bullet_lines(panel.get("setup_summaries"))
        warning_lines = _bullet_lines(panel.get("warnings"))
        return mo.md(
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
        return mo.md("## Readiness Matrix\n" + ("\n".join(row_lines) if row_lines else "- unavailable"))

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
            return mo.md("\n".join(lines))

        flattened = _flatten_mapping_lines(snapshot)
        if flattened:
            lines.extend([f"  - `{field}`: `{value}`" for field, value in flattened])
        else:
            lines.append("  - <unavailable>")
        return mo.md("\n".join(lines))

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
        return mo.md("## Trigger Table\n" + ("\n".join(row_lines) if row_lines else "- unavailable"))

    if key == "query_action":
        lines = [
            "## Live Query",
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
        return mo.vstack(content)

    if key == "decision_review":
        if panel.get("has_result") is True:
            return mo.md(
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
        return mo.md(
            "\n".join(
                [
                    "## Decision Review",
                    f"- Ready: `{_as_str(panel.get('ready'), default=False)}`",
                    f"- Status: `{_as_str(panel.get('status'), default='NOT_READY')}`",
                    f"- Message: {_as_str(panel.get('message'), default='Decision Review is not ready yet.')}",
                ]
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
            return mo.md("\n".join(lines))

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
        return mo.md("\n".join(lines))

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
        return mo.md("\n".join(lines))

    return mo.md(f"## {key}\n- unavailable")


def _as_str(value: object, *, default: str = "<missing>") -> str:
    if value is None:
        return default
    return str(value)


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
            + f"mode={_as_str(item.get('runtime_mode'))}, "
            + f"contract={_as_str(item.get('contract'))}, "
            + f"session_date={_as_str(item.get('session_date'))}"
        )
    return "\n".join(lines) if lines else "  - <none>"
