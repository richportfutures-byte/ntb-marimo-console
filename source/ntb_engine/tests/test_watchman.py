from __future__ import annotations

import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ninjatradebuilder.readiness_adapter import build_readiness_runtime_inputs_from_packet
from ninjatradebuilder.watchman import (
    _normalize_megacap_value,
    _classify_vwap_posture,
    build_watchman_context_from_runtime_inputs,
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


def _recheck_trigger() -> dict[str, str]:
    return {
        "trigger_family": "recheck_at_time",
        "recheck_at_time": "2026-01-14T15:15:00Z",
    }


@pytest.mark.parametrize(
    ("contract", "expected_macro_state"),
    [
        ("ES", "breadth_cash_delta_aligned"),
        ("NQ", "relative_strength_leader"),
        ("CL", "eia_sensitive"),
        ("ZN", "auction_sensitive"),
        ("6E", "dxy_supported_europe_drive"),
        ("MGC", "macro_supportive"),
    ],
)
def test_build_watchman_context_for_each_supported_contract(
    contract: str,
    expected_macro_state: str,
) -> None:
    runtime_inputs = build_readiness_runtime_inputs_from_packet(_packet_payload(contract))

    context = build_watchman_context_from_runtime_inputs(runtime_inputs, _recheck_trigger())

    assert context.contract == contract
    assert context.contract_specific_macro_state == expected_macro_state
    assert context.allowed_hours_state == "inside_allowed_hours"
    assert context.staleness_state == "fresh"
    assert context.visual_readiness_state == "sufficient"
    assert isinstance(context.vwap_posture_state, str)
    assert context.vwap_posture_state in {
        "price_above_vwap",
        "price_below_vwap",
        "price_at_vwap",
    }
    assert context.level_proximity_state in {
        "near_prior_day_level",
        "near_overnight_level",
        "near_previous_session_value_level",
        "near_major_htf_level",
        "near_key_hvn_lvn",
        "clear_of_structure",
    }
    assert context.trigger_proximity is not None
    assert context.trigger_proximity.trigger_family == "recheck_at_time"
    assert context.trigger_proximity.time_distance_minutes is not None
    assert context.trigger_proximity.price_distance_ticks is None
    assert context.missing_inputs == []
    assert "contract_specific_macro_state" in context.rationales


def test_trigger_proximity_for_recheck_at_time() -> None:
    runtime_inputs = build_readiness_runtime_inputs_from_packet(_packet_payload("ES"))

    context = build_watchman_context_from_runtime_inputs(runtime_inputs, _recheck_trigger())

    assert context.trigger_proximity.trigger_family == "recheck_at_time"
    assert context.trigger_proximity.time_distance_minutes == 10.0
    assert context.trigger_proximity.price_distance_ticks is None


def test_trigger_proximity_for_recheck_at_time_when_past_due() -> None:
    runtime_inputs = build_readiness_runtime_inputs_from_packet(_packet_payload("ES"))
    runtime_inputs["evaluation_timestamp_iso"] = "2026-01-14T15:20:00Z"
    runtime_inputs["market_packet_json"]["timestamp"] = "2026-01-14T15:20:00Z"

    context = build_watchman_context_from_runtime_inputs(runtime_inputs, _recheck_trigger())

    assert context.trigger_proximity.trigger_family == "recheck_at_time"
    assert context.trigger_proximity.time_distance_minutes == -5.0
    assert context.trigger_proximity.price_distance_ticks is None


def test_trigger_proximity_for_price_level_touch() -> None:
    runtime_inputs = build_readiness_runtime_inputs_from_packet(_packet_payload("ES"))

    context = build_watchman_context_from_runtime_inputs(
        runtime_inputs,
        {"trigger_family": "price_level_touch", "price_level": 5030.0},
    )

    assert context.trigger_proximity.trigger_family == "price_level_touch"
    assert context.trigger_proximity.price_distance_ticks == 10.0
    assert context.trigger_proximity.time_distance_minutes is None


def test_trigger_proximity_for_price_level_touch_below() -> None:
    runtime_inputs = build_readiness_runtime_inputs_from_packet(_packet_payload("ES"))

    context = build_watchman_context_from_runtime_inputs(
        runtime_inputs,
        {"trigger_family": "price_level_touch", "price_level": 5040.0},
    )

    assert context.trigger_proximity.trigger_family == "price_level_touch"
    assert context.trigger_proximity.price_distance_ticks == -30.0
    assert context.trigger_proximity.time_distance_minutes is None


def test_level_proximity_state_es_fixture_near_overnight() -> None:
    runtime_inputs = build_readiness_runtime_inputs_from_packet(_packet_payload("ES"))

    context = build_watchman_context_from_runtime_inputs(runtime_inputs, _recheck_trigger())

    assert context.level_proximity_state == "near_overnight_level"
    assert "overnight_high" in context.rationales["level_proximity_state"]


def test_level_proximity_state_clear_of_structure() -> None:
    packet = _packet_payload("ES")
    packet["market_packet"]["current_price"] = 5024.5
    packet["market_packet"]["major_higher_timeframe_levels"] = []
    packet["market_packet"]["key_hvns"] = []
    packet["market_packet"]["key_lvns"] = []
    runtime_inputs = build_readiness_runtime_inputs_from_packet(packet)

    context = build_watchman_context_from_runtime_inputs(runtime_inputs, _recheck_trigger())

    assert context.level_proximity_state == "clear_of_structure"
    assert (
        context.rationales["level_proximity_state"]
        == "Current price is not within proximity threshold of any structural level."
    )


def test_level_proximity_state_prior_day_takes_precedence() -> None:
    packet = _packet_payload("ES")
    packet["market_packet"]["current_price"] = 5040.0
    runtime_inputs = build_readiness_runtime_inputs_from_packet(packet)

    context = build_watchman_context_from_runtime_inputs(runtime_inputs, _recheck_trigger())

    assert context.level_proximity_state == "near_prior_day_level"


def test_level_proximity_handles_none_list_fields() -> None:
    packet = _packet_payload("ES")
    packet["market_packet"]["major_higher_timeframe_levels"] = None
    packet["market_packet"]["key_hvns"] = None
    packet["market_packet"]["key_lvns"] = None
    runtime_inputs = build_readiness_runtime_inputs_from_packet(packet)

    context = build_watchman_context_from_runtime_inputs(runtime_inputs, _recheck_trigger())

    assert context.level_proximity_state in {
        "near_prior_day_level",
        "near_overnight_level",
        "near_previous_session_value_level",
        "near_major_htf_level",
        "near_key_hvn_lvn",
        "clear_of_structure",
    }


def test_sixe_london_close_thinning_uses_configurable_threshold() -> None:
    runtime_inputs = build_readiness_runtime_inputs_from_packet(_packet_payload("6E"))
    runtime_inputs["evaluation_timestamp_iso"] = "2026-01-14T16:35:00Z"
    runtime_inputs["market_packet_json"]["timestamp"] = "2026-01-14T16:35:00Z"

    context = build_watchman_context_from_runtime_inputs(runtime_inputs, _recheck_trigger())

    assert context.contract_specific_macro_state == "london_close_thinning"
    assert "london_close_thinning" in context.awareness_flags


def test_sixe_london_close_thinning_respects_constant_boundary() -> None:
    runtime_inputs = build_readiness_runtime_inputs_from_packet(_packet_payload("6E"))
    runtime_inputs["evaluation_timestamp_iso"] = "2026-01-14T16:29:00Z"
    runtime_inputs["market_packet_json"]["timestamp"] = "2026-01-14T16:29:00Z"

    context = build_watchman_context_from_runtime_inputs(runtime_inputs, _recheck_trigger())

    assert context.contract_specific_macro_state != "london_close_thinning"


def test_sixe_london_close_thinning_at_exact_boundary() -> None:
    runtime_inputs = build_readiness_runtime_inputs_from_packet(_packet_payload("6E"))
    runtime_inputs["evaluation_timestamp_iso"] = "2026-01-14T16:30:00Z"
    runtime_inputs["market_packet_json"]["timestamp"] = "2026-01-14T16:30:00Z"

    context = build_watchman_context_from_runtime_inputs(runtime_inputs, _recheck_trigger())

    assert context.contract_specific_macro_state == "london_close_thinning"


def test_normalize_megacap_value_handles_variations() -> None:
    cases = [
        ("up", "up"),
        ("Up", "up"),
        (" UP ", "up"),
        ("higher", "up"),
        ("positive", "up"),
        ("+", "up"),
        ("bullish", "up"),
        ("down", "down"),
        ("Down", "down"),
        (" DOWN ", "down"),
        ("lower", "down"),
        ("negative", "down"),
        ("-", "down"),
        ("bearish", "down"),
        ("flat", "flat"),
        ("Flat", "flat"),
        ("unchanged", "flat"),
        ("neutral", "flat"),
        ("mixed", "flat"),
        ("", "unknown"),
        (None, "unknown"),
        (42, "unknown"),
        ("something_else", "unknown"),
    ]

    for raw_value, expected in cases:
        assert _normalize_megacap_value(raw_value) == expected


def test_nq_megacap_normalization_robust_to_casing_variation() -> None:
    packet = _packet_payload("NQ")
    packet["contract_specific_extension"]["megacap_leadership_table"] = {
        "NVDA": "UP",
        "MSFT": " up ",
        "AAPL": "Down",
        "GOOGL": "higher",
    }
    runtime_inputs = build_readiness_runtime_inputs_from_packet(packet)

    context = build_watchman_context_from_runtime_inputs(runtime_inputs, _recheck_trigger())

    assert context.contract_specific_macro_state in {
        "relative_strength_leader",
        "relative_strength_fragile",
        "mixed_tech_tone",
    }


def test_nq_megacap_normalization_handles_none_values_in_table() -> None:
    packet = _packet_payload("NQ")
    packet["contract_specific_extension"]["megacap_leadership_table"] = {
        "NVDA": None,
        "MSFT": "up",
        "AAPL": 42,
    }
    runtime_inputs = build_readiness_runtime_inputs_from_packet(packet)

    context = build_watchman_context_from_runtime_inputs(runtime_inputs, _recheck_trigger())

    assert context.contract_specific_macro_state in {
        "relative_strength_leader",
        "relative_strength_fragile",
        "mixed_tech_tone",
    }


def test_vwap_posture_state_classifies_deterministically() -> None:
    epsilon = 1e-9
    cases = [
        (101.0, 100.0, 0.25, "price_above_vwap"),
        (99.0, 100.0, 0.25, "price_below_vwap"),
        (100.0, 100.0, 0.25, "price_at_vwap"),
        (100.125, 100.0, 0.25, "price_at_vwap"),
        (100.125 + epsilon, 100.0, 0.25, "price_above_vwap"),
        (99.875, 100.0, 0.25, "price_at_vwap"),
    ]

    for current_price, vwap, tick_size, expected in cases:
        packet = SimpleNamespace(
            market_packet=SimpleNamespace(current_price=current_price, vwap=vwap),
            contract_metadata=SimpleNamespace(tick_size=tick_size),
        )

        assert _classify_vwap_posture(packet) == expected


def test_vwap_posture_state_appears_in_full_watchman_context() -> None:
    runtime_inputs = build_readiness_runtime_inputs_from_packet(_packet_payload("ES"))

    context = build_watchman_context_from_runtime_inputs(runtime_inputs, _recheck_trigger())

    assert context.vwap_posture_state in {
        "price_above_vwap",
        "price_below_vwap",
        "price_at_vwap",
    }
    assert "vwap_posture_state" in context.rationales


def test_missing_inputs_reports_absent_cross_market_context() -> None:
    packet = _packet_payload("ES")
    packet["market_packet"]["cross_market_context"] = None
    runtime_inputs = build_readiness_runtime_inputs_from_packet(packet)

    context = build_watchman_context_from_runtime_inputs(runtime_inputs, _recheck_trigger())

    assert "cross_market_context" in context.missing_inputs
    assert isinstance(context.contract_specific_macro_state, str)


def test_missing_inputs_reports_absent_megacap_table_for_nq() -> None:
    packet = _packet_payload("NQ")
    packet["contract_specific_extension"]["megacap_leadership_table"] = None
    runtime_inputs = build_readiness_runtime_inputs_from_packet(packet)

    context = build_watchman_context_from_runtime_inputs(runtime_inputs, _recheck_trigger())

    assert "megacap_leadership_table" in context.missing_inputs
    assert isinstance(context.contract_specific_macro_state, str)


def test_missing_inputs_reports_absent_last_stopout_time() -> None:
    packet = _packet_payload("ES")
    packet["challenge_state"]["last_stopout_time_by_contract"] = None
    runtime_inputs = build_readiness_runtime_inputs_from_packet(packet)

    context = build_watchman_context_from_runtime_inputs(runtime_inputs, _recheck_trigger())

    assert "last_stopout_time_by_contract" in context.missing_inputs


def test_missing_inputs_reports_cl_liquidity_fields() -> None:
    packet = _packet_payload("CL")
    packet["contract_specific_extension"]["liquidity_sweep_summary"] = None
    packet["contract_specific_extension"]["dom_liquidity_summary"] = None
    runtime_inputs = build_readiness_runtime_inputs_from_packet(packet)

    context = build_watchman_context_from_runtime_inputs(runtime_inputs, _recheck_trigger())

    assert "liquidity_sweep_summary" in context.missing_inputs
    assert "dom_liquidity_summary" in context.missing_inputs


def test_missing_inputs_empty_when_all_optional_fields_present() -> None:
    runtime_inputs = build_readiness_runtime_inputs_from_packet(_packet_payload("ES"))

    context = build_watchman_context_from_runtime_inputs(runtime_inputs, _recheck_trigger())

    assert context.missing_inputs == []


def test_build_watchman_context_rejects_missing_required_runtime_slot() -> None:
    runtime_inputs = build_readiness_runtime_inputs_from_packet(_packet_payload("ZN"))
    runtime_inputs.pop("market_packet_json")

    with pytest.raises(ValueError) as exc_info:
        build_watchman_context_from_runtime_inputs(runtime_inputs, _recheck_trigger())

    assert "market_packet_json" in str(exc_info.value)


def test_build_watchman_context_rejects_malformed_runtime_packet_component() -> None:
    runtime_inputs = build_readiness_runtime_inputs_from_packet(_packet_payload("ES"))
    runtime_inputs["contract_specific_extension_json"] = {"contract": "ES"}

    with pytest.raises(ValueError) as exc_info:
        build_watchman_context_from_runtime_inputs(runtime_inputs, _recheck_trigger())

    assert "breadth" in str(exc_info.value)


def test_build_watchman_context_sets_stale_flag_deterministically() -> None:
    runtime_inputs = build_readiness_runtime_inputs_from_packet(_packet_payload("ES"))
    runtime_inputs["evaluation_timestamp_iso"] = "2026-01-14T15:20:01Z"

    context = build_watchman_context_from_runtime_inputs(runtime_inputs, _recheck_trigger())

    assert context.staleness_state == "stale"
    assert "stale_market_packet" in context.hard_lockout_flags


def test_build_watchman_context_sets_session_wind_down_flag_deterministically() -> None:
    runtime_inputs = build_readiness_runtime_inputs_from_packet(_packet_payload("ZN"))
    runtime_inputs["evaluation_timestamp_iso"] = "2026-01-14T19:30:00Z"
    runtime_inputs["market_packet_json"]["timestamp"] = "2026-01-14T19:30:00Z"

    context = build_watchman_context_from_runtime_inputs(runtime_inputs, _recheck_trigger())

    assert context.session_wind_down_state == "winding_down"
    assert "session_winding_down" in context.awareness_flags


def test_build_watchman_context_sets_event_lockout_flag_deterministically() -> None:
    runtime_inputs = build_readiness_runtime_inputs_from_packet(_packet_payload("ES"))
    event = runtime_inputs["market_packet_json"]["event_calendar_remainder"][0]
    event["event_state"] = "upcoming"
    event["minutes_until"] = 5
    event.pop("minutes_since", None)

    context = build_watchman_context_from_runtime_inputs(runtime_inputs, _recheck_trigger())

    assert context.event_risk_state == "lockout_active"
    assert "event_lockout_active" in context.hard_lockout_flags
