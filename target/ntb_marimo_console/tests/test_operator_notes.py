from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pytest

from ntb_marimo_console.operator_notes import (
    OPERATOR_NOTE_PAYLOAD_TYPE,
    OPERATOR_NOTE_SCHEMA_VERSION,
    OperatorNotesRegistry,
    parse_tags_text,
)


@dataclass
class FakeClock:
    current: datetime = datetime(2026, 5, 12, 13, 0, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current = self.current + timedelta(seconds=seconds)


def test_add_and_list_notes() -> None:
    clock = FakeClock()
    registry = OperatorNotesRegistry(clock=clock)

    note = registry.add(
        content="Premarket auction is balanced.",
        category="pre_market",
        contract=None,
        tags=("context", "balance"),
        note_id="note-1",
    )

    assert note.note_id == "note-1"
    assert note.timestamp == "2026-05-12T13:00:00+00:00"
    assert note.category == "pre_market"
    assert note.contract is None
    assert note.tags == ("context", "balance")
    assert registry.list() == (note,)


def test_list_by_category_filters_correctly() -> None:
    registry = OperatorNotesRegistry(clock=FakeClock())
    premarket = registry.add(content="Opening plan set.", category="pre_market", note_id="note-1")
    registry.add(content="Midday chop noted.", category="intraday", note_id="note-2")

    assert registry.list_by_category("pre_market") == (premarket,)


def test_list_by_contract_filters_correctly() -> None:
    registry = OperatorNotesRegistry(clock=FakeClock())
    es_note = registry.add(content="ES holding above VWAP.", contract="es", note_id="note-1")
    registry.add(content="Session-wide risk remains low.", contract=None, note_id="note-2")
    registry.add(content="NQ lagging ES.", contract="NQ", note_id="note-3")

    assert registry.list_by_contract("ES") == (es_note,)


def test_zn_and_gc_contract_notes_are_rejected() -> None:
    registry = OperatorNotesRegistry(clock=FakeClock())

    for contract in ("ZN", "GC"):
        with pytest.raises(ValueError, match="not in the final target universe"):
            registry.add(content="Excluded contract note.", contract=contract)


def test_json_round_trip_serialization() -> None:
    registry = OperatorNotesRegistry(clock=FakeClock())
    registry.add(
        content="MGC respecting supplied context.",
        category="intraday",
        contract="MGC",
        tags=parse_tags_text("metals, context, metals"),
        note_id="note-1",
    )

    restored = OperatorNotesRegistry.from_json(registry.to_json(), clock=FakeClock())
    payload = restored.to_payload()

    assert payload["payload_type"] == OPERATOR_NOTE_PAYLOAD_TYPE
    assert payload["schema_version"] == OPERATOR_NOTE_SCHEMA_VERSION
    assert payload["saved_at_utc"] == "2026-05-12T13:00:00+00:00"
    assert payload["notes"] == registry.to_payload()["notes"]
    assert restored.list()[0].tags == ("metals", "context")


def test_notes_are_chronologically_ordered() -> None:
    registry = OperatorNotesRegistry(clock=FakeClock())
    later = registry.add(
        content="Later observation.",
        timestamp="2026-05-12T14:30:00+00:00",
        note_id="note-later",
    )
    earlier = registry.add(
        content="Earlier observation.",
        timestamp="2026-05-12T13:15:00+00:00",
        note_id="note-earlier",
    )

    assert registry.list() == (earlier, later)


def test_export_json_produces_valid_output() -> None:
    registry = OperatorNotesRegistry(clock=FakeClock())
    registry.add(
        content="Post-session summary recorded.",
        category="post_session",
        contract="CL",
        tags=("review",),
        note_id="note-1",
    )

    payload = json.loads(registry.export_json())

    assert payload["payload_type"] == OPERATOR_NOTE_PAYLOAD_TYPE
    assert payload["schema_version"] == OPERATOR_NOTE_SCHEMA_VERSION
    assert payload["notes"][0]["contract"] == "CL"
    assert payload["notes"][0]["content"] == "Post-session summary recorded."
