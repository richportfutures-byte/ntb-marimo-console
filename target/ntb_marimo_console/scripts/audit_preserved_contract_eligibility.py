from __future__ import annotations

from ntb_marimo_console.preserved_contract_onboarding import (
    build_contract_eligibility_snapshot,
    render_contract_eligibility_report,
)


def main() -> None:
    snapshot = build_contract_eligibility_snapshot()
    print(render_contract_eligibility_report(snapshot))


if __name__ == "__main__":
    main()
