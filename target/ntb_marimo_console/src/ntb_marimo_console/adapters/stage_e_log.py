from __future__ import annotations

import os
from pathlib import Path

STAGE_E_LOG_ROOT_ENV = "NTB_STAGE_E_LOG_ROOT"
DEFAULT_STAGE_E_LOG_ROOT = Path(__file__).resolve().parents[3] / ".state" / "stage_e"


def resolve_stage_e_log_root(root: str | Path | None = None) -> Path:
    if root is not None:
        return Path(root)

    env_value = os.getenv(STAGE_E_LOG_ROOT_ENV)
    if env_value:
        return Path(env_value).expanduser()

    return DEFAULT_STAGE_E_LOG_ROOT


def resolve_stage_e_log_path(
    contract: str,
    *,
    root: str | Path | None = None,
) -> Path:
    return resolve_stage_e_log_root(root) / contract / "run_history.jsonl"
