from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from .adapters.contracts import LIVE_OBSERVABLE_FIELD_PATHS
from .contract_universe import is_final_target_contract, is_never_supported_contract, normalize_contract_symbol


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
    checks.append(_validate_contract_supported(brief))
    checks.append(_validate_session_date_present(brief))
    checks.append(_validate_version_present(brief))
    checks.append(_validate_artifact_status_shape(brief))
    checks.append(_validate_source_context(brief))
    checks.append(_validate_unavailable_fields(brief))

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
        checks.append(_validate_setup_ids(setup_mappings))
        checks.append(_validate_setup_required_fields(setup_mappings))
        checks.append(_validate_query_triggers(setup_mappings))
        checks.append(_validate_trigger_ids(setup_mappings))
        checks.append(_validate_trigger_descriptions(setup_mappings))
        checks.append(_validate_observable_conditions(setup_mappings))
        checks.append(_validate_trigger_required_fields(setup_mappings))
        checks.append(_validate_trigger_invalidators(setup_mappings))
        checks.append(_validate_warnings_present(setup_mappings))
        checks.append(_validate_warnings_actionable(setup_mappings))

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


def _validate_contract_supported(brief: Mapping[str, object]) -> WatchmanValidatorCheck:
    contract = brief.get("contract")
    if not isinstance(contract, str) or not contract.strip():
        return WatchmanValidatorCheck(
            name="brief_contract_supported",
            status=_FAILED,
            summary="Pre-market brief contract support cannot be evaluated without a contract.",
        )
    normalized = normalize_contract_symbol(contract)
    if is_never_supported_contract(normalized) or not is_final_target_contract(normalized):
        return WatchmanValidatorCheck(
            name="brief_contract_supported",
            status=_FAILED,
            summary=f"Pre-market brief contract {normalized} is not a final target contract.",
        )
    return WatchmanValidatorCheck(
        name="brief_contract_supported",
        status=_PASS,
        summary="Pre-market brief contract is a final target contract.",
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


def _validate_version_present(brief: Mapping[str, object]) -> WatchmanValidatorCheck:
    version = brief.get("version")
    if not isinstance(version, str) or not version.strip():
        return WatchmanValidatorCheck(
            name="brief_version_present",
            status=_FAILED,
            summary="Pre-market brief version marker must be a non-empty string.",
        )
    return WatchmanValidatorCheck(
        name="brief_version_present",
        status=_PASS,
        summary="Pre-market brief version marker is populated.",
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


def _validate_source_context(brief: Mapping[str, object]) -> WatchmanValidatorCheck:
    source_context = brief.get("source_context")
    if source_context is None:
        return WatchmanValidatorCheck(
            name="required_source_context_available",
            status=_PASS,
            summary="Pre-market brief does not declare source-context gaps.",
        )
    if not isinstance(source_context, Mapping):
        return WatchmanValidatorCheck(
            name="required_source_context_available",
            status=_FAILED,
            summary="Pre-market brief source_context must be a JSON object when provided.",
        )
    missing = _string_items(source_context.get("missing_required_context"))
    unavailable = _string_items(source_context.get("unavailable_required_context"))
    if missing or unavailable:
        gaps = ", ".join((*missing, *unavailable))
        return WatchmanValidatorCheck(
            name="required_source_context_available",
            status=_REVIEW,
            summary=f"Required source context is missing or unavailable: {gaps}.",
        )
    return WatchmanValidatorCheck(
        name="required_source_context_available",
        status=_PASS,
        summary="Required source context is available for this brief foundation.",
    )


def _validate_unavailable_fields(brief: Mapping[str, object]) -> WatchmanValidatorCheck:
    unavailable_fields = brief.get("unavailable_fields")
    if unavailable_fields is None:
        return WatchmanValidatorCheck(
            name="unavailable_fields_labeled",
            status=_PASS,
            summary="Pre-market brief does not declare unavailable optional fields.",
        )
    if not isinstance(unavailable_fields, list):
        return WatchmanValidatorCheck(
            name="unavailable_fields_labeled",
            status=_FAILED,
            summary="Pre-market brief unavailable_fields must be a JSON array when provided.",
        )
    malformed = [
        str(index)
        for index, item in enumerate(unavailable_fields, start=1)
        if not isinstance(item, Mapping)
        or not isinstance(item.get("field"), str)
        or not str(item.get("field")).strip()
        or not isinstance(item.get("reason"), str)
        or not str(item.get("reason")).strip()
    ]
    if malformed:
        return WatchmanValidatorCheck(
            name="unavailable_fields_labeled",
            status=_FAILED,
            summary=(
                "Unavailable fields must each declare a non-empty field and reason. "
                f"Malformed positions: {', '.join(malformed)}."
            ),
        )
    return WatchmanValidatorCheck(
        name="unavailable_fields_labeled",
        status=_PASS,
        summary="Unavailable optional fields are labeled with explicit reasons.",
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


def _validate_setup_ids(
    setups: list[Mapping[str, object]],
) -> WatchmanValidatorCheck:
    missing = [
        str(index)
        for index, setup in enumerate(setups, start=1)
        if not isinstance(setup.get("id"), str) or not str(setup.get("id")).strip()
    ]
    if missing:
        return WatchmanValidatorCheck(
            name="setup_ids_present",
            status=_FAILED,
            summary=f"Structural setup IDs are missing for setup positions: {', '.join(missing)}.",
        )
    return WatchmanValidatorCheck(
        name="setup_ids_present",
        status=_PASS,
        summary="Every structural setup declares a setup ID.",
    )


def _validate_setup_required_fields(
    setups: list[Mapping[str, object]],
) -> WatchmanValidatorCheck:
    for setup in setups:
        required_fields = setup.get("required_live_fields")
        if not isinstance(required_fields, list) or not _string_items(required_fields):
            return WatchmanValidatorCheck(
                name="setup_required_live_fields_present",
                status=_FAILED,
                summary="Every structural setup must declare non-empty required_live_fields.",
            )
        unknown = _unknown_live_field_paths(required_fields)
        if unknown:
            return WatchmanValidatorCheck(
                name="setup_required_live_fields_present",
                status=_FAILED,
                summary="Structural setup declares unknown live field paths: " + ", ".join(unknown),
            )
    return WatchmanValidatorCheck(
        name="setup_required_live_fields_present",
        status=_PASS,
        summary="Every structural setup declares known required live fields.",
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


def _validate_trigger_ids(
    setups: list[Mapping[str, object]],
) -> WatchmanValidatorCheck:
    missing: list[str] = []
    for setup_index, trigger in _iter_query_triggers(setups):
        if not isinstance(trigger.get("id"), str) or not str(trigger.get("id")).strip():
            missing.append(str(setup_index))
    if missing:
        return WatchmanValidatorCheck(
            name="query_trigger_ids_present",
            status=_FAILED,
            summary="Every query trigger must declare an ID. Missing under setup positions: " + ", ".join(missing),
        )
    return WatchmanValidatorCheck(
        name="query_trigger_ids_present",
        status=_PASS,
        summary="Every query trigger declares an ID.",
    )


def _validate_trigger_descriptions(
    setups: list[Mapping[str, object]],
) -> WatchmanValidatorCheck:
    missing: list[str] = []
    for setup_index, trigger in _iter_query_triggers(setups):
        if not isinstance(trigger.get("description"), str) or not str(trigger.get("description")).strip():
            missing.append(str(setup_index))
    if missing:
        return WatchmanValidatorCheck(
            name="query_trigger_descriptions_present",
            status=_REVIEW,
            summary=(
                "Every query trigger must include an operator-readable description. "
                "Missing under setup positions: " + ", ".join(missing)
            ),
        )
    return WatchmanValidatorCheck(
        name="query_trigger_descriptions_present",
        status=_PASS,
        summary="Every query trigger includes an operator-readable description.",
    )


def _validate_observable_conditions(
    setups: list[Mapping[str, object]],
) -> WatchmanValidatorCheck:
    for _, trigger in _iter_query_triggers(setups):
        observable_conditions = trigger.get("observable_conditions")
        if not isinstance(observable_conditions, list) or not _string_items(observable_conditions):
            return WatchmanValidatorCheck(
                name="observable_conditions_present",
                status=_REVIEW,
                summary="Each briefed query trigger must include at least one observable condition.",
            )
    return WatchmanValidatorCheck(
        name="observable_conditions_present",
        status=_PASS,
        summary="Every query trigger contains observable conditions.",
    )


def _validate_trigger_required_fields(
    setups: list[Mapping[str, object]],
) -> WatchmanValidatorCheck:
    for _, trigger in _iter_query_triggers(setups):
        required_fields = trigger.get("required_live_fields")
        if not isinstance(required_fields, list) or not _string_items(required_fields):
            return WatchmanValidatorCheck(
                name="trigger_required_live_fields_present",
                status=_FAILED,
                summary="Every query trigger must declare non-empty required_live_fields.",
            )
        fields_used = trigger.get("fields_used")
        if not isinstance(fields_used, list) or not _string_items(fields_used):
            return WatchmanValidatorCheck(
                name="trigger_required_live_fields_present",
                status=_FAILED,
                summary="Every query trigger must declare non-empty fields_used.",
            )
        unknown = _unknown_live_field_paths(required_fields)
        if unknown:
            return WatchmanValidatorCheck(
                name="trigger_required_live_fields_present",
                status=_FAILED,
                summary="Query trigger declares unknown live field paths: " + ", ".join(unknown),
            )
        if tuple(_string_items(required_fields)) != tuple(_string_items(fields_used)):
            return WatchmanValidatorCheck(
                name="trigger_required_live_fields_present",
                status=_FAILED,
                summary="Query trigger required_live_fields must match fields_used for deterministic gating.",
            )
    return WatchmanValidatorCheck(
        name="trigger_required_live_fields_present",
        status=_PASS,
        summary="Every query trigger declares known required live fields.",
    )


def _validate_trigger_invalidators(
    setups: list[Mapping[str, object]],
) -> WatchmanValidatorCheck:
    for _, trigger in _iter_query_triggers(setups):
        invalidators = trigger.get("invalidators")
        if isinstance(invalidators, list) and invalidators:
            malformed = [
                str(index)
                for index, invalidator in enumerate(invalidators, start=1)
                if not isinstance(invalidator, Mapping)
                or not isinstance(invalidator.get("id"), str)
                or not str(invalidator.get("id")).strip()
                or not isinstance(invalidator.get("condition"), str)
                or not str(invalidator.get("condition")).strip()
            ]
            if malformed:
                return WatchmanValidatorCheck(
                    name="trigger_invalidators_declared",
                    status=_FAILED,
                    summary=(
                        "Trigger invalidators must each include non-empty id and condition. "
                        f"Malformed positions: {', '.join(malformed)}."
                    ),
                )
            continue
        policy = trigger.get("invalidator_policy")
        if not isinstance(policy, str) or not policy.strip():
            return WatchmanValidatorCheck(
                name="trigger_invalidators_declared",
                status=_REVIEW,
                summary="Every query trigger must declare invalidators or explain why none are applicable.",
            )
    return WatchmanValidatorCheck(
        name="trigger_invalidators_declared",
        status=_PASS,
        summary="Every query trigger declares invalidators or an explicit invalidator policy.",
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


def _validate_warnings_actionable(
    setups: list[Mapping[str, object]],
) -> WatchmanValidatorCheck:
    weak: list[str] = []
    for setup_index, setup in enumerate(setups, start=1):
        warnings = setup.get("warnings")
        if not isinstance(warnings, list):
            continue
        for warning_index, warning in enumerate(warnings, start=1):
            if not isinstance(warning, str) or not warning.strip():
                weak.append(f"{setup_index}.{warning_index}")
                continue
            normalized = warning.lower()
            if not any(verb in normalized for verb in _ACTIONABLE_WARNING_TERMS):
                weak.append(f"{setup_index}.{warning_index}")
    if weak:
        return WatchmanValidatorCheck(
            name="warnings_actionable",
            status=_REVIEW,
            summary="Warnings must be operator-actionable. Weak warning positions: " + ", ".join(weak),
        )
    return WatchmanValidatorCheck(
        name="warnings_actionable",
        status=_PASS,
        summary="Every warning is operator-actionable.",
    )


def _iter_query_triggers(
    setups: list[Mapping[str, object]],
) -> tuple[tuple[int, Mapping[str, object]], ...]:
    triggers: list[tuple[int, Mapping[str, object]]] = []
    for setup_index, setup in enumerate(setups, start=1):
        query_triggers = setup.get("query_triggers")
        if not isinstance(query_triggers, list):
            continue
        triggers.extend((setup_index, trigger) for trigger in query_triggers if isinstance(trigger, Mapping))
    return tuple(triggers)


def _unknown_live_field_paths(paths: object) -> tuple[str, ...]:
    return tuple(path for path in _string_items(paths) if path not in LIVE_OBSERVABLE_FIELD_PATHS)


def _string_items(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(str(item).strip() for item in value if isinstance(item, str) and item.strip())


def _as_str(value: object, *, default: str = "<missing>") -> str:
    if value is None:
        return default
    return str(value)


_ACTIONABLE_WARNING_TERMS: tuple[str, ...] = (
    "block",
    "keep",
    "do not",
    "don't",
    "wait",
    "reduce",
    "verify",
    "avoid",
    "confirm",
    "treat",
    "hold",
    "require",
    "stop",
)
