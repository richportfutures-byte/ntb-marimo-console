from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


HARNESS_LABEL = "E1 release-candidate fixture-safe harness"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHONPATH_ENTRIES = ("src", "../../source/ntb_engine/src", ".")
PYTHONPATH_DISPLAY = "src:../../source/ntb_engine/src:."
D3_REHEARSAL_STATUS = (
    "D3 live rehearsal status: LEVELONE_FUTURES BOUNDED LIVE DELIVERY RECORDED; "
    "market_data_received=yes; received_contracts_count=5; "
    "CHART_FUTURES and production live Schwab readiness remain unproven."
)


@dataclass(frozen=True)
class ReleaseCandidateGroup:
    group_id: str
    label: str
    coverage: tuple[str, ...]
    test_files: tuple[str, ...]

    def command(self) -> tuple[str, ...]:
        return (sys.executable, "-m", "pytest", "-q", *self.test_files)


REQUIRED_RELEASE_CANDIDATE_SURFACES: tuple[str, ...] = (
    "contract_universe_guards",
    "runtime_profile_registry",
    "launch_default_non_live",
    "no_fixture_fallback_after_live_failure",
    "live_observable_schema",
    "stream_manager_cache",
    "chart_bar_builder",
    "trigger_state_engine",
    "pipeline_query_gate_provenance",
    "operator_cockpit_rendering",
    "blocked_state_display",
    "evidence_replay_attribution",
    "redaction",
    "d2_dry_run_non_live",
    "d3_partial_fail_closed_record",
)


RELEASE_CANDIDATE_GROUPS: tuple[ReleaseCandidateGroup, ...] = (
    ReleaseCandidateGroup(
        group_id="contract_universe_guards",
        label="Final target universe and excluded-contract guards",
        coverage=("contract_universe_guards",),
        test_files=(
            "tests/test_contract_universe.py",
            "tests/test_authority_contract_universe.py",
            "tests/test_contract_truth_audit.py",
        ),
    ),
    ReleaseCandidateGroup(
        group_id="runtime_launch_modes",
        label="Runtime profile registry, launch defaults, and live opt-in boundaries",
        coverage=(
            "runtime_profile_registry",
            "launch_default_non_live",
            "no_fixture_fallback_after_live_failure",
        ),
        test_files=(
            "tests/test_launch_config.py",
            "tests/test_market_data_config.py",
            "tests/test_runtime_profiles.py",
            "tests/test_runtime_preflight.py",
            "tests/test_runtime_modes_preserved.py",
            "tests/test_operator_live_runtime.py",
            "tests/test_operator_live_launcher.py",
        ),
    ),
    ReleaseCandidateGroup(
        group_id="stream_cache_observables_bars",
        label="Stream manager/cache, live observable schema, redaction, and bar builder",
        coverage=(
            "stream_manager_cache",
            "live_observable_schema",
            "chart_bar_builder",
            "redaction",
        ),
        test_files=(
            "tests/test_schwab_stream_manager_foundation.py",
            "tests/test_schwab_stream_client.py",
            "tests/test_schwab_streamer_session.py",
            "tests/test_futures_quote_service_config.py",
            "tests/test_futures_quote_service_factory.py",
            "tests/test_schwab_futures_market_data_adapter.py",
            "tests/test_live_observable_snapshot_v2.py",
            "tests/test_live_observables_surface.py",
            "tests/test_chart_futures_bar_builder.py",
        ),
    ),
    ReleaseCandidateGroup(
        group_id="trigger_query_gate_provenance",
        label="Trigger-state engine and pipeline query-gate provenance",
        coverage=(
            "trigger_state_engine",
            "pipeline_query_gate_provenance",
        ),
        test_files=(
            "tests/test_trigger_evaluator.py",
            "tests/test_trigger_state_engine.py",
            "tests/test_trigger_state_result_producer.py",
            "tests/test_pipeline_query_gate.py",
            "tests/test_phase1_pipeline_query_gate_wiring.py",
        ),
    ),
    ReleaseCandidateGroup(
        group_id="operator_cockpit_blocked_state",
        label="Operator cockpit rendering and blocked-state display",
        coverage=(
            "operator_cockpit_rendering",
            "blocked_state_display",
            "pipeline_query_gate_provenance",
        ),
        test_files=(
            "tests/test_operator_workspace.py",
            "tests/test_marimo_phase1_renderer.py",
        ),
    ),
    ReleaseCandidateGroup(
        group_id="evidence_replay_attribution",
        label="Session evidence, cockpit events, replay attribution, and review surfaces",
        coverage=(
            "evidence_replay_attribution",
            "operator_cockpit_rendering",
            "redaction",
        ),
        test_files=(
            "tests/test_session_evidence.py",
            "tests/test_session_evidence_store.py",
            "tests/test_session_lifecycle.py",
            "tests/test_evidence_replay.py",
            "tests/test_cockpit_event_evidence.py",
            "tests/test_trigger_transition_replay_source.py",
            "tests/test_trigger_transition_narrative.py",
            "tests/test_decision_review_replay.py",
            "tests/test_performance_review.py",
        ),
    ),
    ReleaseCandidateGroup(
        group_id="rehearsal_safety_and_release_record",
        label="D2 dry-run safety, D3 partial/fail-closed record, and harness integrity",
        coverage=(
            "d2_dry_run_non_live",
            "d3_partial_fail_closed_record",
            "launch_default_non_live",
            "no_fixture_fallback_after_live_failure",
            "redaction",
        ),
        test_files=(
            "tests/test_manual_live_rehearsal.py",
            "tests/test_run_operator_live_runtime_rehearsal.py",
            "tests/test_chart_futures_live_proof_preconditions.py",
            "tests/test_five_contract_live_proof_capture.py",
            "tests/test_release_candidate_readiness_audit.py",
            "tests/test_release_candidate_cut.py",
            "tests/test_non_live_acceptance_harness.py",
        ),
    ),
)


def canonical_pytest_files() -> tuple[str, ...]:
    files: list[str] = []
    for group in RELEASE_CANDIDATE_GROUPS:
        files.extend(group.test_files)
    return tuple(files)


def canonical_commands() -> tuple[tuple[str, ...], ...]:
    return tuple(group.command() for group in RELEASE_CANDIDATE_GROUPS)


def covered_surfaces() -> tuple[str, ...]:
    return tuple(sorted({surface for group in RELEASE_CANDIDATE_GROUPS for surface in group.coverage}))


def render_plan() -> str:
    lines = [
        HARNESS_LABEL,
        "Default mode: credential-free fixture-safe release-candidate verification only.",
        f"PYTHONPATH={PYTHONPATH_DISPLAY}",
        D3_REHEARSAL_STATUS,
        "",
    ]
    for group in RELEASE_CANDIDATE_GROUPS:
        lines.append(f"[{group.group_id}] {group.label}")
        lines.append("  coverage: " + ", ".join(group.coverage))
        lines.append("  " + " ".join(group.command()))
    return "\n".join(lines)


def _pythonpath_for_env(existing: str | None) -> str:
    prefix = os.pathsep.join(PYTHONPATH_ENTRIES)
    if not existing:
        return prefix
    return f"{prefix}{os.pathsep}{existing}"


def run_group(group: ReleaseCandidateGroup) -> int:
    print(f"\n=== {group.label} ===", flush=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = _pythonpath_for_env(env.get("PYTHONPATH"))
    completed = subprocess.run(group.command(), cwd=PROJECT_ROOT, env=env, check=False)
    return completed.returncode


def run_all() -> int:
    print(HARNESS_LABEL, flush=True)
    print("Default mode: credential-free fixture-safe release-candidate verification only.", flush=True)
    print(f"PYTHONPATH={PYTHONPATH_DISPLAY}", flush=True)
    print(D3_REHEARSAL_STATUS, flush=True)
    failures: list[tuple[str, int]] = []
    for group in RELEASE_CANDIDATE_GROUPS:
        return_code = run_group(group)
        if return_code != 0:
            failures.append((group.group_id, return_code))
    if failures:
        print("\nFAILED release-candidate groups:", flush=True)
        for group_id, return_code in failures:
            print(f"- {group_id}: exit {return_code}", flush=True)
        return 1
    print("\nAll release-candidate groups passed.", flush=True)
    return 0


def parse_args(argv: tuple[str, ...]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=HARNESS_LABEL)
    parser.add_argument("--list", action="store_true", help="Print the release-candidate plan without running pytest.")
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
