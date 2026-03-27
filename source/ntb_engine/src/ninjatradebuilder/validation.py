from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .schemas.packet import CLHistoricalPacket, HistoricalPacket


def validate_historical_packet(packet: Mapping[str, Any]) -> HistoricalPacket:
    return HistoricalPacket.model_validate(dict(packet))


def validate_cl_historical_packet(packet: Mapping[str, Any]) -> CLHistoricalPacket:
    return CLHistoricalPacket.model_validate(dict(packet))
