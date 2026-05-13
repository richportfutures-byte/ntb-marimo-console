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
    SessionTarget,
    WatchmanContextLike,
)
from .adapters.trigger_evaluator import TriggerEvaluator
from .decision_review_audit import build_decision_review_audit_event
from .decision_review_replay import build_decision_review_replay_vm
from .market_data import FuturesQuoteService
from .adapters.trigger_specs import trigger_specs_from_brief
from .operator_workspace import OperatorWorkspaceRequest, build_r14_cockpit_view_model
from .pipeline_query_gate import (
    PipelineQueryGateRequest,
    PipelineQueryGateResult,
    evaluate_pipeline_query_gate,
)
from .state.session_state import OperatorSessionMachine, SessionState
from .trigger_state import TriggerState, TriggerStateResult
from .trigger_state_result_producer import (
    TriggerStateResultProducerRequest,
    build_trigger_state_results,
)
from .ui.app_shell import AppShellPayload, build_app_shell
from .viewmodels.mappers import (
    live_observable_vm_from_snapshot,
    pipeline_trace_vm_from_summary,
    premarket_brief_vm_from_brief,
    readiness_card_vm_from_context,
    run_history_row_vm_from_row,
    session_header_vm,
    timeline_events_from_session,
    trigger_status_vm_from_eval,
)
from .viewmodels.models import PipelineTraceVM
from .watchman_gate import WatchmanValidatorResult, build_watchman_gate_payload, validate_watchman_brief


@dataclass
class Phase1AppDependencies:
    premarket_store: PreMarketArtifactStore
    run_history_store: RunHistoryStore
    audit_replay_store: AuditReplayStore
    trigger_evaluator: TriggerEvaluator
    market_data_service: FuturesQuoteService | None = None


@dataclass(frozen=True)
class Phase1RuntimeStatus:
    state: SessionState
    state_history: tuple[SessionState, ...]


@dataclass(frozen=True)
class Phase1WorkflowStatus:
    state: SessionState
    state_history: tuple[SessionState, ...]
    watchman_gate_status: str
    watchman_gate_open: bool
    live_query_status: str
    query_action_status: str
    query_enabled: bool
    readiness_gate: bool
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
    watchman_gate: dict[str, object]
    premarket_brief: Mapping[str, object]
    audit_replay: AuditReplayRecord | None
    run_history_source: str
    trigger_state_results: tuple[TriggerStateResult, ...]
    pipeline_query_gate: PipelineQueryGateResult


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

    watchman_validator = validate_watchman_brief(premarket.brief)
    watchman_gate = build_watchman_gate_payload(watchman_validator)

    try:
        watchman_map = backend.sweep_watchman(inputs.premarket)
    except Exception as exc:
        _fail_closed(session, "Failed to load watchman readiness context.", exc)

    watchman_context = watchman_map.get(session_target.contract)
    if watchman_context is None:
        _fail_closed(session, f"Missing watchman context for {session_target.contract}.")

    trigger_specs = trigger_specs_from_brief(premarket.brief)
    trigger_state_results = build_trigger_state_results(
        TriggerStateResultProducerRequest(
            contract=session_target.contract,
            premarket_brief=premarket.brief,
            live_snapshot=inputs.live_snapshot,
            last_updated=inputs.pipeline_query.evaluation_timestamp_iso,
        )
    )
    try:
        eval_bundle = dependencies.trigger_evaluator.evaluate(trigger_specs, inputs.live_snapshot)
    except Exception as exc:
        _fail_closed(session, "Failed to evaluate trigger predicates.", exc)

    trigger_vms = tuple(trigger_status_vm_from_eval(item) for item in eval_bundle.evaluations)
    pipeline_query_gate = _build_pipeline_query_gate(
        session_target=session_target,
        inputs=inputs,
        watchman_validator=watchman_validator,
        watchman_context=watchman_context,
        trigger_state_results=trigger_state_results,
    )
    blocked_reasons = _build_blocked_reasons(
        watchman_gate=watchman_gate,
        watchman_context=watchman_context,
        pipeline_query_gate=pipeline_query_gate,
    )
    readiness_gate = watchman_validator.pipeline_gate_open and not watchman_context.hard_lockout_flags
    query_enabled = pipeline_query_gate.enabled

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
                narrative = backend.narrate_pipeline_result(pipeline_result)
            except Exception as exc:
                session.mark_query_action_failed()
                error_message = f"Query action failed: {exc}"
            else:
                session.mark_query_action_completed()
                pipeline_vm = pipeline_trace_vm_from_summary(summary, narrative)
                session.mark_decision_review_ready()
                try:
                    audit_replay = dependencies.audit_replay_store.load_replay(session_target)
                except Exception as exc:
                    error_message = f"Audit/replay load failed after bounded query completion: {exc}"
                    session.mark_error()
                else:
                    if audit_replay.get("replay_available") is True:
                        session.mark_audit_replay_ready()
                    else:
                        error_message = (
                            "Audit/replay stayed unavailable after bounded query completion. "
                            "The session failed closed because no persisted Stage E record was available."
                        )
                        session.mark_error()

    try:
        history_rows = dependencies.run_history_store.list_rows(session_target)
    except Exception as exc:
        _fail_closed(session, "Failed to load run history.", exc)
    run_history_source = _run_history_source(dependencies.run_history_store, session_target=session_target)

    payload = AppShellPayload(
        session_header=session_header_vm(session_target.contract, session_target.session_date),
        premarket_brief=premarket_brief_vm_from_brief(
            premarket.brief,
            status_override=watchman_validator.status,
        ),
        live_observable=live_observable_vm_from_snapshot(
            inputs.live_snapshot,
            market_data_service=dependencies.market_data_service,
            market_data_symbol=session_target.contract,
        ),
        readiness_cards=(readiness_card_vm_from_context(watchman_context),),
        trigger_rows=trigger_vms,
        pipeline_trace=pipeline_vm,
        run_history_rows=tuple(run_history_row_vm_from_row(item) for item in history_rows),
        timeline_events=timeline_events_from_session(
            trigger_transitions=trigger_state_results,
            pipeline_traces=() if pipeline_vm is None else (pipeline_vm,),
            session_timestamp=inputs.pipeline_query.evaluation_timestamp_iso,
        ),
    )
    runtime_status = Phase1RuntimeStatus(
        state=session.state,
        state_history=session.state_history,
    )
    workflow_status = _build_workflow_status(
        session=session,
        query_enabled=query_enabled,
        readiness_gate=readiness_gate,
        watchman_validator=watchman_validator,
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
        watchman_gate=watchman_gate,
        premarket_brief=premarket.brief,
        audit_replay=audit_replay,
        run_history_source=run_history_source,
        trigger_state_results=trigger_state_results,
        pipeline_query_gate=pipeline_query_gate,
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
    return build_phase1_shell_from_artifacts(
        artifacts,
        inputs=inputs,
        query_action_requested=query_action_requested,
    )


def build_phase1_shell_from_artifacts(
    artifacts: Phase1BuildArtifacts,
    *,
    inputs: OperatorRuntimeInputs,
    query_action_requested: bool = True,
) -> dict[str, object]:
    """Build the app shell from already-produced Phase 1 artifacts."""
    shell = build_app_shell(artifacts.payload)

    surfaces = shell.get("surfaces")
    if isinstance(surfaces, Mapping):
        query_panel = surfaces.get("query_action")
        if isinstance(query_panel, dict):
            query_panel.update(
                {
                    "watchman_gate_status": artifacts.workflow_status.watchman_gate_status,
                    "live_query_status": artifacts.workflow_status.live_query_status,
                    "query_action_status": artifacts.workflow_status.query_action_status,
                    "readiness_gate": artifacts.workflow_status.readiness_gate,
                    "query_enabled": artifacts.workflow_status.query_enabled,
                    "action_available": artifacts.workflow_status.query_action_available,
                    "action_requested": query_action_requested,
                    "action_label": "Run bounded query for loaded snapshot",
                    "blocked_reasons": list(artifacts.workflow_status.blocked_reasons),
                    "pipeline_query_gate": artifacts.pipeline_query_gate.to_dict(),
                    "pipeline_query_gate_status": artifacts.pipeline_query_gate.status.value,
                    "pipeline_query_gate_missing_conditions": list(artifacts.pipeline_query_gate.missing_conditions),
                    "pipeline_query_gate_disabled_reasons": list(artifacts.pipeline_query_gate.disabled_reasons),
                    "trigger_state": artifacts.pipeline_query_gate.trigger_state,
                    "trigger_state_setup_id": artifacts.pipeline_query_gate.setup_id,
                    "trigger_state_trigger_id": artifacts.pipeline_query_gate.trigger_id,
                    "trigger_state_from_real_producer": artifacts.pipeline_query_gate.trigger_state_from_real_producer,
                    "pipeline_query_gate_enabled_reasons": list(artifacts.pipeline_query_gate.enabled_reasons),
                    "status_summary": artifacts.workflow_status.status_summary,
                    "next_action": artifacts.workflow_status.next_action,
                    "bounded_action_description": artifacts.workflow_status.bounded_action_description,
                    "failure_message": artifacts.workflow_status.error_message,
                }
            )

        narrative_audit_replay: dict[str, object] | None = None
        decision_panel = surfaces.get("decision_review")
        if isinstance(decision_panel, dict):
            decision_panel.update(
                {
                    "ready": artifacts.workflow_status.decision_review_ready,
                    "status": "READY" if artifacts.workflow_status.decision_review_ready else "NOT_READY",
                    "message": _decision_review_message(artifacts.workflow_status),
                }
            )
            decision_panel["narrative_audit_event"] = build_decision_review_audit_event(
                decision_review=decision_panel,
                profile_id=inputs.selection.profile_id,
                source=artifacts.run_history_source,
            ).to_dict()
            narrative_audit_replay = build_decision_review_replay_vm(
                decision_panel["narrative_audit_event"],
                audit_replay_record=artifacts.audit_replay,
            ).to_dict()
            decision_panel["narrative_audit_replay"] = narrative_audit_replay

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
                        "mode": artifacts.audit_replay["source"],
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
            if narrative_audit_replay is not None:
                audit_panel["narrative_audit_replay"] = narrative_audit_replay

        run_history_panel = surfaces.get("run_history")
        if isinstance(run_history_panel, dict):
            run_history_panel["source"] = artifacts.run_history_source

    shell["watchman_gate"] = dict(artifacts.watchman_gate)
    if inputs.pipeline_query.operator_anchor_inputs is not None:
        shell["operator_anchor_inputs"] = dict(inputs.pipeline_query.operator_anchor_inputs)
        anchors = inputs.pipeline_query.operator_anchor_inputs.get("anchors")
        shell["anchor_inputs"] = {
            "status": "ready",
            "rows": list(anchors.values()) if isinstance(anchors, Mapping) else [],
            "message": "Operator-supplied context only; preserved engine remains decision authority.",
            "integration_status": inputs.pipeline_query.operator_anchor_inputs.get(
                "integration_status",
                "operator_context_available_not_gate_enforced",
            ),
        }
    shell["workflow"] = {
        "current_state": artifacts.workflow_status.state.value,
        "state_history": [state.value for state in artifacts.workflow_status.state_history],
        "watchman_gate_status": artifacts.workflow_status.watchman_gate_status,
        "watchman_gate_open": artifacts.workflow_status.watchman_gate_open,
        "live_query_status": artifacts.workflow_status.live_query_status,
        "query_action_status": artifacts.workflow_status.query_action_status,
        "query_enabled": artifacts.workflow_status.query_enabled,
        "readiness_gate": artifacts.workflow_status.readiness_gate,
        "query_action_available": artifacts.workflow_status.query_action_available,
        "decision_review_ready": artifacts.workflow_status.decision_review_ready,
        "audit_replay_ready": artifacts.workflow_status.audit_replay_ready,
        "blocked_reasons": list(artifacts.workflow_status.blocked_reasons),
        "pipeline_query_gate": artifacts.pipeline_query_gate.to_dict(),
        "operator_anchor_inputs_status": (
            "available"
            if inputs.pipeline_query.operator_anchor_inputs is not None
            else "not_supplied"
        ),
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
        "watchman_gate_status": artifacts.workflow_status.watchman_gate_status,
        "live_query_status": artifacts.workflow_status.live_query_status,
        "query_action_status": artifacts.workflow_status.query_action_status,
        "decision_review_ready": artifacts.workflow_status.decision_review_ready,
        "audit_replay_ready": artifacts.workflow_status.audit_replay_ready,
        "next_action": artifacts.workflow_status.next_action,
    }
    shell["r14_cockpit"] = build_r14_cockpit_view_model(
        OperatorWorkspaceRequest(
            contract=inputs.selection.session.contract,
            profile_id=inputs.selection.profile_id,
            watchman_validator=artifacts.watchman_gate,
            trigger_state=_select_pipeline_trigger_state_result(
                contract=inputs.selection.session.contract,
                trigger_state_results=artifacts.trigger_state_results,
            ),
            pipeline_query_gate=artifacts.pipeline_query_gate,
            premarket_brief=artifacts.premarket_brief,
            live_observable=inputs.live_snapshot,
            provider_status=artifacts.pipeline_query_gate.provider_status,
            stream_status=artifacts.pipeline_query_gate.stream_status,
            quote_freshness="fresh" if "quote_fresh" in artifacts.pipeline_query_gate.enabled_reasons else "blocked",
            bar_freshness=(
                "fresh"
                if "bars_fresh_and_available" in artifacts.pipeline_query_gate.enabled_reasons
                else "blocked"
            ),
            session_status="valid" if artifacts.pipeline_query_gate.session_valid else "invalid",
            event_lockout_status="active" if artifacts.pipeline_query_gate.event_lockout_active else "inactive",
            evaluated_at=artifacts.pipeline_query_gate.evaluated_at,
            last_pipeline_result=_last_pipeline_result_from_trace(artifacts.payload.pipeline_trace),
            run_history_status="available" if artifacts.run_history_source else "unavailable",
            audit_replay_record=artifacts.audit_replay,
            operator_notes_status="unavailable",
        )
    ).to_dict()
    return shell


def _run_history_source(store: RunHistoryStore, *, session_target: SessionTarget) -> str:
    source_label = getattr(store, "source_label", None)
    if callable(source_label):
        source = source_label(session_target)
        if isinstance(source, str) and source:
            return source
    return "fixture_backed"


def _build_blocked_reasons(
    *,
    watchman_gate: Mapping[str, object],
    watchman_context: WatchmanContextLike,
    pipeline_query_gate: PipelineQueryGateResult,
) -> tuple[str, ...]:
    reasons: list[str] = []

    if watchman_gate.get("pipeline_gate_open") is not True:
        reasons.append(
            str(
                watchman_gate.get(
                    "status_summary",
                    "Watchman validator has not authorized this brief yet.",
                )
            )
        )

    if watchman_context.hard_lockout_flags:
        flags = ", ".join(watchman_context.hard_lockout_flags)
        reasons.append(f"Readiness is blocked by hard lockout flags: {flags}.")

    if watchman_context.missing_inputs:
        missing = ", ".join(watchman_context.missing_inputs)
        reasons.append(f"Readiness context is incomplete: {missing}.")

    reasons.extend(pipeline_query_gate.disabled_reasons)

    return tuple(reasons)


def _build_pipeline_query_gate(
    *,
    session_target: SessionTarget,
    inputs: OperatorRuntimeInputs,
    watchman_validator: WatchmanValidatorResult,
    watchman_context: WatchmanContextLike,
    trigger_state_results: tuple[TriggerStateResult, ...],
) -> PipelineQueryGateResult:
    matching_real_results = tuple(
        result for result in trigger_state_results if result.contract == session_target.contract
    )
    trigger_state = _select_pipeline_trigger_state_result(
        contract=session_target.contract,
        trigger_state_results=trigger_state_results,
    )
    fixture_mode_accepted = inputs.selection.mode in {"fixture_demo", "preserved_engine"}
    provider_status = "fixture" if fixture_mode_accepted else None
    stream_status = "fixture" if fixture_mode_accepted else None
    return evaluate_pipeline_query_gate(
        PipelineQueryGateRequest(
            contract=session_target.contract,
            profile_id=inputs.selection.profile_id,
            profile_exists=True,
            profile_preflight_passed=True,
            watchman_validator_status=watchman_validator.status,
            live_snapshot=inputs.live_snapshot,
            trigger_state=trigger_state,
            bars_available=True,
            bars_fresh=True,
            support_matrix_final_supported=None,
            provider_status=provider_status,
            stream_status=stream_status,
            session_valid=True,
            event_lockout_active=bool(watchman_context.hard_lockout_flags),
            fixture_mode_accepted=fixture_mode_accepted,
            evaluated_at=inputs.pipeline_query.evaluation_timestamp_iso,
            trigger_state_from_real_producer=bool(matching_real_results),
        )
    )


def _select_pipeline_trigger_state_result(
    *,
    contract: str,
    trigger_state_results: tuple[TriggerStateResult, ...],
) -> TriggerStateResult:
    matching = tuple(result for result in trigger_state_results if result.contract == contract)
    if not matching:
        return TriggerStateResult(
            contract=contract,
            setup_id=None,
            trigger_id=None,
            state=TriggerState.UNAVAILABLE,
            distance_to_trigger_ticks=None,
            required_fields=(),
            missing_fields=(),
            invalid_reasons=(),
            blocking_reasons=("trigger_state_result_unavailable",),
            last_updated=None,
        )

    blocking_states = {
        TriggerState.UNAVAILABLE,
        TriggerState.BLOCKED,
        TriggerState.INVALIDATED,
        TriggerState.LOCKOUT,
        TriggerState.STALE,
        TriggerState.ERROR,
    }
    for result in matching:
        if result.state in blocking_states or result.missing_fields:
            return result
    for result in matching:
        if result.state == TriggerState.QUERY_READY:
            return result
    return matching[0]


def _build_workflow_status(
    *,
    session: OperatorSessionMachine,
    query_enabled: bool,
    readiness_gate: bool,
    watchman_validator: WatchmanValidatorResult,
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
        watchman_gate_status=watchman_validator.status,
        watchman_gate_open=watchman_validator.pipeline_gate_open,
        live_query_status=live_query_status,
        query_action_status=query_action_status,
        query_enabled=query_enabled,
        readiness_gate=readiness_gate,
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


def _last_pipeline_result_from_trace(trace: PipelineTraceVM | None) -> dict[str, object] | None:
    if trace is None:
        return None
    return {
        "status": "completed",
        "contract": trace.contract,
        "termination_stage": trace.termination_stage,
        "final_decision": trace.final_decision,
        "sufficiency_gate_status": trace.stage_a_status,
        "contract_analysis_outcome": trace.stage_b_outcome,
        "proposed_setup_outcome": trace.stage_c_outcome,
        "risk_authorization_decision": trace.stage_d_decision,
    }
