from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Final, Literal

from ntb_marimo_console.anchor_inputs import AnchorInputRegistry
from ntb_marimo_console.contract_universe import is_final_target_contract, normalize_contract_symbol
from ntb_marimo_console.operator_notes import OperatorNotesRegistry


PremarketBriefSectionType = Literal[
    "session_thesis",
    "prior_session",
    "overnight_range",
    "economic_calendar",
    "correlation_context",
    "key_levels",
]
PremarketBriefSectionSource = Literal["operator", "derived", "placeholder"]
PremarketBriefContent = str | dict[str, object]

SECTION_ORDER: Final[tuple[PremarketBriefSectionType, ...]] = (
    "session_thesis",
    "prior_session",
    "overnight_range",
    "economic_calendar",
    "correlation_context",
    "key_levels",
)


@dataclass(frozen=True)
class PremarketBriefSection:
    section_type: PremarketBriefSectionType
    contract: str | None
    content: PremarketBriefContent
    source: PremarketBriefSectionSource
    updated_at: str

    def __post_init__(self) -> None:
        contract = _optional_contract(self.contract)
        _validate_iso_datetime(self.updated_at, field_name="updated_at")
        object.__setattr__(self, "contract", contract)

    def to_dict(self) -> dict[str, object]:
        return {
            "section_type": self.section_type,
            "contract": self.contract,
            "content": self.content,
            "source": self.source,
            "updated_at": self.updated_at,
        }


@dataclass(frozen=True)
class PremarketBrief:
    session_date: str
    sections: tuple[PremarketBriefSection, ...]
    generated_at: str

    def __post_init__(self) -> None:
        session_date = self.session_date.strip()
        if not session_date:
            raise ValueError("Premarket brief session_date is required.")
        _validate_iso_datetime(self.generated_at, field_name="generated_at")
        object.__setattr__(self, "session_date", session_date)

    def to_dict(self) -> dict[str, object]:
        return {
            "session_date": self.session_date,
            "generated_at": self.generated_at,
            "sections": [section.to_dict() for section in self.sections],
        }


def build_premarket_brief(
    *,
    session_date: str,
    anchor_inputs: AnchorInputRegistry | None = None,
    operator_notes: OperatorNotesRegistry | None = None,
    generated_at: str | None = None,
    manual_sections: Mapping[str, object] | None = None,
) -> PremarketBrief:
    generated_at_value = generated_at or _isoformat_utc(_utc_now())
    manual = dict(manual_sections or {})
    sections: list[PremarketBriefSection] = [
        _session_thesis_section(operator_notes, generated_at_value),
        _prior_session_section(manual, generated_at_value),
        _overnight_range_section(manual, generated_at_value),
        _economic_calendar_section(manual, generated_at_value),
        _correlation_context_section(anchor_inputs, manual, generated_at_value),
    ]
    sections.extend(_key_level_sections(anchor_inputs, generated_at_value))
    return PremarketBrief(
        session_date=session_date,
        sections=tuple(sorted(sections, key=_section_sort_key)),
        generated_at=generated_at_value,
    )


def _session_thesis_section(
    operator_notes: OperatorNotesRegistry | None,
    generated_at: str,
) -> PremarketBriefSection:
    notes = operator_notes.list_by_category("pre_market") if operator_notes is not None else ()
    if not notes:
        return _placeholder_section(
            "session_thesis",
            "No pre-market operator thesis has been recorded for this session.",
            generated_at,
        )
    return PremarketBriefSection(
        section_type="session_thesis",
        contract=None,
        content={
            "notes": [
                {
                    "note_id": note.note_id,
                    "timestamp": note.timestamp,
                    "contract": note.contract,
                    "content": note.content,
                    "tags": list(note.tags),
                }
                for note in notes
            ],
        },
        source="operator",
        updated_at=max(note.timestamp for note in notes),
    )


def _prior_session_section(
    manual: Mapping[str, object],
    generated_at: str,
) -> PremarketBriefSection:
    return _manual_or_placeholder_section(
        manual,
        key="prior_session",
        section_type="prior_session",
        placeholder="Prior-session key levels are not supplied yet.",
        generated_at=generated_at,
    )


def _overnight_range_section(
    manual: Mapping[str, object],
    generated_at: str,
) -> PremarketBriefSection:
    return _manual_or_placeholder_section(
        manual,
        key="overnight_range",
        section_type="overnight_range",
        placeholder="Overnight range summary awaits operator entry or future data integration.",
        generated_at=generated_at,
    )


def _economic_calendar_section(
    manual: Mapping[str, object],
    generated_at: str,
) -> PremarketBriefSection:
    return _manual_or_placeholder_section(
        manual,
        key="economic_calendar",
        section_type="economic_calendar",
        placeholder="Economic calendar is a manual placeholder and does not gate readiness.",
        generated_at=generated_at,
    )


def _correlation_context_section(
    anchor_inputs: AnchorInputRegistry | None,
    manual: Mapping[str, object],
    generated_at: str,
) -> PremarketBriefSection:
    manual_text = _manual_text(manual.get("correlation_context"))
    if manual_text is not None:
        return PremarketBriefSection(
            section_type="correlation_context",
            contract=None,
            content=manual_text,
            source="operator",
            updated_at=generated_at,
        )
    anchors = anchor_inputs.list() if anchor_inputs is not None else ()
    correlation_rows = [
        {
            "contract": anchor.contract,
            "correlation_anchor": anchor.correlation_anchor,
            "operator_note": anchor.operator_note,
            "updated_at": anchor.updated_at,
        }
        for anchor in anchors
        if anchor.correlation_anchor is not None or anchor.operator_note
    ]
    if not correlation_rows:
        return _placeholder_section(
            "correlation_context",
            "Cross-asset correlation notes are not supplied yet.",
            generated_at,
        )
    return PremarketBriefSection(
        section_type="correlation_context",
        contract=None,
        content={"anchors": correlation_rows},
        source="derived",
        updated_at=max(str(row["updated_at"]) for row in correlation_rows),
    )


def _key_level_sections(
    anchor_inputs: AnchorInputRegistry | None,
    generated_at: str,
) -> tuple[PremarketBriefSection, ...]:
    anchors = anchor_inputs.list() if anchor_inputs is not None else ()
    if not anchors:
        return (
            _placeholder_section(
                "key_levels",
                "No cross-asset anchor key levels have been supplied.",
                generated_at,
            ),
        )
    return tuple(
        PremarketBriefSection(
            section_type="key_levels",
            contract=anchor.contract,
            content={
                "key_levels": list(anchor.key_levels),
                "session_high": anchor.session_high,
                "session_low": anchor.session_low,
                "correlation_anchor": anchor.correlation_anchor,
                "operator_note": anchor.operator_note,
            },
            source="derived",
            updated_at=anchor.updated_at,
        )
        for anchor in anchors
    )


def _manual_or_placeholder_section(
    manual: Mapping[str, object],
    *,
    key: str,
    section_type: PremarketBriefSectionType,
    placeholder: str,
    generated_at: str,
) -> PremarketBriefSection:
    manual_text = _manual_text(manual.get(key))
    if manual_text is None:
        return _placeholder_section(section_type, placeholder, generated_at)
    return PremarketBriefSection(
        section_type=section_type,
        contract=None,
        content=manual_text,
        source="operator",
        updated_at=generated_at,
    )


def _placeholder_section(
    section_type: PremarketBriefSectionType,
    content: str,
    generated_at: str,
) -> PremarketBriefSection:
    return PremarketBriefSection(
        section_type=section_type,
        contract=None,
        content=content,
        source="placeholder",
        updated_at=generated_at,
    )


def _section_sort_key(section: PremarketBriefSection) -> tuple[int, str]:
    return (SECTION_ORDER.index(section.section_type), section.contract or "")


def _manual_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_contract(contract: str | None) -> str | None:
    if contract is None or not contract.strip():
        return None
    normalized = normalize_contract_symbol(contract)
    if not is_final_target_contract(normalized):
        raise ValueError(f"Premarket brief contract is not in the final target universe: {normalized}.")
    return normalized


def _validate_iso_datetime(value: str, *, field_name: str) -> None:
    if not value:
        raise ValueError(f"Premarket brief {field_name} is required.")
    try:
        datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Premarket brief {field_name} must be an ISO datetime.") from exc


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat_utc(value: object) -> str:
    if not isinstance(value, datetime):
        raise TypeError("Clock must return a datetime.")
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()
