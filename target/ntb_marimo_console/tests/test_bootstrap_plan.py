from __future__ import annotations

import unittest
from pathlib import Path

from ntb_marimo_console.bootstrap import build_bootstrap_plan


class BootstrapPlanTests(unittest.TestCase):
    def test_bootstrap_plan_points_at_target_local_engine_and_refresh_script(self) -> None:
        plan = build_bootstrap_plan()

        self.assertTrue(str(plan.project_root).endswith("target/ntb_marimo_console"))
        self.assertTrue(str(plan.engine_root).endswith("source/ntb_engine"))
        self.assertTrue(str(plan.path_bootstrap_script).endswith("scripts/bootstrap_target_paths.py"))
        self.assertTrue(str(plan.refresh_script).endswith("scripts/refresh_runtime_profile_artifacts.py"))
        self.assertEqual(
            plan.commands,
            (
                ("python3", "-m", "venv", "--clear", "--system-site-packages", ".venv"),
                (str(plan.venv_python), str(plan.path_bootstrap_script)),
                (str(plan.venv_python), str(plan.refresh_script)),
            ),
        )

    def test_bootstrap_script_exists(self) -> None:
        script = Path("scripts/bootstrap_target_env.sh")
        self.assertTrue(script.exists())


if __name__ == "__main__":
    unittest.main()
