from __future__ import annotations

from pathlib import Path

from ntb_marimo_console.preserved_fixture_artifacts import refresh_preserved_fixture_artifacts


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    fixtures_root = project_root / "fixtures" / "golden" / "phase1"
    refreshed = refresh_preserved_fixture_artifacts(fixtures_root)
    for profile_id in sorted(refreshed):
        print(f"Refreshed preserved artifacts for {profile_id} under {fixtures_root}")


if __name__ == "__main__":
    main()
