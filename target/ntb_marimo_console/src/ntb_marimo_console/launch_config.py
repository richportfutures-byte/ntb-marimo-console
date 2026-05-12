from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .adapters.contracts import RuntimeMode
from .market_data import FuturesQuoteServiceConfig, resolve_futures_quote_service_config
from .market_data.stream_manager import StreamManagerSnapshot
from .operator_live_runtime import (
    OperatorRuntimeMode,
    OperatorRuntimeSnapshotResult,
    RuntimeSnapshotProducer,
    operator_runtime_mode_from_env,
    resolve_operator_runtime_snapshot,
)
from .readiness_summary import RuntimeReadinessSnapshot, build_five_contract_readiness_summary_surface
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
from .app import build_phase1_shell_from_artifacts
from .runtime_modes import assemble_runtime_for_profile, build_phase1_artifacts_from_assembly, parse_runtime_mode
from .runtime_profiles import (
    RuntimeProfile,
    RuntimeProfileError,
    default_profile_id_for_mode,
    get_runtime_profile,
)
from .startup_flow import build_startup_payload
from .trigger_state import TriggerStateResult


@dataclass(frozen=True)
class LaunchConfig:
    mode: RuntimeMode
    profile: RuntimeProfile
    lockout: bool
    fixtures_root: Path | None
    adapter_binding: str | None
    model_adapter: object | None
    market_data_config: FuturesQuoteServiceConfig
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
    operator_runtime: OperatorRuntimeSnapshotResult
    trigger_state_results: tuple[TriggerStateResult, ...] = ()


def build_launch_artifacts_from_env(
    *,
    default_mode: RuntimeMode = "fixture_demo",
    default_profile_id: str | None = None,
    runtime_snapshot: RuntimeReadinessSnapshot | None = None,
    runtime_snapshot_producer: RuntimeSnapshotProducer | None = None,
    operator_runtime_mode: OperatorRuntimeMode | str | None = None,
) -> LaunchArtifacts:
    startup = build_startup_artifacts_from_env(
        default_mode=default_mode,
        default_profile_id=default_profile_id,
        query_action_requested=True,
        runtime_snapshot=runtime_snapshot,
        runtime_snapshot_producer=runtime_snapshot_producer,
        operator_runtime_mode=operator_runtime_mode,
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
    runtime_snapshot: RuntimeReadinessSnapshot | None = None,
    runtime_snapshot_producer: RuntimeSnapshotProducer | None = None,
    operator_runtime_mode: OperatorRuntimeMode | str | None = None,
) -> LaunchArtifacts:
    """Backward-compatible alias for env-driven app bootstrapping."""

    return build_launch_artifacts_from_env(
        default_mode=default_mode,
        default_profile_id=default_profile_id,
        runtime_snapshot=runtime_snapshot,
        runtime_snapshot_producer=runtime_snapshot_producer,
        operator_runtime_mode=operator_runtime_mode,
    )


def build_startup_artifacts_from_env(
    *,
    default_mode: RuntimeMode = "fixture_demo",
    default_profile_id: str | None = None,
    query_action_requested: bool = False,
    runtime_snapshot: RuntimeReadinessSnapshot | None = None,
    runtime_snapshot_producer: RuntimeSnapshotProducer | None = None,
    operator_runtime_mode: OperatorRuntimeMode | str | None = None,
) -> StartupArtifacts:
    resolved_operator_runtime_mode = operator_runtime_mode
    if (
        resolved_operator_runtime_mode is None
        and runtime_snapshot is None
        and runtime_snapshot_producer is None
    ):
        resolved_operator_runtime_mode = operator_runtime_mode_from_env()
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
        operator_runtime = resolve_operator_runtime_snapshot(
            mode=resolved_operator_runtime_mode,
            producer=runtime_snapshot_producer,
            runtime_snapshot=runtime_snapshot,
        )
        shell = _build_startup_shell(report, operator_runtime=operator_runtime)
        return StartupArtifacts(shell=shell, report=report, ready=False, config=None, operator_runtime=operator_runtime)

    return build_startup_artifacts(
        request,
        query_action_requested=query_action_requested,
        runtime_snapshot=runtime_snapshot,
        runtime_snapshot_producer=runtime_snapshot_producer,
        operator_runtime_mode=resolved_operator_runtime_mode,
    )


def build_startup_artifacts(
    request: LaunchRequest,
    *,
    query_action_requested: bool = False,
    runtime_snapshot: RuntimeReadinessSnapshot | None = None,
    runtime_snapshot_producer: RuntimeSnapshotProducer | None = None,
    operator_runtime_mode: OperatorRuntimeMode | str | None = None,
) -> StartupArtifacts:
    report = build_preflight_report(request)
    return _build_startup_artifacts_from_report(
        report,
        query_action_requested=query_action_requested,
        runtime_snapshot=runtime_snapshot,
        runtime_snapshot_producer=runtime_snapshot_producer,
        operator_runtime_mode=operator_runtime_mode,
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
        market_data_config=_resolve_market_data_config_from_env(),
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
        requested_mode = parse_runtime_mode(raw_mode) if raw_mode is not None else None
    else:
        requested_mode = parse_runtime_mode(raw_mode or default_mode)
        mode = requested_mode
        profile = _resolve_profile_with_diagnostics(default_profile_id_for_mode(mode))

    return _build_launch_request(
        profile=profile,
        requested_mode=requested_mode,
        fixtures_root=_fixtures_root_from_env(),
        lockout=_lockout_from_env(),
        adapter_binding=os.getenv("NTB_MODEL_ADAPTER_REF"),
    )


def resolve_launch_request_for_profile_id(
    profile_id: str,
    *,
    requested_mode: RuntimeMode | None = None,
    fixtures_root: Path | None = None,
    lockout: bool | None = None,
    adapter_binding: str | None = None,
    use_env_defaults: bool = True,
) -> LaunchRequest:
    profile = _resolve_profile_with_diagnostics(profile_id)
    resolved_fixtures_root = fixtures_root
    if resolved_fixtures_root is None and use_env_defaults:
        resolved_fixtures_root = _fixtures_root_from_env()

    resolved_lockout = lockout
    if resolved_lockout is None:
        resolved_lockout = _lockout_from_env() if use_env_defaults else False

    resolved_adapter_binding = adapter_binding
    if resolved_adapter_binding is None and use_env_defaults:
        resolved_adapter_binding = os.getenv("NTB_MODEL_ADAPTER_REF")

    return _build_launch_request(
        profile=profile,
        requested_mode=requested_mode,
        fixtures_root=resolved_fixtures_root,
        lockout=resolved_lockout,
        adapter_binding=resolved_adapter_binding,
    )


def _build_launch_request(
    *,
    profile: RuntimeProfile,
    requested_mode: RuntimeMode | None,
    fixtures_root: Path | None,
    lockout: bool,
    adapter_binding: str | None,
) -> LaunchRequest:
    mode = requested_mode or profile.runtime_mode
    if requested_mode is not None and profile.runtime_mode != requested_mode:
        raise RuntimeDiagnosticError(
            category=DIAG_LAUNCH_PREFLIGHT_MISMATCH,
            summary=(
                f"Runtime profile {profile.profile_id} requires runtime mode {profile.runtime_mode}, "
                f"got {requested_mode}."
            ),
            remedy="Either remove NTB_CONSOLE_MODE or set it to the runtime mode required by the selected profile.",
        )

    resolved_adapter_binding: str | None = adapter_binding
    if profile.runtime_mode == "preserved_engine":
        resolved_adapter_binding = resolved_adapter_binding or profile.default_model_adapter_ref

    return LaunchRequest(
        mode=mode,
        profile=profile,
        lockout=lockout,
        fixtures_root=fixtures_root,
        adapter_binding=resolved_adapter_binding,
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


def attach_launch_metadata(
    shell: dict[str, object],
    report: PreflightReport,
    *,
    runtime_snapshot: RuntimeReadinessSnapshot | None = None,
    operator_runtime: OperatorRuntimeSnapshotResult | None = None,
) -> dict[str, object]:
    resolved_operator_runtime = operator_runtime or resolve_operator_runtime_snapshot(runtime_snapshot=runtime_snapshot)
    _attach_five_contract_readiness_summary(
        shell,
        report,
        runtime_snapshot=resolved_operator_runtime.snapshot,
    )
    _attach_runtime_identity(shell, report)
    _attach_operator_live_runtime_metadata(shell, resolved_operator_runtime)
    _attach_startup_payload(shell, report)
    return shell


def _attach_five_contract_readiness_summary(
    shell: dict[str, object],
    report: PreflightReport,
    *,
    runtime_snapshot: RuntimeReadinessSnapshot | None,
) -> None:
    surfaces = shell.get("surfaces")
    if not isinstance(surfaces, dict) or report.request is None:
        return
    surfaces["five_contract_readiness_summary"] = build_five_contract_readiness_summary_surface(
        active_profile_id=report.request.profile.profile_id,
        runtime_snapshot=runtime_snapshot,
    )


def _attach_operator_live_runtime_metadata(
    shell: dict[str, object],
    operator_runtime: OperatorRuntimeSnapshotResult,
) -> None:
    payload = operator_runtime.to_dict()
    stream_health = _stream_health_payload(operator_runtime)
    shell["operator_live_runtime"] = payload
    if stream_health is not None:
        shell["stream_health"] = stream_health
        cockpit = shell.get("r14_cockpit")
        if isinstance(cockpit, dict):
            runtime_status = cockpit.get("runtime_status")
            if isinstance(runtime_status, dict):
                runtime_status["stream_health"] = stream_health
    runtime = shell.get("runtime")
    if not isinstance(runtime, dict):
        runtime = {}
        shell["runtime"] = runtime
    runtime.update(
        {
            "operator_live_runtime_mode": operator_runtime.mode,
            "operator_live_runtime_status": operator_runtime.status,
            "operator_live_runtime_source": operator_runtime.source,
            "operator_live_runtime_requested": operator_runtime.requested_live_runtime,
            "operator_live_runtime_cache_derived": operator_runtime.runtime_cache_derived,
            "operator_live_runtime_refresh_floor_seconds": operator_runtime.refresh_floor_seconds,
            "operator_live_runtime_blocking_reasons": list(operator_runtime.blocking_reasons),
            "operator_live_runtime_cache_provider_status": operator_runtime.cache_provider_status,
            "operator_live_runtime_cache_generated_at": operator_runtime.cache_generated_at,
            "operator_live_runtime_cache_snapshot_ready": operator_runtime.cache_snapshot_ready,
        }
    )


def _stream_health_payload(operator_runtime: OperatorRuntimeSnapshotResult) -> dict[str, object] | None:
    if operator_runtime.mode != "OPERATOR_LIVE_RUNTIME":
        return None
    if isinstance(operator_runtime.snapshot, StreamManagerSnapshot):
        from .viewmodels.mappers import stream_health_vm_from_snapshot

        return stream_health_vm_from_snapshot(operator_runtime.snapshot).to_dict()
    return {
        "connection_state": operator_runtime.cache_provider_status or "unavailable",
        "token_status": "unavailable",
        "token_expires_in_seconds": None,
        "reconnect_attempts": 0,
        "reconnect_active": operator_runtime.status == "LIVE_RUNTIME_UNAVAILABLE",
        "per_contract_status": {},
        "stale_contracts": [],
        "blocking_reasons": list(operator_runtime.blocking_reasons),
        "overall_health": "unavailable",
    }


def _build_startup_shell(
    report: PreflightReport,
    *,
    operator_runtime: OperatorRuntimeSnapshotResult,
) -> dict[str, object]:
    shell: dict[str, object] = {
        "title": "NTB Marimo Console",
        "surfaces": {},
        "runtime": {},
    }
    attach_launch_metadata(shell, report, operator_runtime=operator_runtime)
    return shell


def _build_startup_artifacts_from_report(
    report: PreflightReport,
    *,
    query_action_requested: bool,
    runtime_snapshot: RuntimeReadinessSnapshot | None,
    runtime_snapshot_producer: RuntimeSnapshotProducer | None,
    operator_runtime_mode: OperatorRuntimeMode | str | None,
) -> StartupArtifacts:
    operator_runtime = resolve_operator_runtime_snapshot(
        mode=operator_runtime_mode,
        producer=runtime_snapshot_producer,
        runtime_snapshot=runtime_snapshot,
    )
    if not report.passed or report.request is None:
        shell = _build_startup_shell(report, operator_runtime=operator_runtime)
        return StartupArtifacts(shell=shell, report=report, ready=False, config=None, operator_runtime=operator_runtime)

    request = report.request
    config = LaunchConfig(
        mode=request.mode,
        profile=request.profile,
        lockout=request.lockout,
        fixtures_root=request.fixtures_root,
        adapter_binding=request.adapter_binding,
        model_adapter=report.resolved_adapter,
        market_data_config=_resolve_market_data_config_from_env(),
        preflight=report,
    )

    try:
        assembly = assemble_runtime_for_profile(
            profile=config.profile,
            fixtures_root=config.fixtures_root,
            lockout=config.lockout,
            model_adapter=config.model_adapter,
            market_data_config=config.market_data_config,
        )
        artifacts = build_phase1_artifacts_from_assembly(
            assembly,
            query_action_requested=query_action_requested,
        )
        shell = build_phase1_shell_from_artifacts(
            artifacts,
            inputs=assembly.inputs,
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
        shell = _build_startup_shell(failed_report, operator_runtime=operator_runtime)
        return StartupArtifacts(shell=shell, report=failed_report, ready=False, config=config, operator_runtime=operator_runtime)

    attach_launch_metadata(shell, report, operator_runtime=operator_runtime)
    return StartupArtifacts(
        shell=shell,
        report=report,
        ready=True,
        config=config,
        operator_runtime=operator_runtime,
        trigger_state_results=artifacts.trigger_state_results,
    )


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


def _fixtures_root_from_env() -> Path | None:
    fixtures_root_env = os.getenv("NTB_FIXTURES_ROOT")
    if not fixtures_root_env:
        return None
    return Path(fixtures_root_env).expanduser()


def _lockout_from_env() -> bool:
    return _parse_bool_env(os.getenv("NTB_FIXTURE_LOCKOUT"), default=False)


def _resolve_market_data_config_from_env() -> FuturesQuoteServiceConfig:
    return resolve_futures_quote_service_config(
        _market_data_env_values(),
        target_root=_market_data_target_root(),
    )


def _market_data_env_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for key in (
        "NTB_MARKET_DATA_PROVIDER",
        "NTB_MARKET_DATA_SYMBOL",
        "NTB_MARKET_DATA_FIELD_IDS",
        "NTB_MARKET_DATA_MAX_QUOTE_AGE_SECONDS",
        "NTB_MARKET_DATA_TIMEOUT_SECONDS",
        "SCHWAB_TOKEN_PATH",
    ):
        value = os.getenv(key)
        if value is not None:
            values[key] = value
    return values


def _market_data_target_root() -> Path:
    return Path(__file__).resolve().parents[2]
