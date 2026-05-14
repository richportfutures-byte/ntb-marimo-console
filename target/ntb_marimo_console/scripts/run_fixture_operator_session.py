from __future__ import annotations

import argparse
import json

from ntb_marimo_console.fixture_operator_session import (
    build_fixture_operator_session_summary,
    render_fixture_operator_session_text,
)

# Re-export at module level so existing importlib-based tests continue to work.
__all__ = [
    "build_fixture_operator_session_summary",
    "render_fixture_operator_session_text",
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="run_fixture_operator_session",
        description="Run a credential-free five-contract fixture operator session dry run.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit the sanitized session summary as JSON.",
    )
    args = parser.parse_args(argv)
    summary = build_fixture_operator_session_summary()
    if args.json:
        print(json.dumps(summary, indent=2, sort_keys=True))
    else:
        print(render_fixture_operator_session_text(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
