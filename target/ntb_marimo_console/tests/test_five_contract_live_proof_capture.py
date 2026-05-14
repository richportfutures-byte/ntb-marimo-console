from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Mapping
from pathlib import Path

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "capture_five_contract_live_proof.py"
AUDIT_DOC_PATH = Path(__file__).resolve().parents[1] / "docs" / "release_candidate_readiness_audit.md"
spec = importlib.util.spec_from_file_location("capture_five_contract_live_proof", SCRIPT_PATH)
capture = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["capture_five_contract_live_proof"] = capture
spec.loader.exec_module(capture)


FORBIDDEN_OUTPUT_FRAGMENTS = (
    "Authorization: Bearer",
    "Bearer ey",
    "access_token",
    "refresh_token",
    "app_key",
    "app_secret",
    "credential",
    "customerId",
    "correlId",
    "accountId",
    "schwabClientCustomerId",
    "schwabClientCorrelId",
    "streamer-api",
    "wss://",
    "https://",
)
FORBIDDEN_DOMAIN_FIELDS = ("broker", "order", "fill", "account", "p&l", "pnl")


def run_and_load(argv: tuple[str, ...], capsys: pytest.CaptureFixture[str]) -> tuple[int, dict[str, object]]:
    exit_code = capture.run(argv)
    output = capsys.readouterr().out
    return exit_code, json.loads(output)


def test_default_mode_is_non_live_and_fixture_safe(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code, artifact = run_and_load((), capsys)

    assert exit_code == 0
    assert artifact["mode"] == "fixture"
    assert artifact["operator_attested_live"] is False
    assert artifact["proof_verdict"] == "MANUAL_REQUIRED"
    assert artifact["fixture_verification"] == "FIXTURE_PASS"
    assert artifact["sensitive_output_scan"]["passed"] is True  # type: ignore[index]


def test_live_mode_requires_explicit_live_and_attestations(capsys: pytest.CaptureFixture[str]) -> None:
    exit_code, artifact = run_and_load(("--operator-attested-live",), capsys)

    assert exit_code == 0
    assert artifact["mode"] == "fixture"
    assert artifact["operator_attested_live"] is False

    exit_code, artifact = run_and_load(("--live",), capsys)

    assert exit_code == 2
    assert artifact["mode"] == "live"
    assert artifact["operator_attested_live"] is False
    assert artifact["proof_verdict"] == "MANUAL_REQUIRED"
    assert "operator_attested_live_required" in artifact["operator_input_gaps"]
    assert "levelone_missing_contracts:6E,CL,ES,MGC,NQ" in artifact["operator_input_gaps"]


def test_live_refusal_does_not_write_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output_path = tmp_path / "live-proof.json"

    exit_code, artifact = run_and_load(("--live", "--output", str(output_path)), capsys)

    assert exit_code == 2
    assert artifact["proof_verdict"] == "MANUAL_REQUIRED"
    assert not output_path.exists()


def test_fixture_output_can_write_only_after_sanitizer_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    output_path = tmp_path / "fixture-proof.json"

    exit_code, artifact = run_and_load(("--output", str(output_path)), capsys)

    assert exit_code == 0
    assert output_path.exists()
    written = json.loads(output_path.read_text(encoding="utf-8"))
    assert written == artifact
    assert written["sensitive_output_scan"]["status"] == "pass"


def test_final_target_universe_is_exact_and_zn_gc_are_excluded() -> None:
    artifact = capture.build_fixture_artifact(generated_at="2026-05-09T00:00:00+00:00")

    assert artifact["final_target_contracts"] == ["ES", "NQ", "CL", "6E", "MGC"]
    assert artifact["excluded_contracts"] == ["ZN", "GC"]
    assert "ZN" not in artifact["final_target_contracts"]
    assert "GC" not in artifact["final_target_contracts"]


def test_mgc_is_not_gc() -> None:
    artifact = capture.build_fixture_artifact(generated_at="2026-05-09T00:00:00+00:00")
    rows = artifact["per_contract_proof_rows"]

    assert "MGC" in artifact["final_target_contracts"]
    assert "GC" not in artifact["final_target_contracts"]
    assert any(row["contract"] == "MGC" for row in rows)
    assert not any(row["contract"] == "GC" for row in rows)


def test_fixture_output_cannot_satisfy_real_live_proof() -> None:
    artifact = capture.build_fixture_artifact(generated_at="2026-05-09T00:00:00+00:00")

    assert artifact["mode"] == "fixture"
    assert artifact["operator_attested_live"] is False
    assert artifact["proof_verdict"] != "PASS"
    assert artifact["fixture_verification"] == "FIXTURE_PASS"


def test_proof_artifact_schema_is_stable() -> None:
    artifact = capture.build_fixture_artifact(generated_at="2026-05-09T00:00:00+00:00")
    expected_keys = {
        "schema_name",
        "schema_version",
        "generated_at",
        "mode",
        "operator_attested_live",
        "final_target_contracts",
        "excluded_contracts",
        "services",
        "refresh_floor_seconds",
        "per_contract_proof_rows",
        "one_connection_discipline_observation",
        "repeated_refresh_no_relogin_observation",
        "no_fixture_fallback_after_live_failure_assertion",
        "fail_closed_query_readiness_assertion",
        "manual_only_execution_assertion",
        "preserved_engine_authority_assertion",
        "sensitive_output_scan",
        "proof_verdict",
        "fixture_verification",
        "limitations",
    }

    assert set(artifact) == expected_keys
    assert artifact["schema_name"] == "five_contract_schwab_live_proof_capture"
    assert artifact["schema_version"] == 1
    assert artifact["proof_verdict"] in capture.PROOF_VERDICTS
    row = artifact["per_contract_proof_rows"][0]
    assert set(row) == {
        "contract",
        "service",
        "status",
        "observed",
        "blocked",
        "source",
        "raw_data_recorded",
        "blocking_reasons",
    }


def test_sanitizer_rejects_forbidden_labels_and_secret_like_strings() -> None:
    with pytest.raises(capture.ArtifactSanitizationError):
        capture.validate_artifact_safe({"access_token": "redacted"})

    with pytest.raises(capture.ArtifactSanitizationError):
        capture.validate_artifact_safe({"safe": "Abcdefghijklmnopqrstuvwx123456"})

    with pytest.raises(capture.ArtifactSanitizationError):
        capture.validate_artifact_safe({"safe": "wss://example.invalid/path"})


def test_artifact_contains_no_sensitive_material_or_identifiers() -> None:
    rendered = json.dumps(capture.build_fixture_artifact(generated_at="2026-05-09T00:00:00+00:00"), sort_keys=True)

    for fragment in FORBIDDEN_OUTPUT_FRAGMENTS:
        assert fragment not in rendered


def test_no_broker_order_fill_account_or_pnl_fields_are_present() -> None:
    artifact = capture.build_fixture_artifact(generated_at="2026-05-09T00:00:00+00:00")
    flattened = "\n".join(_flatten_keys_and_values(artifact)).lower()

    for fragment in FORBIDDEN_DOMAIN_FIELDS:
        assert fragment not in flattened


def test_manual_only_execution_and_preserved_engine_authority_are_present() -> None:
    artifact = capture.build_fixture_artifact(generated_at="2026-05-09T00:00:00+00:00")

    assert artifact["manual_only_execution_assertion"]["asserted"] is True  # type: ignore[index]
    assert artifact["preserved_engine_authority_assertion"]["asserted"] is True  # type: ignore[index]


def test_no_fixture_fallback_after_live_failure_is_represented() -> None:
    artifact = capture.build_fixture_artifact(generated_at="2026-05-09T00:00:00+00:00")

    assert artifact["no_fixture_fallback_after_live_failure_assertion"]["asserted"] is True  # type: ignore[index]
    assert artifact["fail_closed_query_readiness_assertion"]["asserted"] is True  # type: ignore[index]


def test_release_audit_records_levelone_success_but_remains_conditionally_ready() -> None:
    audit_text = AUDIT_DOC_PATH.read_text(encoding="utf-8")

    assert "**Verdict: CONDITIONALLY READY**" in audit_text
    assert "market_data_received=yes" in audit_text
    assert "received_contracts_count=5" in audit_text
    assert "market_data_diagnostic=levelone_futures_updates_received" in audit_text
    assert "bounded LEVELONE_FUTURES delivery" in audit_text
    assert "chart_data_diagnostic=chart_futures_completed_five_minute_bars_received" in audit_text
    assert "Full live-session cockpit usability proof remains pending" in audit_text
    assert "scripts/capture_five_contract_live_proof.py" in audit_text
    assert "Production live readiness remains withheld" in audit_text
    assert "**Verdict: READY**" not in audit_text


def test_help_text_does_not_reveal_sensitive_paths_or_names(capsys: pytest.CaptureFixture[str]) -> None:
    parser = capture.build_parser()

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(["--help"])

    output = capsys.readouterr().out
    assert exc_info.value.code == 0
    assert "--live" in output
    assert "--output" in output
    for fragment in FORBIDDEN_OUTPUT_FRAGMENTS:
        assert fragment not in output


def _flatten_keys_and_values(value: object) -> tuple[str, ...]:
    items: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            items.append(str(key))
            items.extend(_flatten_keys_and_values(item))
    elif isinstance(value, list | tuple):
        for item in value:
            items.extend(_flatten_keys_and_values(item))
    elif isinstance(value, str):
        items.append(value)
    return tuple(items)
