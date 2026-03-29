from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path


class PreservedEngineBoundaryTests(unittest.TestCase):
    def test_no_preserved_engine_files_are_modified(self) -> None:
        git = shutil.which("git")
        if git is None:
            self.skipTest("git is not available in the test environment")

        repo_root = Path(__file__).resolve().parents[3]
        result = subprocess.run(
            [git, "status", "--porcelain", "--", "source/ntb_engine"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(result.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
