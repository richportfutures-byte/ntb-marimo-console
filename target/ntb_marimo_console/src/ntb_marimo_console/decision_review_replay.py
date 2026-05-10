from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final

from ntb_marimo_console.adapters.contracts import AuditReplayRecord
from ntb_marimo_console.decision_review_audit import DecisionReviewAuditEvent
from ntb_marimo_console.market_data.stream_events import redact_sensitive_text


DECISION_REVIEW_REPLAY_VM_SCHEMA: Final[str] = "decision_review_narrative_audit_replay_vm_v1"
DECISION_REVIEW_REPLAY_VM_SCHEMA_VERSION: Final[int] = 1
_UNAVAILABLE_MESSAGE: Final[str] = (
    "Decision Review narrative audit replay is unavailable. No recorded review event is present."
)
_AUTHORITY_UNAVAILABLE_MESSAGE: Final[str] = (
    "Replay authority fields are unavailable because no recorded review event is present."
)
_TRIGGER_NARRATIVE_UNAVAILABLE_MESSAGE: Final[str] = (
    "Trigger transition narrative replay fields are unavailable in the recorded review event."
)
_REPLAY_REFERENCE_UNAVAILABLE_MESSAGE: Final[str] = (
    "Audit replay source reference is unavailable; no existing replay record was supplied."
)
_SAFE_IDENTIFIER_RE: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9_.:-]+")
_SENSITIVE_IDENTIFIER_PARTS: Final[tuple[str, ...]] = (
    "access",
    "authorization",
    "bearer",
    "account",
    "correl",
    "customer",
    "private",
    "refresh",
    "secret",
    "streamer",
    "token",
)


@dataclass(frozen=True)
class DecisionReviewReplayVM:
    available: bool
    unavailable_message: str | None
    audit_schema: str | None
    audit_schema_version: int | None
    created_at: str | None
    contract: str | None
    profile_id: str | None
    setup_id: str | None
    trigger_id: str | None
    trigger_state: str | None
    source: str
    pipeline_result_status: str | None
    final_decision: str | None
    termination_stage: str | None
    engine_narrative_available: bool
    trigger_transition_narrative_available: bool
    engine_reasoning_summary: dict[str, object]
    transition_summary: str | None
    readiness_explanation: str | None
    blocking_explanation: str | None
    invalidation_explanation: str | None
    missing_data_explanation: str | None
    blocking_reasons: tuple[str, ...]
    invalid_reasons: tuple[str, ...]
    missing_fields: tuple[str, ...]
    stale: bool
    lockout: bool
    manual_only_execution: bool
    preserved_engine_authority: bool
    authority_statement: str
    replay_reference_available: bool
    replay_reference_status: str
    replay_reference_source: str
    replay_reference_run_id: str | None
    replay_reference_final_decision: str | None
    replay_reference_stage_e_live_backend: bool
    replay_reference_consistent: bool | None
    replay_reference_message: str
    source_fields: tuple[str, ...]
    schema: str = DECISION_REVIEW_REPLAY_VM_SCHEMA
    schema_version: int = DECISION_REVIEW_REPLAY_VM_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "schema_version": self.schema_version,
            "available": self.available,
            "unavailable_message": self.unavailable_message,
            "audit_schema": self.audit_schema,
            "audit_schema_version": self.audit_schema_version,
            "created_at": self.created_at,
            "source": self.source,
            "contract": self.contract,
            "profile_id": self.profile_id,
            "setup_id": self.setup_id,
            "trigger_id": self.trigger_id,
            "trigger_state": self.trigger_state,
            "pipeline_result_status": self.pipeline_result_status,
            "final_decision": self.final_decision,
            "termination_stage": self.termination_stage,
            "engine_narrative_available": self.engine_narrative_available,
            "trigger_transition_narrative_available": self.trigger_transition_narrative_available,
            "engine_reasoning_summary": self.engine_reasoning_summary,
            "transition_summary": self.transition_summary,
            "readiness_explanation": self.readiness_explanation,
            "blocking_explanation": self.blocking_explanation,
            "invalidation_explanation": self.invalidation_explanation,
            "missing_data_explanation": self.missing_data_explanation,
            "blocking_reasons": list(self.blocking_reasons),
            "invalid_reasons": list(self.invalid_reasons),
            "missing_fields": list(self.missing_fields),
            "stale": self.stale,
            "lockout": self.lockout,
            "manual_only_execution": self.manual_only_execution,
            "preserved_engine_authority": self.preserved_engine_authority,
            "authority_statement": self.authority_statement,
            "replay_reference_available": self.replay_reference_available,
            "replay_reference_status": self.replay_reference_status,
            "replay_reference_source": self.replay_reference_source,
            "replay_reference_run_id": self.replay_reference_run_id,
            "replay_reference_final_decision": self.replay_reference_final_decision,
            "replay_reference_stage_e_live_backend": self.replay_reference_stage_e_live_backend,
            "replay_reference_consistent": self.replay_reference_consistent,
            "replay_reference_message": self.replay_reference_message,
            "source_fields": list(self.source_fields),
        }


def build_decision_review_replay_vm(
    audit_event: DecisionReviewAuditEvent | Mapping[str, Any] | None,
    *,
    audit_replay_record: AuditReplayRecord | Mapping[str, Any] | None = None,
) -> DecisionReviewReplayVM:
    event = _event_mapping(audit_event)
    replay_reference = _replay_reference(audit_replay_record, final_decision=None)
    if not event:
        return DecisionReviewReplayVM(
            available=False,
            unavailable_message=_UNAVAILABLE_MESSAGE,
            audit_schema=None,
            audit_schema_version=None,
            created_at=None,
            contract=None,
            profile_id=None,
            setup_id=None,
            trigger_id=None,
            trigger_state=None,
            source="unknown",
            pipeline_result_status=None,
            final_decision=None,
            termination_stage=None,
            engine_narrative_available=False,
            trigger_transition_narrative_available=False,
            engine_reasoning_summary={
                "available": False,
                "unavailable_message": "Engine reasoning replay fields are unavailable.",
            },
            transition_summary=_TRIGGER_NARRATIVE_UNAVAILABLE_MESSAGE,
            readiness_explanation="No trigger readiness is inferred from an absent audit event.",
            blocking_explanation=_TRIGGER_NARRATIVE_UNAVAILABLE_MESSAGE,
            invalidation_explanation=None,
            missing_data_explanation="Recorded trigger transition fields are unavailable.",
            blocking_reasons=(),
            invalid_reasons=(),
            missing_fields=(),
            stale=False,
            lockout=False,
            manual_only_execution=False,
            preserved_engine_authority=False,
            authority_statement=_AUTHORITY_UNAVAILABLE_MESSAGE,
            replay_reference_available=bool(replay_reference["available"]),
            replay_reference_status=str(replay_reference["status"]),
            replay_reference_source=str(replay_reference["source"]),
            replay_reference_run_id=_optional_text(replay_reference.get("run_id")),
            replay_reference_final_decision=_optional_text(replay_reference.get("final_decision")),
            replay_reference_stage_e_live_backend=replay_reference.get("stage_e_live_backend") is True,
            replay_reference_consistent=_optional_bool(replay_reference.get("consistent")),
            replay_reference_message=str(replay_reference["message"]),
            source_fields=(),
        )

    pipeline_result = _mapping(event.get("pipeline_result"))
    narrative = _mapping(event.get("decision_review_narrative"))
    trigger_review = _mapping(event.get("trigger_review"))
    transition = _mapping(trigger_review.get("transition_narrative"))
    state_flags = _mapping(trigger_review.get("state_flags"))
    final_decision = _optional_text(pipeline_result.get("final_decision"))
    replay_reference = _replay_reference(audit_replay_record, final_decision=final_decision)

    return DecisionReviewReplayVM(
        available=True,
        unavailable_message=None,
        audit_schema=_optional_identifier(event.get("schema")),
        audit_schema_version=_optional_int(event.get("schema_version")),
        created_at=_optional_text(event.get("created_at")),
        contract=_optional_text(event.get("contract")),
        profile_id=_optional_text(event.get("profile_id")),
        setup_id=_optional_text(event.get("setup_id")),
        trigger_id=_optional_text(event.get("trigger_id")),
        trigger_state=_optional_text(event.get("trigger_state")),
        source=_optional_identifier(event.get("source")) or "unknown",
        pipeline_result_status=_optional_text(pipeline_result.get("status")),
        final_decision=final_decision,
        termination_stage=_optional_text(pipeline_result.get("termination_stage")),
        engine_narrative_available=narrative.get("engine_reasoning_available") is True,
        trigger_transition_narrative_available=transition.get("narrative_available") is True,
        engine_reasoning_summary=_engine_reasoning_summary(event.get("engine_reasoning_summary")),
        transition_summary=_optional_text(transition.get("transition_summary"))
        or _TRIGGER_NARRATIVE_UNAVAILABLE_MESSAGE,
        readiness_explanation=_optional_text(transition.get("readiness_explanation"))
        or "Recorded trigger readiness explanation is unavailable.",
        blocking_explanation=_optional_text(transition.get("blocking_explanation")),
        invalidation_explanation=_optional_text(transition.get("invalidation_explanation")),
        missing_data_explanation=_optional_text(transition.get("missing_data_explanation")),
        blocking_reasons=_text_tuple(trigger_review.get("blocking_reasons")),
        invalid_reasons=_text_tuple(trigger_review.get("invalid_reasons")),
        missing_fields=_text_tuple(trigger_review.get("missing_fields")),
        stale=state_flags.get("stale") is True or _optional_text(event.get("trigger_state")) == "STALE",
        lockout=state_flags.get("lockout") is True or _optional_text(event.get("trigger_state")) == "LOCKOUT",
        manual_only_execution=event.get("manual_only_execution") is True,
        preserved_engine_authority=event.get("preserved_engine_authority") is True,
        authority_statement=_optional_text(event.get("authority_statement"))
        or "The preserved engine remains the decision authority, and execution remains manual.",
        replay_reference_available=bool(replay_reference["available"]),
        replay_reference_status=str(replay_reference["status"]),
        replay_reference_source=str(replay_reference["source"]),
        replay_reference_run_id=_optional_text(replay_reference.get("run_id")),
        replay_reference_final_decision=_optional_text(replay_reference.get("final_decision")),
        replay_reference_stage_e_live_backend=replay_reference.get("stage_e_live_backend") is True,
        replay_reference_consistent=_optional_bool(replay_reference.get("consistent")),
        replay_reference_message=str(replay_reference["message"]),
        source_fields=_source_fields(event, transition, replay_reference=replay_reference),
    )


def _event_mapping(
    audit_event: DecisionReviewAuditEvent | Mapping[str, Any] | None,
) -> dict[str, Any]:
    if isinstance(audit_event, DecisionReviewAuditEvent):
        return audit_event.to_dict()
    if isinstance(audit_event, Mapping):
        return dict(audit_event)
    return {}


def _engine_reasoning_summary(value: object) -> dict[str, object]:
    section = _mapping(value)
    if section.get("available") is not True:
        return {
            "available": False,
            "unavailable_message": _optional_text(section.get("unavailable_message"))
            or "Engine reasoning replay fields are unavailable.",
        }

    summary: dict[str, object] = {
        "available": True,
        "market_regime": _optional_text(section.get("market_regime")),
        "directional_bias": _optional_text(section.get("directional_bias")),
        "evidence_score": _optional_int(section.get("evidence_score")),
        "confidence_band": _optional_text(section.get("confidence_band")),
        "outcome": _optional_text(section.get("outcome")),
        "structural_notes": _optional_text(section.get("structural_notes")),
    }
    key_levels = _mapping(section.get("key_levels"))
    if key_levels:
        summary["key_levels"] = {
            "pivot_level": _optional_number(key_levels.get("pivot_level")),
            "support_levels": list(_number_tuple(key_levels.get("support_levels"))),
            "resistance_levels": list(_number_tuple(key_levels.get("resistance_levels"))),
        }
    else:
        summary["key_levels"] = None
    return summary


def _replay_reference(
    audit_replay_record: AuditReplayRecord | Mapping[str, Any] | None,
    *,
    final_decision: str | None,
) -> dict[str, object]:
    record = dict(audit_replay_record) if isinstance(audit_replay_record, Mapping) else {}
    if not record:
        return {
            "available": False,
            "status": "unavailable",
            "source": "unknown",
            "run_id": None,
            "final_decision": None,
            "stage_e_live_backend": False,
            "consistent": None,
            "message": _REPLAY_REFERENCE_UNAVAILABLE_MESSAGE,
        }

    source = _optional_identifier(record.get("source")) or "unknown"
    replay_available = record.get("replay_available") is True
    run_id = _optional_identifier(record.get("last_run_id"))
    reference_final_decision = _optional_text(record.get("last_final_decision"))
    if not replay_available:
        return {
            "available": False,
            "status": "unavailable",
            "source": source,
            "run_id": run_id,
            "final_decision": reference_final_decision,
            "stage_e_live_backend": record.get("stage_e_live_backend") is True,
            "consistent": None,
            "message": "Audit replay source reference is unavailable; the existing replay record is not ready.",
        }

    if run_id is None:
        return {
            "available": False,
            "status": "blocked",
            "source": source,
            "run_id": None,
            "final_decision": reference_final_decision,
            "stage_e_live_backend": record.get("stage_e_live_backend") is True,
            "consistent": None,
            "message": "Audit replay source reference is blocked because the replay run identifier is unavailable.",
        }

    consistent = (
        None
        if final_decision is None or reference_final_decision is None
        else final_decision == reference_final_decision
    )
    if consistent is False:
        message = (
            "Audit replay source reference is available but its final decision does not match the "
            "Decision Review audit event."
        )
        status = "mismatch"
    else:
        message = "Audit replay source reference is available from existing app-owned replay state."
        status = "available"
    return {
        "available": True,
        "status": status,
        "source": source,
        "run_id": run_id,
        "final_decision": reference_final_decision,
        "stage_e_live_backend": record.get("stage_e_live_backend") is True,
        "consistent": consistent,
        "message": message,
    }


def _source_fields(
    event: Mapping[str, Any],
    transition: Mapping[str, Any],
    *,
    replay_reference: Mapping[str, object],
) -> tuple[str, ...]:
    fields = list(_identifier_tuple(event.get("source_fields")))
    fields.extend(
        f"trigger_review.transition_narrative.{field}"
        for field in _identifier_tuple(transition.get("source_fields"))
    )
    if replay_reference.get("available") is True:
        fields.append("audit_replay_record")
        if replay_reference.get("run_id") is not None:
            fields.append("audit_replay_record.last_run_id")
    return tuple(dict.fromkeys(fields))


def _mapping(value: object) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _text_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return ()
    return tuple(_safe_text(item) for item in value if str(item).strip())


def _identifier_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return ()
    identifiers: list[str] = []
    for item in value:
        identifier = _optional_identifier(item)
        if identifier is not None:
            identifiers.append(identifier)
    return tuple(identifiers)


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


def _optional_identifier(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    lowered = text.lower()
    if text and _SAFE_IDENTIFIER_RE.fullmatch(text):
        if any(part in lowered for part in _SENSITIVE_IDENTIFIER_PARTS):
            return "[REDACTED_REF]"
        return text
    return _optional_text(value)


def _optional_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _optional_bool(value: object) -> bool | None:
    if isinstance(value, bool):
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
