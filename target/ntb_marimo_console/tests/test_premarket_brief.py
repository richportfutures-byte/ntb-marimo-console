from __future__ import annotations

import pytest

from ntb_marimo_console.anchor_inputs import AnchorInputRegistry
from ntb_marimo_console.operator_notes import OperatorNotesRegistry
from ntb_marimo_console.premarket_brief import (
    SECTION_ORDER,
    PremarketBrief,
    PremarketBriefSection,
    build_premarket_brief,
)


GENERATED_AT = "2026-05-12T12:00:00+00:00"


def test_build_premarket_brief_with_anchor_inputs_and_pre_market_notes() -> None:
    anchors = AnchorInputRegistry()
    anchors.set(
        contract="NQ",
        key_levels=(18650.0, 18725.5),
        session_high=18780.0,
        session_low=18590.25,
        correlation_anchor="ES",
        operator_note="NQ must confirm against ES breadth.",
        updated_at="2026-05-12T11:45:00+00:00",
    )
    notes = OperatorNotesRegistry()
    notes.add(
        note_id="note-premarket-1",
        timestamp="2026-05-12T11:30:00+00:00",
        category="pre_market",
        contract="NQ",
        content="Primary thesis waits for ES confirmation.",
        tags=("thesis",),
    )

    brief = build_premarket_brief(
        session_date="2026-05-12",
        anchor_inputs=anchors,
        operator_notes=notes,
        generated_at=GENERATED_AT,
    )

    assert isinstance(brief, PremarketBrief)
    session_thesis = brief.sections[0]
    assert session_thesis.section_type == "session_thesis"
    assert session_thesis.source == "operator"
    assert isinstance(session_thesis.content, dict)
    notes_payload = session_thesis.content["notes"]  # type: ignore[index]
    assert notes_payload[0]["content"] == "Primary thesis waits for ES confirmation."
    key_levels = [section for section in brief.sections if section.section_type == "key_levels"]
    assert key_levels[0].contract == "NQ"
    assert key_levels[0].source == "derived"


def test_build_premarket_brief_with_no_anchor_inputs_produces_placeholder_sections() -> None:
    brief = build_premarket_brief(session_date="2026-05-12", generated_at=GENERATED_AT)

    placeholders = [section for section in brief.sections if section.source == "placeholder"]

    assert placeholders
    assert any(section.section_type == "key_levels" for section in placeholders)
    assert any(section.section_type == "economic_calendar" for section in placeholders)
    assert any(section.section_type == "overnight_range" for section in placeholders)


def test_build_premarket_brief_with_no_notes_still_produces_valid_brief() -> None:
    anchors = AnchorInputRegistry()
    anchors.set(
        contract="CL",
        key_levels=(78.25,),
        updated_at="2026-05-12T11:45:00+00:00",
    )

    brief = build_premarket_brief(
        session_date="2026-05-12",
        anchor_inputs=anchors,
        generated_at=GENERATED_AT,
    )

    assert brief.session_date == "2026-05-12"
    assert brief.sections[0].section_type == "session_thesis"
    assert brief.sections[0].source == "placeholder"
    assert any(section.contract == "CL" for section in brief.sections)


def test_section_ordering_is_correct() -> None:
    anchors = AnchorInputRegistry()
    anchors.set(contract="MGC", key_levels=(3380.0,), updated_at="2026-05-12T11:45:00+00:00")

    brief = build_premarket_brief(
        session_date="2026-05-12",
        anchor_inputs=anchors,
        generated_at=GENERATED_AT,
    )

    order_indexes = [SECTION_ORDER.index(section.section_type) for section in brief.sections]
    assert order_indexes == sorted(order_indexes)


def test_zn_and_gc_contract_sections_are_excluded() -> None:
    for contract in ("ZN", "GC"):
        with pytest.raises(ValueError):
            PremarketBriefSection(
                section_type="key_levels",
                contract=contract,
                content="excluded",
                source="placeholder",
                updated_at=GENERATED_AT,
            )
    anchors = AnchorInputRegistry()
    for contract in ("ZN", "GC"):
        with pytest.raises(ValueError):
            anchors.set(contract=contract, key_levels=(1.0,), updated_at=GENERATED_AT)


def test_brief_serialization_to_dict() -> None:
    notes = OperatorNotesRegistry()
    notes.add(
        note_id="note-premarket-serialization",
        timestamp="2026-05-12T11:30:00+00:00",
        category="pre_market",
        content="Session-level thesis.",
        tags=("plan",),
    )

    payload = build_premarket_brief(
        session_date="2026-05-12",
        operator_notes=notes,
        generated_at=GENERATED_AT,
    ).to_dict()

    assert payload["session_date"] == "2026-05-12"
    assert payload["generated_at"] == GENERATED_AT
    assert isinstance(payload["sections"], list)
    assert payload["sections"][0]["section_type"] == "session_thesis"  # type: ignore[index]
