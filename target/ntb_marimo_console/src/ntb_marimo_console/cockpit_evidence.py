from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Final

from .cockpit_manual_query import CockpitManualQueryResult
from .contract_universe import final_target_contracts, is_final_target_contract, normalize_contract_symbol
from .evidence_replay import EvidenceEvent, build_replay_summary, create_evidence_event
from .primary_cockpit import primary_cockpit_surface_key


COCKPIT_EVENT_REPLAY_SURFACE_SCHEMA: Final[str] = "cockpit_event_replay_surface_v1"
COCKPIT_EVIDENCE_MAX_EVENTS: Final[int] = 50
COCKPIT_REPLAY_SAFETY_CLASSIFICATION: Final[str] = (
    "review_only_non_authoritative_non_signal"
)


def build_cockpit_event_replay_surface(
    events: Sequence[EvidenceEvent],
    *,
    active_profile_id: str | None = None,
    max_events: int = COCKPIT_EVIDENCE_MAX_EVENTS,
) -> dict[str, object]:
    bounded_events = tuple(events)[-max_events:]
    per_contract: dict[str, object] = {}
    if bounded_events:
        for contract in final_target_contracts():
            contract_events = tuple(
                event for event in bounded_events if event.contract == contract
            )
            per_contract[contract] = build_replay_summary(
                contract_events,
                contract=contract,
                profile_id=_profile_id_for_contract(
                    contract,
                    active_profile_id=active_profile_id,
                ),
            ).to_dict()
    return {
        "schema": COCKPIT_EVENT_REPLAY_SURFACE_SCHEMA,
        "event_count": len(bounded_events),
        "max_events": max_events,
        "supported_contracts": list(final_target_contracts()),
        "excluded_contracts": ["ZN", "GC"],
        "records": [event.to_dict() for event in bounded_events],
        "per_contract_replays": per_contract,
        "replay_safety_classification": COCKPIT_REPLAY_SAFETY_CLASSIFICATION,
        "replay_can_authorize_trades": False,
        "evidence_can_create_query_ready": False,
        "manual_query_only": True,
        "manual_execution_only": True,
        "raw_quote_values_included": False,
        "raw_bar_values_included": False,
        "raw_streamer_payloads_included": False,
    }


def append_cockpit_evidence_events(
    history: Sequence[EvidenceEvent],
    new_events: Sequence[EvidenceEvent],
    *,
    max_events: int = COCKPIT_EVIDENCE_MAX_EVENTS,
) -> tuple[EvidenceEvent, ...]:
    updated = tuple(history) + tuple(new_events)
    if max_events > 0 and len(updated) > max_events:
        updated = updated[-max_events:]
    return updated


def cockpit_readiness_snapshot_events(
    surface: Mapping[str, object],
    *,
    timestamp: str,
    sequence: int,
    source_surface: str = "current_state",
    active_profile_id: str | None = None,
) -> tuple[EvidenceEvent, ...]:
    rows = surface.get("rows")
    row_maps = [row for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []
    rows_by_contract = {
        normalize_contract_symbol(str(row.get("contract") or "")): row
        for row in row_maps
        if _optional_text(row.get("contract"))
    }
    return tuple(
        _readiness_snapshot_event(
            contract=contract,
            row=rows_by_contract.get(contract),
            timestamp=timestamp,
            sequence=sequence,
            source_surface=source_surface,
            active_profile_id=active_profile_id,
        )
        for contract in final_target_contracts()
    )


def cockpit_manual_query_evidence_events(
    *,
    result: CockpitManualQueryResult,
    surface: Mapping[str, object],
    timestamp: str,
    sequence: int,
    active_profile_id: str | None = None,
) -> tuple[EvidenceEvent, ...]:
    contract = normalize_contract_symbol(result.contract)
    if not is_final_target_contract(contract):
        return tuple()
    events: list[EvidenceEvent] = []
    if result.submitted and result.request_status == "SUBMITTED":
        events.append(
            _readiness_snapshot_event(
                contract=contract,
                row=_row_for_contract(surface, contract),
                timestamp=timestamp,
                sequence=sequence,
                source_surface="manual_query",
                active_profile_id=active_profile_id,
            )
        )
        events.append(
            _event(
                event_type="query_submitted",
                contract=contract,
                timestamp=timestamp,
                sequence=sequence,
                source_surface="manual_query",
                active_profile_id=active_profile_id,
                pipeline_run_id=result.attempted_action,
                data_quality={
                    "status": "submitted",
                    "request_status": result.request_status,
                    "gate_enabled": True,
                    "manual_query_allowed": True,
                    "query_action_state": result.query_action_state,
                    "summary": result.operator_feedback_text,
                },
            )
        )
        events.append(
            _event(
                event_type="pipeline_result",
                contract=contract,
                timestamp=timestamp,
                sequence=sequence,
                source_surface="manual_query",
                active_profile_id=active_profile_id,
                pipeline_run_id=result.attempted_action,
                data_quality={
                    "status": result.pipeline_result_status,
                    "request_status": result.request_status,
                    "summary": result.bounded_result_summary,
                    "pipeline_summary": {
                        "contract": contract,
                        "termination_stage": result.stage_termination_reason,
                        "final_decision": result.terminal_summary,
                    },
                },
            )
        )
    else:
        events.append(
            _event(
                event_type="query_blocked",
                contract=contract,
                timestamp=timestamp,
                sequence=sequence,
                source_surface="manual_query",
                active_profile_id=active_profile_id,
                pipeline_run_id=result.attempted_action,
                data_quality={
                    "status": "blocked",
                    "request_status": result.request_status,
                    "gate_enabled": False,
                    "manual_query_allowed": False,
                    "query_action_state": result.query_action_state,
                    "reason": result.blocked_reason,
                    "summary": result.operator_feedback_text,
                },
            )
        )
    events.append(
        _latest_action_event(
            contract=contract,
            timestamp=timestamp,
            sequence=sequence,
            source_surface="action_timeline",
            active_profile_id=active_profile_id,
            action_status=result.request_status,
            summary=result.operator_feedback_text,
            reason=result.blocked_reason,
            query_action_state=result.query_action_state,
        )
    )
    return tuple(events)


def cockpit_operator_note_evidence_event(
    *,
    contract: str | None,
    text: str,
    timestamp: str,
    sequence: int,
    active_profile_id: str | None = None,
) -> EvidenceEvent:
    normalized = _normalized_or_active_contract(contract, active_profile_id)
    return _event(
        event_type="operator_note_added",
        contract=normalized,
        timestamp=timestamp,
        sequence=sequence,
        source_surface="operator_notes",
        active_profile_id=active_profile_id,
        operator_note=text,
        data_quality={
            "status": "recorded",
            "summary": "Operator note recorded for replay review only.",
        },
    )


def cockpit_lifecycle_evidence_events(
    *,
    event_type: str,
    surface: Mapping[str, object],
    timestamp: str,
    sequence: int,
    action_status: str,
    summary: str,
    active_profile_id: str | None = None,
) -> tuple[EvidenceEvent, ...]:
    events: list[EvidenceEvent] = list(
        cockpit_readiness_snapshot_events(
            surface,
            timestamp=timestamp,
            sequence=sequence,
            source_surface="current_state",
            active_profile_id=active_profile_id,
        )
    )
    for contract in final_target_contracts():
        events.append(
            _event(
                event_type=event_type,
                contract=contract,
                timestamp=timestamp,
                sequence=sequence,
                source_surface="session_lifecycle",
                active_profile_id=active_profile_id,
                data_quality={
                    "status": action_status,
                    "summary": summary,
                },
            )
        )
        events.append(
            _latest_action_event(
                contract=contract,
                timestamp=timestamp,
                sequence=sequence,
                source_surface="action_timeline",
                active_profile_id=active_profile_id,
                action_status=action_status,
                summary=summary,
            )
        )
    return tuple(events)


def cockpit_evidence_timestamp(
    shell: Mapping[str, object],
    *,
    fallback: str | None = None,
) -> str:
    surfaces = shell.get("surfaces")
    if isinstance(surfaces, Mapping):
        cockpit = surfaces.get(primary_cockpit_surface_key(shell))
        if isinstance(cockpit, Mapping):
            generated = _optional_text(cockpit.get("generated_at"))
            if generated:
                return generated
    runtime = shell.get("runtime")
    if isinstance(runtime, Mapping):
        generated = _optional_text(runtime.get("operator_live_runtime_cache_generated_at"))
        if generated:
            return generated
    if fallback:
        return fallback
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _readiness_snapshot_event(
    *,
    contract: str,
    row: Mapping[str, object] | None,
    timestamp: str,
    sequence: int,
    source_surface: str,
    active_profile_id: str | None,
) -> EvidenceEvent:
    row_map = row or {}
    query_state = _optional_text(row_map.get("query_action_state")) or "DISABLED"
    enabled = row_map.get("query_enabled") is True and query_state == "ENABLED"
    reason = (
        _optional_text(row_map.get("query_disabled_reason"))
        or _optional_text(row_map.get("query_reason"))
    )
    status = "enabled" if enabled else "blocked"
    return _event(
        event_type="readiness_snapshot_observed",
        contract=contract,
        timestamp=timestamp,
        sequence=sequence,
        source_surface=source_surface,
        active_profile_id=active_profile_id,
        data_quality={
            "status": status,
            "state": status,
            "ready": enabled,
            "gate_enabled": enabled,
            "manual_query_allowed": enabled,
            "query_action_state": query_state,
            "reason": reason,
            "blocking_reasons": _blocking_reasons(row_map, reason),
            "summary": (
                f"{contract} manual-query gate observed as {status} "
                "from existing cockpit state."
            ),
        },
    )


def _latest_action_event(
    *,
    contract: str,
    timestamp: str,
    sequence: int,
    source_surface: str,
    active_profile_id: str | None,
    action_status: str,
    summary: str,
    reason: str | None = None,
    query_action_state: str | None = None,
) -> EvidenceEvent:
    return _event(
        event_type="latest_action_state_changed",
        contract=contract,
        timestamp=timestamp,
        sequence=sequence,
        source_surface=source_surface,
        active_profile_id=active_profile_id,
        data_quality={
            "status": action_status,
            "request_status": action_status,
            "query_action_state": query_action_state,
            "reason": reason,
            "summary": summary,
        },
    )


def _event(
    *,
    event_type: str,
    contract: str,
    timestamp: str,
    sequence: int,
    source_surface: str,
    active_profile_id: str | None,
    data_quality: Mapping[str, object],
    pipeline_run_id: str | None = None,
    operator_note: str | None = None,
) -> EvidenceEvent:
    normalized = normalize_contract_symbol(contract)
    enriched = dict(data_quality)
    enriched.update(
        {
            "source_surface": source_surface,
            "replay_safety_classification": COCKPIT_REPLAY_SAFETY_CLASSIFICATION,
            "creates_query_ready": False,
            "replay_can_authorize_trades": False,
        }
    )
    return create_evidence_event(
        event_id=_event_id(event_type, normalized, sequence),
        timestamp=timestamp,
        contract=normalized,
        profile_id=_profile_id_for_contract(normalized, active_profile_id=active_profile_id),
        event_type=event_type,
        source="manual",
        pipeline_run_id=pipeline_run_id,
        operator_note=operator_note,
        data_quality=enriched,
        synthetic=False,
    )


def _row_for_contract(
    surface: Mapping[str, object],
    contract: str,
) -> Mapping[str, object] | None:
    rows = surface.get("rows")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if (
            isinstance(row, Mapping)
            and normalize_contract_symbol(str(row.get("contract") or "")) == contract
        ):
            return row
    return None


def _blocking_reasons(
    row: Mapping[str, object],
    fallback_reason: str | None,
) -> list[str]:
    reasons = row.get("blocking_reasons")
    if isinstance(reasons, list):
        return [str(reason) for reason in reasons if str(reason).strip()]
    if fallback_reason:
        return [fallback_reason]
    return []


def _normalized_or_active_contract(
    contract: str | None,
    active_profile_id: str | None,
) -> str:
    if contract:
        normalized = normalize_contract_symbol(contract)
        if is_final_target_contract(normalized):
            return normalized
    if active_profile_id:
        for item in final_target_contracts():
            if active_profile_id.endswith(f"_{item.lower()}_phase1"):
                return item
        if active_profile_id == "fixture_es_demo":
            return "ES"
    return "ES"


def _profile_id_for_contract(
    contract: str,
    *,
    active_profile_id: str | None,
) -> str:
    normalized = normalize_contract_symbol(contract)
    if active_profile_id:
        if active_profile_id == "fixture_es_demo" and normalized == "ES":
            return active_profile_id
        if active_profile_id.endswith(f"_{normalized.lower()}_phase1"):
            return active_profile_id
    return f"preserved_{normalized.lower()}_phase1"


def _event_id(event_type: str, contract: str, sequence: int) -> str:
    return f"cockpit.{event_type}.{contract}.{sequence}"


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
