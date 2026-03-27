#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${PROJECT_ROOT}"

python3 -m venv --clear --system-site-packages .venv
.venv/bin/python scripts/bootstrap_target_paths.py
.venv/bin/python scripts/refresh_runtime_profile_artifacts.py

.venv/bin/python - <<'PY'
import marimo
import ntb_marimo_console
import ninjatradebuilder
import pydantic

print("marimo", marimo.__version__)
print("ntb_marimo_console", getattr(ntb_marimo_console, "__name__", "ntb_marimo_console"))
print("ninjatradebuilder", getattr(ninjatradebuilder, "__name__", "ninjatradebuilder"))
print("pydantic", pydantic.__version__)
PY
