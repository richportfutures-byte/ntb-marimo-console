from __future__ import annotations

from ntb_marimo_console.windows_acceptance import (
    render_acceptance_report,
    run_windows_acceptance,
)


def main() -> int:
    report = run_windows_acceptance()
    print(render_acceptance_report(report))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
