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

from ntb_marimo_console.operator_live_runtime import (
    LIVE_RUNTIME_DISABLED,
    LIVE_RUNTIME_ERROR,
    LIVE_RUNTIME_STALE,
    LIVE_RUNTIME_UNAVAILABLE,
    OPERATOR_LIVE_RUNTIME,
    operator_runtime_mode_from_env,
)
from ntb_marimo_console.ui.marimo_phase1_renderer import build_primary_cockpit_plan


APP_ENTRYPOINT_RELATIVE = Path("src/ntb_marimo_console/operator_console_app.py")
DEFAULT_SAFE_PROFILE = "fixture_es_demo"
DEFAULT_SAFE_MODE = "fixture_demo"
DEFAULT_OPERATOR_RUNTIME_MODE = "SAFE_NON_LIVE"
DEFAULT_MARKET_DATA_PROVIDER = "disabled"
LIVE_OPERATOR_RUNTIME_MODE = OPERATOR_LIVE_RUNTIME
LIVE_MARKET_DATA_PROVIDER = "schwab"
REQUIRED_LIVE_ENV_KEYS = ("SCHWAB_APP_KEY", "SCHWAB_APP_SECRET", "SCHWAB_TOKEN_PATH")
FAIL_CLOSED_LIVE_RUNTIME_STATUSES = frozenset(
    {
        LIVE_RUNTIME_UNAVAILABLE,
        LIVE_RUNTIME_STALE,
        LIVE_RUNTIME_ERROR,
        LIVE_RUNTIME_DISABLED,
    }
)
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


@dataclass(frozen=True)
class LiveLaunchPrerequisites:
    """Explicit, file-free preconditions for an opt-in live cockpit launch.

    Every field is a boolean derived only from environment-variable presence.
    No secret value, token file, or ``.state/secrets`` material is read,
    parsed, or surfaced — only that the explicit opt-in and the required
    credential env keys exist.
    """

    explicit_runtime_mode_opt_in: bool
    required_env_keys_present: bool
    ready: bool
    blocking_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "explicit_runtime_mode_opt_in": self.explicit_runtime_mode_opt_in,
            "required_env_keys_present": self.required_env_keys_present,
            "ready": self.ready,
            "blocking_reasons": list(self.blocking_reasons),
        }


@dataclass(frozen=True)
class LiveOperatorCockpitLaunchSmoke:
    app_entrypoint: str
    formatted_marimo_command: str
    operator_runtime_mode: str
    operator_runtime_status: str
    market_data_provider: str
    explicit_runtime_mode_opt_in: bool
    required_env_keys_present: bool
    prerequisites_ready: bool
    app_importable: bool
    primary_cockpit_present: bool
    live_runtime_fail_closed: bool
    default_launch_live: bool
    supported_contracts: tuple[str, ...]
    mgc_label: str
    blocking_reasons: tuple[str, ...]
    smoke_passed: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "app_entrypoint": self.app_entrypoint,
            "formatted_marimo_command": self.formatted_marimo_command,
            "operator_runtime_mode": self.operator_runtime_mode,
            "operator_runtime_status": self.operator_runtime_status,
            "market_data_provider": self.market_data_provider,
            "explicit_runtime_mode_opt_in": self.explicit_runtime_mode_opt_in,
            "required_env_keys_present": self.required_env_keys_present,
            "prerequisites_ready": self.prerequisites_ready,
            "app_importable": self.app_importable,
            "primary_cockpit_present": self.primary_cockpit_present,
            "live_runtime_fail_closed": self.live_runtime_fail_closed,
            "default_launch_live": self.default_launch_live,
            "supported_contracts": list(self.supported_contracts),
            "mgc_label": self.mgc_label,
            "blocking_reasons": list(self.blocking_reasons),
            "smoke_passed": self.smoke_passed,
        }


def live_launch_prerequisites(
    base_env: Mapping[str, str] | None = None,
) -> LiveLaunchPrerequisites:
    """Resolve the explicit opt-in preconditions for a live cockpit launch.

    Live launch is gated by two explicit, operator-set signals:

    1. ``NTB_OPERATOR_RUNTIME_MODE=OPERATOR_LIVE_RUNTIME`` (or the equally
       explicit ``NTB_OPERATOR_LIVE_RUNTIME`` truthy guard) already present in
       the caller's environment — never inferred from env files or token files.
    2. The required Schwab credential env keys present (presence only — values
       are never read, parsed, or printed).
    """

    env = dict(base_env) if base_env is not None else dict(os.environ)
    explicit_opt_in = operator_runtime_mode_from_env(env) == OPERATOR_LIVE_RUNTIME
    keys_present = all((env.get(key) or "").strip() for key in REQUIRED_LIVE_ENV_KEYS)
    blocking_reasons: list[str] = []
    if not explicit_opt_in:
        blocking_reasons.append("operator_live_runtime_opt_in_required")
    if not keys_present:
        blocking_reasons.append("required_live_env_keys_missing")
    return LiveLaunchPrerequisites(
        explicit_runtime_mode_opt_in=explicit_opt_in,
        required_env_keys_present=keys_present,
        ready=explicit_opt_in and keys_present,
        blocking_reasons=tuple(blocking_reasons),
    )


def build_live_launch_environment(
    base_env: Mapping[str, str] | None = None,
    *,
    project_root: str | Path | None = None,
) -> dict[str, str]:
    """Build the env for an explicit opt-in live cockpit launch.

    Unlike :func:`build_safe_launch_environment`, this preserves the operator's
    Schwab credential env keys because the app/runtime reads configured token
    material internally for live observation. The credential values are never
    printed: only :func:`format_live_marimo_launch_command` is used for display,
    and it emits the non-sensitive ``NTB_*`` prefix only.

    The live env intentionally does **not** set ``NTB_CONSOLE_MODE`` or
    ``NTB_CONSOLE_PROFILE``: injecting the fixture console identity was what
    made the explicit live cockpit still present as Fixture/Demo. The explicit
    ``NTB_OPERATOR_RUNTIME_MODE=OPERATOR_LIVE_RUNTIME`` opt-in is the live
    console identity; the app derives a live-observation cockpit from it. The
    credential-free preserved-engine scaffolding still resolves from the app's
    own default, which keeps the cockpit observation-only.

    Callers must verify :func:`live_launch_prerequisites` is ``ready`` before
    invoking this; it does not itself re-check the opt-in.
    """

    root = (
        Path(project_root).resolve()
        if project_root is not None
        else project_root_from_module()
    )
    source_path = str(root / "src")
    env = dict(base_env) if base_env is not None else dict(os.environ)
    for key in LAUNCH_ENV_KEYS:
        env.pop(key, None)
    env.update(
        {
            "NTB_FIXTURE_LOCKOUT": "false",
            "NTB_OPERATOR_RUNTIME_MODE": LIVE_OPERATOR_RUNTIME_MODE,
            "NTB_OPERATOR_LIVE_RUNTIME": "1",
            "NTB_MARKET_DATA_PROVIDER": LIVE_MARKET_DATA_PROVIDER,
            "PYTHONPATH": source_path,
        }
    )
    return env


def format_live_marimo_launch_command(
    *,
    python_executable: str | None = None,
    project_root: str | Path | None = None,
) -> str:
    """Render a copy-pasteable live cockpit launch command, secret-free.

    Only the non-sensitive ``NTB_*`` launch keys are emitted. Schwab credential
    env keys are intentionally absent: the operator must already have them
    present in their own shell, and this command never embeds or prints them.
    """

    root = (
        Path(project_root).resolve()
        if project_root is not None
        else project_root_from_module()
    )
    command = build_marimo_launch_command(
        python_executable=python_executable,
        project_root=root,
    )
    # No NTB_CONSOLE_MODE / NTB_CONSOLE_PROFILE here: the explicit
    # OPERATOR_LIVE_RUNTIME opt-in is the live console identity. Injecting the
    # fixture console identity is what made --live still render Fixture/Demo.
    env_prefix = {
        "NTB_OPERATOR_RUNTIME_MODE": LIVE_OPERATOR_RUNTIME_MODE,
        "NTB_OPERATOR_LIVE_RUNTIME": "1",
        "NTB_MARKET_DATA_PROVIDER": LIVE_MARKET_DATA_PROVIDER,
        "PYTHONPATH": "src",
    }
    env_text = " ".join(
        f"{key}={shlex.quote(value)}" for key, value in env_prefix.items()
    )
    command_text = " ".join(shlex.quote(part) for part in command)
    return "\n".join(
        (
            "# Explicit opt-in live-observation cockpit launch.",
            "# Requires SCHWAB_APP_KEY, SCHWAB_APP_SECRET, and SCHWAB_TOKEN_PATH "
            "already present in your environment.",
            "# This command never prints, embeds, or echoes credential values.",
            f"cd {shlex.quote(str(root))} && {env_text} {command_text}",
        )
    )


def build_live_operator_cockpit_launch_smoke(
    *,
    project_root: str | Path | None = None,
    base_env: Mapping[str, str] | None = None,
    python_executable: str | None = None,
) -> LiveOperatorCockpitLaunchSmoke:
    """Verify the explicit opt-in live cockpit launch state without starting Marimo.

    Fails closed when the explicit live prerequisites are not satisfied: the
    smoke short-circuits, attempts no live behavior, and never falls back to the
    fixture cockpit. When prerequisites are satisfied, it builds the startup
    artifacts under the live env and confirms the cockpit surface reflects the
    operator live runtime status. With no operator-owned manager registered the
    live runtime status is fail-closed (observation-only) by design; that is a
    structurally valid live launch, not a readiness claim.
    """

    root = (
        Path(project_root).resolve()
        if project_root is not None
        else project_root_from_module()
    )
    prerequisites = live_launch_prerequisites(base_env)
    formatted_command = format_live_marimo_launch_command(
        python_executable=python_executable,
        project_root=root,
    )
    app_path = operator_app_entrypoint(root)
    entrypoint = APP_ENTRYPOINT_RELATIVE.as_posix()

    if not prerequisites.ready:
        return LiveOperatorCockpitLaunchSmoke(
            app_entrypoint=entrypoint,
            formatted_marimo_command=formatted_command,
            operator_runtime_mode="",
            operator_runtime_status="LIVE_PREREQUISITES_NOT_SATISFIED",
            market_data_provider=LIVE_MARKET_DATA_PROVIDER,
            explicit_runtime_mode_opt_in=prerequisites.explicit_runtime_mode_opt_in,
            required_env_keys_present=prerequisites.required_env_keys_present,
            prerequisites_ready=False,
            app_importable=False,
            primary_cockpit_present=False,
            live_runtime_fail_closed=True,
            default_launch_live=False,
            supported_contracts=(),
            mgc_label="",
            blocking_reasons=prerequisites.blocking_reasons,
            smoke_passed=False,
        )

    if not app_path.is_file():
        raise FileNotFoundError(f"Operator console app entrypoint not found: {app_path}")

    live_env = build_live_launch_environment(base_env, project_root=root)

    with _temporary_environ(live_env):
        app_module = importlib.import_module("ntb_marimo_console.operator_console_app")
        app_importable = getattr(app_module, "app", None) is not None

        from ntb_marimo_console.launch_config import build_startup_artifacts_from_env

        artifacts = build_startup_artifacts_from_env(default_mode=DEFAULT_SAFE_MODE)

    operator_runtime = artifacts.operator_runtime
    primary = build_primary_cockpit_plan(artifacts.shell)
    rows = _rows_by_contract(primary)
    supported_contracts = tuple(
        str(item) for item in primary.get("supported_contracts", ())
    )
    mgc_label = str(rows.get("MGC", {}).get("profile_label", ""))
    runtime_mode = str(operator_runtime.mode)
    runtime_status = str(operator_runtime.status)
    blocking_reasons = tuple(str(reason) for reason in operator_runtime.blocking_reasons)
    live_runtime_fail_closed = runtime_status in FAIL_CLOSED_LIVE_RUNTIME_STATUSES
    live_runtime_ready = (
        runtime_status == OPERATOR_LIVE_RUNTIME and operator_runtime.cache_snapshot_ready
    )
    default_launch_live = primary.get("default_launch_live") is True
    smoke_passed = (
        app_importable
        and primary.get("present") is True
        and runtime_mode == OPERATOR_LIVE_RUNTIME
        and (live_runtime_fail_closed or live_runtime_ready)
        and default_launch_live is False
        and supported_contracts == SUPPORTED_CONTRACTS
        and "ZN" not in rows
        and "GC" not in rows
        and mgc_label == "Micro Gold"
    )

    return LiveOperatorCockpitLaunchSmoke(
        app_entrypoint=entrypoint,
        formatted_marimo_command=formatted_command,
        operator_runtime_mode=runtime_mode,
        operator_runtime_status=runtime_status,
        market_data_provider=LIVE_MARKET_DATA_PROVIDER,
        explicit_runtime_mode_opt_in=prerequisites.explicit_runtime_mode_opt_in,
        required_env_keys_present=prerequisites.required_env_keys_present,
        prerequisites_ready=True,
        app_importable=app_importable,
        primary_cockpit_present=primary.get("present") is True,
        live_runtime_fail_closed=live_runtime_fail_closed,
        default_launch_live=default_launch_live,
        supported_contracts=supported_contracts,
        mgc_label=mgc_label,
        blocking_reasons=blocking_reasons,
        smoke_passed=smoke_passed,
    )


def render_live_operator_cockpit_launch_smoke(
    smoke: LiveOperatorCockpitLaunchSmoke,
) -> str:
    status = "PASS" if smoke.smoke_passed else "FAIL"
    primary = "present" if smoke.primary_cockpit_present else "missing"
    lines = [
        f"Live-observation cockpit launch smoke: {status}",
        f"app={smoke.app_entrypoint}",
        f"operator_runtime_mode={smoke.operator_runtime_mode or 'not_resolved'}",
        f"operator_runtime_status={smoke.operator_runtime_status}",
        f"market_data_provider={smoke.market_data_provider}",
        "explicit_runtime_mode_opt_in="
        + ("yes" if smoke.explicit_runtime_mode_opt_in else "no"),
        "required_env_keys_present="
        + ("yes" if smoke.required_env_keys_present else "no"),
        "prerequisites_ready=" + ("yes" if smoke.prerequisites_ready else "no"),
        "app_importable=" + ("yes" if smoke.app_importable else "no"),
        f"primary_cockpit={primary}",
        "live_runtime_fail_closed="
        + ("yes" if smoke.live_runtime_fail_closed else "no"),
        "default_launch_live=" + ("yes" if smoke.default_launch_live else "no"),
        "supported_contracts="
        + (",".join(smoke.supported_contracts) if smoke.supported_contracts else "none"),
        f"MGC_label={smoke.mgc_label or 'not_resolved'}",
        "fixture_fallback_after_live_failure=no",
    ]
    for reason in smoke.blocking_reasons:
        lines.append(f"blocking_reason={reason}")
    lines.append(f"marimo_command={smoke.formatted_marimo_command}")
    return "\n".join(lines)


def launch_operator_cockpit_live(
    *,
    base_env: Mapping[str, str] | None = None,
    project_root: str | Path | None = None,
    python_executable: str | None = None,
) -> int:
    """Launch the live-observation cockpit behind explicit opt-in, fail-closed.

    Refuses (non-zero exit) when the explicit live prerequisites are missing and
    never falls back to the fixture cockpit after a live refusal or failure.
    """

    root = (
        Path(project_root).resolve()
        if project_root is not None
        else project_root_from_module()
    )
    env_source = dict(base_env) if base_env is not None else dict(os.environ)
    prerequisites = live_launch_prerequisites(env_source)
    if not prerequisites.ready:
        print("Live-observation cockpit launch refused: explicit prerequisites not satisfied.")
        for reason in prerequisites.blocking_reasons:
            print(f"blocking_reason={reason}")
        print(
            "Explicit opt-in requires NTB_OPERATOR_RUNTIME_MODE=OPERATOR_LIVE_RUNTIME "
            "and the required Schwab credential env keys present."
        )
        print("No fixture fallback after live failure. Default non-live launch is unaffected.")
        return 2

    live_env = build_live_launch_environment(env_source, project_root=root)
    command = build_marimo_launch_command(
        python_executable=python_executable,
        project_root=root,
    )
    print("Launching live-observation cockpit (explicit opt-in):")
    print(
        format_live_marimo_launch_command(
            python_executable=python_executable,
            project_root=root,
        )
    )
    completed = subprocess.run(command, cwd=root, env=live_env, check=False)
    return int(completed.returncode)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="launch_operator_cockpit",
        description=(
            "Launch the Marimo operator cockpit. Default launch is the "
            "credential-free non-live fixture cockpit. The live-observation "
            "cockpit launches only behind the explicit --live opt-in."
        ),
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help=(
            "Explicit opt-in: launch the live-observation cockpit. Also requires "
            "NTB_OPERATOR_RUNTIME_MODE=OPERATOR_LIVE_RUNTIME and the Schwab "
            "credential env keys already present. Fails closed otherwise."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify the cockpit launch state without starting Marimo.",
    )
    parser.add_argument(
        "--print-command",
        action="store_true",
        help="Print the Marimo launch command without launching it.",
    )
    args = parser.parse_args(argv)

    if args.print_command:
        if args.live:
            print(format_live_marimo_launch_command())
        else:
            print(format_marimo_launch_command())
        return 0
    if args.dry_run:
        if args.live:
            live_smoke = build_live_operator_cockpit_launch_smoke()
            print(render_live_operator_cockpit_launch_smoke(live_smoke))
            return 0 if live_smoke.smoke_passed else 1
        smoke = build_operator_cockpit_launch_smoke()
        print(render_operator_cockpit_launch_smoke(smoke))
        return 0 if smoke.smoke_passed else 1
    if args.live:
        return launch_operator_cockpit_live()
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
