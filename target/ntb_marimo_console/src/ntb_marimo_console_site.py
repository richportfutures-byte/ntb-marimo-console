from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TargetOwnedMarimoPaths:
    project_root: Path
    runtime_root: Path
    user_profile: Path
    xdg_config_home: Path
    xdg_cache_home: Path
    xdg_state_home: Path
    marimo_config_dir: Path
    marimo_config_file: Path
    marimo_cache_dir: Path
    marimo_state_dir: Path


def build_target_owned_marimo_paths(
    project_root: str | Path | None = None,
) -> TargetOwnedMarimoPaths:
    resolved_project_root = (
        Path(project_root).resolve()
        if project_root is not None
        else Path(__file__).resolve().parents[1]
    )
    runtime_root = resolved_project_root / ".state" / "marimo"
    user_profile = runtime_root / "user_profile"
    xdg_config_home = runtime_root / "xdg_config"
    xdg_cache_home = runtime_root / "xdg_cache"
    xdg_state_home = runtime_root / "xdg_state"
    marimo_config_dir = xdg_config_home / "marimo"
    marimo_config_file = marimo_config_dir / "marimo.toml"
    marimo_cache_dir = xdg_cache_home / "marimo"
    if os.name == "nt":
        marimo_state_dir = user_profile / ".marimo"
    else:
        marimo_state_dir = xdg_state_home / "marimo"
    return TargetOwnedMarimoPaths(
        project_root=resolved_project_root,
        runtime_root=runtime_root,
        user_profile=user_profile,
        xdg_config_home=xdg_config_home,
        xdg_cache_home=xdg_cache_home,
        xdg_state_home=xdg_state_home,
        marimo_config_dir=marimo_config_dir,
        marimo_config_file=marimo_config_file,
        marimo_cache_dir=marimo_cache_dir,
        marimo_state_dir=marimo_state_dir,
    )


def prepare_target_owned_marimo_env(
    project_root: str | Path | None = None,
) -> TargetOwnedMarimoPaths:
    paths = build_target_owned_marimo_paths(project_root)
    try:
        for directory in (
            paths.runtime_root,
            paths.user_profile,
            paths.xdg_config_home,
            paths.xdg_cache_home,
            paths.xdg_state_home,
            paths.marimo_config_dir,
            paths.marimo_cache_dir,
            paths.marimo_state_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        if not paths.marimo_config_file.exists():
            paths.marimo_config_file.touch()
    except OSError as exc:
        raise RuntimeError(
            "Target-owned Marimo runtime directories could not be prepared under "
            f"{paths.runtime_root}. The console will not fall back to the denied host-level "
            f"Marimo path. Detail: {exc}"
        ) from exc

    os.environ["XDG_CONFIG_HOME"] = str(paths.xdg_config_home)
    os.environ["XDG_CACHE_HOME"] = str(paths.xdg_cache_home)
    os.environ["XDG_STATE_HOME"] = str(paths.xdg_state_home)

    if os.name == "nt":
        user_profile = str(paths.user_profile)
        os.environ["USERPROFILE"] = user_profile
        os.environ["HOME"] = user_profile
        drive, tail = os.path.splitdrive(user_profile)
        os.environ["HOMEDRIVE"] = drive
        os.environ["HOMEPATH"] = tail if tail else "\\"

    return paths
