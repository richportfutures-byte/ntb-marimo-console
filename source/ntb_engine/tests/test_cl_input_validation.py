from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from ninjatradebuilder.validation import validate_cl_historical_packet, validate_historical_packet

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text())


def _build_packet(contract: str) -> dict:
    payload = _load_fixture("packets.valid.json")
    packet = {
        "$schema": "historical_packet_v1",
        "challenge_state": payload["shared"]["challenge_state"],
        "attached_visuals": payload["shared"]["attached_visuals"],
        "contract_metadata": payload["contracts"][contract]["contract_metadata"],
        "market_packet": payload["contracts"][contract]["market_packet"],
        "contract_specific_extension": payload["contracts"][contract]["contract_specific_extension"],
    }
    return copy.deepcopy(packet)


@pytest.mark.parametrize("contract", ["ES", "NQ", "CL", "ZN", "6E", "MGC"])
def test_valid_supported_contract_packets_pass_validation(contract: str) -> None:
    packet = validate_historical_packet(_build_packet(contract))

    assert packet.market_packet.contract == contract


def test_cl_wrapper_accepts_valid_cl_packet() -> None:
    packet = validate_cl_historical_packet(_build_packet("CL"))

    assert packet.market_packet.contract == "CL"
    assert packet.contract_specific_extension.realized_volatility_context == "normal"


def test_released_event_requires_minutes_since() -> None:
    invalid_packet = _build_packet("ES")
    invalid_packet["market_packet"]["event_calendar_remainder"][0] = {
        "name": "CPI",
        "time": "2026-01-14T13:30:00Z",
        "tier": 1,
        "event_state": "released",
    }

    with pytest.raises(ValidationError) as exc_info:
        validate_historical_packet(invalid_packet)

    assert "minutes_since" in str(exc_info.value)


def test_released_eia_requires_minutes_since() -> None:
    invalid_packet = _build_packet("CL")
    invalid_packet["contract_specific_extension"]["eia_timing"] = {
        "status": "released",
        "scheduled_time": "2026-01-14T15:30:00Z",
    }

    with pytest.raises(ValidationError) as exc_info:
        validate_historical_packet(invalid_packet)

    assert "minutes_since" in str(exc_info.value)
