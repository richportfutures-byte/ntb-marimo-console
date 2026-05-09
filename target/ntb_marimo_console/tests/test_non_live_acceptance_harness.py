from __future__ import annotations

import subprocess
import sys

from scripts.verify_non_live_acceptance import (
    HARNESS_LABEL,
    VERIFICATION_GROUPS,
    canonical_commands,
    canonical_pytest_files,
    main,
    render_plan,
)


FORBIDDEN_COMMAND_FRAGMENTS = (
    "--live",
    "schwab_live.env",
    ".state/secrets",
    "prepare_schwab_oauth_token",
    "probe_schwab",
    "run_schwab_market_data_live_harness",
    "run_manual_live_rehearsal",
    "0DTE",
    "SPX",
    "marimo run",
)


def test_harness_has_explicit_non_live_default_safe_label() -> None:
    assert HARNESS_LABEL == "R17 non-live/default-safe acceptance harness"
    plan = render_plan()

    assert "non-live fixture-safe" in plan
    assert "Default mode" in plan


def test_harness_command_list_does_not_include_live_flags_or_secret_paths() -> None:
    rendered = "\n".join(" ".join(command) for command in canonical_commands())

    for fragment in FORBIDDEN_COMMAND_FRAGMENTS:
        assert fragment not in rendered


def test_harness_includes_contract_universe_tests() -> None:
    files = canonical_pytest_files()

    assert "tests/test_contract_universe.py" in files
    assert "tests/test_authority_contract_universe.py" in files
    assert "tests/test_contract_truth_audit.py" in files


def test_harness_includes_trigger_query_evidence_performance_slices() -> None:
    files = canonical_pytest_files()

    assert "tests/test_trigger_state_engine.py" in files
    assert "tests/test_pipeline_query_gate.py" in files
    assert "tests/test_operator_workspace.py" in files
    assert "tests/test_evidence_replay.py" in files
    assert "tests/test_performance_review.py" in files


def test_harness_includes_stream_live_observable_bar_builder_and_watchman_slices() -> None:
    files = canonical_pytest_files()

    assert "tests/test_schwab_stream_manager_foundation.py" in files
    assert "tests/test_live_observable_snapshot_v2.py" in files
    assert "tests/test_chart_futures_bar_builder.py" in files
    assert "tests/test_watchman_brief_foundations.py" in files
    assert "tests/test_watchman_gate.py" in files


def test_harness_includes_final_contract_workstation_foundations() -> None:
    files = canonical_pytest_files()

    assert "tests/test_es_live_workstation_foundation.py" in files
    assert "tests/test_cl_live_workstation_foundation.py" in files
    assert "tests/test_nq_live_workstation_foundation.py" in files
    assert "tests/test_6e_live_workstation_foundation.py" in files
    assert "tests/test_mgc_live_workstation_foundation.py" in files


def test_harness_excludes_live_probe_and_auth_tests() -> None:
    files = canonical_pytest_files()

    assert all("probe_schwab" not in item for item in files)
    assert "tests/test_prepare_schwab_oauth_token.py" not in files
    assert "tests/test_schwab_live_run_harness.py" not in files


def test_harness_can_run_in_list_mode_without_executing_pytest(monkeypatch) -> None:
    calls: list[object] = []

    def fail_if_called(*args: object, **kwargs: object) -> object:
        calls.append((args, kwargs))
        raise AssertionError("pytest execution should not happen in list mode")

    monkeypatch.setattr(subprocess, "run", fail_if_called)

    assert main(("--list",)) == 0
    assert main(("--dry-run",)) == 0
    assert calls == []


def test_each_harness_command_uses_current_python_pytest_and_test_paths_only() -> None:
    for command in canonical_commands():
        assert command[0] == sys.executable
        assert command[1:3] == ("-m", "pytest")
        assert all(item.startswith("tests/test_") and item.endswith(".py") for item in command[3:])


def test_harness_groups_are_named_and_non_empty() -> None:
    assert VERIFICATION_GROUPS
    for group in VERIFICATION_GROUPS:
        assert group.group_id
        assert group.label
        assert group.test_files
