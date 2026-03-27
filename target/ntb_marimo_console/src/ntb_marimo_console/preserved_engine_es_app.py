from __future__ import annotations

import marimo as mo

from ntb_marimo_console.launch_config import build_launch_artifacts_from_env
from ntb_marimo_console.ui.marimo_phase1_renderer import render_phase1_console

app = mo.App()


@app.cell
def __() -> tuple[dict[str, object], str, str, str]:
    launch = build_launch_artifacts_from_env(
        default_mode="preserved_engine",
        default_profile_id="preserved_es_phase1",
    )
    return (
        launch.shell,
        launch.config.mode,
        launch.config.profile.profile_id,
        launch.config.profile.contract,
    )


@app.cell
def __(shell: dict[str, object], mode: str, profile_id: str, contract: str) -> tuple[object]:
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
    return (rendered,)


if __name__ == "__main__":
    app.run()
