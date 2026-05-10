from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal

from ntb_marimo_console.market_data.stream_events import redact_sensitive_text


DECISION_REVIEW_NARRATIVE_QUALITY_SCHEMA: Final[str] = "decision_review_narrative_quality_v1"
DECISION_REVIEW_NARRATIVE_QUALITY_SCHEMA_VERSION: Final[int] = 1

QualityStatus = Literal["PASS", "WARN", "FAIL"]

_UNSUPPORTED_CONTRACT_RE: Final[re.Pattern[str]] = re.compile(r"(?<![A-Z0-9])(?:ZN|GC)(?![A-Z0-9])")
_UNSAFE_PHRASE_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\btake\s+the\s+trade\b", re.IGNORECASE),
    re.compile(r"\benter\s+now\b", re.IGNORECASE),
    re.compile(r"\bbuy\s+now\b", re.IGNORECASE),
    re.compile(r"\bsell\s+now\b", re.IGNORECASE),
    re.compile(r"\bshort\s+now\b", re.IGNORECASE),
    re.compile(r"\blong\s+now\b", re.IGNORECASE),
    re.compile(r"\bplace\s+an?\s+order\b", re.IGNORECASE),
    re.compile(r"\bsend\s+an?\s+order\b", re.IGNORECASE),
    re.compile(r"\bsubmit\s+an?\s+order\b", re.IGNORECASE),
    re.compile(r"\bplace\s+an?\s+execution\b", re.IGNORECASE),
    re.compile(r"\bsend\s+an?\s+execution\b", re.IGNORECASE),
    re.compile(r"\bsubmit\s+an?\s+execution\b", re.IGNORECASE),
    re.compile(r"\bfill\s+confirmed\b", re.IGNORECASE),
    re.compile(r"\baccount\s+state\b", re.IGNORECASE),
    re.compile(r"\bp&l\b", re.IGNORECASE),
    re.compile(r"\bauto[-\s]?trade\b", re.IGNORECASE),
    re.compile(r"\bmove\s+stop\b", re.IGNORECASE),
    re.compile(r"\bscale\s+out\b", re.IGNORECASE),
)
_UNSAFE_FIELD_KEYS: Final[tuple[str, ...]] = (
    "broker",
    "order",
    "fill",
    "account",
    "pnl",
    "auto_trade",
    "autotrade",
    "trade_authorized",
    "execution_authorized",
    "execution_request",
    "move_stop",
    "scale_out",
    "trailing_stop",
)
_UNSUPPORTED_MARKET_READ_CLAIM_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    re.compile(r"\bguarantees?\b", re.IGNORECASE),
    re.compile(r"\bconfirmed\s+by\s+(?:footprint|dom|sweep|aggressive\s+order\s+flow)\b", re.IGNORECASE),
    re.compile(r"\b(?:footprint|dom|sweep|aggressive\s+order\s+flow)\s+confirms?\b", re.IGNORECASE),
    re.compile(r"\b(?:footprint|dom|sweep|aggressive\s+order\s+flow)\s+(?:shows?|proves?)\b", re.IGNORECASE),
)


@dataclass(frozen=True)
class NarrativeQualityCheckResult:
    check_id: str
    status: QualityStatus
    message: str

    def to_dict(self) -> dict[str, object]:
        return {
            "check_id": self.check_id,
            "status": self.status,
            "message": self.message,
        }


@dataclass(frozen=True)
class NarrativeQualityReport:
    status: QualityStatus
    checks: tuple[NarrativeQualityCheckResult, ...]
    blocking_reasons: tuple[str, ...]
    warnings: tuple[str, ...]
    source_reference_present: bool
    replay_reference_present: bool
    manual_only_language_present: bool
    preserved_engine_authority_language_present: bool
    raw_json_primary_surface_detected: bool
    unsafe_execution_language_detected: bool
    unsupported_market_read_claim_detected: bool
    unsupported_contract_language_detected: bool
    missing_narrative_detected: bool
    trigger_transition_narrative_present: bool
    schema: str = DECISION_REVIEW_NARRATIVE_QUALITY_SCHEMA
    schema_version: int = DECISION_REVIEW_NARRATIVE_QUALITY_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "schema_version": self.schema_version,
            "status": self.status,
            "checks": [check.to_dict() for check in self.checks],
            "blocking_reasons": list(self.blocking_reasons),
            "warnings": list(self.warnings),
            "source_reference_present": self.source_reference_present,
            "replay_reference_present": self.replay_reference_present,
            "manual_only_language_present": self.manual_only_language_present,
            "preserved_engine_authority_language_present": self.preserved_engine_authority_language_present,
            "raw_json_primary_surface_detected": self.raw_json_primary_surface_detected,
            "unsafe_execution_language_detected": self.unsafe_execution_language_detected,
            "unsupported_market_read_claim_detected": self.unsupported_market_read_claim_detected,
            "unsupported_contract_language_detected": self.unsupported_contract_language_detected,
            "missing_narrative_detected": self.missing_narrative_detected,
            "trigger_transition_narrative_present": self.trigger_transition_narrative_present,
        }


def validate_decision_review_narrative_quality(
    replay: Mapping[str, Any] | None,
    *,
    primary_surface_text: str | None = None,
) -> NarrativeQualityReport:
    replay_payload = dict(replay) if isinstance(replay, Mapping) else {}
    text = _surface_text(replay_payload, primary_surface_text=primary_surface_text)
    field_keys = set(_field_keys(replay_payload))

    available = replay_payload.get("available") is True
    source_reference_present = _source_reference_present(replay_payload)
    replay_reference_present = _replay_reference_present(replay_payload)
    manual_only_language_present = _manual_only_language_present(replay_payload, text)
    preserved_engine_authority_language_present = _authority_language_present(replay_payload, text)
    raw_json_primary_surface_detected = _raw_json_primary_surface_detected(primary_surface_text)
    unsafe_execution_language_detected = _unsafe_language_detected(text, field_keys)
    unsupported_market_read_claim_detected = _unsupported_market_read_claim_detected(text)
    unsupported_contract_language_detected = _unsupported_contract_language_detected(replay_payload, text)
    missing_narrative_detected = _missing_narrative_detected(replay_payload)
    trigger_transition_narrative_present = (
        replay_payload.get("trigger_transition_narrative_available") is True
    )

    checks: list[NarrativeQualityCheckResult] = []
    checks.append(
        _check(
            "replay_surface_available",
            "PASS" if available else "FAIL",
            "Replay surface is available." if available else "Replay surface is unavailable.",
        )
    )
    checks.append(
        _check(
            "source_reference_present",
            "PASS" if source_reference_present else "WARN",
            "Source attribution is present."
            if source_reference_present
            else "Source attribution is unavailable or incomplete.",
        )
    )
    checks.append(
        _check(
            "replay_reference_present",
            "PASS" if replay_reference_present else _missing_replay_reference_status(replay_payload),
            "Replay reference is present."
            if replay_reference_present
            else "Replay reference is unavailable, blocked, or inconsistent.",
        )
    )
    checks.append(
        _check(
            "manual_only_language_present",
            "PASS" if manual_only_language_present else "FAIL",
            "Manual-only language is present."
            if manual_only_language_present
            else "Manual-only language is missing.",
        )
    )
    checks.append(
        _check(
            "preserved_engine_authority_language_present",
            "PASS" if preserved_engine_authority_language_present else "FAIL",
            "Preserved-engine authority language is present."
            if preserved_engine_authority_language_present
            else "Preserved-engine authority language is missing.",
        )
    )
    checks.append(
        _check(
            "raw_json_primary_surface_detected",
            "FAIL" if raw_json_primary_surface_detected else "PASS",
            "Raw JSON primary surface was detected."
            if raw_json_primary_surface_detected
            else "No raw JSON primary surface detected.",
        )
    )
    checks.append(
        _check(
            "unsafe_execution_language_detected",
            "FAIL" if unsafe_execution_language_detected else "PASS",
            "Unsafe authority language was detected."
            if unsafe_execution_language_detected
            else "No unsafe authority language detected.",
        )
    )
    checks.append(
        _check(
            "unsupported_contract_language_detected",
            "FAIL" if unsupported_contract_language_detected else "PASS",
            "Unsupported contract language was detected."
            if unsupported_contract_language_detected
            else "No unsupported contract language detected.",
        )
    )
    checks.append(
        _check(
            "unsupported_market_read_claim_detected",
            "FAIL" if unsupported_market_read_claim_detected else "PASS",
            "Unsupported market-read claim was detected."
            if unsupported_market_read_claim_detected
            else "No unsupported market-read claims detected.",
        )
    )
    checks.append(
        _check(
            "missing_narrative_detected",
            _missing_narrative_status(available, missing_narrative_detected),
            "Narrative content is present."
            if not missing_narrative_detected
            else "Narrative content is unavailable or incomplete.",
        )
    )
    checks.append(
        _check(
            "trigger_transition_narrative_present",
            "PASS" if trigger_transition_narrative_present else "WARN",
            "Trigger-transition narrative is present."
            if trigger_transition_narrative_present
            else "Trigger-transition narrative is unavailable; replay surface remains explicit and is not fabricated.",
        )
    )

    status = _overall_status(checks)
    return NarrativeQualityReport(
        status=status,
        checks=tuple(checks),
        blocking_reasons=tuple(check.check_id for check in checks if check.status == "FAIL"),
        warnings=tuple(check.check_id for check in checks if check.status == "WARN"),
        source_reference_present=source_reference_present,
        replay_reference_present=replay_reference_present,
        manual_only_language_present=manual_only_language_present,
        preserved_engine_authority_language_present=preserved_engine_authority_language_present,
        raw_json_primary_surface_detected=raw_json_primary_surface_detected,
        unsafe_execution_language_detected=unsafe_execution_language_detected,
        unsupported_market_read_claim_detected=unsupported_market_read_claim_detected,
        unsupported_contract_language_detected=unsupported_contract_language_detected,
        missing_narrative_detected=missing_narrative_detected,
        trigger_transition_narrative_present=trigger_transition_narrative_present,
    )


def _check(check_id: str, status: QualityStatus, message: str) -> NarrativeQualityCheckResult:
    return NarrativeQualityCheckResult(check_id=check_id, status=status, message=message)


def _overall_status(checks: Sequence[NarrativeQualityCheckResult]) -> QualityStatus:
    if any(check.status == "FAIL" for check in checks):
        return "FAIL"
    if any(check.status == "WARN" for check in checks):
        return "WARN"
    return "PASS"


def _source_reference_present(replay: Mapping[str, Any]) -> bool:
    source = _safe_text(replay.get("source")).lower()
    source_fields = replay.get("source_fields")
    return bool(source and source != "unknown" and replay.get("audit_schema") and source_fields)


def _replay_reference_present(replay: Mapping[str, Any]) -> bool:
    return (
        replay.get("replay_reference_available") is True
        and replay.get("replay_reference_status") == "available"
        and bool(_safe_text(replay.get("replay_reference_run_id")))
    )


def _manual_only_language_present(replay: Mapping[str, Any], text: str) -> bool:
    lowered = text.lower()
    return replay.get("manual_only_execution") is True or "execution remains manual" in lowered


def _authority_language_present(replay: Mapping[str, Any], text: str) -> bool:
    lowered = text.lower()
    return (
        replay.get("preserved_engine_authority") is True
        or "preserved engine remains the decision authority" in lowered
        or "preserved pipeline must still decide" in lowered
    )


def _raw_json_primary_surface_detected(primary_surface_text: str | None) -> bool:
    if not primary_surface_text:
        return False
    stripped = primary_surface_text.strip()
    lowered = stripped.lower()
    if "```json" in lowered:
        return True
    return (stripped.startswith("{") or stripped.startswith("[")) and ":" in stripped


def _unsafe_language_detected(text: str, field_keys: set[str]) -> bool:
    return any(pattern.search(text) for pattern in _UNSAFE_PHRASE_PATTERNS) or any(
        key in field_keys for key in _UNSAFE_FIELD_KEYS
    )


def _unsupported_market_read_claim_detected(text: str) -> bool:
    return any(pattern.search(text) for pattern in _UNSUPPORTED_MARKET_READ_CLAIM_PATTERNS)


def _unsupported_contract_language_detected(replay: Mapping[str, Any], text: str) -> bool:
    contract = _safe_text(replay.get("contract")).upper()
    return contract in {"ZN", "GC"} or bool(_UNSUPPORTED_CONTRACT_RE.search(text.upper()))


def _missing_narrative_detected(replay: Mapping[str, Any]) -> bool:
    if replay.get("available") is not True:
        return True
    return (
        replay.get("engine_narrative_available") is not True
        and replay.get("trigger_transition_narrative_available") is not True
    )


def _missing_replay_reference_status(replay: Mapping[str, Any]) -> QualityStatus:
    status = replay.get("replay_reference_status")
    return "FAIL" if status in {"blocked", "mismatch"} else "WARN"


def _missing_narrative_status(available: bool, missing_narrative_detected: bool) -> QualityStatus:
    if not missing_narrative_detected:
        return "PASS"
    return "FAIL" if not available else "WARN"


def _surface_text(replay: Mapping[str, Any], *, primary_surface_text: str | None) -> str:
    encoded = json.dumps(replay, sort_keys=True, default=str)
    if primary_surface_text:
        encoded = f"{encoded}\n{primary_surface_text}"
    return encoded


def _field_keys(value: object) -> tuple[str, ...]:
    if isinstance(value, Mapping):
        keys: list[str] = []
        for key, item in value.items():
            keys.append(str(key))
            keys.extend(_field_keys(item))
        return tuple(keys)
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        keys = []
        for item in value:
            keys.extend(_field_keys(item))
        return tuple(keys)
    return ()


def _safe_text(value: object) -> str:
    return redact_sensitive_text(value).strip()
