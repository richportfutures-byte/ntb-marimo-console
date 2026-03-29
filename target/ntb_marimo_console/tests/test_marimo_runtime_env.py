from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ntb_marimo_console_site import (
    build_target_owned_marimo_paths,
    prepare_target_owned_marimo_env,
)


class MarimoRuntimeEnvTests(unittest.TestCase):
    def test_prepare_target_owned_marimo_env_sets_writable_target_owned_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            paths = prepare_target_owned_marimo_env(project_root=temp_dir)
            self.assertEqual(paths.runtime_root, Path(temp_dir).resolve() / ".state" / "marimo")
            self.assertTrue(paths.marimo_config_dir.is_dir())
            self.assertTrue(paths.marimo_cache_dir.is_dir())
            self.assertTrue(paths.marimo_state_dir.is_dir())
            self.assertTrue(paths.marimo_config_file.is_file())
            self.assertEqual(os.environ["XDG_CONFIG_HOME"], str(paths.xdg_config_home))
            self.assertEqual(os.environ["XDG_CACHE_HOME"], str(paths.xdg_cache_home))
            self.assertEqual(os.environ["XDG_STATE_HOME"], str(paths.xdg_state_home))
            if os.name == "nt":
                self.assertEqual(os.environ["USERPROFILE"], str(paths.user_profile))
                self.assertEqual(os.environ["HOME"], str(paths.user_profile))

    def test_prepare_target_owned_marimo_env_fails_readably(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch("pathlib.Path.touch", side_effect=OSError("touch blocked")):
                with self.assertRaises(RuntimeError) as exc_info:
                    prepare_target_owned_marimo_env(project_root=temp_dir)

        self.assertIn("could not be prepared", str(exc_info.exception))
        self.assertIn("will not fall back", str(exc_info.exception))

    def test_sitecustomize_bootstraps_target_owned_marimo_paths_for_python_process(self) -> None:
        project_root = Path(__file__).resolve().parents[1]
        expected = build_target_owned_marimo_paths(project_root=project_root)
        env = os.environ.copy()
        env["PYTHONPATH"] = "src"
        env["USERPROFILE"] = r"C:\Denied\UserProfile"
        env["XDG_CONFIG_HOME"] = r"C:\Denied\XDG\Config"
        env["XDG_CACHE_HOME"] = r"C:\Denied\XDG\Cache"

        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import json, os; "
                    "from pathlib import Path; "
                    "from marimo._utils.xdg import marimo_config_path, marimo_state_dir; "
                    "print(json.dumps({"
                    "'userprofile': os.environ.get('USERPROFILE'), "
                    "'xdg_config_home': os.environ.get('XDG_CONFIG_HOME'), "
                    "'xdg_cache_home': os.environ.get('XDG_CACHE_HOME'), "
                    "'xdg_state_home': os.environ.get('XDG_STATE_HOME'), "
                    "'config_path': str(marimo_config_path()), "
                    "'state_dir': str(marimo_state_dir())"
                    "}))"
                ),
            ],
            cwd=project_root,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )

        payload = json.loads(completed.stdout.strip())
        self.assertEqual(payload["xdg_config_home"], str(expected.xdg_config_home))
        self.assertEqual(payload["xdg_cache_home"], str(expected.xdg_cache_home))
        self.assertEqual(payload["xdg_state_home"], str(expected.xdg_state_home))
        self.assertEqual(payload["config_path"], str(expected.marimo_config_file))
        self.assertEqual(payload["state_dir"], str(expected.marimo_state_dir))
        if os.name == "nt":
            self.assertEqual(payload["userprofile"], str(expected.user_profile))
        self.assertEqual(completed.stderr.strip(), "")


if __name__ == "__main__":
    unittest.main()
