import marimo

app = marimo.App(width="full")


@app.cell
def __():
    import marimo as mo

    from ntb_marimo_console.active_trade import ActiveTradeRegistry
    from ntb_marimo_console.operator_live_runtime import (
        build_operator_runtime_snapshot_producer_from_env,
        operator_runtime_mode_from_env,
    )
    from ntb_marimo_console.session_lifecycle import (
        clear_retained_evidence,
        refresh_runtime_snapshot,
        load_session_lifecycle_from_env,
        reload_current_profile,
        request_query_action,
        reset_session,
        switch_profile,
    )

    get_lifecycle, set_lifecycle = mo.state(None)
    get_runtime_snapshot_producer, set_runtime_snapshot_producer = mo.state(None)
    get_pending_profile_id, set_pending_profile_id = mo.state(None)
    get_active_trade_registry, set_active_trade_registry = mo.state(None)
    runtime_snapshot_producer = get_runtime_snapshot_producer()
    if runtime_snapshot_producer is None:
        runtime_snapshot_producer = build_operator_runtime_snapshot_producer_from_env()
        set_runtime_snapshot_producer(runtime_snapshot_producer)
    active_trade_registry = get_active_trade_registry()
    if active_trade_registry is None:
        active_trade_registry = ActiveTradeRegistry()
        set_active_trade_registry(active_trade_registry)

    operator_runtime_mode = operator_runtime_mode_from_env()
    lifecycle = get_lifecycle()
    if lifecycle is None:
        lifecycle = load_session_lifecycle_from_env(
            default_mode="fixture_demo",
            runtime_snapshot_producer=runtime_snapshot_producer,
            operator_runtime_mode=operator_runtime_mode,
        )
        set_lifecycle(lifecycle)
        startup = lifecycle.shell.get("startup", {})
        if isinstance(startup, dict):
            _initial_profile_id = startup.get("selected_profile_id")
            if _initial_profile_id is not None:
                set_pending_profile_id(str(_initial_profile_id))

    return (
        mo,
        lifecycle,
        set_lifecycle,
        runtime_snapshot_producer,
        active_trade_registry,
        set_active_trade_registry,
        get_pending_profile_id,
        set_pending_profile_id,
        clear_retained_evidence,
        refresh_runtime_snapshot,
        reload_current_profile,
        request_query_action,
        reset_session,
        switch_profile,
    )


@app.cell
def __(
    active_trade_registry,
    lifecycle,
    mo,
    get_pending_profile_id,
    set_pending_profile_id,
):
    from collections.abc import Mapping as _Mapping

    controls_shell = lifecycle.shell
    controls_startup_panel = controls_shell.get("startup")
    controls_runtime_panel = controls_shell.get("runtime")
    controls_workflow_panel = controls_shell.get("workflow")
    controls_lifecycle_panel = controls_shell.get("lifecycle")

    if not isinstance(controls_startup_panel, _Mapping):
        controls_startup_panel = {}
    if not isinstance(controls_runtime_panel, _Mapping):
        controls_runtime_panel = {}
    if not isinstance(controls_workflow_panel, _Mapping):
        controls_workflow_panel = {}
    if not isinstance(controls_lifecycle_panel, _Mapping):
        controls_lifecycle_panel = {}

    query_available = controls_workflow_panel.get("query_action_available") is True
    reset_available = controls_lifecycle_panel.get("reset_available") is True
    reload_available = controls_lifecycle_panel.get("reload_available") is True
    selected_profile_id = str(controls_startup_panel.get("selected_profile_id", "<unresolved>"))
    supported_profiles = controls_startup_panel.get("supported_profiles")
    profile_options: dict[str, str] = {}
    profile_label_by_id: dict[str, str] = {}
    if isinstance(supported_profiles, list):
        for item in supported_profiles:
            if not isinstance(item, _Mapping):
                continue
            _option_profile_id = str(item.get("profile_id", "<unresolved>"))
            label = (
                f"{_option_profile_id} | {item.get('profile_kind', item.get('runtime_mode', '<unresolved>'))} | "
                f"{item.get('contract', '<unresolved>')} | {item.get('session_date', '<unresolved>')}"
            )
            profile_options[label] = _option_profile_id
            if _option_profile_id not in profile_label_by_id:
                profile_label_by_id[_option_profile_id] = label

    pending_profile_id = get_pending_profile_id()
    if pending_profile_id not in profile_label_by_id:
        pending_profile_id = selected_profile_id if selected_profile_id in profile_label_by_id else None
        if pending_profile_id is not None:
            set_pending_profile_id(pending_profile_id)
    pending_profile_label = profile_label_by_id.get(pending_profile_id) if pending_profile_id is not None else None

    profile_selector = mo.ui.dropdown(
        options=profile_options,
        value=pending_profile_label,
        label="Supported Profile",
        on_change=set_pending_profile_id,
        full_width=True,
    )
    switch_available = bool(profile_options) and pending_profile_id is not None and pending_profile_id != selected_profile_id

    query_button = mo.ui.run_button(
        label="Run bounded query for loaded snapshot",
        kind="success" if query_available else "neutral",
        disabled=not query_available,
        tooltip=(
            "Runs the bounded Phase 1 pipeline against the currently loaded snapshot."
            if query_available
            else "Live query is blocked until the current loaded snapshot is eligible."
        ),
        full_width=True,
    )
    reset_button = mo.ui.run_button(
        label="Reset Session",
        kind="warn" if reset_available else "neutral",
        disabled=not reset_available,
        tooltip=(
            "Clears the bounded query, Decision Review, and Audit / Replay state while keeping the current profile loaded."
            if reset_available
            else "Reset becomes available only after a valid profile context is loaded."
        ),
        full_width=True,
    )
    reload_button = mo.ui.run_button(
        label="Reload Current Profile",
        kind="neutral",
        disabled=not reload_available,
        tooltip=(
            "Reruns preflight and reloads the current profile from its declared artifact source."
            if reload_available
            else "Reload is unavailable until a supported profile is selected."
        ),
        full_width=True,
    )
    runtime_refresh = mo.ui.refresh(
        options=["15s"],
        default_interval="15s",
        label="Runtime Cache Refresh",
    )
    switch_button = mo.ui.run_button(
        label="Switch To Selected Profile",
        kind="neutral",
        disabled=not switch_available,
        tooltip=(
            "Reruns preflight and reloads the selected supported profile as a fresh session."
            if switch_available
            else "Select a different supported profile to run a profile switch."
        ),
        full_width=True,
    )
    clear_retained_button = mo.ui.run_button(
        label="Clear Retained Evidence",
        kind="warn",
        tooltip=(
            "Clears only the durable retained evidence file. "
            "Current-session evidence remains visible until restart or subsequent actions."
        ),
        full_width=True,
    )
    operator_live_mode = str(controls_runtime_panel.get("operator_live_runtime_mode", "SAFE_NON_LIVE"))
    active_trade_controls_enabled = operator_live_mode == "OPERATOR_LIVE_RUNTIME"
    active_trade_form = mo.ui.form(
        mo.ui.dictionary(
            {
                "contract": mo.ui.dropdown(
                    options=["ES", "NQ", "CL", "6E", "MGC"],
                    value="ES",
                    label="Contract",
                    full_width=True,
                ),
                "direction": mo.ui.radio(
                    options=["long", "short"],
                    value="long",
                    label="Direction",
                    inline=True,
                    disabled=not active_trade_controls_enabled,
                ),
                "entry_price": mo.ui.number(
                    start=0,
                    step=0.01,
                    value=None,
                    label="Entry Price",
                    full_width=True,
                    disabled=not active_trade_controls_enabled,
                ),
                "stop_loss": mo.ui.number(
                    start=0,
                    step=0.01,
                    value=None,
                    label="Stop Loss",
                    full_width=True,
                    disabled=not active_trade_controls_enabled,
                ),
                "target": mo.ui.number(
                    start=0,
                    step=0.01,
                    value=None,
                    label="Target",
                    full_width=True,
                    disabled=not active_trade_controls_enabled,
                ),
                "pipeline_result_id": mo.ui.text(
                    label="Thesis Result ID",
                    placeholder="optional pipeline result id",
                    full_width=True,
                    disabled=not active_trade_controls_enabled,
                ),
                "trigger_name": mo.ui.text(
                    label="Thesis Trigger",
                    placeholder="optional trigger name",
                    full_width=True,
                    disabled=not active_trade_controls_enabled,
                ),
                "trigger_state": mo.ui.text(
                    label="Thesis State",
                    placeholder="optional trigger state",
                    full_width=True,
                    disabled=not active_trade_controls_enabled,
                ),
                "operator_notes": mo.ui.text_area(
                    label="Operator Notes",
                    placeholder="optional notes",
                    rows=3,
                    full_width=True,
                    disabled=not active_trade_controls_enabled,
                ),
            }
        ),
        submit_button_label="Record Active Trade",
        submit_button_disabled=not active_trade_controls_enabled,
        clear_on_submit=True,
        show_clear_button=True,
        label="Record Active Trade",
    )
    open_trade_options = {
        f"{trade.contract} {trade.direction} @ {trade.entry_price} | {trade.trade_id}": trade.trade_id
        for trade in active_trade_registry.list(status="open")
    }
    active_trade_action_selector = mo.ui.dropdown(
        options=open_trade_options,
        value=None,
        label="Open Trade",
        full_width=True,
    )
    active_trade_close_button = mo.ui.run_button(
        label="Mark Closed",
        kind="neutral",
        disabled=not active_trade_controls_enabled or not bool(open_trade_options),
        tooltip="Records an operator annotation only. No order or broker action is sent.",
        full_width=True,
    )
    active_trade_stopped_button = mo.ui.run_button(
        label="Mark Stopped",
        kind="warn",
        disabled=not active_trade_controls_enabled or not bool(open_trade_options),
        tooltip="Records an operator annotation only. No order or broker action is sent.",
        full_width=True,
    )

    profile_controls = mo.vstack(
        [
            mo.md(
                "\n".join(
                    [
                        "## Profile Selector",
                        f"- Active Profile: `{selected_profile_id}`",
                        "- Only supported profiles are selectable here.",
                        "- A completed switch clears bounded query, Decision Review, and Audit / Replay state from the prior profile.",
                    ]
                )
            ),
            profile_selector,
            switch_button,
        ]
    )
    evidence_controls = mo.vstack(
        [
            mo.md(
                "\n".join(
                    [
                        "## Retained Evidence",
                        "- This control clears only the durable retained evidence ledger under the target-owned `.state` path.",
                        "- Current-session evidence remains readable in this app session until restart or subsequent actions.",
                    ]
                )
            ),
            clear_retained_button,
        ]
    )
    active_trade_controls = mo.vstack(
        [
            mo.md(
                "\n".join(
                    [
                        "## Active Trade Controls",
                        "- Records operator-entered trade annotations only.",
                        "- The console does not submit orders, execute trades, or contact a broker from this surface.",
                    ]
                )
            ),
            active_trade_form,
            active_trade_action_selector,
            mo.hstack([active_trade_close_button, active_trade_stopped_button], widths="equal"),
        ],
        gap=0.5,
    )

    lifecycle_controls = mo.vstack(
        [
            runtime_refresh,
            mo.hstack([reload_button, reset_button], widths="equal"),
        ]
    )

    return (
        controls_shell,
        controls_startup_panel,
        query_available,
        reset_available,
        reload_available,
        selected_profile_id,
        switch_available,
        profile_selector,
        query_button,
        reset_button,
        reload_button,
        runtime_refresh,
        switch_button,
        clear_retained_button,
        lifecycle_controls,
        profile_controls,
        evidence_controls,
        active_trade_form,
        active_trade_action_selector,
        active_trade_close_button,
        active_trade_stopped_button,
        active_trade_controls,
    )


@app.cell
def __(
    active_trade_action_selector,
    active_trade_close_button,
    active_trade_form,
    active_trade_registry,
    active_trade_stopped_button,
    clear_retained_button,
    clear_retained_evidence,
    controls_shell,
    controls_startup_panel,
    evidence_controls,
    lifecycle,
    lifecycle_controls,
    profile_controls,
    profile_selector,
    query_available,
    query_button,
    reload_available,
    reload_button,
    reload_current_profile,
    reset_available,
    reset_button,
    reset_session,
    runtime_refresh,
    refresh_runtime_snapshot,
    request_query_action,
    selected_profile_id,
    set_active_trade_registry,
    set_lifecycle,
    set_pending_profile_id,
    switch_available,
    switch_button,
    switch_profile,
):
    from collections.abc import Mapping as _Mapping
    from copy import deepcopy
    from datetime import datetime, timezone

    from ntb_marimo_console.active_trade import ThesisReference
    from ntb_marimo_console.market_data.stream_cache import StreamCacheSnapshot
    from ntb_marimo_console.market_data.stream_manager import StreamManagerSnapshot
    from ntb_marimo_console.viewmodels.mappers import active_trade_vms_from_registry

    current_lifecycle = lifecycle
    switch_target = profile_selector.value

    if switch_button.value and switch_available and switch_target is not None:
        switched = switch_profile(lifecycle, str(switch_target))
        set_lifecycle(switched)
        current_lifecycle = switched
        startup_after_switch = switched.shell.get("startup", {})
        if isinstance(startup_after_switch, _Mapping):
            pending_after_switch = startup_after_switch.get("selected_profile_id")
            if pending_after_switch is not None:
                set_pending_profile_id(str(pending_after_switch))
    elif clear_retained_button.value:
        current_lifecycle = clear_retained_evidence(lifecycle)
        set_lifecycle(current_lifecycle)
    elif reload_button.value and reload_available:
        current_lifecycle = reload_current_profile(lifecycle)
        set_lifecycle(current_lifecycle)
    elif reset_button.value and reset_available:
        current_lifecycle = reset_session(lifecycle)
        set_lifecycle(current_lifecycle)
    elif query_button.value and query_available:
        current_lifecycle = request_query_action(lifecycle)
        set_lifecycle(current_lifecycle)
    elif runtime_refresh.value:
        current_lifecycle = refresh_runtime_snapshot(lifecycle)
        set_lifecycle(current_lifecycle)

    submitted_trade = active_trade_form.value
    if isinstance(submitted_trade, _Mapping):
        entry_price = _positive_float_or_none(submitted_trade.get("entry_price"))
        if entry_price is not None:
            thesis_reference = _optional_thesis_reference(submitted_trade, ThesisReference)
            active_trade_registry.add(
                contract=str(submitted_trade.get("contract") or "ES"),
                direction=str(submitted_trade.get("direction") or "long"),
                entry_price=entry_price,
                stop_loss=_positive_float_or_none(submitted_trade.get("stop_loss")),
                target=_positive_float_or_none(submitted_trade.get("target")),
                thesis_reference=thesis_reference,
                operator_notes=str(submitted_trade.get("operator_notes") or ""),
            )
            set_active_trade_registry(active_trade_registry)

    selected_active_trade_id = active_trade_action_selector.value
    if (
        selected_active_trade_id is not None
        and active_trade_close_button.value
    ):
        active_trade_registry.close(
            str(selected_active_trade_id),
            status="closed",
            close_reason="operator_marked_closed",
        )
        set_active_trade_registry(active_trade_registry)
    elif (
        selected_active_trade_id is not None
        and active_trade_stopped_button.value
    ):
        active_trade_registry.close(
            str(selected_active_trade_id),
            status="stopped",
            close_reason="operator_marked_stopped",
        )
        set_active_trade_registry(active_trade_registry)

    shell = deepcopy(current_lifecycle.shell if current_lifecycle is not None else controls_shell)
    cache_snapshot = _cache_snapshot_from_runtime(current_lifecycle.runtime_snapshot, StreamManagerSnapshot)
    if cache_snapshot is None:
        cache_snapshot = StreamCacheSnapshot(
            generated_at=datetime.now(timezone.utc).isoformat(),
            provider="active_trade_surface",
            provider_status="blocked",
            cache_max_age_seconds=15.0,
            records=(),
            blocking_reasons=("active_trade_live_cache_unavailable",),
            stale_symbols=(),
        )
    active_trade_rows = [
        item.to_dict()
        for item in active_trade_vms_from_registry(active_trade_registry, cache_snapshot)
    ]
    shell["active_trades"] = {
        "status": "ready",
        "rows": active_trade_rows,
        "message": "Operator-recorded annotations only; P&L is a display calculation and execution remains manual.",
    }
    mode = str(controls_startup_panel.get("runtime_mode", "<unresolved>"))
    profile_id = selected_profile_id
    contract = str(controls_startup_panel.get("contract", "<unresolved>"))
    readiness_state = str(controls_startup_panel.get("readiness_state", "<unresolved>"))
    running_as = str(controls_startup_panel.get("running_as", "<unresolved>"))

    return (
        shell,
        mode,
        profile_id,
        contract,
        readiness_state,
        running_as,
    )


def _positive_float_or_none(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _optional_thesis_reference(values, thesis_reference_type):
    pipeline_result_id = str(values.get("pipeline_result_id") or "").strip()
    trigger_name = str(values.get("trigger_name") or "").strip()
    trigger_state = str(values.get("trigger_state") or "").strip()
    if not pipeline_result_id or not trigger_name or not trigger_state:
        return None
    return thesis_reference_type(
        pipeline_result_id=pipeline_result_id,
        trigger_name=trigger_name,
        trigger_state=trigger_state,
    )


def _cache_snapshot_from_runtime(runtime_snapshot, stream_manager_snapshot_type):
    if runtime_snapshot is None:
        return None
    if isinstance(runtime_snapshot, stream_manager_snapshot_type):
        return runtime_snapshot.cache
    return runtime_snapshot


@app.cell
def __(mo, shell, mode, profile_id, contract, readiness_state, running_as, lifecycle_controls, profile_controls, evidence_controls, active_trade_controls, query_button):
    from ntb_marimo_console.ui.marimo_phase1_renderer import (
        render_phase1_console,
        render_watchman_gate_stop_output,
    )

    stop_output = render_watchman_gate_stop_output(
        shell,
        heading="NTB Marimo Operator Console",
        mode_summary=(
            "Explicit profile-driven operator console with startup preflight, in-session workflow gating, "
            "and repeatable manual lifecycle controls.\n\n"
            f"- Selected profile: `{profile_id}`.\n"
            f"- Runtime mode: `{mode}`.\n"
            f"- Running as: `{running_as}`.\n"
            "- Startup Status confirms whether the console is actually ready.\n"
            "- Session Lifecycle shows whether the current profile was freshly reloaded, reset, or left unchanged.\n"
            "- Recent Session Evidence shows bounded, ordered evidence for the active and recently used profiles.\n"
            "- Restored Prior Run versus Current Session labels keep persisted evidence truthful across app restarts.\n"
            "- Session Workflow shows whether live query is blocked, eligible, requested, completed, or failed.\n"
            "- Supported Profile Operations lists all supported profiles plus blocked candidate contracts.\n"
            "- Profile Selector switches only between supported profiles and fails closed when validation does not complete.\n"
            "- Reload Current Profile reruns preflight and reloads the declared source artifacts for the selected profile.\n"
            "- Reset Session clears bounded query state without changing the selected profile.\n"
            "- The live-query action runs only against the currently loaded bounded snapshot.\n"
            "- It does not place orders, imply fills, or bypass fail-closed gating.\n"
            "- Debug JSON stays secondary only."
        ),
        lifecycle_control_panel=lifecycle_controls,
        profile_control_panel=profile_controls,
        evidence_control_panel=evidence_controls,
        active_trade_control_panel=active_trade_controls,
    )
    mo.stop(stop_output is not None, stop_output)

    rendered = render_phase1_console(
        shell,
        heading="NTB Marimo Operator Console",
        mode_summary=(
            "Explicit profile-driven operator console with startup preflight, in-session workflow gating, "
            "and repeatable manual lifecycle controls.\n\n"
            f"- Selected profile: `{profile_id}`.\n"
            f"- Runtime mode: `{mode}`.\n"
            f"- Running as: `{running_as}`.\n"
            "- Startup Status confirms whether the console is actually ready.\n"
            "- Session Lifecycle shows whether the current profile was freshly reloaded, reset, or left unchanged.\n"
            "- Recent Session Evidence shows bounded, ordered evidence for the active and recently used profiles.\n"
            "- Restored Prior Run versus Current Session labels keep persisted evidence truthful across app restarts.\n"
            "- Session Workflow shows whether live query is blocked, eligible, requested, completed, or failed.\n"
            "- Supported Profile Operations lists all supported profiles plus blocked candidate contracts.\n"
            "- Profile Selector switches only between supported profiles and fails closed when validation does not complete.\n"
            "- Reload Current Profile reruns preflight and reloads the declared source artifacts for the selected profile.\n"
            "- Reset Session clears bounded query state without changing the selected profile.\n"
            "- The live-query action runs only against the currently loaded bounded snapshot.\n"
            "- It does not place orders, imply fills, or bypass fail-closed gating.\n"
            "- Debug JSON stays secondary only."
        ),
        query_action_control=query_button,
        lifecycle_control_panel=lifecycle_controls,
        profile_control_panel=profile_controls,
        evidence_control_panel=evidence_controls,
    )
    rendered
    return (rendered,)


if __name__ == "__main__":
    app.run()
