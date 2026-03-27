from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from .adapters.contracts import (
    AuditReplayRecord,
    AuditReplayStore,
    OperatorRuntimeInputs,
    PipelineBackend,
    PreMarketArtifactStore,
    RunHistoryStore,
    WatchmanContextLike,
)
from .adapters.trigger_evaluator import TriggerEvaluator
from .adapters.trigger_specs import trigger_specs_from_brief
from .state.session_state import OperatorSessionMachine, SessionState
from .ui.app_shell import AppShellPayload, build_app_shell
from .viewmodels.mappers import (
    live_observable_vm_from_snapshot,
    pipeline_trace_vm_from_summary,
    premarket_brief_vm_from_brief,
    readiness_card_vm_from_context,
    run_history_row_vm_from_row,
    session_header_vm,
    trigger_status_vm_from_eval,
)
from .viewmodels.models import PipelineTraceVM, TriggerStatusVM


@dataclass
class Phase1AppDependencies:
    premarket_store: PreMarketArtifactStore
    run_history_store: RunHistoryStore
    audit_replay_store: AuditReplayStore
    trigger_evaluator: TriggerEvaluator


@dataclass(frozen=True)
class Phase1RuntimeStatus:
    state: SessionState
    state_history: tuple[SessionState, ...]


@dataclass(frozen=True)
class Phase1WorkflowStatus:
    state: SessionState
    state_history: tuple[SessionState, ...]
    live_query_status: str
    query_action_status: str
    query_action_available: bool
    decision_review_ready: bool
    audit_replay_ready: bool
    blocked_reasons: tuple[str, ...]
    status_summary: str
    next_action: str
    bounded_action_description: str
    error_message: str | None


@dataclass(frozen=True)
class Phase1BuildArtifacts:
    payload: AppShellPayload
    runtime_status: Phase1RuntimeStatus
    workflow_status: Phase1WorkflowStatus
    audit_replay: AuditReplayRecord | None


def _fail_closed(
    session: OperatorSessionMachine,
    message: str,
    exc: Exception | None = None,
) -> None:
    session.mark_error()
    if exc is None:
        raise ValueError(message)
    raise ValueError(message) from exc


def _validate_runtime_inputs(inputs: OperatorRuntimeInputs) -> None:
    session = inputs.selection.session
    if inputs.pipeline_query.contract != session.contract:
        raise ValueError("Pipeline query contract must match selected operator session contract.")

    snapshot_contract = inputs.live_snapshot.get("contract")
    if snapshot_contract != session.contract:
        raise ValueError("Live observable snapshot contract must match selected operator session contract.")


def build_phase1_payload(
    backend: PipelineBackend,
    inputs: OperatorRuntimeInputs,
    dependencies: Phase1AppDependencies,
    *,
    query_action_requested: bool = True,
) -> Phase1BuildArtifacts:
    """Construct app payload with strict adapter/viewmodel layering."""

    _validate_runtime_inputs(inputs)
    session_target = inputs.selection.session
    session = OperatorSessionMachine()
    session.mark_startup_ready()

    try:
        premarket = dependencies.premarket_store.load(session_target)
    except Exception as exc:
        _fail_closed(session, "Failed to load pre-market artifacts.", exc)

    packet_contract = premarket.packet.get("contract")
    brief_contract = premarket.brief.get("contract")
    packet_session_date = premarket.packet.get("session_date")
    brief_session_date = premarket.brief.get("session_date")
    if packet_contract != session_target.contract or brief_contract != session_target.contract:
        _fail_closed(session, "Pre-market artifacts did not match the selected operator contract.")
    if packet_session_date != session_target.session_date or brief_session_date != session_target.session_date:
        _fail_closed(session, "Pre-market artifacts did not match the selected operator session date.")

    try:
        watchman_map = backend.sweep_watchman(inputs.premarket)
    except Exception as exc:
        _fail_closed(session, "Failed to load watchman readiness context.", exc)

    watchman_context = watchman_map.get(session_target.contract)
    if watchman_context is None:
        _fail_closed(session, f"Missing watchman context for {session_target.contract}.")

    trigger_specs = trigger_specs_from_brief(premarket.brief)
    try:
        eval_bundle = dependencies.trigger_evaluator.evaluate(trigger_specs, inputs.live_snapshot)
    except Exception as exc:
        _fail_closed(session, "Failed to evaluate trigger predicates.", exc)

    trigger_vms = tuple(trigger_status_vm_from_eval(item) for item in eval_bundle.evaluations)
    blocked_reasons = _build_blocked_reasons(
        watchman_context=watchman_context,
        trigger_rows=trigger_vms,
    )
    query_enabled = eval_bundle.query_gate_true and not watchman_context.hard_lockout_flags

    if query_enabled:
        session.mark_live_query_eligible()
    else:
        session.mark_live_query_blocked()

    pipeline_vm: PipelineTraceVM | None = None
    audit_replay: AuditReplayRecord | None = None
    error_message: str | None = None

    if query_action_requested:
        if not query_enabled:
            session.mark_query_action_failed()
            error_message = (
                "Query action was rejected because the loaded snapshot is not eligible. "
                "Resolve the blocked conditions before requesting a bounded query."
            )
        else:
            session.mark_query_action_requested()
            try:
                pipeline_result = backend.run_pipeline(inputs.pipeline_query)
                summary = backend.summarize_pipeline_result(pipeline_result)
            except Exception as exc:
                session.mark_query_action_failed()
                error_message = f"Query action failed: {exc}"
            else:
                session.mark_query_action_completed()
                pipeline_vm = pipeline_trace_vm_from_summary(summary)
                session.mark_decision_review_ready()
                try:
                    audit_replay = dependencies.audit_replay_store.load_replay(session_target)
                except Exception as exc:
                    error_message = f"Audit/replay load failed after bounded query completion: {exc}"
                    session.mark_error()
                else:
                    session.mark_audit_replay_ready()

    try:
        history_rows = dependencies.run_history_store.list_rows(session_target)
    except Exception as exc:
        _fail_closed(session, "Failed to load run history.", exc)

    payload = AppShellPayload(
        session_header=session_header_vm(session_target.contract, session_target.session_date),
        premarket_brief=premarket_brief_vm_from_brief(premarket.brief),
        live_observable=live_observable_vm_from_snapshot(inputs.live_snapshot),
        readiness_cards=(readiness_card_vm_from_context(watchman_context),),
        trigger_rows=trigger_vms,
        pipeline_trace=pipeline_vm,
        run_history_rows=tuple(run_history_row_vm_from_row(item) for item in history_rows),
    )
    runtime_status = Phase1RuntimeStatus(
        state=session.state,
        state_history=session.state_history,
    )
    workflow_status = _build_workflow_status(
        session=session,
        query_enabled=query_enabled,
        query_action_requested=query_action_requested,
        pipeline_vm=pipeline_vm,
        audit_replay=audit_replay,
        blocked_reasons=blocked_reasons,
        error_message=error_message,
    )
    return Phase1BuildArtifacts(
        payload=payload,
        runtime_status=runtime_status,
        workflow_status=workflow_status,
        audit_replay=audit_replay,
    )


def build_phase1_app(
    backend: PipelineBackend,
    inputs: OperatorRuntimeInputs,
    dependencies: Phase1AppDependencies,
    *,
    query_action_requested: bool = True,
) -> dict[str, object]:
    """Entry surface for the marimo Phase 1 app shell."""

    artifacts = build_phase1_payload(
        backend=backend,
        inputs=inputs,
        dependencies=dependencies,
        query_action_requested=query_action_requested,
    )
    shell = build_app_shell(artifacts.payload)

    surfaces = shell.get("surfaces")
    if isinstance(surfaces, Mapping):
        query_panel = surfaces.get("query_action")
        if isinstance(query_panel, dict):
            query_panel.update(
                {
                    "live_query_status": artifacts.workflow_status.live_query_status,
                    "query_action_status": artifacts.workflow_status.query_action_status,
                    "action_available": artifacts.workflow_status.query_action_available,
                    "action_requested": query_action_requested,
                    "action_label": "Run bounded query for loaded snapshot",
                    "blocked_reasons": list(artifacts.workflow_status.blocked_reasons),
                    "status_summary": artifacts.workflow_status.status_summary,
                    "next_action": artifacts.workflow_status.next_action,
                    "bounded_action_description": artifacts.workflow_status.bounded_action_description,
                    "failure_message": artifacts.workflow_status.error_message,
                }
            )

        decision_panel = surfaces.get("decision_review")
        if isinstance(decision_panel, dict):
            decision_panel.update(
                {
                    "ready": artifacts.workflow_status.decision_review_ready,
                    "status": "READY" if artifacts.workflow_status.decision_review_ready else "NOT_READY",
                    "message": _decision_review_message(artifacts.workflow_status),
                }
            )

        audit_panel = surfaces.get("audit_replay")
        if isinstance(audit_panel, dict):
            audit_panel.update(
                {
                    "ready": artifacts.workflow_status.audit_replay_ready,
                    "status": "READY" if artifacts.workflow_status.audit_replay_ready else "NOT_READY",
                    "message": _audit_replay_message(artifacts.workflow_status),
                }
            )
            if artifacts.audit_replay is not None:
                audit_panel.update(
                    {
                        "source": artifacts.audit_replay["source"],
                        "replay_available": artifacts.audit_replay["replay_available"],
                        "last_run_id": artifacts.audit_replay["last_run_id"],
                        "last_final_decision": artifacts.audit_replay["last_final_decision"],
                        "stage_e_live_backend": artifacts.audit_replay["stage_e_live_backend"],
                    }
                )
            else:
                audit_panel.update(
                    {
                        "source": "not_ready",
                        "replay_available": False,
                        "last_run_id": None,
                        "last_final_decision": None,
                        "stage_e_live_backend": False,
                    }
                )

    shell["workflow"] = {
        "current_state": artifacts.workflow_status.state.value,
        "state_history": [state.value for state in artifacts.workflow_status.state_history],
        "live_query_status": artifacts.workflow_status.live_query_status,
        "query_action_status": artifacts.workflow_status.query_action_status,
        "query_action_available": artifacts.workflow_status.query_action_available,
        "decision_review_ready": artifacts.workflow_status.decision_review_ready,
        "audit_replay_ready": artifacts.workflow_status.audit_replay_ready,
        "blocked_reasons": list(artifacts.workflow_status.blocked_reasons),
        "status_summary": artifacts.workflow_status.status_summary,
        "next_action": artifacts.workflow_status.next_action,
        "bounded_action_description": artifacts.workflow_status.bounded_action_description,
        "error_message": artifacts.workflow_status.error_message,
    }
    shell["runtime"] = {
        "runtime_mode": inputs.selection.mode,
        "profile_id": inputs.selection.profile_id,
        "contract": inputs.selection.session.contract,
        "session_date": inputs.selection.session.session_date,
        "session_state": artifacts.runtime_status.state.value,
        "state_history": [state.value for state in artifacts.runtime_status.state_history],
        "live_query_status": artifacts.workflow_status.live_query_status,
        "query_action_status": artifacts.workflow_status.query_action_status,
        "decision_review_ready": artifacts.workflow_status.decision_review_ready,
        "audit_replay_ready": artifacts.workflow_status.audit_replay_ready,
        "next_action": artifacts.workflow_status.next_action,
    }
    return shell


def _build_blocked_reasons(
    *,
    watchman_context: WatchmanContextLike,
    trigger_rows: tuple[TriggerStatusVM, ...],
) -> tuple[str, ...]:
    reasons: list[str] = []

    if watchman_context.hard_lockout_flags:
        flags = ", ".join(watchman_context.hard_lockout_flags)
        reasons.append(f"Readiness is blocked by hard lockout flags: {flags}.")

    if watchman_context.missing_inputs:
        missing = ", ".join(watchman_context.missing_inputs)
        reasons.append(f"Readiness context is incomplete: {missing}.")

    invalid_triggers = [row.trigger_id for row in trigger_rows if not row.is_valid]
    if invalid_triggers:
        reasons.append(
            "One or more query triggers are invalid for the loaded snapshot: "
            + ", ".join(invalid_triggers)
            + "."
        )

    if not any(row.is_valid and row.is_true for row in trigger_rows):
        reasons.append("No declared query trigger is currently true for the loaded snapshot.")

    return tuple(reasons)


def _build_workflow_status(
    *,
    session: OperatorSessionMachine,
    query_enabled: bool,
    query_action_requested: bool,
    pipeline_vm: PipelineTraceVM | None,
    audit_replay: AuditReplayRecord | None,
    blocked_reasons: tuple[str, ...],
    error_message: str | None,
) -> Phase1WorkflowStatus:
    if session.state == SessionState.QUERY_ACTION_FAILED:
        query_action_status = "FAILED"
    elif SessionState.QUERY_ACTION_COMPLETED in session.state_history:
        query_action_status = "COMPLETED"
    elif SessionState.QUERY_ACTION_REQUESTED in session.state_history:
        query_action_status = "REQUESTED"
    elif query_enabled and not query_action_requested:
        query_action_status = "AVAILABLE"
    elif query_enabled:
        query_action_status = "AVAILABLE"
    else:
        query_action_status = "BLOCKED"

    live_query_status = "ELIGIBLE" if query_enabled else "BLOCKED"
    decision_review_ready = pipeline_vm is not None
    audit_replay_ready = audit_replay is not None and session.state == SessionState.AUDIT_REPLAY_READY
    query_action_available = query_enabled and query_action_status == "AVAILABLE"

    if session.state == SessionState.QUERY_ACTION_FAILED:
        status_summary = "The bounded query action failed. Decision Review and Audit / Replay remain blocked."
        next_action = "Review the failure message, correct the blocking issue, and reload the session before retrying."
    elif session.state == SessionState.ERROR:
        status_summary = "The session hit an unrecoverable error after query execution. The workflow is blocked."
        next_action = "Resolve the reported runtime error, then reload the session."
    elif session.state == SessionState.AUDIT_REPLAY_READY:
        status_summary = "Bounded query execution completed. Decision Review and Audit / Replay are ready."
        next_action = "Review the Decision Review result, then inspect Audit / Replay for the bounded trace."
    elif session.state == SessionState.LIVE_QUERY_ELIGIBLE:
        status_summary = "The loaded snapshot is eligible for a bounded query action."
        next_action = "Use the in-app query action to run the bounded pipeline against the current snapshot."
    else:
        status_summary = "The loaded snapshot is not currently eligible for a bounded query action."
        next_action = blocked_reasons[0] if blocked_reasons else "Wait for eligibility before requesting a bounded query."

    return Phase1WorkflowStatus(
        state=session.state,
        state_history=session.state_history,
        live_query_status=live_query_status,
        query_action_status=query_action_status,
        query_action_available=query_action_available,
        decision_review_ready=decision_review_ready,
        audit_replay_ready=audit_replay_ready,
        blocked_reasons=blocked_reasons,
        status_summary=status_summary,
        next_action=next_action,
        bounded_action_description=(
            "Runs the bounded Phase 1 pipeline against the currently loaded snapshot. "
            "It does not place orders, imply fills, or invent live execution."
        ),
        error_message=error_message,
    )


def _decision_review_message(workflow: Phase1WorkflowStatus) -> str:
    if workflow.decision_review_ready:
        return "Decision Review is ready for the current bounded query run."
    if workflow.query_action_status == "FAILED":
        return "Decision Review is blocked because the bounded query action failed."
    if workflow.query_action_status == "AVAILABLE":
        return "Decision Review will become available after a bounded query action completes."
    return "Decision Review is not ready for the current session state."


def _audit_replay_message(workflow: Phase1WorkflowStatus) -> str:
    if workflow.audit_replay_ready:
        return "Audit / Replay is ready for the current bounded query run."
    if workflow.decision_review_ready:
        return "Audit / Replay is still blocked for this session."
    return "Audit / Replay becomes available only after a bounded query action completes."
