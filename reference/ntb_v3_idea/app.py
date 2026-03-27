import marimo

__generated_with = "0.8.0"
app = marimo.App(width="full", app_title="NinjaTradeBuilder v3")


@app.cell
def _imports():
    import marimo as mo
    import json
    import os
    from pathlib import Path
    from datetime import datetime, timezone
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    return mo, json, os, Path, datetime, timezone, sys


@app.cell
def _styles(mo):
    mo.md("""
    <style>
    .ntb-header {
        background: linear-gradient(135deg, #1a1f2e 0%, #0d1117 100%);
        border: 1px solid #30363d; border-radius: 8px;
        padding: 20px 28px; margin-bottom: 16px;
    }
    .ntb-header h1 { margin:0; font-size:1.4rem; color:#448aff; letter-spacing:2px; }
    .ntb-header p  { margin:4px 0 0; font-size:0.78rem; color:#90a4ae; }
    .ntb-card { background:#161b22; border:1px solid #30363d; border-radius:8px; padding:16px 20px; margin-bottom:12px; }
    .ntb-card h3 { margin:0 0 12px; font-size:0.85rem; color:#90a4ae; text-transform:uppercase; letter-spacing:1px; }
    .trigger-box { background:#1c2233; border-left:3px solid #ffc400; padding:10px 14px; margin:8px 0; border-radius:0 4px 4px 0; font-size:0.85rem; }
    .trigger-label { color:#ffc400; font-size:0.7rem; text-transform:uppercase; margin-bottom:4px; }
    .thesis-long  { border-left:3px solid #00c853; background:#0d1f0d; padding:10px 14px; margin:6px 0; border-radius:0 4px 4px 0; font-size:0.85rem; }
    .thesis-short { border-left:3px solid #ff1744; background:#1f0d0d; padding:10px 14px; margin:6px 0; border-radius:0 4px 4px 0; font-size:0.85rem; }
    .stage-flow { display:flex; gap:4px; align-items:center; margin:12px 0; flex-wrap:wrap; }
    .stage-box { padding:6px 14px; border-radius:4px; font-size:0.78rem; font-weight:bold; text-align:center; min-width:70px; }
    .s-pass { background:#1a3a1a; border:1px solid #00c853; color:#00c853; }
    .s-fail { background:#3a1a1a; border:1px solid #ff1744; color:#ff1744; }
    .s-skip { background:#1a1a1a; border:1px solid #30363d; color:#90a4ae; }
    .s-arrow { color:#30363d; font-size:1.2rem; margin:0 2px; }
    </style>
    """)


@app.cell
def _header(mo):
    mo.md("""
    <div class="ntb-header">
      <h1>⚡ NINJATRADEBUILDER v3</h1>
      <p>Staged · Fail-Closed · Gemini-Powered · Pre-Market Condition Framework</p>
    </div>
    """)


@app.cell
def _api_check(mo, os):
    _api_ok = bool(os.environ.get("GEMINI_API_KEY"))
    _api_status = mo.md("<small style='color:#30363d'>API key loaded ✓</small>") if _api_ok else mo.callout(
        mo.md("**GEMINI_API_KEY not set.**\n\nRun in terminal:\n```\nexport GEMINI_API_KEY=your-api-key-here\n```\nThen restart the app. Readiness Matrix works without it."),
        kind="warn"
    )
    _api_status


# ---------------------------------------------------------------------------
# Packet loader
# ---------------------------------------------------------------------------
@app.cell
def _packet_controls(mo, Path):
    _default_dir = str(Path(__file__).parent / "data")
    _default_path = str(Path(__file__).parent / "data" / "sample_packet.json")

    packet_path = mo.ui.text(value=_default_path, label="Packet JSON path", full_width=True)
    file_browser = mo.ui.file_browser(
        initial_path=_default_dir,
        filetypes=[".json"],
        multiple=False,
        label="Or browse for a packet file:",
    )

    mo.vstack([
        mo.md('<div class="ntb-card"><h3>📂 Packet Data</h3>'),
        packet_path,
        mo.md("---"),
        file_browser,
        mo.md("</div>"),
    ])
    return (file_browser, packet_path)


@app.cell
def _resolve_packet_path(file_browser, packet_path):
    # If a file was selected via the browser, use that; otherwise use the text input
    if file_browser.value:
        resolved_packet_path = str(file_browser.path(index=0))
    else:
        resolved_packet_path = packet_path.value
    return (resolved_packet_path,)


@app.cell
def _load_packet(resolved_packet_path, json, Path):
    from pipeline.schemas import PacketBundle
    try:
        _data = json.loads(Path(resolved_packet_path).read_text())
        bundle = PacketBundle(**_data)
        load_error = None
    except Exception as _e:
        bundle = None
        load_error = str(_e)
    return bundle, load_error, PacketBundle


@app.cell
def _show_load_error(mo, load_error):
    if load_error:
        mo.output.replace(mo.callout(mo.md(f"Packet load error: `{load_error}`"), kind="danger"))


# ---------------------------------------------------------------------------
# Mode selector
# ---------------------------------------------------------------------------
@app.cell
def _mode_selector(mo):
    mode = mo.ui.radio(
        options={
            "📋 Pre-Market Brief": "premarket",
            "🔁 Live Pipeline":    "pipeline",
            "📡 Readiness Matrix": "matrix",
        },
        value="📋 Pre-Market Brief",
        label="**Select Mode**",
    )
    mode
    return (mode,)


# ---------------------------------------------------------------------------
# READINESS MATRIX
# ---------------------------------------------------------------------------
@app.cell
def _matrix(mo, mode, bundle):
    mo.stop(mode.value != "matrix" or bundle is None)

    from pipeline.watchman import sweep_all
    _states = sweep_all(bundle)
    _icon = {"ready": "🟢", "caution": "🟡", "blocked": "🔴"}

    _rows = []
    for _c, _ws in _states.items():
        _rows.append({
            "Contract": _c,
            "Status": f"{_icon.get(_ws.overall_status,'⚪')} {_ws.overall_status.upper()}",
            "VWAP":  _ws.vwap_posture.replace("_"," "),
            "Value": _ws.value_location.replace("_"," "),
            "Level": _ws.level_proximity.replace("_"," "),
            "Delta": _ws.delta_posture,
            "Events": _ws.event_risk,
            "Macro":  _ws.macro_state or "—",
            "Lockouts": " | ".join(_ws.hard_lockout_flags) or "—",
            "Missing":  " | ".join(_ws.missing_context) or "—",
        })

    mo.vstack([
        mo.md('<div class="ntb-card"><h3>📡 Readiness Matrix — Deterministic Pre-Flight (No LLM)</h3></div>'),
        mo.ui.table(_rows),
    ])


# ---------------------------------------------------------------------------
# PRE-MARKET BRIEF
# ---------------------------------------------------------------------------
@app.cell
def _premarket_controls(mo, mode, bundle):
    mo.stop(mode.value != "premarket")

    _available = list(bundle.packets.keys()) if bundle else ["ES","NQ","CL","ZN","6E","MGC"]
    pm_contracts = mo.ui.multiselect(options=_available, value=[_available[0]], label="Contracts")
    pm_run = mo.ui.run_button(label="⚡ Generate Pre-Market Brief", kind="success")

    mo.vstack([
        mo.md('<div class="ntb-card"><h3>📋 Pre-Market Condition Framework</h3>'),
        mo.md("*Reads prior-day packet data → generates field-specific structural briefings + explicit query triggers.*"),
        mo.hstack([pm_contracts, pm_run], gap=2, align="end"),
        mo.md("</div>"),
    ])
    return pm_contracts, pm_run


@app.cell
def _run_premarket(mo, mode, bundle, pm_contracts, pm_run):
    mo.stop(mode.value != "premarket" or pm_run is None or not pm_run.value)

    if bundle is None:
        pm_briefs = {"error": "No packet loaded"}
    else:
        from pipeline.watchman import sweep_all as _sweep_all_pm
        from pipeline.premarket import generate_premarket_brief

        _ws_states = _sweep_all_pm(bundle)
        _selected = pm_contracts.value if pm_contracts else []
        pm_briefs = {}

        with mo.status.spinner(title="Generating pre-market briefs via Gemini..."):
            for _contract in _selected:
                _packet = bundle.packets.get(_contract)
                _ext = bundle.extensions.get(_contract, {})
                _ws = _ws_states.get(_contract)
                try:
                    pm_briefs[_contract] = generate_premarket_brief(
                        contract=_contract,
                        packet=_packet,
                        ext=_ext,
                        session_date=bundle.session_date,
                        watchman_state=_ws,
                    )
                except Exception as _e:
                    pm_briefs[_contract] = _e

    return (pm_briefs,)


@app.cell
def _show_premarket(mo, mode, pm_briefs):
    mo.stop(mode.value != "premarket")

    if not pm_briefs:
        mo.output.replace(mo.md("*Select contracts and press **Generate Pre-Market Brief**.*"))
    else:
        _cells = []
        for _contract, _brief in pm_briefs.items():
            if isinstance(_brief, Exception):
                _cells.append(mo.callout(mo.md(f"**{_contract}** — error: `{_brief}`"), kind="danger"))
                continue

            # Key levels table
            _lvl_rows = [
                {"Field": f"`{l.level_name}`", "Value": str(l.value), "Why It Matters": l.significance}
                for l in _brief.key_structural_levels
            ]

            # Trigger blocks
            _trigger_html = "".join([
                f'<div class="trigger-box"><div class="trigger-label">⚡ Query Trigger</div>'
                f'{t.condition}'
                f'{f" → <strong>{t.level_or_value}</strong>" if t.level_or_value else ""}'
                f'<br><small style="color:#90a4ae">Check: {", ".join(t.schema_fields)}</small></div>'
                for t in _brief.query_triggers
            ])

            _watch_md = "\n".join(f"- {w}" for w in _brief.watch_for)

            _cells.append(mo.vstack([
                mo.md(f"""
<div class="ntb-card">
<h3>📊 {_contract} — Pre-Market Brief &nbsp;<small style="color:#90a4ae; font-weight:normal">{_brief.session_date}</small></h3>
<p><strong>Framework:</strong> {_brief.analytical_framework}</p>
<p><strong>Current Structure:</strong> {_brief.current_structure_summary}</p>
</div>
                """),
                mo.ui.table(_lvl_rows, label=f"{_contract} Key Structural Levels") if _lvl_rows else mo.md(""),
                mo.md(f"""
<div class="ntb-card">
<div style="margin-bottom:12px">
  <div style="font-size:0.72rem;color:#90a4ae;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px">Long Thesis</div>
  <div class="thesis-long">{_brief.long_thesis or "No long thesis — structural conditions not supportive."}</div>
</div>
<div>
  <div style="font-size:0.72rem;color:#90a4ae;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px">Short Thesis</div>
  <div class="thesis-short">{_brief.short_thesis or "No short thesis — structural conditions not supportive."}</div>
</div>
</div>
                """),
                mo.md(f"""
<div class="ntb-card">
<h3>⚡ Query Triggers — When to Send Updated Packet</h3>
{_trigger_html}
</div>
                """),
                mo.md(f"""
<div class="ntb-card">
<h3>👁 Watch For</h3>

{_watch_md}

<p style="margin-top:12px;font-size:0.75rem;color:#90a4ae">
<strong>Schema fields referenced:</strong> {", ".join(f"`{f}`" for f in _brief.schema_fields_referenced)}
</p>
</div>
                """),
            ]))

        mo.output.replace(mo.vstack(_cells))


# ---------------------------------------------------------------------------
# LIVE PIPELINE
# ---------------------------------------------------------------------------
@app.cell
def _pipeline_controls(mo, mode, bundle):
    mo.stop(mode.value != "pipeline")

    _available = list(bundle.packets.keys()) if bundle else ["ES"]
    pl_contract = mo.ui.dropdown(options=_available, value=_available[0], label="Contract")
    pl_run = mo.ui.run_button(label="▶ Run Pipeline A→B→C→D", kind="warn")

    mo.vstack([
        mo.md('<div class="ntb-card"><h3>🔁 Full Pipeline Run</h3>'),
        mo.md("*Fail-closed: each stage gate must pass before the next runs. NO_TRADE is the expected majority outcome.*"),
        mo.hstack([pl_contract, pl_run], gap=2, align="end"),
        mo.md("</div>"),
    ])
    return pl_contract, pl_run


@app.cell
def _run_pipeline(mo, mode, bundle, pl_contract, pl_run):
    mo.stop(mode.value != "pipeline" or pl_run is None or not pl_run.value)

    if bundle is None:
        pl_result = None
        pl_error = "No packet loaded."
    else:
        from pipeline.stages import run_pipeline

        _contract = pl_contract.value if pl_contract else "ES"
        with mo.status.spinner(title=f"Running pipeline for {_contract}..."):
            try:
                pl_result = run_pipeline(_contract, bundle)
                pl_error = None
            except Exception as _e:
                pl_result = None
                pl_error = str(_e)

    return pl_result, pl_error


@app.cell
def _show_pipeline(mo, mode, pl_result, pl_error):
    mo.stop(mode.value != "pipeline")

    if pl_error:
        mo.output.replace(mo.callout(mo.md(f"Error: `{pl_error}`"), kind="danger"))
    elif pl_result is None:
        mo.output.replace(mo.md("*Select a contract and press **Run Pipeline**.*"))
    else:
        r = pl_result
        decision = r.final_decision or "UNKNOWN"
        _dc = {"APPROVED":"#00c853","REJECTED":"#ff1744","NO_TRADE":"#90a4ae",
               "NEED_INPUT":"#ffc400","INSUFFICIENT_DATA":"#ffc400","EVENT_LOCKOUT":"#ffc400","ERROR":"#ff1744"}
        _color = _dc.get(decision, "#90a4ae")

        # Stage flow
        _stages = ["STAGE_A","STAGE_B","STAGE_C","STAGE_D"]
        _term = r.termination_stage or ""
        _term_idx = next((i for i,s in enumerate(_stages) if s in _term), -1)

        def _sc(idx):
            if idx < _term_idx:
                return "s-pass"
            if idx == _term_idx:
                return "s-fail" if decision in ("REJECTED","NO_TRADE","ERROR","NEED_INPUT","INSUFFICIENT_DATA","EVENT_LOCKOUT") else "s-pass"
            return "s-skip"

        _labels = ["A<br><small>Sufficiency</small>","B<br><small>Market Read</small>","C<br><small>Setup</small>","D<br><small>Risk Auth</small>"]
        _flow = "".join(
            f'<div class="stage-box {_sc(i)}">{_labels[i]}</div>' + ('<span class="s-arrow">→</span>' if i < 3 else "")
            for i in range(4)
        )
        _flow += f'<span class="s-arrow">→</span><div class="stage-box" style="background:#1a2040;border:2px solid {_color};color:{_color};font-size:0.9rem">{decision}</div>'

        _sections = [mo.md(f"""
<div class="ntb-card">
<h3>{r.contract} — Run {r.run_id} &nbsp;<small style="font-weight:normal;color:#90a4ae">{r.started_at}</small></h3>
<div class="stage-flow">{_flow}</div>
Terminated at: <strong>{r.termination_stage}</strong>
{f"<br>⚠️ Error: {r.error}" if r.error else ""}
</div>
        """)]

        if r.sufficiency:
            s = r.sufficiency
            _sc_color = "#00c853" if s.status == "READY" else "#ff1744"
            _sections.append(mo.md(f"""
<div class="ntb-card">
<h3>Stage A — Sufficiency Gate</h3>
Status: <strong style="color:{_sc_color}">{s.status}</strong> &nbsp;|&nbsp;
Packet age: {f"{s.packet_age_seconds:.0f}s" if s.packet_age_seconds else "unknown"} &nbsp;|&nbsp;
Challenge valid: {"✅" if s.challenge_state_valid else "❌"}
{"<br>Missing fields: `" + "`, `".join(s.missing_fields) + "`" if s.missing_fields else ""}
{"<br>Disqualifiers: " + "; ".join(s.disqualifiers) if s.disqualifiers else ""}
{"<br>Lockout: " + s.event_lockout_detail if s.event_lockout_detail else ""}
{"<br>Notes: " + s.notes if s.notes else ""}
</div>
            """))

        if r.analysis:
            a = r.analysis
            _bc = {"LONG":"#00c853","SHORT":"#ff1744","NEUTRAL":"#90a4ae","CONFLICTED":"#ffc400"}.get(a.directional_bias or "", "#90a4ae")
            _sections.append(mo.md(f"""
<div class="ntb-card">
<h3>Stage B — Market Read</h3>
Outcome: <strong>{a.outcome}</strong> &nbsp;|&nbsp;
Regime: `{a.market_regime or "—"}` &nbsp;|&nbsp;
Bias: <strong style="color:{_bc}">{a.directional_bias or "—"}</strong><br>
Evidence: <strong>{a.evidence_score or "—"}/10</strong> &nbsp;|&nbsp;
Confidence: <strong>{a.confidence_band or "—"}</strong><br>
{f"*{a.structural_notes}*" if a.structural_notes else ""}
{f"<br>Value context: {a.value_context}" if a.value_context else ""}
{f"<br>Conflicts: " + "; ".join(a.conflicting_signals) if a.conflicting_signals else ""}
{f"<br>No-trade reason: {a.no_trade_reason}" if a.no_trade_reason else ""}
</div>
            """))

        if r.setup:
            _s = r.setup
            if _s.outcome == "TRADE_PROPOSED":
                _dc2 = "#00c853" if _s.direction == "LONG" else "#ff1744"
                _sm = _s.sizing_math
                _sections.append(mo.md(f"""
<div class="ntb-card">
<h3>Stage C — Proposed Setup</h3>
Direction: <strong style="color:{_dc2}">{_s.direction}</strong> &nbsp;|&nbsp;
Class: `{_s.setup_class}` &nbsp;|&nbsp;
R:R: <strong>{f"{_s.reward_risk_ratio:.2f}:1" if _s.reward_risk_ratio else "—"}</strong><br>
Entry: <strong>{_s.entry_price}</strong> &nbsp;|&nbsp;
Stop: <strong>{_s.stop_price}</strong> &nbsp;|&nbsp;
T1: <strong>{_s.target_1}</strong> {f"| T2: **{_s.target_2}**" if _s.target_2 else ""}
{f"<br>{_sm.position_size} contracts | Stop: {_sm.stop_distance_ticks:.1f} ticks | Risk: ${_sm.adjusted_risk_dollars:.0f}" if _sm else ""}
{f"<br>*{_s.rationale}*" if _s.rationale else ""}
</div>
                """))
            else:
                _sections.append(mo.md(f"""
<div class="ntb-card">
<h3>Stage C — No Trade</h3>
{_s.no_trade_reason or "Setup did not meet requirements."}
{f"<br>Disqualifiers: " + "; ".join(_s.disqualifiers) if _s.disqualifiers else ""}
</div>
                """))

        if r.authorization:
            _auth = r.authorization
            _adc = "#00c853" if _auth.decision == "APPROVED" else "#ff1744"
            _check_rows = [
                {"#": c.check_id, "Check": c.name,
                 "Result": "✅ PASS" if c.passed else "❌ FAIL",
                 "Detail": c.detail}
                for c in _auth.checks
            ]
            _sections.append(mo.vstack([
                mo.md(f"""
<div class="ntb-card">
<h3>Stage D — Risk Authorization</h3>
Decision: <strong style="color:{_adc}">{_auth.decision}</strong>
{f"<br>Rejections: " + "; ".join(_auth.rejection_reasons) if _auth.rejection_reasons else ""}
{f"<br>Adjusted size: {_auth.adjusted_position_size} contracts" if _auth.adjusted_position_size else ""}
{f"<br>Notes: {_auth.notes}" if _auth.notes else ""}
</div>
                """),
                mo.ui.table(_check_rows, label="13 Risk Checks"),
            ]))

        mo.output.replace(mo.vstack(_sections))


if __name__ == "__main__":
    app.run()
