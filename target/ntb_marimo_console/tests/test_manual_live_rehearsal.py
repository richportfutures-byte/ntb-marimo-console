from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_manual_live_rehearsal.py"
spec = importlib.util.spec_from_file_location("run_manual_live_rehearsal", SCRIPT_PATH)
rehearsal = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["run_manual_live_rehearsal"] = rehearsal
spec.loader.exec_module(rehearsal)


SENSITIVE_OUTPUT_FRAGMENTS = (
    "ACCESS_VALUE_PRIVATE",
    "REFRESH_VALUE_PRIVATE",
    "BEARER_VALUE_PRIVATE",
    "CUSTOMER_VALUE_PRIVATE",
    "CORREL_VALUE_PRIVATE",
    "ACCOUNT_VALUE_PRIVATE",
    "schwab_live.env",
    ".state/secrets",
    "token.json",
    "streamer-api.schwab.com",
    "wss://",
    "https://",
)


def check_by_name(report: object, name: str) -> object:
    for check in report.checks:
        if check.name == name:
            return check
    raise AssertionError(f"missing check {name}")


def test_default_behavior_remains_non_live_and_requires_explicit_mode(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = rehearsal.run(())

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "MANUAL_LIVE_REHEARSAL_BLOCKED" in output
    assert "explicit_rehearsal_mode_required" in output
    assert "mode=disabled" in output
    assert "--live" in output
    for fragment in SENSITIVE_OUTPUT_FRAGMENTS:
        assert fragment not in output


def test_fixture_rehearsal_passes_without_live_credentials(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = rehearsal.run(("--fixture",))

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "MANUAL_LIVE_REHEARSAL_FIXTURE_PASS" in output
    assert "contracts=ES,NQ,CL,6E,MGC" in output
    assert "services=LEVELONE_FUTURES,CHART_FUTURES" in output
    assert "refresh_floor_seconds=15" in output
    for fragment in SENSITIVE_OUTPUT_FRAGMENTS:
        assert fragment not in output


def test_live_mode_is_explicit_and_manual_checklist_only(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = rehearsal.run(("--live",))

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "MANUAL_LIVE_REHEARSAL_MANUAL_REQUIRED" in output
    assert "mode=manual_live" in output
    assert "manual_operator_observation" in output
    assert "contracts=ES,NQ,CL,6E,MGC" in output
    for fragment in SENSITIVE_OUTPUT_FRAGMENTS:
        assert fragment not in output


def test_final_target_universe_is_exact_and_zn_gc_are_not_supported() -> None:
    report = rehearsal.run_fixture_rehearsal("ready")
    unsupported = check_by_name(report, "no_unsupported_contract_ready_state")

    assert report.final_target_contracts == ("ES", "NQ", "CL", "6E", "MGC")
    assert "ZN" not in report.final_target_contracts
    assert "GC" not in report.final_target_contracts
    assert unsupported.status == "pass"
    assert any("excluded_contract_requested:ZN" in item for item in unsupported.details)
    assert any("never_supported_contract_requested:GC" in item for item in unsupported.details)


def test_one_connection_discipline_and_repeated_refresh_do_not_relogin() -> None:
    report = rehearsal.run_fixture_rehearsal("ready")
    connection = check_by_name(report, "one_stream_connection_discipline")
    refresh = check_by_name(report, "repeated_refresh_does_not_relogin")

    assert connection.status == "pass"
    assert "login_count=1" in connection.details
    assert "subscription_count=1" in connection.details
    assert refresh.status == "pass"
    assert "refresh_reads=3" in refresh.details
    assert "login_count=1" in refresh.details


@pytest.mark.parametrize("scenario", ("missing", "stale", "mismatch"))
def test_missing_stale_and_mismatched_fixture_data_blocks_readiness(scenario: str) -> None:
    report = rehearsal.run_fixture_rehearsal(scenario)
    blocked_data = check_by_name(report, "stale_missing_mismatched_data_fail_closed")
    cache_read = check_by_name(report, "cache_readable_for_operator_workspace")

    assert report.passed is True
    assert blocked_data.status == "pass"
    assert cache_read.status == "pass"
    assert "cache_or_live_observable_not_ready" in cache_read.blocking_reasons


def test_no_fixture_fallback_after_simulated_live_failure() -> None:
    report = rehearsal.run_fixture_rehearsal("live_failure")
    no_fallback = check_by_name(report, "simulated_live_failure_no_fixture_fallback")
    sanitized = check_by_name(report, "live_failure_sanitized")
    rendered = rehearsal.render_report(report)

    assert report.passed is True
    assert no_fallback.status == "pass"
    assert sanitized.status == "pass"
    assert "subscription_count=1" not in rendered
    assert "ACCESS_VALUE_PRIVATE" not in rendered
    assert "REFRESH_VALUE_PRIVATE" not in rendered
    assert "BEARER_VALUE_PRIVATE" not in rendered
    assert "CUSTOMER_VALUE_PRIVATE" not in rendered
    assert "Authorization: Bearer" not in rendered


def test_query_readiness_remains_fail_closed_without_deterministic_prerequisites() -> None:
    report = rehearsal.run_fixture_rehearsal("ready")
    gate = check_by_name(report, "no_false_query_ready")

    assert gate.status == "pass"
    assert "trigger_state_not_query_ready:DORMANT" in gate.details
    assert "manual_rehearsal_no_preserved_engine_query_ready" in gate.details


def test_json_output_is_sanitized_and_schema_is_visible(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = rehearsal.run(("--fixture", "--json"))

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "manual_live_rehearsal_v1" in output
    for fragment in SENSITIVE_OUTPUT_FRAGMENTS:
        assert fragment not in output


def test_mode_selection_rejects_fixture_and_live_together(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code = rehearsal.run(("--fixture", "--live"))

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "choose_fixture_or_live_not_both" in output
