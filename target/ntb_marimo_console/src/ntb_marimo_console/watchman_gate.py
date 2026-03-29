from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal


WatchmanValidatorStatus = Literal["READY", "NEEDS_REVIEW", "FAILED"]
_PASS = "PASS"
_REVIEW = "NEEDS_REVIEW"
_FAILED = "FAILED"
_VALID_STATUS_VALUES = {"READY", "NEEDS_REVIEW", "FAILED"}
VALIDATOR_SOURCE = "watchman_brief_validator_v1"


@dataclass(frozen=True)
class WatchmanValidatorCheck:
    name: str
    status: Literal["PASS", "NEEDS_REVIEW", "FAILED"]
    summary: str


@dataclass(frozen=True)
class WatchmanValidatorResult:
    status: WatchmanValidatorStatus
    source: str
    pipeline_gate_open: bool
    brief_render_allowed: bool
    summary: str
    checks: tuple[WatchmanValidatorCheck, ...]
    failing_validators: tuple[str, ...]
    failing_validator_summaries: tuple[str, ...]
    artifact_status: str | None


def validate_watchman_brief(brief: Mapping[str, object]) -> WatchmanValidatorResult:
    checks: list[WatchmanValidatorCheck] = []
    checks.append(_validate_contract_present(brief))
    checks.append(_validate_session_date_present(brief))
    checks.append(_validate_artifact_status_shape(brief))

    setups = brief.get("structural_setups")
    setup_mappings: list[Mapping[str, object]] = []
    if not isinstance(setups, list):
        checks.append(
            WatchmanValidatorCheck(
                name="structural_setup_collection_shape",
                status=_FAILED,
                summary="Pre-market brief structural_setups must be a JSON array.",
            )
        )
    else:
        if not setups:
            checks.append(
                WatchmanValidatorCheck(
                    name="structural_setup_present",
                    status=_REVIEW,
                    summary="Pre-market brief requires at least one structural setup.",
                )
            )
        else:
            checks.append(
                WatchmanValidatorCheck(
                    name="structural_setup_present",
                    status=_PASS,
                    summary="At least one structural setup is present.",
                )
            )
        malformed_indices = [index for index, item in enumerate(setups, start=1) if not isinstance(item, Mapping)]
        if malformed_indices:
            checks.append(
                WatchmanValidatorCheck(
                    name="structural_setup_shape",
                    status=_FAILED,
                    summary=(
                        "Each structural setup must be a JSON object. "
                        f"Malformed setup positions: {', '.join(str(item) for item in malformed_indices)}."
                    ),
                )
            )
        else:
            checks.append(
                WatchmanValidatorCheck(
                    name="structural_setup_shape",
                    status=_PASS,
                    summary="All structural setups are JSON objects.",
                )
            )
            setup_mappings = list(setups)

    if setup_mappings:
        checks.append(_validate_narrative_substance(setup_mappings))
        checks.append(_validate_query_triggers(setup_mappings))
        checks.append(_validate_observable_conditions(setup_mappings))
        checks.append(_validate_warnings_present(setup_mappings))

    failing_checks = tuple(check for check in checks if check.status != _PASS)
    if any(check.status == _FAILED for check in failing_checks):
        status: WatchmanValidatorStatus = "FAILED"
    elif failing_checks:
        status = "NEEDS_REVIEW"
    else:
        status = "READY"

    if status == "READY":
        summary = "Watchman Validator authorized this brief. The pipeline gate is open."
    else:
        validator_names = ", ".join(check.name for check in failing_checks)
        summary = (
            f"Watchman Validator returned {status}. "
            f"The pipeline gate remains blocked until these validator checks pass: {validator_names}."
        )

    return WatchmanValidatorResult(
        status=status,
        source=VALIDATOR_SOURCE,
        pipeline_gate_open=status == "READY",
        brief_render_allowed=status == "READY",
        summary=summary,
        checks=tuple(checks),
        failing_validators=tuple(check.name for check in failing_checks),
        failing_validator_summaries=tuple(check.summary for check in failing_checks),
        artifact_status=str(brief.get("status")) if brief.get("status") is not None else None,
    )


def build_watchman_gate_payload(result: WatchmanValidatorResult) -> dict[str, object]:
    return {
        "validator_source": result.source,
        "validator_status": result.status,
        "artifact_status": result.artifact_status,
        "pipeline_gate_open": result.pipeline_gate_open,
        "brief_render_allowed": result.brief_render_allowed,
        "stop_required": result.pipeline_gate_open is False,
        "status_summary": result.summary,
        "failing_validators": list(result.failing_validators),
        "failing_validator_summaries": list(result.failing_validator_summaries),
    }


def watchman_gate_requires_stop(shell: Mapping[str, object]) -> bool:
    gate = shell.get("watchman_gate")
    if not isinstance(gate, Mapping):
        return False
    return gate.get("stop_required") is True


def build_watchman_gate_markdown(gate: Mapping[str, object]) -> str:
    lines = [
        "## Watchman Gate",
        f"- Validator Source: `{_as_str(gate.get('validator_source'), default='<unavailable>')}`",
        f"- Validator Status: `{_as_str(gate.get('validator_status'), default='<unavailable>')}`",
        f"- Pipeline Gate Open: `{_as_str(gate.get('pipeline_gate_open'), default=False)}`",
        f"- Status Summary: {_as_str(gate.get('status_summary'), default='<unavailable>')}",
        "- Pipeline and brief surfaces remain blocked until the Validator status is `READY`.",
    ]

    failing_validators = gate.get("failing_validators")
    failing_summaries = gate.get("failing_validator_summaries")
    if isinstance(failing_validators, list) and failing_validators:
        lines.append("- Failing Validators:")
        for index, name in enumerate(failing_validators):
            summary = None
            if isinstance(failing_summaries, list) and index < len(failing_summaries):
                summary = failing_summaries[index]
            lines.append(f"  - {_as_str(name)}: {_as_str(summary, default='<unavailable>')}")

    return "\n".join(lines)


def _validate_contract_present(brief: Mapping[str, object]) -> WatchmanValidatorCheck:
    contract = brief.get("contract")
    if not isinstance(contract, str) or not contract.strip():
        return WatchmanValidatorCheck(
            name="brief_contract_present",
            status=_FAILED,
            summary="Pre-market brief contract must be a non-empty string.",
        )
    return WatchmanValidatorCheck(
        name="brief_contract_present",
        status=_PASS,
        summary="Pre-market brief contract is populated.",
    )


def _validate_session_date_present(brief: Mapping[str, object]) -> WatchmanValidatorCheck:
    session_date = brief.get("session_date")
    if not isinstance(session_date, str) or not session_date.strip():
        return WatchmanValidatorCheck(
            name="brief_session_date_present",
            status=_FAILED,
            summary="Pre-market brief session_date must be a non-empty string.",
        )
    return WatchmanValidatorCheck(
        name="brief_session_date_present",
        status=_PASS,
        summary="Pre-market brief session_date is populated.",
    )


def _validate_artifact_status_shape(brief: Mapping[str, object]) -> WatchmanValidatorCheck:
    artifact_status = brief.get("status")
    if artifact_status is None:
        return WatchmanValidatorCheck(
            name="artifact_status_shape",
            status=_PASS,
            summary="Pre-market brief artifact status is absent and remains informational only.",
        )
    if not isinstance(artifact_status, str) or artifact_status not in _VALID_STATUS_VALUES:
        return WatchmanValidatorCheck(
            name="artifact_status_shape",
            status=_FAILED,
            summary="Pre-market brief status must be READY, NEEDS_REVIEW, or FAILED when provided.",
        )
    return WatchmanValidatorCheck(
        name="artifact_status_shape",
        status=_PASS,
        summary="Pre-market brief artifact status uses an allowed value and remains informational only.",
    )


def _validate_narrative_substance(
    setups: list[Mapping[str, object]],
) -> WatchmanValidatorCheck:
    missing = [
        str(index)
        for index, setup in enumerate(setups, start=1)
        if not isinstance(setup.get("description"), str) or not str(setup.get("description")).strip()
    ]
    if missing:
        return WatchmanValidatorCheck(
            name="narrative_substance_present",
            status=_REVIEW,
            summary=(
                "Structural setup narrative substance is incomplete. "
                f"Missing non-empty description for setup positions: {', '.join(missing)}."
            ),
        )
    return WatchmanValidatorCheck(
        name="narrative_substance_present",
        status=_PASS,
        summary="Every structural setup includes non-empty narrative substance.",
    )


def _validate_query_triggers(
    setups: list[Mapping[str, object]],
) -> WatchmanValidatorCheck:
    for setup in setups:
        triggers = setup.get("query_triggers")
        if isinstance(triggers, list) and any(isinstance(trigger, Mapping) for trigger in triggers):
            return WatchmanValidatorCheck(
                name="query_trigger_present",
                status=_PASS,
                summary="At least one query trigger is present in the brief.",
            )
    return WatchmanValidatorCheck(
        name="query_trigger_present",
        status=_REVIEW,
        summary="Pre-market brief requires at least one query trigger.",
    )


def _validate_observable_conditions(
    setups: list[Mapping[str, object]],
) -> WatchmanValidatorCheck:
    for setup in setups:
        triggers = setup.get("query_triggers")
        if not isinstance(triggers, list):
            continue
        for trigger in triggers:
            if not isinstance(trigger, Mapping):
                continue
            observable_conditions = trigger.get("observable_conditions")
            if isinstance(observable_conditions, list) and any(
                isinstance(condition, str) and condition.strip() for condition in observable_conditions
            ):
                return WatchmanValidatorCheck(
                    name="observable_conditions_present",
                    status=_PASS,
                    summary="At least one query trigger contains observable conditions.",
                )
    return WatchmanValidatorCheck(
        name="observable_conditions_present",
        status=_REVIEW,
        summary="Each briefed query trigger must include at least one observable condition.",
    )


def _validate_warnings_present(
    setups: list[Mapping[str, object]],
) -> WatchmanValidatorCheck:
    for setup in setups:
        warnings = setup.get("warnings")
        if isinstance(warnings, list) and any(isinstance(warning, str) and warning.strip() for warning in warnings):
            return WatchmanValidatorCheck(
                name="warnings_present",
                status=_PASS,
                summary="The brief contains at least one warning.",
            )
    return WatchmanValidatorCheck(
        name="warnings_present",
        status=_REVIEW,
        summary="Pre-market brief requires at least one warning.",
    )


def _as_str(value: object, *, default: str = "<missing>") -> str:
    if value is None:
        return default
    return str(value)
