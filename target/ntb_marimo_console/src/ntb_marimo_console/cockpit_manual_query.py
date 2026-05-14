from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Final

from ntb_marimo_console.adapters.contracts import PipelineBackend, PipelineQueryRequest
from ntb_marimo_console.contract_universe import (
    final_target_contracts,
    is_final_target_contract,
    normalize_contract_symbol,
)


COCKPIT_MANUAL_QUERY_SCHEMA: Final[str] = "cockpit_manual_query_result_v1"
COCKPIT_OPERATOR_ACTION_STATUS_SCHEMA: Final[str] = "cockpit_operator_action_status_v1"
COCKPIT_OPERATOR_ACTION_TIMELINE_ENTRY_SCHEMA: Final[str] = "cockpit_operator_action_timeline_entry_v1"
COCKPIT_OPERATOR_ACTION_TIMELINE_MAX_ENTRIES: Final[int] = 10
COCKPIT_OPERATOR_NOTE_SCHEMA: Final[str] = "cockpit_operator_note_v1"
COCKPIT_OPERATOR_NOTES_SURFACE_SCHEMA: Final[str] = "cockpit_operator_notes_v1"
COCKPIT_OPERATOR_NOTES_MAX_ENTRIES: Final[int] = 10
COCKPIT_OPERATOR_NOTE_MAX_TEXT_LENGTH: Final[int] = 500
COCKPIT_CURRENT_STATE_SUMMARY_SCHEMA: Final[str] = "cockpit_current_state_summary_v1"
COCKPIT_CURRENT_STATE_SUMMARY_MAX_TEXT_LENGTH: Final[int] = 240
NO_QUERY_SUBMITTED_TEXT: Final[str] = "No manual query has been submitted from the primary cockpit."
MANUAL_QUERY_DECISION_AUTHORITY: Final[str] = "preserved_engine_only"
MANUAL_QUERY_SOURCE: Final[str] = "primary_cockpit_manual_action"
QUERY_READY_PROVENANCE: Final[str] = "real_trigger_state_result_and_pipeline_gate"


@dataclass(frozen=True)
class CockpitManualQueryResult:
    contract: str
    request_status: str
    submitted: bool
    submitted_at: str | None
    gate_provenance_basis: str
    pipeline_result_status: str
    terminal_summary: str | None
    stage_termination_reason: str | None
    blocked_reason: str | None
    query_action_state: str
    query_action_text: str
    attempted_action: str
    operator_feedback_text: str
    bounded_result_summary: str
    next_operator_state: str
    pipeline_boundary: str = "PipelineBackend"
    decision_authority: str = MANUAL_QUERY_DECISION_AUTHORITY
    manual_query_only: bool = True
    manual_execution_only: bool = True
    raw_quote_values_included: bool = False
    raw_bar_values_included: bool = False
    raw_streamer_payloads_included: bool = False
    schema: str = COCKPIT_MANUAL_QUERY_SCHEMA

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "contract": self.contract,
            "request_status": self.request_status,
            "submitted": self.submitted,
            "submitted_at": self.submitted_at,
            "gate_provenance_basis": self.gate_provenance_basis,
            "pipeline_result_status": self.pipeline_result_status,
            "terminal_summary": self.terminal_summary,
            "stage_termination_reason": self.stage_termination_reason,
            "blocked_reason": self.blocked_reason,
            "query_action_state": self.query_action_state,
            "query_action_text": self.query_action_text,
            "attempted_action": self.attempted_action,
            "operator_feedback_text": self.operator_feedback_text,
            "bounded_result_summary": self.bounded_result_summary,
            "next_operator_state": self.next_operator_state,
            "pipeline_boundary": self.pipeline_boundary,
            "decision_authority": self.decision_authority,
            "manual_query_only": self.manual_query_only,
            "manual_execution_only": self.manual_execution_only,
            "raw_quote_values_included": self.raw_quote_values_included,
            "raw_bar_values_included": self.raw_bar_values_included,
            "raw_streamer_payloads_included": self.raw_streamer_payloads_included,
        }


@dataclass(frozen=True)
class CockpitOperatorActionStatus:
    action_kind: str
    action_status: str
    contract: str | None
    action_text: str
    blocked_reason: str | None
    bounded_result_summary: str
    runtime_readiness_status: str
    runtime_readiness_preserved: bool
    next_operator_state: str
    gate_provenance_basis: str
    manual_query_only: bool = True
    manual_execution_only: bool = True
    raw_quote_values_included: bool = False
    raw_bar_values_included: bool = False
    raw_streamer_payloads_included: bool = False
    schema: str = COCKPIT_OPERATOR_ACTION_STATUS_SCHEMA

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "action_kind": self.action_kind,
            "action_status": self.action_status,
            "contract": self.contract,
            "action_text": self.action_text,
            "blocked_reason": self.blocked_reason,
            "bounded_result_summary": self.bounded_result_summary,
            "runtime_readiness_status": self.runtime_readiness_status,
            "runtime_readiness_preserved": self.runtime_readiness_preserved,
            "next_operator_state": self.next_operator_state,
            "gate_provenance_basis": self.gate_provenance_basis,
            "manual_query_only": self.manual_query_only,
            "manual_execution_only": self.manual_execution_only,
            "raw_quote_values_included": self.raw_quote_values_included,
            "raw_bar_values_included": self.raw_bar_values_included,
            "raw_streamer_payloads_included": self.raw_streamer_payloads_included,
        }


def no_cockpit_manual_query_result(contract: str | None = None) -> dict[str, object]:
    normalized = normalize_contract_symbol(contract or "ES")
    return CockpitManualQueryResult(
        contract=normalized,
        request_status="NOT_SUBMITTED",
        submitted=False,
        submitted_at=None,
        gate_provenance_basis="not_submitted",
        pipeline_result_status="not_submitted",
        terminal_summary=None,
        stage_termination_reason=None,
        blocked_reason=NO_QUERY_SUBMITTED_TEXT,
        query_action_state="NOT_SUBMITTED",
        query_action_text=NO_QUERY_SUBMITTED_TEXT,
        attempted_action="none",
        operator_feedback_text=NO_QUERY_SUBMITTED_TEXT,
        bounded_result_summary="No bounded pipeline result is available.",
        next_operator_state="Select an enabled contract before submitting a manual query.",
    ).to_dict()


def no_cockpit_operator_action_status() -> dict[str, object]:
    return CockpitOperatorActionStatus(
        action_kind="IDLE",
        action_status="IDLE",
        contract=None,
        action_text="No cockpit operator action has been attempted.",
        blocked_reason=None,
        bounded_result_summary="No bounded pipeline result is available.",
        runtime_readiness_status="LIVE_RUNTIME_NOT_REQUESTED",
        runtime_readiness_preserved=False,
        next_operator_state="Select an enabled contract before submitting a manual query.",
        gate_provenance_basis="not_submitted",
    ).to_dict()


@dataclass(frozen=True)
class CockpitOperatorActionTimelineEntry:
    sequence: int
    recorded_at: str | None
    action_kind: str
    action_status: str
    contract: str | None
    action_text: str
    blocked_reason: str | None
    bounded_result_summary: str
    runtime_readiness_status: str
    runtime_readiness_preserved: bool
    next_operator_state: str
    gate_provenance_basis: str
    manual_query_only: bool = True
    manual_execution_only: bool = True
    raw_quote_values_included: bool = False
    raw_bar_values_included: bool = False
    raw_streamer_payloads_included: bool = False
    schema: str = COCKPIT_OPERATOR_ACTION_TIMELINE_ENTRY_SCHEMA

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "sequence": self.sequence,
            "recorded_at": self.recorded_at,
            "action_kind": self.action_kind,
            "action_status": self.action_status,
            "contract": self.contract,
            "action_text": self.action_text,
            "blocked_reason": self.blocked_reason,
            "bounded_result_summary": self.bounded_result_summary,
            "runtime_readiness_status": self.runtime_readiness_status,
            "runtime_readiness_preserved": self.runtime_readiness_preserved,
            "next_operator_state": self.next_operator_state,
            "gate_provenance_basis": self.gate_provenance_basis,
            "manual_query_only": self.manual_query_only,
            "manual_execution_only": self.manual_execution_only,
            "raw_quote_values_included": self.raw_quote_values_included,
            "raw_bar_values_included": self.raw_bar_values_included,
            "raw_streamer_payloads_included": self.raw_streamer_payloads_included,
        }


def append_operator_action_timeline_entry(
    history: Sequence[CockpitOperatorActionTimelineEntry],
    *,
    status: Mapping[str, object],
    recorded_at: str | None,
    max_entries: int = COCKPIT_OPERATOR_ACTION_TIMELINE_MAX_ENTRIES,
) -> tuple[CockpitOperatorActionTimelineEntry, ...]:
    sequence = (history[-1].sequence + 1) if history else 1
    entry = CockpitOperatorActionTimelineEntry(
        sequence=sequence,
        recorded_at=recorded_at,
        action_kind=str(status.get("action_kind") or "UNKNOWN"),
        action_status=str(status.get("action_status") or "UNKNOWN"),
        contract=_optional_text(status.get("contract")),
        action_text=str(status.get("action_text") or ""),
        blocked_reason=_optional_text(status.get("blocked_reason")),
        bounded_result_summary=str(
            status.get("bounded_result_summary")
            or "No bounded pipeline result is available."
        ),
        runtime_readiness_status=str(
            status.get("runtime_readiness_status") or "LIVE_RUNTIME_NOT_REQUESTED"
        ),
        runtime_readiness_preserved=bool(status.get("runtime_readiness_preserved")),
        next_operator_state=str(status.get("next_operator_state") or ""),
        gate_provenance_basis=str(status.get("gate_provenance_basis") or "not_submitted"),
    )
    updated = tuple(history) + (entry,)
    if max_entries > 0 and len(updated) > max_entries:
        updated = updated[-max_entries:]
    return updated


@dataclass(frozen=True)
class CockpitOperatorNote:
    sequence: int
    recorded_at: str | None
    contract: str | None
    profile_id: str | None
    text: str
    source: str = "OPERATOR_NOTE"
    schema: str = COCKPIT_OPERATOR_NOTE_SCHEMA
    raw_quote_values_included: bool = False
    raw_bar_values_included: bool = False
    raw_streamer_payloads_included: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "sequence": self.sequence,
            "recorded_at": self.recorded_at,
            "contract": self.contract,
            "profile_id": self.profile_id,
            "text": self.text,
            "source": self.source,
            "raw_quote_values_included": self.raw_quote_values_included,
            "raw_bar_values_included": self.raw_bar_values_included,
            "raw_streamer_payloads_included": self.raw_streamer_payloads_included,
        }


def sanitize_cockpit_operator_note_text(
    text: object,
    *,
    max_length: int = COCKPIT_OPERATOR_NOTE_MAX_TEXT_LENGTH,
) -> str | None:
    """Bound and sanitize a candidate operator-note text string.

    Returns the cleaned text, or None if the input is empty/whitespace-only
    or not a string. Length is bounded; control characters are stripped.
    """
    if not isinstance(text, str):
        return None
    cleaned = "".join(
        ch for ch in text if ch == "\n" or ch == "\t" or (ord(ch) >= 32 and ord(ch) != 127)
    )
    cleaned = cleaned.strip()
    if not cleaned:
        return None
    if max_length > 0 and len(cleaned) > max_length:
        cleaned = cleaned[:max_length]
    return cleaned


def append_cockpit_operator_note(
    history: Sequence[CockpitOperatorNote],
    *,
    text: object,
    recorded_at: str | None,
    contract: str | None = None,
    profile_id: str | None = None,
    max_entries: int = COCKPIT_OPERATOR_NOTES_MAX_ENTRIES,
    max_text_length: int = COCKPIT_OPERATOR_NOTE_MAX_TEXT_LENGTH,
) -> tuple[tuple[CockpitOperatorNote, ...], CockpitOperatorNote | None]:
    """Return (updated_notes, added_note) — added_note is None when rejected."""
    cleaned = sanitize_cockpit_operator_note_text(text, max_length=max_text_length)
    if cleaned is None:
        return tuple(history), None
    sequence = (history[-1].sequence + 1) if history else 1
    note = CockpitOperatorNote(
        sequence=sequence,
        recorded_at=recorded_at,
        contract=_optional_text(contract),
        profile_id=_optional_text(profile_id),
        text=cleaned,
    )
    updated = tuple(history) + (note,)
    if max_entries > 0 and len(updated) > max_entries:
        updated = updated[-max_entries:]
    return updated, note


def build_cockpit_operator_notes_payload(
    notes: Sequence[CockpitOperatorNote],
    *,
    max_entries: int = COCKPIT_OPERATOR_NOTES_MAX_ENTRIES,
    max_text_length: int = COCKPIT_OPERATOR_NOTE_MAX_TEXT_LENGTH,
) -> dict[str, object]:
    return {
        "schema": COCKPIT_OPERATOR_NOTES_SURFACE_SCHEMA,
        "max_entries": max_entries,
        "max_text_length": max_text_length,
        "entry_count": len(notes),
        "entries": [note.to_dict() for note in notes],
        "raw_quote_values_included": False,
        "raw_bar_values_included": False,
        "raw_streamer_payloads_included": False,
    }


def _bounded_summary_text(
    text: object,
    *,
    max_length: int = COCKPIT_CURRENT_STATE_SUMMARY_MAX_TEXT_LENGTH,
) -> str:
    cleaned = _optional_text(text)
    if cleaned is None:
        return ""
    if max_length > 0 and len(cleaned) > max_length:
        return cleaned[: max_length - 1].rstrip() + "…"
    return cleaned


def _runtime_state_text(runtime_readiness_status: str, runtime_readiness_preserved: bool) -> str:
    status = runtime_readiness_status.strip() or "LIVE_RUNTIME_NOT_REQUESTED"
    if status == "LIVE_RUNTIME_CONNECTED":
        base = "Runtime cache connected"
        if runtime_readiness_preserved:
            return f"{base}; runtime-cache-derived readiness preserved."
        return f"{base}; readiness preservation not confirmed."
    if status in {"LIVE_RUNTIME_NOT_REQUESTED", "SAFE_NON_LIVE"}:
        return "Fixture / non-live; live runtime not requested."
    return f"Runtime readiness status: {status}."


def build_cockpit_current_state_summary(surface: Mapping[str, object]) -> dict[str, object]:
    """Build a plain-English current-state summary from a cockpit surface.

    Pure display/view-model derivation: it only reads existing cockpit surface
    fields. It never creates QUERY_READY, never calls the pipeline, and never
    exposes raw quote/bar/streamer payloads.
    """
    action_status = surface.get("operator_action_status")
    action_status_map = action_status if isinstance(action_status, Mapping) else {}
    timeline = surface.get("operator_action_timeline")
    timeline_map = timeline if isinstance(timeline, Mapping) else {}
    notes = surface.get("operator_notes")
    notes_map = notes if isinstance(notes, Mapping) else {}

    rows = surface.get("rows")
    rows_list = [row for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []
    enabled_count = sum(1 for row in rows_list if row.get("query_action_state") == "ENABLED")
    blocked_count = sum(1 for row in rows_list if row.get("query_action_state") != "ENABLED")
    total_rows = len(rows_list)

    blocked_reason_text: str | None = None
    for row in rows_list:
        if row.get("query_action_state") != "ENABLED":
            reason = (
                _optional_text(row.get("query_disabled_reason"))
                or _optional_text(row.get("query_reason"))
            )
            if reason:
                contract = _optional_text(row.get("contract")) or "<contract>"
                blocked_reason_text = _bounded_summary_text(f"{contract}: {reason}")
                break

    if total_rows == 0:
        query_state_text = "Query gate state is unavailable for this cockpit surface."
    elif enabled_count == 0:
        query_state_text = (
            f"No contract is query-ready; all {total_rows} are blocked (fail-closed)."
        )
    elif blocked_count == 0:
        query_state_text = f"All {total_rows} contracts are query-ready by the existing gate."
    else:
        query_state_text = (
            f"{enabled_count} of {total_rows} contracts query-ready; "
            f"{blocked_count} blocked (fail-closed)."
        )

    runtime_readiness_status = str(
        action_status_map.get("runtime_readiness_status") or "LIVE_RUNTIME_NOT_REQUESTED"
    )
    runtime_readiness_preserved = bool(action_status_map.get("runtime_readiness_preserved"))

    last_action_kind = str(action_status_map.get("action_kind") or "IDLE")
    last_action_status = str(action_status_map.get("action_status") or "IDLE")
    last_action_text = _bounded_summary_text(
        action_status_map.get("action_text")
        or "No cockpit operator action has been attempted."
    )

    timeline_entry_count = int(timeline_map.get("entry_count") or 0)
    timeline_max = int(
        timeline_map.get("max_entries") or COCKPIT_OPERATOR_ACTION_TIMELINE_MAX_ENTRIES
    )
    if timeline_entry_count == 0:
        timeline_state_text = "No recent operator actions recorded yet."
    elif timeline_entry_count == 1:
        timeline_state_text = f"1 recent operator action recorded (bounded max {timeline_max})."
    else:
        timeline_state_text = (
            f"{timeline_entry_count} recent operator actions recorded (bounded max {timeline_max})."
        )

    notes_entry_count = int(notes_map.get("entry_count") or 0)
    notes_max = int(notes_map.get("max_entries") or COCKPIT_OPERATOR_NOTES_MAX_ENTRIES)
    if notes_entry_count == 0:
        notes_state_text = "No operator notes recorded yet."
    elif notes_entry_count == 1:
        notes_state_text = f"1 operator note recorded (bounded max {notes_max})."
    else:
        notes_state_text = (
            f"{notes_entry_count} operator notes recorded (bounded max {notes_max})."
        )

    supported = surface.get("supported_contracts")
    supported_list = (
        [str(item) for item in supported] if isinstance(supported, (list, tuple)) else []
    )
    if not supported_list:
        supported_list = list(final_target_contracts())
    contract_universe_text = (
        f"Cockpit universe: {', '.join(supported_list)}. "
        "ZN and GC remain excluded. MGC is Micro Gold."
    )

    return {
        "schema": COCKPIT_CURRENT_STATE_SUMMARY_SCHEMA,
        "runtime_state_text": _runtime_state_text(
            runtime_readiness_status, runtime_readiness_preserved
        ),
        "runtime_readiness_status": runtime_readiness_status,
        "runtime_readiness_preserved": runtime_readiness_preserved,
        "default_launch_live": bool(surface.get("default_launch_live")),
        "query_state_text": query_state_text,
        "query_enabled_count": enabled_count,
        "query_blocked_count": blocked_count,
        "query_blocked_reason_text": blocked_reason_text,
        "last_action_kind": last_action_kind,
        "last_action_status": last_action_status,
        "last_action_text": last_action_text,
        "timeline_state_text": timeline_state_text,
        "timeline_entry_count": timeline_entry_count,
        "notes_state_text": notes_state_text,
        "notes_entry_count": notes_entry_count,
        "contract_universe_text": contract_universe_text,
        "supported_contracts": supported_list,
        "decision_authority": MANUAL_QUERY_DECISION_AUTHORITY,
        "manual_query_only": True,
        "manual_execution_only": True,
        "creates_query_ready": False,
        "raw_quote_values_included": False,
        "raw_bar_values_included": False,
        "raw_streamer_payloads_included": False,
    }


def operator_action_status_from_manual_query_result(
    result: CockpitManualQueryResult,
    *,
    runtime_readiness_status: str,
    runtime_readiness_preserved: bool,
) -> dict[str, object]:
    return CockpitOperatorActionStatus(
        action_kind="MANUAL_QUERY",
        action_status=result.request_status,
        contract=result.contract,
        action_text=result.operator_feedback_text,
        blocked_reason=result.blocked_reason,
        bounded_result_summary=result.bounded_result_summary,
        runtime_readiness_status=runtime_readiness_status,
        runtime_readiness_preserved=runtime_readiness_preserved,
        next_operator_state=result.next_operator_state,
        gate_provenance_basis=result.gate_provenance_basis,
    ).to_dict()


def operator_action_status_for_lifecycle_action(
    *,
    action_kind: str,
    action_status: str,
    action_text: str,
    runtime_readiness_status: str,
    runtime_readiness_preserved: bool,
    next_operator_state: str,
    blocked_reason: str | None = None,
    contract: str | None = None,
    bounded_result_summary: str = "No new bounded pipeline result was produced by this action.",
) -> dict[str, object]:
    return CockpitOperatorActionStatus(
        action_kind=action_kind,
        action_status=action_status,
        contract=contract,
        action_text=action_text,
        blocked_reason=blocked_reason,
        bounded_result_summary=bounded_result_summary,
        runtime_readiness_status=runtime_readiness_status,
        runtime_readiness_preserved=runtime_readiness_preserved,
        next_operator_state=next_operator_state,
        gate_provenance_basis="lifecycle_action_no_query_submission",
    ).to_dict()


def submit_cockpit_manual_query(
    *,
    contract: str,
    action_rows: Sequence[Mapping[str, object]],
    backend: PipelineBackend,
    pipeline_query: PipelineQueryRequest,
    submitted_at: str | None,
) -> CockpitManualQueryResult:
    normalized = normalize_contract_symbol(contract)
    blocked = _blocked_before_pipeline(normalized, action_rows, pipeline_query)
    if blocked is not None:
        return blocked

    try:
        pipeline_result = backend.run_pipeline(pipeline_query)
        summary = backend.summarize_pipeline_result(pipeline_result)
        backend.narrate_pipeline_result(pipeline_result)
    except Exception as exc:
        return CockpitManualQueryResult(
            contract=normalized,
            request_status="FAILED",
            submitted=True,
            submitted_at=submitted_at,
            gate_provenance_basis=QUERY_READY_PROVENANCE,
            pipeline_result_status="failed",
            terminal_summary=None,
            stage_termination_reason=None,
            blocked_reason=f"Manual query failed closed: {exc}",
            query_action_state="ENABLED",
            query_action_text="Manual query submitted; preserved pipeline failed closed.",
            attempted_action=f"manual_query:{normalized}",
            operator_feedback_text=(
                f"Manual query was submitted for {normalized}, but the preserved pipeline failed closed."
            ),
            bounded_result_summary="No bounded pipeline result is available because the query failed closed.",
            next_operator_state="Review the failure reason and wait for a valid manual query state before retrying.",
        )

    terminal_summary = _optional_text(summary.get("final_decision"))
    stage_termination_reason = _optional_text(summary.get("termination_stage"))
    return CockpitManualQueryResult(
        contract=normalized,
        request_status="SUBMITTED",
        submitted=True,
        submitted_at=submitted_at,
        gate_provenance_basis=QUERY_READY_PROVENANCE,
        pipeline_result_status="completed",
        terminal_summary=terminal_summary,
        stage_termination_reason=stage_termination_reason,
        blocked_reason=None,
        query_action_state="ENABLED",
        query_action_text="Manual query submitted; preserved pipeline returned a bounded result.",
        attempted_action=f"manual_query:{normalized}",
        operator_feedback_text=(
            f"Manual query submitted for {normalized}; preserved pipeline returned a bounded result."
        ),
        bounded_result_summary=_bounded_result_summary(
            terminal_summary=terminal_summary,
            stage_termination_reason=stage_termination_reason,
        ),
        next_operator_state="Review the bounded result; execution remains manual-only and outside this cockpit.",
    )


def _blocked_before_pipeline(
    contract: str,
    action_rows: Sequence[Mapping[str, object]],
    pipeline_query: PipelineQueryRequest,
) -> CockpitManualQueryResult | None:
    if not is_final_target_contract(contract):
        return _blocked_result(
            contract=contract,
            reason=f"Manual query blocked: {contract} is not a supported cockpit query contract.",
            provenance="contract_universe",
        )
    if pipeline_query.contract != contract:
        return _blocked_result(
            contract=contract,
            reason="Manual query blocked: pipeline request contract does not match the cockpit request.",
            provenance="pipeline_query_contract_match",
        )

    row = _row_for_contract(contract, action_rows)
    if row is None:
        return _blocked_result(
            contract=contract,
            reason="Manual query blocked: no cockpit gate row is available for this contract.",
            provenance="cockpit_action_row_unavailable",
        )
    if row.get("query_action_state") != "ENABLED":
        return _blocked_result(
            contract=contract,
            reason=_blocked_reason_from_row(row),
            provenance=_optional_text(row.get("query_action_provenance")) or "blocked",
        )
    if row.get("query_action_provenance") != QUERY_READY_PROVENANCE:
        return _blocked_result(
            contract=contract,
            reason="Manual query blocked: QUERY_READY provenance is not verified.",
            provenance=_optional_text(row.get("query_action_provenance")) or "unavailable",
        )
    if row.get("query_action_source") != "existing_pipeline_gate_provenance":
        return _blocked_result(
            contract=contract,
            reason="Manual query blocked: query eligibility source is not the existing pipeline gate.",
            provenance=_optional_text(row.get("query_action_source")) or "unavailable",
        )
    if row.get("query_gate_contract") not in {None, contract}:
        return _blocked_result(
            contract=contract,
            reason="Manual query blocked: cockpit gate contract does not match the requested contract.",
            provenance="query_gate_contract_match",
        )
    return None


def _blocked_result(*, contract: str, reason: str, provenance: str) -> CockpitManualQueryResult:
    return CockpitManualQueryResult(
        contract=contract,
        request_status="BLOCKED",
        submitted=False,
        submitted_at=None,
        gate_provenance_basis=provenance,
        pipeline_result_status="not_submitted",
        terminal_summary=None,
        stage_termination_reason=None,
        blocked_reason=reason,
        query_action_state="DISABLED",
        query_action_text="Manual query blocked.",
        attempted_action=f"manual_query:{contract}",
        operator_feedback_text=reason,
        bounded_result_summary="No bounded pipeline result is available because the query was not submitted.",
        next_operator_state="Wait for existing gate/provenance authorization before submitting a manual query.",
    )


def _row_for_contract(
    contract: str,
    action_rows: Sequence[Mapping[str, object]],
) -> Mapping[str, object] | None:
    for row in action_rows:
        if normalize_contract_symbol(str(row.get("contract") or "")) == contract:
            return row
    return None


def _blocked_reason_from_row(row: Mapping[str, object]) -> str:
    reason = _optional_text(row.get("query_disabled_reason"))
    if reason:
        return reason
    reason = _optional_text(row.get("query_reason"))
    if reason:
        return reason
    contract = _optional_text(row.get("contract")) or "<unavailable>"
    return f"Manual query blocked: {contract} is not query-ready."


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _bounded_result_summary(
    *,
    terminal_summary: str | None,
    stage_termination_reason: str | None,
) -> str:
    terminal = terminal_summary or "unavailable"
    stage = stage_termination_reason or "unavailable"
    return f"Preserved pipeline completed with terminal summary {terminal}; termination stage {stage}."


def supported_cockpit_query_contracts() -> tuple[str, ...]:
    return final_target_contracts()
