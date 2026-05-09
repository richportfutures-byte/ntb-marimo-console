from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Final

from ntb_marimo_console.market_data.stream_events import redact_sensitive_text


DECISION_REVIEW_AUDIT_EVENT_SCHEMA: Final[str] = "decision_review_narrative_audit_event_v1"
DECISION_REVIEW_AUDIT_EVENT_SCHEMA_VERSION: Final[int] = 1
_UNKNOWN_SOURCE: Final[str] = "unknown"


@dataclass(frozen=True)
class DecisionReviewAuditEvent:
    created_at: str
    contract: str | None
    profile_id: str | None
    setup_id: str | None
    trigger_id: str | None
    trigger_state: str | None
    source: str
    pipeline_result: dict[str, object]
    decision_review_narrative: dict[str, object]
    engine_reasoning_summary: dict[str, object]
    trigger_review: dict[str, object]
    source_fields: tuple[str, ...]
    manual_only_execution: bool = True
    preserved_engine_authority: bool = True
    authority_statement: str = (
        "Audit evidence records what the operator-facing review displayed. "
        "The preserved engine remains the decision authority, and execution remains manual."
    )
    schema: str = DECISION_REVIEW_AUDIT_EVENT_SCHEMA
    schema_version: int = DECISION_REVIEW_AUDIT_EVENT_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "schema_version": self.schema_version,
            "created_at": self.created_at,
            "source": self.source,
            "contract": self.contract,
            "profile_id": self.profile_id,
            "setup_id": self.setup_id,
            "trigger_id": self.trigger_id,
            "trigger_state": self.trigger_state,
            "pipeline_result": self.pipeline_result,
            "decision_review_narrative": self.decision_review_narrative,
            "engine_reasoning_summary": self.engine_reasoning_summary,
            "trigger_review": self.trigger_review,
            "manual_only_execution": self.manual_only_execution,
            "preserved_engine_authority": self.preserved_engine_authority,
            "authority_statement": self.authority_statement,
            "source_fields": list(self.source_fields),
        }


def build_decision_review_audit_event(
    *,
    decision_review: Mapping[str, Any] | None,
    live_thesis_monitor: Mapping[str, Any] | None = None,
    profile_id: str | None = None,
    created_at: str | None = None,
    source: str | None = None,
) -> DecisionReviewAuditEvent:
    decision = dict(decision_review) if isinstance(decision_review, Mapping) else {}
    live_thesis = dict(live_thesis_monitor) if isinstance(live_thesis_monitor, Mapping) else {}
    trigger_review = _trigger_review(live_thesis)
    pipeline_result = _pipeline_result(decision)
    narrative = _decision_review_narrative(decision)
    engine_reasoning = _engine_reasoning_summary(decision.get("engine_reasoning"))
    contract = _optional_text(decision.get("contract"))
    setup_id = _optional_text(live_thesis.get("setup_id"))
    trigger_id = _optional_text(live_thesis.get("trigger_id"))
    trigger_state = _optional_text(live_thesis.get("trigger_state"))

    return DecisionReviewAuditEvent(
        created_at=_safe_text(created_at or _utc_now_iso()),
        contract=contract,
        profile_id=_optional_text(profile_id),
        setup_id=setup_id,
        trigger_id=trigger_id,
        trigger_state=trigger_state,
        source=_source_label(source),
        pipeline_result=pipeline_result,
        decision_review_narrative=narrative,
        engine_reasoning_summary=engine_reasoning,
        trigger_review=trigger_review,
        source_fields=_source_fields(
            decision=decision,
            live_thesis=live_thesis,
            pipeline_result=pipeline_result,
            narrative=narrative,
            engine_reasoning=engine_reasoning,
            trigger_review=trigger_review,
            profile_id=profile_id,
            source=source,
        ),
    )


def _pipeline_result(decision: Mapping[str, Any]) -> dict[str, object]:
    has_result = decision.get("has_result") is True
    return {
        "has_result": has_result,
        "status": _safe_text(decision.get("status") or ("available" if has_result else "not_loaded")),
        "final_decision": _optional_text(decision.get("final_decision")),
        "termination_stage": _optional_text(decision.get("termination_stage")),
        "stage_a_status": _optional_text(decision.get("stage_a_status")),
        "stage_b_outcome": _optional_text(decision.get("stage_b_outcome")),
        "stage_c_outcome": _optional_text(decision.get("stage_c_outcome")),
        "stage_d_decision": _optional_text(decision.get("stage_d_decision")),
    }


def _decision_review_narrative(decision: Mapping[str, Any]) -> dict[str, object]:
    engine_reasoning = _mapping(decision.get("engine_reasoning"))
    trade_thesis = _mapping(decision.get("trade_thesis"))
    risk_authorization = _mapping(decision.get("risk_authorization_detail"))
    invalidation = _mapping(decision.get("invalidation"))
    narrative_available = decision.get("narrative_available") is True
    unavailable = _optional_text(decision.get("narrative_unavailable_message"))
    if unavailable is None and not narrative_available:
        unavailable = "Decision Review narrative is unavailable."
    return {
        "narrative_available": narrative_available,
        "engine_reasoning_available": engine_reasoning.get("available") is True,
        "trade_thesis_available": trade_thesis.get("available") is True,
        "risk_authorization_available": risk_authorization.get("available") is True,
        "invalidation_available": invalidation.get("available") is True,
        "unavailable_message": unavailable,
    }


def _engine_reasoning_summary(value: object) -> dict[str, object]:
    section = _mapping(value)
    if section.get("available") is not True:
        return {
            "available": False,
            "unavailable_message": _optional_text(section.get("unavailable_message"))
            or "Engine reasoning narrative is unavailable.",
        }

    return {
        "available": True,
        "market_regime": _optional_text(section.get("market_regime")),
        "directional_bias": _optional_text(section.get("directional_bias")),
        "evidence_score": _optional_int(section.get("evidence_score")),
        "confidence_band": _optional_text(section.get("confidence_band")),
        "outcome": _optional_text(section.get("outcome")),
        "structural_notes": _optional_text(section.get("structural_notes")),
        "key_levels": _key_levels(section.get("key_levels")),
    }


def _key_levels(value: object) -> dict[str, object] | None:
    levels = _mapping(value)
    if not levels:
        return None
    return {
        "pivot_level": _optional_number(levels.get("pivot_level")),
        "support_levels": list(_number_tuple(levels.get("support_levels"))),
        "resistance_levels": list(_number_tuple(levels.get("resistance_levels"))),
    }


def _trigger_review(live_thesis: Mapping[str, Any]) -> dict[str, object]:
    transition = _mapping(live_thesis.get("transition_narrative"))
    if transition:
        transition_narrative = _transition_narrative(transition)
    else:
        transition_narrative = _unavailable_transition_narrative()
    return {
        "setup_id": _optional_text(live_thesis.get("setup_id")),
        "trigger_id": _optional_text(live_thesis.get("trigger_id")),
        "trigger_state": _optional_text(live_thesis.get("trigger_state")),
        "distance_to_trigger_ticks": _optional_number(live_thesis.get("distance_to_trigger_ticks")),
        "missing_fields": list(_text_tuple(live_thesis.get("missing_fields"))),
        "invalid_reasons": list(_text_tuple(live_thesis.get("invalid_reasons"))),
        "blocking_reasons": list(_text_tuple(live_thesis.get("blocking_reasons"))),
        "state_flags": _state_flags(live_thesis.get("state_flags")),
        "transition_narrative": transition_narrative,
    }


def _transition_narrative(value: Mapping[str, Any]) -> dict[str, object]:
    return {
        "narrative_available": value.get("narrative_available") is True,
        "state_label": _optional_text(value.get("state_label")),
        "transition_summary": _optional_text(value.get("transition_summary")),
        "readiness_explanation": _optional_text(value.get("readiness_explanation")),
        "blocking_explanation": _optional_text(value.get("blocking_explanation")),
        "invalidation_explanation": _optional_text(value.get("invalidation_explanation")),
        "missing_data_explanation": _optional_text(value.get("missing_data_explanation")),
        "operator_guidance": _optional_text(value.get("operator_guidance")),
        "source_fields": list(_text_tuple(value.get("source_fields"))),
    }


def _unavailable_transition_narrative() -> dict[str, object]:
    return {
        "narrative_available": False,
        "state_label": "UNAVAILABLE",
        "transition_summary": "Trigger transition narrative is unavailable for this audit event.",
        "readiness_explanation": "No trigger readiness is inferred without trigger transition narrative state.",
        "blocking_explanation": "Trigger transition narrative is unavailable.",
        "invalidation_explanation": None,
        "missing_data_explanation": "Trigger transition narrative fields are unavailable.",
        "operator_guidance": (
            "Audit evidence records review context only. The preserved pipeline remains the decision authority, "
            "and execution remains manual."
        ),
        "source_fields": [],
    }


def _state_flags(value: object) -> dict[str, object]:
    flags = _mapping(value)
    return {
        "stale": flags.get("stale") is True,
        "lockout": flags.get("lockout") is True,
        "error": flags.get("error") is True,
        "invalidated": flags.get("invalidated") is True,
        "blocked": flags.get("blocked") is True,
        "unavailable": flags.get("unavailable") is True,
    }


def _source_fields(
    *,
    decision: Mapping[str, Any],
    live_thesis: Mapping[str, Any],
    pipeline_result: Mapping[str, object],
    narrative: Mapping[str, object],
    engine_reasoning: Mapping[str, object],
    trigger_review: Mapping[str, object],
    profile_id: str | None,
    source: str | None,
) -> tuple[str, ...]:
    fields: list[str] = ["decision_review"]
    for key in (
        "contract",
        "has_result",
        "final_decision",
        "termination_stage",
        "stage_a_status",
        "stage_b_outcome",
        "stage_c_outcome",
        "stage_d_decision",
    ):
        if key in decision and decision.get(key) is not None:
            fields.append(f"decision_review.{key}")
    if profile_id is not None:
        fields.append("profile_id")
    if source is not None:
        fields.append("source")
    if pipeline_result.get("has_result") is True:
        fields.append("pipeline_result")
    if narrative.get("narrative_available") is True:
        fields.append("decision_review_narrative")
    if engine_reasoning.get("available") is True:
        fields.append("engine_reasoning")
    if live_thesis:
        fields.append("live_thesis_monitor")
    if isinstance(live_thesis.get("transition_narrative"), Mapping):
        fields.append("transition_narrative")
    return tuple(dict.fromkeys(fields))


def _source_label(source: str | None) -> str:
    if source is None:
        return _UNKNOWN_SOURCE
    value = _safe_text(source).strip().lower()
    if value in {"fixture", "fixture_backed", "fixture_demo"}:
        return "fixture"
    if value in {"live_cache", "runtime_cache_derived"}:
        return "live_cache"
    if value == "manual":
        return "manual"
    return _UNKNOWN_SOURCE


def _mapping(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _text_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return ()
    return tuple(_safe_text(item) for item in value if str(item).strip())


def _number_tuple(value: object) -> tuple[float, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return ()
    numbers: list[float] = []
    for item in value:
        number = _optional_number(item)
        if number is not None:
            numbers.append(number)
    return tuple(numbers)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = _safe_text(value)
    return text or None


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


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


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
