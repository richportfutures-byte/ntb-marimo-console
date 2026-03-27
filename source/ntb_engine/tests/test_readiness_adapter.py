from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

from ninjatradebuilder.readiness_adapter import (
    READINESS_RUNTIME_INPUT_SLOT_NAMES,
    SUPPORTED_PACKET_READINESS_CONTRACTS,
    build_readiness_runtime_inputs_from_packet,
    is_readiness_runtime_inputs,
    run_readiness,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _packet_payload(contract: str) -> dict:
    fixture = json.loads((FIXTURES_DIR / "packets.valid.json").read_text())
    return {
        "$schema": "historical_packet_v1",
        "challenge_state": fixture["shared"]["challenge_state"],
        "attached_visuals": fixture["shared"]["attached_visuals"],
        "contract_metadata": fixture["contracts"][contract]["contract_metadata"],
        "market_packet": fixture["contracts"][contract]["market_packet"],
        "contract_specific_extension": fixture["contracts"][contract]["contract_specific_extension"],
    }


@pytest.mark.parametrize(
    ("contract", "expected_max_size", "expected_timestamp"),
    [
        ("ZN", 4, "2026-01-14T15:05:00Z"),
        ("ES", 2, "2026-01-14T15:05:00Z"),
        ("NQ", 2, "2026-01-14T15:05:00Z"),
        ("CL", 2, "2026-01-14T14:05:00Z"),
        ("6E", 4, "2026-01-14T14:05:00Z"),
        ("MGC", 12, "2026-01-14T15:05:00Z"),
    ],
)
def test_build_readiness_runtime_inputs_from_supported_packet(
    contract: str,
    expected_max_size: int,
    expected_timestamp: str,
) -> None:
    runtime_inputs = build_readiness_runtime_inputs_from_packet(_packet_payload(contract))

    assert runtime_inputs["evaluation_timestamp_iso"] == expected_timestamp
    assert runtime_inputs["contract_metadata_json"]["contract"] == contract
    assert runtime_inputs["market_packet_json"]["contract"] == contract
    assert runtime_inputs["contract_specific_extension_json"]["contract"] == contract
    assert runtime_inputs["challenge_state_json"]["max_position_size_by_contract"][contract] == expected_max_size
    assert "MASTER DOCTRINE" in runtime_inputs["master_doctrine_text"]


def test_build_readiness_runtime_inputs_rejects_unsupported_contract() -> None:
    invalid_packet = copy.deepcopy(_packet_payload("MGC"))
    invalid_packet["contract_metadata"]["contract"] = "GC"
    invalid_packet["market_packet"]["contract"] = "GC"
    invalid_packet["contract_specific_extension"]["contract"] = "GC"

    with pytest.raises(ValueError) as exc_info:
        build_readiness_runtime_inputs_from_packet(invalid_packet)

    message = str(exc_info.value)
    assert "GC" in message or "MGC" in message or "ContractSymbol" in message


def test_build_readiness_runtime_inputs_rejects_malformed_packet() -> None:
    with pytest.raises(ValueError) as exc_info:
        build_readiness_runtime_inputs_from_packet({"packet": "not-a-historical-packet"})

    assert "challenge_state" in str(exc_info.value)


def test_build_readiness_runtime_inputs_rejects_missing_required_fields() -> None:
    invalid_packet = copy.deepcopy(_packet_payload("6E"))
    invalid_packet["contract_specific_extension"].pop("europe_initiative_status")

    with pytest.raises(ValueError) as exc_info:
        build_readiness_runtime_inputs_from_packet(invalid_packet)

    assert "europe_initiative_status" in str(exc_info.value)


def test_supported_packet_readiness_contracts_are_frozen() -> None:
    assert SUPPORTED_PACKET_READINESS_CONTRACTS == ("ES", "NQ", "CL", "ZN", "6E", "MGC")


def test_is_readiness_runtime_inputs_detects_valid_inputs() -> None:
    runtime_inputs = build_readiness_runtime_inputs_from_packet(_packet_payload("ES"))

    assert is_readiness_runtime_inputs(runtime_inputs) is True


def test_is_readiness_runtime_inputs_rejects_raw_packet() -> None:
    assert is_readiness_runtime_inputs(_packet_payload("ES")) is False


def test_run_readiness_delegates_for_packet_input(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    expected_result = object()
    trigger = {"trigger_family": "recheck_at_time", "recheck_at_time": "2026-01-14T15:15:00Z"}
    adapter = object()

    def fake_run_readiness(*, runtime_inputs, readiness_trigger, model_adapter):
        captured["runtime_inputs"] = runtime_inputs
        captured["readiness_trigger"] = readiness_trigger
        captured["model_adapter"] = model_adapter
        return expected_result

    monkeypatch.setattr("ninjatradebuilder.readiness_adapter.runtime_module.run_readiness", fake_run_readiness)

    result = run_readiness(
        _packet_payload("ZN"),
        trigger,
        model_adapter=adapter,
    )

    assert result is expected_result
    assert captured["readiness_trigger"] == trigger
    assert captured["model_adapter"] is adapter
    assert captured["runtime_inputs"]["contract_metadata_json"]["contract"] == "ZN"
    assert all(slot_name in captured["runtime_inputs"] for slot_name in READINESS_RUNTIME_INPUT_SLOT_NAMES)


def test_run_readiness_delegates_for_runtime_inputs(monkeypatch) -> None:
    captured: dict[str, Any] = {}
    expected_result = object()
    trigger = {"trigger_family": "price_level_touch", "price_level": 110.40625}
    adapter = object()
    runtime_inputs = build_readiness_runtime_inputs_from_packet(_packet_payload("ZN"))

    def fake_run_readiness(*, runtime_inputs, readiness_trigger, model_adapter):
        captured["runtime_inputs"] = runtime_inputs
        captured["readiness_trigger"] = readiness_trigger
        captured["model_adapter"] = model_adapter
        return expected_result

    monkeypatch.setattr("ninjatradebuilder.readiness_adapter.runtime_module.run_readiness", fake_run_readiness)

    result = run_readiness(
        runtime_inputs,
        trigger,
        model_adapter=adapter,
    )

    assert result is expected_result
    assert captured["runtime_inputs"] == runtime_inputs
    assert captured["readiness_trigger"] == trigger
    assert captured["model_adapter"] is adapter
