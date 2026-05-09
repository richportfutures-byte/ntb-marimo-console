from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from ntb_marimo_console.contract_universe import contract_policy_label, is_final_target_contract, normalize_contract_symbol
from ntb_marimo_console.live_observables.schema_v2 import LiveObservableSnapshotV2
from ntb_marimo_console.market_data.stream_events import redact_sensitive_text
from ntb_marimo_console.pipeline_query_gate import PipelineQueryGateResult
from ntb_marimo_console.trigger_state import TriggerStateResult
from ntb_marimo_console.trigger_transition_narrative import narrate_trigger_transition
from ntb_marimo_console.watchman_gate import WatchmanValidatorResult


OPERATOR_WORKSPACE_SCHEMA: Final[str] = "operator_workspace_view_model_v1"
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
    operator_notes_status: str | None = None
    trigger_transition_log_status: str | None = None
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
    evidence = _build_evidence_and_replay(request)
    return OperatorWorkspaceViewModel(
        header=header,
        premarket_plan=premarket_plan,
        live_thesis_monitor=live_thesis,
        pipeline_gate=pipeline_gate,
        last_pipeline_result=last_pipeline_result,
        evidence_and_replay=evidence,
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
    enabled = gate.get("enabled") is True or gate.get("pipeline_query_authorized") is True
    disabled_reasons = _sequence_text(gate.get("disabled_reasons"))
    blocking_reasons = _sequence_text(gate.get("blocking_reasons"))
    if not gate:
        disabled_reasons = ("pipeline_query_gate_result_unavailable",)
        blocking_reasons = disabled_reasons
    return {
        "gate_enabled": enabled,
        "manual_query_allowed": enabled,
        "enabled_reasons": list(_sequence_text(gate.get("enabled_reasons"))),
        "disabled_reasons": list(disabled_reasons),
        "blocking_reasons": list(blocking_reasons),
        "required_conditions": list(_sequence_text(gate.get("required_conditions"))),
        "missing_conditions": list(_sequence_text(gate.get("missing_conditions"))),
        "gate_statement": PIPELINE_GATE_STATEMENT,
    }


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


def _build_evidence_and_replay(request: OperatorWorkspaceRequest) -> dict[str, object]:
    reasons = tuple(_safe_text(reason) for reason in request.evidence_unavailable_reasons if str(reason).strip())
    if not reasons:
        reasons = (
            "Run history source not supplied to the workspace view model.",
            "Audit replay source not supplied to the workspace view model.",
            "Operator notes source not wired in this foundation.",
            "Trigger transition log source not wired in this foundation.",
        )
    return {
        "run_history_status": _safe_status(request.run_history_status or "unavailable"),
        "audit_replay_status": _safe_status(request.audit_replay_status or "unavailable"),
        "operator_notes_status": _safe_status(request.operator_notes_status or "unavailable"),
        "trigger_transition_log_status": _safe_status(request.trigger_transition_log_status or "unavailable"),
        "unavailable_reasons": list(reasons),
        "replay_statement": _NO_SYNTHETIC_REPLAY_STATEMENT,
    }


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
