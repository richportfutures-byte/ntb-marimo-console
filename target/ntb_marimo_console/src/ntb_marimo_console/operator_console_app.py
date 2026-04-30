import marimo

app = marimo.App(width="full")


@app.cell
def __():
    import marimo as mo

    from ntb_marimo_console.session_lifecycle import (
        clear_retained_evidence,
        load_session_lifecycle_from_env,
        reload_current_profile,
        request_query_action,
        reset_session,
        switch_profile,
    )

    get_lifecycle, set_lifecycle = mo.state(None)
    get_pending_profile_id, set_pending_profile_id = mo.state(None)
    lifecycle = get_lifecycle()
    if lifecycle is None:
        lifecycle = load_session_lifecycle_from_env(default_mode="fixture_demo")
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
        get_pending_profile_id,
        set_pending_profile_id,
        clear_retained_evidence,
        reload_current_profile,
        request_query_action,
        reset_session,
        switch_profile,
    )


@app.cell
def __(
    lifecycle,
    mo,
    reload_current_profile,
    request_query_action,
    reset_session,
    set_lifecycle,
    get_pending_profile_id,
    set_pending_profile_id,
    clear_retained_evidence,
    switch_profile,
):
    from collections.abc import Mapping as _Mapping

    shell = lifecycle.shell
    startup_panel = shell.get("startup")
    workflow_panel = shell.get("workflow")
    lifecycle_panel = shell.get("lifecycle")

    if not isinstance(startup_panel, _Mapping):
        startup_panel = {}
    if not isinstance(workflow_panel, _Mapping):
        workflow_panel = {}
    if not isinstance(lifecycle_panel, _Mapping):
        lifecycle_panel = {}

    query_available = workflow_panel.get("query_action_available") is True
    reset_available = lifecycle_panel.get("reset_available") is True
    reload_available = lifecycle_panel.get("reload_available") is True
    selected_profile_id = str(startup_panel.get("selected_profile_id", "<unresolved>"))
    supported_profiles = startup_panel.get("supported_profiles")
    profile_options: dict[str, str] = {}
    profile_label_by_id: dict[str, str] = {}
    if isinstance(supported_profiles, list):
        for item in supported_profiles:
            if not isinstance(item, _Mapping):
                continue
            profile_id = str(item.get("profile_id", "<unresolved>"))
            label = (
                f"{profile_id} | {item.get('profile_kind', item.get('runtime_mode', '<unresolved>'))} | "
                f"{item.get('contract', '<unresolved>')} | {item.get('session_date', '<unresolved>')}"
            )
            profile_options[label] = profile_id
            if profile_id not in profile_label_by_id:
                profile_label_by_id[profile_id] = label

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
    switch_target = profile_selector.value
    switch_available = bool(profile_options) and switch_target is not None and switch_target != selected_profile_id

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

    if switch_button.value and switch_available:
        switched = switch_profile(lifecycle, str(switch_target))
        set_lifecycle(switched)
        startup_after_switch = switched.shell.get("startup", {})
        if isinstance(startup_after_switch, _Mapping):
            pending_after_switch = startup_after_switch.get("selected_profile_id")
            if pending_after_switch is not None:
                set_pending_profile_id(str(pending_after_switch))
    elif clear_retained_button.value:
        set_lifecycle(clear_retained_evidence(lifecycle))
    elif reload_button.value and reload_available:
        set_lifecycle(reload_current_profile(lifecycle))
    elif reset_button.value and reset_available:
        set_lifecycle(reset_session(lifecycle))
    elif query_button.value and query_available:
        set_lifecycle(request_query_action(lifecycle))

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

    mode = str(startup_panel.get("runtime_mode", "<unresolved>"))
    profile_id = selected_profile_id
    contract = str(startup_panel.get("contract", "<unresolved>"))
    readiness_state = str(startup_panel.get("readiness_state", "<unresolved>"))
    running_as = str(startup_panel.get("running_as", "<unresolved>"))
    lifecycle_controls = mo.hstack([reload_button, reset_button], widths="equal")

    return (
        shell,
        mode,
        profile_id,
        contract,
        readiness_state,
        running_as,
        query_button,
        lifecycle_controls,
        profile_controls,
        evidence_controls,
    )


@app.cell
def __(shell, mode, profile_id, contract, readiness_state, running_as, lifecycle_controls, profile_controls, evidence_controls, query_button):
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
    return (rendered,)


if __name__ == "__main__":
    app.run()
