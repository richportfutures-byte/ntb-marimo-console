from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, NamedTuple

from ntb_marimo_console.contract_universe import normalize_contract_symbol
from ntb_marimo_console.evidence_replay import EvidenceEvent, ReplaySummary, build_replay_summary
from ntb_marimo_console.trigger_state import TriggerStateResult
from ntb_marimo_console.trigger_transition_evidence import build_trigger_transition_evidence_events


class TriggerTransitionObservationKey(NamedTuple):
    contract: str
    profile_id: str | None
    setup_id: str | None
    trigger_id: str | None


@dataclass
class TriggerTransitionReplaySource:
    """In-memory source for replay evidence from observed trigger-state changes."""

    source: str
    _previous_by_key: dict[TriggerTransitionObservationKey, dict[str, Any]] = field(default_factory=dict)
    _events: list[EvidenceEvent] = field(default_factory=list)

    @property
    def events(self) -> tuple[EvidenceEvent, ...]:
        return tuple(self._events)

    def observe(
        self,
        current: TriggerStateResult | Mapping[str, Any],
        *,
        timestamp: str,
        profile_id: str,
        live_snapshot_ref: str | None = None,
        premarket_brief_ref: str | None = None,
    ) -> tuple[EvidenceEvent, ...]:
        current_payload = _payload(current)
        safe_profile_id = _text_or_none(profile_id)
        key = _observation_key(current_payload, profile_id=safe_profile_id)
        if key is None:
            return ()

        previous_payload = self._previous_by_key.get(key)
        emitted = build_trigger_transition_evidence_events(
            previous_payload,
            current_payload,
            timestamp=timestamp,
            profile_id=safe_profile_id or "",
            source=self.source,
            live_snapshot_ref=live_snapshot_ref,
            premarket_brief_ref=premarket_brief_ref,
        )
        self._previous_by_key[key] = dict(current_payload)
        self._events.extend(emitted)
        return emitted

    def replay_summary(
        self,
        *,
        contract: str,
        profile_id: str | None = None,
    ) -> ReplaySummary | None:
        contract_key = normalize_contract_symbol(contract)
        safe_profile_id = _text_or_none(profile_id)
        events = tuple(
            event
            for event in self._events
            if event.contract == contract_key
            and (safe_profile_id is None or event.profile_id == safe_profile_id)
        )
        if not events:
            return None
        return build_replay_summary(events, contract=contract_key, profile_id=safe_profile_id)

    def trigger_transition_log(
        self,
        *,
        contract: str,
        profile_id: str | None = None,
    ) -> dict[str, object] | None:
        summary = self.replay_summary(contract=contract, profile_id=profile_id)
        if summary is None:
            return None
        return summary.to_dict()


def _payload(value: TriggerStateResult | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(value, TriggerStateResult):
        return value.to_dict()
    return dict(value)


def _observation_key(
    payload: Mapping[str, Any],
    *,
    profile_id: str | None,
) -> TriggerTransitionObservationKey | None:
    contract = _text_or_none(payload.get("contract"))
    if contract is None:
        return None
    return TriggerTransitionObservationKey(
        contract=normalize_contract_symbol(contract),
        profile_id=profile_id,
        setup_id=_text_or_none(payload.get("setup_id")),
        trigger_id=_text_or_none(payload.get("trigger_id")),
    )


def _text_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
