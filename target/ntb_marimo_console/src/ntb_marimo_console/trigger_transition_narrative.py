from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ntb_marimo_console.market_data.stream_events import redact_sensitive_text
from ntb_marimo_console.trigger_state import TriggerState, TriggerStateResult


@dataclass(frozen=True)
class TriggerTransitionNarrativeVM:
    narrative_available: bool
    state_label: str
    transition_summary: str
    readiness_explanation: str
    blocking_explanation: str | None
    invalidation_explanation: str | None
    missing_data_explanation: str | None
    operator_guidance: str
    source_fields: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "narrative_available": self.narrative_available,
            "state_label": self.state_label,
            "transition_summary": self.transition_summary,
            "readiness_explanation": self.readiness_explanation,
            "blocking_explanation": self.blocking_explanation,
            "invalidation_explanation": self.invalidation_explanation,
            "missing_data_explanation": self.missing_data_explanation,
            "operator_guidance": self.operator_guidance,
            "source_fields": list(self.source_fields),
        }


def narrate_trigger_transition(
    trigger_state: TriggerStateResult | Mapping[str, Any] | None,
) -> TriggerTransitionNarrativeVM:
    payload = _trigger_payload(trigger_state)
    if not payload:
        return _unavailable_narrative(
            "Trigger transition narrative is unavailable because no trigger-state payload was supplied.",
            source_fields=(),
        )

    state = _state_from_payload(payload)
    if state is None:
        return _unavailable_narrative(
            "Trigger transition narrative is unavailable because the trigger state is missing or unrecognized.",
            source_fields=_present_fields(payload, ("state", "blocking_reasons", "missing_fields")),
        )

    facts = _NarrativeFacts(
        state=state,
        setup_id=_optional_text(payload.get("setup_id")),
        trigger_id=_optional_text(payload.get("trigger_id")),
        distance_to_trigger_ticks=_optional_number(payload.get("distance_to_trigger_ticks")),
        missing_fields=_sequence_text(payload.get("missing_fields")),
        invalid_reasons=_sequence_text(payload.get("invalid_reasons")),
        blocking_reasons=_sequence_text(payload.get("blocking_reasons")),
        required_fields=_sequence_text(payload.get("required_fields")),
    )
    return _narrative_for_state(facts)


@dataclass(frozen=True)
class _NarrativeFacts:
    state: TriggerState
    setup_id: str | None
    trigger_id: str | None
    distance_to_trigger_ticks: float | None
    missing_fields: tuple[str, ...]
    invalid_reasons: tuple[str, ...]
    blocking_reasons: tuple[str, ...]
    required_fields: tuple[str, ...]


def _narrative_for_state(facts: _NarrativeFacts) -> TriggerTransitionNarrativeVM:
    source_fields = _source_fields(facts)
    blocking = _blocking_explanation(facts)
    invalidation = _invalidation_explanation(facts)
    missing = _missing_data_explanation(facts)
    guidance = (
        "Use this deterministic read model for audit context only. The preserved pipeline remains the decision "
        "authority, and any execution remains manual."
    )

    if facts.state == TriggerState.UNAVAILABLE:
        return TriggerTransitionNarrativeVM(
            narrative_available=True,
            state_label=facts.state.value,
            transition_summary=_with_context(
                facts,
                "Required trigger artifact, profile, snapshot, or app-owned trigger state is unavailable.",
            ),
            readiness_explanation="The trigger transition is fail-closed until the required state is present.",
            blocking_explanation=blocking,
            invalidation_explanation=None,
            missing_data_explanation=missing,
            operator_guidance=guidance,
            source_fields=source_fields,
        )

    if facts.state == TriggerState.DORMANT:
        return TriggerTransitionNarrativeVM(
            narrative_available=True,
            state_label=facts.state.value,
            transition_summary=_with_context(
                facts,
                _distance_summary(
                    facts,
                    available_prefix="No actionable trigger proximity has been reached",
                    unavailable_summary="No actionable trigger proximity has been reached; distance-to-trigger ticks is unavailable, so proximity is not inferred.",
                ),
            ),
            readiness_explanation="The trigger remains dormant and the bounded pipeline query gate is not satisfied.",
            blocking_explanation=blocking,
            invalidation_explanation=None,
            missing_data_explanation=missing,
            operator_guidance=guidance,
            source_fields=source_fields,
        )

    if facts.state == TriggerState.APPROACHING:
        return TriggerTransitionNarrativeVM(
            narrative_available=True,
            state_label=facts.state.value,
            transition_summary=_with_context(
                facts,
                _distance_summary(
                    facts,
                    available_prefix="The trigger is approaching its declared level",
                    unavailable_summary="The trigger is marked approaching, but distance-to-trigger ticks is unavailable; proximity beyond the reported state is not inferred.",
                ),
            ),
            readiness_explanation="The trigger has not reached deterministic touch and confirmation requirements.",
            blocking_explanation=blocking,
            invalidation_explanation=None,
            missing_data_explanation=missing,
            operator_guidance=guidance,
            source_fields=source_fields,
        )

    if facts.state == TriggerState.TOUCHED:
        return TriggerTransitionNarrativeVM(
            narrative_available=True,
            state_label=facts.state.value,
            transition_summary=_with_context(
                facts,
                "Trigger level contact is reported, but completed-bar confirmation is incomplete.",
            ),
            readiness_explanation="The read model is waiting for completed deterministic confirmation before the query gate can pass.",
            blocking_explanation=blocking,
            invalidation_explanation=None,
            missing_data_explanation=missing,
            operator_guidance=guidance,
            source_fields=source_fields,
        )

    if facts.state == TriggerState.ARMED:
        return TriggerTransitionNarrativeVM(
            narrative_available=True,
            state_label=facts.state.value,
            transition_summary=_with_context(
                facts,
                "Partial deterministic confirmation is present, but the query gate has not fully passed.",
            ),
            readiness_explanation="Additional confirmation or predicate evidence is still required before a bounded pipeline query is available.",
            blocking_explanation=blocking,
            invalidation_explanation=None,
            missing_data_explanation=missing,
            operator_guidance=guidance,
            source_fields=source_fields,
        )

    if facts.state == TriggerState.QUERY_READY:
        return TriggerTransitionNarrativeVM(
            narrative_available=True,
            state_label=facts.state.value,
            transition_summary=_with_context(
                facts,
                "Deterministic trigger and data-quality gates are satisfied for a bounded pipeline query.",
            ),
            readiness_explanation=(
                "The preserved pipeline must still decide; QUERY_READY does not approve or authorize a trade, "
                "and execution remains manual."
            ),
            blocking_explanation=None,
            invalidation_explanation=None,
            missing_data_explanation=missing,
            operator_guidance=guidance,
            source_fields=source_fields,
        )

    if facts.state == TriggerState.INVALIDATED:
        return TriggerTransitionNarrativeVM(
            narrative_available=True,
            state_label=facts.state.value,
            transition_summary=_with_context(
                facts,
                "The trigger has been invalidated by app-owned invalidation state.",
            ),
            readiness_explanation="The trigger remains fail-closed while invalidation is active.",
            blocking_explanation=blocking,
            invalidation_explanation=invalidation or "Invalidation is active, but no invalidator detail was supplied.",
            missing_data_explanation=missing,
            operator_guidance=guidance + " The narrative does not provide a replacement thesis.",
            source_fields=source_fields,
        )

    if facts.state == TriggerState.BLOCKED:
        return TriggerTransitionNarrativeVM(
            narrative_available=True,
            state_label=facts.state.value,
            transition_summary=_with_context(
                facts,
                "The trigger is blocked by deterministic prerequisites or missing app-owned fields.",
            ),
            readiness_explanation="The bounded pipeline query gate remains unavailable until the blockers clear.",
            blocking_explanation=blocking or "Trigger blocking state is present without a supplied blocking reason.",
            invalidation_explanation=invalidation,
            missing_data_explanation=missing,
            operator_guidance=guidance,
            source_fields=source_fields,
        )

    if facts.state == TriggerState.LOCKOUT:
        return TriggerTransitionNarrativeVM(
            narrative_available=True,
            state_label=facts.state.value,
            transition_summary=_with_context(facts, "An event or session lockout is active for this trigger."),
            readiness_explanation="Lockout suppresses trigger readiness regardless of proximity or partial confirmation.",
            blocking_explanation=blocking or "Lockout is active without a supplied lockout reason.",
            invalidation_explanation=None,
            missing_data_explanation=missing,
            operator_guidance=guidance,
            source_fields=source_fields,
        )

    if facts.state == TriggerState.STALE:
        return TriggerTransitionNarrativeVM(
            narrative_available=True,
            state_label=facts.state.value,
            transition_summary=_with_context(facts, "Quote, bar, or cache state is stale for the trigger read model."),
            readiness_explanation="Fresh deterministic inputs are required before a bounded pipeline query is available.",
            blocking_explanation=blocking or "Stale trigger state is present without a supplied stale reason.",
            invalidation_explanation=None,
            missing_data_explanation=missing,
            operator_guidance=guidance,
            source_fields=source_fields,
        )

    return TriggerTransitionNarrativeVM(
        narrative_available=True,
        state_label=facts.state.value,
        transition_summary=_with_context(facts, "A deterministic trigger runtime or predicate error was reported."),
        readiness_explanation="The trigger state remains fail-closed while the runtime error state is present.",
        blocking_explanation=blocking or "Runtime error state is present; sensitive details are not surfaced here.",
        invalidation_explanation=invalidation,
        missing_data_explanation=missing,
        operator_guidance=guidance,
        source_fields=source_fields,
    )


def _unavailable_narrative(message: str, *, source_fields: tuple[str, ...]) -> TriggerTransitionNarrativeVM:
    return TriggerTransitionNarrativeVM(
        narrative_available=False,
        state_label="UNAVAILABLE",
        transition_summary=message,
        readiness_explanation="No trigger readiness is inferred without a recognized trigger-state payload.",
        blocking_explanation="Trigger transition narrative is blocked by unavailable app-owned state.",
        invalidation_explanation=None,
        missing_data_explanation="Required trigger-state fields are unavailable.",
        operator_guidance=(
            "Use this deterministic read model for audit context only. The preserved pipeline remains the decision "
            "authority, and any execution remains manual."
        ),
        source_fields=source_fields,
    )


def _trigger_payload(value: TriggerStateResult | Mapping[str, Any] | None) -> dict[str, Any]:
    if isinstance(value, TriggerStateResult):
        return value.to_dict()
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _state_from_payload(payload: Mapping[str, Any]) -> TriggerState | None:
    raw = payload.get("state", payload.get("trigger_state"))
    if isinstance(raw, TriggerState):
        return raw
    try:
        return TriggerState(str(raw).strip().upper())
    except ValueError:
        return None


def _distance_summary(facts: _NarrativeFacts, *, available_prefix: str, unavailable_summary: str) -> str:
    if facts.distance_to_trigger_ticks is None:
        return unavailable_summary
    return f"{available_prefix}; distance-to-trigger is {_format_number(facts.distance_to_trigger_ticks)} ticks."


def _with_context(facts: _NarrativeFacts, summary: str) -> str:
    parts: list[str] = []
    if facts.setup_id is not None:
        parts.append(f"setup {facts.setup_id}")
    if facts.trigger_id is not None:
        parts.append(f"trigger {facts.trigger_id}")
    if not parts:
        return summary
    return f"{' / '.join(parts)}: {summary}"


def _blocking_explanation(facts: _NarrativeFacts) -> str | None:
    if not facts.blocking_reasons:
        return None
    return "Blocking reasons: " + ", ".join(facts.blocking_reasons) + "."


def _invalidation_explanation(facts: _NarrativeFacts) -> str | None:
    if not facts.invalid_reasons:
        return None
    return "Invalidation reasons: " + ", ".join(facts.invalid_reasons) + "."


def _missing_data_explanation(facts: _NarrativeFacts) -> str | None:
    messages: list[str] = []
    if facts.missing_fields:
        messages.append("Missing required trigger data: " + ", ".join(facts.missing_fields) + ".")
    if "trigger_level_required" in facts.blocking_reasons:
        messages.append("Trigger level is unavailable; no level is inferred.")
    if facts.distance_to_trigger_ticks is None and facts.state in {
        TriggerState.DORMANT,
        TriggerState.APPROACHING,
        TriggerState.TOUCHED,
        TriggerState.ARMED,
        TriggerState.QUERY_READY,
        TriggerState.INVALIDATED,
        TriggerState.LOCKOUT,
    }:
        messages.append("Distance-to-trigger ticks is unavailable; no proximity is inferred.")
    if not messages:
        return None
    return " ".join(messages)


def _source_fields(facts: _NarrativeFacts) -> tuple[str, ...]:
    fields = ["state"]
    if facts.setup_id is not None:
        fields.append("setup_id")
    if facts.trigger_id is not None:
        fields.append("trigger_id")
    if facts.distance_to_trigger_ticks is not None:
        fields.append("distance_to_trigger_ticks")
    if facts.required_fields:
        fields.append("required_fields")
    if facts.missing_fields:
        fields.append("missing_fields")
    if facts.invalid_reasons:
        fields.append("invalid_reasons")
    if facts.blocking_reasons:
        fields.append("blocking_reasons")
    return tuple(fields)


def _present_fields(payload: Mapping[str, Any], fields: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(field for field in fields if field in payload)


def _sequence_text(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return ()
    return tuple(_safe_text(item) for item in value if str(item).strip())


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = _safe_text(value)
    return text or None


def _optional_number(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return None


def _safe_text(value: object) -> str:
    return redact_sensitive_text(value).strip()


def _format_number(value: float) -> str:
    return f"{value:g}"
