import marimo

app = marimo.App()


@app.cell
def __():
    import marimo as mo

    from ntb_marimo_console.session_lifecycle import (
        load_session_lifecycle_from_env,
        reload_current_profile,
        request_query_action,
        reset_session,
    )

    get_lifecycle, set_lifecycle = mo.state(None)
    lifecycle = get_lifecycle()
    if lifecycle is None:
        lifecycle = load_session_lifecycle_from_env(default_mode="fixture_demo")
        set_lifecycle(lifecycle)

    return (
        mo,
        lifecycle,
        set_lifecycle,
        reload_current_profile,
        request_query_action,
        reset_session,
    )


@app.cell
def __(lifecycle, mo, reload_current_profile, request_query_action, reset_session, set_lifecycle):
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

    if reload_button.value and reload_available:
        set_lifecycle(reload_current_profile(lifecycle))
    elif reset_button.value and reset_available:
        set_lifecycle(reset_session(lifecycle))
    elif query_button.value and query_available:
        set_lifecycle(request_query_action(lifecycle))

    return (
        shell,
        str(startup_panel.get("runtime_mode", "<unresolved>")),
        str(startup_panel.get("selected_profile_id", "<unresolved>")),
        str(startup_panel.get("contract", "<unresolved>")),
        str(startup_panel.get("readiness_state", "<unresolved>")),
        str(startup_panel.get("running_as", "<unresolved>")),
        query_button,
        mo.hstack([reload_button, reset_button], widths="equal"),
    )


@app.cell
def __(shell, mode, profile_id, contract, readiness_state, running_as, lifecycle_controls, query_button):
    from ntb_marimo_console.ui.marimo_phase1_renderer import render_phase1_console

    rendered = render_phase1_console(
        shell,
        heading=f"NTB Marimo Console | {profile_id} | {contract} | {readiness_state}",
        mode_summary=(
            "Explicit profile-driven operator console with startup preflight, in-session workflow gating, "
            "and repeatable manual lifecycle controls.\n\n"
            f"- Selected profile: `{profile_id}`.\n"
            f"- Runtime mode: `{mode}`.\n"
            f"- Running as: `{running_as}`.\n"
            "- Startup Status confirms whether the console is actually ready.\n"
            "- Session Lifecycle shows whether the current profile was freshly reloaded, reset, or left unchanged.\n"
            "- Session Workflow shows whether live query is blocked, eligible, requested, completed, or failed.\n"
            "- Reload Current Profile reruns preflight and reloads the declared source artifacts for the selected profile.\n"
            "- Reset Session clears bounded query state without changing the selected profile.\n"
            "- The live-query action runs only against the currently loaded bounded snapshot.\n"
            "- It does not place orders, imply fills, or bypass fail-closed gating.\n"
            "- Debug JSON stays secondary only."
        ),
        query_action_control=query_button,
        lifecycle_control_panel=lifecycle_controls,
    )
    return (rendered,)


if __name__ == "__main__":
    app.run()
