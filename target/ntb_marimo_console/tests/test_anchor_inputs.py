from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import pytest

from ntb_marimo_console.anchor_inputs import (
    ANCHOR_INPUT_PAYLOAD_TYPE,
    ANCHOR_INPUT_SCHEMA_VERSION,
    AnchorInputRegistry,
    anchor_inputs_payload_for_pipeline,
    parse_key_levels_text,
)


@dataclass
class FakeClock:
    current: datetime = datetime(2026, 5, 12, 15, 30, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.current


def test_set_and_get_anchor_inputs_per_contract() -> None:
    registry = AnchorInputRegistry(clock=FakeClock())

    anchor = registry.set(
        contract="nq",
        key_levels=(18650.0, 18725.5),
        session_high=18780.0,
        session_low=18590.25,
        correlation_anchor="ES",
        operator_note="NQ watching ES acceptance above opening range.",
    )

    assert anchor.contract == "NQ"
    assert anchor.updated_at == "2026-05-12T15:30:00+00:00"
    assert registry.get("NQ") == anchor
    assert anchor.to_dict()["key_levels"] == [18650.0, 18725.5]


def test_es_is_rejected_as_anchor_input_target() -> None:
    registry = AnchorInputRegistry(clock=FakeClock())

    with pytest.raises(ValueError, match="ES is the primary anchor contract"):
        registry.set(contract="ES", key_levels=(5325.0,))


def test_zn_and_gc_are_rejected() -> None:
    registry = AnchorInputRegistry(clock=FakeClock())

    for contract in ("ZN", "GC"):
        with pytest.raises(ValueError, match="not an allowed cross-asset target"):
            registry.set(contract=contract, key_levels=(100.0,))


def test_key_levels_parsing_and_validation() -> None:
    assert parse_key_levels_text("18725.5, 18650, 18725.5") == (18650.0, 18725.5)
    assert parse_key_levels_text("") == ()

    with pytest.raises(ValueError, match="key_levels must be numeric"):
        parse_key_levels_text("18725, nope")


def test_json_round_trip_serialization() -> None:
    registry = AnchorInputRegistry(clock=FakeClock())
    registry.set(
        contract="6E",
        key_levels=parse_key_levels_text("1.085, 1.091"),
        session_high=1.093,
        session_low=1.082,
        correlation_anchor="ES",
        operator_note="DXY context supplied separately.",
    )

    restored = AnchorInputRegistry.from_json(registry.to_json(), clock=FakeClock())
    payload = restored.to_payload()

    assert payload["payload_type"] == ANCHOR_INPUT_PAYLOAD_TYPE
    assert payload["schema_version"] == ANCHOR_INPUT_SCHEMA_VERSION
    assert payload["saved_at_utc"] == "2026-05-12T15:30:00+00:00"
    assert payload["anchors"] == registry.to_payload()["anchors"]


def test_listing_all_anchor_inputs_uses_target_contract_order() -> None:
    registry = AnchorInputRegistry(clock=FakeClock())
    registry.set(contract="MGC", key_levels=(2385.0,), correlation_anchor="ES")
    registry.set(contract="NQ", key_levels=(18650.0,), correlation_anchor="ES")
    registry.set(contract="CL", key_levels=(78.2,), correlation_anchor="ES")

    assert tuple(anchor.contract for anchor in registry.list()) == ("NQ", "CL", "MGC")


def test_updating_existing_anchor_input_replaces_contract_record() -> None:
    registry = AnchorInputRegistry(clock=FakeClock())
    registry.set(contract="CL", key_levels=(78.2,), session_high=79.0, session_low=77.5)
    updated = registry.set(
        contract="CL",
        key_levels=(78.6, 79.2),
        session_high=79.4,
        session_low=77.9,
        operator_note="Updated after pit open.",
    )

    assert registry.list() == (updated,)
    assert updated.key_levels == (78.6, 79.2)
    assert updated.operator_note == "Updated after pit open."


def test_pipeline_payload_boundary_is_operator_context_not_gate_authority() -> None:
    registry = AnchorInputRegistry(clock=FakeClock())
    registry.set(contract="NQ", key_levels=(18650.0,), correlation_anchor="ES")

    payload = anchor_inputs_payload_for_pipeline(registry)

    assert payload["schema"] == ANCHOR_INPUT_PAYLOAD_TYPE
    assert payload["primary_anchor_contract"] == "ES"
    assert payload["required_for_contracts"] == ["NQ", "CL", "6E", "MGC"]
    assert payload["integration_status"] == "operator_context_available_not_gate_enforced"
    assert "NQ" in payload["anchors"]  # type: ignore[operator]
