from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from uuid import uuid4

from .evidence_replay import EvidenceEvent, ReplaySummary
from .launch_config import (
    LaunchConfig,
    RuntimeReadinessSnapshot,
    StartupArtifacts,
    attach_launch_metadata,
    build_startup_artifacts,
    build_startup_artifacts_from_env,
    resolve_launch_request_for_profile_id,
)
from .operator_live_runtime import (
    OperatorRuntimeMode,
    OperatorRuntimeSnapshotResult,
    RuntimeSnapshotProducer,
    resolve_operator_runtime_snapshot,
)
from .profile_operations import evaluate_profile_switch
from .runtime_diagnostics import (
    DIAG_RUNTIME_ASSEMBLY_FAILURE,
    ArtifactSourceSnapshot,
    LaunchRequest,
    PreflightReport,
    build_artifact_source_snapshot,
)
from .app import build_phase1_shell_from_artifacts
from .cockpit_manual_query import (
    COCKPIT_OPERATOR_ACTION_TIMELINE_MAX_ENTRIES,
    CockpitManualQueryResult,
    CockpitOperatorActionTimelineEntry,
    CockpitOperatorNote,
    append_cockpit_operator_note,
    append_operator_action_timeline_entry,
    build_cockpit_contract_readiness_detail,
    build_cockpit_current_state_summary,
    build_cockpit_operator_notes_payload,
    operator_action_status_for_lifecycle_action,
    operator_action_status_from_manual_query_result,
    submit_cockpit_manual_query,
)
from .cockpit_evidence import (
    append_cockpit_evidence_events,
    build_cockpit_event_replay_surface,
    cockpit_evidence_timestamp,
    cockpit_lifecycle_evidence_events,
    cockpit_manual_query_evidence_events,
    cockpit_operator_note_evidence_event,
)
from .contract_universe import normalize_contract_symbol
from .primary_cockpit import primary_cockpit_surface_key
from .runtime_modes import RuntimeAssembly, assemble_runtime_for_profile, build_phase1_artifacts_from_assembly
from .session_evidence import (
    SessionEvidenceRecord,
    append_session_evidence,
    build_session_evidence_panel,
)
from .session_evidence_store import (
    clear_session_evidence_history,
    persist_session_evidence_history,
    restore_session_evidence_history,
)
from .state.session_state import OperatorSessionMachine, SessionState
from .trigger_state import TriggerStateResult
from .trigger_transition_replay_source import TriggerTransitionReplaySource


class LifecycleAction(str, Enum):
    INITIAL_LOAD = "INITIAL_LOAD"
    RUN_BOUNDED_QUERY = "RUN_BOUNDED_QUERY"
    RUN_COCKPIT_MANUAL_QUERY = "RUN_COCKPIT_MANUAL_QUERY"
    RELOAD_CURRENT_PROFILE = "RELOAD_CURRENT_PROFILE"
    RESET_SESSION = "RESET_SESSION"
    SWITCH_PROFILE = "SWITCH_PROFILE"
    ADD_COCKPIT_OPERATOR_NOTE = "ADD_COCKPIT_OPERATOR_NOTE"


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
    profile_switch_target_id: str | None
    profile_switch_result: str
    evidence_app_session_id: str
    evidence_persistence_path: str
    evidence_persist_min_event_index: int
    evidence_restore_status: str
    evidence_restore_message: str
    evidence_persistence_health_status: str
    evidence_last_persistence_status: str
    evidence_last_persistence_message: str
    evidence_last_persistence_at_utc: str | None
    evidence_history: tuple[SessionEvidenceRecord, ...]
    runtime_snapshot: RuntimeReadinessSnapshot | None = None
    operator_runtime: OperatorRuntimeSnapshotResult | None = None
    runtime_snapshot_producer: RuntimeSnapshotProducer | None = None
    operator_runtime_mode: OperatorRuntimeMode | str | None = None
    operator_action_timeline: tuple[CockpitOperatorActionTimelineEntry, ...] = ()
    cockpit_operator_notes: tuple[CockpitOperatorNote, ...] = ()
    cockpit_evidence_events: tuple[EvidenceEvent, ...] = ()
    trigger_transition_replay_source: TriggerTransitionReplaySource = field(
        default_factory=lambda: TriggerTransitionReplaySource(source="session_lifecycle"),
        repr=False,
        compare=False,
    )

    def observe_trigger_state_result(
        self,
        trigger_state_result: TriggerStateResult,
        *,
        timestamp: str | None = None,
        profile_id: str | None = None,
        live_snapshot_ref: str | None = None,
        premarket_brief_ref: str | None = None,
    ) -> tuple[EvidenceEvent, ...]:
        if not isinstance(trigger_state_result, TriggerStateResult):
            raise TypeError("observe_trigger_state_result requires a TriggerStateResult")
        return self.trigger_transition_replay_source.observe(
            trigger_state_result,
            timestamp=_observation_text(timestamp)
            or _observation_text(trigger_state_result.last_updated)
            or "",
            profile_id=_observation_text(profile_id) or _selected_profile_id(self) or "",
            live_snapshot_ref=live_snapshot_ref,
            premarket_brief_ref=premarket_brief_ref,
        )

    def trigger_transition_replay_summary(
        self,
        *,
        contract: str,
        profile_id: str | None = None,
    ) -> ReplaySummary | None:
        return self.trigger_transition_replay_source.replay_summary(
            contract=contract,
            profile_id=_observation_text(profile_id) or _selected_profile_id(self),
        )

    def trigger_transition_log(
        self,
        *,
        contract: str,
        profile_id: str | None = None,
    ) -> dict[str, object] | None:
        return self.trigger_transition_replay_source.trigger_transition_log(
            contract=contract,
            profile_id=_observation_text(profile_id) or _selected_profile_id(self),
        )


def observe_phase1_trigger_state_results(
    lifecycle: SessionLifecycle,
    trigger_state_results: Iterable[TriggerStateResult],
    *,
    timestamp: str | None = None,
    profile_id: str | None = None,
    live_snapshot_ref: str | None = None,
    premarket_brief_ref: str | None = None,
) -> tuple[EvidenceEvent, ...]:
    emitted: list[EvidenceEvent] = []
    for trigger_state_result in trigger_state_results:
        if not isinstance(trigger_state_result, TriggerStateResult):
            raise TypeError("observe_phase1_trigger_state_results requires TriggerStateResult values")
        emitted.extend(
            lifecycle.observe_trigger_state_result(
                trigger_state_result,
                timestamp=timestamp,
                profile_id=profile_id,
                live_snapshot_ref=live_snapshot_ref,
                premarket_brief_ref=premarket_brief_ref,
            )
        )
    return tuple(emitted)


def load_session_lifecycle_from_env(
    *,
    default_mode: str = "fixture_demo",
    default_profile_id: str | None = None,
    evidence_store_path: str | Path | None = None,
    runtime_snapshot: RuntimeReadinessSnapshot | None = None,
    runtime_snapshot_producer: RuntimeSnapshotProducer | None = None,
    operator_runtime_mode: OperatorRuntimeMode | str | None = None,
) -> SessionLifecycle:
    restore_snapshot = restore_session_evidence_history(path=evidence_store_path)
    app_session_id = uuid4().hex
    startup = build_startup_artifacts_from_env(
        default_mode=default_mode,
        default_profile_id=default_profile_id,
        query_action_requested=False,
        runtime_snapshot=runtime_snapshot,
        runtime_snapshot_producer=runtime_snapshot_producer,
        operator_runtime_mode=operator_runtime_mode,
    )
    assembly = _assemble_runtime(startup)
    artifact_snapshot = _artifact_snapshot_for_report(startup.report)
    current_shell = deepcopy(startup.shell)
    baseline_shell = deepcopy(startup.shell) if startup.ready else None
    lifecycle_history = _build_initial_history(current_shell)
    lifecycle_state = _shell_session_state(current_shell)
    status_summary = _initial_summary(startup)
    next_action = _extract_next_action(current_shell)
    lifecycle = _finalize_lifecycle(
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
        profile_switch_target_id=None,
        profile_switch_result="NOT_RUN",
        evidence_app_session_id=app_session_id,
        evidence_persistence_path=restore_snapshot.persistence_path,
        evidence_persist_min_event_index=1,
        evidence_restore_status=restore_snapshot.restore_status,
        evidence_restore_message=restore_snapshot.restore_message,
        evidence_persistence_health_status="UNKNOWN",
        evidence_last_persistence_status="NOT_ATTEMPTED",
        evidence_last_persistence_message="Retained evidence has not been written yet in this app session.",
        evidence_last_persistence_at_utc=None,
        evidence_history=restore_snapshot.history,
        evidence_originating_profile_id=_selected_profile_id_from_shell(current_shell),
        evidence_requested_profile_id=None,
        runtime_snapshot=startup.operator_runtime.snapshot,
        operator_runtime=startup.operator_runtime,
        runtime_snapshot_producer=runtime_snapshot_producer,
        operator_runtime_mode=startup.operator_runtime.mode,
    )
    observe_phase1_trigger_state_results(lifecycle, startup.trigger_state_results)
    return lifecycle


def request_query_action(lifecycle: SessionLifecycle) -> SessionLifecycle:
    if lifecycle.assembly is None or lifecycle.config is None:
        return _blocked_action(
            lifecycle,
            summary=(
                "Bounded query remains blocked because no valid runtime context is loaded. "
                "Reload the selected profile after preflight passes."
            ),
        )

    operator_runtime = _resolve_operator_runtime_for_lifecycle(lifecycle)
    artifacts = build_phase1_artifacts_from_assembly(
        lifecycle.assembly,
        query_action_requested=True,
    )
    current_shell = build_phase1_shell_from_artifacts(
        artifacts,
        inputs=lifecycle.assembly.inputs,
        query_action_requested=True,
    )
    attach_launch_metadata(current_shell, lifecycle.report, operator_runtime=operator_runtime)
    lifecycle_history = _continue_history(
        lifecycle.lifecycle_history,
        runtime_shell=current_shell,
    )
    lifecycle_state = _shell_session_state(current_shell)
    status_summary = _query_summary(current_shell)
    next_action = _extract_next_action(current_shell)
    next_lifecycle = _finalize_lifecycle(
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
        profile_switch_target_id=lifecycle.profile_switch_target_id,
        profile_switch_result=lifecycle.profile_switch_result,
        evidence_app_session_id=lifecycle.evidence_app_session_id,
        evidence_persistence_path=lifecycle.evidence_persistence_path,
        evidence_persist_min_event_index=lifecycle.evidence_persist_min_event_index,
        evidence_restore_status=lifecycle.evidence_restore_status,
        evidence_restore_message=lifecycle.evidence_restore_message,
        evidence_persistence_health_status=lifecycle.evidence_persistence_health_status,
        evidence_last_persistence_status=lifecycle.evidence_last_persistence_status,
        evidence_last_persistence_message=lifecycle.evidence_last_persistence_message,
        evidence_last_persistence_at_utc=lifecycle.evidence_last_persistence_at_utc,
        evidence_history=lifecycle.evidence_history,
        evidence_originating_profile_id=_selected_profile_id(lifecycle),
        evidence_requested_profile_id=None,
        runtime_snapshot=operator_runtime.snapshot,
        operator_runtime=operator_runtime,
        runtime_snapshot_producer=lifecycle.runtime_snapshot_producer,
        operator_runtime_mode=operator_runtime.mode,
        operator_action_timeline=lifecycle.operator_action_timeline,
        cockpit_operator_notes=lifecycle.cockpit_operator_notes,
        cockpit_evidence_events=lifecycle.cockpit_evidence_events,
        trigger_transition_replay_source=lifecycle.trigger_transition_replay_source,
    )
    observe_phase1_trigger_state_results(next_lifecycle, artifacts.trigger_state_results)
    return next_lifecycle


def request_cockpit_manual_query(lifecycle: SessionLifecycle, contract: str) -> SessionLifecycle:
    normalized_contract = normalize_contract_symbol(contract)
    current_shell = deepcopy(lifecycle.shell)
    rows = _fixture_cockpit_rows(current_shell)
    assembly_result = _manual_query_assembly_for_contract(lifecycle, normalized_contract)
    if isinstance(assembly_result, CockpitManualQueryResult):
        result = assembly_result
    else:
        result = submit_cockpit_manual_query(
            contract=normalized_contract,
            action_rows=rows,
            backend=assembly_result.backend,
            pipeline_query=assembly_result.inputs.pipeline_query,
            submitted_at=assembly_result.inputs.pipeline_query.evaluation_timestamp_iso,
        )
    _attach_cockpit_manual_query_result(current_shell, result.to_dict())
    operator_action_status = operator_action_status_from_manual_query_result(
        result,
        runtime_readiness_status=_cockpit_runtime_readiness_status(current_shell),
        runtime_readiness_preserved=_cockpit_runtime_readiness_preserved(current_shell),
    )
    _attach_cockpit_operator_action_status(current_shell, operator_action_status)
    operator_action_timeline = append_operator_action_timeline_entry(
        lifecycle.operator_action_timeline,
        status=operator_action_status,
        recorded_at=result.submitted_at
        or _resolved_recorded_at(lifecycle.operator_runtime),
    )
    event_timestamp = result.submitted_at or cockpit_evidence_timestamp(
        current_shell,
        fallback=_resolved_recorded_at(lifecycle.operator_runtime),
    )
    cockpit_evidence_events = append_cockpit_evidence_events(
        lifecycle.cockpit_evidence_events,
        cockpit_manual_query_evidence_events(
            result=result,
            surface=_fixture_cockpit_surface(current_shell),
            timestamp=event_timestamp,
            sequence=operator_action_timeline[-1].sequence,
            active_profile_id=_selected_profile_id(lifecycle),
        ),
    )
    status_summary = _cockpit_manual_query_summary(result)
    next_action = _cockpit_manual_query_next_action(result)
    return _finalize_lifecycle(
        shell=current_shell,
        baseline_shell=deepcopy(lifecycle.baseline_shell) if lifecycle.baseline_shell is not None else None,
        report=lifecycle.report,
        ready=lifecycle.ready,
        config=lifecycle.config,
        assembly=lifecycle.assembly,
        artifact_snapshot=lifecycle.artifact_snapshot,
        lifecycle_state=lifecycle.lifecycle_state,
        lifecycle_history=lifecycle.lifecycle_history,
        last_action=LifecycleAction.RUN_COCKPIT_MANUAL_QUERY,
        status_summary=status_summary,
        next_action=next_action,
        reload_changed_sources=lifecycle.reload_changed_sources,
        profile_switch_target_id=lifecycle.profile_switch_target_id,
        profile_switch_result=lifecycle.profile_switch_result,
        evidence_app_session_id=lifecycle.evidence_app_session_id,
        evidence_persistence_path=lifecycle.evidence_persistence_path,
        evidence_persist_min_event_index=lifecycle.evidence_persist_min_event_index,
        evidence_restore_status=lifecycle.evidence_restore_status,
        evidence_restore_message=lifecycle.evidence_restore_message,
        evidence_persistence_health_status=lifecycle.evidence_persistence_health_status,
        evidence_last_persistence_status=lifecycle.evidence_last_persistence_status,
        evidence_last_persistence_message=lifecycle.evidence_last_persistence_message,
        evidence_last_persistence_at_utc=lifecycle.evidence_last_persistence_at_utc,
        evidence_history=lifecycle.evidence_history,
        evidence_originating_profile_id=_selected_profile_id(lifecycle),
        evidence_requested_profile_id=None,
        record_evidence=False,
        runtime_snapshot=lifecycle.runtime_snapshot,
        operator_runtime=lifecycle.operator_runtime,
        runtime_snapshot_producer=lifecycle.runtime_snapshot_producer,
        operator_runtime_mode=lifecycle.operator_runtime_mode,
        operator_action_timeline=operator_action_timeline,
        cockpit_operator_notes=lifecycle.cockpit_operator_notes,
        cockpit_evidence_events=cockpit_evidence_events,
        trigger_transition_replay_source=lifecycle.trigger_transition_replay_source,
    )


def refresh_runtime_snapshot(lifecycle: SessionLifecycle) -> SessionLifecycle:
    operator_runtime = _resolve_operator_runtime_for_lifecycle(lifecycle)
    current_shell = deepcopy(lifecycle.shell)
    attach_launch_metadata(current_shell, lifecycle.report, operator_runtime=operator_runtime)
    runtime_refresh_status = operator_action_status_for_lifecycle_action(
        action_kind="RUNTIME_REFRESH",
        action_status="REFRESHED",
        action_text="Runtime snapshot refresh completed; no manual query was submitted.",
        runtime_readiness_status=_cockpit_runtime_readiness_status(current_shell),
        runtime_readiness_preserved=_cockpit_runtime_readiness_preserved(current_shell),
        next_operator_state="Review the refreshed cockpit gate states before any manual query.",
    )
    _attach_cockpit_operator_action_status(current_shell, runtime_refresh_status)
    operator_action_timeline = append_operator_action_timeline_entry(
        lifecycle.operator_action_timeline,
        status=runtime_refresh_status,
        recorded_at=_resolved_recorded_at(operator_runtime),
    )
    cockpit_evidence_events = append_cockpit_evidence_events(
        lifecycle.cockpit_evidence_events,
        cockpit_lifecycle_evidence_events(
            event_type="cockpit_refreshed",
            surface=_fixture_cockpit_surface(current_shell),
            timestamp=cockpit_evidence_timestamp(
                current_shell,
                fallback=_resolved_recorded_at(operator_runtime),
            ),
            sequence=operator_action_timeline[-1].sequence,
            action_status="REFRESHED",
            summary="Runtime snapshot refresh completed; no manual query was submitted.",
            active_profile_id=_selected_profile_id(lifecycle),
        ),
    )
    lifecycle_history = _continue_history(
        lifecycle.lifecycle_history,
        runtime_shell=current_shell,
    )
    next_lifecycle = _finalize_lifecycle(
        shell=current_shell,
        baseline_shell=deepcopy(lifecycle.baseline_shell) if lifecycle.baseline_shell is not None else None,
        report=lifecycle.report,
        ready=lifecycle.ready,
        config=lifecycle.config,
        assembly=lifecycle.assembly,
        artifact_snapshot=lifecycle.artifact_snapshot,
        lifecycle_state=_shell_session_state(current_shell),
        lifecycle_history=lifecycle_history,
        last_action=lifecycle.last_action,
        status_summary=lifecycle.status_summary,
        next_action=_extract_next_action(current_shell),
        reload_changed_sources=lifecycle.reload_changed_sources,
        profile_switch_target_id=lifecycle.profile_switch_target_id,
        profile_switch_result=lifecycle.profile_switch_result,
        evidence_app_session_id=lifecycle.evidence_app_session_id,
        evidence_persistence_path=lifecycle.evidence_persistence_path,
        evidence_persist_min_event_index=lifecycle.evidence_persist_min_event_index,
        evidence_restore_status=lifecycle.evidence_restore_status,
        evidence_restore_message=lifecycle.evidence_restore_message,
        evidence_persistence_health_status=lifecycle.evidence_persistence_health_status,
        evidence_last_persistence_status=lifecycle.evidence_last_persistence_status,
        evidence_last_persistence_message=lifecycle.evidence_last_persistence_message,
        evidence_last_persistence_at_utc=lifecycle.evidence_last_persistence_at_utc,
        evidence_history=lifecycle.evidence_history,
        evidence_originating_profile_id=_selected_profile_id(lifecycle),
        evidence_requested_profile_id=None,
        record_evidence=False,
        runtime_snapshot=operator_runtime.snapshot,
        operator_runtime=operator_runtime,
        runtime_snapshot_producer=lifecycle.runtime_snapshot_producer,
        operator_runtime_mode=operator_runtime.mode,
        operator_action_timeline=operator_action_timeline,
        cockpit_operator_notes=lifecycle.cockpit_operator_notes,
        cockpit_evidence_events=cockpit_evidence_events,
        trigger_transition_replay_source=lifecycle.trigger_transition_replay_source,
    )
    return next_lifecycle


def add_cockpit_operator_note(
    lifecycle: SessionLifecycle,
    text: object,
    *,
    contract: str | None = None,
) -> SessionLifecycle:
    """Append a bounded, sanitized operator note to the cockpit notes surface.

    Empty/whitespace-only text is rejected: the lifecycle is returned unchanged
    apart from a status_summary noting the rejection. Adding a note does not
    call the pipeline, alter runtime readiness, or create QUERY_READY.
    """
    current_shell = deepcopy(lifecycle.shell)
    profile_id = _selected_profile_id(lifecycle)
    recorded_at = _resolved_recorded_at(lifecycle.operator_runtime)
    updated_notes, added = append_cockpit_operator_note(
        lifecycle.cockpit_operator_notes,
        text=text,
        recorded_at=recorded_at,
        contract=contract,
        profile_id=profile_id,
    )
    if added is None:
        status_summary = (
            "Operator note rejected: text was empty or whitespace-only after sanitization."
        )
        next_action = "Re-enter a non-empty operator note before submitting."
        cockpit_evidence_events = lifecycle.cockpit_evidence_events
    else:
        status_summary = (
            f"Operator note recorded (#{added.sequence}); cockpit query gating, runtime readiness, "
            "and preserved-engine authority are unchanged."
        )
        next_action = "Review the operator notes panel; the preserved engine remains the only decision authority."
        cockpit_evidence_events = append_cockpit_evidence_events(
            lifecycle.cockpit_evidence_events,
            (
                cockpit_operator_note_evidence_event(
                    contract=added.contract,
                    text=added.text,
                    timestamp=recorded_at
                    or cockpit_evidence_timestamp(current_shell),
                    sequence=added.sequence,
                    active_profile_id=profile_id,
                ),
            ),
        )
    return _finalize_lifecycle(
        shell=current_shell,
        baseline_shell=deepcopy(lifecycle.baseline_shell) if lifecycle.baseline_shell is not None else None,
        report=lifecycle.report,
        ready=lifecycle.ready,
        config=lifecycle.config,
        assembly=lifecycle.assembly,
        artifact_snapshot=lifecycle.artifact_snapshot,
        lifecycle_state=lifecycle.lifecycle_state,
        lifecycle_history=lifecycle.lifecycle_history,
        last_action=LifecycleAction.ADD_COCKPIT_OPERATOR_NOTE,
        status_summary=status_summary,
        next_action=next_action,
        reload_changed_sources=lifecycle.reload_changed_sources,
        profile_switch_target_id=lifecycle.profile_switch_target_id,
        profile_switch_result=lifecycle.profile_switch_result,
        evidence_app_session_id=lifecycle.evidence_app_session_id,
        evidence_persistence_path=lifecycle.evidence_persistence_path,
        evidence_persist_min_event_index=lifecycle.evidence_persist_min_event_index,
        evidence_restore_status=lifecycle.evidence_restore_status,
        evidence_restore_message=lifecycle.evidence_restore_message,
        evidence_persistence_health_status=lifecycle.evidence_persistence_health_status,
        evidence_last_persistence_status=lifecycle.evidence_last_persistence_status,
        evidence_last_persistence_message=lifecycle.evidence_last_persistence_message,
        evidence_last_persistence_at_utc=lifecycle.evidence_last_persistence_at_utc,
        evidence_history=lifecycle.evidence_history,
        evidence_originating_profile_id=profile_id,
        evidence_requested_profile_id=None,
        record_evidence=False,
        runtime_snapshot=lifecycle.runtime_snapshot,
        operator_runtime=lifecycle.operator_runtime,
        runtime_snapshot_producer=lifecycle.runtime_snapshot_producer,
        operator_runtime_mode=lifecycle.operator_runtime_mode,
        operator_action_timeline=lifecycle.operator_action_timeline,
        cockpit_operator_notes=updated_notes,
        cockpit_evidence_events=cockpit_evidence_events,
        trigger_transition_replay_source=lifecycle.trigger_transition_replay_source,
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

    operator_runtime = _resolve_operator_runtime_for_lifecycle(lifecycle)
    current_shell = deepcopy(lifecycle.baseline_shell)
    attach_launch_metadata(current_shell, lifecycle.report, operator_runtime=operator_runtime)
    reset_status = operator_action_status_for_lifecycle_action(
        action_kind="SESSION_RESET",
        action_status="RESET",
        action_text="Session reset completed; bounded query and manual-query display state were cleared.",
        runtime_readiness_status=_cockpit_runtime_readiness_status(current_shell),
        runtime_readiness_preserved=_cockpit_runtime_readiness_preserved(current_shell),
        next_operator_state="Review the reset cockpit state before submitting another manual query.",
    )
    _attach_cockpit_operator_action_status(current_shell, reset_status)
    operator_action_timeline = append_operator_action_timeline_entry(
        lifecycle.operator_action_timeline,
        status=reset_status,
        recorded_at=_resolved_recorded_at(operator_runtime),
    )
    reset_summary = (
        "Session reset completed; bounded query and manual-query display states were cleared."
    )
    cockpit_evidence_events = append_cockpit_evidence_events(
        lifecycle.cockpit_evidence_events,
        cockpit_lifecycle_evidence_events(
            event_type="cockpit_reset",
            surface=_fixture_cockpit_surface(current_shell),
            timestamp=cockpit_evidence_timestamp(
                current_shell,
                fallback=_resolved_recorded_at(operator_runtime),
            ),
            sequence=operator_action_timeline[-1].sequence,
            action_status="RESET",
            summary=reset_summary,
            active_profile_id=_selected_profile_id(lifecycle),
        ),
    )
    lifecycle_history = _continue_history(
        lifecycle.lifecycle_history,
        action_states=(
            SessionState.SESSION_RESET_REQUESTED,
            SessionState.SESSION_RESET_COMPLETED,
        ),
        runtime_shell=current_shell,
    )
    next_action = _extract_next_action(current_shell)
    next_lifecycle = _finalize_lifecycle(
        shell=current_shell,
        baseline_shell=deepcopy(current_shell),
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
        profile_switch_target_id=lifecycle.profile_switch_target_id,
        profile_switch_result=lifecycle.profile_switch_result,
        evidence_app_session_id=lifecycle.evidence_app_session_id,
        evidence_persistence_path=lifecycle.evidence_persistence_path,
        evidence_persist_min_event_index=lifecycle.evidence_persist_min_event_index,
        evidence_restore_status=lifecycle.evidence_restore_status,
        evidence_restore_message=lifecycle.evidence_restore_message,
        evidence_persistence_health_status=lifecycle.evidence_persistence_health_status,
        evidence_last_persistence_status=lifecycle.evidence_last_persistence_status,
        evidence_last_persistence_message=lifecycle.evidence_last_persistence_message,
        evidence_last_persistence_at_utc=lifecycle.evidence_last_persistence_at_utc,
        evidence_history=lifecycle.evidence_history,
        evidence_originating_profile_id=_selected_profile_id(lifecycle),
        evidence_requested_profile_id=None,
        runtime_snapshot=operator_runtime.snapshot,
        operator_runtime=operator_runtime,
        runtime_snapshot_producer=lifecycle.runtime_snapshot_producer,
        operator_runtime_mode=operator_runtime.mode,
        operator_action_timeline=operator_action_timeline,
        cockpit_operator_notes=lifecycle.cockpit_operator_notes,
        cockpit_evidence_events=cockpit_evidence_events,
        trigger_transition_replay_source=lifecycle.trigger_transition_replay_source,
    )
    return next_lifecycle


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
        runtime_snapshot=lifecycle.runtime_snapshot,
        runtime_snapshot_producer=lifecycle.runtime_snapshot_producer,
        operator_runtime_mode=lifecycle.operator_runtime_mode,
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
            profile_switch_target_id=lifecycle.profile_switch_target_id,
            profile_switch_result=lifecycle.profile_switch_result,
            evidence_app_session_id=lifecycle.evidence_app_session_id,
            evidence_persistence_path=lifecycle.evidence_persistence_path,
            evidence_persist_min_event_index=lifecycle.evidence_persist_min_event_index,
            evidence_restore_status=lifecycle.evidence_restore_status,
            evidence_restore_message=lifecycle.evidence_restore_message,
            evidence_persistence_health_status=lifecycle.evidence_persistence_health_status,
            evidence_last_persistence_status=lifecycle.evidence_last_persistence_status,
            evidence_last_persistence_message=lifecycle.evidence_last_persistence_message,
            evidence_last_persistence_at_utc=lifecycle.evidence_last_persistence_at_utc,
            evidence_history=lifecycle.evidence_history,
            evidence_originating_profile_id=_selected_profile_id(lifecycle),
            evidence_requested_profile_id=None,
            runtime_snapshot=startup.operator_runtime.snapshot,
            operator_runtime=startup.operator_runtime,
            runtime_snapshot_producer=lifecycle.runtime_snapshot_producer,
            operator_runtime_mode=startup.operator_runtime.mode,
            operator_action_timeline=lifecycle.operator_action_timeline,
            cockpit_operator_notes=lifecycle.cockpit_operator_notes,
            cockpit_evidence_events=lifecycle.cockpit_evidence_events,
            trigger_transition_replay_source=lifecycle.trigger_transition_replay_source,
        )

    current_shell = deepcopy(startup.shell)
    profile_refresh_status = operator_action_status_for_lifecycle_action(
        action_kind="PROFILE_REFRESH",
        action_status="REFRESHED",
        action_text="Current profile refresh completed; no manual query was submitted.",
        runtime_readiness_status=_cockpit_runtime_readiness_status(current_shell),
        runtime_readiness_preserved=_cockpit_runtime_readiness_preserved(current_shell),
        next_operator_state="Review the refreshed cockpit gate states before any manual query.",
    )
    _attach_cockpit_operator_action_status(current_shell, profile_refresh_status)
    operator_action_timeline = append_operator_action_timeline_entry(
        lifecycle.operator_action_timeline,
        status=profile_refresh_status,
        recorded_at=_resolved_recorded_at(startup.operator_runtime),
    )
    cockpit_evidence_events = append_cockpit_evidence_events(
        lifecycle.cockpit_evidence_events,
        cockpit_lifecycle_evidence_events(
            event_type="cockpit_refreshed",
            surface=_fixture_cockpit_surface(current_shell),
            timestamp=cockpit_evidence_timestamp(
                current_shell,
                fallback=_resolved_recorded_at(startup.operator_runtime),
            ),
            sequence=operator_action_timeline[-1].sequence,
            action_status="REFRESHED",
            summary="Current profile refresh completed; no manual query was submitted.",
            active_profile_id=_selected_profile_id(lifecycle),
        ),
    )
    lifecycle_history = _continue_history(
        lifecycle.lifecycle_history,
        action_states=(
            SessionState.REFRESH_REQUESTED,
            SessionState.REFRESH_COMPLETED,
        ),
        runtime_shell=current_shell,
    )
    next_lifecycle = _finalize_lifecycle(
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
        profile_switch_target_id=lifecycle.profile_switch_target_id,
        profile_switch_result=lifecycle.profile_switch_result,
        evidence_app_session_id=lifecycle.evidence_app_session_id,
        evidence_persistence_path=lifecycle.evidence_persistence_path,
        evidence_persist_min_event_index=lifecycle.evidence_persist_min_event_index,
        evidence_restore_status=lifecycle.evidence_restore_status,
        evidence_restore_message=lifecycle.evidence_restore_message,
        evidence_persistence_health_status=lifecycle.evidence_persistence_health_status,
        evidence_last_persistence_status=lifecycle.evidence_last_persistence_status,
        evidence_last_persistence_message=lifecycle.evidence_last_persistence_message,
        evidence_last_persistence_at_utc=lifecycle.evidence_last_persistence_at_utc,
        evidence_history=lifecycle.evidence_history,
        evidence_originating_profile_id=_selected_profile_id(lifecycle),
        evidence_requested_profile_id=None,
        runtime_snapshot=startup.operator_runtime.snapshot,
        operator_runtime=startup.operator_runtime,
        runtime_snapshot_producer=lifecycle.runtime_snapshot_producer,
        operator_runtime_mode=startup.operator_runtime.mode,
        operator_action_timeline=operator_action_timeline,
        cockpit_operator_notes=lifecycle.cockpit_operator_notes,
        cockpit_evidence_events=cockpit_evidence_events,
        trigger_transition_replay_source=lifecycle.trigger_transition_replay_source,
    )
    observe_phase1_trigger_state_results(next_lifecycle, startup.trigger_state_results)
    return next_lifecycle


def clear_retained_evidence(lifecycle: SessionLifecycle) -> SessionLifecycle:
    current_session_history = tuple(
        record
        for record in lifecycle.evidence_history
        if record.app_session_id == lifecycle.evidence_app_session_id
    )
    clear_status = clear_session_evidence_history(
        path=lifecycle.evidence_persistence_path,
    )
    clear_succeeded = clear_status.last_status in {"CLEAR_OK", "CLEAR_MISSING"}
    history = lifecycle.evidence_history
    persist_min_event_index = lifecycle.evidence_persist_min_event_index
    restore_status = lifecycle.evidence_restore_status
    restore_message = lifecycle.evidence_restore_message

    if clear_succeeded:
        history = current_session_history
        persist_min_event_index = _next_event_index(lifecycle.evidence_history)
        restore_status = "RESTORE_CLEARED"
        restore_message = (
            "Retained prior-run evidence was cleared intentionally. "
            "Current-session evidence remains visible until restart or subsequent actions."
        )

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
        status_summary=lifecycle.status_summary,
        next_action=lifecycle.next_action,
        reload_changed_sources=lifecycle.reload_changed_sources,
        profile_switch_target_id=lifecycle.profile_switch_target_id,
        profile_switch_result=lifecycle.profile_switch_result,
        evidence_app_session_id=lifecycle.evidence_app_session_id,
        evidence_persistence_path=clear_status.persistence_path,
        evidence_persist_min_event_index=persist_min_event_index,
        evidence_restore_status=restore_status,
        evidence_restore_message=restore_message,
        evidence_persistence_health_status=clear_status.health_status,
        evidence_last_persistence_status=clear_status.last_status,
        evidence_last_persistence_message=clear_status.last_message,
        evidence_last_persistence_at_utc=clear_status.last_persisted_at_utc,
        evidence_history=history,
        evidence_originating_profile_id=_selected_profile_id(lifecycle),
        evidence_requested_profile_id=None,
        record_evidence=False,
        runtime_snapshot=lifecycle.runtime_snapshot,
        operator_runtime=lifecycle.operator_runtime,
        runtime_snapshot_producer=lifecycle.runtime_snapshot_producer,
        operator_runtime_mode=lifecycle.operator_runtime_mode,
        operator_action_timeline=lifecycle.operator_action_timeline,
        cockpit_operator_notes=lifecycle.cockpit_operator_notes,
        cockpit_evidence_events=lifecycle.cockpit_evidence_events,
        trigger_transition_replay_source=lifecycle.trigger_transition_replay_source,
    )


def switch_profile(lifecycle: SessionLifecycle, profile_id: str) -> SessionLifecycle:
    active_profile_id = _selected_profile_id(lifecycle)
    evaluation = evaluate_profile_switch(
        profile_id,
        current_profile_id=active_profile_id,
    )
    base_action_states = (
        SessionState.PROFILE_SWITCH_REQUESTED,
        SessionState.PROFILE_SWITCH_VALIDATING,
    )

    if evaluation.status != "supported":
        lifecycle_history = _continue_history(
            lifecycle.lifecycle_history,
            action_states=(*base_action_states, SessionState.PROFILE_SWITCH_BLOCKED),
        )
        return _finalize_lifecycle(
            shell=deepcopy(lifecycle.shell),
            baseline_shell=deepcopy(lifecycle.baseline_shell) if lifecycle.baseline_shell is not None else None,
            report=lifecycle.report,
            ready=lifecycle.ready,
            config=lifecycle.config,
            assembly=lifecycle.assembly,
            artifact_snapshot=lifecycle.artifact_snapshot,
            lifecycle_state=SessionState.PROFILE_SWITCH_BLOCKED,
            lifecycle_history=lifecycle_history,
            last_action=LifecycleAction.SWITCH_PROFILE,
            status_summary=evaluation.summary,
            next_action=evaluation.next_action,
            reload_changed_sources=lifecycle.reload_changed_sources,
            profile_switch_target_id=profile_id,
            profile_switch_result="SWITCH_BLOCKED",
            evidence_app_session_id=lifecycle.evidence_app_session_id,
            evidence_persistence_path=lifecycle.evidence_persistence_path,
            evidence_persist_min_event_index=lifecycle.evidence_persist_min_event_index,
            evidence_restore_status=lifecycle.evidence_restore_status,
            evidence_restore_message=lifecycle.evidence_restore_message,
            evidence_persistence_health_status=lifecycle.evidence_persistence_health_status,
            evidence_last_persistence_status=lifecycle.evidence_last_persistence_status,
            evidence_last_persistence_message=lifecycle.evidence_last_persistence_message,
            evidence_last_persistence_at_utc=lifecycle.evidence_last_persistence_at_utc,
            evidence_history=lifecycle.evidence_history,
            evidence_originating_profile_id=active_profile_id,
            evidence_requested_profile_id=profile_id,
            runtime_snapshot=lifecycle.runtime_snapshot,
            operator_runtime=lifecycle.operator_runtime,
            runtime_snapshot_producer=lifecycle.runtime_snapshot_producer,
            operator_runtime_mode=lifecycle.operator_runtime_mode,
            operator_action_timeline=lifecycle.operator_action_timeline,
            cockpit_operator_notes=lifecycle.cockpit_operator_notes,
            cockpit_evidence_events=lifecycle.cockpit_evidence_events,
            trigger_transition_replay_source=lifecycle.trigger_transition_replay_source,
        )

    request = _switch_request_from_lifecycle(
        lifecycle,
        requested_profile_id=profile_id,
    )
    startup = build_startup_artifacts(
        request,
        query_action_requested=False,
        runtime_snapshot=lifecycle.runtime_snapshot,
        runtime_snapshot_producer=lifecycle.runtime_snapshot_producer,
        operator_runtime_mode=lifecycle.operator_runtime_mode,
    )
    if not startup.ready:
        failure_categories = [check.category for check in startup.report.checks if not check.passed]
        lifecycle_state = (
            SessionState.PROFILE_SWITCH_FAILED
            if DIAG_RUNTIME_ASSEMBLY_FAILURE in failure_categories
            else SessionState.PROFILE_SWITCH_BLOCKED
        )
        result = "SWITCH_FAILED" if lifecycle_state == SessionState.PROFILE_SWITCH_FAILED else "SWITCH_BLOCKED"
        summary = _profile_switch_failure_summary(
            target_profile_id=profile_id,
            active_profile_id=active_profile_id,
            startup=startup,
        )
        next_action = _extract_next_action(startup.shell)
        lifecycle_history = _continue_history(
            lifecycle.lifecycle_history,
            action_states=(*base_action_states, lifecycle_state),
        )
        return _finalize_lifecycle(
            shell=deepcopy(lifecycle.shell),
            baseline_shell=deepcopy(lifecycle.baseline_shell) if lifecycle.baseline_shell is not None else None,
            report=lifecycle.report,
            ready=lifecycle.ready,
            config=lifecycle.config,
            assembly=lifecycle.assembly,
            artifact_snapshot=lifecycle.artifact_snapshot,
            lifecycle_state=lifecycle_state,
            lifecycle_history=lifecycle_history,
            last_action=LifecycleAction.SWITCH_PROFILE,
            status_summary=summary,
            next_action=next_action,
            reload_changed_sources=lifecycle.reload_changed_sources,
            profile_switch_target_id=profile_id,
            profile_switch_result=result,
            evidence_app_session_id=lifecycle.evidence_app_session_id,
            evidence_persistence_path=lifecycle.evidence_persistence_path,
            evidence_persist_min_event_index=lifecycle.evidence_persist_min_event_index,
            evidence_restore_status=lifecycle.evidence_restore_status,
            evidence_restore_message=lifecycle.evidence_restore_message,
            evidence_persistence_health_status=lifecycle.evidence_persistence_health_status,
            evidence_last_persistence_status=lifecycle.evidence_last_persistence_status,
            evidence_last_persistence_message=lifecycle.evidence_last_persistence_message,
            evidence_last_persistence_at_utc=lifecycle.evidence_last_persistence_at_utc,
            evidence_history=lifecycle.evidence_history,
            evidence_originating_profile_id=active_profile_id,
            evidence_requested_profile_id=profile_id,
            runtime_snapshot=lifecycle.runtime_snapshot,
            operator_runtime=lifecycle.operator_runtime,
            runtime_snapshot_producer=lifecycle.runtime_snapshot_producer,
            operator_runtime_mode=lifecycle.operator_runtime_mode,
            operator_action_timeline=lifecycle.operator_action_timeline,
            cockpit_operator_notes=lifecycle.cockpit_operator_notes,
            cockpit_evidence_events=lifecycle.cockpit_evidence_events,
            trigger_transition_replay_source=lifecycle.trigger_transition_replay_source,
        )

    current_shell = deepcopy(startup.shell)
    lifecycle_history = _continue_history(
        lifecycle.lifecycle_history,
        action_states=(*base_action_states, SessionState.PROFILE_SWITCH_COMPLETED),
        runtime_shell=current_shell,
    )
    current_active_profile = _selected_profile_id_from_shell(current_shell)
    next_lifecycle = _finalize_lifecycle(
        shell=current_shell,
        baseline_shell=deepcopy(startup.shell),
        report=startup.report,
        ready=True,
        config=startup.config,
        assembly=_assemble_runtime(startup),
        artifact_snapshot=_artifact_snapshot_for_report(startup.report),
        lifecycle_state=SessionState.PROFILE_SWITCH_COMPLETED,
        lifecycle_history=lifecycle_history,
        last_action=LifecycleAction.SWITCH_PROFILE,
        status_summary=_profile_switch_completed_summary(
            previous_profile_id=active_profile_id,
            current_profile_id=current_active_profile,
        ),
        next_action=_extract_next_action(current_shell),
        reload_changed_sources=None,
        profile_switch_target_id=current_active_profile,
        profile_switch_result="SWITCH_COMPLETED",
        evidence_app_session_id=lifecycle.evidence_app_session_id,
        evidence_persistence_path=lifecycle.evidence_persistence_path,
        evidence_persist_min_event_index=lifecycle.evidence_persist_min_event_index,
        evidence_restore_status=lifecycle.evidence_restore_status,
        evidence_restore_message=lifecycle.evidence_restore_message,
        evidence_persistence_health_status=lifecycle.evidence_persistence_health_status,
        evidence_last_persistence_status=lifecycle.evidence_last_persistence_status,
        evidence_last_persistence_message=lifecycle.evidence_last_persistence_message,
        evidence_last_persistence_at_utc=lifecycle.evidence_last_persistence_at_utc,
        evidence_history=lifecycle.evidence_history,
        evidence_originating_profile_id=active_profile_id,
        evidence_requested_profile_id=profile_id,
        runtime_snapshot=startup.operator_runtime.snapshot,
        operator_runtime=startup.operator_runtime,
        runtime_snapshot_producer=lifecycle.runtime_snapshot_producer,
        operator_runtime_mode=startup.operator_runtime.mode,
        operator_action_timeline=(),
        cockpit_operator_notes=(),
        cockpit_evidence_events=(),
        trigger_transition_replay_source=lifecycle.trigger_transition_replay_source,
    )
    observe_phase1_trigger_state_results(next_lifecycle, startup.trigger_state_results)
    return next_lifecycle


def _assemble_runtime(startup: StartupArtifacts) -> RuntimeAssembly | None:
    if not startup.ready or startup.config is None:
        return None
    return assemble_runtime_for_profile(
        profile=startup.config.profile,
        fixtures_root=startup.config.fixtures_root,
        lockout=startup.config.lockout,
        model_adapter=startup.config.model_adapter,
    )


_PRESERVED_PROFILE_BY_CONTRACT = {
    "ES": "preserved_es_phase1",
    "NQ": "preserved_nq_phase1",
    "CL": "preserved_cl_phase1",
    "6E": "preserved_6e_phase1",
    "MGC": "preserved_mgc_phase1",
}


def _manual_query_assembly_for_contract(
    lifecycle: SessionLifecycle,
    contract: str,
) -> RuntimeAssembly | CockpitManualQueryResult:
    if lifecycle.assembly is not None and lifecycle.assembly.profile.contract == contract:
        return lifecycle.assembly

    profile_id = _PRESERVED_PROFILE_BY_CONTRACT.get(contract)
    if profile_id is None:
        return _manual_query_blocked_result(
            contract=contract,
            reason=f"Manual query blocked: {contract} is not a supported cockpit query contract.",
            provenance="contract_universe",
        )

    fixtures_root = lifecycle.config.fixtures_root if lifecycle.config is not None else None
    try:
        request = resolve_launch_request_for_profile_id(
            profile_id,
            fixtures_root=fixtures_root,
            lockout=False,
            use_env_defaults=False,
        )
        startup = build_startup_artifacts(
            request,
            query_action_requested=False,
            runtime_snapshot=lifecycle.runtime_snapshot,
            runtime_snapshot_producer=lifecycle.runtime_snapshot_producer,
            operator_runtime_mode=lifecycle.operator_runtime_mode,
        )
        assembly = _assemble_runtime(startup)
    except Exception as exc:
        return _manual_query_blocked_result(
            contract=contract,
            reason=f"Manual query blocked: runtime assembly failed for {contract}: {exc}",
            provenance="runtime_profile_preflight",
        )
    if assembly is None:
        return _manual_query_blocked_result(
            contract=contract,
            reason=f"Manual query blocked: runtime assembly is unavailable for {contract}.",
            provenance="runtime_profile_preflight",
        )
    return assembly


def _manual_query_blocked_result(
    *,
    contract: str,
    reason: str,
    provenance: str,
) -> CockpitManualQueryResult:
    return CockpitManualQueryResult(
        contract=contract,
        request_status="BLOCKED",
        submitted=False,
        submitted_at=None,
        gate_provenance_basis=provenance,
        pipeline_result_status="not_submitted",
        terminal_summary=None,
        stage_termination_reason=None,
        blocked_reason=reason,
        query_action_state="DISABLED",
        query_action_text="Manual query blocked.",
        attempted_action=f"manual_query:{contract}",
        operator_feedback_text=reason,
        bounded_result_summary="No bounded pipeline result is available because the query was not submitted.",
        next_operator_state="Wait for gate/provenance authorization before submitting a manual query.",
    )


def _fixture_cockpit_rows(shell: Mapping[str, object]) -> tuple[Mapping[str, object], ...]:
    cockpit = _fixture_cockpit_surface(shell)
    rows = cockpit.get("rows")
    if not isinstance(rows, list):
        return ()
    return tuple(row for row in rows if isinstance(row, Mapping))


def _fixture_cockpit_surface(shell: Mapping[str, object]) -> Mapping[str, object]:
    surfaces = shell.get("surfaces")
    if not isinstance(surfaces, Mapping):
        return {}
    cockpit = surfaces.get(primary_cockpit_surface_key(shell))
    if not isinstance(cockpit, Mapping):
        return {}
    return cockpit


def _attach_cockpit_manual_query_result(
    shell: dict[str, object],
    result: dict[str, object],
) -> None:
    surfaces = shell.get("surfaces")
    if isinstance(surfaces, dict):
        cockpit = surfaces.get(primary_cockpit_surface_key(shell))
        if isinstance(cockpit, dict):
            cockpit["last_query_result"] = dict(result)
            rows = cockpit.get("rows")
            if isinstance(rows, list):
                for row in rows:
                    if not isinstance(row, dict) or row.get("contract") != result.get("contract"):
                        continue
                    row["last_query_status"] = result.get("request_status")
                    row["last_query_result_status"] = result.get("pipeline_result_status")
                    row["last_query_terminal_summary"] = result.get("terminal_summary")
                    row["last_query_blocked_reason"] = result.get("blocked_reason")
    workflow = shell.get("workflow")
    if isinstance(workflow, dict):
        workflow["cockpit_manual_query_status"] = result.get("request_status")
        workflow["cockpit_manual_query_contract"] = result.get("contract")
        workflow["cockpit_manual_query_result"] = dict(result)


def _attach_cockpit_operator_action_status(
    shell: dict[str, object],
    status: dict[str, object],
) -> None:
    surfaces = shell.get("surfaces")
    if isinstance(surfaces, dict):
        cockpit = surfaces.get(primary_cockpit_surface_key(shell))
        if isinstance(cockpit, dict):
            cockpit["operator_action_status"] = dict(status)
    workflow = shell.get("workflow")
    if isinstance(workflow, dict):
        workflow["cockpit_operator_action_status"] = dict(status)


def _attach_cockpit_operator_notes(
    shell: dict[str, object],
    notes: tuple[CockpitOperatorNote, ...],
) -> None:
    payload = build_cockpit_operator_notes_payload(notes)
    surfaces = shell.get("surfaces")
    if isinstance(surfaces, dict):
        cockpit = surfaces.get(primary_cockpit_surface_key(shell))
        if isinstance(cockpit, dict):
            cockpit["operator_notes"] = dict(payload)
            cockpit["operator_notes"]["entries"] = [
                dict(entry) for entry in payload["entries"]
            ]
    workflow = shell.get("workflow")
    if isinstance(workflow, dict):
        workflow["cockpit_operator_notes_entry_count"] = len(notes)


def _attach_cockpit_current_state_summary(shell: dict[str, object]) -> None:
    surfaces = shell.get("surfaces")
    if not isinstance(surfaces, dict):
        return
    cockpit = surfaces.get(primary_cockpit_surface_key(shell))
    if not isinstance(cockpit, dict):
        return
    cockpit["current_state_summary"] = build_cockpit_current_state_summary(cockpit)
    cockpit["contract_readiness_detail"] = build_cockpit_contract_readiness_detail(
        cockpit
    )


def _attach_cockpit_event_replay(
    shell: dict[str, object],
    events: tuple[EvidenceEvent, ...],
) -> None:
    surfaces = shell.get("surfaces")
    if not isinstance(surfaces, dict):
        return
    cockpit = surfaces.get(primary_cockpit_surface_key(shell))
    if not isinstance(cockpit, dict):
        return
    payload = build_cockpit_event_replay_surface(
        events,
        active_profile_id=_selected_profile_id_from_shell(shell),
    )
    cockpit["cockpit_event_replay"] = payload
    workflow = shell.get("workflow")
    if isinstance(workflow, dict):
        workflow["cockpit_event_replay_event_count"] = payload["event_count"]


def _attach_cockpit_operator_action_timeline(
    shell: dict[str, object],
    timeline: tuple[CockpitOperatorActionTimelineEntry, ...],
) -> None:
    payload = {
        "schema": "cockpit_operator_action_timeline_v1",
        "max_entries": COCKPIT_OPERATOR_ACTION_TIMELINE_MAX_ENTRIES,
        "entry_count": len(timeline),
        "entries": [entry.to_dict() for entry in timeline],
    }
    surfaces = shell.get("surfaces")
    if isinstance(surfaces, dict):
        cockpit = surfaces.get(primary_cockpit_surface_key(shell))
        if isinstance(cockpit, dict):
            cockpit["operator_action_timeline"] = dict(payload)
            cockpit["operator_action_timeline"]["entries"] = [
                dict(entry) for entry in payload["entries"]
            ]
    workflow = shell.get("workflow")
    if isinstance(workflow, dict):
        workflow["cockpit_operator_action_timeline_entry_count"] = len(timeline)


def _resolved_recorded_at(
    operator_runtime: OperatorRuntimeSnapshotResult | None,
    *,
    fallback: str | None = None,
) -> str | None:
    if operator_runtime is not None:
        cache_generated = operator_runtime.cache_generated_at
        if cache_generated:
            return str(cache_generated)
        snapshot = operator_runtime.snapshot
        if snapshot is not None:
            generated = getattr(snapshot, "generated_at", None)
            if generated:
                return str(generated)
    return fallback


def _cockpit_runtime_readiness_status(shell: Mapping[str, object]) -> str:
    summary = _five_contract_readiness_summary(shell)
    status = summary.get("live_runtime_readiness_status")
    return str(status).strip() if status is not None and str(status).strip() else "LIVE_RUNTIME_NOT_REQUESTED"


def _cockpit_runtime_readiness_preserved(shell: Mapping[str, object]) -> bool:
    summary = _five_contract_readiness_summary(shell)
    return (
        summary.get("readiness_source") == "runtime_cache_derived"
        and summary.get("live_runtime_readiness_status") == "LIVE_RUNTIME_CONNECTED"
        and summary.get("runtime_cache_bound_to_operator_launch") is True
    )


def _five_contract_readiness_summary(shell: Mapping[str, object]) -> Mapping[str, object]:
    surfaces = shell.get("surfaces")
    if not isinstance(surfaces, Mapping):
        return {}
    summary = surfaces.get("five_contract_readiness_summary")
    return summary if isinstance(summary, Mapping) else {}


def _cockpit_manual_query_summary(result: CockpitManualQueryResult) -> str:
    if result.submitted and result.pipeline_result_status == "completed":
        return (
            f"Manual cockpit query submitted for {result.contract}. "
            "The preserved pipeline returned a bounded result."
        )
    if result.request_status == "FAILED":
        return f"Manual cockpit query failed closed for {result.contract}."
    return result.blocked_reason or f"Manual cockpit query blocked for {result.contract}."


def _cockpit_manual_query_next_action(result: CockpitManualQueryResult) -> str:
    if result.submitted and result.pipeline_result_status == "completed":
        return "Review the bounded last-query status in the primary cockpit."
    return result.blocked_reason or "Wait for gate/provenance authorization before submitting a manual query."


def _resolve_operator_runtime_for_lifecycle(lifecycle: SessionLifecycle) -> OperatorRuntimeSnapshotResult:
    return resolve_operator_runtime_snapshot(
        mode=lifecycle.operator_runtime_mode,
        producer=lifecycle.runtime_snapshot_producer,
        runtime_snapshot=lifecycle.runtime_snapshot,
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


def _selected_profile_id(lifecycle: SessionLifecycle) -> str | None:
    if lifecycle.report.request is not None:
        return lifecycle.report.request.profile.profile_id
    return _selected_profile_id_from_shell(lifecycle.shell)


def _selected_profile_id_from_shell(shell: Mapping[str, object]) -> str | None:
    startup = shell.get("startup")
    if isinstance(startup, Mapping):
        selected = startup.get("selected_profile_id")
        if selected is not None:
            return str(selected)

    runtime = shell.get("runtime")
    if isinstance(runtime, Mapping):
        selected = runtime.get("profile_id")
        if selected is not None:
            return str(selected)
    return None


def _observation_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _switch_request_from_lifecycle(
    lifecycle: SessionLifecycle,
    *,
    requested_profile_id: str,
) -> LaunchRequest:
    current_request = lifecycle.report.request
    fixtures_root = None if current_request is None else current_request.fixtures_root
    lockout = None if current_request is None else current_request.lockout
    return resolve_launch_request_for_profile_id(
        requested_profile_id,
        fixtures_root=fixtures_root,
        lockout=lockout,
        use_env_defaults=True,
    )


def _profile_switch_completed_summary(
    *,
    previous_profile_id: str | None,
    current_profile_id: str | None,
) -> str:
    previous = previous_profile_id or "<unresolved>"
    current = current_profile_id or "<unresolved>"
    return (
        f"Profile switch completed. Active profile changed from {previous} to {current}. "
        "The session was reinitialized from the new profile's declared artifacts, so bounded query, "
        "Decision Review, Audit / Replay, and runtime identity now belong only to the newly loaded profile."
    )


def _profile_switch_failure_summary(
    *,
    target_profile_id: str,
    active_profile_id: str | None,
    startup: StartupArtifacts,
) -> str:
    failed_checks = [check for check in startup.report.checks if not check.passed]
    first_failure = failed_checks[0].summary if failed_checks else "Unknown profile-switch validation failure."
    active = active_profile_id or "<unresolved>"
    return (
        f"Profile switch to {target_profile_id} did not complete. {first_failure} "
        f"Active profile remains {active}, so no cross-profile session state was carried into the blocked switch."
    )


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
        profile_switch_target_id=lifecycle.profile_switch_target_id,
        profile_switch_result=lifecycle.profile_switch_result,
        evidence_app_session_id=lifecycle.evidence_app_session_id,
        evidence_persistence_path=lifecycle.evidence_persistence_path,
        evidence_persist_min_event_index=lifecycle.evidence_persist_min_event_index,
        evidence_restore_status=lifecycle.evidence_restore_status,
        evidence_restore_message=lifecycle.evidence_restore_message,
        evidence_persistence_health_status=lifecycle.evidence_persistence_health_status,
        evidence_last_persistence_status=lifecycle.evidence_last_persistence_status,
        evidence_last_persistence_message=lifecycle.evidence_last_persistence_message,
        evidence_last_persistence_at_utc=lifecycle.evidence_last_persistence_at_utc,
        evidence_history=lifecycle.evidence_history,
        evidence_originating_profile_id=_selected_profile_id(lifecycle),
        evidence_requested_profile_id=None,
        record_evidence=False,
        runtime_snapshot=lifecycle.runtime_snapshot,
        operator_runtime=lifecycle.operator_runtime,
        runtime_snapshot_producer=lifecycle.runtime_snapshot_producer,
        operator_runtime_mode=lifecycle.operator_runtime_mode,
        operator_action_timeline=lifecycle.operator_action_timeline,
        cockpit_operator_notes=lifecycle.cockpit_operator_notes,
        cockpit_evidence_events=lifecycle.cockpit_evidence_events,
        trigger_transition_replay_source=lifecycle.trigger_transition_replay_source,
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
    profile_switch_target_id: str | None,
    profile_switch_result: str,
    evidence_app_session_id: str,
    evidence_persistence_path: str,
    evidence_persist_min_event_index: int,
    evidence_restore_status: str,
    evidence_restore_message: str,
    evidence_persistence_health_status: str,
    evidence_last_persistence_status: str,
    evidence_last_persistence_message: str,
    evidence_last_persistence_at_utc: str | None,
    evidence_history: tuple[SessionEvidenceRecord, ...],
    evidence_originating_profile_id: str | None,
    evidence_requested_profile_id: str | None,
    record_evidence: bool = True,
    runtime_snapshot: RuntimeReadinessSnapshot | None = None,
    operator_runtime: OperatorRuntimeSnapshotResult | None = None,
    runtime_snapshot_producer: RuntimeSnapshotProducer | None = None,
    operator_runtime_mode: OperatorRuntimeMode | str | None = None,
    operator_action_timeline: tuple[CockpitOperatorActionTimelineEntry, ...] = (),
    cockpit_operator_notes: tuple[CockpitOperatorNote, ...] = (),
    cockpit_evidence_events: tuple[EvidenceEvent, ...] = (),
    trigger_transition_replay_source: TriggerTransitionReplaySource | None = None,
) -> SessionLifecycle:
    resolved_operator_runtime = operator_runtime or resolve_operator_runtime_snapshot(
        mode=operator_runtime_mode,
        runtime_snapshot=runtime_snapshot,
    )
    resolved_transition_replay_source = trigger_transition_replay_source or TriggerTransitionReplaySource(
        source="session_lifecycle",
    )
    _attach_cockpit_operator_action_timeline(shell, operator_action_timeline)
    _attach_cockpit_operator_notes(shell, cockpit_operator_notes)
    _attach_cockpit_current_state_summary(shell)
    _attach_cockpit_event_replay(shell, cockpit_evidence_events)
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
        profile_switch_target_id=profile_switch_target_id,
        profile_switch_result=profile_switch_result,
    )
    updated_evidence_history = evidence_history
    if record_evidence:
        updated_evidence_history = append_session_evidence(
            evidence_history,
            shell,
            app_session_id=evidence_app_session_id,
            originating_profile_id=evidence_originating_profile_id,
            requested_profile_id=evidence_requested_profile_id,
        )
        persistence_status = persist_session_evidence_history(
            updated_evidence_history,
            path=evidence_persistence_path,
            minimum_event_index=evidence_persist_min_event_index,
        )
        evidence_persistence_path = persistence_status.persistence_path
        evidence_persistence_health_status = persistence_status.health_status
        evidence_last_persistence_status = persistence_status.last_status
        evidence_last_persistence_message = persistence_status.last_message
        evidence_last_persistence_at_utc = persistence_status.last_persisted_at_utc
    shell["evidence"] = build_session_evidence_panel(
        updated_evidence_history,
        shell,
        current_app_session_id=evidence_app_session_id,
        persistence_path=evidence_persistence_path,
        restore_status=evidence_restore_status,
        restore_message=evidence_restore_message,
        persistence_health_status=evidence_persistence_health_status,
        last_persistence_status=evidence_last_persistence_status,
        last_persistence_message=evidence_last_persistence_message,
        last_persistence_at_utc=evidence_last_persistence_at_utc,
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
        profile_switch_target_id=profile_switch_target_id,
        profile_switch_result=profile_switch_result,
        evidence_app_session_id=evidence_app_session_id,
        evidence_persistence_path=evidence_persistence_path,
        evidence_persist_min_event_index=evidence_persist_min_event_index,
        evidence_restore_status=evidence_restore_status,
        evidence_restore_message=evidence_restore_message,
        evidence_persistence_health_status=evidence_persistence_health_status,
        evidence_last_persistence_status=evidence_last_persistence_status,
        evidence_last_persistence_message=evidence_last_persistence_message,
        evidence_last_persistence_at_utc=evidence_last_persistence_at_utc,
        evidence_history=updated_evidence_history,
        runtime_snapshot=resolved_operator_runtime.snapshot,
        operator_runtime=resolved_operator_runtime,
        runtime_snapshot_producer=runtime_snapshot_producer,
        operator_runtime_mode=operator_runtime_mode or resolved_operator_runtime.mode,
        operator_action_timeline=operator_action_timeline,
        cockpit_operator_notes=cockpit_operator_notes,
        cockpit_evidence_events=cockpit_evidence_events,
        trigger_transition_replay_source=resolved_transition_replay_source,
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
    profile_switch_target_id: str | None,
    profile_switch_result: str,
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
        "preflight_reran": last_action in {
            LifecycleAction.RELOAD_CURRENT_PROFILE,
            LifecycleAction.SWITCH_PROFILE,
        },
        "reload_result": reload_result,
        "reload_changed_sources": reload_changed_sources,
        "reset_available": reset_available,
        "reload_available": reload_available,
        "profile_switch_available": True,
        "profile_switch_target_id": profile_switch_target_id,
        "profile_switch_result": profile_switch_result,
        "selected_profile_id": startup_panel.get("selected_profile_id", runtime_panel.get("profile_id", "<unresolved>")),
        "runtime_mode": startup_panel.get("runtime_mode", runtime_panel.get("runtime_mode", "<unresolved>")),
        "running_as": startup_panel.get("running_as", "<unresolved>"),
        "operator_ready": startup_panel.get("operator_ready", False),
        "query_action_status": workflow_panel.get("query_action_status", "<unavailable>"),
        "operator_live_runtime_mode": runtime_panel.get("operator_live_runtime_mode", "SAFE_NON_LIVE"),
        "operator_live_runtime_status": runtime_panel.get("operator_live_runtime_status", "SAFE_NON_LIVE"),
        "operator_live_runtime_source": runtime_panel.get("operator_live_runtime_source", "fixture_preserved_shell"),
        "operator_live_runtime_cache_derived": runtime_panel.get("operator_live_runtime_cache_derived", False),
        "operator_live_runtime_refresh_floor_seconds": runtime_panel.get(
            "operator_live_runtime_refresh_floor_seconds",
            15.0,
        ),
        "decision_review_ready": workflow_panel.get("decision_review_ready", False),
        "audit_replay_ready": workflow_panel.get("audit_replay_ready", False),
        "status_summary": status_summary,
        "next_action": next_action,
        "blocked": startup_panel.get("operator_ready") is not True,
    }


def _next_event_index(history: tuple[SessionEvidenceRecord, ...]) -> int:
    if not history:
        return 1
    return history[-1].event_index + 1
