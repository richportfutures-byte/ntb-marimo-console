from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BootstrapPlan:
    project_root: Path
    engine_root: Path
    venv_python: Path
    path_bootstrap_script: Path
    refresh_script: Path

    @property
    def commands(self) -> tuple[tuple[str, ...], ...]:
        return (
            ("python3", "-m", "venv", "--clear", "--system-site-packages", ".venv"),
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
        venv_python=resolved_project_root / ".venv" / "bin" / "python",
        path_bootstrap_script=resolved_project_root / "scripts" / "bootstrap_target_paths.py",
        refresh_script=resolved_project_root / "scripts" / "refresh_runtime_profile_artifacts.py",
    )
