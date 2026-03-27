from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import AwareDatetime, ValidationError

from .pipeline import PipelineExecutionResult
from .schemas.inputs import StrictModel
from .watchman import WatchmanReadinessContext

DEFAULT_LOG_PATH = Path("logs") / "run_history.jsonl"


class RunHistoryRecord(StrictModel):
    run_id: str
    logged_at: AwareDatetime
    contract: str
    evaluation_timestamp_iso: str
    run_type: Literal["watchman_only", "full_pipeline"]
    trigger_family: str
    watchman_status: str
    watchman_hard_lockouts: list[str]
    watchman_awareness_flags: list[str]
    watchman_missing_inputs: list[str]
    vwap_posture: str
    value_location: str
    level_proximity: str
    event_risk: str
    trigger_state: str
    final_decision: str | None = None
    termination_stage: str | None = None
    sufficiency_gate_status: str | None = None
    contract_analysis_outcome: str | None = None
    proposed_setup_outcome: str | None = None
    risk_authorization_decision: str | None = None
    notes: str | None = None


def _watchman_status(context: WatchmanReadinessContext) -> str:
    if context.hard_lockout_flags:
        return "blocked"
    if context.awareness_flags or context.missing_inputs:
        return "caution"
    return "ready"


def _evaluation_timestamp_iso(context: WatchmanReadinessContext) -> str:
    return context.timestamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _watchman_fields(
    context: WatchmanReadinessContext,
    trigger_family: str,
    *,
    run_type: Literal["watchman_only", "full_pipeline"],
    notes: str | None,
) -> dict[str, object]:
    return {
        "run_id": str(uuid.uuid4()),
        "logged_at": datetime.now(tz=timezone.utc),
        "contract": context.contract,
        "evaluation_timestamp_iso": _evaluation_timestamp_iso(context),
        "run_type": run_type,
        "trigger_family": trigger_family,
        "watchman_status": _watchman_status(context),
        "watchman_hard_lockouts": list(context.hard_lockout_flags),
        "watchman_awareness_flags": list(context.awareness_flags),
        "watchman_missing_inputs": list(context.missing_inputs),
        "vwap_posture": context.vwap_posture_state,
        "value_location": context.value_location_state,
        "level_proximity": context.level_proximity_state,
        "event_risk": context.event_risk_state,
        "trigger_state": context.trigger_context_state,
        "notes": notes,
    }


def build_logging_record_from_watchman(
    context: WatchmanReadinessContext,
    trigger_family: str,
    *,
    notes: str | None = None,
) -> RunHistoryRecord:
    return RunHistoryRecord(
        **_watchman_fields(
            context,
            trigger_family,
            run_type="watchman_only",
            notes=notes,
        )
    )


def build_logging_record_from_pipeline(
    context: WatchmanReadinessContext,
    pipeline_result: PipelineExecutionResult,
    trigger_family: str,
    *,
    notes: str | None = None,
) -> RunHistoryRecord:
    return RunHistoryRecord(
        **_watchman_fields(
            context,
            trigger_family,
            run_type="full_pipeline",
            notes=notes,
        ),
        final_decision=getattr(pipeline_result, "final_decision", None),
        termination_stage=getattr(pipeline_result, "termination_stage", None),
        sufficiency_gate_status=getattr(
            getattr(pipeline_result, "sufficiency_gate_output", None),
            "status",
            None,
        ),
        contract_analysis_outcome=getattr(
            getattr(pipeline_result, "contract_analysis", None),
            "outcome",
            None,
        ),
        proposed_setup_outcome=getattr(
            getattr(pipeline_result, "proposed_setup", None),
            "outcome",
            None,
        ),
        risk_authorization_decision=getattr(
            getattr(pipeline_result, "risk_authorization", None),
            "decision",
            None,
        ),
    )


def append_log_record(
    record: RunHistoryRecord,
    log_path: Path | str,
) -> None:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record.model_dump(mode="json")) + "\n")


def read_log_records(log_path: Path | str) -> list[RunHistoryRecord]:
    path = Path(log_path)
    if not path.exists():
        return []

    records: list[RunHistoryRecord] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            payload = line.strip()
            if not payload:
                continue
            try:
                records.append(RunHistoryRecord.model_validate(json.loads(payload)))
            except (json.JSONDecodeError, ValidationError):
                continue
    return records


__all__ = [
    "DEFAULT_LOG_PATH",
    "RunHistoryRecord",
    "append_log_record",
    "build_logging_record_from_pipeline",
    "build_logging_record_from_watchman",
    "read_log_records",
]
