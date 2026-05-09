from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final
from urllib.error import URLError
from urllib.request import urlopen

from .bootstrap import platform_bootstrap_command
from ntb_marimo_console_site import (
    TargetOwnedMarimoPaths,
    build_target_owned_marimo_paths,
    prepare_target_owned_marimo_env,
)

EXPECTED_SUPPORTED_PROFILE_IDS: Final[tuple[str, ...]] = (
    "fixture_es_demo",
    "preserved_6e_phase1",
    "preserved_cl_phase1",
    "preserved_es_phase1",
    "preserved_nq_phase1",
    "preserved_zn_phase1",
)
EXPECTED_BLOCKED_CONTRACTS: Final[dict[str, str]] = {
    "MGC": "blocked_missing_numeric_cross_asset_source",
}
WATCHMAN_GATE_REGRESSION_TARGETS: Final[tuple[str, ...]] = (
    "tests/test_watchman_gate.py",
)
RUN_HISTORY_AUDIT_REPLAY_REGRESSION_TARGETS: Final[tuple[str, ...]] = (
    "tests/test_stage_e_jsonl_store.py",
    "tests/test_runtime_modes_preserved.py",
)
EVIDENCE_REGRESSION_TARGETS: Final[tuple[str, ...]] = (
    "tests/test_session_evidence.py",
    "tests/test_session_evidence_store.py",
)
LAUNCH_PROBE_PROFILE_ID: Final[str] = "preserved_es_phase1"


@dataclass(frozen=True)
class AcceptanceCheck:
    name: str
    passed: bool
    summary: str
    details: tuple[str, ...] = ()
    command: str | None = None


@dataclass(frozen=True)
class AcceptanceSection:
    title: str
    checks: tuple[AcceptanceCheck, ...]

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)


@dataclass(frozen=True)
class AcceptanceReport:
    generated_at_utc: str
    sections: tuple[AcceptanceSection, ...]

    @property
    def passed(self) -> bool:
        return all(section.passed for section in self.sections)


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def run_windows_acceptance() -> AcceptanceReport:
    root = project_root()
    sections = (
        AcceptanceSection(
            title="Environment / Bootstrap Status",
            checks=(
                _environment_bootstrap_check(root),
            ),
        ),
        AcceptanceSection(
            title="Supported Profile Status",
            checks=(
                _supported_profile_listing_check(root),
                _supported_profile_preflight_check(root),
            ),
        ),
        AcceptanceSection(
            title="Blocked Contract Status",
            checks=(
                _blocked_contract_audit_check(root),
            ),
        ),
        AcceptanceSection(
            title="Watchman Gate Status",
            checks=(
                _watchman_gate_regression_check(root),
            ),
        ),
        AcceptanceSection(
            title="Run History / Audit Replay Status",
            checks=(
                _run_history_audit_replay_regression_check(root),
            ),
        ),
        AcceptanceSection(
            title="Evidence Lifecycle Status",
            checks=(
                _evidence_regression_check(root),
            ),
        ),
        AcceptanceSection(
            title="Launch-Path Status",
            checks=(
                _marimo_runtime_resolution_check(root),
                _bounded_direct_launch_check(root),
            ),
        ),
    )
    return AcceptanceReport(
        generated_at_utc=_utc_now_iso(),
        sections=sections,
    )


def render_acceptance_report(report: AcceptanceReport) -> str:
    lines = [
        "NTB Marimo Console Windows Acceptance",
        f"Generated At UTC: {report.generated_at_utc}",
        f"Overall Result: {'PASS' if report.passed else 'FAIL'}",
    ]
    for section in report.sections:
        lines.extend(
            [
                "",
                f"{section.title}: {'PASS' if section.passed else 'FAIL'}",
            ]
        )
        for check in section.checks:
            marker = "PASS" if check.passed else "FAIL"
            lines.append(f"- [{marker}] {check.name}: {check.summary}")
            if check.command is not None:
                lines.append(f"  Command: {check.command}")
            for detail in check.details:
                lines.append(f"  {detail}")
    return "\n".join(lines)


def extract_profile_ids_from_listing(output: str) -> tuple[str, ...]:
    profile_ids: list[str] = []
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        profile_ids.append(stripped.split("\t", 1)[0])
    return tuple(profile_ids)


def build_supported_listing_check(output: str) -> AcceptanceCheck:
    profile_ids = extract_profile_ids_from_listing(output)
    if profile_ids != EXPECTED_SUPPORTED_PROFILE_IDS:
        return AcceptanceCheck(
            name="Supported profiles listed",
            passed=False,
            summary=(
                "Supported profile listing did not match the current bounded registry. "
                f"Expected {EXPECTED_SUPPORTED_PROFILE_IDS}, got {profile_ids}."
            ),
            details=tuple(f"Listed profile: {profile_id}" for profile_id in profile_ids),
        )
    return AcceptanceCheck(
        name="Supported profiles listed",
        passed=True,
        summary="Supported profile listing matches the current bounded registry.",
        details=tuple(f"Listed profile: {profile_id}" for profile_id in profile_ids),
    )


def build_blocked_contract_audit_check(output: str) -> AcceptanceCheck:
    missing: list[str] = []
    for contract, reason in EXPECTED_BLOCKED_CONTRACTS.items():
        expected_fragment = f"- {contract} ->"
        if expected_fragment not in output or reason not in output:
            missing.append(f"{contract}={reason}")

    if missing:
        return AcceptanceCheck(
            name="Blocked contracts reported truthfully",
            passed=False,
            summary=(
                "Blocked contract audit output did not contain the expected fail-closed reason categories. "
                f"Missing: {', '.join(missing)}."
            ),
        )
    return AcceptanceCheck(
        name="Blocked contracts reported truthfully",
        passed=True,
        summary="Blocked contract audit output matches the current fail-closed reason categories.",
        details=tuple(
            f"{contract}: {reason}"
            for contract, reason in EXPECTED_BLOCKED_CONTRACTS.items()
        ),
    )


def _environment_bootstrap_check(root: Path) -> AcceptanceCheck:
    try:
        marimo_paths = prepare_target_owned_marimo_env(root)
        import marimo  # noqa: F401
        import ninjatradebuilder  # noqa: F401
        import ntb_marimo_console  # noqa: F401
        import pydantic  # noqa: F401
    except Exception as exc:
        return AcceptanceCheck(
            name="Bootstrap environment assumptions usable",
            passed=False,
            summary=(
                "Current acceptance interpreter could not load the required target dependencies "
                f"or prepare the target-owned Marimo runtime path. Detail: {exc}"
            ),
            details=(
                f"Bootstrap command: {platform_bootstrap_command()}",
                f"Interpreter: {sys.executable}",
            ),
        )

    return AcceptanceCheck(
        name="Bootstrap environment assumptions usable",
        passed=True,
        summary=(
            "Current interpreter imports the required packages and the target-owned Marimo runtime path is writable."
        ),
        details=_bootstrap_details(marimo_paths),
    )


def _supported_profile_listing_check(root: Path) -> AcceptanceCheck:
    command = _python_command_text("scripts\\list_runtime_profiles.py")
    result = _run_python_command(root, ["scripts/list_runtime_profiles.py"])
    if result.returncode != 0:
        return AcceptanceCheck(
            name="Supported profiles listed",
            passed=False,
            summary="Supported profile listing command failed.",
            details=_result_details(result),
            command=command,
        )
    check = build_supported_listing_check(result.stdout)
    return AcceptanceCheck(
        name=check.name,
        passed=check.passed,
        summary=check.summary,
        details=check.details,
        command=command,
    )


def _supported_profile_preflight_check(root: Path) -> AcceptanceCheck:
    details: list[str] = []
    for profile_id in EXPECTED_SUPPORTED_PROFILE_IDS:
        command = _python_command_text("scripts\\run_runtime_preflight.py", profile_id=profile_id)
        result = _run_python_command(
            root,
            ["scripts/run_runtime_preflight.py"],
            extra_env={"NTB_CONSOLE_PROFILE": profile_id},
        )
        if result.returncode != 0 or "Runtime Preflight: PASS" not in result.stdout:
            return AcceptanceCheck(
                name="Supported profile preflight passes",
                passed=False,
                summary=f"Strict preflight failed for supported profile {profile_id}.",
                details=(f"Profile: {profile_id}", *(_result_details(result))),
                command=command,
            )
        details.append(f"{profile_id}: Runtime Preflight: PASS")

    return AcceptanceCheck(
        name="Supported profile preflight passes",
        passed=True,
        summary="Strict preflight passes for every currently supported profile.",
        details=tuple(details),
    )


def _blocked_contract_audit_check(root: Path) -> AcceptanceCheck:
    command = _python_command_text("scripts\\audit_preserved_contract_eligibility.py")
    result = _run_python_command(root, ["scripts/audit_preserved_contract_eligibility.py"])
    if result.returncode != 0:
        return AcceptanceCheck(
            name="Blocked contracts reported truthfully",
            passed=False,
            summary="Blocked contract audit command failed.",
            details=_result_details(result),
            command=command,
        )
    check = build_blocked_contract_audit_check(result.stdout)
    return AcceptanceCheck(
        name=check.name,
        passed=check.passed,
        summary=check.summary,
        details=check.details,
        command=command,
    )


def _evidence_regression_check(root: Path) -> AcceptanceCheck:
    return _pytest_slice_check(
        root,
        name="Retained-evidence regression slice passes",
        summary_on_failure="Retained-evidence regression pytest slice failed.",
        summary_on_success_prefix="Retained-evidence regression slice passed.",
        targets=EVIDENCE_REGRESSION_TARGETS,
    )


def _watchman_gate_regression_check(root: Path) -> AcceptanceCheck:
    return _pytest_slice_check(
        root,
        name="Validator-driven Watchman gate regression slice passes",
        summary_on_failure="Watchman gate regression pytest slice failed.",
        summary_on_success_prefix="Watchman gate regression slice passed.",
        targets=WATCHMAN_GATE_REGRESSION_TARGETS,
    )


def _run_history_audit_replay_regression_check(root: Path) -> AcceptanceCheck:
    return _pytest_slice_check(
        root,
        name="JSONL-backed Run History / Audit Replay regression slice passes",
        summary_on_failure="Run History / Audit Replay regression pytest slice failed.",
        summary_on_success_prefix="Run History / Audit Replay regression slice passed.",
        targets=RUN_HISTORY_AUDIT_REPLAY_REGRESSION_TARGETS,
    )


def _marimo_runtime_resolution_check(root: Path) -> AcceptanceCheck:
    expected = build_target_owned_marimo_paths(root)
    command = (
        ".\\.venv\\Scripts\\python.exe -c \"from marimo._utils.xdg import marimo_config_path, marimo_state_dir; ...\""
    )
    env = _child_env(
        {
            "USERPROFILE": r"C:\Denied\UserProfile",
            "HOME": r"C:\Denied\UserProfile",
            "XDG_CONFIG_HOME": r"C:\Denied\XDG\Config",
            "XDG_CACHE_HOME": r"C:\Denied\XDG\Cache",
            "XDG_STATE_HOME": r"C:\Denied\XDG\State",
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json, os; "
                "from marimo._utils.xdg import marimo_config_path, marimo_state_dir; "
                "print(json.dumps({"
                "'userprofile': os.environ.get('USERPROFILE'), "
                "'xdg_config_home': os.environ.get('XDG_CONFIG_HOME'), "
                "'xdg_cache_home': os.environ.get('XDG_CACHE_HOME'), "
                "'xdg_state_home': os.environ.get('XDG_STATE_HOME'), "
                "'config_path': str(marimo_config_path()), "
                "'state_dir': str(marimo_state_dir())"
                "}))"
            ),
        ],
        cwd=root,
        env=env,
        capture_output=True,
        text=True,
        timeout=20,
    )
    if result.returncode != 0:
        return AcceptanceCheck(
            name="Target-owned Marimo runtime path resolves in a fresh process",
            passed=False,
            summary="Fresh-process Marimo runtime path resolution failed.",
            details=_result_details(result),
            command=command,
        )
    import json

    payload = json.loads(result.stdout.strip())
    expected_config = str(expected.marimo_config_file)
    expected_state = str(expected.marimo_state_dir)
    if payload.get("config_path") != expected_config or payload.get("state_dir") != expected_state:
        return AcceptanceCheck(
            name="Target-owned Marimo runtime path resolves in a fresh process",
            passed=False,
            summary="Fresh-process Marimo runtime path did not resolve to the target-owned .state path.",
            details=(
                f"Expected config: {expected_config}",
                f"Actual config: {payload.get('config_path')}",
                f"Expected state: {expected_state}",
                f"Actual state: {payload.get('state_dir')}",
            ),
            command=command,
        )
    return AcceptanceCheck(
        name="Target-owned Marimo runtime path resolves in a fresh process",
        passed=True,
        summary="Fresh-process Marimo config and state both resolve under the target-owned .state path.",
        details=(
            f"Config path: {payload['config_path']}",
            f"State path: {payload['state_dir']}",
        ),
        command=command,
    )


def _bounded_direct_launch_check(root: Path) -> AcceptanceCheck:
    evidence_path = root / ".state" / "acceptance_launch_probe.evidence.json"
    evidence_path.parent.mkdir(parents=True, exist_ok=True)
    command_text = (
        "cmd.exe /c "
        f"\"set NTB_CONSOLE_PROFILE={LAUNCH_PROBE_PROFILE_ID} && "
        f"set NTB_CONSOLE_EVIDENCE_STORE_PATH={evidence_path} && "
        "set PYTHONPATH=src && "
        ".\\.venv\\Scripts\\python.exe -m marimo run src\\ntb_marimo_console\\operator_console_app.py\""
    )
    if _local_url_ready():
        return AcceptanceCheck(
            name="Bounded direct launch path is coherent",
            passed=False,
            summary=(
                "Local port 2718 was already serving before the bounded launch probe started, "
                "so the documented direct foreground launch check could not be trusted."
            ),
            command=command_text,
        )
    process = subprocess.Popen(
        [
            "cmd.exe",
            "/c",
            (
                f"set NTB_CONSOLE_PROFILE={LAUNCH_PROBE_PROFILE_ID} && "
                f"set NTB_CONSOLE_EVIDENCE_STORE_PATH={evidence_path} && "
                "set PYTHONPATH=src && "
                ".\\.venv\\Scripts\\python.exe -m marimo run src\\ntb_marimo_console\\operator_console_app.py"
            ),
        ],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    url_ready = False
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            if _local_url_ready():
                url_ready = True
                break
            time.sleep(1)
    finally:
        _terminate_process_tree(process.pid)

    try:
        stdout, stderr = process.communicate(timeout=5)
    except subprocess.TimeoutExpired:
        stdout = ""
        stderr = ""

    combined = stdout + "\n" + stderr
    warning_present = ".config\\marimo" in combined or ".config/marimo" in combined
    alive_during_probe = process.returncode is None or url_ready
    if not alive_during_probe or not url_ready or warning_present:
        details = [
            "Bounded startup probe should stay alive long enough to answer a localhost readiness check.",
            f"Alive during probe: {alive_during_probe}",
            f"Local URL ready: {url_ready}",
            f"Denied host config warning present: {warning_present}",
            "Last output lines:",
            *(_tail_lines(combined)),
        ]
        return AcceptanceCheck(
            name="Bounded direct launch path is coherent",
            passed=False,
            summary=(
                "Documented direct foreground launch did not meet the bounded startup acceptance conditions."
            ),
            details=tuple(details),
            command=command_text,
        )
    return AcceptanceCheck(
        name="Bounded direct launch path is coherent",
        passed=True,
        summary=(
            "Documented direct foreground launch answered the localhost readiness probe without the prior denied "
            "host-config warning. This is a bounded startup probe only, not browser automation."
        ),
        details=tuple(_tail_lines(combined)),
        command=command_text,
    )


def _bootstrap_details(paths: TargetOwnedMarimoPaths) -> tuple[str, ...]:
    return (
        f"Interpreter: {sys.executable}",
        f"Bootstrap command: {platform_bootstrap_command()}",
        f"Target-owned Marimo config: {paths.marimo_config_file}",
        f"Target-owned Marimo state: {paths.marimo_state_dir}",
    )


def _pytest_slice_check(
    root: Path,
    *,
    name: str,
    summary_on_failure: str,
    summary_on_success_prefix: str,
    targets: tuple[str, ...],
) -> AcceptanceCheck:
    command = " ".join(
        [
            ".\\.venv\\Scripts\\python.exe",
            "-m",
            "pytest",
            *(target.replace("/", "\\") for target in targets),
        ]
    )
    result = _run_python_command(root, ["-m", "pytest", *targets])
    if result.returncode != 0:
        return AcceptanceCheck(
            name=name,
            passed=False,
            summary=summary_on_failure,
            details=_result_details(result),
            command=command,
        )
    summary_line = _last_nonempty_line(result.stdout)
    return AcceptanceCheck(
        name=name,
        passed=True,
        summary=f"{summary_on_success_prefix} {summary_line}",
        details=tuple(target.replace("/", "\\") for target in targets),
        command=command,
    )


def _run_python_command(
    root: Path,
    arguments: list[str],
    *,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, *arguments],
        cwd=root,
        env=_child_env(extra_env),
        capture_output=True,
        text=True,
        timeout=120,
    )


def _child_env(extra_env: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = "src"
    if extra_env is not None:
        env.update(extra_env)
    return env


def _python_command_text(script: str, *, profile_id: str | None = None) -> str:
    prefix = ""
    if profile_id is not None:
        prefix = f"set NTB_CONSOLE_PROFILE={profile_id} && "
    return prefix + f".\\.venv\\Scripts\\python.exe {script}"


def _result_details(result: subprocess.CompletedProcess[str]) -> tuple[str, ...]:
    details: list[str] = [f"Exit code: {result.returncode}"]
    stdout_tail = _tail_lines(result.stdout)
    stderr_tail = _tail_lines(result.stderr)
    if stdout_tail:
        details.append("stdout:")
        details.extend(stdout_tail)
    if stderr_tail:
        details.append("stderr:")
        details.extend(stderr_tail)
    return tuple(details)


def _tail_lines(text: str, *, count: int = 6) -> tuple[str, ...]:
    lines = [line for line in text.splitlines() if line.strip()]
    return tuple(lines[-count:])


def _last_nonempty_line(text: str) -> str:
    for line in reversed(text.splitlines()):
        if line.strip():
            return line.strip()
    return "<no output>"


def _terminate_process_tree(pid: int) -> None:
    subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        capture_output=True,
        text=True,
        timeout=20,
    )


def _local_url_ready() -> bool:
    try:
        with urlopen("http://127.0.0.1:2718", timeout=2) as response:
            return response.status >= 200
    except (URLError, TimeoutError, OSError):
        return False


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
