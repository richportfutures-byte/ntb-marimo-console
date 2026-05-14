from __future__ import annotations

import json
from collections.abc import Mapping
from html import escape as _html_escape
from typing import Any

try:
    import marimo as mo
except ModuleNotFoundError:

    class _MissingMarimo:
        def __getattr__(self, name: str) -> object:
            raise RuntimeError("marimo is required to render Marimo UI surfaces.")

    mo = _MissingMarimo()

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

# ---------------------------------------------------------------------------
# Dark-theme CSS design system — injected once via _ntb_css_style_element()
# ---------------------------------------------------------------------------

_NTB_CSS = """
.marimo-cell-output:has(.ntb-shell),
.marimo-cell-output:has(.ntb-card),
.marimo-cell-output:has(.ntb-section),
.marimo-cell-output:has(.ntb-severity),
.marimo-cell-output:has(.ntb-ribbon) {
  background:#0b1220!important; color:#e2e8f0;
}
.ntb-shell{padding:0 4px;background:#0b1220;color:#e2e8f0}
.ntb-header{display:flex;align-items:center;gap:14px;padding:12px 16px;
  border:1px solid #334155;border-radius:10px;background:#0f172a}
.ntb-header__title{font-size:1.05em;font-weight:700;letter-spacing:-0.01em;color:#e2e8f0}
.ntb-header__subtitle{color:#94a3b8;font-size:0.78em;margin-top:2px}
.ntb-header__pills{margin-left:auto;display:flex;gap:8px;
  align-items:center;flex-wrap:wrap;justify-content:flex-end}
.ntb-pill{display:inline-flex;align-items:center;gap:6px;
  background:#1e293b;color:#e2e8f0;border:1px solid #334155;
  padding:4px 10px;border-radius:6px;font-size:0.8em;font-weight:500}
.ntb-pill__label{color:#94a3b8;font-size:0.72em;text-transform:uppercase;
  letter-spacing:0.06em;font-weight:600}
.ntb-pill__value{font-weight:700;font-variant-numeric:tabular-nums}
.ntb-section{margin:18px 0 6px;padding:0 4px;
  display:flex;align-items:center;gap:10px}
.ntb-section__title{font-size:0.78em;font-weight:700;letter-spacing:0.1em;
  text-transform:uppercase;color:#cbd5e1;white-space:nowrap}
.ntb-section__rule{flex:1;height:1px;background:#334155}
.ntb-card{background:#1e293b;color:#e2e8f0;
  border:1px solid #334155;border-radius:10px;padding:14px;margin:6px 0}
.ntb-grid-2{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.ntb-grid-3{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}
.ntb-grid-4{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:8px}
.ntb-stat{background:#1e293b;border-radius:8px;padding:10px;
  border:1px solid #334155}
.ntb-stat__label{color:#94a3b8;font-size:0.72em;text-transform:uppercase;
  letter-spacing:0.06em;font-weight:600}
.ntb-stat__value{margin-top:4px;color:#e2e8f0;font-size:0.95em;
  font-variant-numeric:tabular-nums}
.ntb-severity{display:flex;align-items:center;gap:14px;
  padding:14px 16px;border-radius:10px;border:1px solid;margin-bottom:10px}
.ntb-severity__badge{font-weight:800;font-size:0.78em;letter-spacing:0.1em;
  text-transform:uppercase;padding:4px 10px;border-radius:6px;color:#0b1220}
.ntb-severity__title{font-size:1em;font-weight:700;color:#e2e8f0}
.ntb-severity__subtitle{color:#94a3b8;font-size:0.85em;margin-top:2px}
.ntb-severity--ready{border-color:#1f5132;background:rgba(34,197,94,0.07)}
.ntb-severity--caution{border-color:#7a5b15;background:rgba(250,204,21,0.07)}
.ntb-severity--blocked{border-color:#7f1d1d;background:rgba(239,68,68,0.08)}
.ntb-chip{display:inline-flex;align-items:center;padding:3px 9px;
  border-radius:14px;font-size:0.78em;font-weight:600;border:1px solid;
  margin:2px 4px 2px 0;font-variant-numeric:tabular-nums}
.ntb-chip--ready{color:#86efac;border-color:#1f5132;background:rgba(34,197,94,0.07)}
.ntb-chip--blocked{color:#fca5a5;border-color:#7f1d1d;background:rgba(239,68,68,0.07)}
.ntb-chip--caution{color:#fde68a;border-color:#7a5b15;background:rgba(250,204,21,0.07)}
.ntb-chip--info{color:#93c5fd;border-color:#1e3a5f;background:rgba(59,130,246,0.07)}
.ntb-ribbon{padding:6px 12px;border-radius:6px;font-size:0.78em;
  color:#94a3b8;background:#0b1220;border:1px dashed #334155;margin:8px 0 14px}
.ntb-callout{background:rgba(99,102,241,0.07);border-left:3px solid #818cf8;
  border-radius:8px;padding:14px;margin-bottom:12px}
.ntb-list{margin:6px 0 0;padding:0;list-style:none}
.ntb-list li{padding:5px 0;color:#cbd5e1;border-top:1px dashed #334155}
.ntb-list li:first-child{border-top:none}
.ntb-muted{color:#94a3b8;font-size:0.85em}
.ntb-table{width:100%;border-collapse:collapse;font-size:0.84em}
.ntb-table th{text-align:left;color:#94a3b8;font-weight:600;padding:6px 8px;
  border-bottom:1px solid #334155}
.ntb-table td{padding:6px 8px;border-top:1px solid #1e293b;color:#cbd5e1}
"""


def _ntb_css_style_element() -> Any:
    """Return a marimo Html element that injects the NTB dark-theme CSS."""
    return mo.Html(f"<style>{_NTB_CSS}</style>")


# ---------------------------------------------------------------------------
# HTML builder helpers
# ---------------------------------------------------------------------------


def _h(value: object) -> str:
    """HTML-escape a value for safe embedding."""
    return _html_escape(str(value)) if value is not None else ""


def _ntb_pill(label: str, value: str, *, color: str | None = None) -> str:
    """Render a header pill badge."""
    style = f' style="color:{color}"' if color else ""
    return (
        '<span class="ntb-pill">'
        f'<span class="ntb-pill__label">{_h(label)}</span>'
        f'<span class="ntb-pill__value"{style}>{_h(value)}</span>'
        "</span>"
    )


def _ntb_chip(value: str, kind: str = "info") -> str:
    """Render a colored inline chip badge."""
    return f'<span class="ntb-chip ntb-chip--{kind}">{_h(value)}</span>'


def _ntb_chip_for_status(value: str) -> str:
    """Auto-select chip color based on common status values."""
    v = str(value).lower()
    if v in (
        "true",
        "ready",
        "pass",
        "enabled",
        "available",
        "fresh",
        "valid",
        "healthy",
        "final_supported",
        "inactive",
        "clear",
    ):
        return _ntb_chip(value, "ready")
    if v in (
        "false",
        "blocked",
        "disabled",
        "fail",
        "not_ready",
        "unavailable",
        "stale",
        "error",
        "not_queried",
    ):
        return _ntb_chip(value, "blocked")
    if v in ("touched", "caution", "degraded", "warn", "warning"):
        return _ntb_chip(value, "caution")
    return _ntb_chip(value, "info")


def _ntb_severity_banner(
    status: str,
    title: str,
    subtitle: str,
    *,
    tier: str | None = None,
) -> str:
    """Render a colored severity banner."""
    if tier is None:
        sl = status.lower()
        if sl in ("ready", "pass", "enabled", "healthy", "ok"):
            tier = "ready"
        elif sl in ("blocked", "disabled", "fail", "error", "not_ready"):
            tier = "blocked"
        else:
            tier = "caution"
    badge_colors = {"ready": "#22c55e", "caution": "#facc15", "blocked": "#ef4444"}
    badge_bg = badge_colors.get(tier, "#94a3b8")
    return (
        f'<div class="ntb-severity ntb-severity--{tier}">'
        f'<span class="ntb-severity__badge" style="background:{badge_bg}">'
        f"{_h(status)}</span>"
        "<div>"
        f'<div class="ntb-severity__title">{_h(title)}</div>'
        f'<div class="ntb-severity__subtitle">{_h(subtitle)}</div>'
        "</div></div>"
    )


def _ntb_stat_card(
    label: str, value: str, *, chip: bool = False, note: str | None = None
) -> str:
    """Render a single stat card for use inside a grid."""
    if chip:
        val_html = _ntb_chip_for_status(value)
    else:
        val_html = _h(value)
    note_html = (
        f'<div class="ntb-muted" style="margin-top:6px">{_h(note)}</div>'
        if note
        else ""
    )
    return (
        '<div class="ntb-stat">'
        f'<div class="ntb-stat__label">{_h(label)}</div>'
        f'<div class="ntb-stat__value">{val_html}</div>'
        f"{note_html}"
        "</div>"
    )


def _ntb_section_divider(title: str) -> str:
    """Render an uppercase section title with a horizontal rule."""
    return (
        '<div class="ntb-section">'
        f'<div class="ntb-section__title">{_h(title)}</div>'
        '<div class="ntb-section__rule"></div>'
        "</div>"
    )


def _ntb_ribbon(text: str) -> str:
    """Render a dashed-border boundary disclaimer."""
    return f'<div class="ntb-ribbon">{_h(text)}</div>'


def _ntb_list_html(items: list[str]) -> str:
    """Render a styled list."""
    if not items:
        return '<span class="ntb-muted">&lt;none&gt;</span>'
    li = "".join(f"<li>{_h(item)}</li>" for item in items)
    return f'<ul class="ntb-list">{li}</ul>'


# ---------------------------------------------------------------------------
# Style dicts — updated for dark theme
# ---------------------------------------------------------------------------

_CONSOLE_STACK_STYLE = {
    "gap": "14px",
    "padding": "12px",
    "background": "#0b1220",
}

_HEADER_STYLE: dict[str, str] = {}  # header now uses HTML classes

_CARD_STYLE = {
    "border": "1px solid #334155",
    "borderRadius": "10px",
    "padding": "14px",
    "background": "#1e293b",
    "color": "#e2e8f0",
}

_CONTROL_CARD_STYLE = {
    "border": "1px solid #334155",
    "borderRadius": "10px",
    "padding": "12px",
    "background": "#1e293b",
    "color": "#e2e8f0",
}

_DEBUG_CARD_STYLE = {
    "border": "1px dashed #334155",
    "borderRadius": "8px",
    "padding": "10px 12px",
    "background": "#0f172a",
    "color": "#94a3b8",
    "opacity": "0.86",
}


def build_primary_cockpit_plan(shell: Mapping[str, object]) -> dict[str, object]:
    """Return the primary operator cockpit plan from the fixture cockpit overview surface.

    This is the testable anchor for the first-position landing surface.  The
    returned dict is plain Python (no Marimo objects) so tests can assert on
    it without needing a Marimo runtime.

    Keys
    ----
    present        – True when the surface is available and populated
    position       – "primary" when present; "unavailable" otherwise
    key            – always "fixture_cockpit_overview"
    mode           – surface mode string (e.g. "fixture_dry_run_non_live")
    live_credentials_required – bool
    default_launch_live       – bool
    decision_authority        – str
    supported_contracts       – list[str]
    rows                      – list of per-contract row dicts
    """
    surfaces_raw = shell.get("surfaces")
    if not isinstance(surfaces_raw, Mapping):
        return {
            "present": False,
            "position": "unavailable",
            "key": "fixture_cockpit_overview",
            "mode": None,
            "live_credentials_required": None,
            "default_launch_live": None,
            "decision_authority": None,
            "supported_contracts": [],
            "rows": [],
        }
    surface = surfaces_raw.get("fixture_cockpit_overview")
    if not isinstance(surface, Mapping):
        return {
            "present": False,
            "position": "unavailable",
            "key": "fixture_cockpit_overview",
            "mode": None,
            "live_credentials_required": None,
            "default_launch_live": None,
            "decision_authority": None,
            "supported_contracts": [],
            "rows": [],
        }
    return {
        "present": True,
        "position": "primary",
        "key": "fixture_cockpit_overview",
        "mode": surface.get("mode"),
        "live_credentials_required": surface.get("live_credentials_required"),
        "default_launch_live": surface.get("default_launch_live"),
        "decision_authority": surface.get("decision_authority"),
        "supported_contracts": list(surface.get("supported_contracts") or []),
        "rows": list(surface.get("rows") or []),
    }


def build_phase1_render_plan(shell: Mapping[str, object]) -> dict[str, object]:
    warnings: list[str] = []

    title = _as_str(shell.get("title"), default="NTB Marimo Console")
    surfaces_raw = shell.get("surfaces")
    surfaces: dict[str, object] = {}
    if isinstance(surfaces_raw, Mapping):
        surfaces = dict(surfaces_raw)
    else:
        warnings.append(
            "Missing or invalid shell.surfaces; rendering fail-closed placeholders."
        )

    rendered_sections: list[dict[str, object]] = []
    for key in FROZEN_SURFACE_KEYS:
        value = surfaces.get(key)
        if key == "five_contract_readiness_summary" and not isinstance(value, Mapping):
            value = _build_five_contract_readiness_summary_fallback(shell)
        if not isinstance(value, Mapping):
            warnings.append(f"Missing or invalid surface: {key}")
            rendered_sections.append(
                {"key": key, "panel": {"surface": key, "warning": "unavailable"}}
            )
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
    active_trade_control_panel: Any | None = None,
    anchor_input_control_panel: Any | None = None,
    operator_notes_control_panel: Any | None = None,
    premarket_brief_control_panel: Any | None = None,
) -> Any:
    plan = build_phase1_render_plan(shell)
    startup = shell.get("startup")
    operator_ready = True
    if isinstance(startup, Mapping):
        operator_ready = startup.get("operator_ready") is True

    elements: list[Any] = [
        _ntb_css_style_element(),
        _render_console_header(shell, heading=heading, mode_summary=mode_summary),
    ]

    # PRIMARY LANDING SURFACE — fixture cockpit renders immediately after the header,
    # before pre-market brief, stream health, anchors, notes, and all metadata sections.
    surfaces_raw = shell.get("surfaces")
    if isinstance(surfaces_raw, Mapping):
        fixture_cockpit_surface = surfaces_raw.get("fixture_cockpit_overview")
        if operator_ready and isinstance(fixture_cockpit_surface, Mapping):
            elements.append(_render_fixture_cockpit_primary(fixture_cockpit_surface))

    elements.append(
        render_premarket_brief_panel(shell, control_panel=premarket_brief_control_panel)
    )

    stream_health_panel = render_stream_health_panel(shell)
    if stream_health_panel is not None:
        elements.append(stream_health_panel)

    elements.append(
        render_anchor_inputs_panel(shell, control_panel=anchor_input_control_panel)
    )
    elements.append(
        render_operator_notes_panel(shell, control_panel=operator_notes_control_panel)
    )

    active_trades_panel = render_active_trades_panel(
        shell, control_panel=active_trade_control_panel
    )
    if active_trades_panel is not None:
        elements.append(active_trades_panel)

    cockpit = shell.get("r14_cockpit")
    if operator_ready and isinstance(cockpit, Mapping):
        elements.append(render_r14_cockpit_shell(cockpit))

    if isinstance(startup, Mapping):
        elements.append(_render_startup_status_html(startup))
        if profile_control_panel is not None:
            elements.append(_render_control_card(profile_control_panel))
        elements.append(
            mo.accordion(
                {
                    "Supported Profile Operations": _render_markdown_card(
                        build_profile_operations_markdown(startup)
                    )
                }
            )
        )

    runtime = shell.get("runtime")
    if isinstance(runtime, Mapping):
        elements.append(
            mo.accordion(
                {
                    "Runtime Identity": _render_markdown_card(
                        build_runtime_identity_markdown(runtime)
                    )
                }
            )
        )

    lifecycle = shell.get("lifecycle")
    if isinstance(lifecycle, Mapping):
        elements.append(_render_session_lifecycle_html(lifecycle))
        if lifecycle_control_panel is not None:
            elements.append(_render_control_card(lifecycle_control_panel))

    evidence = shell.get("evidence")
    if isinstance(evidence, Mapping):
        elements.append(_render_session_evidence_html(evidence))
        if evidence_control_panel is not None:
            elements.append(_render_control_card(evidence_control_panel))

    workflow = shell.get("workflow")
    if isinstance(workflow, Mapping):
        elements.append(_render_session_workflow_html(workflow))

    if operator_ready:
        for warning in plan["warnings"]:
            elements.append(
                mo.Html(
                    '<div class="ntb-severity ntb-severity--caution" style="margin:6px 0">'
                    '<span class="ntb-severity__badge" style="background:#facc15">WARNING</span>'
                    f'<div><div class="ntb-severity__title">{_h(warning)}</div></div></div>'
                )
            )

        for section in plan["sections"]:
            key = _as_str(section.get("key"), default="unknown")
            if key == "pre_market_brief":
                continue
            panel_raw = section.get("panel")
            panel = (
                panel_raw
                if isinstance(panel_raw, Mapping)
                else {"warning": "unavailable"}
            )
            elements.append(
                _render_surface_section(
                    key, panel, query_action_control=query_action_control
                )
            )
    else:
        elements.append(
            mo.Html(
                _ntb_severity_banner(
                    "BLOCKED",
                    "Operator Surfaces Blocked",
                    "Blocked until startup preflight passes and runtime assembly completes. "
                    "Fix the reported startup diagnostics, then relaunch the console.",
                    tier="blocked",
                )
            )
        )

    elements.append(
        _render_debug_secondary(_as_str(plan["debug"].get("shell_json"), default="{}"))
    )
    return mo.vstack(elements, gap=0.75).style(_CONSOLE_STACK_STYLE)


def render_watchman_gate_stop_output(
    shell: Mapping[str, object],
    *,
    heading: str,
    mode_summary: str,
    lifecycle_control_panel: Any | None = None,
    profile_control_panel: Any | None = None,
    evidence_control_panel: Any | None = None,
    active_trade_control_panel: Any | None = None,
    anchor_input_control_panel: Any | None = None,
    operator_notes_control_panel: Any | None = None,
    premarket_brief_control_panel: Any | None = None,
) -> Any | None:
    if not watchman_gate_requires_stop(shell):
        return None

    elements: list[Any] = [
        _ntb_css_style_element(),
        _render_console_header(shell, heading=heading, mode_summary=mode_summary),
    ]
    elements.append(
        render_premarket_brief_panel(shell, control_panel=premarket_brief_control_panel)
    )

    startup = shell.get("startup")
    if isinstance(startup, Mapping):
        elements.append(_render_markdown_card(build_startup_status_markdown(startup)))
        elements.append(
            _render_markdown_card(build_profile_operations_markdown(startup))
        )
        if profile_control_panel is not None:
            elements.append(_render_control_card(profile_control_panel))

    runtime = shell.get("runtime")
    if isinstance(runtime, Mapping):
        elements.append(_render_markdown_card(build_runtime_identity_markdown(runtime)))

    lifecycle = shell.get("lifecycle")
    if isinstance(lifecycle, Mapping):
        elements.append(
            _render_markdown_card(build_session_lifecycle_markdown(lifecycle))
        )
        if lifecycle_control_panel is not None:
            elements.append(_render_control_card(lifecycle_control_panel))

    evidence = shell.get("evidence")
    if isinstance(evidence, Mapping):
        elements.append(
            _render_markdown_card(build_session_evidence_markdown(evidence))
        )
        if evidence_control_panel is not None:
            elements.append(_render_control_card(evidence_control_panel))

    workflow = shell.get("workflow")
    if isinstance(workflow, Mapping):
        elements.append(
            _render_markdown_card(build_session_workflow_markdown(workflow))
        )

    elements.append(
        render_anchor_inputs_panel(shell, control_panel=anchor_input_control_panel)
    )
    elements.append(
        render_operator_notes_panel(shell, control_panel=operator_notes_control_panel)
    )

    surfaces = shell.get("surfaces")
    if isinstance(surfaces, Mapping):
        session_header = surfaces.get("session_header")
        if isinstance(session_header, Mapping):
            elements.append(_render_surface_section("session_header", session_header))
        readiness_matrix = surfaces.get("readiness_matrix")
        if isinstance(readiness_matrix, Mapping):
            elements.append(
                _render_surface_section("readiness_matrix", readiness_matrix)
            )

    gate = shell.get("watchman_gate")
    if isinstance(gate, Mapping):
        elements.append(_render_markdown_card(build_watchman_gate_markdown(gate)))

    elements.append(_render_debug_secondary(json.dumps(dict(shell), indent=2)))
    return mo.vstack(elements, gap=0.75).style(_CONSOLE_STACK_STYLE)


# ---------------------------------------------------------------------------
# HTML section builders (Phase 2 conversions)
# ---------------------------------------------------------------------------


def _render_startup_status_html(startup: Mapping[str, object]) -> Any:
    """Render Startup Status as an HTML card with stat grid and chips."""
    readiness = _as_str(startup.get("readiness_state"), default="<unavailable>")
    operator_ready = startup.get("operator_ready") is True
    tier = "ready" if operator_ready else "blocked"
    title = (
        "Startup preflight passed" if operator_ready else "Startup preflight incomplete"
    )
    subtitle = _as_str(startup.get("status_summary"), default="")

    stats = '<div class="ntb-grid-3">'
    stats += _ntb_stat_card(
        "App Identity", _as_str(startup.get("app_name"), default="NTB Marimo Console")
    )
    stats += _ntb_stat_card(
        "Selected Profile",
        _as_str(startup.get("selected_profile_id"), default="<unresolved>"),
    )
    stats += _ntb_stat_card(
        "Contract", _as_str(startup.get("contract"), default="<unresolved>")
    )
    stats += _ntb_stat_card(
        "Runtime Mode",
        _as_str(startup.get("runtime_mode_label"), default="<unavailable>"),
    )
    stats += _ntb_stat_card(
        "Running As", _as_str(startup.get("running_as"), default="<unavailable>")
    )
    stats += _ntb_stat_card(
        "Session Date", _as_str(startup.get("session_date"), default="<unresolved>")
    )
    stats += _ntb_stat_card(
        "Preflight",
        _as_str(startup.get("preflight_status"), default="<unavailable>"),
        chip=True,
    )
    stats += _ntb_stat_card("Readiness", readiness, chip=True)
    stats += _ntb_stat_card(
        "Operator Ready",
        _as_str(startup.get("operator_ready"), default="False"),
        chip=True,
    )
    stats += _ntb_stat_card(
        "Session State",
        _as_str(startup.get("current_session_state"), default="NOT_ASSEMBLED"),
        chip=True,
    )
    stats += "</div>"

    readiness_history = startup.get("readiness_history")
    history_text = "<unavailable>"
    if isinstance(readiness_history, list):
        history_text = (
            " → ".join(_as_str(item) for item in readiness_history)
            if readiness_history
            else "<none>"
        )

    detail_html = (
        '<div class="ntb-muted" style="margin-top:10px">'
        f"<strong>Startup Path:</strong> {_h(history_text)}"
        "</div>"
        '<div class="ntb-muted" style="margin-top:4px">'
        f"<strong>Next Action:</strong> {_h(_as_str(startup.get('next_action'), default='<unavailable>'))}"
        "</div>"
    )

    blocking_html = ""
    blocking_checks = startup.get("blocking_checks")
    if isinstance(blocking_checks, list) and blocking_checks:
        items = []
        for check in blocking_checks:
            if not isinstance(check, Mapping):
                continue
            cat = _as_str(check.get("category"), default="unknown")
            summary = _as_str(check.get("summary"), default="<unavailable>")
            remedy = _as_str(check.get("remedy"), default="<unavailable>")
            items.append(f"[{cat}] {summary} — Remedy: {remedy}")
        if items:
            blocking_html = (
                '<div style="margin-top:10px">'
                '<div class="ntb-stat__label" style="color:#ef4444">Blocking Diagnostics</div>'
                + _ntb_list_html(items)
                + "</div>"
            )

    full_html = (
        _ntb_section_divider("Startup Status")
        + '<div class="ntb-card">'
        + _ntb_severity_banner(
            _as_str(startup.get("preflight_status"), default="INCOMPLETE"),
            title,
            subtitle,
            tier=tier,
        )
        + stats
        + detail_html
        + blocking_html
        + "</div>"
    )
    return mo.Html(full_html)


def _render_session_lifecycle_html(lifecycle: Mapping[str, object]) -> Any:
    """Render Session Lifecycle as an HTML card."""
    current_state = _as_str(
        lifecycle.get("current_lifecycle_state"), default="<unavailable>"
    )
    session_state = _as_str(
        lifecycle.get("current_session_state"), default="<unavailable>"
    )
    last_action = _as_str(lifecycle.get("last_action"), default="<unavailable>")

    stats = '<div class="ntb-grid-3">'
    stats += _ntb_stat_card("Lifecycle State", current_state, chip=True)
    stats += _ntb_stat_card("Session State", session_state, chip=True)
    stats += _ntb_stat_card("Last Action", last_action)
    stats += _ntb_stat_card(
        "Reload Result",
        _as_str(lifecycle.get("reload_result"), default="<unavailable>"),
        chip=True,
    )
    stats += _ntb_stat_card(
        "Operator Ready",
        _as_str(lifecycle.get("operator_ready"), default="False"),
        chip=True,
    )
    stats += _ntb_stat_card(
        "Query Action",
        _as_str(lifecycle.get("query_action_status"), default="<unavailable>"),
        chip=True,
    )
    stats += _ntb_stat_card(
        "Reset Available",
        _as_str(lifecycle.get("reset_available"), default="False"),
        chip=True,
    )
    stats += _ntb_stat_card(
        "Reload Available",
        _as_str(lifecycle.get("reload_available"), default="False"),
        chip=True,
    )
    stats += _ntb_stat_card(
        "Profile Switch",
        _as_str(lifecycle.get("profile_switch_available"), default="False"),
        chip=True,
    )
    stats += "</div>"

    detail_html = (
        '<div class="ntb-muted" style="margin-top:10px">'
        f"<strong>Live Runtime Mode:</strong> {_h(_as_str(lifecycle.get('operator_live_runtime_mode'), default='SAFE_NON_LIVE'))}"
        "</div>"
        '<div class="ntb-muted" style="margin-top:4px">'
        f"<strong>Status Summary:</strong> {_h(_as_str(lifecycle.get('status_summary'), default='<unavailable>'))}"
        "</div>"
        '<div class="ntb-muted" style="margin-top:4px">'
        f"<strong>Next Action:</strong> {_h(_as_str(lifecycle.get('next_action'), default='<unavailable>'))}"
        "</div>"
    )

    full_html = (
        _ntb_section_divider("Session Lifecycle")
        + '<div class="ntb-card">'
        + stats
        + detail_html
        + "</div>"
    )
    return mo.Html(full_html)


def _render_session_workflow_html(workflow: Mapping[str, object]) -> Any:
    """Render Session Workflow as an HTML card."""
    current = _as_str(workflow.get("current_state"), default="<unavailable>")
    watchman = _as_str(workflow.get("watchman_gate_status"), default="<unavailable>")
    live_query = _as_str(workflow.get("live_query_status"), default="<unavailable>")

    stats = '<div class="ntb-grid-3">'
    stats += _ntb_stat_card("Current State", current, chip=True)
    stats += _ntb_stat_card("Watchman Gate", watchman, chip=True)
    stats += _ntb_stat_card("Live Query", live_query, chip=True)
    stats += _ntb_stat_card(
        "Query Action",
        _as_str(workflow.get("query_action_status"), default="<unavailable>"),
        chip=True,
    )
    stats += _ntb_stat_card(
        "Query Available",
        _as_str(workflow.get("query_action_available"), default="False"),
        chip=True,
    )
    stats += _ntb_stat_card(
        "Decision Review",
        _as_str(workflow.get("decision_review_ready"), default="False"),
        chip=True,
    )
    stats += _ntb_stat_card(
        "Audit/Replay",
        _as_str(workflow.get("audit_replay_ready"), default="False"),
        chip=True,
    )
    stats += "</div>"

    history = workflow.get("state_history")
    history_text = "<unavailable>"
    if isinstance(history, list):
        history_text = (
            " → ".join(_as_str(item) for item in history) if history else "<none>"
        )

    detail_html = (
        '<div class="ntb-muted" style="margin-top:10px">'
        f"<strong>Workflow History:</strong> {_h(history_text)}"
        "</div>"
        '<div class="ntb-muted" style="margin-top:4px">'
        f"<strong>Status Summary:</strong> {_h(_as_str(workflow.get('status_summary'), default='<unavailable>'))}"
        "</div>"
        '<div class="ntb-muted" style="margin-top:4px">'
        f"<strong>Next Action:</strong> {_h(_as_str(workflow.get('next_action'), default='<unavailable>'))}"
        "</div>"
    )

    blocked_html = ""
    blocked_reasons = workflow.get("blocked_reasons")
    if isinstance(blocked_reasons, list) and blocked_reasons:
        items = [_as_str(r) for r in blocked_reasons]
        blocked_html = (
            '<div style="margin-top:10px">'
            '<div class="ntb-stat__label" style="color:#ef4444">Blocked Reasons</div>'
            + _ntb_list_html(items)
            + "</div>"
        )

    error_html = ""
    error_message = workflow.get("error_message")
    if error_message is not None:
        error_html = (
            '<div class="ntb-severity ntb-severity--blocked" style="margin-top:10px">'
            '<span class="ntb-severity__badge" style="background:#ef4444">ERROR</span>'
            f'<div><div class="ntb-severity__title">{_h(_as_str(error_message))}</div></div></div>'
        )

    full_html = (
        _ntb_section_divider("Session Workflow")
        + '<div class="ntb-card">'
        + stats
        + detail_html
        + blocked_html
        + error_html
        + "</div>"
    )
    return mo.Html(full_html)


def _render_session_evidence_html(evidence: Mapping[str, object]) -> Any:
    """Render Session Evidence as an HTML card."""
    persistence_health = _as_str(
        evidence.get("persistence_health_status"), default="<unavailable>"
    )
    tier = "ready" if persistence_health.lower() in ("healthy", "ok") else "caution"

    stats = '<div class="ntb-grid-3">'
    stats += _ntb_stat_card("Persistence Health", persistence_health, chip=True)
    stats += _ntb_stat_card(
        "Current Session Events",
        _as_str(evidence.get("current_session_record_count"), default="0"),
    )
    stats += _ntb_stat_card(
        "Restored Prior-Run",
        _as_str(evidence.get("restored_record_count"), default="0"),
    )
    stats += _ntb_stat_card(
        "Active Profile",
        _as_str(evidence.get("active_profile_id"), default="<unavailable>"),
    )
    stats += _ntb_stat_card(
        "Restore Status",
        _as_str(evidence.get("restore_status"), default="<unavailable>"),
        chip=True,
    )
    stats += _ntb_stat_card(
        "Last Persistence",
        _as_str(evidence.get("last_persistence_status"), default="<unavailable>"),
        chip=True,
    )
    stats += "</div>"

    recent_profiles = evidence.get("recent_profiles")
    recent_profiles_text = "<none>"
    if isinstance(recent_profiles, list):
        recent_profiles_text = (
            ", ".join(_as_str(item) for item in recent_profiles)
            if recent_profiles
            else "<none>"
        )

    detail_html = (
        '<div class="ntb-muted" style="margin-top:10px">'
        f"<strong>Recent Profiles:</strong> {_h(recent_profiles_text)}"
        "</div>"
        '<div class="ntb-muted" style="margin-top:4px">'
        f"<strong>Status Summary:</strong> {_h(_as_str(evidence.get('status_summary'), default='<unavailable>'))}"
        "</div>"
    )

    # Last known outcomes table
    outcomes_html = ""
    last_known_outcomes = evidence.get("last_known_outcomes")
    if isinstance(last_known_outcomes, list) and last_known_outcomes:
        rows = ""
        for outcome in last_known_outcomes:
            if not isinstance(outcome, Mapping):
                continue
            profile = _h(_as_str(outcome.get("profile_id")))
            if outcome.get("has_recent_evidence") is not True:
                summary = _h(
                    _as_str(
                        outcome.get("status_summary"),
                        default=NO_RECENT_SESSION_EVIDENCE,
                    )
                )
                rows += f'<tr><td>{profile}</td><td colspan="3">{summary}</td></tr>'
            else:
                rows += (
                    f"<tr><td>{profile}</td>"
                    f"<td>#{_h(_as_str(outcome.get('event_index')))}</td>"
                    f"<td>{_h(_as_str(outcome.get('source_label'), default=outcome.get('source_scope')))}</td>"
                    f"<td>{_ntb_chip_for_status(_as_str(outcome.get('last_action'), default='<unavailable>'))}</td>"
                    f"</tr>"
                )
        if rows:
            outcomes_html = (
                '<div style="margin-top:12px">'
                '<div class="ntb-stat__label" style="margin-bottom:6px">Last Known Outcome By Profile</div>'
                '<div style="overflow-x:auto">'
                '<table class="ntb-table"><thead><tr>'
                "<th>Profile</th><th>Event</th><th>Source</th><th>Action</th>"
                "</tr></thead><tbody>" + rows + "</tbody></table></div></div>"
            )

    # Recent activity
    activity_html = ""
    recent_activity = evidence.get("recent_activity")
    if isinstance(recent_activity, list) and recent_activity:
        items = []
        for item in recent_activity:
            if not isinstance(item, Mapping):
                continue
            idx = _as_str(item.get("event_index"))
            source = _as_str(item.get("source_label"), default=item.get("source_scope"))
            ts = _as_str(item.get("recorded_at_utc"))
            profile = _as_str(item.get("active_profile_id"))
            summary = _as_str(item.get("summary"), default="<unavailable>")
            items.append(f"#{idx} [{source}] at {ts} {profile}: {summary}")
        if items:
            activity_html = (
                '<div style="margin-top:10px">'
                '<div class="ntb-stat__label" style="margin-bottom:4px">Recent Activity</div>'
                + _ntb_list_html(items)
                + "</div>"
            )

    full_html = (
        _ntb_section_divider("Recent Session Evidence")
        + '<div class="ntb-card">'
        + _ntb_severity_banner(
            persistence_health,
            "Evidence Persistence",
            _as_str(evidence.get("restore_status_summary"), default=""),
            tier=tier,
        )
        + stats
        + detail_html
        + outcomes_html
        + activity_html
        + "</div>"
    )
    return mo.Html(full_html)


def build_startup_status_markdown(startup: Mapping[str, object]) -> str:
    profile_lines = _supported_profile_lines(startup.get("supported_profiles"))
    readiness_history = startup.get("readiness_history")
    readiness_path = "<unavailable>"
    if isinstance(readiness_history, list):
        readiness_path = (
            " -> ".join(_as_str(item) for item in readiness_history)
            if readiness_history
            else "<none>"
        )

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
                "    Remedy: " + _as_str(check.get("remedy"), default="<unavailable>")
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
        history_text = (
            " -> ".join(_as_str(item) for item in state_history)
            if state_history
            else "<none>"
        )

    startup_history = runtime.get("startup_state_history")
    startup_text = "<unavailable>"
    if isinstance(startup_history, list):
        startup_text = (
            " -> ".join(_as_str(item) for item in startup_history)
            if startup_history
            else "<none>"
        )

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
            f"- Operator Live Runtime Mode: `{_as_str(runtime.get('operator_live_runtime_mode'), default='SAFE_NON_LIVE')}`",
            f"- Operator Live Runtime Status: `{_as_str(runtime.get('operator_live_runtime_status'), default='SAFE_NON_LIVE')}`",
            f"- Operator Live Runtime Source: `{_as_str(runtime.get('operator_live_runtime_source'), default='fixture_preserved_shell')}`",
            f"- Operator Live Runtime Cache Derived: `{_as_str(runtime.get('operator_live_runtime_cache_derived'), default=False)}`",
            f"- Operator Live Runtime Refresh Floor Seconds: `{_as_str(runtime.get('operator_live_runtime_refresh_floor_seconds'), default=15.0)}`",
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
        history_text = (
            " -> ".join(_as_str(item) for item in history) if history else "<none>"
        )

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
        history_text = (
            " -> ".join(_as_str(item) for item in history) if history else "<none>"
        )

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
            f"- Operator Live Runtime Mode: `{_as_str(lifecycle.get('operator_live_runtime_mode'), default='SAFE_NON_LIVE')}`",
            f"- Operator Live Runtime Status: `{_as_str(lifecycle.get('operator_live_runtime_status'), default='SAFE_NON_LIVE')}`",
            f"- Operator Live Runtime Source: `{_as_str(lifecycle.get('operator_live_runtime_source'), default='fixture_preserved_shell')}`",
            f"- Operator Live Runtime Cache Derived: `{_as_str(lifecycle.get('operator_live_runtime_cache_derived'), default=False)}`",
            f"- Operator Live Runtime Refresh Floor Seconds: `{_as_str(lifecycle.get('operator_live_runtime_refresh_floor_seconds'), default=15.0)}`",
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
        recent_profiles_text = (
            ", ".join(_as_str(item) for item in recent_profiles)
            if recent_profiles
            else "<none>"
        )

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
                    + _as_str(
                        outcome.get("status_summary"),
                        default=NO_RECENT_SESSION_EVIDENCE,
                    )
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


def render_stream_health_panel(shell: Mapping[str, object]) -> Any | None:
    runtime = shell.get("runtime")
    runtime_map = runtime if isinstance(runtime, Mapping) else {}
    mode = _as_str(
        runtime_map.get("operator_live_runtime_mode"), default="SAFE_NON_LIVE"
    )
    if mode != "OPERATOR_LIVE_RUNTIME":
        return None
    health = shell.get("stream_health")
    if not isinstance(health, Mapping):
        health = {
            "connection_state": "unavailable",
            "token_status": "unavailable",
            "token_expires_in_seconds": None,
            "reconnect_attempts": 0,
            "reconnect_active": False,
            "per_contract_status": {},
            "stale_contracts": [],
            "blocking_reasons": runtime_map.get(
                "operator_live_runtime_blocking_reasons", []
            ),
            "overall_health": "unavailable",
        }
    return _render_markdown_card(build_stream_health_markdown(health))


def render_active_trades_panel(
    shell: Mapping[str, object],
    *,
    control_panel: Any | None = None,
) -> Any | None:
    runtime = shell.get("runtime")
    runtime_map = runtime if isinstance(runtime, Mapping) else {}
    mode = _as_str(
        runtime_map.get("operator_live_runtime_mode"), default="SAFE_NON_LIVE"
    )
    if mode != "OPERATOR_LIVE_RUNTIME":
        return None

    content: list[Any] = []
    active_trades = shell.get("active_trades")
    if isinstance(active_trades, Mapping):
        content.append(mo.md(build_active_trades_markdown(active_trades)))
    else:
        content.append(
            mo.md(
                build_active_trades_markdown(
                    {
                        "status": "unavailable",
                        "rows": [],
                        "message": "Active-trade registry is unavailable for this app session.",
                    }
                )
            )
        )
    if control_panel is not None:
        content.append(control_panel)
    return _render_surface_card(mo.vstack(content, gap=0.65))


def render_anchor_inputs_panel(
    shell: Mapping[str, object],
    *,
    control_panel: Any | None = None,
) -> Any:
    content: list[Any] = []
    anchor_inputs = shell.get("anchor_inputs")
    if not isinstance(anchor_inputs, Mapping):
        anchor_inputs = {
            "status": "not_configured",
            "rows": [],
            "message": "Operator anchor inputs are available as session context and are not a decision authority.",
            "integration_status": "operator_context_available_not_gate_enforced",
        }
    content.append(mo.md(build_anchor_inputs_markdown(anchor_inputs)))
    if control_panel is not None:
        content.append(control_panel)
    return _render_surface_card(mo.vstack(content, gap=0.65))


def render_operator_notes_panel(
    shell: Mapping[str, object],
    *,
    control_panel: Any | None = None,
) -> Any:
    content: list[Any] = []
    operator_notes = shell.get("operator_notes")
    if not isinstance(operator_notes, Mapping):
        operator_notes = {
            "status": "empty",
            "rows": [],
            "message": "Session journal entries are operator annotations only.",
        }
    content.append(mo.md(build_operator_notes_markdown(operator_notes)))
    if control_panel is not None:
        content.append(control_panel)
    return _render_surface_card(mo.vstack(content, gap=0.65))


def render_premarket_brief_panel(
    shell: Mapping[str, object],
    *,
    control_panel: Any | None = None,
) -> Any:
    content: list[Any] = []
    surfaces = shell.get("surfaces")
    premarket_panel = (
        surfaces.get("pre_market_brief") if isinstance(surfaces, Mapping) else None
    )
    panel = premarket_panel if isinstance(premarket_panel, Mapping) else {}
    content.append(mo.md(build_premarket_brief_markdown(panel)))
    if control_panel is not None:
        content.append(control_panel)
    return _render_surface_card(mo.vstack(content, gap=0.65))


def render_audit_timeline_panel(shell: Mapping[str, object]) -> Any:
    surfaces = shell.get("surfaces")
    panel: Mapping[str, object] = {}
    audit_panel = (
        surfaces.get("audit_replay") if isinstance(surfaces, Mapping) else None
    )
    if isinstance(audit_panel, Mapping):
        panel = audit_panel
    return _render_surface_card(_render_audit_timeline_content(panel))


def _render_audit_timeline_content(panel: Mapping[str, object]) -> Any:
    return mo.md(build_audit_timeline_markdown(panel))


def build_anchor_inputs_markdown(panel: Mapping[str, object]) -> str:
    rows = panel.get("rows")
    lines = [
        "## Cross-Asset Anchor Inputs",
        f"- Status: `{_as_str(panel.get('status'), default='not_configured')}`",
        f"- Boundary: {_as_str(panel.get('message'), default='Operator-supplied context only; preserved engine remains decision authority.')}",
        f"- Integration: `{_as_str(panel.get('integration_status'), default='operator_context_available_not_gate_enforced')}`",
        "",
        "| Contract | Key Levels | Session High | Session Low | Correlation Anchor | Updated | Note |",
        "| --- | --- | ---: | ---: | --- | --- | --- |",
    ]
    if not isinstance(rows, list) or not rows:
        lines.append("| `<none>` |  |  |  |  |  |  |")
        return "\n".join(lines)
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        key_levels = row.get("key_levels")
        key_level_text = "<none>"
        if isinstance(key_levels, list | tuple) and key_levels:
            key_level_text = ", ".join(_number_text(item) for item in key_levels)
        lines.append(
            "| "
            + f"`{_table_value(row.get('contract'))}` | "
            + f"`{_table_value(key_level_text)}` | "
            + f"`{_number_text(row.get('session_high'))}` | "
            + f"`{_number_text(row.get('session_low'))}` | "
            + f"`{_table_value(row.get('correlation_anchor'))}` | "
            + f"`{_table_value(row.get('updated_at'))}` | "
            + f"{_table_value(row.get('operator_note'))} |"
        )
    return "\n".join(lines)


def build_premarket_brief_markdown(panel: Mapping[str, object]) -> str:
    enrichment = panel.get("enrichment")
    lines = [
        "## Premarket Brief",
        f"- Contract: `{_as_str(panel.get('contract'), default='<unavailable>')}`",
        f"- Session Date: `{_as_str(panel.get('session_date'), default='<unavailable>')}`",
        f"- Watchman Status: `{_as_str(panel.get('status'), default='<unavailable>')}`",
        "- Boundary: session-planning context only; missing enrichment does not block readiness.",
        "",
    ]

    if isinstance(enrichment, Mapping):
        lines.append(
            f"- Enrichment Generated At: `{_as_str(enrichment.get('generated_at'), default='<unknown>')}`"
        )
        lines.append("")
        sections = enrichment.get("sections")
        if isinstance(sections, list) and sections:
            for section in sections:
                if not isinstance(section, Mapping):
                    continue
                lines.extend(_premarket_brief_section_lines(section))
            return "\n".join(lines)

    setup_lines = _bullet_lines(panel.get("setup_summaries"))
    warning_lines = _bullet_lines(panel.get("warnings"))
    lines.extend(
        [
            "### Watchman Setup Summaries",
            setup_lines,
            "### Watchman Warnings",
            warning_lines,
        ]
    )
    return "\n".join(lines)


def _premarket_brief_section_lines(section: Mapping[str, object]) -> list[str]:
    section_type = _as_str(section.get("section_type"), default="unknown")
    contract = _as_str(section.get("contract"), default="session")
    source = _as_str(section.get("source"), default="placeholder")
    updated_at = _as_str(section.get("updated_at"), default="<unknown>")
    title = section_type.replace("_", " ").title()
    if contract != "session":
        title = f"{title} - {contract}"
    lines = [
        f"### {title}",
        f"- Source: `{source}`",
        f"- Updated: `{updated_at}`",
    ]
    content = section.get("content")
    if isinstance(content, Mapping):
        lines.extend(_premarket_content_lines(content))
    else:
        lines.append(f"- Content: {_as_str(content, default='<empty>')}")
    lines.append("")
    return lines


def _premarket_content_lines(content: Mapping[str, object]) -> list[str]:
    lines: list[str] = []
    for key, value in content.items():
        label = str(key).replace("_", " ").title()
        if isinstance(value, list):
            if not value:
                lines.append(f"- {label}: `<none>`")
                continue
            lines.append(f"- {label}:")
            for item in value:
                if isinstance(item, Mapping):
                    lines.append("  - " + _inline_mapping(item))
                else:
                    lines.append(f"  - {_as_str(item)}")
        else:
            lines.append(f"- {label}: `{_table_value(value)}`")
    return lines


def build_audit_timeline_markdown(panel: Mapping[str, object]) -> str:
    rows = panel.get("timeline_events")
    filters = panel.get("timeline_filters")
    event_filters = "<none>"
    contract_filters = "<none>"
    selected_event_types: tuple[str, ...] = ()
    selected_contracts: tuple[str, ...] = ()
    if isinstance(filters, Mapping):
        event_types = filters.get("event_types")
        contracts = filters.get("contracts")
        if isinstance(event_types, list | tuple) and event_types:
            event_filters = ", ".join(f"`{_table_value(item)}`" for item in event_types)
        if isinstance(contracts, list | tuple) and contracts:
            contract_filters = ", ".join(
                f"`{_table_value(item)}`" for item in contracts
            )
        selected_event_types = _selected_filter_values(
            filters.get("selected_event_types")
        )
        selected_contracts = _selected_filter_values(filters.get("selected_contracts"))

    lines = [
        "## Audit / Replay Timeline",
        f"- Status: `{_as_str(panel.get('timeline_status'), default='empty')}`",
        "- Boundary: read-only audit context; preserved engine remains the sole decision authority and execution remains manual.",
        f"- Event Type Filters: {event_filters}",
        f"- Contract Filters: {contract_filters}",
        f"- Active Event Type Filters: {_filter_value_text(selected_event_types)}",
        f"- Active Contract Filters: {_filter_value_text(selected_contracts)}",
        "",
        "| Time | Type | Contract | Status | Summary | Detail |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    if not isinstance(rows, list) or not rows:
        lines.append("| `<none>` |  |  |  |  |  |")
        return "\n".join(lines)

    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if not _timeline_row_matches_filters(
            row,
            selected_event_types=selected_event_types,
            selected_contracts=selected_contracts,
        ):
            continue
        contract = row.get("contract") or "session"
        lines.append(
            "| "
            + f"`{_table_value(row.get('timestamp'))}` | "
            + f"`{_table_value(row.get('event_type'))}` | "
            + f"`{_table_value(contract)}` | "
            + f"`{_table_value(row.get('status_badge'))}` | "
            + f"{_table_value(row.get('summary'))} | "
            + f"{_table_value(row.get('detail'))} |"
        )
    return "\n".join(lines)


def _selected_filter_values(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(
        _as_str(item, default="").strip()
        for item in value
        if _as_str(item, default="").strip()
    )


def _filter_value_text(values: tuple[str, ...]) -> str:
    if not values:
        return "`<none>`"
    return ", ".join(f"`{_table_value(item)}`" for item in values)


def _timeline_row_matches_filters(
    row: Mapping[str, object],
    *,
    selected_event_types: tuple[str, ...],
    selected_contracts: tuple[str, ...],
) -> bool:
    if (
        selected_event_types
        and _as_str(row.get("event_type"), default="") not in selected_event_types
    ):
        return False
    contract = _as_str(row.get("contract") or "session", default="session")
    if selected_contracts and contract not in selected_contracts:
        return False
    return True


def build_operator_notes_markdown(panel: Mapping[str, object]) -> str:
    rows = panel.get("rows")
    lines = [
        "## Operator Notes",
        f"- Status: `{_as_str(panel.get('status'), default='empty')}`",
        f"- Boundary: {_as_str(panel.get('message'), default='Session journal entries are operator annotations only.')}",
        "",
        "| Timestamp | Category | Contract | Tags | Note |",
        "| --- | --- | --- | --- | --- |",
    ]
    if not isinstance(rows, list) or not rows:
        lines.append("| `<none>` |  |  |  |  |")
        return "\n".join(lines)
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        tags = row.get("tags")
        tag_text = "<none>"
        if isinstance(tags, list | tuple) and tags:
            tag_text = ", ".join(_table_value(item) for item in tags)
        category = _operator_note_category_badge(row.get("category"))
        contract = row.get("contract") or "session"
        lines.append(
            "| "
            + f"`{_table_value(row.get('timestamp'))}` | "
            + f"`{category}` | "
            + f"`{_table_value(contract)}` | "
            + f"`{_table_value(tag_text)}` | "
            + f"{_table_value(row.get('content'))} |"
        )
    return "\n".join(lines)


def build_active_trades_markdown(panel: Mapping[str, object]) -> str:
    rows = panel.get("rows")
    status = _as_str(panel.get("status"), default="unavailable")
    message = _as_str(
        panel.get("message"),
        default="Operator-recorded trades only. The console does not submit orders or close positions.",
    )
    lines = [
        "## Active Trades",
        f"- Status: `{status}`",
        f"- Boundary: {message}",
        "",
        (
            "| Contract | Direction | Entry | Current | Unrealized P&L | Stop Distance | "
            "Target Distance | Thesis Health | Status | Notes |"
        ),
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | --- |",
    ]
    if not isinstance(rows, list) or not rows:
        lines.append("| `<none>` |  |  |  |  |  |  | `gray` no open trades |  |  |")
        return "\n".join(lines)

    for row in rows:
        if not isinstance(row, Mapping):
            continue
        health = _as_str(row.get("thesis_health"), default="unknown")
        pnl = _optional_float(row.get("unrealized_pnl"))
        lines.append(
            "| "
            + f"`{_table_value(row.get('contract'))}` | "
            + f"`{_table_value(row.get('direction'))}` | "
            + f"`{_number_text(row.get('entry_price'))}` | "
            + f"`{_number_text(row.get('current_price'))}` | "
            + f"`{_pnl_indicator(pnl)} {_number_text(pnl)}` | "
            + f"`{_number_text(row.get('distance_from_stop'))}` | "
            + f"`{_number_text(row.get('distance_from_target'))}` | "
            + f"`{_thesis_health_badge(health)}` | "
            + f"`{_table_value(row.get('status'))}` | "
            + f"{_table_value(row.get('operator_notes'))} |"
        )
    return "\n".join(lines)


def build_stream_health_markdown(health: Mapping[str, object]) -> str:
    connection_state = _as_str(health.get("connection_state"), default="unavailable")
    token_status = _as_str(health.get("token_status"), default="unavailable")
    expires_in = health.get("token_expires_in_seconds")
    reconnect_attempts = _as_str(health.get("reconnect_attempts"), default=0)
    reconnect_active = health.get("reconnect_active") is True
    overall_health = _as_str(health.get("overall_health"), default="unavailable")

    lines = [
        "## Live Stream Health",
        f"- Overall Health: `{overall_health}`",
        f"- Connection State: `{connection_state}`",
        f"- Token Status: `{token_status}`",
        f"- Token Expires In Seconds: `{_as_str(expires_in, default='<unknown>')}`",
        f"- Reconnect Active: `{reconnect_active}`",
        f"- Reconnect Attempts: `{reconnect_attempts}`",
        "",
        "### Contract Heartbeats",
        "| Contract | Indicator | Status |",
        "| --- | --- | --- |",
    ]

    per_contract = health.get("per_contract_status")
    if isinstance(per_contract, Mapping) and per_contract:
        for contract, status in per_contract.items():
            status_text = _as_str(status, default="not_subscribed")
            lines.append(
                f"| `{_as_str(contract)}` | `{_contract_health_indicator(status_text)}` | `{status_text}` |"
            )
    else:
        lines.append("| `<none>` | `gray` | `not_applicable` |")

    stale_contracts = health.get("stale_contracts")
    if isinstance(stale_contracts, list | tuple) and stale_contracts:
        lines.append("")
        lines.append(
            "- Stale Contracts: "
            + ", ".join(f"`{_as_str(contract)}`" for contract in stale_contracts)
        )

    blocking_reasons = health.get("blocking_reasons")
    if isinstance(blocking_reasons, list | tuple) and blocking_reasons:
        lines.append("")
        lines.append("### Blocking Reasons")
        for reason in blocking_reasons:
            lines.append(f"- `{_as_str(reason)}`")

    return "\n".join(lines)


def _contract_health_indicator(status: object) -> str:
    normalized = _as_str(status, default="not_subscribed").strip().lower()
    if normalized == "active":
        return "green"
    if normalized in {"stale", "no_data"}:
        return "red"
    return "yellow"


def _thesis_health_badge(status: object) -> str:
    normalized = _as_str(status, default="unknown").strip().lower()
    color = {
        "healthy": "green",
        "degraded": "yellow",
        "invalidated": "red",
        "unknown": "gray",
        "no_thesis": "gray",
    }.get(normalized, "gray")
    return f"{color} {normalized}"


def _operator_note_category_badge(category: object) -> str:
    normalized = _as_str(category, default="general").strip().lower()
    color = {
        "pre_market": "blue",
        "intraday": "green",
        "post_session": "gray",
        "general": "gray",
    }.get(normalized, "gray")
    return f"{color} {normalized}"


def _pnl_indicator(value: float | None) -> str:
    if value is None or value == 0:
        return "gray"
    if value > 0:
        return "green"
    return "red"


def _number_text(value: object) -> str:
    number = _optional_float(value)
    if number is None:
        return "N/A"
    return f"{number:.4f}".rstrip("0").rstrip(".")


def _optional_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def render_r14_cockpit_shell(cockpit: Mapping[str, object]) -> Any:
    return mo.vstack(
        [
            _render_r14_cockpit_header_html(cockpit),
            mo.hstack(
                [
                    _render_markdown_card(
                        build_r14_cockpit_premarket_markdown(cockpit)
                    ),
                    _render_markdown_card(
                        build_r14_cockpit_live_thesis_markdown(cockpit)
                    ),
                    _render_markdown_card(
                        build_r14_cockpit_pipeline_gate_markdown(cockpit)
                    ),
                ],
                gap=0.75,
            ),
            _render_markdown_card(build_r14_cockpit_evidence_markdown(cockpit)),
        ],
        gap=0.75,
    )


def _render_r14_cockpit_header_html(cockpit: Mapping[str, object]) -> Any:
    """Render the cockpit header as HTML stat grids with chips."""
    identity = _mapping_or_empty(cockpit.get("identity"))
    runtime = _mapping_or_empty(cockpit.get("runtime_status"))
    query = _mapping_or_empty(cockpit.get("query_readiness"))

    gate_status = _as_str(query.get("pipeline_gate_state"), default="DISABLED")
    gate_tier = "ready" if gate_status == "ENABLED" else "blocked"
    gate_title = (
        "Pipeline gate is open"
        if gate_status == "ENABLED"
        else "Pipeline gate is disabled"
    )
    gate_subtitle = _as_str(query.get("gate_statement"), default="")

    # Stat grid cards
    stats_html = '<div class="ntb-grid-3">'
    stats_html += _ntb_stat_card(
        "Profile", _as_str(identity.get("current_profile"), default="<unavailable>")
    )
    stats_html += _ntb_stat_card(
        "Contract", _as_str(identity.get("contract"), default="<unavailable>")
    )
    stats_html += _ntb_stat_card(
        "Support",
        _as_str(identity.get("contract_support_status"), default="<unavailable>"),
        chip=True,
    )
    stats_html += _ntb_stat_card(
        "Runtime",
        _as_str(identity.get("runtime_profile_status"), default="<unavailable>"),
        chip=True,
    )
    stats_html += _ntb_stat_card(
        "Provider",
        _as_str(runtime.get("provider_status"), default="<unavailable>"),
        chip=True,
    )
    stats_html += _ntb_stat_card(
        "Stream",
        _as_str(runtime.get("stream_status"), default="<unavailable>"),
        chip=True,
    )
    stats_html += _ntb_stat_card(
        "Quote",
        _as_str(runtime.get("quote_freshness"), default="<unavailable>"),
        chip=True,
    )
    stats_html += _ntb_stat_card(
        "Chart",
        _as_str(runtime.get("bar_freshness"), default="<unavailable>"),
        chip=True,
    )
    stats_html += _ntb_stat_card(
        "Session",
        _as_str(runtime.get("session_clock_state"), default="<unavailable>"),
        chip=True,
    )
    stats_html += _ntb_stat_card(
        "Event",
        _as_str(runtime.get("event_lockout_state"), default="<unavailable>"),
        chip=True,
    )
    stats_html += _ntb_stat_card("Gate", gate_status, chip=True)
    stats_html += _ntb_stat_card(
        "Manual Query",
        _as_str(query.get("manual_query_allowed"), default="False"),
        chip=True,
    )
    stats_html += _ntb_stat_card(
        "Evaluated At", _as_str(runtime.get("evaluated_at"), default="<unavailable>")
    )
    stats_html += "</div>"

    # Query reason
    reason_html = (
        '<div class="ntb-muted" style="margin-top:10px">'
        f"<strong>Query Reason:</strong> {_h(_query_reason(query))}"
        "</div>"
        '<div class="ntb-muted" style="margin-top:4px">'
        f"<strong>Provenance:</strong> {_h(_as_str(query.get('query_ready_provenance'), default='<unavailable>'))}"
        "</div>"
    )

    # Operator states as callout
    operator_states = cockpit.get("operator_states")
    states_html = ""
    if isinstance(operator_states, list) and operator_states:
        items = []
        for state in operator_states:
            if isinstance(state, Mapping):
                cat = _as_str(state.get("category"), default="")
                st = _as_str(state.get("state"), default="")
                summary = _as_str(state.get("summary"), default="")
                reason = _as_str(state.get("reason"), default="")
                source = _as_str(state.get("source"), default="")
                items.append(
                    f"{_h(cat)} / {_h(st)}: {_h(summary)} Reason: {_h(reason)}. Source: {_h(source)}."
                )
        states_html = (
            '<div class="ntb-callout" style="margin-top:10px">'
            '<div class="ntb-stat__label" style="color:#818cf8">Operator State Reasons</div>'
            + _ntb_list_html(items)
            + "</div>"
        )

    contract_status_html = _contract_status_table_html(cockpit.get("contract_statuses"))
    full_html = (
        _ntb_section_divider("Primary Operator Cockpit")
        + '<div class="ntb-card">'
        + _ntb_severity_banner(gate_status, gate_title, gate_subtitle, tier=gate_tier)
        + stats_html
        + contract_status_html
        + reason_html
        + states_html
        + "</div>"
    )
    return mo.Html(full_html)


def build_r14_cockpit_header_markdown(cockpit: Mapping[str, object]) -> str:
    identity = _mapping_or_empty(cockpit.get("identity"))
    runtime = _mapping_or_empty(cockpit.get("runtime_status"))
    query = _mapping_or_empty(cockpit.get("query_readiness"))
    return "\n".join(
        [
            "## Primary Operator Cockpit",
            "",
            "| Profile | Contract | Support | Runtime | Provider | Stream | Quote | Chart | Session | Event | Gate |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
            (
                f"| `{_table_value(identity.get('current_profile'))}` "
                f"| `{_table_value(identity.get('contract'))}` "
                f"| `{_table_value(identity.get('contract_support_status'))}` "
                f"| `{_table_value(identity.get('runtime_profile_status'))}` "
                f"| `{_table_value(runtime.get('provider_status'))}` "
                f"| `{_table_value(runtime.get('stream_status'))}` "
                f"| `{_table_value(runtime.get('quote_freshness'))}` "
                f"| `{_table_value(runtime.get('bar_freshness'))}` "
                f"| `{_table_value(runtime.get('session_clock_state'))}` "
                f"| `{_table_value(runtime.get('event_lockout_state'))}` "
                f"| `{_table_value(query.get('pipeline_gate_state'))}` |"
            ),
            "",
            "### Contract Data Status",
            _contract_status_markdown(cockpit.get("contract_statuses")),
            f"- Manual Query Allowed: `{_as_str(query.get('manual_query_allowed'), default=False)}`",
            f"- Query Reason: {_query_reason(query)}",
            f"- QUERY_READY Provenance: `{_as_str(query.get('query_ready_provenance'), default='<unavailable>')}`",
            f"- Evaluated At: `{_as_str(runtime.get('evaluated_at'), default='<unavailable>')}`",
            "- Operator State Reasons:",
            _operator_state_lines(cockpit.get("operator_states")),
        ]
    )


def build_r14_cockpit_premarket_markdown(cockpit: Mapping[str, object]) -> str:
    premarket = _mapping_or_empty(cockpit.get("premarket"))
    return "\n".join(
        [
            "## Premarket Plan",
            f"- Brief Status: `{_as_str(premarket.get('premarket_brief_status'), default='<unavailable>')}`",
            f"- Active Setup Count: `{_as_str(premarket.get('active_setup_count'), default=0)}`",
            "- Structural Setups:",
            _mapping_item_lines(
                premarket.get("setup_summaries"), ("setup_id", "summary")
            ),
            "- Global Guidance:",
            _plain_item_lines(premarket.get("global_guidance")),
            "- Warnings:",
            _plain_item_lines(premarket.get("warnings")),
            "- Invalidators:",
            _mapping_item_lines(
                premarket.get("invalidators"), ("invalidator_id", "condition", "action")
            ),
            "- Trigger Definitions:",
            _mapping_item_lines(
                premarket.get("trigger_definitions"), ("trigger_id", "summary")
            ),
            "- Fields Used:",
            _plain_item_lines(premarket.get("required_fields")),
            "- Missing / Unavailable Fields:",
            _mixed_item_lines(
                premarket.get("missing_fields"), premarket.get("unavailable_fields")
            ),
            "- Plan Blocking Reasons:",
            _plain_item_lines(premarket.get("blocking_reasons")),
        ]
    )


def build_r14_cockpit_live_thesis_markdown(cockpit: Mapping[str, object]) -> str:
    triggers = cockpit.get("triggers")
    lines = ["## Live Thesis Monitor"]
    if not isinstance(triggers, list) or not triggers:
        lines.append("- Trigger State: `<unavailable>`")
        lines.append("- Blocking Reasons:")
        lines.append("  - `<unavailable>`")
        return "\n".join(lines)

    for trigger in triggers:
        if not isinstance(trigger, Mapping):
            continue
        lines.extend(
            [
                f"- Setup: `{_as_str(trigger.get('setup_id'), default='<unavailable>')}`",
                f"- Trigger: `{_as_str(trigger.get('trigger_id'), default='<unavailable>')}`",
                f"- State: `{_as_str(trigger.get('trigger_state'), default='UNAVAILABLE')}`",
                f"- Distance To Trigger Ticks: `{_as_str(trigger.get('distance_to_trigger_ticks'), default='<unavailable>')}`",
                f"- QUERY_READY Provenance: `{_as_str(trigger.get('query_ready_provenance'), default='<unavailable>')}`",
                "- Current Live / Fixture Values:",
                _mapping_item_lines(
                    trigger.get("current_values"), ("field", "value", "status")
                ),
                "- Required Fields:",
                _plain_item_lines(trigger.get("required_fields")),
                "- Missing Fields:",
                _plain_item_lines(trigger.get("missing_fields")),
                "- Invalidators / Invalid Reasons:",
                _plain_item_lines(trigger.get("invalid_reasons")),
                "- Blocking Reasons:",
                _plain_item_lines(trigger.get("blocking_reasons")),
            ]
        )
    return "\n".join(lines)


def build_r14_cockpit_pipeline_gate_markdown(cockpit: Mapping[str, object]) -> str:
    query = _mapping_or_empty(cockpit.get("query_readiness"))
    result = _mapping_or_empty(cockpit.get("last_pipeline_result"))
    return "\n".join(
        [
            "## Pipeline Gate",
            f"- Gate Status: `{_as_str(query.get('pipeline_gate_state'), default='DISABLED')}`",
            f"- Query Ready: `{_as_str(query.get('query_ready'), default=False)}`",
            f"- Manual Query Allowed: `{_as_str(query.get('manual_query_allowed'), default=False)}`",
            f"- Reason: {_query_reason(query)}",
            f"- QUERY_READY Provenance: `{_as_str(query.get('query_ready_provenance'), default='<unavailable>')}`",
            f"- Trigger State From Real Producer: `{_as_str(query.get('trigger_state_from_real_producer'), default=False)}`",
            "- Enabled Reasons:",
            _plain_item_lines(query.get("enabled_reasons")),
            "- Disabled / Blocking Reasons:",
            _plain_item_lines(
                query.get("blocking_reasons") or query.get("disabled_reasons")
            ),
            "- Missing Conditions:",
            _plain_item_lines(query.get("missing_conditions")),
            "- Operator State Reasons:",
            _operator_state_lines(cockpit.get("operator_states")),
            f"- Gate Statement: {_as_str(query.get('gate_statement'), default='<unavailable>')}",
            "",
            "### Last Pipeline Result",
            f"- Result Status: `{_as_str(result.get('status'), default='not_queried')}`",
            f"- Stage Termination: `{_as_str(result.get('termination_stage'), default='<unavailable>')}`",
            f"- Stage Termination Reason: `{_as_str(result.get('stage_termination_reason'), default='<unavailable>')}`",
            f"- Final Decision: `{_as_str(result.get('final_decision'), default='<unavailable>')}`",
            f"- NO_TRADE Summary: {_as_str(result.get('no_trade_summary'), default='<unavailable>')}",
            f"- APPROVED Summary: {_as_str(result.get('approved_summary'), default='<unavailable>')}",
            f"- REJECTED Summary: {_as_str(result.get('rejected_summary'), default='<unavailable>')}",
        ]
    )


def build_r14_cockpit_evidence_markdown(cockpit: Mapping[str, object]) -> str:
    replay = _mapping_or_empty(cockpit.get("replay_availability"))
    return "\n".join(
        [
            "## Evidence And Replay",
            f"- Run History Availability: `{_as_str(replay.get('run_history_status'), default='unavailable')}`",
            f"- Audit / Replay Availability: `{_as_str(replay.get('audit_replay_status'), default='unavailable')}`",
            f"- Audit / Replay Available: `{_as_str(replay.get('audit_replay_available'), default=False)}`",
            f"- Session Evidence Availability: `{_as_str(replay.get('session_evidence_status'), default='unavailable')}`",
            f"- Operator Notes Availability: `{_as_str(replay.get('operator_note_status'), default='unavailable')}`",
            f"- Trigger Transition Log Availability: `{_as_str(replay.get('trigger_transition_status'), default='unavailable')}`",
            f"- Trigger Transition Count: `{_as_str(replay.get('trigger_transition_count'), default=0)}`",
            f"- Replay Statement: {_as_str(replay.get('replay_statement'), default='<unavailable>')}",
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
        return _render_surface_card(
            mo.md(
                f"## Session Header\n- Contract: `{contract}`\n- Session Date: `{session_date}`"
            )
        )

    if key == "pre_market_brief":
        return _render_surface_card(mo.md(build_premarket_brief_markdown(panel)))

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
        return _render_surface_card(
            mo.md(
                "## Readiness Matrix\n"
                + ("\n".join(row_lines) if row_lines else "- unavailable")
            )
        )

    if key == "five_contract_readiness_summary":
        rows = panel.get("rows")
        lines = [
            "## Five-Contract Readiness Summary",
            f"- Mode: `{_as_str(panel.get('mode'), default='<unavailable>')}`",
            f"- Readiness Source: `{_as_str(panel.get('readiness_source'), default='<unavailable>')}`",
            f"- Active Profile: `{_as_str(panel.get('active_profile_id'), default='<none>')}`",
            f"- Default Launch Live: `{_as_str(panel.get('default_launch_live'), default=False)}`",
            f"- Live Credentials Required: `{_as_str(panel.get('live_credentials_required'), default=False)}`",
            f"- Decision Authority: `{_as_str(panel.get('decision_authority'), default='<unavailable>')}`",
            f"- Manual Execution Only: `{_as_str(panel.get('manual_execution_only'), default=True)}`",
            f"- Summary Can Authorize Trades: `{_as_str(panel.get('summary_can_authorize_trades'), default=False)}`",
            f"- Live Runtime Readiness: `{_as_str(panel.get('live_runtime_readiness_status'), default='<unavailable>')}`",
            f"- Runtime Cache Bound To Operator Launch: `{_as_str(panel.get('runtime_cache_bound_to_operator_launch'), default=False)}`",
            f"- Runtime Cache Source: `{_as_str(panel.get('runtime_cache_source_type'), default='<unavailable>')}`",
            f"- Runtime Provider Status: `{_as_str(panel.get('runtime_cache_provider_status'), default='<unavailable>')}`",
            f"- Runtime Snapshot Ready: `{_as_str(panel.get('runtime_cache_snapshot_ready'), default=False)}`",
            f"- Runtime Readiness Blockers: `{_as_str(panel.get('live_runtime_readiness_blockers'), default=[])}`",
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
                    + f"quote={_as_str(row.get('quote_status'), default='<unavailable>')}, "
                    + f"chart={_as_str(row.get('chart_status'), default='<unavailable>')}, "
                    + f"source={_as_str(row.get('readiness_source'), default='<unavailable>')}, "
                    + f"live_state={_as_str(row.get('live_runtime_readiness_state'), default='<unavailable>')}, "
                    + f"runtime_cache={_as_str(row.get('runtime_cache_status'), default='<unavailable>')}, "
                    + f"trigger={_as_str(row.get('trigger_state_summary'))}, "
                    + f"query={_as_str(row.get('query_gate_status'))}"
                )
                blocked = row.get("primary_blocked_reasons")
                if isinstance(blocked, list) and blocked:
                    lines.append(
                        "    Blocked: " + ", ".join(_as_str(item) for item in blocked)
                    )
                query_not_ready = row.get("query_not_ready_reasons")
                if isinstance(query_not_ready, list) and query_not_ready:
                    lines.append(
                        "    Query Not Ready: "
                        + ", ".join(_as_str(item) for item in query_not_ready)
                    )
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
        return _render_surface_card(
            mo.md(
                "## Trigger Table\n"
                + ("\n".join(row_lines) if row_lines else "- unavailable")
            )
        )

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
        lines.extend(_render_pipeline_query_gate_lines(panel))
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
            lines = [
                "## Decision Review",
                "",
                "### Decision Summary",
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
            lines.extend(
                _render_decision_review_engine_reasoning(panel.get("engine_reasoning"))
            )
            lines.extend(
                _render_decision_review_trade_thesis(panel.get("trade_thesis"))
            )
            lines.extend(
                _render_decision_review_risk_authorization(
                    panel.get("risk_authorization_detail")
                )
            )
            lines.extend(
                _render_decision_review_invalidation(panel.get("invalidation"))
            )
            lines.extend(
                _render_decision_review_replay(panel.get("narrative_audit_replay"))
            )
            unavailable_message = panel.get("narrative_unavailable_message")
            if (
                isinstance(unavailable_message, str)
                and panel.get("narrative_available") is not True
            ):
                lines.append("")
                lines.append(f"_{unavailable_message}_")
            return _render_surface_card(mo.md("\n".join(lines)))
        return _render_surface_card(
            mo.md(
                "\n".join(
                    [
                        "## Decision Review",
                        f"- Ready: `{_as_str(panel.get('ready'), default=False)}`",
                        f"- Status: `{_as_str(panel.get('status'), default='NOT_READY')}`",
                        f"- Message: {_as_str(panel.get('message'), default='Decision Review is not ready yet.')}",
                    ]
                    + _render_decision_review_replay(
                        panel.get("narrative_audit_replay")
                    )
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
            lines.append(
                f"  - [{index}] " + "; ".join(row_parts)
                if row_parts
                else f"  - [{index}] <unavailable>"
            )
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
        lines.extend(
            _render_decision_review_replay(panel.get("narrative_audit_replay"))
        )
        return _render_surface_card(
            mo.vstack(
                [
                    mo.md("\n".join(lines)),
                    _render_audit_timeline_content(panel),
                ],
                gap=0.65,
            )
        )

    return _render_surface_card(mo.md(f"## {key}\n- unavailable"))


def _render_fixture_cockpit_primary(surface: Mapping[str, object]) -> Any:
    """Render the fixture cockpit as the primary operator landing surface.

    This is the first operator-visible section in the console, positioned
    before all metadata, profile, and debug sections.  It renders an HTML
    table of per-contract status — no raw quote/bar/streamer values.
    """
    mode = _as_str(surface.get("mode"), default="<unavailable>")
    authority = _as_str(surface.get("decision_authority"), default="<unavailable>")
    error = surface.get("error")

    # Mode banner
    banner = _ntb_severity_banner(
        "FIXTURE",
        "Non-Live Fixture Cockpit — Credential-Free",
        f"Mode: {mode} | Decision authority: {authority} | Manual query only | No credentials required",
        tier="ready",
    )

    # Per-contract table rows
    rows = surface.get("rows")
    tbody_html = ""
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            contract = _as_str(row.get("contract"))
            label = _as_str(row.get("profile_label"))
            quote = _as_str(row.get("quote_status"))
            chart = _as_str(row.get("chart_status"))
            gate = _as_str(row.get("query_gate_state"))
            action_state = _as_str(row.get("query_action_state"), default="DISABLED")
            action_text = _as_str(row.get("query_action_text"), default="Manual query blocked.")
            reason = _as_str(row.get("query_reason"))
            tbody_html += (
                "<tr>"
                f"<td><strong>{_h(contract)}</strong></td>"
                f"<td>{_h(label)}</td>"
                f"<td>{_ntb_chip_for_status(quote)}</td>"
                f"<td>{_ntb_chip_for_status(chart)}</td>"
                f"<td>{_ntb_chip_for_status(gate)}</td>"
                f"<td>{_ntb_chip_for_status(action_state)}</td>"
                f"<td>{_h(action_text)}</td>"
                f"<td class='ntb-muted'>{_h(reason)}</td>"
                "</tr>"
            )
    if not tbody_html:
        tbody_html = (
            "<tr><td colspan='8' class='ntb-muted'>&lt;unavailable&gt;</td></tr>"
        )

    table_html = (
        "<table class='ntb-table'>"
        "<thead><tr>"
        "<th>Contract</th><th>Label</th><th>Quote</th><th>Chart</th>"
        "<th>Gate</th><th>Manual Query State</th><th>Operator Action</th><th>Block / Eligible Reason</th>"
        "</tr></thead>"
        f"<tbody>{tbody_html}</tbody>"
        "</table>"
    )

    error_html = ""
    if error is not None:
        error_html = (
            f'<div class="ntb-muted" style="margin-top:8px">'
            f"Build error: {_h(_as_str(error))}</div>"
        )

    full_html = (
        _ntb_section_divider("FIVE-CONTRACT FIXTURE COCKPIT")
        + '<div class="ntb-card">'
        + banner
        + table_html
        + error_html
        + "</div>"
    )
    return mo.Html(full_html)


# Backward-compatible alias (kept for any external callers; use the primary variant in new code)
_render_fixture_cockpit_overview = _render_fixture_cockpit_primary


def _render_console_header(
    shell: Mapping[str, object], *, heading: str, mode_summary: str
) -> Any:
    startup = shell.get("startup")
    runtime = shell.get("runtime")
    startup_map = startup if isinstance(startup, Mapping) else {}
    runtime_map = runtime if isinstance(runtime, Mapping) else {}

    mode = _first_value(startup_map, runtime_map, "runtime_mode_label", "runtime_mode")
    profile_id = _first_value(
        startup_map, runtime_map, "selected_profile_id", "profile_id"
    )
    contract = _first_value(startup_map, runtime_map, "contract")
    readiness = _first_value(
        startup_map, runtime_map, "readiness_state", "startup_readiness_state"
    )
    session_state = _first_value(
        startup_map, runtime_map, "current_session_state", "session_state"
    )
    running_as = _first_value(startup_map, runtime_map, "running_as", "runtime_backend")

    readiness_color = "#22c55e" if readiness == "OPERATOR_SURFACES_READY" else "#facc15"
    session_color = (
        "#22c55e"
        if "READY" in session_state
        else ("#facc15" if "BLOCKED" in session_state else "#94a3b8")
    )

    pills_html = (
        '<div class="ntb-header__pills">'
        + _ntb_pill("Mode", mode)
        + _ntb_pill("Profile", profile_id)
        + _ntb_pill("Contract", contract)
        + _ntb_pill("Readiness", readiness, color=readiness_color)
        + _ntb_pill("Session", session_state, color=session_color)
        + "</div>"
    )

    header_html = (
        '<div class="ntb-shell"><div class="ntb-header">'
        "<div>"
        f'<div class="ntb-header__title">{_h(heading)}</div>'
        f'<div class="ntb-header__subtitle">'
        f"Running as {_h(running_as)} &middot; {_h(mode)}"
        "</div></div>" + pills_html + "</div>" + _ntb_ribbon(mode_summary) + "</div>"
    )
    return mo.Html(header_html)


def _build_context_summary_markdown(shell: Mapping[str, object]) -> str:
    startup = shell.get("startup")
    runtime = shell.get("runtime")
    startup_map = startup if isinstance(startup, Mapping) else {}
    runtime_map = runtime if isinstance(runtime, Mapping) else {}

    mode = _first_value(startup_map, runtime_map, "runtime_mode_label", "runtime_mode")
    profile_id = _first_value(
        startup_map, runtime_map, "selected_profile_id", "profile_id"
    )
    contract = _first_value(startup_map, runtime_map, "contract")
    readiness = _first_value(
        startup_map, runtime_map, "readiness_state", "startup_readiness_state"
    )
    session_state = _first_value(
        startup_map, runtime_map, "current_session_state", "session_state"
    )
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


def _first_value(
    primary: Mapping[str, object], secondary: Mapping[str, object], *keys: str
) -> str:
    for key in keys:
        value = primary.get(key)
        if value is not None:
            return _as_str(value, default="<unavailable>")
        value = secondary.get(key)
        if value is not None:
            return _as_str(value, default="<unavailable>")
    return "<unavailable>"


def _build_five_contract_readiness_summary_fallback(
    shell: Mapping[str, object],
) -> dict[str, object]:
    from ..readiness_summary import build_five_contract_readiness_summary_surface

    startup = shell.get("startup")
    runtime = shell.get("runtime")
    startup_map = startup if isinstance(startup, Mapping) else {}
    runtime_map = runtime if isinstance(runtime, Mapping) else {}
    active_profile_id = _first_value(
        startup_map, runtime_map, "selected_profile_id", "profile_id"
    )
    if active_profile_id == "<unavailable>":
        active_profile_id = None
    return build_five_contract_readiness_summary_surface(
        active_profile_id=active_profile_id
    )


def _table_value(value: object) -> str:
    return _as_str(value, default="<unavailable>").replace("|", "\\|")


def _mapping_or_empty(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _query_reason(query: Mapping[str, object]) -> str:
    enabled_reason = query.get("query_enabled_reason")
    if enabled_reason is not None:
        return _as_str(enabled_reason, default="<unavailable>")
    return _as_str(query.get("query_disabled_reason"), default="<unavailable>")


def _as_str(value: object, *, default: str = "<missing>") -> str:
    if value is None:
        return default
    return str(value)


def _render_debug_secondary(shell_json: str) -> Any:
    debug_content = mo.vstack(
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
    return mo.accordion({"Debug (Secondary)": debug_content})


def _safe_json(value: object) -> str:
    return json.dumps(value, indent=2)


def _inline_value(value: object) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"))
    return _as_str(value)


def _inline_mapping(mapping: Mapping[object, object]) -> str:
    return "; ".join(
        f"{_table_value(key)}={_table_value(value)}" for key, value in mapping.items()
    )


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


def _plain_item_lines(value: object) -> str:
    if isinstance(value, list | tuple):
        lines = [
            f"  - `{_as_str(item)}`"
            for item in value
            if _as_str(item, default="").strip()
        ]
        return "\n".join(lines) if lines else "  - `<none>`"
    return "  - `<unavailable>`"


def _operator_state_lines(value: object) -> str:
    if not isinstance(value, list | tuple):
        return "  - `<unavailable>`"
    lines: list[str] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        category = _as_str(item.get("category"), default="<unavailable>")
        state = _as_str(item.get("state"), default="<unavailable>")
        summary = _as_str(item.get("summary"), default="<unavailable>")
        reason = _as_str(item.get("reason"), default="<unavailable>")
        source = _as_str(item.get("source"), default="<unavailable>")
        lines.append(
            f"  - `{state}` / `{category}`: {summary} Reason: `{reason}`. Source: `{source}`."
        )
    return "\n".join(lines) if lines else "  - `<none>`"


def _contract_status_markdown(value: object) -> str:
    if not isinstance(value, list | tuple):
        return "`<unavailable>`"
    lines = [
        "| Contract | Label | Mode | Support | Quote | Chart | Action State | Operator Action | Disabled Reason | Provenance | Message | Reasons |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    rendered = 0
    for item in value:
        if not isinstance(item, Mapping):
            continue
        reasons = item.get("blocking_reasons")
        reason_text = (
            ", ".join(_as_str(reason) for reason in reasons)
            if isinstance(reasons, list)
            else ""
        )
        lines.append(
            "| "
            + f"`{_table_value(item.get('contract'))}` "
            + f"| `{_table_value(item.get('profile_label'))}` "
            + f"| `{_table_value(item.get('runtime_state'))}` "
            + f"| `{_table_value(item.get('support_state'))}` "
            + f"| `{_table_value(item.get('quote_status'))}` "
            + f"| `{_table_value(item.get('chart_status'))}` "
            + f"| `{_table_value(item.get('query_action_state'))}` "
            + f"| {_table_value(item.get('query_action_text'))} "
            + f"| {_table_value(item.get('query_disabled_reason') or '<none>')} "
            + f"| `{_table_value(item.get('query_action_provenance'))}` "
            + f"| {_table_value(item.get('status_text'))} "
            + f"| `{_table_value(reason_text or '<none>')}` |"
        )
        rendered += 1
    if rendered == 0:
        lines.append(
            "| `<unavailable>` | `<unavailable>` | `<unavailable>` | `<unavailable>` | `<unavailable>` | `<unavailable>` | `<unavailable>` | `<unavailable>` | `<unavailable>` | `<unavailable>` | `<unavailable>` | `<unavailable>` |"
        )
    return "\n".join(lines)


def _contract_status_table_html(value: object) -> str:
    if not isinstance(value, list | tuple):
        return ""
    rows: list[str] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        reasons = item.get("blocking_reasons")
        reason_text = (
            ", ".join(_as_str(reason) for reason in reasons)
            if isinstance(reasons, list)
            else ""
        )
        rows.append(
            "<tr>"
            + f"<td>{_h(_as_str(item.get('contract'), default='<unavailable>'))}</td>"
            + f"<td>{_h(_as_str(item.get('profile_label'), default='<unavailable>'))}</td>"
            + f"<td>{_h(_as_str(item.get('runtime_state'), default='<unavailable>'))}</td>"
            + f"<td>{_h(_as_str(item.get('support_state'), default='<unavailable>'))}</td>"
            + f"<td>{_h(_as_str(item.get('quote_status'), default='<unavailable>'))}</td>"
            + f"<td>{_h(_as_str(item.get('chart_status'), default='<unavailable>'))}</td>"
            + f"<td>{_ntb_chip_for_status(_as_str(item.get('query_action_state'), default='DISABLED'))}</td>"
            + f"<td>{_h(_as_str(item.get('query_action_text'), default='Manual query blocked.'))}</td>"
            + f"<td>{_h(_as_str(item.get('query_disabled_reason'), default='<none>'))}</td>"
            + f"<td>{_h(_as_str(item.get('query_action_provenance'), default='<unavailable>'))}</td>"
            + f"<td>{_h(_as_str(item.get('status_text'), default='<unavailable>'))}</td>"
            + f"<td>{_h(reason_text or '<none>')}</td>"
            + "</tr>"
        )
    if not rows:
        return ""
    return (
        '<div style="margin-top:12px; overflow-x:auto">'
        '<div class="ntb-stat__label" style="margin-bottom:6px">Contract Data Status</div>'
        '<table class="ntb-table"><thead><tr>'
        "<th>Contract</th><th>Label</th><th>Mode</th><th>Support</th><th>Quote</th><th>Chart</th><th>Action State</th><th>Operator Action</th><th>Disabled Reason</th><th>Provenance</th><th>Message</th><th>Reasons</th>"
        "</tr></thead><tbody>" + "".join(rows) + "</tbody></table></div>"
    )


def _mapping_item_lines(value: object, fields: tuple[str, ...]) -> str:
    if not isinstance(value, list | tuple):
        return "  - `<unavailable>`"
    lines: list[str] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        parts = [
            f"{field}={_inline_value(item.get(field))}"
            for field in fields
            if field in item
        ]
        lines.append("  - " + "; ".join(parts) if parts else "  - `<unavailable>`")
    return "\n".join(lines) if lines else "  - `<none>`"


def _mixed_item_lines(primary: object, secondary: object) -> str:
    lines: list[str] = []
    if isinstance(primary, list | tuple):
        lines.extend(f"  - `{_as_str(item)}`" for item in primary)
    if isinstance(secondary, list | tuple):
        for item in secondary:
            if isinstance(item, Mapping):
                field = _as_str(item.get("field"), default="<unavailable>")
                reason = _as_str(item.get("reason"), default="<unavailable>")
                status = _as_str(item.get("status"), default="<unavailable>")
                lines.append(f"  - `{field}`: {status}; {reason}")
    return "\n".join(lines) if lines else "  - `<none>`"


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
        lines.append(
            "    Summary: " + _as_str(item.get("summary"), default="<unavailable>")
        )
    return "\n".join(lines) if lines else "  - <none>"


def _ready_outcome_suffix(state: object, outcome: object) -> str:
    state_text = _as_str(state, default="<unavailable>")
    if outcome is None:
        return state_text
    return f"{state_text} ({_as_str(outcome)})"


def _render_pipeline_query_gate_lines(panel: Mapping[str, object]) -> list[str]:
    gate = panel.get("pipeline_query_gate")
    if not isinstance(gate, Mapping):
        return [
            "",
            "### Pipeline Query Gate",
            "- Status: `unavailable`",
            "- Reason: `pipeline_query_gate_result_unavailable`",
        ]

    contract = _as_str(gate.get("contract"), default="<unavailable>")
    setup_id = _as_str(gate.get("setup_id"), default="<unavailable>")
    trigger_id = _as_str(gate.get("trigger_id"), default="<unavailable>")
    trigger_state = _as_str(gate.get("trigger_state"), default="UNAVAILABLE")
    from_real_producer = gate.get("trigger_state_from_real_producer") is True
    raw_enabled = (
        gate.get("enabled") is True or gate.get("pipeline_query_authorized") is True
    )
    enabled = raw_enabled and trigger_state == "QUERY_READY" and from_real_producer
    status = "ENABLED" if enabled else "DISABLED"

    lines = [
        "",
        "### Pipeline Query Gate",
        f"- Status: `{status}`",
        f"- Gate Enabled: `{enabled}`",
        f"- Contract: `{contract}`",
        f"- Selected Setup ID: `{setup_id}`",
        f"- Selected Trigger ID: `{trigger_id}`",
        f"- Trigger State: `{trigger_state}`",
        f"- Trigger State From Real Producer: `{from_real_producer}`",
        f"- Gate Statement: {_GATE_STATEMENT_TEXT}",
    ]

    if not from_real_producer:
        lines.append(
            "- Producer Note: Real trigger state result was not supplied; the gate stays fail-closed."
        )
        if raw_enabled:
            lines.append(
                "- Provenance Guard: raw gate enablement was ignored because QUERY_READY was not proven by the real producer."
            )

    if enabled:
        lines.append("- Primary Enabled Reasons:")
        enabled_reasons = gate.get("enabled_reasons")
        if isinstance(enabled_reasons, list) and enabled_reasons:
            for reason in enabled_reasons:
                lines.append(f"  - `{_as_str(reason)}`")
        else:
            lines.append("  - `query_ready_conditions_met`")
        if trigger_state != "QUERY_READY":
            lines.append(
                "- Note: Gate enabled requires a real produced QUERY_READY trigger state; "
                "any other state must keep this gate disabled."
            )
    else:
        lines.append("- Disabled Because:")
        disabled_reasons = gate.get("disabled_reasons")
        if isinstance(disabled_reasons, list) and disabled_reasons:
            for reason in disabled_reasons:
                lines.append(f"  - `{_as_str(reason)}`")
        else:
            lines.append("  - `pipeline_query_gate_disabled_unspecified_reason`")
        if trigger_state != "QUERY_READY":
            lines.append(
                f"- Trigger State Explanation: real produced trigger state is `{trigger_state}`, "
                "not `QUERY_READY`; the gate stays disabled until the producer reports QUERY_READY."
            )
        missing_conditions = gate.get("missing_conditions")
        if isinstance(missing_conditions, list) and missing_conditions:
            lines.append("- Missing Required Conditions:")
            for condition in missing_conditions:
                lines.append(f"  - `{_as_str(condition)}`")

    return lines


_GATE_STATEMENT_TEXT = "Gate enabled means only that the operator may manually query the preserved Stage A through D pipeline."


def _render_decision_review_replay(replay: object) -> list[str]:
    lines = ["", "### Narrative Audit Replay"]
    if not isinstance(replay, Mapping) or replay.get("available") is not True:
        message = (
            replay.get("unavailable_message") if isinstance(replay, Mapping) else None
        )
        lines.append(
            f"- _{_as_str(message, default='Decision Review narrative audit replay is unavailable.')}_"
        )
        return lines

    lines.extend(
        [
            f"- Audit Schema: `{_as_str(replay.get('audit_schema'))}`",
            f"- Audit Schema Version: `{_as_str(replay.get('audit_schema_version'))}`",
            f"- Created At: `{_as_str(replay.get('created_at'))}`",
            f"- Source: `{_as_str(replay.get('source'))}`",
            f"- Contract: `{_as_str(replay.get('contract'))}`",
            f"- Profile ID: `{_as_str(replay.get('profile_id'))}`",
            f"- Setup ID: `{_as_str(replay.get('setup_id'))}`",
            f"- Trigger ID: `{_as_str(replay.get('trigger_id'))}`",
            f"- Trigger State: `{_as_str(replay.get('trigger_state'))}`",
            f"- Pipeline Result Status: `{_as_str(replay.get('pipeline_result_status'))}`",
            f"- Final Decision: `{_as_str(replay.get('final_decision'))}`",
            f"- Termination Stage: `{_as_str(replay.get('termination_stage'))}`",
            f"- Engine Narrative Available: `{_as_str(replay.get('engine_narrative_available'), default=False)}`",
            f"- Trigger Transition Narrative Available: `{_as_str(replay.get('trigger_transition_narrative_available'), default=False)}`",
            f"- Manual-Only Execution: `{_as_str(replay.get('manual_only_execution'), default=False)}`",
            f"- Preserved Engine Authority: `{_as_str(replay.get('preserved_engine_authority'), default=False)}`",
            f"- Authority Statement: {_as_str(replay.get('authority_statement'), default='<unavailable>')}",
            f"- Replay Reference Status: `{_as_str(replay.get('replay_reference_status'), default='unavailable')}`",
            f"- Replay Reference Source: `{_as_str(replay.get('replay_reference_source'), default='unknown')}`",
            f"- Replay Reference Run ID: `{_as_str(replay.get('replay_reference_run_id'))}`",
            f"- Replay Reference Final Decision: `{_as_str(replay.get('replay_reference_final_decision'))}`",
            f"- Replay Reference Consistent: `{_as_str(replay.get('replay_reference_consistent'))}`",
            f"- Replay Reference Stage E Live Backend: `{_as_str(replay.get('replay_reference_stage_e_live_backend'), default=False)}`",
            f"- Replay Reference Message: {_as_str(replay.get('replay_reference_message'), default='<unavailable>')}",
        ]
    )

    quality = replay.get("narrative_quality")
    if isinstance(quality, Mapping):
        lines.append(
            f"- Narrative Quality Status: `{_as_str(quality.get('status'), default='WARN')}`"
        )
        blockers = quality.get("blocking_reasons")
        if isinstance(blockers, list) and blockers:
            lines.append("- Narrative Quality Blocking Reasons:")
            for blocker in blockers:
                lines.append(f"    - `{_as_str(blocker)}`")
        warnings = quality.get("warnings")
        if isinstance(warnings, list) and warnings:
            lines.append("- Narrative Quality Warnings:")
            for warning in warnings:
                lines.append(f"    - `{_as_str(warning)}`")
    else:
        lines.append("- Narrative Quality Status: `WARN`")
        lines.append("- Narrative Quality Warnings:")
        lines.append("    - `quality_validation_unavailable`")

    lines.extend(
        [
            f"- Transition Summary: {_as_str(replay.get('transition_summary'), default='<unavailable>')}",
            f"- Readiness Explanation: {_as_str(replay.get('readiness_explanation'), default='<unavailable>')}",
            f"- Blocking Explanation: {_as_str(replay.get('blocking_explanation'), default='<none>')}",
            f"- Invalidation Explanation: {_as_str(replay.get('invalidation_explanation'), default='<none>')}",
            f"- Missing Data Explanation: {_as_str(replay.get('missing_data_explanation'), default='<none>')}",
            f"- Stale Indicator: `{_as_str(replay.get('stale'), default=False)}`",
            f"- Lockout Indicator: `{_as_str(replay.get('lockout'), default=False)}`",
        ]
    )

    engine_summary = replay.get("engine_reasoning_summary")
    if isinstance(engine_summary, Mapping) and engine_summary.get("available") is True:
        lines.append(
            "- Engine Reasoning Summary: "
            + f"regime=`{_as_str(engine_summary.get('market_regime'))}`, "
            + f"bias=`{_as_str(engine_summary.get('directional_bias'))}`, "
            + f"confidence=`{_as_str(engine_summary.get('confidence_band'))}`, "
            + f"outcome=`{_as_str(engine_summary.get('outcome'))}`"
        )
    else:
        message = (
            engine_summary.get("unavailable_message")
            if isinstance(engine_summary, Mapping)
            else None
        )
        lines.append(
            f"- Engine Reasoning Summary: {_as_str(message, default='unavailable')}"
        )

    for label, key in (
        ("Blocking Reasons", "blocking_reasons"),
        ("Invalid Reasons", "invalid_reasons"),
        ("Missing Fields", "missing_fields"),
        ("Source Fields", "source_fields"),
    ):
        values = replay.get(key)
        if isinstance(values, list) and values:
            lines.append(f"- {label}:")
            for value in values:
                lines.append(f"    - `{_as_str(value)}`")
        else:
            lines.append(f"- {label}: _none recorded_")
    return lines


def _render_decision_review_engine_reasoning(section: object) -> list[str]:
    lines = ["", "### Engine Reasoning"]
    if not isinstance(section, Mapping) or section.get("available") is not True:
        message = (
            section.get("unavailable_message") if isinstance(section, Mapping) else None
        )
        lines.append(
            f"- _{_as_str(message, default='Engine narrative unavailable in this run.')}_"
        )
        return lines
    lines.append(f"- Market Regime: `{_as_str(section.get('market_regime'))}`")
    lines.append(f"- Directional Bias: `{_as_str(section.get('directional_bias'))}`")
    lines.append(f"- Confidence Band: `{_as_str(section.get('confidence_band'))}`")
    lines.append(f"- Evidence Score: `{_as_str(section.get('evidence_score'))}`")
    lines.append(f"- Stage B Outcome: `{_as_str(section.get('outcome'))}`")
    structural_notes = section.get("structural_notes")
    if isinstance(structural_notes, str) and structural_notes:
        lines.append(f"- Structural Notes: {structural_notes}")
    else:
        lines.append("- Structural Notes: _unavailable in this run_")
    conflicting_signals = section.get("conflicting_signals")
    if isinstance(conflicting_signals, list) and conflicting_signals:
        lines.append("- Conflicting Signals:")
        for entry in conflicting_signals:
            lines.append(f"    - {_as_str(entry)}")
    else:
        lines.append("- Conflicting Signals: _none reported_")
    assumptions = section.get("assumptions")
    if isinstance(assumptions, list) and assumptions:
        lines.append("- Assumptions:")
        for entry in assumptions:
            lines.append(f"    - {_as_str(entry)}")
    else:
        lines.append("- Assumptions: _none reported_")
    key_levels = section.get("key_levels")
    if isinstance(key_levels, Mapping):
        lines.append("- Key Levels:")
        lines.append(f"    - Pivot: `{_as_str(key_levels.get('pivot_level'))}`")
        supports = key_levels.get("support_levels")
        if isinstance(supports, list) and supports:
            lines.append(
                "    - Supports: "
                + ", ".join(f"`{_as_str(level)}`" for level in supports)
            )
        else:
            lines.append("    - Supports: _none_")
        resistances = key_levels.get("resistance_levels")
        if isinstance(resistances, list) and resistances:
            lines.append(
                "    - Resistances: "
                + ", ".join(f"`{_as_str(level)}`" for level in resistances)
            )
        else:
            lines.append("    - Resistances: _none_")
    else:
        lines.append("- Key Levels: _unavailable in this run_")
    return lines


def _render_decision_review_trade_thesis(section: object) -> list[str]:
    lines = ["", "### Trade Thesis"]
    if not isinstance(section, Mapping) or section.get("available") is not True:
        message = (
            section.get("unavailable_message") if isinstance(section, Mapping) else None
        )
        lines.append(
            f"- _{_as_str(message, default='Engine narrative unavailable in this run.')}_"
        )
        return lines
    is_no_trade = section.get("is_no_trade") is True
    lines.append(f"- Stage C Outcome: `{_as_str(section.get('outcome'))}`")
    if is_no_trade:
        lines.append(
            f"- No-Trade Reason: `{_as_str(section.get('no_trade_reason'), default='unavailable')}`"
        )
        lines.append(
            "- _NO_TRADE is a first-class outcome. The engine did not propose a setup for this run._"
        )
        rationale = section.get("rationale")
        if isinstance(rationale, str) and rationale:
            lines.append(f"- Rationale: {rationale}")
        return lines
    lines.append(f"- Direction: `{_as_str(section.get('direction'))}`")
    lines.append(f"- Setup Class: `{_as_str(section.get('setup_class'))}`")
    lines.append(f"- Entry Price: `{_as_str(section.get('entry_price'))}`")
    lines.append(f"- Stop Price: `{_as_str(section.get('stop_price'))}`")
    lines.append(f"- Target 1: `{_as_str(section.get('target_1'))}`")
    target_2 = section.get("target_2")
    lines.append(
        f"- Target 2: `{_as_str(target_2)}`"
        if target_2 is not None
        else "- Target 2: _none (single-position target_1 only)_"
    )
    lines.append(f"- Position Size: `{_as_str(section.get('position_size'))}`")
    lines.append(f"- Risk ($): `{_as_str(section.get('risk_dollars'))}`")
    lines.append(f"- Reward/Risk Ratio: `{_as_str(section.get('reward_risk_ratio'))}`")
    lines.append(
        f"- Hold Time Estimate (min): `{_as_str(section.get('hold_time_estimate_minutes'))}`"
    )
    rationale = section.get("rationale")
    if isinstance(rationale, str) and rationale:
        lines.append(f"- Rationale: {rationale}")
    else:
        lines.append("- Rationale: _unavailable in this run_")
    sizing_math = section.get("sizing_math")
    if isinstance(sizing_math, Mapping):
        lines.append("- Sizing Math:")
        for label, key in (
            ("Stop Distance (ticks)", "stop_distance_ticks"),
            ("Risk per Tick", "risk_per_tick"),
            ("Raw Risk ($)", "raw_risk_dollars"),
            ("Slippage Cost ($)", "slippage_cost_dollars"),
            ("Adjusted Risk ($)", "adjusted_risk_dollars"),
            ("Blended Target Distance (ticks)", "blended_target_distance_ticks"),
            ("Blended Reward ($)", "blended_reward_dollars"),
        ):
            lines.append(f"    - {label}: `{_as_str(sizing_math.get(key))}`")
    else:
        lines.append("- Sizing Math: _unavailable in this run_")
    return lines


def _render_decision_review_risk_authorization(section: object) -> list[str]:
    lines = ["", "### Risk Authorization"]
    if not isinstance(section, Mapping) or section.get("available") is not True:
        message = (
            section.get("unavailable_message") if isinstance(section, Mapping) else None
        )
        lines.append(
            f"- _{_as_str(message, default='Engine narrative unavailable in this run.')}_"
        )
        return lines
    lines.append(f"- Decision: `{_as_str(section.get('decision'))}`")
    rejection_reasons = section.get("rejection_reasons")
    if isinstance(rejection_reasons, list) and rejection_reasons:
        lines.append("- Rejection Reasons:")
        for reason in rejection_reasons:
            lines.append(f"    - {_as_str(reason)}")
    adjusted_position_size = section.get("adjusted_position_size")
    if adjusted_position_size is not None:
        lines.append(f"- Adjusted Position Size: `{_as_str(adjusted_position_size)}`")
    adjusted_risk_dollars = section.get("adjusted_risk_dollars")
    if adjusted_risk_dollars is not None:
        lines.append(f"- Adjusted Risk ($): `{_as_str(adjusted_risk_dollars)}`")
    remaining_daily = section.get("remaining_daily_risk_budget")
    if remaining_daily is not None:
        lines.append(f"- Remaining Daily Risk Budget ($): `{_as_str(remaining_daily)}`")
    remaining_aggregate = section.get("remaining_aggregate_risk_budget")
    if remaining_aggregate is not None:
        lines.append(
            f"- Remaining Aggregate Risk Budget ($): `{_as_str(remaining_aggregate)}`"
        )
    checks = section.get("checks")
    if isinstance(checks, list) and checks:
        lines.append("- Checks:")
        for check in checks:
            if not isinstance(check, Mapping):
                continue
            lines.append(
                f"    - [{_as_str(check.get('check_id'))}] {_as_str(check.get('check_name'))}: "
                f"`{_as_str(check.get('passed_text'))}` — {_as_str(check.get('detail'), default='no detail')}"
            )
    else:
        lines.append("- Checks: _unavailable in this run_")
    return lines


def _render_decision_review_invalidation(section: object) -> list[str]:
    lines = ["", "### What Would Invalidate This"]
    if not isinstance(section, Mapping) or section.get("available") is not True:
        message = (
            section.get("unavailable_message") if isinstance(section, Mapping) else None
        )
        lines.append(
            f"- _{_as_str(message, default='Disqualifiers list is unavailable for this run.')}_"
        )
        return lines
    disqualifiers = section.get("disqualifiers")
    if isinstance(disqualifiers, list) and disqualifiers:
        for token in disqualifiers:
            lines.append(f"- `{_as_str(token)}`")
    else:
        lines.append("- _none reported_")
    return lines
