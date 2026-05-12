from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from ntb_marimo_console.contract_universe import normalize_contract_symbol
from ntb_marimo_console.evidence_replay import EvidenceEvent, ReplaySummary, build_replay_summary, create_evidence_event
from ntb_marimo_console.market_data.stream_cache import StreamCacheRecord
from ntb_marimo_console.market_data.stream_events import StreamEvent
from ntb_marimo_console.market_data.stream_manager import StreamManagerSnapshot
from ntb_marimo_console.pipeline_query_gate import PipelineQueryGateResult
from ntb_marimo_console.trigger_state import TriggerState, TriggerStateResult


class CockpitEvidenceEventType(StrEnum):
    STREAM_CONNECTED = "stream_connected"
    STREAM_DISCONNECTED = "stream_disconnected"
    SUBSCRIPTION_ADDED = "subscription_added"
    QUOTE_STALE = "quote_stale"
    QUOTE_RECOVERED = "quote_recovered"
    BAR_CLOSED = "bar_closed"
    TRIGGER_APPROACHING = "trigger_approaching"
    TRIGGER_TOUCHED = "trigger_touched"
    TRIGGER_ARMED = "trigger_armed"
    TRIGGER_QUERY_READY = "trigger_query_ready"
    TRIGGER_INVALIDATED = "trigger_invalidated"
    QUERY_SUBMITTED = "query_submitted"
    PIPELINE_RESULT = "pipeline_result"
    OPERATOR_NOTE_ADDED = "operator_note_added"
    SESSION_RESET = "session_reset"


_TRIGGER_EVENT_TYPES = frozenset(
    {
        CockpitEvidenceEventType.TRIGGER_APPROACHING.value,
        CockpitEvidenceEventType.TRIGGER_TOUCHED.value,
        CockpitEvidenceEventType.TRIGGER_ARMED.value,
        CockpitEvidenceEventType.TRIGGER_QUERY_READY.value,
        CockpitEvidenceEventType.TRIGGER_INVALIDATED.value,
    }
)


@dataclass(frozen=True)
class CockpitEvidenceRecord:
    contract: str
    profile_id: str
    event_type: CockpitEvidenceEventType
    timestamp: str
    source: str
    setup_id: str | None = None
    trigger_id: str | None = None
    live_snapshot_ref: str | None = None
    premarket_brief_ref: str | None = None
    pipeline_run_id: str | None = None
    operator_note: str | None = None
    data_quality: Mapping[str, object] = field(default_factory=dict)
    synthetic: bool = False

    def to_evidence_event(self) -> EvidenceEvent:
        return create_evidence_event(
            contract=self.contract,
            profile_id=self.profile_id,
            event_id=_event_id(
                self.contract,
                self.profile_id,
                self.event_type.value,
                self.timestamp,
                self.setup_id,
                self.trigger_id,
                self.pipeline_run_id,
            ),
            timestamp=self.timestamp,
            event_type=self.event_type.value,
            source=self.source,
            setup_id=self.setup_id,
            trigger_id=self.trigger_id,
            live_snapshot_ref=self.live_snapshot_ref,
            premarket_brief_ref=self.premarket_brief_ref,
            pipeline_run_id=self.pipeline_run_id,
            operator_note=self.operator_note,
            data_quality=self.data_quality,
            synthetic=self.synthetic,
        )


@dataclass
class CockpitEventReplaySource:
    """App-owned cockpit evidence source for review-only replay surfaces."""

    source: str
    _events: list[EvidenceEvent] = field(default_factory=list)
    _event_ids: set[str] = field(default_factory=set)
    _stale_contracts: set[tuple[str, str]] = field(default_factory=set)

    @property
    def events(self) -> tuple[EvidenceEvent, ...]:
        return tuple(self._events)

    def append_records(self, records: Sequence[CockpitEvidenceRecord]) -> tuple[EvidenceEvent, ...]:
        emitted: list[EvidenceEvent] = []
        for record in records:
            if record.event_type.value in _TRIGGER_EVENT_TYPES:
                continue
            event = record.to_evidence_event()
            if self._append_event(event):
                emitted.append(event)
        self._events.sort(key=lambda item: (item.timestamp, item.contract, item.profile_id, item.event_id))
        return tuple(emitted)

    def append_trigger_transition_events(self, events: Sequence[EvidenceEvent]) -> tuple[EvidenceEvent, ...]:
        emitted: list[EvidenceEvent] = []
        for event in events:
            if not isinstance(event, EvidenceEvent):
                continue
            if event.event_type not in _TRIGGER_EVENT_TYPES:
                continue
            if self._append_event(event):
                emitted.append(event)
        self._events.sort(key=lambda item: (item.timestamp, item.contract, item.profile_id, item.event_id))
        return tuple(emitted)

    def _append_event(self, event: EvidenceEvent) -> bool:
        if event.event_id in self._event_ids:
            return False
        self._event_ids.add(event.event_id)
        self._events.append(event)
        return True

    def observe_stream_snapshot(
        self,
        snapshot: StreamManagerSnapshot,
        *,
        profile_id: str,
        premarket_brief_ref: str | None = None,
    ) -> tuple[EvidenceEvent, ...]:
        if not isinstance(snapshot, StreamManagerSnapshot):
            raise TypeError("observe_stream_snapshot requires a StreamManagerSnapshot")
        contracts = tuple(
            normalize_contract_symbol(contract)
            for contract in snapshot.config.contracts_requested
            if str(contract).strip()
        )
        records = tuple(snapshot.cache.records)
        records_by_contract = {record.contract: record for record in records}
        emitted_records: list[CockpitEvidenceRecord] = []
        for index, event in enumerate(snapshot.events, start=1):
            emitted_records.extend(
                _records_from_stream_event(
                    event,
                    contracts=contracts,
                    profile_id=profile_id,
                    source=self.source,
                    event_index=index,
                    premarket_brief_ref=premarket_brief_ref,
                )
            )

        for record in records:
            if record.message_type == "bar" and record.fresh:
                emitted_records.append(
                    CockpitEvidenceRecord(
                        contract=record.contract,
                        profile_id=profile_id,
                        event_type=CockpitEvidenceEventType.BAR_CLOSED,
                        timestamp=record.updated_at,
                        source=self.source,
                        premarket_brief_ref=premarket_brief_ref,
                        data_quality={"status": "bar_closed", "fresh": True},
                    )
                )

        stale_contracts = _stale_contracts(snapshot, records_by_contract)
        for contract in stale_contracts:
            self._stale_contracts.add((profile_id, contract))
            record = records_by_contract.get(contract)
            emitted_records.append(
                CockpitEvidenceRecord(
                    contract=contract,
                    profile_id=profile_id,
                    event_type=CockpitEvidenceEventType.QUOTE_STALE,
                    timestamp=record.updated_at if record is not None else snapshot.cache.generated_at,
                    source=self.source,
                    premarket_brief_ref=premarket_brief_ref,
                    data_quality={"status": "stale", "fresh": False},
                )
            )

        recovered = tuple(
            key_contract
            for key_profile, key_contract in sorted(self._stale_contracts)
            if key_profile == profile_id and key_contract in records_by_contract and records_by_contract[key_contract].fresh
        )
        if snapshot.state == "active" and snapshot.cache.provider_status == "active":
            for contract in recovered:
                self._stale_contracts.discard((profile_id, contract))
                emitted_records.append(
                    CockpitEvidenceRecord(
                        contract=contract,
                        profile_id=profile_id,
                        event_type=CockpitEvidenceEventType.QUOTE_RECOVERED,
                        timestamp=records_by_contract[contract].updated_at,
                        source=self.source,
                        premarket_brief_ref=premarket_brief_ref,
                        data_quality={"status": "recovered", "fresh": True},
                    )
                )
        return self.append_records(tuple(emitted_records))

    def observe_query_submission(
        self,
        *,
        gate: PipelineQueryGateResult,
        trigger_state: TriggerStateResult,
        timestamp: str,
        pipeline_run_id: str,
        premarket_brief_ref: str | None = None,
        live_snapshot_ref: str | None = None,
    ) -> tuple[EvidenceEvent, ...]:
        if not isinstance(gate, PipelineQueryGateResult) or not isinstance(trigger_state, TriggerStateResult):
            return ()
        if not gate.enabled or not gate.trigger_state_from_real_producer:
            return ()
        if trigger_state.state != TriggerState.QUERY_READY:
            return ()
        if normalize_contract_symbol(gate.contract) != normalize_contract_symbol(trigger_state.contract):
            return ()
        return self.append_records(
            (
                CockpitEvidenceRecord(
                    contract=trigger_state.contract,
                    profile_id=gate.profile_id or "",
                    event_type=CockpitEvidenceEventType.QUERY_SUBMITTED,
                    timestamp=timestamp,
                    source=self.source,
                    setup_id=trigger_state.setup_id,
                    trigger_id=trigger_state.trigger_id,
                    live_snapshot_ref=live_snapshot_ref,
                    premarket_brief_ref=premarket_brief_ref,
                    pipeline_run_id=pipeline_run_id,
                    data_quality={"gate_enabled": True, "manual_query_allowed": True},
                ),
            )
        )

    def observe_pipeline_result(
        self,
        *,
        contract: str,
        profile_id: str,
        timestamp: str,
        pipeline_run_id: str,
        pipeline_summary: Mapping[str, object],
        premarket_brief_ref: str | None = None,
    ) -> tuple[EvidenceEvent, ...]:
        summary_contract = pipeline_summary.get("contract")
        if summary_contract is not None and normalize_contract_symbol(summary_contract) != normalize_contract_symbol(contract):
            return ()
        return self.append_records(
            (
                CockpitEvidenceRecord(
                    contract=contract,
                    profile_id=profile_id,
                    event_type=CockpitEvidenceEventType.PIPELINE_RESULT,
                    timestamp=timestamp,
                    source=self.source,
                    premarket_brief_ref=premarket_brief_ref,
                    pipeline_run_id=pipeline_run_id,
                    data_quality={"pipeline_summary": dict(pipeline_summary)},
                ),
            )
        )

    def observe_operator_note(
        self,
        *,
        contract: str,
        profile_id: str,
        timestamp: str,
        operator_note: str,
        premarket_brief_ref: str | None = None,
    ) -> tuple[EvidenceEvent, ...]:
        if not operator_note.strip():
            return ()
        return self.append_records(
            (
                CockpitEvidenceRecord(
                    contract=contract,
                    profile_id=profile_id,
                    event_type=CockpitEvidenceEventType.OPERATOR_NOTE_ADDED,
                    timestamp=timestamp,
                    source="manual",
                    premarket_brief_ref=premarket_brief_ref,
                    operator_note=operator_note,
                ),
            )
        )

    def observe_session_reset(
        self,
        *,
        contract: str,
        profile_id: str,
        timestamp: str,
        premarket_brief_ref: str | None = None,
    ) -> tuple[EvidenceEvent, ...]:
        return self.append_records(
            (
                CockpitEvidenceRecord(
                    contract=contract,
                    profile_id=profile_id,
                    event_type=CockpitEvidenceEventType.SESSION_RESET,
                    timestamp=timestamp,
                    source=self.source,
                    premarket_brief_ref=premarket_brief_ref,
                    data_quality={"status": "session_reset"},
                ),
            )
        )

    def replay_summary(self, *, contract: str, profile_id: str | None = None) -> ReplaySummary | None:
        contract_key = normalize_contract_symbol(contract)
        profile_key = _text_or_none(profile_id)
        events = tuple(
            event
            for event in self._events
            if event.contract == contract_key and (profile_key is None or event.profile_id == profile_key)
        )
        if not events:
            return None
        return build_replay_summary(events, contract=contract_key, profile_id=profile_key)

    def replay_log(self, *, contract: str, profile_id: str | None = None) -> dict[str, object] | None:
        summary = self.replay_summary(contract=contract, profile_id=profile_id)
        return None if summary is None else summary.to_dict()


def _records_from_stream_event(
    event: StreamEvent,
    *,
    contracts: Sequence[str],
    profile_id: str,
    source: str,
    event_index: int,
    premarket_brief_ref: str | None,
) -> tuple[CockpitEvidenceRecord, ...]:
    event_type = _stream_event_type(event)
    if event_type is None:
        return ()
    records: list[CockpitEvidenceRecord] = []
    for contract in contracts:
        records.append(
            CockpitEvidenceRecord(
                contract=contract,
                profile_id=profile_id,
                event_type=event_type,
                timestamp=event.generated_at,
                source=source,
                premarket_brief_ref=premarket_brief_ref,
                data_quality={
                    "status": event.state,
                    "blocking_reasons": [event.blocking_reason] if event.blocking_reason else [],
                    "pipeline_summary": {"contract": contract},
                    "event_index": event_index,
                },
            )
        )
    return tuple(records)


def _stream_event_type(event: StreamEvent) -> CockpitEvidenceEventType | None:
    if event.event_type == "login_succeeded":
        return CockpitEvidenceEventType.STREAM_CONNECTED
    if event.event_type in {"connection_lost", "shutdown_completed"}:
        return CockpitEvidenceEventType.STREAM_DISCONNECTED
    if event.event_type == "subscription_succeeded":
        return CockpitEvidenceEventType.SUBSCRIPTION_ADDED
    if event.event_type == "heartbeat_stale":
        return CockpitEvidenceEventType.QUOTE_STALE
    return None


def _stale_contracts(
    snapshot: StreamManagerSnapshot,
    records_by_contract: Mapping[str, StreamCacheRecord],
) -> tuple[str, ...]:
    stale_symbols = {str(symbol).strip().upper() for symbol in snapshot.cache.stale_symbols if str(symbol).strip()}
    stale: set[str] = set()
    for contract, record in records_by_contract.items():
        if not record.fresh or record.symbol in stale_symbols or record.blocking_reasons:
            stale.add(contract)
    if snapshot.cache.provider_status == "stale":
        stale.update(records_by_contract)
    return tuple(sorted(stale))


def _event_id(
    contract: object,
    profile_id: object,
    event_type: object,
    timestamp: object,
    setup_id: object,
    trigger_id: object,
    pipeline_run_id: object,
) -> str:
    return "-".join(
        _event_id_component(part)
        for part in (
            "cockpit",
            contract,
            profile_id,
            event_type,
            setup_id or "setup-unavailable",
            trigger_id or "trigger-unavailable",
            pipeline_run_id or "run-unavailable",
            timestamp,
        )
    )


def _event_id_component(value: object) -> str:
    text = str(value).strip().lower()
    return re.sub(r"[^A-Za-z0-9_.=-]+", "-", text).strip("-") or "unknown"


def _text_or_none(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


__all__ = [
    "CockpitEventReplaySource",
    "CockpitEvidenceEventType",
    "CockpitEvidenceRecord",
]
