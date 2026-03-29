#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENGINE_ROOT="$(cd "${PROJECT_ROOT}/../../source/ntb_engine" && pwd)"
BOOTSTRAP_PYTHON="${NTB_BOOTSTRAP_PYTHON:-python3}"

cd "${PROJECT_ROOT}"

if ! command -v "${BOOTSTRAP_PYTHON}" >/dev/null 2>&1; then
  echo "Bootstrap Python not found: ${BOOTSTRAP_PYTHON}" >&2
  exit 1
fi

"${BOOTSTRAP_PYTHON}" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'
"${BOOTSTRAP_PYTHON}" -m venv --clear .venv
.venv/bin/python -m pip install --upgrade pip setuptools wheel
.venv/bin/python -m pip install -e "${ENGINE_ROOT}"
.venv/bin/python -m pip install -e ".[dev,preserved_engine]"
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
