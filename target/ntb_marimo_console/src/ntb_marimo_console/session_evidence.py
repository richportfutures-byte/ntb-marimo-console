from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Final

SESSION_EVIDENCE_LIMIT: Final[int] = 18
SESSION_EVIDENCE_SCHEMA_VERSION: Final[int] = 1
SESSION_EVIDENCE_PAYLOAD_TYPE: Final[str] = "ntb_marimo_console.session_evidence"
NO_RECENT_SESSION_EVIDENCE: Final[str] = "NO_RECENT_SESSION_EVIDENCE"

_SESSION_EVIDENCE_ROOT_KEYS: Final[frozenset[str]] = frozenset(
    {
        "payload_type",
        "schema_version",
        "history_limit",
        "saved_at_utc",
        "records",
    }
)
_SESSION_EVIDENCE_RECORD_KEYS: Final[frozenset[str]] = frozenset(
    {
        "event_index",
        "profile_event_index",
        "app_session_id",
        "recorded_at_utc",
        "active_profile_id",
        "originating_profile_id",
        "requested_profile_id",
        "runtime_mode",
        "contract",
        "session_date",
        "lifecycle_action",
        "lifecycle_state",
        "current_session_state",
        "preflight_status",
        "startup_outcome",
        "query_eligibility_state",
        "query_action_state",
        "decision_review_state",
        "decision_review_outcome",
        "audit_replay_state",
        "audit_replay_outcome",
        "reload_result",
        "profile_switch_result",
        "status_summary",
        "next_action",
    }
)


@dataclass(frozen=True)
class SessionEvidenceRecord:
    event_index: int
    profile_event_index: int
    app_session_id: str
    recorded_at_utc: str
    active_profile_id: str
    originating_profile_id: str | None
    requested_profile_id: str | None
    runtime_mode: str
    contract: str
    session_date: str
    lifecycle_action: str
    lifecycle_state: str
    current_session_state: str
    preflight_status: str
    startup_outcome: str
    query_eligibility_state: str
    query_action_state: str
    decision_review_state: str
    decision_review_outcome: str | None
    audit_replay_state: str
    audit_replay_outcome: str | None
    reload_result: str
    profile_switch_result: str
    status_summary: str
    next_action: str


def append_session_evidence(
    history: tuple[SessionEvidenceRecord, ...],
    shell: Mapping[str, object],
    *,
    app_session_id: str,
    originating_profile_id: str | None,
    requested_profile_id: str | None,
    limit: int = SESSION_EVIDENCE_LIMIT,
) -> tuple[SessionEvidenceRecord, ...]:
    active_profile_id = _active_profile_id(shell)
    next_event_index = history[-1].event_index + 1 if history else 1
    next_profile_event_index = (
        sum(1 for item in history if item.active_profile_id == active_profile_id) + 1
    )
    record = SessionEvidenceRecord(
        event_index=next_event_index,
        profile_event_index=next_profile_event_index,
        app_session_id=app_session_id,
        recorded_at_utc=_utc_now_iso(),
        active_profile_id=active_profile_id,
        originating_profile_id=originating_profile_id,
        requested_profile_id=requested_profile_id,
        runtime_mode=_runtime_mode(shell),
        contract=_contract(shell),
        session_date=_session_date(shell),
        lifecycle_action=_lifecycle_value(shell, "last_action"),
        lifecycle_state=_lifecycle_value(shell, "current_lifecycle_state"),
        current_session_state=_lifecycle_value(shell, "current_session_state"),
        preflight_status=_startup_value(shell, "preflight_status"),
        startup_outcome=_startup_value(shell, "readiness_state"),
        query_eligibility_state=_workflow_value(shell, "live_query_status"),
        query_action_state=_workflow_value(shell, "query_action_status"),
        decision_review_state=_decision_review_state(shell),
        decision_review_outcome=_decision_review_outcome(shell),
        audit_replay_state=_audit_replay_state(shell),
        audit_replay_outcome=_audit_replay_outcome(shell),
        reload_result=_lifecycle_value(shell, "reload_result"),
        profile_switch_result=_lifecycle_value(shell, "profile_switch_result"),
        status_summary=_lifecycle_value(shell, "status_summary"),
        next_action=_lifecycle_value(shell, "next_action"),
    )
    bounded = (*history, record)
    if len(bounded) <= limit:
        return bounded
    return bounded[-limit:]


def serialize_session_evidence_payload(
    history: tuple[SessionEvidenceRecord, ...],
    *,
    history_limit: int = SESSION_EVIDENCE_LIMIT,
) -> dict[str, object]:
    bounded = history[-history_limit:]
    return {
        "payload_type": SESSION_EVIDENCE_PAYLOAD_TYPE,
        "schema_version": SESSION_EVIDENCE_SCHEMA_VERSION,
        "history_limit": history_limit,
        "saved_at_utc": _utc_now_iso(),
        "records": [asdict(record) for record in bounded],
    }


def deserialize_session_evidence_payload(payload: object) -> tuple[SessionEvidenceRecord, ...]:
    if not isinstance(payload, Mapping):
        raise ValueError("Session evidence payload must be a mapping.")
    if frozenset(str(key) for key in payload.keys()) != _SESSION_EVIDENCE_ROOT_KEYS:
        raise ValueError("Session evidence payload keys are invalid.")

    payload_type = payload.get("payload_type")
    if payload_type != SESSION_EVIDENCE_PAYLOAD_TYPE:
        raise ValueError("Session evidence payload type is unsupported.")

    schema_version = payload.get("schema_version")
    if schema_version != SESSION_EVIDENCE_SCHEMA_VERSION:
        raise ValueError("Session evidence schema version is unsupported.")

    history_limit = payload.get("history_limit")
    if not isinstance(history_limit, int) or history_limit != SESSION_EVIDENCE_LIMIT:
        raise ValueError("Session evidence history limit is incompatible with the current console.")

    saved_at_utc = payload.get("saved_at_utc")
    if not isinstance(saved_at_utc, str) or not saved_at_utc:
        raise ValueError("Session evidence payload saved_at_utc is invalid.")

    records = payload.get("records")
    if not isinstance(records, list):
        raise ValueError("Session evidence payload records must be a list.")
    if len(records) > history_limit:
        raise ValueError("Session evidence payload exceeds the declared bounded history limit.")

    history: list[SessionEvidenceRecord] = []
    for index, record in enumerate(records, start=1):
        history.append(_deserialize_record(record, position=index))
    return tuple(history)


def build_session_evidence_panel(
    history: tuple[SessionEvidenceRecord, ...],
    shell: Mapping[str, object],
    *,
    current_app_session_id: str,
    persistence_path: str,
    restore_status: str,
    restore_message: str,
    persistence_health_status: str,
    last_persistence_status: str,
    last_persistence_message: str,
    last_persistence_at_utc: str | None,
) -> dict[str, object]:
    active_profile_id = _active_profile_id(shell)
    supported_profiles = _supported_profiles(shell, active_profile_id=active_profile_id)
    supported_profile_ids = {profile["profile_id"] for profile in supported_profiles}
    recent_profile_ids = _recent_profile_ids(history, supported_profile_ids=supported_profile_ids)
    restored_record_count = sum(
        1 for record in history if record.app_session_id != current_app_session_id
    )
    current_session_record_count = sum(
        1 for record in history if record.app_session_id == current_app_session_id
    )

    last_known_outcomes: list[dict[str, object]] = []
    for profile in supported_profiles:
        latest = _latest_record_for_profile(history, profile["profile_id"])
        if latest is None:
            last_known_outcomes.append(
                {
                    "profile_id": profile["profile_id"],
                    "profile_kind": profile["profile_kind"],
                    "runtime_mode": profile["runtime_mode"],
                    "contract": profile["contract"],
                    "session_date": profile["session_date"],
                    "active_now": profile["active"],
                    "has_recent_evidence": False,
                    "last_known_outcome": NO_RECENT_SESSION_EVIDENCE,
                    "status_summary": "No retained recent-session evidence recorded for this profile yet.",
                }
            )
            continue

        source_scope = _record_source_scope(latest, current_app_session_id=current_app_session_id)
        last_known_outcomes.append(
            {
                "profile_id": profile["profile_id"],
                "profile_kind": profile["profile_kind"],
                "runtime_mode": profile["runtime_mode"],
                "contract": profile["contract"],
                "session_date": profile["session_date"],
                "active_now": profile["active"],
                "has_recent_evidence": True,
                "event_index": latest.event_index,
                "profile_event_index": latest.profile_event_index,
                "recorded_at_utc": latest.recorded_at_utc,
                "source_scope": source_scope,
                "source_label": _record_source_label(source_scope),
                "last_action": latest.lifecycle_action,
                "lifecycle_state": latest.lifecycle_state,
                "preflight_status": latest.preflight_status,
                "startup_outcome": latest.startup_outcome,
                "query_eligibility_state": latest.query_eligibility_state,
                "query_action_state": latest.query_action_state,
                "decision_review_state": latest.decision_review_state,
                "decision_review_outcome": latest.decision_review_outcome,
                "audit_replay_state": latest.audit_replay_state,
                "audit_replay_outcome": latest.audit_replay_outcome,
                "reload_result": latest.reload_result,
                "profile_switch_result": latest.profile_switch_result,
                "status_summary": latest.status_summary,
            }
        )

    recent_activity = []
    for record in reversed(history[-8:]):
        source_scope = _record_source_scope(record, current_app_session_id=current_app_session_id)
        recent_activity.append(
            {
                "event_index": record.event_index,
                "profile_event_index": record.profile_event_index,
                "recorded_at_utc": record.recorded_at_utc,
                "source_scope": source_scope,
                "source_label": _record_source_label(source_scope),
                "active_profile_id": record.active_profile_id,
                "originating_profile_id": record.originating_profile_id,
                "requested_profile_id": record.requested_profile_id,
                "contract": record.contract,
                "lifecycle_action": record.lifecycle_action,
                "lifecycle_state": record.lifecycle_state,
                "query_action_state": record.query_action_state,
                "decision_review_state": record.decision_review_state,
                "audit_replay_state": record.audit_replay_state,
                "summary": _activity_summary(record),
            }
        )

    return {
        "history_scope": "BOUNDED_PERSISTED_RECENT_HISTORY",
        "history_limit": SESSION_EVIDENCE_LIMIT,
        "persistence_path": persistence_path,
        "restore_status": restore_status,
        "restore_status_summary": restore_message,
        "persistence_health_status": persistence_health_status,
        "last_persistence_status": last_persistence_status,
        "last_persistence_summary": last_persistence_message,
        "last_persistence_at_utc": last_persistence_at_utc,
        "active_profile_id": active_profile_id,
        "current_session_record_count": current_session_record_count,
        "restored_record_count": restored_record_count,
        "recent_profiles": list(recent_profile_ids),
        "recent_activity": recent_activity,
        "last_known_outcomes": last_known_outcomes,
        "status_summary": (
            "Recent session evidence is retained across app restarts in a bounded target-owned ledger. "
            "Current Session versus Restored Prior Run labels prevent stale cross-run evidence from masquerading as live state. "
            "Persistence Health and Last Persistence Status report only grounded read/write/clear outcomes."
        ),
    }


def _deserialize_record(record: object, *, position: int) -> SessionEvidenceRecord:
    if not isinstance(record, Mapping):
        raise ValueError(f"Session evidence record {position} must be a mapping.")
    if frozenset(str(key) for key in record.keys()) != _SESSION_EVIDENCE_RECORD_KEYS:
        raise ValueError(f"Session evidence record {position} keys are invalid.")

    event_index = _required_int(record, "event_index", position=position, minimum=1)
    profile_event_index = _required_int(record, "profile_event_index", position=position, minimum=1)
    return SessionEvidenceRecord(
        event_index=event_index,
        profile_event_index=profile_event_index,
        app_session_id=_required_str(record, "app_session_id", position=position),
        recorded_at_utc=_required_str(record, "recorded_at_utc", position=position),
        active_profile_id=_required_str(record, "active_profile_id", position=position),
        originating_profile_id=_optional_str(record, "originating_profile_id", position=position),
        requested_profile_id=_optional_str(record, "requested_profile_id", position=position),
        runtime_mode=_required_str(record, "runtime_mode", position=position),
        contract=_required_str(record, "contract", position=position),
        session_date=_required_str(record, "session_date", position=position),
        lifecycle_action=_required_str(record, "lifecycle_action", position=position),
        lifecycle_state=_required_str(record, "lifecycle_state", position=position),
        current_session_state=_required_str(record, "current_session_state", position=position),
        preflight_status=_required_str(record, "preflight_status", position=position),
        startup_outcome=_required_str(record, "startup_outcome", position=position),
        query_eligibility_state=_required_str(record, "query_eligibility_state", position=position),
        query_action_state=_required_str(record, "query_action_state", position=position),
        decision_review_state=_required_str(record, "decision_review_state", position=position),
        decision_review_outcome=_optional_str(record, "decision_review_outcome", position=position),
        audit_replay_state=_required_str(record, "audit_replay_state", position=position),
        audit_replay_outcome=_optional_str(record, "audit_replay_outcome", position=position),
        reload_result=_required_str(record, "reload_result", position=position),
        profile_switch_result=_required_str(record, "profile_switch_result", position=position),
        status_summary=_required_str(record, "status_summary", position=position),
        next_action=_required_str(record, "next_action", position=position),
    )


def _required_int(
    mapping: Mapping[str, object],
    key: str,
    *,
    position: int,
    minimum: int,
) -> int:
    value = mapping.get(key)
    if not isinstance(value, int) or value < minimum:
        raise ValueError(f"Session evidence record {position} field {key} is invalid.")
    return value


def _required_str(mapping: Mapping[str, object], key: str, *, position: int) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Session evidence record {position} field {key} is invalid.")
    return value


def _optional_str(mapping: Mapping[str, object], key: str, *, position: int) -> str | None:
    value = mapping.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"Session evidence record {position} field {key} is invalid.")
    return value


def _record_source_scope(
    record: SessionEvidenceRecord,
    *,
    current_app_session_id: str,
) -> str:
    if record.app_session_id == current_app_session_id:
        return "CURRENT_SESSION"
    return "RESTORED_PRIOR_RUN"


def _record_source_label(source_scope: str) -> str:
    if source_scope == "CURRENT_SESSION":
        return "Current Session"
    return "Restored Prior Run"


def _recent_profile_ids(
    history: tuple[SessionEvidenceRecord, ...],
    *,
    supported_profile_ids: set[str],
) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for record in reversed(history):
        profile_id = record.active_profile_id
        if profile_id in seen or profile_id not in supported_profile_ids:
            continue
        seen.add(profile_id)
        ordered.append(profile_id)
    return tuple(ordered)


def _supported_profiles(
    shell: Mapping[str, object],
    *,
    active_profile_id: str,
) -> tuple[dict[str, object], ...]:
    startup = shell.get("startup")
    if not isinstance(startup, Mapping):
        return tuple()

    raw_profiles = startup.get("supported_profiles")
    if not isinstance(raw_profiles, list):
        return tuple()

    supported: list[dict[str, object]] = []
    for item in raw_profiles:
        if not isinstance(item, Mapping):
            continue
        profile_id = str(item.get("profile_id", "<unresolved>"))
        supported.append(
            {
                "profile_id": profile_id,
                "profile_kind": str(item.get("profile_kind", "<unresolved>")),
                "runtime_mode": str(item.get("runtime_mode", "<unresolved>")),
                "contract": str(item.get("contract", "<unresolved>")),
                "session_date": str(item.get("session_date", "<unresolved>")),
                "active": profile_id == active_profile_id,
            }
        )
    return tuple(supported)


def _latest_record_for_profile(
    history: tuple[SessionEvidenceRecord, ...],
    profile_id: str,
) -> SessionEvidenceRecord | None:
    for record in reversed(history):
        if record.active_profile_id == profile_id:
            return record
    return None


def _activity_summary(record: SessionEvidenceRecord) -> str:
    if record.lifecycle_action == "INITIAL_LOAD":
        return (
            f"Loaded {record.active_profile_id} with preflight {record.preflight_status} and "
            f"startup outcome {record.startup_outcome}."
        )
    if record.lifecycle_action == "RUN_BOUNDED_QUERY":
        return (
            f"Bounded query for {record.active_profile_id} ended in {record.query_action_state}; "
            f"Decision Review={record.decision_review_state}, Audit / Replay={record.audit_replay_state}."
        )
    if record.lifecycle_action == "RESET_SESSION":
        return (
            f"Session reset completed for {record.active_profile_id}; bounded query, Decision Review, "
            "and Audit / Replay were cleared for that profile."
        )
    if record.lifecycle_action == "RELOAD_CURRENT_PROFILE":
        return (
            f"Reload for {record.active_profile_id} ended with {record.reload_result}; "
            f"startup outcome is {record.startup_outcome}."
        )
    if record.lifecycle_action == "SWITCH_PROFILE":
        origin = record.originating_profile_id or "<unresolved>"
        requested = record.requested_profile_id or "<unresolved>"
        if record.profile_switch_result == "SWITCH_COMPLETED":
            return (
                f"Profile switch completed from {origin} to {record.active_profile_id}; "
                "the new profile became active as a fresh session."
            )
        return (
            f"Profile switch from {origin} toward {requested} did not complete; "
            f"{record.active_profile_id} remained the active profile with result {record.profile_switch_result}."
        )
    return record.status_summary


def _active_profile_id(shell: Mapping[str, object]) -> str:
    startup = shell.get("startup")
    if isinstance(startup, Mapping):
        selected = startup.get("selected_profile_id")
        if selected is not None:
            return str(selected)

    runtime = shell.get("runtime")
    if isinstance(runtime, Mapping):
        selected = runtime.get("profile_id")
        if selected is not None:
            return str(selected)

    return "<unresolved>"


def _runtime_mode(shell: Mapping[str, object]) -> str:
    startup = shell.get("startup")
    if isinstance(startup, Mapping):
        value = startup.get("runtime_mode")
        if value is not None:
            return str(value)

    runtime = shell.get("runtime")
    if isinstance(runtime, Mapping):
        value = runtime.get("runtime_mode")
        if value is not None:
            return str(value)
    return "<unresolved>"


def _contract(shell: Mapping[str, object]) -> str:
    startup = shell.get("startup")
    if isinstance(startup, Mapping):
        value = startup.get("contract")
        if value is not None:
            return str(value)

    runtime = shell.get("runtime")
    if isinstance(runtime, Mapping):
        value = runtime.get("contract")
        if value is not None:
            return str(value)
    return "<unresolved>"


def _session_date(shell: Mapping[str, object]) -> str:
    startup = shell.get("startup")
    if isinstance(startup, Mapping):
        value = startup.get("session_date")
        if value is not None:
            return str(value)

    runtime = shell.get("runtime")
    if isinstance(runtime, Mapping):
        value = runtime.get("session_date")
        if value is not None:
            return str(value)
    return "<unresolved>"


def _startup_value(shell: Mapping[str, object], key: str) -> str:
    startup = shell.get("startup")
    if isinstance(startup, Mapping):
        value = startup.get(key)
        if value is not None:
            return str(value)
    return "<unavailable>"


def _workflow_value(shell: Mapping[str, object], key: str) -> str:
    workflow = shell.get("workflow")
    if isinstance(workflow, Mapping):
        value = workflow.get(key)
        if value is not None:
            return str(value)
    return "<unavailable>"


def _lifecycle_value(shell: Mapping[str, object], key: str) -> str:
    lifecycle = shell.get("lifecycle")
    if isinstance(lifecycle, Mapping):
        value = lifecycle.get(key)
        if value is not None:
            return str(value)
    return "<unavailable>"


def _decision_review_state(shell: Mapping[str, object]) -> str:
    panel = _decision_panel(shell)
    if panel is None:
        return "<unavailable>"
    if panel.get("ready") is True or panel.get("has_result") is True:
        return "READY"
    status = panel.get("status")
    return str(status) if status is not None else "NOT_READY"


def _decision_review_outcome(shell: Mapping[str, object]) -> str | None:
    panel = _decision_panel(shell)
    if panel is None or (panel.get("has_result") is not True and panel.get("ready") is not True):
        return None
    value = panel.get("final_decision")
    return None if value is None else str(value)


def _audit_replay_state(shell: Mapping[str, object]) -> str:
    panel = _audit_panel(shell)
    if panel is None:
        return "<unavailable>"
    if panel.get("ready") is True:
        return "READY"
    status = panel.get("status")
    return str(status) if status is not None else "NOT_READY"


def _audit_replay_outcome(shell: Mapping[str, object]) -> str | None:
    panel = _audit_panel(shell)
    if panel is None or panel.get("ready") is not True:
        return None
    trace_summary = panel.get("trace_summary")
    if not isinstance(trace_summary, Mapping):
        return None
    final_decision = trace_summary.get("final_decision")
    return None if final_decision is None else str(final_decision)


def _decision_panel(shell: Mapping[str, object]) -> Mapping[str, object] | None:
    return _surface_panel(shell, "decision_review")


def _audit_panel(shell: Mapping[str, object]) -> Mapping[str, object] | None:
    return _surface_panel(shell, "audit_replay")


def _surface_panel(shell: Mapping[str, object], key: str) -> Mapping[str, object] | None:
    surfaces = shell.get("surfaces")
    if not isinstance(surfaces, Mapping):
        return None
    panel = surfaces.get(key)
    return panel if isinstance(panel, Mapping) else None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
