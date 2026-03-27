from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from ..schemas.contracts import ESContractMetadata
from ..schemas.packet import HistoricalPacket
from ..validation import validate_historical_packet
from .models import (
    ESBreadthSourceInput,
    ESCalendarSourceInput,
    ESCumulativeDeltaSourceInput,
    ESHistoricalDataInput,
    ESIndexCashToneSourceInput,
    ESManualOverlayInput,
    HistoricalBar,
    VolumeProfileLevel,
)

ES_CANONICAL_CONTRACT_METADATA = ESContractMetadata.model_validate(
    {
        "$schema": "contract_metadata_v1",
        "contract": "ES",
        "tick_size": 0.25,
        "dollar_per_tick": 12.5,
        "point_value": 50.0,
        "max_position_size": 2,
        "slippage_ticks": 1,
        "allowed_hours_start_et": "09:30",
        "allowed_hours_end_et": "15:45",
    }
)
INITIAL_BALANCE_WINDOW_MINUTES = 60
MIN_INITIAL_BALANCE_OBSERVED_SPAN_MINUTES = 30
PROFILE_VALUE_AREA_FRACTION = 0.70


@dataclass(frozen=True)
class CompiledPacketArtifact:
    packet: HistoricalPacket
    provenance: dict[str, Any]


def _coerce_historical_input(
    payload: ESHistoricalDataInput | Mapping[str, Any],
) -> ESHistoricalDataInput:
    if isinstance(payload, ESHistoricalDataInput):
        return payload
    return ESHistoricalDataInput.model_validate(dict(payload))


def _coerce_overlay_input(payload: ESManualOverlayInput | Mapping[str, Any]) -> ESManualOverlayInput:
    if isinstance(payload, ESManualOverlayInput):
        return payload
    return ESManualOverlayInput.model_validate(dict(payload))


def _coerce_calendar_input(
    payload: ESCalendarSourceInput | Mapping[str, Any],
) -> ESCalendarSourceInput:
    if isinstance(payload, ESCalendarSourceInput):
        return payload
    return ESCalendarSourceInput.model_validate(dict(payload))


def _coerce_breadth_input(
    payload: ESBreadthSourceInput | Mapping[str, Any],
) -> ESBreadthSourceInput:
    if isinstance(payload, ESBreadthSourceInput):
        return payload
    return ESBreadthSourceInput.model_validate(dict(payload))


def _coerce_index_cash_tone_input(
    payload: ESIndexCashToneSourceInput | Mapping[str, Any],
) -> ESIndexCashToneSourceInput:
    if isinstance(payload, ESIndexCashToneSourceInput):
        return payload
    return ESIndexCashToneSourceInput.model_validate(dict(payload))


def _coerce_cumulative_delta_input(
    payload: ESCumulativeDeltaSourceInput | Mapping[str, Any],
) -> ESCumulativeDeltaSourceInput:
    if isinstance(payload, ESCumulativeDeltaSourceInput):
        return payload
    return ESCumulativeDeltaSourceInput.model_validate(dict(payload))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _first_open(bars: list[HistoricalBar]) -> float:
    return bars[0].open


def _last_close(bars: list[HistoricalBar]) -> float:
    return bars[-1].close


def _last_timestamp(bars: list[HistoricalBar]) -> datetime:
    return bars[-1].timestamp


def _max_high(bars: list[HistoricalBar]) -> float:
    return max(bar.high for bar in bars)


def _min_low(bars: list[HistoricalBar]) -> float:
    return min(bar.low for bar in bars)


def _session_range(bars: list[HistoricalBar]) -> float:
    return _max_high(bars) - _min_low(bars)


def _average_session_range(historical: ESHistoricalDataInput) -> float:
    total = sum(session.high - session.low for session in historical.prior_20_rth_sessions)
    return round(total / len(historical.prior_20_rth_sessions), 4)


def _current_volume_vs_average(historical: ESHistoricalDataInput) -> float:
    current_observed_volume = sum(bar.volume for bar in historical.current_rth_bars)
    average_observed_volume = (
        sum(session.observed_volume for session in historical.prior_20_rth_observed_volumes)
        / len(historical.prior_20_rth_observed_volumes)
    )
    return round(current_observed_volume / average_observed_volume, 4)


def _vwap(bars: list[HistoricalBar]) -> float:
    total_volume = sum(bar.volume for bar in bars)
    total_value = sum((((bar.high + bar.low + bar.close) / 3.0) * bar.volume) for bar in bars)
    return round(total_value / total_volume, 4)


def _initial_balance_bars(bars: list[HistoricalBar]) -> list[HistoricalBar]:
    window_start = bars[0].timestamp
    window_end = window_start + timedelta(minutes=INITIAL_BALANCE_WINDOW_MINUTES)
    ib_bars = [bar for bar in bars if window_start <= bar.timestamp < window_end]
    if len(ib_bars) < 2:
        raise ValueError(
            "Current RTH bars must contain at least two bars inside the first 60 minutes "
            "to derive initial balance."
        )
    observed_span = ib_bars[-1].timestamp - ib_bars[0].timestamp
    if observed_span < timedelta(minutes=MIN_INITIAL_BALANCE_OBSERVED_SPAN_MINUTES):
        raise ValueError(
            "Current RTH bars must span at least 30 minutes inside the first 60 minutes "
            "to derive initial balance."
        )
    return ib_bars


def _profile_session_midpoint(levels: list[VolumeProfileLevel]) -> float:
    return (levels[0].price + levels[-1].price) / 2.0


def _profile_poc_index(levels: list[VolumeProfileLevel]) -> int:
    max_volume = max(level.volume for level in levels)
    candidates = [index for index, level in enumerate(levels) if level.volume == max_volume]
    midpoint = _profile_session_midpoint(levels)
    return min(candidates, key=lambda index: (abs(levels[index].price - midpoint), levels[index].price))


def _choose_profile_expansion_side(
    levels: list[VolumeProfileLevel],
    *,
    lower_index: int | None,
    upper_index: int | None,
) -> str:
    if lower_index is None:
        return "upper"
    if upper_index is None:
        return "lower"

    lower_volume = levels[lower_index].volume
    upper_volume = levels[upper_index].volume
    if upper_volume > lower_volume:
        return "upper"
    if lower_volume > upper_volume:
        return "lower"

    midpoint = _profile_session_midpoint(levels)
    lower_distance = abs(levels[lower_index].price - midpoint)
    upper_distance = abs(levels[upper_index].price - midpoint)
    if lower_distance < upper_distance:
        return "lower"
    if upper_distance < lower_distance:
        return "upper"
    return "lower"


def _derive_profile_levels(levels: list[VolumeProfileLevel]) -> dict[str, float]:
    total_volume = sum(level.volume for level in levels)
    target_volume = total_volume * PROFILE_VALUE_AREA_FRACTION
    poc_index = _profile_poc_index(levels)
    included_indices = {poc_index}
    cumulative_volume = levels[poc_index].volume
    low_index = poc_index
    high_index = poc_index

    while cumulative_volume < target_volume:
        candidate_lower = low_index - 1 if low_index > 0 else None
        candidate_upper = high_index + 1 if high_index < len(levels) - 1 else None
        if candidate_lower is None and candidate_upper is None:
            break
        chosen_side = _choose_profile_expansion_side(
            levels,
            lower_index=candidate_lower,
            upper_index=candidate_upper,
        )
        if chosen_side == "lower":
            assert candidate_lower is not None
            included_indices.add(candidate_lower)
            cumulative_volume += levels[candidate_lower].volume
            low_index = candidate_lower
        else:
            assert candidate_upper is not None
            included_indices.add(candidate_upper)
            cumulative_volume += levels[candidate_upper].volume
            high_index = candidate_upper

    selected_levels = [levels[index] for index in sorted(included_indices)]
    return {
        "poc": levels[poc_index].price,
        "vah": selected_levels[-1].price,
        "val": selected_levels[0].price,
    }


def _overlay_provenance(overlay: ESManualOverlayInput, field_name: str, *, assist_derivation: str | None = None) -> dict[str, str]:
    if field_name in overlay.model_fields_set:
        return {"source": "manual_overlay", "field": field_name}
    provenance = {"source": "overlay_assist", "field": field_name}
    if assist_derivation is not None:
        provenance["derivation"] = assist_derivation
    return provenance


def _build_field_provenance(overlay: ESManualOverlayInput) -> dict[str, dict[str, str]]:
    return {
        "challenge_state": {"source": "manual_overlay", "field": "challenge_state"},
        "attached_visuals": _overlay_provenance(
            overlay,
            "attached_visuals",
            assist_derivation="default all visuals to false when omitted",
        ),
        "contract_metadata": {
            "source": "compiler_constant",
            "field": "ES_CANONICAL_CONTRACT_METADATA",
        },
        "market_packet.timestamp": {
            "source": "historical_bars",
            "field": "current_rth_bars",
            "derivation": "last(timestamp)",
        },
        "market_packet.contract": {"source": "compiler_constant", "field": "ES"},
        "market_packet.session_type": {"source": "compiler_constant", "field": "RTH"},
        "market_packet.current_price": {
            "source": "historical_bars",
            "field": "current_rth_bars",
            "derivation": "last(close)",
        },
        "market_packet.session_open": {
            "source": "historical_bars",
            "field": "current_rth_bars",
            "derivation": "first(open)",
        },
        "market_packet.prior_day_high": {
            "source": "historical_bars",
            "field": "prior_rth_bars",
            "derivation": "max(high)",
        },
        "market_packet.prior_day_low": {
            "source": "historical_bars",
            "field": "prior_rth_bars",
            "derivation": "min(low)",
        },
        "market_packet.prior_day_close": {
            "source": "historical_bars",
            "field": "prior_rth_bars",
            "derivation": "last(close)",
        },
        "market_packet.overnight_high": {
            "source": "historical_bars",
            "field": "overnight_bars",
            "derivation": "max(high)",
        },
        "market_packet.overnight_low": {
            "source": "historical_bars",
            "field": "overnight_bars",
            "derivation": "min(low)",
        },
        "market_packet.current_session_vah": {
            "source": "historical_profile",
            "field": "current_rth_volume_profile",
            "derivation": "70% value area high around POC",
        },
        "market_packet.current_session_val": {
            "source": "historical_profile",
            "field": "current_rth_volume_profile",
            "derivation": "70% value area low around POC",
        },
        "market_packet.current_session_poc": {
            "source": "historical_profile",
            "field": "current_rth_volume_profile",
            "derivation": "max volume price with midpoint/lower tie-break",
        },
        "market_packet.previous_session_vah": {
            "source": "historical_profile",
            "field": "prior_rth_volume_profile",
            "derivation": "70% value area high around POC",
        },
        "market_packet.previous_session_val": {
            "source": "historical_profile",
            "field": "prior_rth_volume_profile",
            "derivation": "70% value area low around POC",
        },
        "market_packet.previous_session_poc": {
            "source": "historical_profile",
            "field": "prior_rth_volume_profile",
            "derivation": "max volume price with midpoint/lower tie-break",
        },
        "market_packet.vwap": {
            "source": "historical_bars",
            "field": "current_rth_bars",
            "derivation": "volume_weighted_typical_price",
        },
        "market_packet.session_range": {
            "source": "historical_bars",
            "field": "current_rth_bars",
            "derivation": "max(high)-min(low)",
        },
        "market_packet.avg_20d_session_range": {
            "source": "historical_lookback",
            "field": "prior_20_rth_sessions",
            "derivation": "arithmetic mean of (high-low) across 20 completed prior RTH sessions",
        },
        "market_packet.cumulative_delta": {
            "source": "upstream_cumulative_delta",
            "field": "cumulative_delta",
        },
        "market_packet.current_volume_vs_average": {
            "source": "historical_lookback",
            "field": "prior_20_rth_observed_volumes",
            "derivation": (
                "current observed RTH volume divided by the arithmetic mean of observed volume "
                "across 20 prior matched-window RTH sessions"
            ),
        },
        "market_packet.opening_type": _overlay_provenance(overlay, "opening_type"),
        "market_packet.major_higher_timeframe_levels": _overlay_provenance(
            overlay,
            "major_higher_timeframe_levels",
            assist_derivation="default to null when omitted",
        ),
        "market_packet.key_hvns": _overlay_provenance(
            overlay,
            "key_hvns",
            assist_derivation="default to null when omitted",
        ),
        "market_packet.key_lvns": _overlay_provenance(
            overlay,
            "key_lvns",
            assist_derivation="default to null when omitted",
        ),
        "market_packet.singles_excess_poor_high_low_notes": _overlay_provenance(
            overlay,
            "singles_excess_poor_high_low_notes",
            assist_derivation="default to null when omitted",
        ),
        "market_packet.event_calendar_remainder": {
            "source": "upstream_calendar",
            "field": "event_calendar_remainder",
        },
        "market_packet.cross_market_context": _overlay_provenance(
            overlay,
            "cross_market_context",
            assist_derivation="default to null when omitted",
        ),
        "market_packet.data_quality_flags": _overlay_provenance(
            overlay,
            "data_quality_flags",
            assist_derivation="default to [] when omitted",
        ),
        "contract_specific_extension.contract": {"source": "compiler_constant", "field": "ES"},
        "contract_specific_extension.breadth": {
            "source": "upstream_breadth",
            "field": "breadth",
        },
        "contract_specific_extension.index_cash_tone": {
            "source": "upstream_index_cash_tone",
            "field": "index_cash_tone",
        },
    }


def compile_es_packet(
    historical_input: ESHistoricalDataInput | Mapping[str, Any],
    overlay: ESManualOverlayInput | Mapping[str, Any],
    calendar_input: ESCalendarSourceInput | Mapping[str, Any],
    breadth_input: ESBreadthSourceInput | Mapping[str, Any],
    index_cash_tone_input: ESIndexCashToneSourceInput | Mapping[str, Any],
    cumulative_delta_input: ESCumulativeDeltaSourceInput | Mapping[str, Any],
    *,
    compiled_at_iso: str | None = None,
) -> CompiledPacketArtifact:
    historical = _coerce_historical_input(historical_input)
    manual_overlay = _coerce_overlay_input(overlay)
    calendar = _coerce_calendar_input(calendar_input)
    breadth = _coerce_breadth_input(breadth_input)
    index_cash_tone = _coerce_index_cash_tone_input(index_cash_tone_input)
    cumulative_delta = _coerce_cumulative_delta_input(cumulative_delta_input)
    ib_bars = _initial_balance_bars(historical.current_rth_bars)
    current_profile = _derive_profile_levels(historical.current_rth_volume_profile)
    previous_profile = _derive_profile_levels(historical.prior_rth_volume_profile)
    avg_20d_session_range = _average_session_range(historical)
    current_volume_vs_average = _current_volume_vs_average(historical)
    current_observed_volume = sum(bar.volume for bar in historical.current_rth_bars)

    packet_payload = {
        "$schema": "historical_packet_v1",
        "challenge_state": manual_overlay.challenge_state.model_dump(by_alias=True, mode="json"),
        "contract_metadata": ES_CANONICAL_CONTRACT_METADATA.model_dump(by_alias=True, mode="json"),
        "market_packet": {
            "$schema": "market_packet_v1",
            "timestamp": _last_timestamp(historical.current_rth_bars),
            "contract": "ES",
            "session_type": "RTH",
            "current_price": _last_close(historical.current_rth_bars),
            "session_open": _first_open(historical.current_rth_bars),
            "prior_day_high": _max_high(historical.prior_rth_bars),
            "prior_day_low": _min_low(historical.prior_rth_bars),
            "prior_day_close": _last_close(historical.prior_rth_bars),
            "overnight_high": _max_high(historical.overnight_bars),
            "overnight_low": _min_low(historical.overnight_bars),
            "current_session_vah": current_profile["vah"],
            "current_session_val": current_profile["val"],
            "current_session_poc": current_profile["poc"],
            "previous_session_vah": previous_profile["vah"],
            "previous_session_val": previous_profile["val"],
            "previous_session_poc": previous_profile["poc"],
            "vwap": _vwap(historical.current_rth_bars),
            "session_range": _session_range(historical.current_rth_bars),
            "avg_20d_session_range": avg_20d_session_range,
            "cumulative_delta": cumulative_delta.cumulative_delta,
            "current_volume_vs_average": current_volume_vs_average,
            "opening_type": manual_overlay.opening_type,
            "major_higher_timeframe_levels": manual_overlay.major_higher_timeframe_levels,
            "key_hvns": manual_overlay.key_hvns,
            "key_lvns": manual_overlay.key_lvns,
            "singles_excess_poor_high_low_notes": manual_overlay.singles_excess_poor_high_low_notes,
            "event_calendar_remainder": [
                event.model_dump(by_alias=True, mode="json")
                for event in calendar.event_calendar_remainder
            ],
            "cross_market_context": manual_overlay.cross_market_context,
            "data_quality_flags": manual_overlay.data_quality_flags,
        },
        "contract_specific_extension": {
            "$schema": "contract_specific_extension_v1",
            "contract": "ES",
            "breadth": breadth.breadth,
            "index_cash_tone": index_cash_tone.index_cash_tone,
        },
        "attached_visuals": manual_overlay.attached_visuals.model_dump(by_alias=True, mode="json"),
    }
    packet = validate_historical_packet(packet_payload)
    provenance = {
        "compiler_schema": "packet_compiler_provenance_v1",
        "contract": "ES",
        "compiled_at": compiled_at_iso or _utc_now_iso(),
        "packet_schema": "historical_packet_v1",
        "field_provenance": _build_field_provenance(manual_overlay),
        "derived_features": {
            "ib_high": {
                "value": _max_high(ib_bars),
                "source": "historical_bars",
                "field": "current_rth_bars",
                "derivation": (
                    "max(high) across current_rth_bars where "
                    "first_timestamp <= timestamp < first_timestamp + 60 minutes"
                ),
            },
            "ib_low": {
                "value": _min_low(ib_bars),
                "source": "historical_bars",
                "field": "current_rth_bars",
                "derivation": (
                    "min(low) across current_rth_bars where "
                    "first_timestamp <= timestamp < first_timestamp + 60 minutes"
                ),
            },
            "ib_range": {
                "value": _session_range(ib_bars),
                "source": "historical_bars",
                "field": "current_rth_bars",
                "derivation": "ib_high-ib_low from the first 60 minutes window",
            },
            "weekly_open": {
                "value": historical.weekly_open_bar.open,
                "source": "historical_bars",
                "field": "weekly_open_bar",
                "derivation": "open",
            },
            "avg_20d_session_range": {
                "source": "historical_lookback",
                "field": "prior_20_rth_sessions",
                "algorithm": "arithmetic mean of (high-low) across 20 completed prior RTH sessions",
                "value": avg_20d_session_range,
            },
            "current_volume_vs_average": {
                "source": "historical_lookback",
                "field": "prior_20_rth_observed_volumes",
                "algorithm": (
                    "sum(current_rth_bars.volume) divided by the arithmetic mean of "
                    "observed_volume across 20 prior matched-window RTH sessions"
                ),
                "current_observed_volume": current_observed_volume,
                "value": current_volume_vs_average,
            },
            "current_session_profile": {
                "source": "historical_profile",
                "field": "current_rth_volume_profile",
                "algorithm": (
                    "POC is the highest-volume price; ties break toward session midpoint, then lower "
                    "price. Value area expands from POC until >=70% of total profile volume, adding "
                    "the higher-volume adjacent side first; ties break toward midpoint, then lower side."
                ),
                "vah": current_profile["vah"],
                "val": current_profile["val"],
                "poc": current_profile["poc"],
            },
            "previous_session_profile": {
                "source": "historical_profile",
                "field": "prior_rth_volume_profile",
                "algorithm": (
                    "POC is the highest-volume price; ties break toward session midpoint, then lower "
                    "price. Value area expands from POC until >=70% of total profile volume, adding "
                    "the higher-volume adjacent side first; ties break toward midpoint, then lower side."
                ),
                "vah": previous_profile["vah"],
                "val": previous_profile["val"],
                "poc": previous_profile["poc"],
            },
        },
    }
    return CompiledPacketArtifact(packet=packet, provenance=provenance)


def write_compiled_packet(
    artifact: CompiledPacketArtifact,
    *,
    output_path: Path,
    provenance_output_path: Path | None = None,
) -> tuple[Path, Path]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_provenance_path = provenance_output_path or output_path.with_suffix(".provenance.json")
    resolved_provenance_path.parent.mkdir(parents=True, exist_ok=True)

    output_path.write_text(
        artifact.packet.model_dump_json(by_alias=True, indent=2),
    )
    resolved_provenance_path.write_text(
        json.dumps(artifact.provenance, indent=2, sort_keys=True)
    )
    return output_path, resolved_provenance_path
