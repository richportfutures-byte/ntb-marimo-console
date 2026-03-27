from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .adapters.contracts import RuntimeMode
from .runtime_diagnostics import (
    DIAG_INCOMPLETE_PROFILE_DEFINITION,
    DIAG_LAUNCH_PREFLIGHT_MISMATCH,
    DIAG_UNSUPPORTED_PROFILE,
    LaunchRequest,
    PreflightFailedError,
    PreflightReport,
    RuntimeDiagnosticError,
    build_failed_preflight_report,
    build_preflight_report,
    build_runtime_failure_report,
    runtime_identity_payload,
)
from .runtime_modes import build_app_shell_for_profile, parse_runtime_mode
from .runtime_profiles import (
    RuntimeProfile,
    RuntimeProfileError,
    default_profile_id_for_mode,
    get_runtime_profile,
)
from .startup_flow import build_startup_payload


@dataclass(frozen=True)
class LaunchConfig:
    mode: RuntimeMode
    profile: RuntimeProfile
    lockout: bool
    fixtures_root: Path | None
    adapter_binding: str | None
    model_adapter: object | None
    preflight: PreflightReport


@dataclass(frozen=True)
class LaunchArtifacts:
    shell: dict[str, object]
    config: LaunchConfig


@dataclass(frozen=True)
class StartupArtifacts:
    shell: dict[str, object]
    report: PreflightReport
    ready: bool
    config: LaunchConfig | None


def build_launch_artifacts_from_env(
    *,
    default_mode: RuntimeMode = "fixture_demo",
    default_profile_id: str | None = None,
) -> LaunchArtifacts:
    startup = build_startup_artifacts_from_env(
        default_mode=default_mode,
        default_profile_id=default_profile_id,
        query_action_requested=True,
    )
    if startup.config is None:
        raise PreflightFailedError(startup.report)
    if not startup.ready:
        raise RuntimeError(
            f"Runtime launch failed after successful preflight for profile {startup.config.profile.profile_id}: "
            f"{_runtime_failure_summary(startup.report)}"
        )
    return LaunchArtifacts(shell=startup.shell, config=startup.config)


def build_shell_from_env(
    *,
    default_mode: RuntimeMode = "fixture_demo",
    default_profile_id: str | None = None,
) -> LaunchArtifacts:
    """Backward-compatible alias for env-driven app bootstrapping."""

    return build_launch_artifacts_from_env(
        default_mode=default_mode,
        default_profile_id=default_profile_id,
    )


def build_startup_artifacts_from_env(
    *,
    default_mode: RuntimeMode = "fixture_demo",
    default_profile_id: str | None = None,
    query_action_requested: bool = False,
) -> StartupArtifacts:
    try:
        request = resolve_launch_request_from_env(
            default_mode=default_mode,
            default_profile_id=default_profile_id,
        )
    except RuntimeDiagnosticError as exc:
        report = build_failed_preflight_report(
            requested_profile_id=os.getenv("NTB_CONSOLE_PROFILE") or default_profile_id,
            requested_mode=os.getenv("NTB_CONSOLE_MODE") or default_mode,
            error=exc,
        )
        shell = _build_startup_shell(report)
        return StartupArtifacts(shell=shell, report=report, ready=False, config=None)

    return build_startup_artifacts(
        request,
        query_action_requested=query_action_requested,
    )


def build_startup_artifacts(
    request: LaunchRequest,
    *,
    query_action_requested: bool = False,
) -> StartupArtifacts:
    report = build_preflight_report(request)
    return _build_startup_artifacts_from_report(
        report,
        query_action_requested=query_action_requested,
    )


def load_launch_config_from_env(
    *,
    default_mode: RuntimeMode = "fixture_demo",
    default_profile_id: str | None = None,
) -> LaunchConfig:
    report = build_preflight_report_from_env(
        default_mode=default_mode,
        default_profile_id=default_profile_id,
    )
    if not report.passed or report.request is None:
        raise PreflightFailedError(report)

    request = report.request
    return LaunchConfig(
        mode=request.mode,
        profile=request.profile,
        lockout=request.lockout,
        fixtures_root=request.fixtures_root,
        adapter_binding=request.adapter_binding,
        model_adapter=report.resolved_adapter,
        preflight=report,
    )


def build_preflight_report_from_env(
    *,
    default_mode: RuntimeMode = "fixture_demo",
    default_profile_id: str | None = None,
) -> PreflightReport:
    raw_mode = os.getenv("NTB_CONSOLE_MODE")
    requested_profile_id = os.getenv("NTB_CONSOLE_PROFILE") or default_profile_id
    requested_mode = raw_mode or default_mode

    try:
        request = resolve_launch_request_from_env(
            default_mode=default_mode,
            default_profile_id=default_profile_id,
        )
    except RuntimeDiagnosticError as exc:
        return build_failed_preflight_report(
            requested_profile_id=requested_profile_id,
            requested_mode=requested_mode,
            error=exc,
        )

    return build_preflight_report(request)


def resolve_launch_request_from_env(
    *,
    default_mode: RuntimeMode = "fixture_demo",
    default_profile_id: str | None = None,
) -> LaunchRequest:
    raw_mode = os.getenv("NTB_CONSOLE_MODE")
    requested_profile_id = os.getenv("NTB_CONSOLE_PROFILE")
    if requested_profile_id or default_profile_id is not None:
        resolved_profile_id = requested_profile_id or default_profile_id or ""
        profile = _resolve_profile_with_diagnostics(resolved_profile_id)
        mode = parse_runtime_mode(raw_mode) if raw_mode is not None else profile.runtime_mode
    else:
        mode = parse_runtime_mode(raw_mode or default_mode)
        profile = _resolve_profile_with_diagnostics(default_profile_id_for_mode(mode))

    if raw_mode is not None and profile.runtime_mode != mode:
        raise RuntimeDiagnosticError(
            category=DIAG_LAUNCH_PREFLIGHT_MISMATCH,
            summary=f"Runtime profile {profile.profile_id} requires runtime mode {profile.runtime_mode}, got {mode}.",
            remedy="Either remove NTB_CONSOLE_MODE or set it to the runtime mode required by the selected profile.",
        )

    fixtures_root: Path | None = None
    fixtures_root_env = os.getenv("NTB_FIXTURES_ROOT")
    if fixtures_root_env:
        fixtures_root = Path(fixtures_root_env).expanduser()

    lockout = _parse_bool_env(os.getenv("NTB_FIXTURE_LOCKOUT"), default=False)

    adapter_binding: str | None = None
    if profile.runtime_mode == "preserved_engine":
        adapter_binding = os.getenv("NTB_MODEL_ADAPTER_REF", profile.default_model_adapter_ref)

    return LaunchRequest(
        mode=mode,
        profile=profile,
        lockout=lockout,
        fixtures_root=fixtures_root,
        adapter_binding=adapter_binding,
    )


def _resolve_profile_with_diagnostics(profile_id: str) -> RuntimeProfile:
    try:
        return get_runtime_profile(profile_id)
    except RuntimeProfileError as exc:
        message = str(exc)
        category = (
            DIAG_UNSUPPORTED_PROFILE
            if message.startswith("Unsupported runtime profile")
            else DIAG_INCOMPLETE_PROFILE_DEFINITION
        )
        remedy = (
            "Run scripts/list_runtime_profiles.py and select one of the supported runtime profile ids."
            if category == DIAG_UNSUPPORTED_PROFILE
            else "Fix the selected runtime profile definition in the target-owned registry."
        )
        raise RuntimeDiagnosticError(
            category=category,
            summary=message,
            remedy=remedy,
        ) from exc


def _attach_runtime_identity(shell: dict[str, object], report: PreflightReport) -> None:
    runtime = shell.get("runtime")
    if not isinstance(runtime, dict):
        runtime = {}
        shell["runtime"] = runtime
    runtime.update(runtime_identity_payload(report))


def _attach_startup_payload(shell: dict[str, object], report: PreflightReport) -> None:
    startup = build_startup_payload(report, runtime_shell=shell)
    shell["startup"] = startup

    runtime = shell.get("runtime")
    if not isinstance(runtime, dict):
        runtime = {}
        shell["runtime"] = runtime
    runtime.update(
        {
            "startup_readiness_state": startup["readiness_state"],
            "startup_state_history": startup["readiness_history"],
            "operator_ready": startup["operator_ready"],
            "next_action": startup["next_action"],
        }
    )


def attach_launch_metadata(shell: dict[str, object], report: PreflightReport) -> dict[str, object]:
    _attach_runtime_identity(shell, report)
    _attach_startup_payload(shell, report)
    return shell


def _build_startup_shell(report: PreflightReport) -> dict[str, object]:
    shell: dict[str, object] = {
        "title": "NTB Marimo Console",
        "surfaces": {},
        "runtime": {},
    }
    attach_launch_metadata(shell, report)
    return shell


def _build_startup_artifacts_from_report(
    report: PreflightReport,
    *,
    query_action_requested: bool,
) -> StartupArtifacts:
    if not report.passed or report.request is None:
        shell = _build_startup_shell(report)
        return StartupArtifacts(shell=shell, report=report, ready=False, config=None)

    request = report.request
    config = LaunchConfig(
        mode=request.mode,
        profile=request.profile,
        lockout=request.lockout,
        fixtures_root=request.fixtures_root,
        adapter_binding=request.adapter_binding,
        model_adapter=report.resolved_adapter,
        preflight=report,
    )

    try:
        shell = build_app_shell_for_profile(
            profile=config.profile,
            fixtures_root=config.fixtures_root,
            lockout=config.lockout,
            model_adapter=config.model_adapter,
            query_action_requested=query_action_requested,
        )
    except Exception as exc:
        failed_report = build_runtime_failure_report(
            report,
            summary=(
                f"Runtime assembly failed for profile {config.profile.profile_id}: {exc}"
            ),
            remedy="Inspect the startup diagnostics, fix the blocking runtime issue, then relaunch the console.",
        )
        shell = _build_startup_shell(failed_report)
        return StartupArtifacts(shell=shell, report=failed_report, ready=False, config=config)

    attach_launch_metadata(shell, report)
    return StartupArtifacts(shell=shell, report=report, ready=True, config=config)


def _runtime_failure_summary(report: PreflightReport) -> str:
    for check in report.checks:
        if not check.passed:
            return check.summary
    return "Unknown runtime failure."


def _parse_bool_env(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise RuntimeDiagnosticError(
        category=DIAG_LAUNCH_PREFLIGHT_MISMATCH,
        summary=f"Invalid boolean value: {value}",
        remedy="Use one of: true/false, yes/no, on/off, 1/0.",
    )
