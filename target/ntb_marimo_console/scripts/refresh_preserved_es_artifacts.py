from __future__ import annotations

from ntb_marimo_console.runtime_profiles import get_runtime_profile
from ntb_marimo_console.preserved_fixture_artifacts import write_preserved_fixture_artifacts

from pathlib import Path


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    fixtures_root = project_root / "fixtures" / "golden" / "phase1"
    profile = get_runtime_profile("preserved_es_phase1")
    write_preserved_fixture_artifacts(fixtures_root, profile=profile)
    print(f"Refreshed preserved artifacts for {profile.profile_id} under {fixtures_root}")


if __name__ == "__main__":
    main()
