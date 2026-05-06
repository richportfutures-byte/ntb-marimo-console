from __future__ import annotations

from collections.abc import Mapping
from enum import Enum

from .bootstrap import platform_bootstrap_command
from .profile_operations import build_profile_operations_snapshot
from .runtime_diagnostics import (
    DIAG_ADAPTER_RESOLUTION_FAILURE,
    DIAG_INVALID_ARTIFACT_CONTRACT,
    DIAG_LAUNCH_PREFLIGHT_MISMATCH,
    DIAG_MISSING_ARTIFACT_FILES,
    DIAG_MISSING_DEPENDENCY,
    DIAG_RUNTIME_ASSEMBLY_FAILURE,
    DIAG_UNSUPPORTED_PROFILE,
    PreflightReport,
    runtime_identity_payload,
)


class StartupReadinessState(str, Enum):
    APP_LOADED = "APP_LOADED"
    PROFILE_SELECTED = "PROFILE_SELECTED"
    PREFLIGHT_PASSED = "PREFLIGHT_PASSED"
    RUNTIME_ASSEMBLED = "RUNTIME_ASSEMBLED"
    OPERATOR_SURFACES_READY = "OPERATOR_SURFACES_READY"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"


def build_startup_payload(
    report: PreflightReport,
    *,
    runtime_shell: Mapping[str, object] | None = None,
) -> dict[str, object]:
    identity = runtime_identity_payload(report)
    profile_operations = build_profile_operations_snapshot(
        current_profile_id=str(identity.get("profile_id")) if identity.get("profile_id") is not None else None
    )
    supported_profiles = [
        {
            "profile_id": profile.profile_id,
            "runtime_mode": profile.runtime_mode,
            "runtime_mode_label": profile.runtime_mode_label,
            "profile_kind": profile.profile_kind,
            "contract": profile.contract,
            "session_date": profile.session_date,
            "active": profile.active,
            "final_target_contract": profile.final_target_contract,
            "contract_policy": profile.contract_policy,
            "selectable": profile.operator_selectable,
        }
        for profile in profile_operations.operator_selectable_profiles
    ]
    legacy_profiles = [
        {
            "profile_id": profile.profile_id,
            "runtime_mode": profile.runtime_mode,
            "runtime_mode_label": profile.runtime_mode_label,
            "profile_kind": profile.profile_kind,
            "contract": profile.contract,
            "session_date": profile.session_date,
            "active": profile.active,
            "final_target_contract": profile.final_target_contract,
            "contract_policy": profile.contract_policy,
            "selectable": profile.operator_selectable,
        }
        for profile in profile_operations.legacy_historical_profiles
    ]
    candidate_profiles = [
        {
            "contract": candidate.contract,
            "profile_id": candidate.profile_id,
            "status": candidate.status,
            "reason_category": candidate.reason_category,
            "reason_label": candidate.reason_label,
            "summary": candidate.summary,
        }
        for candidate in profile_operations.candidate_profiles
    ]
    blocked_candidates = [candidate for candidate in candidate_profiles if candidate["status"] == "blocked"]
    readiness_state, readiness_history = _readiness_path(report, runtime_shell=runtime_shell)
    current_session_state = _resolve_current_session_state(runtime_shell, readiness_state)
    operator_ready = readiness_state == StartupReadinessState.OPERATOR_SURFACES_READY.value
    blocking_checks = [check for check in identity["preflight_checks"] if not check["passed"]]

    return {
        "app_name": "NTB Marimo Console",
        "selected_profile_id": identity.get("profile_id", "<unresolved>"),
        "supported_profiles": supported_profiles,
        "supported_profile_ids": [profile["profile_id"] for profile in supported_profiles],
        "legacy_historical_profiles": legacy_profiles,
        "legacy_historical_profile_ids": [profile["profile_id"] for profile in legacy_profiles],
        "candidate_profiles": candidate_profiles,
        "blocked_candidates": blocked_candidates,
        "candidate_audit_available": profile_operations.audit_available,
        "candidate_audit_summary": profile_operations.audit_summary,
        "runtime_mode": identity.get("runtime_mode", "<unresolved>"),
        "runtime_mode_label": _runtime_mode_label(identity.get("runtime_mode")),
        "runtime_backend": identity.get("runtime_backend", "<unresolved>"),
        "contract": identity.get("contract", "<unresolved>"),
        "session_date": identity.get("session_date", "<unresolved>"),
        "artifact_root": identity.get("artifact_root", "<unresolved>"),
        "adapter_binding": identity.get("adapter_binding", "<unresolved>"),
        "preflight_status": identity.get("preflight_status", "FAIL"),
        "preflight_passed": identity.get("preflight_passed", False),
        "readiness_state": readiness_state,
        "readiness_history": readiness_history,
        "operator_ready": operator_ready,
        "current_session_state": current_session_state,
        "status_summary": _status_summary(readiness_state, operator_ready),
        "next_action": _next_action(report, operator_ready=operator_ready),
        "blocking_checks": blocking_checks,
        "running_as": _running_as_label(identity.get("runtime_backend")),
    }


def _readiness_path(
    report: PreflightReport,
    *,
    runtime_shell: Mapping[str, object] | None,
) -> tuple[str, list[str]]:
    history = [StartupReadinessState.APP_LOADED.value]

    if report.request is not None:
        history.append(StartupReadinessState.PROFILE_SELECTED.value)

    core_preflight_passed = _core_preflight_passed(report)
    has_runtime_failure = _has_failed_category(report, DIAG_RUNTIME_ASSEMBLY_FAILURE)

    if core_preflight_passed:
        history.append(StartupReadinessState.PREFLIGHT_PASSED.value)

    if has_runtime_failure:
        history.append(StartupReadinessState.ERROR.value)
        return StartupReadinessState.ERROR.value, history

    if not report.passed:
        history.append(StartupReadinessState.BLOCKED.value)
        return StartupReadinessState.BLOCKED.value, history

    if runtime_shell is not None:
        history.append(StartupReadinessState.RUNTIME_ASSEMBLED.value)
        history.append(StartupReadinessState.OPERATOR_SURFACES_READY.value)
        return StartupReadinessState.OPERATOR_SURFACES_READY.value, history

    history.append(StartupReadinessState.BLOCKED.value)
    return StartupReadinessState.BLOCKED.value, history


def _core_preflight_passed(report: PreflightReport) -> bool:
    for check in report.checks:
        if check.category == DIAG_RUNTIME_ASSEMBLY_FAILURE:
            continue
        if not check.passed:
            return False
    return report.request is not None


def _has_failed_category(report: PreflightReport, category: str) -> bool:
    return any((not check.passed) and check.category == category for check in report.checks)


def _resolve_current_session_state(
    runtime_shell: Mapping[str, object] | None,
    readiness_state: str,
) -> str:
    fallback_state = "NOT_ASSEMBLED"
    if readiness_state == StartupReadinessState.BLOCKED.value:
        fallback_state = "STARTUP_BLOCKED"
    elif readiness_state == StartupReadinessState.OPERATOR_SURFACES_READY.value:
        fallback_state = "STARTUP_READY"
    elif readiness_state == StartupReadinessState.ERROR.value:
        fallback_state = "ERROR"

    if runtime_shell is None:
        return fallback_state

    runtime = runtime_shell.get("runtime")
    if not isinstance(runtime, Mapping):
        return fallback_state

    state = runtime.get("session_state")
    if state is None:
        return fallback_state
    return str(state)


def _status_summary(readiness_state: str, operator_ready: bool) -> str:
    if operator_ready:
        return "Console ready for operator use."
    if readiness_state == StartupReadinessState.ERROR.value:
        return "Startup reached a runtime error after preflight. The console is blocked."
    return "Startup is blocked until the selected profile passes preflight and runtime assembly."


def _next_action(report: PreflightReport, *, operator_ready: bool) -> str:
    if operator_ready:
        return (
            "Review Startup Status, confirm the Pre-Market Brief and Readiness Matrix, "
            "then rely on the Live Query gate before acting."
        )

    failed_categories = [check.category for check in report.checks if not check.passed]
    if not failed_categories:
        return "Investigate the startup state before using the console."

    category = failed_categories[0]
    if category == DIAG_UNSUPPORTED_PROFILE:
        return (
            "Select one of the supported profile ids shown below with Profile Selector, "
            "or restart with NTB_CONSOLE_PROFILE set to a supported profile."
        )
    if category == DIAG_MISSING_ARTIFACT_FILES:
        return (
            "Restore or refresh the declared artifacts, then use Reload Current Profile or switch to "
            "another supported profile."
        )
    if category == DIAG_INVALID_ARTIFACT_CONTRACT:
        return (
            "Replace malformed artifacts with contract-valid inputs, then use Reload Current Profile or "
            "switch to another supported profile."
        )
    if category == DIAG_MISSING_DEPENDENCY:
        return (
            f"Run {platform_bootstrap_command()}, rerun preflight, then relaunch or use Profile Selector "
            "after the environment is restored."
        )
    if category == DIAG_ADAPTER_RESOLUTION_FAILURE:
        return "Fix the adapter binding, rerun preflight, then reload or switch profiles."
    if category == DIAG_LAUNCH_PREFLIGHT_MISMATCH:
        return (
            "Align NTB_CONSOLE_MODE with the selected profile, rerun preflight, then reload the current "
            "profile or relaunch."
        )
    if category == DIAG_RUNTIME_ASSEMBLY_FAILURE:
        return "Fix the runtime assembly error, then reload the current profile or switch to another supported profile."
    return "Fix the reported startup diagnostics, then reload the current profile or switch to another supported profile."


def _runtime_mode_label(value: object) -> str:
    if value == "fixture_demo":
        return "Fixture/Demo"
    if value == "preserved_engine":
        return "Preserved Engine"
    return str(value) if value is not None else "<unresolved>"


def _running_as_label(value: object) -> str:
    if value == "fixture_demo":
        return "Fixture/Demo"
    if value == "preserved_engine_backed":
        return "Preserved-Engine-Backed"
    return str(value) if value is not None else "<unresolved>"
