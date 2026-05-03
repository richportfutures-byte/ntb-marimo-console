from __future__ import annotations

import marimo as mo

app = mo.App(width="full")


@app.cell
def __() -> tuple[dict[str, object], str, str, str]:
    from ntb_marimo_console.launch_config import build_launch_artifacts_from_env

    launch = build_launch_artifacts_from_env(
        default_mode="preserved_engine",
        default_profile_id="preserved_es_phase1",
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
def __(shell: dict[str, object], mode: str, profile_id: str, contract: str) -> tuple[object]:
    from ntb_marimo_console.ui.marimo_phase1_renderer import render_phase1_console

    rendered = render_phase1_console(
        shell,
        heading=f"NTB Marimo Console | {contract} | {profile_id} | Preserved Engine",
        mode_summary=(
            "Compatibility entrypoint for the supported preserved profile.\n\n"
            f"- Launch mode: `{mode}`.\n"
            f"- Runtime profile: `{profile_id}`.\n"
            "- Uses `PreservedEngineBackend` for watchman and pipeline execution.\n"
            "- Loads the profile-bound default adapter unless `NTB_MODEL_ADAPTER_REF` overrides it.\n"
            "- Fails closed on unsupported profiles, missing artifacts, and invalid preserved configuration.\n"
            "- Run history remains fixture-backed.\n"
            "- No manual override and no live-backed Stage E ingestion."
        ),
    )
    rendered
    return (rendered,)


if __name__ == "__main__":
    app.run()
