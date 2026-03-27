from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass
from enum import Enum

from .launch_config import (
    LaunchConfig,
    StartupArtifacts,
    attach_launch_metadata,
    build_startup_artifacts,
    build_startup_artifacts_from_env,
)
from .runtime_diagnostics import (
    ArtifactSourceSnapshot,
    PreflightReport,
    build_artifact_source_snapshot,
)
from .runtime_modes import RuntimeAssembly, assemble_runtime_for_profile, build_app_shell_from_assembly
from .state.session_state import OperatorSessionMachine, SessionState


class LifecycleAction(str, Enum):
    INITIAL_LOAD = "INITIAL_LOAD"
    RUN_BOUNDED_QUERY = "RUN_BOUNDED_QUERY"
    RELOAD_CURRENT_PROFILE = "RELOAD_CURRENT_PROFILE"
    RESET_SESSION = "RESET_SESSION"


@dataclass(frozen=True)
class SessionLifecycle:
    shell: dict[str, object]
    baseline_shell: dict[str, object] | None
    report: PreflightReport
    ready: bool
    config: LaunchConfig | None
    assembly: RuntimeAssembly | None
    artifact_snapshot: ArtifactSourceSnapshot | None
    lifecycle_state: SessionState
    lifecycle_history: tuple[SessionState, ...]
    last_action: LifecycleAction
    status_summary: str
    next_action: str
    reload_changed_sources: bool | None


def load_session_lifecycle_from_env(
    *,
    default_mode: str = "fixture_demo",
    default_profile_id: str | None = None,
) -> SessionLifecycle:
    startup = build_startup_artifacts_from_env(
        default_mode=default_mode,
        default_profile_id=default_profile_id,
        query_action_requested=False,
    )
    assembly = _assemble_runtime(startup)
    artifact_snapshot = _artifact_snapshot_for_report(startup.report)
    current_shell = deepcopy(startup.shell)
    baseline_shell = deepcopy(startup.shell) if startup.ready else None
    lifecycle_history = _build_initial_history(current_shell)
    lifecycle_state = _shell_session_state(current_shell)
    status_summary = _initial_summary(startup)
    next_action = _extract_next_action(current_shell)
    return _finalize_lifecycle(
        shell=current_shell,
        baseline_shell=baseline_shell,
        report=startup.report,
        ready=startup.ready,
        config=startup.config,
        assembly=assembly,
        artifact_snapshot=artifact_snapshot,
        lifecycle_state=lifecycle_state,
        lifecycle_history=lifecycle_history,
        last_action=LifecycleAction.INITIAL_LOAD,
        status_summary=status_summary,
        next_action=next_action,
        reload_changed_sources=None,
    )


def request_query_action(lifecycle: SessionLifecycle) -> SessionLifecycle:
    if lifecycle.assembly is None or lifecycle.config is None:
        return _blocked_action(
            lifecycle,
            summary=(
                "Bounded query remains blocked because no valid runtime context is loaded. "
                "Reload the selected profile after preflight passes."
            ),
        )

    current_shell = build_app_shell_from_assembly(
        lifecycle.assembly,
        query_action_requested=True,
    )
    attach_launch_metadata(current_shell, lifecycle.report)
    lifecycle_history = _continue_history(
        lifecycle.lifecycle_history,
        runtime_shell=current_shell,
    )
    lifecycle_state = _shell_session_state(current_shell)
    status_summary = _query_summary(current_shell)
    next_action = _extract_next_action(current_shell)
    return _finalize_lifecycle(
        shell=current_shell,
        baseline_shell=lifecycle.baseline_shell,
        report=lifecycle.report,
        ready=lifecycle.ready,
        config=lifecycle.config,
        assembly=lifecycle.assembly,
        artifact_snapshot=lifecycle.artifact_snapshot,
        lifecycle_state=lifecycle_state,
        lifecycle_history=lifecycle_history,
        last_action=LifecycleAction.RUN_BOUNDED_QUERY,
        status_summary=status_summary,
        next_action=next_action,
        reload_changed_sources=lifecycle.reload_changed_sources,
    )


def reset_session(lifecycle: SessionLifecycle) -> SessionLifecycle:
    if lifecycle.baseline_shell is None:
        return _blocked_action(
            lifecycle,
            summary=(
                "Session reset is unavailable because no validated profile context is loaded. "
                "Reload the current profile first."
            ),
        )

    current_shell = deepcopy(lifecycle.baseline_shell)
    lifecycle_history = _continue_history(
        lifecycle.lifecycle_history,
        action_states=(
            SessionState.SESSION_RESET_REQUESTED,
            SessionState.SESSION_RESET_COMPLETED,
        ),
        runtime_shell=current_shell,
    )
    next_action = _extract_next_action(current_shell)
    return _finalize_lifecycle(
        shell=current_shell,
        baseline_shell=deepcopy(lifecycle.baseline_shell),
        report=lifecycle.report,
        ready=lifecycle.ready,
        config=lifecycle.config,
        assembly=lifecycle.assembly,
        artifact_snapshot=lifecycle.artifact_snapshot,
        lifecycle_state=SessionState.SESSION_RESET_COMPLETED,
        lifecycle_history=lifecycle_history,
        last_action=LifecycleAction.RESET_SESSION,
        status_summary=(
            "Session reset completed. The selected profile remains loaded, but the bounded query, "
            "Decision Review, and Audit / Replay state were cleared."
        ),
        next_action=next_action,
        reload_changed_sources=lifecycle.reload_changed_sources,
    )


def reload_current_profile(lifecycle: SessionLifecycle) -> SessionLifecycle:
    request = lifecycle.report.request
    if request is None:
        return _blocked_action(
            lifecycle,
            summary=(
                "Profile reload is unavailable because the current startup selection did not resolve "
                "to a supported runtime profile."
            ),
        )

    startup = build_startup_artifacts(
        request,
        query_action_requested=False,
    )
    artifact_snapshot = _artifact_snapshot_for_report(startup.report)
    reload_changed_sources = _compare_artifact_snapshots(
        lifecycle.artifact_snapshot,
        artifact_snapshot,
    )

    if not startup.ready:
        current_shell = deepcopy(startup.shell)
        lifecycle_history = _continue_history(
            lifecycle.lifecycle_history,
            action_states=(
                SessionState.REFRESH_REQUESTED,
                SessionState.REFRESH_FAILED,
            ),
        )
        return _finalize_lifecycle(
            shell=current_shell,
            baseline_shell=None,
            report=startup.report,
            ready=False,
            config=startup.config,
            assembly=None,
            artifact_snapshot=artifact_snapshot,
            lifecycle_state=SessionState.REFRESH_FAILED,
            lifecycle_history=lifecycle_history,
            last_action=LifecycleAction.RELOAD_CURRENT_PROFILE,
            status_summary=(
                "Profile reload failed closed. The console is blocked until the selected profile "
                "passes preflight and runtime assembly again."
            ),
            next_action=_extract_next_action(current_shell),
            reload_changed_sources=reload_changed_sources,
        )

    current_shell = deepcopy(startup.shell)
    lifecycle_history = _continue_history(
        lifecycle.lifecycle_history,
        action_states=(
            SessionState.REFRESH_REQUESTED,
            SessionState.REFRESH_COMPLETED,
        ),
        runtime_shell=current_shell,
    )
    return _finalize_lifecycle(
        shell=current_shell,
        baseline_shell=deepcopy(startup.shell),
        report=startup.report,
        ready=True,
        config=startup.config,
        assembly=_assemble_runtime(startup),
        artifact_snapshot=artifact_snapshot,
        lifecycle_state=SessionState.REFRESH_COMPLETED,
        lifecycle_history=lifecycle_history,
        last_action=LifecycleAction.RELOAD_CURRENT_PROFILE,
        status_summary=_refresh_summary(reload_changed_sources),
        next_action=_extract_next_action(current_shell),
        reload_changed_sources=reload_changed_sources,
    )


def _assemble_runtime(startup: StartupArtifacts) -> RuntimeAssembly | None:
    if not startup.ready or startup.config is None:
        return None
    return assemble_runtime_for_profile(
        profile=startup.config.profile,
        fixtures_root=startup.config.fixtures_root,
        lockout=startup.config.lockout,
        model_adapter=startup.config.model_adapter,
    )


def _artifact_snapshot_for_report(report: PreflightReport) -> ArtifactSourceSnapshot | None:
    if report.request is None:
        return None
    return build_artifact_source_snapshot(report.request)


def _build_initial_history(shell: Mapping[str, object]) -> tuple[SessionState, ...]:
    return _continue_history(tuple(), runtime_shell=shell)


def _continue_history(
    history: tuple[SessionState, ...],
    *,
    action_states: tuple[SessionState, ...] = (),
    runtime_shell: Mapping[str, object] | None = None,
) -> tuple[SessionState, ...]:
    machine = OperatorSessionMachine.from_history(history) if history else OperatorSessionMachine()
    for state in action_states:
        machine.transition(state)

    runtime_states = _normalized_runtime_sequence(runtime_shell)
    overlap = _history_overlap(machine.state_history, runtime_states)
    for state in runtime_states[overlap:]:
        if state == machine.state:
            continue
        machine.transition(state)
    return machine.state_history


def _normalized_runtime_sequence(shell: Mapping[str, object] | None) -> tuple[SessionState, ...]:
    if shell is None:
        return tuple()

    runtime = shell.get("runtime")
    states: list[SessionState] = []
    if isinstance(runtime, Mapping):
        raw_history = runtime.get("state_history")
        if isinstance(raw_history, list):
            for item in raw_history:
                states.append(SessionState(str(item)))
    if not states:
        states.append(_shell_session_state(shell))
    if states and states[0] == SessionState.BOOTSTRAP:
        return tuple(states[1:])
    return tuple(states)


def _history_overlap(
    history: tuple[SessionState, ...],
    candidate: tuple[SessionState, ...],
) -> int:
    max_overlap = min(len(history), len(candidate))
    for size in range(max_overlap, 0, -1):
        if history[-size:] == candidate[:size]:
            return size
    return 0


def _shell_session_state(shell: Mapping[str, object]) -> SessionState:
    runtime = shell.get("runtime")
    if isinstance(runtime, Mapping):
        raw_state = runtime.get("session_state")
        if raw_state is not None:
            return SessionState(str(raw_state))

    startup = shell.get("startup")
    if isinstance(startup, Mapping):
        raw_state = startup.get("current_session_state")
        if raw_state is not None:
            return SessionState(str(raw_state))

    return SessionState.ERROR


def _initial_summary(startup: StartupArtifacts) -> str:
    if startup.ready:
        return (
            "Current profile loaded. The session is ready to monitor live-query eligibility "
            "against the currently loaded context."
        )
    return (
        "Startup is blocked. The console does not have a valid loaded session context yet."
    )


def _query_summary(shell: Mapping[str, object]) -> str:
    workflow = shell.get("workflow")
    if not isinstance(workflow, Mapping):
        return "Bounded query action completed with an unavailable workflow summary."

    decision_ready = workflow.get("decision_review_ready") is True
    audit_ready = workflow.get("audit_replay_ready") is True
    query_status = str(workflow.get("query_action_status", "<unavailable>"))
    if query_status == "FAILED":
        return (
            "Bounded query failed closed against the currently loaded snapshot. "
            "Decision Review and Audit / Replay remain blocked."
        )
    if decision_ready and audit_ready:
        return (
            "Bounded query completed against the currently loaded snapshot. "
            "Decision Review and Audit / Replay are ready."
        )
    if decision_ready:
        return (
            "Bounded query completed against the currently loaded snapshot. "
            "Decision Review is ready, but Audit / Replay remains blocked."
        )
    return str(workflow.get("status_summary", "<unavailable>"))


def _refresh_summary(reload_changed_sources: bool | None) -> str:
    if reload_changed_sources is True:
        return (
            "Current profile revalidated and reloaded from the declared source artifacts. "
            "New source files were loaded for this session."
        )
    if reload_changed_sources is False:
        return (
            "Current profile revalidated and reloaded from the declared source artifacts. "
            "The source files were unchanged, so the session now reflects a clean reload of the same inputs."
        )
    return (
        "Current profile revalidated and reloaded from the declared source artifacts."
    )


def _compare_artifact_snapshots(
    previous: ArtifactSourceSnapshot | None,
    current: ArtifactSourceSnapshot | None,
) -> bool | None:
    if previous is None or current is None:
        return None
    return previous.signature != current.signature


def _extract_next_action(shell: Mapping[str, object]) -> str:
    workflow = shell.get("workflow")
    if isinstance(workflow, Mapping):
        value = workflow.get("next_action")
        if value is not None:
            return str(value)

    startup = shell.get("startup")
    if isinstance(startup, Mapping):
        value = startup.get("next_action")
        if value is not None:
            return str(value)

    return "Inspect the current session state before proceeding."


def _blocked_action(lifecycle: SessionLifecycle, *, summary: str) -> SessionLifecycle:
    return _finalize_lifecycle(
        shell=deepcopy(lifecycle.shell),
        baseline_shell=deepcopy(lifecycle.baseline_shell) if lifecycle.baseline_shell is not None else None,
        report=lifecycle.report,
        ready=lifecycle.ready,
        config=lifecycle.config,
        assembly=lifecycle.assembly,
        artifact_snapshot=lifecycle.artifact_snapshot,
        lifecycle_state=lifecycle.lifecycle_state,
        lifecycle_history=lifecycle.lifecycle_history,
        last_action=lifecycle.last_action,
        status_summary=summary,
        next_action=lifecycle.next_action,
        reload_changed_sources=lifecycle.reload_changed_sources,
    )


def _finalize_lifecycle(
    *,
    shell: dict[str, object],
    baseline_shell: dict[str, object] | None,
    report: PreflightReport,
    ready: bool,
    config: LaunchConfig | None,
    assembly: RuntimeAssembly | None,
    artifact_snapshot: ArtifactSourceSnapshot | None,
    lifecycle_state: SessionState,
    lifecycle_history: tuple[SessionState, ...],
    last_action: LifecycleAction,
    status_summary: str,
    next_action: str,
    reload_changed_sources: bool | None,
) -> SessionLifecycle:
    shell["lifecycle"] = _build_lifecycle_panel(
        shell=shell,
        lifecycle_state=lifecycle_state,
        lifecycle_history=lifecycle_history,
        last_action=last_action,
        status_summary=status_summary,
        next_action=next_action,
        reload_changed_sources=reload_changed_sources,
        reset_available=baseline_shell is not None and ready,
        reload_available=report.request is not None,
    )
    return SessionLifecycle(
        shell=shell,
        baseline_shell=baseline_shell,
        report=report,
        ready=ready,
        config=config,
        assembly=assembly,
        artifact_snapshot=artifact_snapshot,
        lifecycle_state=lifecycle_state,
        lifecycle_history=lifecycle_history,
        last_action=last_action,
        status_summary=status_summary,
        next_action=next_action,
        reload_changed_sources=reload_changed_sources,
    )


def _build_lifecycle_panel(
    *,
    shell: Mapping[str, object],
    lifecycle_state: SessionState,
    lifecycle_history: tuple[SessionState, ...],
    last_action: LifecycleAction,
    status_summary: str,
    next_action: str,
    reload_changed_sources: bool | None,
    reset_available: bool,
    reload_available: bool,
) -> dict[str, object]:
    startup = shell.get("startup")
    startup_panel = startup if isinstance(startup, Mapping) else {}
    runtime = shell.get("runtime")
    runtime_panel = runtime if isinstance(runtime, Mapping) else {}
    workflow = shell.get("workflow")
    workflow_panel = workflow if isinstance(workflow, Mapping) else {}

    if last_action == LifecycleAction.RELOAD_CURRENT_PROFILE:
        if lifecycle_state == SessionState.REFRESH_FAILED:
            reload_result = "RELOAD_FAILED"
        elif reload_changed_sources is True:
            reload_result = "RELOADED_CHANGED"
        elif reload_changed_sources is False:
            reload_result = "RELOADED_UNCHANGED"
        else:
            reload_result = "RELOADED"
    else:
        reload_result = "NOT_RUN"

    return {
        "current_lifecycle_state": lifecycle_state.value,
        "current_session_state": _shell_session_state(shell).value,
        "state_history": [state.value for state in lifecycle_history],
        "last_action": last_action.value,
        "preflight_reran": last_action == LifecycleAction.RELOAD_CURRENT_PROFILE,
        "reload_result": reload_result,
        "reload_changed_sources": reload_changed_sources,
        "reset_available": reset_available,
        "reload_available": reload_available,
        "selected_profile_id": startup_panel.get("selected_profile_id", runtime_panel.get("profile_id", "<unresolved>")),
        "runtime_mode": startup_panel.get("runtime_mode", runtime_panel.get("runtime_mode", "<unresolved>")),
        "running_as": startup_panel.get("running_as", "<unresolved>"),
        "operator_ready": startup_panel.get("operator_ready", False),
        "query_action_status": workflow_panel.get("query_action_status", "<unavailable>"),
        "decision_review_ready": workflow_panel.get("decision_review_ready", False),
        "audit_replay_ready": workflow_panel.get("audit_replay_ready", False),
        "status_summary": status_summary,
        "next_action": next_action,
        "blocked": startup_panel.get("operator_ready") is not True,
    }
