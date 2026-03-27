from __future__ import annotations

import site
from pathlib import Path


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    paths = (
        (project_root / "src").resolve(),
        (project_root / "../../source/ntb_engine/src").resolve(),
    )

    site_packages = None
    for candidate in site.getsitepackages():
        if candidate.endswith("site-packages"):
            site_packages = Path(candidate)
            break
    if site_packages is None:
        raise RuntimeError("Could not resolve site-packages for the target virtual environment.")

    pth_path = site_packages / "ntb_marimo_console_workspace_paths.pth"
    pth_path.write_text("".join(f"{path}\n" for path in paths), encoding="utf-8")
    print(f"Wrote workspace path bootstrap file to {pth_path}")


if __name__ == "__main__":
    main()
