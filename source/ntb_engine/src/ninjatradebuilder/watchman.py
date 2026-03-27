from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel

from .schemas.cl import CLContractSpecificExtension
from .schemas.contracts import (
    ESContractSpecificExtension,
    MGCContractSpecificExtension,
    NQContractSpecificExtension,
    SixEContractSpecificExtension,
    ZNContractSpecificExtension,
)
from .schemas.inputs import ContractSymbol, SessionType, StrictModel
from .schemas.packet import HistoricalPacket
from .validation import validate_historical_packet

AllowedHoursState = Literal["inside_allowed_hours", "outside_allowed_hours"]
ContractSpecificMacroState = str
DeltaAgreementState = Literal["bullish_agreement", "bearish_agreement", "mixed", "neutral"]
EventRiskState = Literal["clear", "elevated", "lockout_active"]
OpeningState = Literal[
    "open_drive",
    "open_test_drive",
    "open_rejection_reverse",
    "open_auction",
    "not_yet_classified",
]
RangeExpansionState = Literal["expanded", "normal", "compressed"]
SessionWindDownState = Literal["normal", "winding_down", "closed"]
StalenessState = Literal["fresh", "stale"]
TriggerContextState = Literal[
    "scheduled_recheck_pending",
    "scheduled_recheck_due",
    "above_trigger_level",
    "below_trigger_level",
    "at_trigger_level",
]
LevelProximityState = Literal[
    "near_prior_day_level",
    "near_overnight_level",
    "near_previous_session_value_level",
    "near_major_htf_level",
    "near_key_hvn_lvn",
    "clear_of_structure",
]
ValueLocationState = Literal["above_value", "inside_value", "below_value"]
VisualReadinessState = Literal["sufficient", "partial", "insufficient"]
VolumeParticipationState = Literal["elevated", "normal", "subdued"]
VwapPostureState = Literal["price_above_vwap", "price_below_vwap", "price_at_vwap"]

ET_TZ = ZoneInfo("America/New_York")
WATCHMAN_STALENESS_THRESHOLD_SECONDS = 300
WATCHMAN_WIND_DOWN_MINUTES = 30
WATCHMAN_EVENT_ELEVATED_WINDOW_MINUTES = 30
SIXE_LONDON_CLOSE_THINNING_START_ET: str = "11:30"
LEVEL_PROXIMITY_THRESHOLD_TICKS: dict[str, int] = {
    "ES": 16,
    "NQ": 16,
    "CL": 20,
    "ZN": 8,
    "6E": 20,
    "MGC": 20,
}

REQUIRED_WATCHMAN_RUNTIME_INPUT_SLOTS: tuple[str, ...] = (
    "evaluation_timestamp_iso",
    "challenge_state_json",
    "contract_metadata_json",
    "market_packet_json",
    "contract_specific_extension_json",
    "attached_visuals_json",
)


class TriggerProximity(StrictModel):
    trigger_family: str
    price_distance_ticks: float | None = None
    time_distance_minutes: float | None = None


class WatchmanReadinessContext(StrictModel):
    contract: ContractSymbol
    timestamp: AwareDatetime
    session_state: SessionType
    allowed_hours_state: AllowedHoursState
    event_risk_state: EventRiskState
    session_wind_down_state: SessionWindDownState
    staleness_state: StalenessState
    visual_readiness_state: VisualReadinessState
    value_location_state: ValueLocationState
    vwap_posture_state: VwapPostureState
    level_proximity_state: LevelProximityState
    opening_state: OpeningState
    range_expansion_state: RangeExpansionState
    volume_participation_state: VolumeParticipationState
    delta_agreement_state: DeltaAgreementState
    trigger_context_state: TriggerContextState
    trigger_proximity: TriggerProximity
    contract_specific_macro_state: ContractSpecificMacroState
    hard_lockout_flags: list[str]
    awareness_flags: list[str]
    missing_inputs: list[str]
    rationales: dict[str, str]


def build_watchman_context_from_runtime_inputs(
    runtime_inputs: Mapping[str, Any],
    readiness_trigger: Mapping[str, Any],
) -> WatchmanReadinessContext:
    packet = _validate_packet_from_runtime_inputs(runtime_inputs)
    evaluation_timestamp = _require_aware_datetime(
        runtime_inputs,
        "evaluation_timestamp_iso",
    )
    normalized_trigger = _normalize_trigger_payload(readiness_trigger)

    packet_timestamp = packet.market_packet.timestamp
    packet_age_seconds = int((evaluation_timestamp - packet_timestamp).total_seconds())
    if packet_age_seconds < 0:
        raise ValueError(
            "evaluation_timestamp_iso must be at or after market_packet_json.timestamp."
        )

    et_timestamp = evaluation_timestamp.astimezone(ET_TZ)
    session_end = _et_datetime(et_timestamp, packet.contract_metadata.allowed_hours_end_et)
    inside_allowed_hours = _is_inside_allowed_hours(et_timestamp, packet)
    minutes_to_close = int((session_end - et_timestamp).total_seconds() // 60)

    hard_lockout_flags: set[str] = set()
    awareness_flags: set[str] = set()
    rationales: dict[str, str] = {}

    allowed_hours_state: AllowedHoursState = (
        "inside_allowed_hours" if inside_allowed_hours else "outside_allowed_hours"
    )
    rationales["allowed_hours_state"] = (
        f"Evaluation time {et_timestamp.strftime('%H:%M %Z')} is "
        f"{'inside' if inside_allowed_hours else 'outside'} the contract window "
        f"{packet.contract_metadata.allowed_hours_start_et}-{packet.contract_metadata.allowed_hours_end_et} ET."
    )
    if not inside_allowed_hours:
        hard_lockout_flags.add("outside_allowed_hours")

    if not inside_allowed_hours:
        session_wind_down_state: SessionWindDownState = "closed"
    elif minutes_to_close <= WATCHMAN_WIND_DOWN_MINUTES:
        session_wind_down_state = "winding_down"
        awareness_flags.add("session_winding_down")
    else:
        session_wind_down_state = "normal"
    rationales["session_wind_down_state"] = (
        "Session closed."
        if session_wind_down_state == "closed"
        else (
            f"{minutes_to_close} minutes remain in the allowed session."
            if session_wind_down_state == "winding_down"
            else "The allowed session still has adequate time remaining."
        )
    )

    staleness_state: StalenessState = (
        "stale"
        if packet_age_seconds > WATCHMAN_STALENESS_THRESHOLD_SECONDS
        else "fresh"
    )
    rationales["staleness_state"] = (
        f"Packet age is {packet_age_seconds} seconds against a "
        f"{WATCHMAN_STALENESS_THRESHOLD_SECONDS}-second threshold."
    )
    if staleness_state == "stale":
        hard_lockout_flags.add("stale_market_packet")

    visual_readiness_state = _classify_visual_readiness(packet)
    rationales["visual_readiness_state"] = _visual_rationale(packet)
    if visual_readiness_state == "partial":
        awareness_flags.add("visual_context_partial")
    if visual_readiness_state == "insufficient":
        awareness_flags.add("visual_context_insufficient")

    value_location_state = _classify_value_location(packet)
    rationales["value_location_state"] = (
        f"Current price {packet.market_packet.current_price} is "
        f"{value_location_state.replace('_', ' ')} relative to the developing value area."
    )

    vwap_posture_state = _classify_vwap_posture(packet)
    rationales["vwap_posture_state"] = (
        f"Current price {packet.market_packet.current_price} is "
        f"{vwap_posture_state.replace('_', ' ')} relative to VWAP {packet.market_packet.vwap} "
        f"with half-tick threshold {packet.contract_metadata.tick_size / 2:.4f}."
    )
    level_proximity_state, level_proximity_rationale = _classify_level_proximity(packet)
    rationales["level_proximity_state"] = level_proximity_rationale

    opening_state = _classify_opening_state(packet)
    rationales["opening_state"] = (
        f"Opening type is {packet.market_packet.opening_type}."
    )
    if opening_state == "not_yet_classified":
        awareness_flags.add("opening_type_not_yet_classified")

    range_expansion_state = _classify_range_expansion(packet)
    rationales["range_expansion_state"] = (
        f"Session range ratio is "
        f"{packet.market_packet.session_range / packet.market_packet.avg_20d_session_range:.2f}."
    )

    volume_participation_state = _classify_volume_participation(packet)
    rationales["volume_participation_state"] = (
        f"Current volume versus average is {packet.market_packet.current_volume_vs_average:.2f}."
    )

    delta_agreement_state = _classify_delta_agreement(packet)
    rationales["delta_agreement_state"] = (
        f"Price change from open is "
        f"{packet.market_packet.current_price - packet.market_packet.session_open:.4f} "
        f"with cumulative delta {packet.market_packet.cumulative_delta:.2f}."
    )
    if delta_agreement_state == "mixed":
        awareness_flags.add("delta_divergence")

    trigger_context_state = _classify_trigger_context(
        packet,
        evaluation_timestamp,
        normalized_trigger,
    )
    trigger_proximity = _compute_trigger_proximity(
        packet,
        evaluation_timestamp,
        normalized_trigger,
    )
    rationales["trigger_context_state"] = _trigger_rationale(
        packet,
        evaluation_timestamp,
        normalized_trigger,
        trigger_context_state,
    )

    event_risk_state = _classify_event_risk(
        packet,
        hard_lockout_flags,
        awareness_flags,
        rationales,
    )

    _apply_governance_flags(packet, evaluation_timestamp, hard_lockout_flags, awareness_flags, rationales)

    contract_specific_macro_state = _classify_contract_specific_macro_state(
        packet,
        evaluation_timestamp,
        awareness_flags,
        rationales,
    )
    missing_inputs = _collect_missing_inputs(packet)

    return WatchmanReadinessContext(
        contract=packet.market_packet.contract,
        timestamp=evaluation_timestamp,
        session_state=packet.market_packet.session_type,
        allowed_hours_state=allowed_hours_state,
        event_risk_state=event_risk_state,
        session_wind_down_state=session_wind_down_state,
        staleness_state=staleness_state,
        visual_readiness_state=visual_readiness_state,
        value_location_state=value_location_state,
        vwap_posture_state=vwap_posture_state,
        level_proximity_state=level_proximity_state,
        opening_state=opening_state,
        range_expansion_state=range_expansion_state,
        volume_participation_state=volume_participation_state,
        delta_agreement_state=delta_agreement_state,
        trigger_context_state=trigger_context_state,
        trigger_proximity=trigger_proximity,
        contract_specific_macro_state=contract_specific_macro_state,
        hard_lockout_flags=sorted(hard_lockout_flags),
        awareness_flags=sorted(awareness_flags),
        missing_inputs=missing_inputs,
        rationales=rationales,
    )


def build_watchman_context_json_from_runtime_inputs(
    runtime_inputs: Mapping[str, Any],
    readiness_trigger: Mapping[str, Any],
) -> dict[str, Any]:
    return build_watchman_context_from_runtime_inputs(
        runtime_inputs,
        readiness_trigger,
    ).model_dump(mode="json", by_alias=True)


def _validate_packet_from_runtime_inputs(runtime_inputs: Mapping[str, Any]) -> HistoricalPacket:
    missing_slots = [
        slot_name
        for slot_name in REQUIRED_WATCHMAN_RUNTIME_INPUT_SLOTS
        if slot_name not in runtime_inputs
    ]
    if missing_slots:
        raise ValueError(
            "Watchman requires runtime_inputs fields: "
            f"{sorted(missing_slots)}."
        )

    packet_payload = {
        "$schema": "historical_packet_v1",
        "challenge_state": _require_mapping(runtime_inputs, "challenge_state_json"),
        "contract_metadata": _require_mapping(runtime_inputs, "contract_metadata_json"),
        "market_packet": _require_mapping(runtime_inputs, "market_packet_json"),
        "contract_specific_extension": _require_mapping(
            runtime_inputs,
            "contract_specific_extension_json",
        ),
        "attached_visuals": _require_mapping(runtime_inputs, "attached_visuals_json"),
    }
    return validate_historical_packet(packet_payload)


def _normalize_runtime_value(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json", by_alias=True)
    return value


def _require_mapping(runtime_inputs: Mapping[str, Any], slot_name: str) -> Mapping[str, Any]:
    value = _normalize_runtime_value(runtime_inputs.get(slot_name))
    if not isinstance(value, Mapping):
        raise ValueError(f"{slot_name} must be a JSON object for Watchman.")
    return value


def _require_aware_datetime(runtime_inputs: Mapping[str, Any], slot_name: str) -> datetime:
    value = runtime_inputs.get(slot_name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{slot_name} must be a non-empty ISO-8601 timestamp string.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{slot_name} must be a valid ISO-8601 timestamp string.") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{slot_name} must be timezone-aware.")
    return parsed


def _normalize_trigger_payload(readiness_trigger: Mapping[str, Any]) -> Mapping[str, Any]:
    family = readiness_trigger.get("trigger_family")
    if family == "recheck_at_time":
        value = readiness_trigger.get("recheck_at_time")
        if not isinstance(value, str) or not value.strip():
            raise ValueError(
                "Watchman requires readiness_trigger.recheck_at_time for recheck_at_time triggers."
            )
        _ = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return readiness_trigger
    if family == "price_level_touch":
        value = readiness_trigger.get("price_level")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(
                "Watchman requires readiness_trigger.price_level for price_level_touch triggers."
            )
        return readiness_trigger
    raise ValueError(
        "Watchman received unsupported readiness trigger family."
    )


def _et_datetime(et_timestamp: datetime, hhmm: str) -> datetime:
    hour_str, minute_str = hhmm.split(":")
    return et_timestamp.replace(
        hour=int(hour_str),
        minute=int(minute_str),
        second=0,
        microsecond=0,
    )


def _is_inside_allowed_hours(et_timestamp: datetime, packet: HistoricalPacket) -> bool:
    session_start = _et_datetime(et_timestamp, packet.contract_metadata.allowed_hours_start_et)
    session_end = _et_datetime(et_timestamp, packet.contract_metadata.allowed_hours_end_et)
    return session_start <= et_timestamp <= session_end


def _classify_visual_readiness(packet: HistoricalPacket) -> VisualReadinessState:
    visuals = packet.attached_visuals
    if visuals.execution_chart_attached and visuals.daily_chart_attached:
        return "sufficient"
    if any(
        (
            visuals.execution_chart_attached,
            visuals.daily_chart_attached,
            visuals.higher_timeframe_chart_attached,
            visuals.volume_profile_attached,
        )
    ):
        return "partial"
    return "insufficient"


def _visual_rationale(packet: HistoricalPacket) -> str:
    visuals = packet.attached_visuals
    available = [
        name
        for name, attached in (
            ("daily_chart", visuals.daily_chart_attached),
            ("higher_timeframe_chart", visuals.higher_timeframe_chart_attached),
            ("tpo_chart", visuals.tpo_chart_attached),
            ("volume_profile", visuals.volume_profile_attached),
            ("execution_chart", visuals.execution_chart_attached),
            ("footprint_chart", visuals.footprint_chart_attached),
            ("dom_snapshot", visuals.dom_snapshot_attached),
        )
        if attached
    ]
    return f"Visuals attached: {', '.join(available) if available else 'none'}."


def _classify_value_location(packet: HistoricalPacket) -> ValueLocationState:
    current_price = packet.market_packet.current_price
    if current_price > packet.market_packet.current_session_vah:
        return "above_value"
    if current_price < packet.market_packet.current_session_val:
        return "below_value"
    return "inside_value"


def _classify_vwap_posture(packet: HistoricalPacket) -> VwapPostureState:
    current_price = packet.market_packet.current_price
    vwap = packet.market_packet.vwap
    half_tick = packet.contract_metadata.tick_size / 2
    distance = abs(current_price - vwap)

    if distance <= half_tick:
        return "price_at_vwap"
    if current_price > vwap:
        return "price_above_vwap"
    return "price_below_vwap"


def _classify_level_proximity(packet: HistoricalPacket) -> tuple[LevelProximityState, str]:
    current_price = packet.market_packet.current_price
    contract = packet.market_packet.contract
    tick_size = packet.contract_metadata.tick_size
    threshold_ticks = LEVEL_PROXIMITY_THRESHOLD_TICKS[contract]
    threshold_price = threshold_ticks * tick_size

    def _match_tier(
        state: LevelProximityState,
        levels: list[tuple[str, float]],
    ) -> tuple[LevelProximityState, str] | None:
        closest_match: tuple[str, float, float] | None = None
        for level_name, level_value in levels:
            distance_price = abs(current_price - level_value)
            if distance_price > threshold_price:
                continue
            distance_ticks = distance_price / tick_size
            if closest_match is None or distance_ticks < closest_match[2]:
                closest_match = (level_name, level_value, distance_ticks)
        if closest_match is None:
            return None
        level_name, level_value, distance_ticks = closest_match
        return (
            state,
            f"Current price {current_price} is {distance_ticks:.1f} ticks from "
            f"{level_name} {level_value} (threshold: {threshold_ticks} ticks).",
        )

    tiers: tuple[tuple[LevelProximityState, list[tuple[str, float]]], ...] = (
        (
            "near_prior_day_level",
            [
                ("prior_day_high", packet.market_packet.prior_day_high),
                ("prior_day_low", packet.market_packet.prior_day_low),
            ],
        ),
        (
            "near_overnight_level",
            [
                ("overnight_high", packet.market_packet.overnight_high),
                ("overnight_low", packet.market_packet.overnight_low),
            ],
        ),
        (
            "near_previous_session_value_level",
            [
                ("previous_session_vah", packet.market_packet.previous_session_vah),
                ("previous_session_val", packet.market_packet.previous_session_val),
                ("previous_session_poc", packet.market_packet.previous_session_poc),
            ],
        ),
        (
            "near_major_htf_level",
            [
                ("major_higher_timeframe_levels", level)
                for level in (packet.market_packet.major_higher_timeframe_levels or [])
            ],
        ),
        (
            "near_key_hvn_lvn",
            [
                ("key_hvns", level) for level in (packet.market_packet.key_hvns or [])
            ]
            + [
                ("key_lvns", level) for level in (packet.market_packet.key_lvns or [])
            ],
        ),
    )

    for state, levels in tiers:
        matched = _match_tier(state, levels)
        if matched is not None:
            return matched

    return (
        "clear_of_structure",
        "Current price is not within proximity threshold of any structural level.",
    )


def _collect_missing_inputs(packet: HistoricalPacket) -> list[str]:
    missing_inputs: list[str] = []

    if packet.market_packet.cross_market_context is None:
        missing_inputs.append("cross_market_context")
    if packet.market_packet.data_quality_flags is None:
        missing_inputs.append("data_quality_flags")

    extension = packet.contract_specific_extension
    if isinstance(extension, NQContractSpecificExtension):
        if extension.megacap_leadership_table is None:
            missing_inputs.append("megacap_leadership_table")
    elif isinstance(extension, CLContractSpecificExtension):
        if extension.liquidity_sweep_summary is None:
            missing_inputs.append("liquidity_sweep_summary")
        if extension.dom_liquidity_summary is None:
            missing_inputs.append("dom_liquidity_summary")
    elif isinstance(extension, MGCContractSpecificExtension):
        if extension.swing_penetration_volume_summary is None:
            missing_inputs.append("swing_penetration_volume_summary")

    if packet.challenge_state.last_stopout_time_by_contract is None:
        missing_inputs.append("last_stopout_time_by_contract")

    return sorted(missing_inputs)


def _normalize_megacap_value(raw_value: Any) -> str:
    if raw_value is None:
        return "unknown"

    normalized = str(raw_value).strip().lower()
    if not normalized:
        return "unknown"
    if normalized in {"up", "higher", "positive", "+", "bullish"}:
        return "up"
    if normalized in {"down", "lower", "negative", "-", "bearish"}:
        return "down"
    if normalized in {"flat", "unchanged", "neutral", "mixed"}:
        return "flat"
    return "unknown"


def _normalize_megacap_table(raw_table: dict[str, Any]) -> dict[str, str]:
    return {
        key: _normalize_megacap_value(value)
        for key, value in raw_table.items()
    }


def _classify_opening_state(packet: HistoricalPacket) -> OpeningState:
    return {
        "Open-Drive": "open_drive",
        "Open-Test-Drive": "open_test_drive",
        "Open-Rejection-Reverse": "open_rejection_reverse",
        "Open-Auction": "open_auction",
        "NOT_YET_CLASSIFIED": "not_yet_classified",
    }[packet.market_packet.opening_type]


def _classify_range_expansion(packet: HistoricalPacket) -> RangeExpansionState:
    if packet.market_packet.avg_20d_session_range <= 0:
        raise ValueError("market_packet_json.avg_20d_session_range must be positive for Watchman.")
    if packet.market_packet.session_range < 0:
        raise ValueError("market_packet_json.session_range must be non-negative for Watchman.")
    ratio = packet.market_packet.session_range / packet.market_packet.avg_20d_session_range
    if ratio >= 1.2:
        return "expanded"
    if ratio <= 0.8:
        return "compressed"
    return "normal"


def _classify_volume_participation(packet: HistoricalPacket) -> VolumeParticipationState:
    volume_ratio = packet.market_packet.current_volume_vs_average
    if volume_ratio >= 1.15:
        return "elevated"
    if volume_ratio <= 0.85:
        return "subdued"
    return "normal"


def _classify_delta_agreement(packet: HistoricalPacket) -> DeltaAgreementState:
    price_change = packet.market_packet.current_price - packet.market_packet.session_open
    cumulative_delta = packet.market_packet.cumulative_delta
    if abs(price_change) < packet.contract_metadata.tick_size and abs(cumulative_delta) < 1e-6:
        return "neutral"
    if price_change > 0 and cumulative_delta > 0:
        return "bullish_agreement"
    if price_change < 0 and cumulative_delta < 0:
        return "bearish_agreement"
    return "mixed"


def _classify_trigger_context(
    packet: HistoricalPacket,
    evaluation_timestamp: datetime,
    readiness_trigger: Mapping[str, Any],
) -> TriggerContextState:
    if readiness_trigger["trigger_family"] == "recheck_at_time":
        recheck_time = datetime.fromisoformat(
            str(readiness_trigger["recheck_at_time"]).replace("Z", "+00:00")
        )
        if evaluation_timestamp >= recheck_time:
            return "scheduled_recheck_due"
        return "scheduled_recheck_pending"

    price_level = float(readiness_trigger["price_level"])
    delta = packet.market_packet.current_price - price_level
    threshold = packet.contract_metadata.tick_size / 2
    if abs(delta) <= threshold:
        return "at_trigger_level"
    if packet.market_packet.current_price > price_level:
        return "above_trigger_level"
    return "below_trigger_level"


def _compute_trigger_proximity(
    packet: HistoricalPacket,
    evaluation_timestamp: datetime,
    readiness_trigger: Mapping[str, Any],
) -> TriggerProximity:
    if readiness_trigger["trigger_family"] == "recheck_at_time":
        recheck_time = datetime.fromisoformat(
            str(readiness_trigger["recheck_at_time"]).replace("Z", "+00:00")
        )
        return TriggerProximity(
            trigger_family="recheck_at_time",
            time_distance_minutes=(recheck_time - evaluation_timestamp).total_seconds() / 60,
        )

    price_level = float(readiness_trigger["price_level"])
    return TriggerProximity(
        trigger_family="price_level_touch",
        price_distance_ticks=(
            (packet.market_packet.current_price - price_level) / packet.contract_metadata.tick_size
        ),
    )


def _trigger_rationale(
    packet: HistoricalPacket,
    evaluation_timestamp: datetime,
    readiness_trigger: Mapping[str, Any],
    trigger_context_state: TriggerContextState,
) -> str:
    if readiness_trigger["trigger_family"] == "recheck_at_time":
        return (
            f"Recheck trigger is {trigger_context_state.replace('_', ' ')} relative to "
            f"evaluation timestamp {evaluation_timestamp.isoformat()}."
        )
    return (
        f"Current price {packet.market_packet.current_price} is "
        f"{trigger_context_state.replace('_', ' ')} "
        f"relative to trigger level {float(readiness_trigger['price_level'])}."
    )


def _classify_event_risk(
    packet: HistoricalPacket,
    hard_lockout_flags: set[str],
    awareness_flags: set[str],
    rationales: dict[str, str],
) -> EventRiskState:
    before_minutes = packet.challenge_state.event_lockout_minutes_before
    after_minutes = packet.challenge_state.event_lockout_minutes_after
    event_risk_state: EventRiskState = "clear"
    reasons: list[str] = []

    for event in packet.market_packet.event_calendar_remainder:
        if event.tier != 1:
            continue
        if event.event_state == "upcoming" and event.minutes_until is not None:
            reasons.append(f"{event.name} in {event.minutes_until}m")
            if event.minutes_until <= before_minutes:
                event_risk_state = "lockout_active"
                hard_lockout_flags.add("event_lockout_active")
            elif event.minutes_until <= WATCHMAN_EVENT_ELEVATED_WINDOW_MINUTES:
                event_risk_state = "elevated"
                awareness_flags.add("event_risk_elevated")
        if event.event_state == "released" and event.minutes_since is not None:
            reasons.append(f"{event.name} released {event.minutes_since}m ago")
            if event.minutes_since <= after_minutes:
                event_risk_state = "lockout_active"
                hard_lockout_flags.add("event_lockout_active")
            elif event.minutes_since <= WATCHMAN_EVENT_ELEVATED_WINDOW_MINUTES:
                event_risk_state = "elevated"
                awareness_flags.add("event_risk_elevated")

    extension = packet.contract_specific_extension
    if isinstance(extension, CLContractSpecificExtension):
        eia = extension.eia_timing
        if eia.status == "scheduled" and eia.minutes_until is not None:
            reasons.append(f"EIA in {eia.minutes_until}m")
            if eia.minutes_until <= before_minutes:
                event_risk_state = "lockout_active"
                hard_lockout_flags.add("event_lockout_active")
            elif eia.minutes_until <= WATCHMAN_EVENT_ELEVATED_WINDOW_MINUTES:
                event_risk_state = "elevated"
                awareness_flags.add("event_risk_elevated")
        if eia.status == "released" and eia.minutes_since is not None:
            reasons.append(f"EIA released {eia.minutes_since}m ago")
            if eia.minutes_since <= after_minutes:
                event_risk_state = "lockout_active"
                hard_lockout_flags.add("event_lockout_active")
            elif eia.minutes_since <= WATCHMAN_EVENT_ELEVATED_WINDOW_MINUTES:
                event_risk_state = "elevated"
                awareness_flags.add("event_risk_elevated")

    rationales["event_risk_state"] = (
        "; ".join(reasons) if reasons else "No tier-1 or contract-critical event risk is active."
    )
    return event_risk_state


def _apply_governance_flags(
    packet: HistoricalPacket,
    evaluation_timestamp: datetime,
    hard_lockout_flags: set[str],
    awareness_flags: set[str],
    rationales: dict[str, str],
) -> None:
    contract = packet.market_packet.contract
    challenge_state = packet.challenge_state
    trade_counts = challenge_state.trades_today_by_contract.model_dump(mode="python", by_alias=True)
    max_sizes = challenge_state.max_position_size_by_contract.model_dump(mode="python", by_alias=True)
    last_stopouts = (
        challenge_state.last_stopout_time_by_contract.model_dump(mode="python", by_alias=True)
        if challenge_state.last_stopout_time_by_contract is not None
        else {}
    )

    if challenge_state.daily_realized_pnl <= -abs(challenge_state.daily_loss_stop_dollars):
        hard_lockout_flags.add("daily_loss_stop_reached")
    if challenge_state.trades_today_all >= challenge_state.max_trades_per_day:
        hard_lockout_flags.add("max_trades_reached")
    if trade_counts[contract] >= challenge_state.max_trades_per_contract_per_day:
        hard_lockout_flags.add("contract_trade_limit_reached")

    contract_open_size = sum(
        position.size for position in challenge_state.current_open_positions if position.contract == contract
    )
    if contract_open_size >= max_sizes[contract]:
        hard_lockout_flags.add("max_position_size_reached")

    last_stopout_time = last_stopouts.get(contract)
    if isinstance(last_stopout_time, datetime):
        cooldown_end = last_stopout_time + timedelta(
            minutes=challenge_state.cooldown_after_stopout_minutes
        )
        if evaluation_timestamp < cooldown_end:
            hard_lockout_flags.add("cooldown_active")
    if challenge_state.current_open_positions:
        awareness_flags.add("open_positions_present")

    rationales["hard_lockout_flags"] = (
        ", ".join(sorted(hard_lockout_flags)) if hard_lockout_flags else "No hard lockout flags."
    )


def _classify_contract_specific_macro_state(
    packet: HistoricalPacket,
    evaluation_timestamp: datetime,
    awareness_flags: set[str],
    rationales: dict[str, str],
) -> ContractSpecificMacroState:
    contract = packet.market_packet.contract
    extension = packet.contract_specific_extension

    if isinstance(extension, ESContractSpecificExtension):
        breadth = extension.breadth.lower()
        breadth_positive = "positive" in breadth or breadth.startswith("+")
        breadth_negative = "negative" in breadth or breadth.startswith("-")
        price_up = packet.market_packet.current_price >= packet.market_packet.session_open
        if (
            price_up
            and breadth_positive
            and extension.index_cash_tone == "bullish"
            and packet.market_packet.cumulative_delta >= 0
        ):
            state = "breadth_cash_delta_aligned"
        elif (
            not price_up
            and breadth_negative
            and extension.index_cash_tone == "bearish"
            and packet.market_packet.cumulative_delta <= 0
        ):
            state = "breadth_cash_delta_aligned"
        elif extension.index_cash_tone in {"flat", "choppy"}:
            state = "cash_tone_unsettled"
            awareness_flags.add("cash_tone_unsettled")
        else:
            state = "breadth_cash_divergent"
            awareness_flags.add("breadth_cash_divergent")
        rationales["contract_specific_macro_state"] = (
            f"ES breadth is '{extension.breadth}', cash tone is {extension.index_cash_tone}, "
            f"and cumulative delta is {packet.market_packet.cumulative_delta:.2f}."
        )
        return state

    if isinstance(extension, NQContractSpecificExtension):
        megacap_table = extension.megacap_leadership_table or {}
        normalized_table = _normalize_megacap_table(megacap_table)
        up_count = sum(1 for value in normalized_table.values() if value == "up")
        down_count = sum(1 for value in normalized_table.values() if value == "down")
        if extension.relative_strength_vs_es >= 1.02 and up_count >= down_count:
            state = "relative_strength_leader"
            awareness_flags.add("nq_relative_strength_leader")
        elif extension.relative_strength_vs_es <= 0.98 or down_count > up_count:
            state = "relative_strength_fragile"
            awareness_flags.add("nq_relative_strength_fragile")
        else:
            state = "mixed_tech_tone"
        if not megacap_table:
            awareness_flags.add("megacap_leadership_unavailable")
        cross_market_context = packet.market_packet.cross_market_context or {}
        if str(cross_market_context.get("bond_yield_direction", "")).lower() == "rising":
            awareness_flags.add("yield_headwind")
        rationales["contract_specific_macro_state"] = (
            f"NQ relative_strength_vs_es is {extension.relative_strength_vs_es:.4f}; "
            f"megacap table entries: {len(megacap_table)}."
        )
        return state

    if isinstance(extension, CLContractSpecificExtension):
        if extension.eia_timing.status in {"scheduled", "released"}:
            state = "eia_sensitive"
            awareness_flags.add("eia_timing_active")
        elif extension.realized_volatility_context == "elevated":
            state = "volatility_elevated"
            awareness_flags.add("elevated_realized_volatility")
        elif extension.liquidity_sweep_summary or extension.dom_liquidity_summary:
            state = "liquidity_sensitive"
            awareness_flags.add("liquidity_instability_monitor")
        else:
            state = "balanced_energy_tone"
        rationales["contract_specific_macro_state"] = (
            f"CL EIA timing is {extension.eia_timing.status}; realized volatility is "
            f"{extension.realized_volatility_context}."
        )
        return state

    if isinstance(extension, ZNContractSpecificExtension):
        flags = packet.market_packet.data_quality_flags or []
        if "auction_proximity_risk" in flags or "today" in extension.treasury_auction_schedule.lower():
            state = "auction_sensitive"
            awareness_flags.add("auction_proximity_risk")
        elif extension.cash_10y_yield >= 4.5:
            state = "high_yield_pressure"
            awareness_flags.add("high_cash_yield")
        else:
            state = "balanced_rates_tone"
        rationales["contract_specific_macro_state"] = (
            f"ZN cash_10y_yield is {extension.cash_10y_yield:.2f}; "
            f"auction schedule is '{extension.treasury_auction_schedule}'."
        )
        return state

    if isinstance(extension, SixEContractSpecificExtension):
        et_timestamp = evaluation_timestamp.astimezone(ET_TZ)
        london_close_start = _et_datetime(et_timestamp, SIXE_LONDON_CLOSE_THINNING_START_ET)
        if et_timestamp >= london_close_start:
            state = "london_close_thinning"
            awareness_flags.add("london_close_thinning")
        elif (
            extension.dxy_context == "weakening"
            and "drove higher" in extension.europe_initiative_status.lower()
            and packet.market_packet.current_price >= extension.asia_high_low.high
        ):
            state = "dxy_supported_europe_drive"
            awareness_flags.add("above_asia_high")
        elif extension.dxy_context == "strengthening":
            state = "dxy_pressure"
            awareness_flags.add("dxy_strengthening")
        else:
            state = "balanced_fx_tone"
        if packet.market_packet.current_price <= extension.asia_high_low.low:
            awareness_flags.add("below_asia_low")
        if packet.market_packet.current_price >= extension.asia_high_low.high:
            awareness_flags.add("above_asia_high")
        rationales["contract_specific_macro_state"] = (
            f"6E DXY context is {extension.dxy_context}; Europe initiative is "
            f"'{extension.europe_initiative_status}'."
        )
        return state

    if isinstance(extension, MGCContractSpecificExtension):
        if extension.dxy_context == "weakening" and extension.yield_context == "falling":
            state = "macro_supportive"
            awareness_flags.add("macro_tailwind")
        elif extension.dxy_context == "strengthening" or extension.yield_context == "rising":
            state = "macro_headwind"
            awareness_flags.add("macro_headwind")
        else:
            state = "mixed_precious_metals_tone"
        if extension.swing_penetration_volume_summary:
            awareness_flags.add("swing_penetration_volume_context")
        if extension.macro_fear_catalyst_summary.lower() != "none":
            awareness_flags.add("fear_catalyst_active")
        rationales["contract_specific_macro_state"] = (
            f"MGC DXY context is {extension.dxy_context}; yield context is "
            f"{extension.yield_context}."
        )
        return state

    raise ValueError(f"Watchman received unsupported contract extension for {contract}.")
