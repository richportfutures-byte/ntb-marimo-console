import marimo

app = marimo.App(width="full")


@app.cell
def __():
    from ntb_marimo_console.launch_config import build_launch_artifacts_from_env

    launch = build_launch_artifacts_from_env(
        default_mode="fixture_demo",
        default_profile_id="fixture_es_demo",
    )
    shell = launch.shell
    mode = launch.config.mode
    profile_id = launch.config.profile.profile_id
    contract = launch.config.profile.contract
    return (
        shell,
        mode,
        profile_id,
        contract,
    )


@app.cell
def __(shell, mode, profile_id, contract):
    from ntb_marimo_console.ui.marimo_phase1_renderer import render_phase1_console

    rendered = render_phase1_console(
        shell,
        heading=f"NTB Marimo Console | {contract} | {profile_id} | Fixture Demo",
        mode_summary=(
            "Profile-driven fixture console.\n\n"
            f"- Launch mode: `{mode}`.\n"
            f"- Runtime profile: `{profile_id}`.\n"
            "- Functional: pre-market brief, readiness matrix, live observables, "
            "trigger table, query action gating, Stage A/B/C/D decision review, "
            "fixture-backed run history.\n"
            "- Stubbed/frozen: no manual override, no live Stage E audit backend."
        ),
    )
    return (rendered,)


if __name__ == "__main__":
    app.run()
