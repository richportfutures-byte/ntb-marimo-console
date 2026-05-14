from __future__ import annotations

import argparse
import importlib
import os
import shlex
import subprocess
import sys
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from ntb_marimo_console.ui.marimo_phase1_renderer import build_primary_cockpit_plan


APP_ENTRYPOINT_RELATIVE = Path("src/ntb_marimo_console/operator_console_app.py")
DEFAULT_SAFE_PROFILE = "fixture_es_demo"
DEFAULT_SAFE_MODE = "fixture_demo"
DEFAULT_OPERATOR_RUNTIME_MODE = "SAFE_NON_LIVE"
DEFAULT_MARKET_DATA_PROVIDER = "disabled"
SUPPORTED_CONTRACTS = ("ES", "NQ", "CL", "6E", "MGC")
SENSITIVE_ENV_FRAGMENTS = (
    "SCHWAB",
    "TOKEN",
    "SECRET",
    "AUTH",
    "ACCOUNT",
    "CUSTOMER",
    "CORREL",
    "STREAMER",
    "API_KEY",
)
LAUNCH_ENV_KEYS = (
    "NTB_CONSOLE_MODE",
    "NTB_CONSOLE_PROFILE",
    "NTB_FIXTURES_ROOT",
    "NTB_FIXTURE_LOCKOUT",
    "NTB_MODEL_ADAPTER_REF",
    "NTB_MARKET_DATA_PROVIDER",
    "NTB_MARKET_DATA_SYMBOL",
    "NTB_MARKET_DATA_FIELD_IDS",
    "NTB_MARKET_DATA_MAX_QUOTE_AGE_SECONDS",
    "NTB_MARKET_DATA_TIMEOUT_SECONDS",
    "NTB_OPERATOR_RUNTIME_MODE",
    "NTB_OPERATOR_LIVE_RUNTIME",
)


@dataclass(frozen=True)
class OperatorCockpitLaunchSmoke:
    app_entrypoint: str
    marimo_command: tuple[str, ...]
    formatted_marimo_command: str
    mode: str
    profile: str
    operator_runtime_mode: str
    market_data_provider: str
    app_importable: bool
    primary_cockpit_present: bool
    live_credentials_required: bool
    default_launch_live: bool
    supported_contracts: tuple[str, ...]
    mgc_label: str
    query_readiness_provenance_reflected: bool
    smoke_passed: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "app_entrypoint": self.app_entrypoint,
            "marimo_command": list(self.marimo_command),
            "formatted_marimo_command": self.formatted_marimo_command,
            "mode": self.mode,
            "profile": self.profile,
            "operator_runtime_mode": self.operator_runtime_mode,
            "market_data_provider": self.market_data_provider,
            "app_importable": self.app_importable,
            "primary_cockpit_present": self.primary_cockpit_present,
            "live_credentials_required": self.live_credentials_required,
            "default_launch_live": self.default_launch_live,
            "supported_contracts": list(self.supported_contracts),
            "mgc_label": self.mgc_label,
            "query_readiness_provenance_reflected": self.query_readiness_provenance_reflected,
            "smoke_passed": self.smoke_passed,
        }


def project_root_from_module() -> Path:
    return Path(__file__).resolve().parents[2]


def operator_app_entrypoint(project_root: str | Path | None = None) -> Path:
    root = (
        Path(project_root).resolve()
        if project_root is not None
        else project_root_from_module()
    )
    return root / APP_ENTRYPOINT_RELATIVE


def build_safe_launch_environment(
    base_env: Mapping[str, str] | None = None,
    *,
    project_root: str | Path | None = None,
) -> dict[str, str]:
    root = (
        Path(project_root).resolve()
        if project_root is not None
        else project_root_from_module()
    )
    source_path = str(root / "src")
    env = {
        key: value
        for key, value in (base_env or os.environ).items()
        if not _is_sensitive_env_key(key)
    }
    for key in LAUNCH_ENV_KEYS:
        env.pop(key, None)
    env.update(
        {
            "NTB_CONSOLE_MODE": DEFAULT_SAFE_MODE,
            "NTB_CONSOLE_PROFILE": DEFAULT_SAFE_PROFILE,
            "NTB_FIXTURE_LOCKOUT": "false",
            "NTB_OPERATOR_RUNTIME_MODE": DEFAULT_OPERATOR_RUNTIME_MODE,
            "NTB_OPERATOR_LIVE_RUNTIME": "0",
            "NTB_MARKET_DATA_PROVIDER": DEFAULT_MARKET_DATA_PROVIDER,
            "PYTHONPATH": source_path,
        }
    )
    return env


def build_marimo_launch_command(
    *,
    python_executable: str | None = None,
    project_root: str | Path | None = None,
) -> tuple[str, ...]:
    root = (
        Path(project_root).resolve()
        if project_root is not None
        else project_root_from_module()
    )
    app_path = operator_app_entrypoint(root).relative_to(root)
    return (
        python_executable or sys.executable,
        "-m",
        "marimo",
        "run",
        app_path.as_posix(),
    )


def format_marimo_launch_command(
    *,
    python_executable: str | None = None,
    project_root: str | Path | None = None,
) -> str:
    root = (
        Path(project_root).resolve()
        if project_root is not None
        else project_root_from_module()
    )
    command = build_marimo_launch_command(
        python_executable=python_executable,
        project_root=root,
    )
    env_prefix = {
        "NTB_CONSOLE_MODE": DEFAULT_SAFE_MODE,
        "NTB_CONSOLE_PROFILE": DEFAULT_SAFE_PROFILE,
        "NTB_OPERATOR_RUNTIME_MODE": DEFAULT_OPERATOR_RUNTIME_MODE,
        "NTB_OPERATOR_LIVE_RUNTIME": "0",
        "NTB_MARKET_DATA_PROVIDER": DEFAULT_MARKET_DATA_PROVIDER,
        "PYTHONPATH": "src",
    }
    env_text = " ".join(
        f"{key}={shlex.quote(value)}" for key, value in env_prefix.items()
    )
    command_text = " ".join(shlex.quote(part) for part in command)
    return f"cd {shlex.quote(str(root))} && {env_text} {command_text}"


def build_operator_cockpit_launch_smoke(
    *,
    project_root: str | Path | None = None,
    base_env: Mapping[str, str] | None = None,
    python_executable: str | None = None,
) -> OperatorCockpitLaunchSmoke:
    root = (
        Path(project_root).resolve()
        if project_root is not None
        else project_root_from_module()
    )
    app_path = operator_app_entrypoint(root)
    if not app_path.is_file():
        raise FileNotFoundError(f"Operator console app entrypoint not found: {app_path}")

    safe_env = build_safe_launch_environment(base_env, project_root=root)
    command = build_marimo_launch_command(
        python_executable=python_executable,
        project_root=root,
    )
    formatted_command = format_marimo_launch_command(
        python_executable=python_executable,
        project_root=root,
    )

    with _temporary_environ(safe_env):
        app_module = importlib.import_module("ntb_marimo_console.operator_console_app")
        app_importable = getattr(app_module, "app", None) is not None

        from ntb_marimo_console.launch_config import build_startup_artifacts_from_env

        artifacts = build_startup_artifacts_from_env(default_mode=DEFAULT_SAFE_MODE)

    primary = build_primary_cockpit_plan(artifacts.shell)
    rows = _rows_by_contract(primary)
    supported_contracts = tuple(
        str(item) for item in primary.get("supported_contracts", ())
    )
    mgc_label = str(rows.get("MGC", {}).get("profile_label", ""))
    query_readiness_provenance_reflected = _query_readiness_provenance_reflected(primary)
    smoke_passed = (
        app_importable
        and artifacts.ready
        and primary.get("present") is True
        and primary.get("mode") == "fixture_dry_run_non_live"
        and primary.get("live_credentials_required") is False
        and primary.get("default_launch_live") is False
        and supported_contracts == SUPPORTED_CONTRACTS
        and "ZN" not in rows
        and "GC" not in rows
        and mgc_label == "Micro Gold"
        and query_readiness_provenance_reflected
    )

    return OperatorCockpitLaunchSmoke(
        app_entrypoint=APP_ENTRYPOINT_RELATIVE.as_posix(),
        marimo_command=command,
        formatted_marimo_command=formatted_command,
        mode=DEFAULT_SAFE_MODE,
        profile=DEFAULT_SAFE_PROFILE,
        operator_runtime_mode=DEFAULT_OPERATOR_RUNTIME_MODE,
        market_data_provider=DEFAULT_MARKET_DATA_PROVIDER,
        app_importable=app_importable,
        primary_cockpit_present=primary.get("present") is True,
        live_credentials_required=primary.get("live_credentials_required") is True,
        default_launch_live=primary.get("default_launch_live") is True,
        supported_contracts=supported_contracts,
        mgc_label=mgc_label,
        query_readiness_provenance_reflected=query_readiness_provenance_reflected,
        smoke_passed=smoke_passed,
    )


def render_operator_cockpit_launch_smoke(smoke: OperatorCockpitLaunchSmoke) -> str:
    status = "PASS" if smoke.smoke_passed else "FAIL"
    primary = "present" if smoke.primary_cockpit_present else "missing"
    return "\n".join(
        (
            f"Fixture cockpit launch smoke: {status}",
            f"app={smoke.app_entrypoint}",
            f"mode={smoke.mode}",
            f"operator_runtime={smoke.operator_runtime_mode}",
            f"market_data_provider={smoke.market_data_provider}",
            f"primary_cockpit={primary}",
            "supported_contracts=" + ",".join(smoke.supported_contracts),
            f"MGC_label={smoke.mgc_label}",
            "query_readiness_provenance="
            + ("reflected" if smoke.query_readiness_provenance_reflected else "failed"),
            f"marimo_command={smoke.formatted_marimo_command}",
        )
    )


def launch_operator_cockpit(
    *,
    project_root: str | Path | None = None,
    python_executable: str | None = None,
) -> int:
    root = (
        Path(project_root).resolve()
        if project_root is not None
        else project_root_from_module()
    )
    command = build_marimo_launch_command(
        python_executable=python_executable,
        project_root=root,
    )
    env = build_safe_launch_environment(project_root=root)
    print("Launching fixture cockpit:")
    print(
        format_marimo_launch_command(
            python_executable=python_executable,
            project_root=root,
        )
    )
    completed = subprocess.run(command, cwd=root, env=env, check=False)
    return int(completed.returncode)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="launch_operator_cockpit",
        description="Launch the credential-free non-live Marimo fixture cockpit.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify the safe fixture cockpit launch state without starting Marimo.",
    )
    parser.add_argument(
        "--print-command",
        action="store_true",
        help="Print the safe Marimo command without launching it.",
    )
    args = parser.parse_args(argv)

    if args.print_command:
        print(format_marimo_launch_command())
        return 0
    if args.dry_run:
        smoke = build_operator_cockpit_launch_smoke()
        print(render_operator_cockpit_launch_smoke(smoke))
        return 0 if smoke.smoke_passed else 1
    return launch_operator_cockpit()


def _is_sensitive_env_key(key: str) -> bool:
    normalized = key.upper()
    return any(fragment in normalized for fragment in SENSITIVE_ENV_FRAGMENTS)


def _rows_by_contract(plan: Mapping[str, object]) -> dict[str, dict[str, object]]:
    rows = plan.get("rows")
    if not isinstance(rows, list):
        return {}
    return {
        str(row["contract"]): dict(row)
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("contract"), str)
    }


def _query_readiness_provenance_reflected(plan: Mapping[str, object]) -> bool:
    rows = plan.get("rows")
    if not isinstance(rows, list):
        return False
    for row in rows:
        if not isinstance(row, dict):
            return False
        provenance = row.get("query_ready_provenance")
        if row.get("query_enabled") is True:
            if provenance != "real_trigger_state_result_and_pipeline_gate":
                return False
        elif provenance != "unavailable_not_inferred_from_display_or_raw_enabled_mapping":
            return False
    return True


@contextmanager
def _temporary_environ(env: Mapping[str, str]) -> Iterator[None]:
    old_env = dict(os.environ)
    os.environ.clear()
    os.environ.update(env)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(old_env)


if __name__ == "__main__":
    raise SystemExit(main())
