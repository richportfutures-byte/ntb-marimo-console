from __future__ import annotations

import subprocess
import sys

from scripts.verify_release_candidate import (
    D3_REHEARSAL_STATUS,
    HARNESS_LABEL,
    PYTHONPATH_DISPLAY,
    RELEASE_CANDIDATE_GROUPS,
    REQUIRED_RELEASE_CANDIDATE_SURFACES,
    canonical_commands,
    canonical_pytest_files,
    covered_surfaces,
    main,
    render_plan,
)


FORBIDDEN_COMMAND_FRAGMENTS = (
    "--live",
    "prepare_schwab_oauth_token",
    "probe_schwab",
    "run_schwab_market_data_live_harness",
    "run_manual_live_rehearsal.py --live",
    "run_operator_live_runtime_rehearsal.py --live",
    ".state",
    "secrets",
    "marimo run",
)


def test_release_candidate_harness_has_explicit_fixture_safe_label() -> None:
    assert HARNESS_LABEL == "E1 release-candidate fixture-safe harness"
    plan = render_plan()

    assert "credential-free fixture-safe release-candidate verification only" in plan
    assert f"PYTHONPATH={PYTHONPATH_DISPLAY}" in plan
    assert D3_REHEARSAL_STATUS in plan
    assert "PARTIAL / FAIL-CLOSED" in plan
    assert "production live Schwab readiness remains unproven" in plan


def test_release_candidate_harness_covers_required_surfaces() -> None:
    surfaces = covered_surfaces()

    for surface in REQUIRED_RELEASE_CANDIDATE_SURFACES:
        assert surface in surfaces


def test_release_candidate_harness_includes_core_release_readiness_tests() -> None:
    files = canonical_pytest_files()

    assert "tests/test_contract_universe.py" in files
    assert "tests/test_runtime_profiles.py" in files
    assert "tests/test_launch_config.py" in files
    assert "tests/test_runtime_modes_preserved.py" in files
    assert "tests/test_operator_live_runtime.py" in files
    assert "tests/test_schwab_stream_manager_foundation.py" in files
    assert "tests/test_schwab_streamer_session.py" in files
    assert "tests/test_live_observable_snapshot_v2.py" in files
    assert "tests/test_chart_futures_bar_builder.py" in files
    assert "tests/test_trigger_state_engine.py" in files
    assert "tests/test_trigger_state_result_producer.py" in files
    assert "tests/test_pipeline_query_gate.py" in files
    assert "tests/test_operator_workspace.py" in files
    assert "tests/test_marimo_phase1_renderer.py" in files
    assert "tests/test_evidence_replay.py" in files
    assert "tests/test_cockpit_event_evidence.py" in files
    assert "tests/test_trigger_transition_replay_source.py" in files


def test_release_candidate_harness_includes_d2_d3_and_redaction_safety_tests() -> None:
    files = canonical_pytest_files()

    assert "tests/test_manual_live_rehearsal.py" in files
    assert "tests/test_run_operator_live_runtime_rehearsal.py" in files
    assert "tests/test_five_contract_live_proof_capture.py" in files
    assert "tests/test_release_candidate_readiness_audit.py" in files
    assert "tests/test_release_candidate_cut.py" in files
    assert "tests/test_decision_review_replay.py" in files
    assert "tests/test_non_live_acceptance_harness.py" in files


def test_release_candidate_harness_excludes_live_probe_and_auth_tests() -> None:
    files = canonical_pytest_files()
    rendered = "\n".join(" ".join(command) for command in canonical_commands())

    assert "tests/test_prepare_schwab_oauth_token.py" not in files
    assert "tests/test_schwab_live_run_harness.py" not in files
    assert all("tests/test_probe_schwab" not in item for item in files)
    for fragment in FORBIDDEN_COMMAND_FRAGMENTS:
        assert fragment not in rendered


def test_release_candidate_harness_list_modes_do_not_execute_pytest(monkeypatch) -> None:
    calls: list[object] = []

    def fail_if_called(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        raise AssertionError("pytest execution should not happen in list mode")

    monkeypatch.setattr(subprocess, "run", fail_if_called)

    assert main(("--list",)) == 0
    assert main(("--dry-run",)) == 0
    assert calls == []


def test_each_release_candidate_command_uses_current_python_pytest_q_and_test_paths_only() -> None:
    for command in canonical_commands():
        assert command[0] == sys.executable
        assert command[1:4] == ("-m", "pytest", "-q")
        assert all(item.startswith("tests/test_") and item.endswith(".py") for item in command[4:])


def test_release_candidate_groups_are_named_unique_and_non_empty() -> None:
    group_ids = [group.group_id for group in RELEASE_CANDIDATE_GROUPS]

    assert RELEASE_CANDIDATE_GROUPS
    assert len(group_ids) == len(set(group_ids))
    for group in RELEASE_CANDIDATE_GROUPS:
        assert group.group_id
        assert group.label
        assert group.coverage
        assert group.test_files
