from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


HARNESS_LABEL = "R17 non-live/default-safe acceptance harness"
PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class VerificationGroup:
    group_id: str
    label: str
    test_files: tuple[str, ...]

    def command(self) -> tuple[str, ...]:
        return (sys.executable, "-m", "pytest", *self.test_files)


VERIFICATION_GROUPS: tuple[VerificationGroup, ...] = (
    VerificationGroup(
        group_id="contract_universe_and_exclusions",
        label="Final contract universe and excluded-contract guards",
        test_files=(
            "tests/test_contract_universe.py",
            "tests/test_authority_contract_universe.py",
            "tests/test_contract_truth_audit.py",
        ),
    ),
    VerificationGroup(
        group_id="default_non_live_launch_and_profiles",
        label="Fixture-safe non-live default launch and profile preflight",
        test_files=(
            "tests/test_launch_config.py",
            "tests/test_market_data_config.py",
            "tests/test_runtime_profiles.py",
            "tests/test_runtime_preflight.py",
        ),
    ),
    VerificationGroup(
        group_id="stream_cache_parser_redaction_non_live",
        label="Stream manager/cache/parser redaction and non-live behavior",
        test_files=(
            "tests/test_schwab_stream_manager_foundation.py",
            "tests/test_futures_quote_service_config.py",
            "tests/test_futures_quote_service_factory.py",
            "tests/test_schwab_futures_market_data_adapter.py",
        ),
    ),
    VerificationGroup(
        group_id="live_observables_and_bars",
        label="Live observable snapshot v2 and CHART_FUTURES bar builder",
        test_files=(
            "tests/test_live_observable_snapshot_v2.py",
            "tests/test_live_observables_surface.py",
            "tests/test_chart_futures_bar_builder.py",
        ),
    ),
    VerificationGroup(
        group_id="final_contract_live_workstation_foundations",
        label="ES/CL/NQ/6E/MGC live workstation fixture foundations",
        test_files=(
            "tests/test_es_live_workstation_foundation.py",
            "tests/test_cl_live_workstation_foundation.py",
            "tests/test_nq_live_workstation_foundation.py",
            "tests/test_6e_live_workstation_foundation.py",
            "tests/test_mgc_live_workstation_foundation.py",
        ),
    ),
    VerificationGroup(
        group_id="watchman_brief_foundations",
        label="Watchman brief and validator gate foundations",
        test_files=(
            "tests/test_watchman_brief_foundations.py",
            "tests/test_watchman_gate.py",
        ),
    ),
    VerificationGroup(
        group_id="trigger_and_query_fail_closed",
        label="Fail-closed trigger state and pipeline query gate behavior",
        test_files=(
            "tests/test_trigger_evaluator.py",
            "tests/test_trigger_state_engine.py",
            "tests/test_pipeline_query_gate.py",
        ),
    ),
    VerificationGroup(
        group_id="operator_workspace_replay_performance",
        label="Operator workspace, evidence replay, and performance review determinism",
        test_files=(
            "tests/test_operator_workspace.py",
            "tests/test_evidence_replay.py",
            "tests/test_performance_review.py",
        ),
    ),
)


def canonical_pytest_files() -> tuple[str, ...]:
    files: list[str] = []
    for group in VERIFICATION_GROUPS:
        files.extend(group.test_files)
    return tuple(files)


def canonical_commands() -> tuple[tuple[str, ...], ...]:
    return tuple(group.command() for group in VERIFICATION_GROUPS)


def render_plan() -> str:
    lines = [HARNESS_LABEL, "Default mode: non-live fixture-safe verification only.", ""]
    for group in VERIFICATION_GROUPS:
        lines.append(f"[{group.group_id}] {group.label}")
        lines.append("  " + " ".join(group.command()))
    return "\n".join(lines)


def run_group(group: VerificationGroup) -> int:
    print(f"\n=== {group.label} ===", flush=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = "src" if not env.get("PYTHONPATH") else f"src{os.pathsep}{env['PYTHONPATH']}"
    completed = subprocess.run(group.command(), cwd=PROJECT_ROOT, env=env, check=False)
    return completed.returncode


def run_all() -> int:
    print(HARNESS_LABEL, flush=True)
    print("Default mode: non-live fixture-safe verification only.", flush=True)
    failures: list[tuple[str, int]] = []
    for group in VERIFICATION_GROUPS:
        return_code = run_group(group)
        if return_code != 0:
            failures.append((group.group_id, return_code))
    if failures:
        print("\nFAILED non-live acceptance groups:", flush=True)
        for group_id, return_code in failures:
            print(f"- {group_id}: exit {return_code}", flush=True)
        return 1
    print("\nAll non-live acceptance groups passed.", flush=True)
    return 0


def parse_args(argv: tuple[str, ...]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=HARNESS_LABEL)
    parser.add_argument("--list", action="store_true", help="Print the canonical non-live acceptance plan without running pytest.")
    parser.add_argument("--dry-run", action="store_true", help="Alias for --list; does not run pytest.")
    return parser.parse_args(argv)


def main(argv: tuple[str, ...] | None = None) -> int:
    args = parse_args(tuple(sys.argv[1:] if argv is None else argv))
    if args.list or args.dry_run:
        print(render_plan())
        return 0
    return run_all()


if __name__ == "__main__":
    raise SystemExit(main())
