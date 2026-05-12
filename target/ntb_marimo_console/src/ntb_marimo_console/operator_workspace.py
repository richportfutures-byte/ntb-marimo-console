from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from ntb_marimo_console.adapters.contracts import AuditReplayRecord
from ntb_marimo_console.contract_universe import contract_policy_label, is_final_target_contract, normalize_contract_symbol
from ntb_marimo_console.decision_review_audit import build_decision_review_audit_event
from ntb_marimo_console.decision_review_replay import build_decision_review_replay_vm
from ntb_marimo_console.evidence_replay import EVIDENCE_REPLAY_SCHEMA
from ntb_marimo_console.live_observables.schema_v2 import LiveObservableSnapshotV2
from ntb_marimo_console.market_data.stream_events import redact_sensitive_text
from ntb_marimo_console.pipeline_query_gate import PipelineQueryGateResult
from ntb_marimo_console.trigger_state import TriggerStateResult
from ntb_marimo_console.trigger_transition_narrative import narrate_trigger_transition
from ntb_marimo_console.watchman_gate import WatchmanValidatorResult


OPERATOR_WORKSPACE_SCHEMA: Final[str] = "operator_workspace_view_model_v1"
R14_COCKPIT_SCHEMA: Final[str] = "r14_cockpit_view_model_v1"
QUERY_READY_READINESS_STATEMENT: Final[str] = (
    "QUERY_READY is query readiness only; it is not trade authorization and does not approve, reject, size, route, or place trades."
)
PIPELINE_GATE_STATEMENT: Final[str] = (
    "Gate enabled means only that the operator may manually query the preserved Stage A through D pipeline."
)
_NO_PIPELINE_RESULT_REASON: Final[str] = "No preserved pipeline result summary has been supplied."
_NO_SYNTHETIC_REPLAY_STATEMENT: Final[str] = "No synthetic replay is labeled as real evidence."
_SAFE_FIELD_RE = re.compile(r"[A-Za-z0-9_.:-]+")


@dataclass(frozen=True)
class OperatorWorkspaceRequest:
    contract: str
    profile_id: str | None
    watchman_validator: WatchmanValidatorResult | Mapping[str, Any] | str | None
    trigger_state: TriggerStateResult | Mapping[str, Any] | None
    pipeline_query_gate: PipelineQueryGateResult | Mapping[str, Any] | None
    premarket_brief: Mapping[str, Any] | None = None
    live_observable: LiveObservableSnapshotV2 | Mapping[str, Any] | None = None
    support_matrix_final_supported: bool | None = None
    provider_status: str | None = None
    stream_status: str | None = None
    quote_freshness: str | None = None
    bar_freshness: str | None = None
    session_status: str | None = None
    event_lockout_status: str | None = None
    evaluated_at: str | None = None
    last_pipeline_result: Mapping[str, Any] | None = None
    run_history_status: str | None = None
    audit_replay_status: str | None = None
    audit_replay_record: AuditReplayRecord | Mapping[str, Any] | None = None
    operator_notes_status: str | None = None
    trigger_transition_log_status: str | None = None
    trigger_transition_log: Mapping[str, Any] | None = None
    evidence_unavailable_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class OperatorWorkspaceViewModel:
    header: dict[str, object]
    premarket_plan: dict[str, object]
    live_thesis_monitor: dict[str, object]
    pipeline_gate: dict[str, object]
    last_pipeline_result: dict[str, object]
    evidence_and_replay: dict[str, object]
    schema: str = OPERATOR_WORKSPACE_SCHEMA

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "header": self.header,
            "premarket_plan": self.premarket_plan,
            "live_thesis_monitor": self.live_thesis_monitor,
            "pipeline_gate": self.pipeline_gate,
            "last_pipeline_result": self.last_pipeline_result,
            "evidence_and_replay": self.evidence_and_replay,
        }


@dataclass(frozen=True)
class CockpitIdentityVM:
    current_profile: str
    contract: str
    contract_support_status: str
    runtime_profile_status: str

    def to_dict(self) -> dict[str, object]:
        return {
            "current_profile": self.current_profile,
            "contract": self.contract,
            "contract_support_status": self.contract_support_status,
            "runtime_profile_status": self.runtime_profile_status,
        }


@dataclass(frozen=True)
class CockpitRuntimeStatusVM:
    provider_status: str
    stream_status: str
    quote_freshness: str
    bar_freshness: str
    session_clock_state: str
    event_lockout_state: str
    evaluated_at: str

    def to_dict(self) -> dict[str, object]:
        return {
            "provider_status": self.provider_status,
            "stream_status": self.stream_status,
            "quote_freshness": self.quote_freshness,
            "bar_freshness": self.bar_freshness,
            "session_clock_state": self.session_clock_state,
            "event_lockout_state": self.event_lockout_state,
            "evaluated_at": self.evaluated_at,
        }


@dataclass(frozen=True)
class CockpitPremarketVM:
    premarket_brief_status: str
    active_setup_count: int
    setup_summaries: tuple[dict[str, object], ...]
    required_fields: tuple[str, ...]
    missing_fields: tuple[str, ...]
    unavailable_fields: tuple[dict[str, object], ...]
    blocking_reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "premarket_brief_status": self.premarket_brief_status,
            "active_setup_count": self.active_setup_count,
            "setup_summaries": [dict(item) for item in self.setup_summaries],
            "required_fields": list(self.required_fields),
            "missing_fields": list(self.missing_fields),
            "unavailable_fields": [dict(item) for item in self.unavailable_fields],
            "blocking_reasons": list(self.blocking_reasons),
        }


@dataclass(frozen=True)
class CockpitTriggerSummaryVM:
    setup_id: str
    trigger_id: str
    trigger_state: str
    distance_to_trigger_ticks: object
    required_fields: tuple[str, ...]
    missing_fields: tuple[str, ...]
    blocking_reasons: tuple[str, ...]
    invalid_reasons: tuple[str, ...]
    query_ready_provenance: str

    def to_dict(self) -> dict[str, object]:
        return {
            "setup_id": self.setup_id,
            "trigger_id": self.trigger_id,
            "trigger_state": self.trigger_state,
            "distance_to_trigger_ticks": self.distance_to_trigger_ticks,
            "required_fields": list(self.required_fields),
            "missing_fields": list(self.missing_fields),
            "blocking_reasons": list(self.blocking_reasons),
            "invalid_reasons": list(self.invalid_reasons),
            "query_ready_provenance": self.query_ready_provenance,
        }


@dataclass(frozen=True)
class CockpitQueryReadinessVM:
    query_ready: bool
    pipeline_gate_enabled: bool
    manual_query_allowed: bool
    query_enabled_reason: str | None
    query_disabled_reason: str | None
    query_ready_provenance: str
    trigger_state_from_real_producer: bool
    pipeline_gate_state: str
    enabled_reasons: tuple[str, ...]
    disabled_reasons: tuple[str, ...]
    blocking_reasons: tuple[str, ...]
    missing_conditions: tuple[str, ...]
    required_conditions: tuple[str, ...]
    gate_statement: str

    def to_dict(self) -> dict[str, object]:
        return {
            "query_ready": self.query_ready,
            "pipeline_gate_enabled": self.pipeline_gate_enabled,
            "manual_query_allowed": self.manual_query_allowed,
            "query_enabled_reason": self.query_enabled_reason,
            "query_disabled_reason": self.query_disabled_reason,
            "query_ready_provenance": self.query_ready_provenance,
            "trigger_state_from_real_producer": self.trigger_state_from_real_producer,
            "pipeline_gate_state": self.pipeline_gate_state,
            "enabled_reasons": list(self.enabled_reasons),
            "disabled_reasons": list(self.disabled_reasons),
            "blocking_reasons": list(self.blocking_reasons),
            "missing_conditions": list(self.missing_conditions),
            "required_conditions": list(self.required_conditions),
            "gate_statement": self.gate_statement,
        }


@dataclass(frozen=True)
class CockpitPipelineResultVM:
    status: str
    termination_stage: str | None
    stage_termination_reason: str | None
    final_decision: str | None
    no_trade_summary: str | None
    approved_summary: str | None
    rejected_summary: str | None
    stage_a_status: str | None
    stage_b_outcome: str | None
    stage_c_outcome: str | None
    stage_d_decision: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "termination_stage": self.termination_stage,
            "stage_termination_reason": self.stage_termination_reason,
            "final_decision": self.final_decision,
            "no_trade_summary": self.no_trade_summary,
            "approved_summary": self.approved_summary,
            "rejected_summary": self.rejected_summary,
            "stage_a_status": self.stage_a_status,
            "stage_b_outcome": self.stage_b_outcome,
            "stage_c_outcome": self.stage_c_outcome,
            "stage_d_decision": self.stage_d_decision,
        }


@dataclass(frozen=True)
class CockpitReplayAvailabilityVM:
    run_history_status: str
    audit_replay_status: str
    audit_replay_available: bool
    trigger_transition_status: str
    trigger_transition_available: bool
    trigger_transition_count: int
    operator_note_status: str
    operator_note_available: bool
    replay_statement: str

    def to_dict(self) -> dict[str, object]:
        return {
            "run_history_status": self.run_history_status,
            "audit_replay_status": self.audit_replay_status,
            "audit_replay_available": self.audit_replay_available,
            "trigger_transition_status": self.trigger_transition_status,
            "trigger_transition_available": self.trigger_transition_available,
            "trigger_transition_count": self.trigger_transition_count,
            "operator_note_status": self.operator_note_status,
            "operator_note_available": self.operator_note_available,
            "replay_statement": self.replay_statement,
        }


@dataclass(frozen=True)
class R14CockpitViewModel:
    identity: CockpitIdentityVM
    runtime_status: CockpitRuntimeStatusVM
    premarket: CockpitPremarketVM
    triggers: tuple[CockpitTriggerSummaryVM, ...]
    query_readiness: CockpitQueryReadinessVM
    last_pipeline_result: CockpitPipelineResultVM
    replay_availability: CockpitReplayAvailabilityVM
    blocking_reasons: tuple[str, ...]
    schema: str = R14_COCKPIT_SCHEMA

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "identity": self.identity.to_dict(),
            "runtime_status": self.runtime_status.to_dict(),
            "premarket": self.premarket.to_dict(),
            "triggers": [trigger.to_dict() for trigger in self.triggers],
            "query_readiness": self.query_readiness.to_dict(),
            "last_pipeline_result": self.last_pipeline_result.to_dict(),
            "replay_availability": self.replay_availability.to_dict(),
            "blocking_reasons": list(self.blocking_reasons),
        }


def build_operator_workspace_view_model(request: OperatorWorkspaceRequest) -> OperatorWorkspaceViewModel:
    contract = normalize_contract_symbol(request.contract)
    gate = _gate_payload(request.pipeline_query_gate)
    trigger = _trigger_payload(request.trigger_state, gate)
    live = _live_payload(request.live_observable, contract)
    validator = _validator_payload(request.watchman_validator)
    header = _build_header(request, contract, gate, live)
    premarket_plan = _build_premarket_plan(request.premarket_brief, validator)
    live_thesis = _build_live_thesis_monitor(trigger)
    pipeline_gate = _build_pipeline_gate(gate)
    last_pipeline_result = _build_last_pipeline_result(request.last_pipeline_result)
    evidence = _build_evidence_and_replay(
        request,
        contract=contract,
        live_thesis_monitor=live_thesis,
        last_pipeline_result=last_pipeline_result,
    )
    return OperatorWorkspaceViewModel(
        header=header,
        premarket_plan=premarket_plan,
        live_thesis_monitor=live_thesis,
        pipeline_gate=pipeline_gate,
        last_pipeline_result=last_pipeline_result,
        evidence_and_replay=evidence,
    )


def build_r14_cockpit_view_model(request: OperatorWorkspaceRequest) -> R14CockpitViewModel:
    contract = normalize_contract_symbol(request.contract)
    gate = _gate_payload(request.pipeline_query_gate)
    trigger = _trigger_payload(request.trigger_state, gate)
    live = _live_payload(request.live_observable, contract)
    validator = _validator_payload(request.watchman_validator)
    header = _build_header(request, contract, gate, live)
    premarket_plan = _build_premarket_plan(request.premarket_brief, validator)
    evidence = _build_evidence_and_replay(
        request,
        contract=contract,
        live_thesis_monitor=_build_live_thesis_monitor(trigger),
        last_pipeline_result=_build_last_pipeline_result(request.last_pipeline_result),
    )
    query_readiness = _build_cockpit_query_readiness(
        request.trigger_state,
        gate,
    )
    premarket_required_fields = _dedupe(
        (
            *_sequence_fields(premarket_plan.get("required_live_fields")),
            *_sequence_fields(trigger.get("required_fields")),
        )
    )
    premarket_missing_fields = _dedupe(
        (
            *_sequence_fields(trigger.get("missing_fields")),
            *_unavailable_field_names(premarket_plan.get("unavailable_fields")),
            *_sequence_fields(premarket_plan.get("source_context_blockers")),
        )
    )
    return R14CockpitViewModel(
        identity=CockpitIdentityVM(
            current_profile=_safe_text(header["profile_id"]),
            contract=contract,
            contract_support_status=_safe_status(header["final_support_status"]),
            runtime_profile_status=_runtime_profile_status(gate),
        ),
        runtime_status=CockpitRuntimeStatusVM(
            provider_status=_safe_status(header["provider_status"]),
            stream_status=_safe_status(header["stream_status"]),
            quote_freshness=_safe_status(header["quote_freshness"]),
            bar_freshness=_safe_status(header["bar_freshness"]),
            session_clock_state=_safe_status(header["session_status"]),
            event_lockout_state=_safe_status(header["event_lockout_status"]),
            evaluated_at=_safe_text(header["evaluated_at"]),
        ),
        premarket=CockpitPremarketVM(
            premarket_brief_status=_premarket_brief_status(request.premarket_brief, premarket_plan),
            active_setup_count=len(premarket_plan["setup_summaries"]),
            setup_summaries=tuple(_mapping_tuple(premarket_plan["setup_summaries"])),
            required_fields=premarket_required_fields,
            missing_fields=premarket_missing_fields,
            unavailable_fields=tuple(_mapping_tuple(premarket_plan["unavailable_fields"])),
            blocking_reasons=_dedupe(
                (
                    *_sequence_text(premarket_plan.get("source_context_blockers")),
                    *_sequence_text(premarket_plan.get("validation_blockers")),
                )
            ),
        ),
        triggers=(_build_cockpit_trigger_summary(request.trigger_state, trigger),),
        query_readiness=query_readiness,
        last_pipeline_result=_build_cockpit_pipeline_result(request.last_pipeline_result),
        replay_availability=_build_cockpit_replay_availability(evidence),
        blocking_reasons=_dedupe(
            (
                *query_readiness.blocking_reasons,
                *_sequence_text(premarket_plan.get("source_context_blockers")),
                *_sequence_text(premarket_plan.get("validation_blockers")),
            )
        ),
    )


def _build_header(
    request: OperatorWorkspaceRequest,
    contract: str,
    gate: Mapping[str, Any],
    live: Mapping[str, Any],
) -> dict[str, object]:
    provider_status = request.provider_status or _string_or_none(gate.get("provider_status")) or _string_or_none(live.get("provider_status"))
    stream_status = request.stream_status or _string_or_none(gate.get("stream_status")) or "unavailable"
    return {
        "contract": contract,
        "profile_id": _safe_text(request.profile_id or _string_or_none(gate.get("profile_id")) or "unavailable"),
        "final_support_status": _support_status(contract, request.support_matrix_final_supported),
        "provider_status": _safe_status(provider_status or "unavailable"),
        "stream_status": _safe_status(stream_status),
        "quote_freshness": _safe_status(request.quote_freshness or _string_or_none(live.get("quote_freshness")) or "unknown"),
        "bar_freshness": _safe_status(request.bar_freshness or "unknown"),
        "session_status": _safe_status(request.session_status or _session_status_from_gate(gate)),
        "event_lockout_status": _safe_status(request.event_lockout_status or _event_lockout_status_from_gate(gate)),
        "evaluated_at": _safe_text(request.evaluated_at or _string_or_none(gate.get("evaluated_at")) or _string_or_none(live.get("generated_at")) or "unavailable"),
    }


def _build_cockpit_trigger_summary(
    trigger_state_source: TriggerStateResult | Mapping[str, Any] | None,
    trigger: Mapping[str, Any],
) -> CockpitTriggerSummaryVM:
    return CockpitTriggerSummaryVM(
        setup_id=_safe_text(_string_or_none(trigger.get("setup_id")) or "unavailable"),
        trigger_id=_safe_text(_string_or_none(trigger.get("trigger_id")) or "unavailable"),
        trigger_state=_safe_text(_string_or_none(trigger.get("state")) or "UNAVAILABLE").upper(),
        distance_to_trigger_ticks=trigger.get("distance_to_trigger_ticks"),
        required_fields=_sequence_fields(trigger.get("required_fields")),
        missing_fields=_sequence_fields(trigger.get("missing_fields")),
        blocking_reasons=_sequence_text(trigger.get("blocking_reasons")),
        invalid_reasons=_sequence_text(trigger.get("invalid_reasons")),
        query_ready_provenance=(
            "real_trigger_state_result"
            if isinstance(trigger_state_source, TriggerStateResult)
            else "unavailable_not_inferred_from_display"
        ),
    )


def _build_cockpit_query_readiness(
    trigger_state_source: TriggerStateResult | Mapping[str, Any] | None,
    gate: Mapping[str, Any],
) -> CockpitQueryReadinessVM:
    pipeline_gate_enabled = _safe_pipeline_gate_enabled(gate)
    trigger_is_real = isinstance(trigger_state_source, TriggerStateResult)
    trigger_is_query_ready = (
        trigger_state_source.state.value == "QUERY_READY"
        if isinstance(trigger_state_source, TriggerStateResult)
        else False
    )
    query_ready = pipeline_gate_enabled and trigger_is_real and trigger_is_query_ready
    disabled_reasons = _sequence_text(gate.get("disabled_reasons"))
    blocking_reasons = _sequence_text(gate.get("blocking_reasons"))
    missing_conditions = _sequence_text(gate.get("missing_conditions"))
    if not gate:
        disabled_reasons = ("pipeline_query_gate_result_unavailable",)
        blocking_reasons = disabled_reasons
    elif _raw_pipeline_gate_enabled(gate) and not pipeline_gate_enabled:
        disabled_reasons = _dedupe((*disabled_reasons, "pipeline_gate_provenance_not_verified"))
        blocking_reasons = _dedupe((*blocking_reasons, "pipeline_gate_provenance_not_verified"))
    if pipeline_gate_enabled and not trigger_is_real:
        disabled_reasons = _dedupe((*disabled_reasons, "cockpit_trigger_state_result_provenance_not_verified"))
        blocking_reasons = _dedupe((*blocking_reasons, "cockpit_trigger_state_result_provenance_not_verified"))
        missing_conditions = _dedupe((*missing_conditions, "real_trigger_state_result_provenance"))
    if pipeline_gate_enabled and trigger_is_real and not trigger_is_query_ready:
        disabled_reasons = _dedupe((*disabled_reasons, "cockpit_trigger_state_not_query_ready"))
        blocking_reasons = _dedupe((*blocking_reasons, "cockpit_trigger_state_not_query_ready"))
        missing_conditions = _dedupe((*missing_conditions, "trigger_state_query_ready"))
    query_enabled_reason = (
        "QUERY_READY provenance verified from a real TriggerStateResult and enabled PipelineQueryGateResult."
        if query_ready
        else None
    )
    query_disabled_reason = None
    if not query_ready:
        reason = blocking_reasons[0] if blocking_reasons else "query_ready_provenance_not_verified"
        query_disabled_reason = _safe_text(
            f"Manual query disabled: {reason}. QUERY_READY requires real TriggerStateResult provenance and the pipeline gate."
        )
    return CockpitQueryReadinessVM(
        query_ready=query_ready,
        pipeline_gate_enabled=pipeline_gate_enabled,
        manual_query_allowed=query_ready,
        query_enabled_reason=query_enabled_reason,
        query_disabled_reason=query_disabled_reason,
        query_ready_provenance=(
            "real_trigger_state_result_and_pipeline_gate"
            if query_ready
            else "unavailable_not_inferred_from_display_or_raw_enabled_mapping"
        ),
        trigger_state_from_real_producer=gate.get("trigger_state_from_real_producer") is True and trigger_is_real,
        pipeline_gate_state="ENABLED" if pipeline_gate_enabled else "DISABLED",
        enabled_reasons=_sequence_text(gate.get("enabled_reasons")),
        disabled_reasons=disabled_reasons,
        blocking_reasons=blocking_reasons,
        missing_conditions=missing_conditions,
        required_conditions=_sequence_text(gate.get("required_conditions")),
        gate_statement=PIPELINE_GATE_STATEMENT,
    )


def _build_cockpit_pipeline_result(last_pipeline_result: Mapping[str, Any] | None) -> CockpitPipelineResultVM:
    if last_pipeline_result is None:
        return CockpitPipelineResultVM(
            status="not_queried",
            termination_stage=None,
            stage_termination_reason=None,
            final_decision=None,
            no_trade_summary=None,
            approved_summary=None,
            rejected_summary=None,
            stage_a_status=None,
            stage_b_outcome=None,
            stage_c_outcome=None,
            stage_d_decision=None,
        )
    status = _safe_status(last_pipeline_result.get("status") or "available")
    final_decision = _string_or_none(last_pipeline_result.get("final_decision"))
    stage_d_decision = _string_or_none(last_pipeline_result.get("risk_authorization_decision"))
    decision = (final_decision or "").upper()
    stage_d = (stage_d_decision or "").upper()
    return CockpitPipelineResultVM(
        status=status,
        termination_stage=_string_or_none(last_pipeline_result.get("termination_stage")),
        stage_termination_reason=_string_or_none(last_pipeline_result.get("stage_termination_reason")),
        final_decision=final_decision,
        no_trade_summary=(
            "Preserved engine returned NO_TRADE."
            if decision == "NO_TRADE"
            else None
        ),
        approved_summary=(
            "Preserved engine returned APPROVED."
            if decision == "APPROVED" or stage_d == "APPROVED"
            else None
        ),
        rejected_summary=(
            "Preserved engine returned REJECTED or blocked risk authorization."
            if decision == "REJECTED" or stage_d in {"REJECTED", "BLOCKED"}
            else None
        ),
        stage_a_status=_string_or_none(last_pipeline_result.get("sufficiency_gate_status")),
        stage_b_outcome=_string_or_none(last_pipeline_result.get("contract_analysis_outcome")),
        stage_c_outcome=_string_or_none(last_pipeline_result.get("proposed_setup_outcome")),
        stage_d_decision=stage_d_decision,
    )


def _build_cockpit_replay_availability(evidence: Mapping[str, Any]) -> CockpitReplayAvailabilityVM:
    transition_log = evidence.get("trigger_transition_log")
    transition_status = _safe_status(evidence.get("trigger_transition_log_status") or "unavailable")
    transition_count = 0
    if isinstance(transition_log, Mapping):
        count = transition_log.get("count")
        transition_count = count if isinstance(count, int) else 0
    operator_note_status = _safe_status(evidence.get("operator_notes_status") or "unavailable")
    audit_replay_status = _safe_status(evidence.get("audit_replay_status") or "unavailable")
    return CockpitReplayAvailabilityVM(
        run_history_status=_safe_status(evidence.get("run_history_status") or "unavailable"),
        audit_replay_status=audit_replay_status,
        audit_replay_available=audit_replay_status == "available",
        trigger_transition_status=transition_status,
        trigger_transition_available=transition_status == "available",
        trigger_transition_count=transition_count,
        operator_note_status=operator_note_status,
        operator_note_available=operator_note_status == "available",
        replay_statement=_safe_text(evidence.get("replay_statement") or _NO_SYNTHETIC_REPLAY_STATEMENT),
    )


def _runtime_profile_status(gate: Mapping[str, Any]) -> str:
    if gate.get("profile_id") is None:
        return "unavailable"
    missing = _sequence_text(gate.get("missing_conditions"))
    if "runtime_profile_preflight_passed" in missing:
        return "blocked"
    return "available"


def _premarket_brief_status(
    brief: Mapping[str, Any] | None,
    premarket_plan: Mapping[str, Any],
) -> str:
    if isinstance(brief, Mapping):
        status = _string_or_none(brief.get("status"))
        if status:
            return status
    return _safe_text(premarket_plan.get("validator_status") or "unavailable")


def _unavailable_field_names(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return ()
    fields: list[str] = []
    for item in value:
        if isinstance(item, Mapping):
            fields.append(_safe_field(item.get("field") or "unavailable"))
    return tuple(fields)


def _mapping_tuple(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return ()
    return tuple(dict(item) for item in value if isinstance(item, Mapping))


def _build_premarket_plan(
    brief: Mapping[str, Any] | None,
    validator: Mapping[str, Any],
) -> dict[str, object]:
    setup_summaries, trigger_summaries, required_live_fields, warnings, invalidators = _brief_sections(brief)
    unavailable_fields = _unavailable_fields(brief)
    source_context_blockers = _source_context_blockers(brief)
    validation_blockers = _sequence_text(validator.get("failing_validator_summaries"))
    if not validation_blockers:
        validation_blockers = _sequence_text(validator.get("failing_validators"))
    return {
        "validator_status": _safe_text(_string_or_none(validator.get("status")) or "unavailable"),
        "setup_summaries": setup_summaries,
        "trigger_summaries": trigger_summaries,
        "required_live_fields": list(required_live_fields),
        "unavailable_fields": unavailable_fields,
        "warnings": list(warnings),
        "invalidators": invalidators,
        "source_context_blockers": list(source_context_blockers),
        "validation_blockers": list(validation_blockers),
        "raw_brief_json_included": False,
    }


def _build_live_thesis_monitor(trigger: Mapping[str, Any]) -> dict[str, object]:
    trigger_state = _safe_text(_string_or_none(trigger.get("state")) or "UNAVAILABLE").upper()
    blocking_reasons = _sequence_text(trigger.get("blocking_reasons"))
    invalid_reasons = _sequence_text(trigger.get("invalid_reasons"))
    transition_narrative = narrate_trigger_transition(trigger).to_dict()
    return {
        "setup_id": _safe_text(_string_or_none(trigger.get("setup_id")) or "unavailable"),
        "trigger_id": _safe_text(_string_or_none(trigger.get("trigger_id")) or "unavailable"),
        "trigger_state": trigger_state,
        "distance_to_trigger_ticks": trigger.get("distance_to_trigger_ticks"),
        "required_fields": list(_sequence_fields(trigger.get("required_fields"))),
        "missing_fields": list(_sequence_fields(trigger.get("missing_fields"))),
        "invalid_reasons": list(invalid_reasons),
        "blocking_reasons": list(blocking_reasons),
        "state_flags": {
            "stale": trigger_state == "STALE",
            "lockout": trigger_state == "LOCKOUT",
            "error": trigger_state == "ERROR",
            "invalidated": trigger_state == "INVALIDATED",
            "blocked": trigger_state == "BLOCKED" or bool(blocking_reasons),
            "unavailable": trigger_state == "UNAVAILABLE",
        },
        "transition_narrative": transition_narrative,
        "query_readiness_statement": QUERY_READY_READINESS_STATEMENT,
    }


def _build_pipeline_gate(gate: Mapping[str, Any]) -> dict[str, object]:
    enabled = _safe_pipeline_gate_enabled(gate)
    disabled_reasons = _sequence_text(gate.get("disabled_reasons"))
    blocking_reasons = _sequence_text(gate.get("blocking_reasons"))
    if not gate:
        disabled_reasons = ("pipeline_query_gate_result_unavailable",)
        blocking_reasons = disabled_reasons
    elif _raw_pipeline_gate_enabled(gate) and not enabled:
        disabled_reasons = _dedupe((*disabled_reasons, "pipeline_gate_provenance_not_verified"))
        blocking_reasons = _dedupe((*blocking_reasons, "pipeline_gate_provenance_not_verified"))
    return {
        "gate_enabled": enabled,
        "manual_query_allowed": enabled,
        "contract": _safe_text(_string_or_none(gate.get("contract")) or "unavailable"),
        "setup_id": _safe_text(_string_or_none(gate.get("setup_id")) or "unavailable"),
        "trigger_id": _safe_text(_string_or_none(gate.get("trigger_id")) or "unavailable"),
        "trigger_state": _safe_text(_string_or_none(gate.get("trigger_state")) or "UNAVAILABLE").upper(),
        "trigger_state_from_real_producer": gate.get("trigger_state_from_real_producer") is True,
        "enabled_reasons": list(_sequence_text(gate.get("enabled_reasons"))),
        "disabled_reasons": list(disabled_reasons),
        "blocking_reasons": list(blocking_reasons),
        "required_conditions": list(_sequence_text(gate.get("required_conditions"))),
        "missing_conditions": list(_sequence_text(gate.get("missing_conditions"))),
        "gate_statement": PIPELINE_GATE_STATEMENT,
    }


def _raw_pipeline_gate_enabled(gate: Mapping[str, Any]) -> bool:
    return gate.get("enabled") is True or gate.get("pipeline_query_authorized") is True


def _safe_pipeline_gate_enabled(gate: Mapping[str, Any]) -> bool:
    if not _raw_pipeline_gate_enabled(gate):
        return False
    return (
        _safe_text(_string_or_none(gate.get("trigger_state")) or "UNAVAILABLE").upper() == "QUERY_READY"
        and gate.get("trigger_state_from_real_producer") is True
    )


def _build_last_pipeline_result(last_pipeline_result: Mapping[str, Any] | None) -> dict[str, object]:
    if last_pipeline_result is None:
        return {
            "status": "not_queried",
            "summary": {},
            "unavailable_reason": _NO_PIPELINE_RESULT_REASON,
            "result_statement": "No preserved-engine decision is invented before an operator-initiated query.",
        }
    status = _safe_status(_string_or_none(last_pipeline_result.get("status")) or "available")
    summary_keys = (
        "contract",
        "termination_stage",
        "final_decision",
        "sufficiency_gate_status",
        "contract_analysis_outcome",
        "proposed_setup_outcome",
    )
    summary = {
        key: _safe_text(value) if value is not None else None
        for key in summary_keys
        if (value := last_pipeline_result.get(key)) is not None
    }
    return {
        "status": status,
        "summary": summary,
        "result_statement": "Preserved-engine summary only; no alternate suggestions are generated.",
    }


def _build_evidence_and_replay(
    request: OperatorWorkspaceRequest,
    *,
    contract: str,
    live_thesis_monitor: Mapping[str, Any],
    last_pipeline_result: Mapping[str, Any],
) -> dict[str, object]:
    transition_log = _trigger_transition_log_summary(
        request.trigger_transition_log,
        contract,
        profile_id=request.profile_id,
    )
    transition_log_status = _safe_status(
        request.trigger_transition_log_status or transition_log["status"]
    )
    reasons = tuple(_safe_text(reason) for reason in request.evidence_unavailable_reasons if str(reason).strip())
    if not reasons:
        default_reasons = [
            "Run history source not supplied to the workspace view model.",
            "Audit replay source not supplied to the workspace view model.",
            "Operator notes source not wired in this foundation.",
        ]
        if request.trigger_transition_log is None:
            default_reasons.append("Trigger transition log source not wired in this foundation.")
        reasons = tuple(default_reasons)
    decision_review_audit_event = build_decision_review_audit_event(
        decision_review=_decision_review_payload_from_last_pipeline_result(
            last_pipeline_result,
            contract=contract,
        ),
        live_thesis_monitor=live_thesis_monitor,
        profile_id=request.profile_id,
        created_at=request.evaluated_at,
    ).to_dict()
    decision_review_replay = build_decision_review_replay_vm(
        decision_review_audit_event,
        audit_replay_record=request.audit_replay_record,
    ).to_dict()
    return {
        "run_history_status": _safe_status(request.run_history_status or "unavailable"),
        "audit_replay_status": _safe_status(_audit_replay_status(request)),
        "operator_notes_status": _safe_status(request.operator_notes_status or "unavailable"),
        "trigger_transition_log_status": transition_log_status,
        "trigger_transition_log": transition_log,
        "unavailable_reasons": list(reasons),
        "decision_review_audit_event": decision_review_audit_event,
        "decision_review_replay": decision_review_replay,
        "replay_statement": _NO_SYNTHETIC_REPLAY_STATEMENT,
    }


def _trigger_transition_log_summary(
    log: Mapping[str, Any] | None,
    contract: str,
    *,
    profile_id: str | None = None,
) -> dict[str, object]:
    if log is None:
        return {
            "status": "unavailable",
            "count": 0,
            "contract": contract,
            "blocking_reasons": ["log_source_not_wired"],
            "source_schema": None,
        }
    log_contract = _safe_text(log.get("contract") or "").upper()
    source_schema = _string_or_none(log.get("schema"))
    safe_source_schema = _safe_text(source_schema) if source_schema else None
    expected_profile_id = _safe_text(profile_id) if profile_id else None
    log_profile_id = _string_or_none(log.get("profile_id"))
    safe_log_profile_id = _safe_text(log_profile_id) if log_profile_id else None
    if source_schema != EVIDENCE_REPLAY_SCHEMA:
        return {
            "status": "blocked",
            "count": 0,
            "contract": contract,
            "profile_id": expected_profile_id,
            "blocking_reasons": [
                f"unsupported_transition_log_schema:{safe_source_schema or '<missing>'}",
            ],
            "source_schema": safe_source_schema,
        }
    transitions = log.get("trigger_transitions")
    transition_tuple = tuple(transitions) if isinstance(transitions, (list, tuple)) else ()
    if log_contract and log_contract != contract:
        return {
            "status": "blocked",
            "count": 0,
            "contract": contract,
            "profile_id": expected_profile_id,
            "blocking_reasons": [f"cross_contract_replay_summary:{log_contract}"],
            "source_schema": safe_source_schema,
        }
    if not transition_tuple:
        return {
            "status": "unavailable",
            "count": 0,
            "contract": contract,
            "profile_id": expected_profile_id,
            "blocking_reasons": ["log_empty_no_transitions_recorded"],
            "source_schema": safe_source_schema,
        }
    if expected_profile_id and safe_log_profile_id != expected_profile_id:
        return {
            "status": "blocked",
            "count": 0,
            "contract": contract,
            "profile_id": expected_profile_id,
            "blocking_reasons": [
                f"cross_profile_replay_summary:{safe_log_profile_id or '<missing>'}",
            ],
            "source_schema": safe_source_schema,
        }
    return {
        "status": "available",
        "count": len(transition_tuple),
        "contract": contract,
        "profile_id": expected_profile_id,
        "blocking_reasons": [],
        "source_schema": safe_source_schema,
    }


def _decision_review_payload_from_last_pipeline_result(
    last_pipeline_result: Mapping[str, Any],
    *,
    contract: str,
) -> dict[str, object]:
    summary = last_pipeline_result.get("summary")
    if not isinstance(summary, Mapping) or not summary:
        return {
            "surface": "Decision Review",
            "has_result": False,
            "contract": contract,
            "message": _safe_text(last_pipeline_result.get("unavailable_reason") or _NO_PIPELINE_RESULT_REASON),
            "narrative_available": False,
        }
    return {
        "surface": "Decision Review",
        "has_result": True,
        "contract": _safe_text(summary.get("contract") or contract),
        "status": _safe_status(last_pipeline_result.get("status") or "available"),
        "termination_stage": _safe_text(summary.get("termination_stage") or "unavailable"),
        "final_decision": _safe_text(summary.get("final_decision") or "unavailable"),
        "stage_a_status": _safe_text(summary.get("sufficiency_gate_status") or "unavailable"),
        "stage_b_outcome": _safe_text(summary.get("contract_analysis_outcome") or "unavailable"),
        "stage_c_outcome": _safe_text(summary.get("proposed_setup_outcome") or "unavailable"),
        "stage_d_decision": _safe_text(summary.get("risk_authorization_decision") or "unavailable"),
        "narrative_available": False,
        "narrative_unavailable_message": "Decision Review engine narrative is unavailable in this workspace snapshot.",
    }


def _audit_replay_status(request: OperatorWorkspaceRequest) -> str:
    if request.audit_replay_status:
        return request.audit_replay_status
    record = request.audit_replay_record
    if isinstance(record, Mapping):
        return "available" if record.get("replay_available") is True else "unavailable"
    return "unavailable"


def _brief_sections(
    brief: Mapping[str, Any] | None,
) -> tuple[list[dict[str, object]], list[dict[str, object]], tuple[str, ...], tuple[str, ...], list[dict[str, object]]]:
    setup_summaries: list[dict[str, object]] = []
    trigger_summaries: list[dict[str, object]] = []
    required_live_fields: list[str] = []
    warnings: list[str] = []
    invalidators: list[dict[str, object]] = []
    setups = brief.get("structural_setups") if isinstance(brief, Mapping) else None
    for setup in setups if isinstance(setups, list) else []:
        if not isinstance(setup, Mapping):
            continue
        setup_id = _safe_text(setup.get("id") or "unavailable")
        setup_summaries.append(
            {
                "setup_id": setup_id,
                "summary": _safe_text(setup.get("summary") or "unavailable"),
            }
        )
        required_live_fields.extend(_sequence_fields(setup.get("required_live_fields")))
        warnings.extend(_sequence_text(setup.get("warnings")))
        triggers = setup.get("query_triggers")
        for trigger in triggers if isinstance(triggers, list) else []:
            if not isinstance(trigger, Mapping):
                continue
            trigger_fields = _sequence_fields(trigger.get("required_live_fields"))
            required_live_fields.extend(trigger_fields)
            trigger_summaries.append(
                {
                    "setup_id": setup_id,
                    "trigger_id": _safe_text(trigger.get("id") or "unavailable"),
                    "summary": _safe_text(trigger.get("description") or trigger.get("logic") or "unavailable"),
                    "required_live_fields": list(trigger_fields),
                }
            )
            invalidators.extend(_invalidator_items(trigger.get("invalidators"), setup_id=setup_id, trigger_id=trigger.get("id")))
    return setup_summaries, trigger_summaries, _dedupe(required_live_fields), tuple(_dedupe(warnings)), invalidators


def _invalidator_items(value: object, *, setup_id: str, trigger_id: object) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for item in value if isinstance(value, list) else []:
        if not isinstance(item, Mapping):
            continue
        items.append(
            {
                "setup_id": setup_id,
                "trigger_id": _safe_text(trigger_id or "unavailable"),
                "invalidator_id": _safe_text(item.get("id") or "unavailable"),
                "condition": _safe_text(item.get("condition") or "unavailable"),
                "action": _safe_text(item.get("action") or "unavailable"),
            }
        )
    return items


def _unavailable_fields(brief: Mapping[str, Any] | None) -> list[dict[str, object]]:
    fields = brief.get("unavailable_fields") if isinstance(brief, Mapping) else None
    result: list[dict[str, object]] = []
    for item in fields if isinstance(fields, list) else []:
        if isinstance(item, Mapping):
            result.append(
                {
                    "field": _safe_field(item.get("field") or "unavailable"),
                    "reason": _safe_text(item.get("reason") or "unavailable"),
                    "status": "unavailable_not_inferred",
                }
            )
        elif isinstance(item, str):
            result.append({"field": _safe_field(item), "reason": "unavailable", "status": "unavailable_not_inferred"})
    return result


def _source_context_blockers(brief: Mapping[str, Any] | None) -> tuple[str, ...]:
    source_context = brief.get("source_context") if isinstance(brief, Mapping) else None
    if not isinstance(source_context, Mapping):
        return ()
    blockers = list(_sequence_fields(source_context.get("missing_required_context")))
    blockers.extend(_sequence_fields(source_context.get("unavailable_required_context")))
    return _dedupe(blockers)


def _validator_payload(value: WatchmanValidatorResult | Mapping[str, Any] | str | None) -> dict[str, object]:
    if isinstance(value, WatchmanValidatorResult):
        return {
            "status": value.status,
            "failing_validators": list(value.failing_validators),
            "failing_validator_summaries": list(value.failing_validator_summaries),
        }
    if isinstance(value, Mapping):
        status = value.get("validator_status", value.get("status"))
        return {
            "status": _safe_text(_string_or_none(status) or "unavailable"),
            "failing_validators": list(_sequence_text(value.get("failing_validators"))),
            "failing_validator_summaries": list(_sequence_text(value.get("failing_validator_summaries"))),
        }
    if isinstance(value, str):
        return {"status": _safe_text(value), "failing_validators": [], "failing_validator_summaries": []}
    return {"status": "unavailable", "failing_validators": [], "failing_validator_summaries": []}


def _trigger_payload(value: TriggerStateResult | Mapping[str, Any] | None, gate: Mapping[str, Any]) -> dict[str, object]:
    if isinstance(value, TriggerStateResult):
        return value.to_dict()
    if isinstance(value, Mapping):
        return dict(value)
    return {
        "setup_id": gate.get("setup_id"),
        "trigger_id": gate.get("trigger_id"),
        "state": gate.get("trigger_state", "UNAVAILABLE"),
        "distance_to_trigger_ticks": None,
        "required_fields": [],
        "missing_fields": [],
        "invalid_reasons": [],
        "blocking_reasons": ["trigger_state_result_unavailable"],
    }


def _gate_payload(value: PipelineQueryGateResult | Mapping[str, Any] | None) -> dict[str, object]:
    if isinstance(value, PipelineQueryGateResult):
        return value.to_dict()
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _live_payload(value: LiveObservableSnapshotV2 | Mapping[str, Any] | None, contract: str) -> dict[str, object]:
    if isinstance(value, LiveObservableSnapshotV2):
        payload = value.to_dict()
    elif isinstance(value, Mapping):
        payload = dict(value)
    else:
        return {}
    quote_freshness = "unknown"
    contracts = payload.get("contracts")
    contract_payload = contracts.get(contract) if isinstance(contracts, Mapping) else None
    if isinstance(contract_payload, Mapping):
        quality = contract_payload.get("quality")
        if isinstance(quality, Mapping):
            quote_freshness = "fresh" if quality.get("fresh") is True else "stale_or_unavailable"
    return {
        "provider_status": payload.get("provider_status"),
        "generated_at": payload.get("generated_at"),
        "quote_freshness": quote_freshness,
    }


def _support_status(contract: str, support_matrix_final_supported: bool | None) -> str:
    if support_matrix_final_supported is False:
        return "support_matrix_mismatch"
    if is_final_target_contract(contract):
        return "final_supported"
    return contract_policy_label(contract)


def _session_status_from_gate(gate: Mapping[str, Any]) -> str:
    if gate.get("session_valid") is True:
        return "valid"
    if gate.get("session_valid") is False:
        return "invalid"
    return "unknown"


def _event_lockout_status_from_gate(gate: Mapping[str, Any]) -> str:
    if gate.get("event_lockout_active") is True:
        return "active"
    if gate.get("event_lockout_active") is False:
        return "inactive"
    return "unknown"


def _sequence_text(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return ()
    return tuple(_safe_text(item) for item in value if str(item).strip())


def _sequence_fields(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return ()
    return tuple(_safe_field(item) for item in value if str(item).strip())


def _safe_text(value: object) -> str:
    return redact_sensitive_text(value).strip()


def _safe_status(value: object) -> str:
    return _safe_text(value).strip().lower() if str(value).strip() else "unavailable"


def _safe_field(value: object) -> str:
    text = str(value).strip()
    if _SAFE_FIELD_RE.fullmatch(text):
        return text
    return _safe_text(text)


def _string_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = _safe_text(value)
    return text if text else None


def _dedupe(values: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return tuple(result)
