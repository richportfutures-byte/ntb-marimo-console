from __future__ import annotations

import io
import json
from pathlib import Path

from ninjatradebuilder.audit_report import (
    build_audit_summary,
    load_audit_records,
    render_audit_summary,
    run_audit_report_cli,
)


def _write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, sort_keys=True))
            handle.write("\n")


def test_build_audit_summary_counts_expected_dimensions(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    _write_jsonl(
        audit_path,
        [
            {
                "requested_contract": "ES",
                "success": True,
                "termination_stage": "contract_market_read",
                "final_decision": "NO_TRADE",
                "error_category": None,
            },
            {
                "requested_contract": "ES",
                "success": False,
                "termination_stage": None,
                "final_decision": None,
                "error_category": "provider_error",
            },
            {
                "requested_contract": "CL",
                "success": True,
                "termination_stage": "risk_authorization",
                "final_decision": "TRADE_APPROVED",
                "error_category": None,
            },
        ],
    )

    summary = build_audit_summary(load_audit_records(audit_path))

    assert summary.total_runs == 3
    assert summary.success_count == 2
    assert summary.failure_count == 1
    assert summary.by_requested_contract == {"ES": 2, "CL": 1}
    assert summary.by_termination_stage == {
        "contract_market_read": 1,
        "risk_authorization": 1,
        "(none)": 1,
    }
    assert summary.by_final_decision == {
        "(none)": 1,
        "NO_TRADE": 1,
        "TRADE_APPROVED": 1,
    }
    assert summary.by_error_category == {
        "(none)": 2,
        "provider_error": 1,
    }


def test_render_audit_summary_is_concise_and_useful(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    _write_jsonl(
        audit_path,
        [
            {
                "requested_contract": "ES",
                "success": True,
                "termination_stage": "contract_market_read",
                "final_decision": "NO_TRADE",
                "error_category": None,
            },
            {
                "requested_contract": "NQ",
                "success": False,
                "termination_stage": None,
                "final_decision": None,
                "error_category": "config_error",
            },
        ],
    )

    summary = build_audit_summary(load_audit_records(audit_path))
    report = render_audit_summary(summary)

    assert "NinjaTradeBuilder Audit Summary" in report
    assert "Total runs: 2" in report
    assert "Success: 1" in report
    assert "Failure: 1" in report
    assert "By requested_contract:" in report
    assert "  ES: 1" in report
    assert "  NQ: 1" in report
    assert "By error_category:" in report
    assert "  config_error: 1" in report


def test_run_audit_report_cli_prints_summary(tmp_path: Path) -> None:
    audit_path = tmp_path / "audit.jsonl"
    _write_jsonl(
        audit_path,
        [
            {
                "requested_contract": "ES",
                "success": True,
                "termination_stage": "contract_market_read",
                "final_decision": "NO_TRADE",
                "error_category": None,
            },
        ],
    )

    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = run_audit_report_cli(
        ["--audit-log", str(audit_path)],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert "Total runs: 1" in stdout.getvalue()


def test_run_audit_report_cli_fails_for_missing_file(tmp_path: Path) -> None:
    missing_path = tmp_path / "missing.jsonl"
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = run_audit_report_cli(
        ["--audit-log", str(missing_path)],
        stdout=stdout,
        stderr=stderr,
    )

    assert exit_code == 2
    assert stdout.getvalue() == ""
    assert "Audit log does not exist" in stderr.getvalue()
