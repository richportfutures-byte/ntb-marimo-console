from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _venv_python_relative_path() -> Path:
    if os.name == "nt":
        return Path(".venv") / "Scripts" / "python.exe"
    return Path(".venv") / "bin" / "python"


def _bootstrap_script_name() -> str:
    return "bootstrap_target_env.ps1" if os.name == "nt" else "bootstrap_target_env.sh"


def platform_bootstrap_command() -> str:
    if os.name == "nt":
        return r"powershell.exe -ExecutionPolicy Bypass -File .\scripts\bootstrap_target_env.ps1"
    return "./scripts/bootstrap_target_env.sh"


@dataclass(frozen=True)
class BootstrapPlan:
    project_root: Path
    engine_root: Path
    venv_python: Path
    bootstrap_script: Path
    path_bootstrap_script: Path
    refresh_script: Path

    @property
    def commands(self) -> tuple[tuple[str, ...], ...]:
        return (
            (platform_bootstrap_command(),),
            (str(self.venv_python), str(self.path_bootstrap_script)),
            (str(self.venv_python), str(self.refresh_script)),
        )


def build_bootstrap_plan(project_root: str | Path | None = None) -> BootstrapPlan:
    resolved_project_root = (
        Path(project_root).resolve()
        if project_root is not None
        else Path(__file__).resolve().parents[2]
    )
    engine_root = (resolved_project_root / "../../source/ntb_engine").resolve()
    return BootstrapPlan(
        project_root=resolved_project_root,
        engine_root=engine_root,
        venv_python=resolved_project_root / _venv_python_relative_path(),
        bootstrap_script=resolved_project_root / "scripts" / _bootstrap_script_name(),
        path_bootstrap_script=resolved_project_root / "scripts" / "bootstrap_target_paths.py",
        refresh_script=resolved_project_root / "scripts" / "refresh_runtime_profile_artifacts.py",
    )
