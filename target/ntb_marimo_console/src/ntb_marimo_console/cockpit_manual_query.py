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
