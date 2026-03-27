from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from ..schemas.contracts import NQContractMetadata
from ..validation import validate_historical_packet
from .es import CompiledPacketArtifact
from .models import (
    NQContractExtensionInput,
    NQHistoricalDataInput,
    NQManualOverlayInput,
    NQRelativeStrengthComparisonInput,
)

NQ_CANONICAL_CONTRACT_METADATA = NQContractMetadata.model_validate(
    {
        "$schema": "contract_metadata_v1",
        "contract": "NQ",
        "tick_size": 0.25,
        "dollar_per_tick": 5.0,
        "point_value": 20.0,
        "max_position_size": 2,
        "slippage_ticks": 1,
        "allowed_hours_start_et": "09:30",
        "allowed_hours_end_et": "15:45",
    }
)


def _coerce_historical_input(
    payload: NQHistoricalDataInput | Mapping[str, Any],
) -> NQHistoricalDataInput:
    if isinstance(payload, NQHistoricalDataInput):
        return payload
    return NQHistoricalDataInput.model_validate(dict(payload))


def _coerce_overlay_input(
    payload: NQManualOverlayInput | Mapping[str, Any],
) -> NQManualOverlayInput:
    if isinstance(payload, NQManualOverlayInput):
        return payload
    return NQManualOverlayInput.model_validate(dict(payload))


def _coerce_extension_input(
    payload: NQContractExtensionInput | Mapping[str, Any],
) -> NQContractExtensionInput:
    if isinstance(payload, NQContractExtensionInput):
        return payload
    return NQContractExtensionInput.model_validate(dict(payload))


def _coerce_relative_strength_input(
    payload: NQRelativeStrengthComparisonInput | Mapping[str, Any],
) -> NQRelativeStrengthComparisonInput:
    if isinstance(payload, NQRelativeStrengthComparisonInput):
        return payload
    return NQRelativeStrengthComparisonInput.model_validate(dict(payload))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _derive_relative_strength_vs_es(
    historical: NQHistoricalDataInput,
    comparison: NQRelativeStrengthComparisonInput,
) -> float:
    if comparison.es_timestamp != historical.timestamp:
        raise ValueError(
            "NQ relative strength comparison input must use the same timestamp as NQ historical input."
        )
    nq_multiplier = historical.current_price / historical.session_open
    es_multiplier = comparison.es_current_price / comparison.es_session_open
    if es_multiplier <= 0:
        raise ValueError("Derived ES session-performance multiplier must be > 0.")
    return round(nq_multiplier / es_multiplier, 4)


def _overlay_provenance(
    overlay: NQManualOverlayInput,
    field_name: str,
    *,
    assist_derivation: str | None = None,
) -> dict[str, str]:
    if field_name in overlay.model_fields_set:
        return {"source": "manual_overlay", "field": field_name}
    provenance = {"source": "overlay_assist", "field": field_name}
    if assist_derivation is not None:
        provenance["derivation"] = assist_derivation
    return provenance


def _build_field_provenance(overlay: NQManualOverlayInput) -> dict[str, dict[str, str]]:
    return {
        "challenge_state": {"source": "manual_overlay", "field": "challenge_state"},
        "attached_visuals": _overlay_provenance(
            overlay,
            "attached_visuals",
            assist_derivation="default all visuals to false when omitted",
        ),
        "contract_metadata": {
            "source": "compiler_constant",
            "field": "NQ_CANONICAL_CONTRACT_METADATA",
        },
        "market_packet.timestamp": {"source": "historical_input", "field": "timestamp"},
        "market_packet.contract": {"source": "compiler_constant", "field": "NQ"},
        "market_packet.session_type": {"source": "compiler_constant", "field": "RTH"},
        "market_packet.current_price": {"source": "historical_input", "field": "current_price"},
        "market_packet.session_open": {"source": "historical_input", "field": "session_open"},
        "market_packet.prior_day_high": {"source": "historical_input", "field": "prior_day_high"},
        "market_packet.prior_day_low": {"source": "historical_input", "field": "prior_day_low"},
        "market_packet.prior_day_close": {"source": "historical_input", "field": "prior_day_close"},
        "market_packet.overnight_high": {"source": "historical_input", "field": "overnight_high"},
        "market_packet.overnight_low": {"source": "historical_input", "field": "overnight_low"},
        "market_packet.current_session_vah": {"source": "historical_input", "field": "current_session_vah"},
        "market_packet.current_session_val": {"source": "historical_input", "field": "current_session_val"},
        "market_packet.current_session_poc": {"source": "historical_input", "field": "current_session_poc"},
        "market_packet.previous_session_vah": {"source": "historical_input", "field": "previous_session_vah"},
        "market_packet.previous_session_val": {"source": "historical_input", "field": "previous_session_val"},
        "market_packet.previous_session_poc": {"source": "historical_input", "field": "previous_session_poc"},
        "market_packet.vwap": {"source": "historical_input", "field": "vwap"},
        "market_packet.session_range": {"source": "historical_input", "field": "session_range"},
        "market_packet.avg_20d_session_range": {"source": "historical_input", "field": "avg_20d_session_range"},
        "market_packet.cumulative_delta": {"source": "historical_input", "field": "cumulative_delta"},
        "market_packet.current_volume_vs_average": {
            "source": "historical_input",
            "field": "current_volume_vs_average",
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
        "market_packet.event_calendar_remainder": {"source": "historical_input", "field": "event_calendar_remainder"},
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
        "contract_specific_extension.contract": {"source": "compiler_constant", "field": "NQ"},
        "contract_specific_extension.relative_strength_vs_es": {
            "source": "comparative_input",
            "field": "es_current_price",
            "derivation": (
                "derive as (NQ current_price / NQ session_open) / "
                "(ES current_price / ES session_open)"
            ),
        },
        "contract_specific_extension.megacap_leadership_table": {
            "source": "upstream_extension",
            "field": "megacap_leadership_table",
        },
    }


def compile_nq_packet(
    historical_input: NQHistoricalDataInput | Mapping[str, Any],
    overlay: NQManualOverlayInput | Mapping[str, Any],
    relative_strength_input: NQRelativeStrengthComparisonInput | Mapping[str, Any],
    extension_input: NQContractExtensionInput | Mapping[str, Any],
    *,
    compiled_at_iso: str | None = None,
) -> CompiledPacketArtifact:
    historical = _coerce_historical_input(historical_input)
    manual_overlay = _coerce_overlay_input(overlay)
    relative_strength = _coerce_relative_strength_input(relative_strength_input)
    extension = _coerce_extension_input(extension_input)
    relative_strength_vs_es = _derive_relative_strength_vs_es(historical, relative_strength)

    packet_payload = {
        "$schema": "historical_packet_v1",
        "challenge_state": manual_overlay.challenge_state.model_dump(by_alias=True, mode="json"),
        "contract_metadata": NQ_CANONICAL_CONTRACT_METADATA.model_dump(by_alias=True, mode="json"),
        "market_packet": {
            "$schema": "market_packet_v1",
            "timestamp": historical.timestamp,
            "contract": "NQ",
            "session_type": "RTH",
            "current_price": historical.current_price,
            "session_open": historical.session_open,
            "prior_day_high": historical.prior_day_high,
            "prior_day_low": historical.prior_day_low,
            "prior_day_close": historical.prior_day_close,
            "overnight_high": historical.overnight_high,
            "overnight_low": historical.overnight_low,
            "current_session_vah": historical.current_session_vah,
            "current_session_val": historical.current_session_val,
            "current_session_poc": historical.current_session_poc,
            "previous_session_vah": historical.previous_session_vah,
            "previous_session_val": historical.previous_session_val,
            "previous_session_poc": historical.previous_session_poc,
            "vwap": historical.vwap,
            "session_range": historical.session_range,
            "avg_20d_session_range": historical.avg_20d_session_range,
            "cumulative_delta": historical.cumulative_delta,
            "current_volume_vs_average": historical.current_volume_vs_average,
            "opening_type": manual_overlay.opening_type,
            "major_higher_timeframe_levels": manual_overlay.major_higher_timeframe_levels,
            "key_hvns": manual_overlay.key_hvns,
            "key_lvns": manual_overlay.key_lvns,
            "singles_excess_poor_high_low_notes": manual_overlay.singles_excess_poor_high_low_notes,
            "event_calendar_remainder": [
                event.model_dump(by_alias=True, mode="json")
                for event in historical.event_calendar_remainder
            ],
            "cross_market_context": manual_overlay.cross_market_context,
            "data_quality_flags": manual_overlay.data_quality_flags,
        },
        "contract_specific_extension": {
            "$schema": "contract_specific_extension_v1",
            "contract": "NQ",
            "relative_strength_vs_es": relative_strength_vs_es,
            "megacap_leadership_table": extension.megacap_leadership_table,
        },
        "attached_visuals": manual_overlay.attached_visuals.model_dump(by_alias=True, mode="json"),
    }
    packet = validate_historical_packet(packet_payload)
    provenance = {
        "compiler_schema": "packet_compiler_provenance_v1",
        "contract": "NQ",
        "compiled_at": compiled_at_iso or _utc_now_iso(),
        "packet_schema": "historical_packet_v1",
        "field_provenance": _build_field_provenance(manual_overlay),
        "derived_features": {
            "relative_strength_vs_es": {
                "value": relative_strength_vs_es,
                "formula": "(NQ current_price / NQ session_open) / (ES current_price / ES session_open)",
            }
        },
    }
    return CompiledPacketArtifact(packet=packet, provenance=provenance)
