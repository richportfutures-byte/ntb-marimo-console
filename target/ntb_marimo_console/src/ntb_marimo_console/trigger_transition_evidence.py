from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, Final

from ntb_marimo_console.evidence_replay import EvidenceEvent, create_evidence_event
from ntb_marimo_console.trigger_state import TriggerState, TriggerStateResult


_TRIGGER_TRANSITION_EVENT_TYPES: Final[dict[TriggerState, str]] = {
    TriggerState.APPROACHING: "trigger_approaching",
    TriggerState.TOUCHED: "trigger_touched",
    TriggerState.ARMED: "trigger_armed",
    TriggerState.QUERY_READY: "trigger_query_ready",
    TriggerState.INVALIDATED: "trigger_invalidated",
}
_EVENT_ID_COMPONENT_RE: Final[re.Pattern[str]] = re.compile(r"[^A-Za-z0-9_.=-]+")


def build_trigger_transition_evidence_events(
    previous: TriggerStateResult | Mapping[str, Any] | None,
    current: TriggerStateResult | Mapping[str, Any],
    *,
    timestamp: str,
    profile_id: str,
    source: str,
    live_snapshot_ref: str | None = None,
    premarket_brief_ref: str | None = None,
    event_id: str | None = None,
) -> tuple[EvidenceEvent, ...]:
    """Build evidence only for an observed material trigger-state transition."""
    previous_payload = _payload(previous)
    current_payload = _payload(current)
    current_state = _state_from_payload(current_payload)
    if current_state not in _TRIGGER_TRANSITION_EVENT_TYPES:
        return ()
    if not previous_payload:
        return ()

    previous_state = _state_from_payload(previous_payload)
    if previous_state == current_state:
        return ()

    current_contract = _text_or_none(current_payload.get("contract"))
    if current_contract is None:
        return ()
    previous_contract = _text_or_none(previous_payload.get("contract"))
    if previous_contract is not None and previous_contract.upper() != current_contract.upper():
        return ()
    if not str(profile_id).strip():
        return ()

    event_type = _TRIGGER_TRANSITION_EVENT_TYPES[current_state]
    event = create_evidence_event(
        contract=current_contract,
        profile_id=profile_id,
        event_id=event_id
        or _deterministic_event_id(
            current_contract,
            previous_state=previous_state,
            current_state=current_state,
            setup_id=_text_or_none(current_payload.get("setup_id")),
            trigger_id=_text_or_none(current_payload.get("trigger_id")),
            timestamp=timestamp,
            source=source,
        ),
        timestamp=timestamp,
        event_type=event_type,
        source=source,
        setup_id=_text_or_none(current_payload.get("setup_id")),
        trigger_id=_text_or_none(current_payload.get("trigger_id")),
        live_snapshot_ref=live_snapshot_ref,
        premarket_brief_ref=premarket_brief_ref,
        data_quality={
            "state": current_state.value,
            "trigger_state": current_state.value,
            "blocking_reasons": list(_text_sequence(current_payload.get("blocking_reasons"))),
            "missing_conditions": list(_text_sequence(current_payload.get("missing_fields"))),
        },
    )
    return (event,)


def _payload(value: TriggerStateResult | Mapping[str, Any] | None) -> dict[str, Any]:
    if isinstance(value, TriggerStateResult):
        return value.to_dict()
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def _state_from_payload(payload: Mapping[str, Any]) -> TriggerState | None:
    value = payload.get("state") or payload.get("trigger_state")
    if isinstance(value, TriggerState):
        return value
    if value is None:
        return None
    try:
        return TriggerState(str(value).strip().upper())
    except ValueError:
        return None


def _text_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _text_sequence(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return ()
    return tuple(str(item).strip() for item in value if str(item).strip())


def _deterministic_event_id(
    contract: str,
    *,
    previous_state: TriggerState | None,
    current_state: TriggerState,
    setup_id: str | None,
    trigger_id: str | None,
    timestamp: str,
    source: str,
) -> str:
    parts = (
        "trigger-transition",
        contract.lower(),
        setup_id or "setup-unavailable",
        trigger_id or "trigger-unavailable",
        (previous_state.value.lower() if previous_state else "unknown"),
        "to",
        current_state.value.lower(),
        timestamp,
        source,
    )
    return "-".join(_event_id_component(part) for part in parts)


def _event_id_component(value: object) -> str:
    text = str(value).strip().lower()
    return _replace_event_id_component(text)


def _replace_event_id_component(text: str) -> str:
    return _EVENT_ID_COMPONENT_RE.sub("-", text).strip("-") or "unknown"
