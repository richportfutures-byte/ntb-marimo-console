from __future__ import annotations

import sys

from ntb_marimo_console.launch_config import build_preflight_report_from_env
from ntb_marimo_console.runtime_diagnostics import render_preflight_report


def main() -> int:
    report = build_preflight_report_from_env()
    print(render_preflight_report(report))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
