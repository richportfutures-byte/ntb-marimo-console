from __future__ import annotations

import json
import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from typing import Final

from ntb_marimo_console.contract_universe import contract_policy_label, is_final_target_contract, normalize_contract_symbol
from ntb_marimo_console.market_data.stream_events import redact_sensitive_text


EVIDENCE_REPLAY_SCHEMA: Final[str] = "evidence_replay_v1"
EVIDENCE_EVENT_SCHEMA: Final[str] = "evidence_event_v1"
ALLOWED_EVIDENCE_EVENT_TYPES: Final[tuple[str, ...]] = (
    "stream_connected",
    "stream_disconnected",
    "subscription_added",
    "quote_stale",
    "quote_recovered",
    "bar_closed",
    "trigger_approaching",
    "trigger_touched",
    "trigger_armed",
    "trigger_query_ready",
    "trigger_invalidated",
    "readiness_snapshot_observed",
    "query_submitted",
    "query_blocked",
    "pipeline_result",
    "operator_note_added",
    "cockpit_refreshed",
    "cockpit_reset",
    "latest_action_state_changed",
    "session_reset",
)
ALLOWED_EVIDENCE_SOURCES: Final[tuple[str, ...]] = ("live_stream", "fixture", "manual")
REQUIRED_EVIDENCE_EVENT_FIELDS: Final[tuple[str, ...]] = (
    "event_id",
    "timestamp",
    "contract",
    "profile_id",
    "event_type",
    "setup_id",
    "trigger_id",
    "live_snapshot_ref",
    "premarket_brief_ref",
    "pipeline_run_id",
    "operator_note",
    "source",
    "data_quality",
    "redaction_status",
    "synthetic",
)
_TRIGGER_EVENT_TYPES: Final[tuple[str, ...]] = (
    "trigger_approaching",
    "trigger_touched",
    "trigger_armed",
    "trigger_query_ready",
    "trigger_invalidated",
)
_STREAM_EVENT_TYPES: Final[tuple[str, ...]] = (
    "stream_connected",
    "stream_disconnected",
    "subscription_added",
    "quote_stale",
    "quote_recovered",
)
_SAFE_DATA_QUALITY_KEYS: Final[tuple[str, ...]] = (
    "state",
    "status",
    "ready",
    "fresh",
    "gate_enabled",
    "manual_query_allowed",
    "blocking_reasons",
    "missing_conditions",
    "trigger_state",
    "pipeline_summary",
    "final_decision",
    "termination_stage",
    "sufficiency_gate_status",
    "contract_analysis_outcome",
    "proposed_setup_outcome",
    "manual_outcome",
    "source_surface",
    "summary",
    "reason",
    "request_status",
    "query_action_state",
    "runtime_readiness_status",
    "runtime_readiness_preserved",
    "replay_safety_classification",
    "creates_query_ready",
    "replay_can_authorize_trades",
)
_PIPELINE_SUMMARY_KEYS: Final[tuple[str, ...]] = (
    "contract",
    "termination_stage",
    "final_decision",
    "sufficiency_gate_status",
    "contract_analysis_outcome",
    "proposed_setup_outcome",
)
_SAFE_REF_RE: Final[re.Pattern[str]] = re.compile(r"[A-Za-z0-9_.:/=-]+")
_SENSITIVE_REF_TERMS: Final[tuple[str, ...]] = (
    "access_token",
    "refresh_token",
    "authorization",
    "bearer",
    "secret",
    "app_key",
    "app_secret",
    "credential",
    "token",
    "customer",
    "correl",
    "account",
    "://",
)


class EvidenceRecordStatus(StrEnum):
    VALID = "valid"
    INVALID = "invalid"


class ReplayStatus(StrEnum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class EvidenceEvent:
    event_id: str
    timestamp: str
    contract: str
    profile_id: str
    event_type: str
    setup_id: str | None
    trigger_id: str | None
    live_snapshot_ref: str | None
    premarket_brief_ref: str | None
    pipeline_run_id: str | None
    operator_note: str | None
    source: str
    data_quality: dict[str, object]
    redaction_status: str
    synthetic: bool
    status: EvidenceRecordStatus
    invalid_reasons: tuple[str, ...]
    schema: str = EVIDENCE_EVENT_SCHEMA

    @property
    def valid(self) -> bool:
        return self.status == EvidenceRecordStatus.VALID

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "event_id": self.event_id,
            "timestamp": self.timestamp,
            "contract": self.contract,
            "profile_id": self.profile_id,
            "event_type": self.event_type,
            "setup_id": self.setup_id,
            "trigger_id": self.trigger_id,
            "live_snapshot_ref": self.live_snapshot_ref,
            "premarket_brief_ref": self.premarket_brief_ref,
            "pipeline_run_id": self.pipeline_run_id,
            "operator_note": self.operator_note,
            "source": self.source,
            "data_quality": self.data_quality,
            "redaction_status": self.redaction_status,
            "synthetic": self.synthetic,
            "status": self.status.value,
            "valid": self.valid,
            "invalid_reasons": list(self.invalid_reasons),
        }


@dataclass(frozen=True)
class EvidenceParseResult:
    valid: bool
    event: EvidenceEvent | None
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "event": self.event.to_dict() if self.event is not None else None,
            "errors": list(self.errors),
        }


@dataclass(frozen=True)
class EvidenceEventsParseResult:
    valid: bool
    events: tuple[EvidenceEvent, ...]
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "valid": self.valid,
            "events": [event.to_dict() for event in self.events],
            "errors": list(self.errors),
        }


@dataclass(frozen=True)
class ReplaySummary:
    contract: str
    profile_id: str | None
    status: ReplayStatus
    complete: bool
    morning_plan_reference: str | None
    stream_state: dict[str, object]
    trigger_transitions: tuple[dict[str, object], ...]
    query_eligibility_events: tuple[dict[str, object], ...]
    pipeline_results: tuple[dict[str, object], ...]
    operator_notes: tuple[dict[str, object], ...]
    cockpit_events: tuple[dict[str, object], ...]
    post_session_manual_outcome: dict[str, object]
    blocking_reasons: tuple[str, ...]
    incomplete_reasons: tuple[str, ...]
    source_integrity: dict[str, object]
    replay_authority: str = "review_only_no_trade_authorization"
    schema: str = EVIDENCE_REPLAY_SCHEMA

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "contract": self.contract,
            "profile_id": self.profile_id,
            "status": self.status.value,
            "complete": self.complete,
            "morning_plan_reference": self.morning_plan_reference,
            "stream_state": self.stream_state,
            "trigger_transitions": list(self.trigger_transitions),
            "query_eligibility_events": list(self.query_eligibility_events),
            "pipeline_results": list(self.pipeline_results),
            "operator_notes": list(self.operator_notes),
            "cockpit_events": list(self.cockpit_events),
            "post_session_manual_outcome": self.post_session_manual_outcome,
            "blocking_reasons": list(self.blocking_reasons),
            "incomplete_reasons": list(self.incomplete_reasons),
            "source_integrity": self.source_integrity,
            "replay_authority": self.replay_authority,
            "replay_can_authorize_trades": False,
            "synthetic_replay_labeled_real": False,
        }


def create_evidence_event(
    *,
    contract: str,
    profile_id: str,
    event_type: str,
    source: str,
    event_id: str | None = None,
    timestamp: str | None = None,
    setup_id: str | None = None,
    trigger_id: str | None = None,
    live_snapshot_ref: str | None = None,
    premarket_brief_ref: str | None = None,
    pipeline_run_id: str | None = None,
    operator_note: str | None = None,
    data_quality: Mapping[str, object] | None = None,
    synthetic: bool = False,
) -> EvidenceEvent:
    normalized_contract = normalize_contract_symbol(contract)
    safe_event_type = _safe_text(event_type).strip().lower()
    safe_source = _safe_text(source).strip().lower()
    event_timestamp = timestamp or datetime.now(tz=timezone.utc).isoformat()
    invalid_reasons: list[str] = []

    if not is_final_target_contract(normalized_contract):
        invalid_reasons.append(f"contract_not_final_supported:{normalized_contract}:{contract_policy_label(normalized_contract)}")
    if safe_event_type not in ALLOWED_EVIDENCE_EVENT_TYPES:
        invalid_reasons.append(f"unsupported_event_type:{safe_event_type or 'missing'}")
    if safe_source not in ALLOWED_EVIDENCE_SOURCES:
        invalid_reasons.append(f"unsupported_source:{safe_source or 'missing'}")
    if synthetic and safe_source == "live_stream":
        invalid_reasons.append("synthetic_event_cannot_be_live_stream")
    if not _is_timezone_aware_iso(event_timestamp):
        invalid_reasons.append("timestamp_not_timezone_aware_iso")
    if data_quality is not None and not isinstance(data_quality, Mapping):
        invalid_reasons.append("data_quality_invalid")
    safe_data_quality = data_quality if isinstance(data_quality, Mapping) else {}

    status = EvidenceRecordStatus.INVALID if invalid_reasons else EvidenceRecordStatus.VALID
    return EvidenceEvent(
        event_id=_safe_ref(event_id or str(uuid.uuid4())),
        timestamp=_safe_text(event_timestamp),
        contract=normalized_contract,
        profile_id=_safe_ref(profile_id),
        event_type=safe_event_type,
        setup_id=_safe_optional_ref(setup_id),
        trigger_id=_safe_optional_ref(trigger_id),
        live_snapshot_ref=_safe_optional_ref(live_snapshot_ref),
        premarket_brief_ref=_safe_optional_ref(premarket_brief_ref),
        pipeline_run_id=_safe_optional_ref(pipeline_run_id),
        operator_note=_safe_optional(operator_note),
        source=safe_source,
        data_quality=_safe_data_quality(safe_data_quality),
        redaction_status="redacted",
        synthetic=bool(synthetic),
        status=status,
        invalid_reasons=tuple(invalid_reasons),
    )


def serialize_evidence_event(event: EvidenceEvent) -> str:
    return json.dumps(event.to_dict(), sort_keys=True)


def parse_evidence_event(payload: str | Mapping[str, object]) -> EvidenceParseResult:
    if isinstance(payload, str):
        try:
            loaded = json.loads(payload)
        except json.JSONDecodeError as exc:
            return EvidenceParseResult(valid=False, event=None, errors=(f"malformed_json:{exc.msg}",))
    else:
        loaded = payload
    if not isinstance(loaded, Mapping):
        return EvidenceParseResult(valid=False, event=None, errors=("event_payload_not_object",))
    missing = tuple(field for field in REQUIRED_EVIDENCE_EVENT_FIELDS if field not in loaded)
    if missing:
        return EvidenceParseResult(
            valid=False,
            event=None,
            errors=tuple(f"missing_required_field:{field}" for field in missing),
        )
    data_quality = loaded.get("data_quality")
    event = create_evidence_event(
        event_id=_string_field(loaded.get("event_id")),
        timestamp=_string_field(loaded.get("timestamp")),
        contract=_string_field(loaded.get("contract")),
        profile_id=_string_field(loaded.get("profile_id")),
        event_type=_string_field(loaded.get("event_type")),
        setup_id=_optional_string_field(loaded.get("setup_id")),
        trigger_id=_optional_string_field(loaded.get("trigger_id")),
        live_snapshot_ref=_optional_string_field(loaded.get("live_snapshot_ref")),
        premarket_brief_ref=_optional_string_field(loaded.get("premarket_brief_ref")),
        pipeline_run_id=_optional_string_field(loaded.get("pipeline_run_id")),
        operator_note=_optional_string_field(loaded.get("operator_note")),
        source=_string_field(loaded.get("source")),
        data_quality=data_quality if isinstance(data_quality, Mapping) else {},
        synthetic=loaded.get("synthetic") is True,
    )
    errors = event.invalid_reasons
    return EvidenceParseResult(valid=event.valid, event=event, errors=errors)


def serialize_evidence_events_jsonl(events: Sequence[EvidenceEvent]) -> str:
    return "\n".join(serialize_evidence_event(event) for event in events) + ("\n" if events else "")


def parse_evidence_events_jsonl(payload: str) -> EvidenceEventsParseResult:
    events: list[EvidenceEvent] = []
    errors: list[str] = []
    for index, line in enumerate(payload.splitlines(), start=1):
        if not line.strip():
            errors.append(f"line_{index}:blank_line")
            continue
        result = parse_evidence_event(line)
        if result.event is not None:
            events.append(result.event)
        if not result.valid:
            errors.extend(f"line_{index}:{error}" for error in result.errors)
    return EvidenceEventsParseResult(valid=not errors, events=tuple(events), errors=tuple(errors))


def build_replay_summary(
    events: Sequence[EvidenceEvent | Mapping[str, object]],
    *,
    contract: str,
    profile_id: str | None = None,
) -> ReplaySummary:
    normalized_contract = normalize_contract_symbol(contract)
    normalized_events, normalization_errors = _normalize_events(events)
    blocking: list[str] = list(normalization_errors)
    incomplete: list[str] = []

    if not is_final_target_contract(normalized_contract):
        blocking.append(f"replay_contract_not_final_supported:{normalized_contract}:{contract_policy_label(normalized_contract)}")

    timestamps: list[datetime] = []
    for event in normalized_events:
        if event.contract != normalized_contract:
            blocking.append(f"cross_contract_evidence:{event.contract}->{normalized_contract}")
        if event.synthetic:
            blocking.append(f"synthetic_evidence_not_replayable:{event.event_id}")
        if event.synthetic and event.source == "live_stream":
            blocking.append(f"synthetic_live_stream_evidence:{event.event_id}")
        parsed_timestamp = _parse_aware_datetime(event.timestamp)
        if parsed_timestamp is None:
            blocking.append(f"timestamp_invalid:{event.event_id}")
        else:
            timestamps.append(parsed_timestamp)
        if not event.valid:
            blocking.extend(f"invalid_event:{event.event_id}:{reason}" for reason in event.invalid_reasons)

    if any(current > nxt for current, nxt in zip(timestamps, timestamps[1:])):
        blocking.append("event_ordering_invalid")

    morning_plan_ref = _first_text(event.premarket_brief_ref for event in normalized_events)
    if morning_plan_ref is None:
        incomplete.append("premarket_brief_ref_missing")

    stream_events = tuple(event for event in normalized_events if event.event_type in _STREAM_EVENT_TYPES)
    if not stream_events:
        incomplete.append("stream_state_evidence_missing")

    trigger_events = tuple(event for event in normalized_events if event.event_type in _TRIGGER_EVENT_TYPES)
    if not trigger_events:
        incomplete.append("trigger_transition_evidence_missing")

    query_events = tuple(event for event in normalized_events if event.event_type == "query_submitted")
    pipeline_events = tuple(event for event in normalized_events if event.event_type == "pipeline_result")
    for event in pipeline_events:
        if not _has_prior_event(normalized_events, event, "query_submitted"):
            blocking.append(f"pipeline_result_without_prior_query_submitted:{event.event_id}")
    for event in query_events:
        if not _has_prior_query_ready_or_gate_enabled(normalized_events, event):
            blocking.append(f"query_submitted_without_query_ready_or_gate_enabled:{event.event_id}")

    stream_state = _stream_state(stream_events)
    trigger_transitions = tuple(_trigger_transition(event) for event in trigger_events)
    query_eligibility = tuple(_query_event(event) for event in normalized_events if _is_query_eligibility_event(event))
    pipeline_results = tuple(_pipeline_result(event) for event in pipeline_events)
    operator_notes = tuple(_operator_note(event) for event in normalized_events if event.event_type == "operator_note_added" and event.operator_note)
    cockpit_events = tuple(
        _cockpit_event(event)
        for event in normalized_events
        if event.event_type in _COCKPIT_EVENT_TYPES
    )
    manual_outcome = _manual_outcome(normalized_events)
    status = ReplayStatus.BLOCKED if blocking else ReplayStatus.INCOMPLETE if incomplete else ReplayStatus.COMPLETE
    return ReplaySummary(
        contract=normalized_contract,
        profile_id=_safe_optional(profile_id),
        status=status,
        complete=status == ReplayStatus.COMPLETE,
        morning_plan_reference=morning_plan_ref,
        stream_state=stream_state,
        trigger_transitions=trigger_transitions,
        query_eligibility_events=query_eligibility,
        pipeline_results=pipeline_results,
        operator_notes=operator_notes,
        cockpit_events=cockpit_events,
        post_session_manual_outcome=manual_outcome,
        blocking_reasons=_dedupe(blocking),
        incomplete_reasons=_dedupe(incomplete),
        source_integrity={
            "synthetic_replay_labeled_real": False,
            "fixture_labeled_live_stream": False,
            "live_stream_events": sum(1 for event in normalized_events if event.source == "live_stream"),
            "fixture_events": sum(1 for event in normalized_events if event.source == "fixture"),
            "manual_events": sum(1 for event in normalized_events if event.source == "manual"),
            "synthetic_events": sum(1 for event in normalized_events if event.synthetic),
        },
    )


def _normalize_events(events: Sequence[EvidenceEvent | Mapping[str, object]]) -> tuple[tuple[EvidenceEvent, ...], tuple[str, ...]]:
    normalized: list[EvidenceEvent] = []
    errors: list[str] = []
    for index, item in enumerate(events, start=1):
        if isinstance(item, EvidenceEvent):
            normalized.append(item)
            continue
        if isinstance(item, Mapping):
            result = parse_evidence_event(item)
            if result.event is not None:
                normalized.append(result.event)
            if not result.valid:
                errors.extend(f"event_{index}:{error}" for error in result.errors)
            continue
        errors.append(f"event_{index}:unsupported_event_payload")
    return tuple(normalized), tuple(errors)


def _stream_state(events: Sequence[EvidenceEvent]) -> dict[str, object]:
    state = "unavailable"
    quote_state = "unknown"
    subscription_count = 0
    blocking_reasons: list[str] = []
    for event in events:
        if event.event_type == "stream_connected":
            state = "connected"
        elif event.event_type == "stream_disconnected":
            state = "disconnected"
            blocking_reasons.append("stream_disconnected")
        elif event.event_type == "subscription_added":
            subscription_count += 1
        elif event.event_type == "quote_stale":
            quote_state = "stale"
            blocking_reasons.append("quote_stale")
        elif event.event_type == "quote_recovered":
            quote_state = "recovered"
    return {
        "state": state,
        "quote_state": quote_state,
        "subscription_count": subscription_count,
        "blocking_reasons": list(_dedupe(blocking_reasons)),
    }


def _trigger_transition(event: EvidenceEvent) -> dict[str, object]:
    return {
        "event_id": event.event_id,
        "timestamp": event.timestamp,
        "event_type": event.event_type,
        "setup_id": event.setup_id,
        "trigger_id": event.trigger_id,
        "trigger_state": event.data_quality.get("trigger_state") or _state_from_trigger_event(event.event_type),
        "source": event.source,
    }


def _query_event(event: EvidenceEvent) -> dict[str, object]:
    return {
        "event_id": event.event_id,
        "timestamp": event.timestamp,
        "event_type": event.event_type,
        "gate_enabled": event.data_quality.get("gate_enabled") is True or event.event_type == "trigger_query_ready",
        "manual_query_allowed": event.data_quality.get("manual_query_allowed") is True or event.event_type == "trigger_query_ready",
        "pipeline_run_id": event.pipeline_run_id,
        "source": event.source,
    }


def _pipeline_result(event: EvidenceEvent) -> dict[str, object]:
    return {
        "event_id": event.event_id,
        "timestamp": event.timestamp,
        "pipeline_run_id": event.pipeline_run_id,
        "summary": _pipeline_summary(event.data_quality.get("pipeline_summary") or event.data_quality),
        "source": event.source,
        "pipeline_result_source": "engine_derived_summary_only",
    }


def _operator_note(event: EvidenceEvent) -> dict[str, object]:
    return {
        "event_id": event.event_id,
        "timestamp": event.timestamp,
        "operator_note": event.operator_note,
        "source": event.source,
    }


_COCKPIT_EVENT_TYPES: Final[tuple[str, ...]] = (
    "readiness_snapshot_observed",
    "query_blocked",
    "cockpit_refreshed",
    "cockpit_reset",
    "latest_action_state_changed",
)


def _cockpit_event(event: EvidenceEvent) -> dict[str, object]:
    return {
        "event_id": event.event_id,
        "timestamp": event.timestamp,
        "event_type": event.event_type,
        "contract": event.contract,
        "source": event.source,
        "source_surface": event.data_quality.get("source_surface"),
        "status": event.data_quality.get("status"),
        "request_status": event.data_quality.get("request_status"),
        "query_action_state": event.data_quality.get("query_action_state"),
        "reason": event.data_quality.get("reason"),
        "summary": event.data_quality.get("summary"),
        "runtime_readiness_status": event.data_quality.get("runtime_readiness_status"),
        "runtime_readiness_preserved": event.data_quality.get("runtime_readiness_preserved") is True,
        "replay_safety_classification": event.data_quality.get(
            "replay_safety_classification"
        ),
        "creates_query_ready": event.data_quality.get("creates_query_ready") is True,
        "replay_can_authorize_trades": event.data_quality.get(
            "replay_can_authorize_trades"
        )
        is True,
    }


def _manual_outcome(events: Sequence[EvidenceEvent]) -> dict[str, object]:
    for event in events:
        if event.source == "manual" and event.data_quality.get("manual_outcome") is not None:
            return {
                "status": "entered_manually",
                "event_id": event.event_id,
                "value": _safe_text(event.data_quality.get("manual_outcome")),
            }
    return {"status": "not_entered", "reason": "No post-session manual outcome was supplied."}


def _is_query_eligibility_event(event: EvidenceEvent) -> bool:
    return event.event_type in {"trigger_query_ready", "query_submitted"} or event.data_quality.get("gate_enabled") is True


def _has_prior_event(events: Sequence[EvidenceEvent], target: EvidenceEvent, event_type: str) -> bool:
    for event in events:
        if event.event_id == target.event_id:
            return False
        if event.event_type == event_type:
            return True
    return False


def _has_prior_query_ready_or_gate_enabled(events: Sequence[EvidenceEvent], target: EvidenceEvent) -> bool:
    for event in events:
        if event.event_id == target.event_id:
            return False
        if event.event_type == "trigger_query_ready" or event.data_quality.get("gate_enabled") is True:
            return True
    return False


def _state_from_trigger_event(event_type: str) -> str:
    return {
        "trigger_approaching": "APPROACHING",
        "trigger_touched": "TOUCHED",
        "trigger_armed": "ARMED",
        "trigger_query_ready": "QUERY_READY",
        "trigger_invalidated": "INVALIDATED",
    }.get(event_type, "UNAVAILABLE")


def _pipeline_summary(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    return {key: _safe_json(value[key]) for key in _PIPELINE_SUMMARY_KEYS if key in value}


def _safe_data_quality(data_quality: Mapping[str, object]) -> dict[str, object]:
    safe: dict[str, object] = {}
    for key, value in data_quality.items():
        safe_key = _safe_text(key).strip()
        if safe_key not in _SAFE_DATA_QUALITY_KEYS:
            continue
        if safe_key == "pipeline_summary":
            safe[safe_key] = _pipeline_summary(value)
        else:
            safe[safe_key] = _safe_json(value)
    return safe


def _safe_json(value: object) -> object:
    if isinstance(value, str):
        return _safe_text(value)
    if value is None or isinstance(value, int | float | bool):
        return value
    if isinstance(value, Mapping):
        return {str(_safe_text(key)): _safe_json(item) for key, item in value.items() if _safe_text(key) in _SAFE_DATA_QUALITY_KEYS or _safe_text(key) in _PIPELINE_SUMMARY_KEYS}
    if isinstance(value, Sequence) and not isinstance(value, bytes):
        return [_safe_json(item) for item in value]
    return _safe_text(value)


def _parse_aware_datetime(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


def _is_timezone_aware_iso(value: str) -> bool:
    return _parse_aware_datetime(value) is not None


def _first_text(values: Sequence[str | None]) -> str | None:
    for value in values:
        if value:
            return value
    return None


def _string_field(value: object) -> str:
    return "" if value is None else str(value)


def _optional_string_field(value: object) -> str | None:
    return None if value is None else str(value)


def _safe_optional(value: object) -> str | None:
    if value is None:
        return None
    text = _safe_text(value).strip()
    return text or None


def _safe_optional_ref(value: object) -> str | None:
    if value is None:
        return None
    text = _safe_ref(value).strip()
    return text or None


def _safe_ref(value: object) -> str:
    text = str(value).strip()
    lowered = text.lower()
    if _SAFE_REF_RE.fullmatch(text) and not any(term in lowered for term in _SENSITIVE_REF_TERMS):
        return text
    return _safe_text(text)


def _safe_text(value: object) -> str:
    return redact_sensitive_text(value).strip()


def _dedupe(values: Sequence[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = _safe_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return tuple(result)
