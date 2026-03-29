from __future__ import annotations

import os
import unittest
from pathlib import Path

from ntb_marimo_console.bootstrap import build_bootstrap_plan


class BootstrapPlanTests(unittest.TestCase):
    def test_bootstrap_plan_points_at_target_local_engine_and_refresh_script(self) -> None:
        plan = build_bootstrap_plan()
        project_root_posix = plan.project_root.as_posix()
        engine_root_posix = plan.engine_root.as_posix()
        bootstrap_path_posix = plan.path_bootstrap_script.as_posix()
        refresh_path_posix = plan.refresh_script.as_posix()

        self.assertTrue(project_root_posix.endswith("target/ntb_marimo_console"))
        self.assertTrue(engine_root_posix.endswith("source/ntb_engine"))
        self.assertEqual(
            plan.venv_python,
            plan.project_root / (Path(".venv/Scripts/python.exe") if os.name == "nt" else Path(".venv/bin/python")),
        )
        self.assertEqual(
            plan.bootstrap_script,
            plan.project_root
            / "scripts"
            / ("bootstrap_target_env.ps1" if os.name == "nt" else "bootstrap_target_env.sh"),
        )
        self.assertTrue(bootstrap_path_posix.endswith("scripts/bootstrap_target_paths.py"))
        self.assertTrue(refresh_path_posix.endswith("scripts/refresh_runtime_profile_artifacts.py"))
        self.assertEqual(
            plan.commands,
            (
                (
                    (r"powershell.exe -ExecutionPolicy Bypass -File .\scripts\bootstrap_target_env.ps1",)
                    if os.name == "nt"
                    else ("./scripts/bootstrap_target_env.sh",)
                ),
                (str(plan.venv_python), str(plan.path_bootstrap_script)),
                (str(plan.venv_python), str(plan.refresh_script)),
            ),
        )

    def test_bootstrap_scripts_exist(self) -> None:
        self.assertTrue(Path("scripts/bootstrap_target_env.sh").exists())
        self.assertTrue(Path("scripts/bootstrap_target_env.ps1").exists())


if __name__ == "__main__":
    unittest.main()
