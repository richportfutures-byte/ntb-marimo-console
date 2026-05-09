from __future__ import annotations

import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from ntb_marimo_console.windows_acceptance import (
    AcceptanceCheck,
    AcceptanceReport,
    AcceptanceSection,
    RUN_HISTORY_AUDIT_REPLAY_REGRESSION_TARGETS,
    WATCHMAN_GATE_REGRESSION_TARGETS,
    _run_history_audit_replay_regression_check,
    _watchman_gate_regression_check,
    build_blocked_contract_audit_check,
    build_supported_listing_check,
    extract_profile_ids_from_listing,
    render_acceptance_report,
)


class WindowsAcceptanceTests(unittest.TestCase):
    def test_extract_profile_ids_from_listing_parses_expected_columns(self) -> None:
        output = "\n".join(
            [
                "fixture_es_demo\tmode=fixture_demo\tcontract=ES\tsession_date=2026-03-25\tadapter=n/a",
                "preserved_6e_phase1\tmode=preserved_engine\tcontract=6E\tsession_date=2026-01-14\tadapter=adapter_6e",
                "preserved_cl_phase1\tmode=preserved_engine\tcontract=CL\tsession_date=2026-01-14\tadapter=adapter_cl",
                "preserved_es_phase1\tmode=preserved_engine\tcontract=ES\tsession_date=2026-03-25\tadapter=adapter",
                "preserved_nq_phase1\tmode=preserved_engine\tcontract=NQ\tsession_date=2026-01-14\tadapter=adapter_nq",
                "preserved_zn_phase1\tmode=preserved_engine\tcontract=ZN\tsession_date=2026-01-14\tadapter=adapter_zn",
            ]
        )

        self.assertEqual(
            extract_profile_ids_from_listing(output),
            (
                "fixture_es_demo",
                "preserved_6e_phase1",
                "preserved_cl_phase1",
                "preserved_es_phase1",
                "preserved_nq_phase1",
                "preserved_zn_phase1",
            ),
        )

    def test_supported_listing_check_fails_on_registry_drift(self) -> None:
        output = "fixture_es_demo\tmode=fixture_demo\tcontract=ES\tsession_date=2026-03-25\tadapter=n/a"

        check = build_supported_listing_check(output)

        self.assertFalse(check.passed)
        self.assertIn("did not match", check.summary)

    def test_blocked_contract_audit_check_requires_expected_reason_categories(self) -> None:
        output = "\n".join(
            [
                "Preserved Contract Eligibility Audit",
                "Blocked:",
                "- MGC -> preserved_mgc_phase1: blocked_missing_numeric_cross_asset_source | blocked",
            ]
        )

        check = build_blocked_contract_audit_check(output)

        self.assertTrue(check.passed)
        self.assertIn("fail-closed reason categories", check.summary)

    def test_render_acceptance_report_is_categorized_and_readable(self) -> None:
        report = AcceptanceReport(
            generated_at_utc="2026-03-27T15:00:00Z",
            sections=(
                AcceptanceSection(
                    title="Environment / Bootstrap Status",
                    checks=(
                        AcceptanceCheck(
                            name="Bootstrap environment assumptions usable",
                            passed=True,
                            summary="Imports and target-owned Marimo paths are usable.",
                            details=("Interpreter: C:\\example\\.venv\\Scripts\\python.exe",),
                        ),
                    ),
                ),
                AcceptanceSection(
                    title="Watchman Gate Status",
                    checks=(
                        AcceptanceCheck(
                            name="Validator-driven Watchman gate regression slice passes",
                            passed=True,
                            summary="Watchman gate regression slice passed. 6 passed",
                        ),
                    ),
                ),
                AcceptanceSection(
                    title="Run History / Audit Replay Status",
                    checks=(
                        AcceptanceCheck(
                            name="JSONL-backed Run History / Audit Replay regression slice passes",
                            passed=True,
                            summary="Run History / Audit Replay regression slice passed. 10 passed",
                        ),
                    ),
                ),
                AcceptanceSection(
                    title="Launch-Path Status",
                    checks=(
                        AcceptanceCheck(
                            name="Bounded direct launch path is coherent",
                            passed=False,
                            summary="Bounded launch probe failed.",
                            command='cmd.exe /c "set NTB_CONSOLE_PROFILE=preserved_es_phase1 && ..."',
                        ),
                    ),
                ),
            ),
        )

        rendered = render_acceptance_report(report)

        self.assertIn("Overall Result: FAIL", rendered)
        self.assertIn("Environment / Bootstrap Status: PASS", rendered)
        self.assertIn("Watchman Gate Status: PASS", rendered)
        self.assertIn("Run History / Audit Replay Status: PASS", rendered)
        self.assertIn("Launch-Path Status: FAIL", rendered)
        self.assertIn("Command: cmd.exe /c", rendered)

    def test_watchman_gate_regression_check_runs_expected_pytest_slice(self) -> None:
        with patch(
            "ntb_marimo_console.windows_acceptance._run_python_command",
            return_value=subprocess.CompletedProcess(
                args=["pytest"],
                returncode=0,
                stdout="collected 6 items\n6 passed in 1.00s\n",
                stderr="",
            ),
        ) as run_command:
            check = _watchman_gate_regression_check(Path("C:/example"))

        self.assertTrue(check.passed)
        self.assertIn("tests\\test_watchman_gate.py", check.command or "")
        self.assertEqual(check.details, tuple(target.replace("/", "\\") for target in WATCHMAN_GATE_REGRESSION_TARGETS))
        run_command.assert_called_once_with(
            Path("C:/example"),
            ["-m", "pytest", *WATCHMAN_GATE_REGRESSION_TARGETS],
        )

    def test_run_history_audit_replay_regression_check_fails_closed(self) -> None:
        with patch(
            "ntb_marimo_console.windows_acceptance._run_python_command",
            return_value=subprocess.CompletedProcess(
                args=["pytest"],
                returncode=1,
                stdout="",
                stderr="assertion failed",
            ),
        ) as run_command:
            check = _run_history_audit_replay_regression_check(Path("C:/example"))

        self.assertFalse(check.passed)
        self.assertIn("regression pytest slice failed", check.summary)
        self.assertIn("assertion failed", "\n".join(check.details))
        self.assertEqual(check.details[0], "Exit code: 1")
        run_command.assert_called_once_with(
            Path("C:/example"),
            ["-m", "pytest", *RUN_HISTORY_AUDIT_REPLAY_REGRESSION_TARGETS],
        )


if __name__ == "__main__":
    unittest.main()
