from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from ..schemas.contracts import MGCContractMetadata
from ..validation import validate_historical_packet
from .es import CompiledPacketArtifact
from .models import MGCContractExtensionInput, MGCHistoricalDataInput, MGCManualOverlayInput

MGC_CANONICAL_CONTRACT_METADATA = MGCContractMetadata.model_validate(
    {
        "$schema": "contract_metadata_v1",
        "contract": "MGC",
        "tick_size": 0.1,
        "dollar_per_tick": 1.0,
        "point_value": 10.0,
        "max_position_size": 12,
        "slippage_ticks": 1,
        "allowed_hours_start_et": "08:20",
        "allowed_hours_end_et": "13:15",
    }
)


def _coerce_historical_input(
    payload: MGCHistoricalDataInput | Mapping[str, Any],
) -> MGCHistoricalDataInput:
    if isinstance(payload, MGCHistoricalDataInput):
        return payload
    return MGCHistoricalDataInput.model_validate(dict(payload))


def _coerce_overlay_input(
    payload: MGCManualOverlayInput | Mapping[str, Any],
) -> MGCManualOverlayInput:
    if isinstance(payload, MGCManualOverlayInput):
        return payload
    return MGCManualOverlayInput.model_validate(dict(payload))


def _coerce_extension_input(
    payload: MGCContractExtensionInput | Mapping[str, Any],
) -> MGCContractExtensionInput:
    if isinstance(payload, MGCContractExtensionInput):
        return payload
    return MGCContractExtensionInput.model_validate(dict(payload))


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _overlay_provenance(
    overlay: MGCManualOverlayInput,
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


def _build_field_provenance(overlay: MGCManualOverlayInput) -> dict[str, dict[str, str]]:
    return {
        "challenge_state": {"source": "manual_overlay", "field": "challenge_state"},
        "attached_visuals": _overlay_provenance(
            overlay,
            "attached_visuals",
            assist_derivation="default all visuals to false when omitted",
        ),
        "contract_metadata": {
            "source": "compiler_constant",
            "field": "MGC_CANONICAL_CONTRACT_METADATA",
        },
        "market_packet.timestamp": {"source": "historical_input", "field": "timestamp"},
        "market_packet.contract": {"source": "compiler_constant", "field": "MGC"},
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
        "market_packet.event_calendar_remainder": {
            "source": "historical_input",
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
        "contract_specific_extension.contract": {"source": "compiler_constant", "field": "MGC"},
        "contract_specific_extension.dxy_context": {"source": "upstream_extension", "field": "dxy_context"},
        "contract_specific_extension.yield_context": {"source": "upstream_extension", "field": "yield_context"},
        "contract_specific_extension.swing_penetration_volume_summary": {
            "source": "upstream_extension",
            "field": "swing_penetration_volume_summary",
        },
        "contract_specific_extension.macro_fear_catalyst_summary": {
            "source": "upstream_extension",
            "field": "macro_fear_catalyst_summary",
        },
    }


def compile_mgc_packet(
    historical_input: MGCHistoricalDataInput | Mapping[str, Any],
    overlay: MGCManualOverlayInput | Mapping[str, Any],
    extension_input: MGCContractExtensionInput | Mapping[str, Any],
    *,
    compiled_at_iso: str | None = None,
) -> CompiledPacketArtifact:
    historical = _coerce_historical_input(historical_input)
    manual_overlay = _coerce_overlay_input(overlay)
    extension = _coerce_extension_input(extension_input)

    packet_payload = {
        "$schema": "historical_packet_v1",
        "challenge_state": manual_overlay.challenge_state.model_dump(by_alias=True, mode="json"),
        "contract_metadata": MGC_CANONICAL_CONTRACT_METADATA.model_dump(by_alias=True, mode="json"),
        "market_packet": {
            "$schema": "market_packet_v1",
            "timestamp": historical.timestamp,
            "contract": "MGC",
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
            "contract": "MGC",
            "dxy_context": extension.dxy_context,
            "yield_context": extension.yield_context,
            "swing_penetration_volume_summary": extension.swing_penetration_volume_summary,
            "macro_fear_catalyst_summary": extension.macro_fear_catalyst_summary,
        },
        "attached_visuals": manual_overlay.attached_visuals.model_dump(by_alias=True, mode="json"),
    }
    packet = validate_historical_packet(packet_payload)
    provenance = {
        "compiler_schema": "packet_compiler_provenance_v1",
        "contract": "MGC",
        "compiled_at": compiled_at_iso or _utc_now_iso(),
        "packet_schema": "historical_packet_v1",
        "field_provenance": _build_field_provenance(manual_overlay),
        "derived_features": {},
    }
    return CompiledPacketArtifact(packet=packet, provenance=provenance)
