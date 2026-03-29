from __future__ import annotations

from ntb_marimo_console_site import prepare_target_owned_marimo_env


try:
    prepare_target_owned_marimo_env()
except RuntimeError as exc:
    raise SystemExit(
        "NTB Marimo Console startup blocked: "
        + str(exc)
    ) from exc
