"""
Deterministic pre-flight market awareness. No LLM calls.
Computes structural states from the packet for display in the Readiness Matrix
and as context injected into the pre-market brief.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime, timezone
import re

from .schemas import (
    MarketPacket, ContractSymbol, PacketBundle,
    CLExtension, ZNExtension, SixEExtension
)


MAX_PACKET_AGE_SECONDS = 300
CL_MAX_PACKET_AGE_SECONDS = 180

ALLOWED_HOURS: dict[str, tuple[str, str]] = {
    "ES": ("08:30", "15:00"),
    "NQ": ("08:30", "15:00"),
    "CL": ("08:00", "14:30"),
    "ZN": ("07:00", "15:00"),
    "6E": ("07:00", "11:00"),
    "MGC": ("08:00", "14:00"),
}


@dataclass
class WatchmanState:
    contract: str
    # Freshness
    packet_age_seconds: Optional[float]
    is_stale: bool
    # Session
    inside_allowed_hours: bool
    session_time_remaining_minutes: Optional[float]
    # Price vs structure
    vwap_posture: str           # "above_vwap" / "below_vwap" / "at_vwap" / "unknown"
    value_location: str         # "above_value" / "inside_value" / "below_value" / "unknown"
    level_proximity: str        # "near_pdh" / "near_pdl" / "near_vah" / "near_val" / "near_poc" / "near_overnight_high" / "near_overnight_low" / "clear"
    nearest_level_name: Optional[str]
    nearest_level_value: Optional[float]
    nearest_level_distance: Optional[float]
    # Delta
    delta_posture: str          # "bullish" / "bearish" / "neutral" / "unknown"
    # Event risk
    event_risk: str             # "clear" / "elevated" / "lockout"
    event_detail: Optional[str]
    # Contract-specific macro state
    macro_state: Optional[str]
    # Hard lockout flags
    hard_lockout_flags: list[str] = field(default_factory=list)
    # Awareness flags (caution, not blocking)
    awareness_flags: list[str] = field(default_factory=list)
    # Missing context fields
    missing_context: list[str] = field(default_factory=list)
    # Overall readiness
    overall_status: str = "unknown"   # "ready" / "caution" / "blocked"


def _time_str_to_minutes(t: str) -> int:
    """Convert 'HH:MM' to minutes since midnight."""
    h, m = t.split(":")
    return int(h) * 60 + int(m)


def _parse_et_time(timestamp_et: str) -> Optional[datetime]:
    """Parse ISO timestamp string — supports with or without timezone info."""
    try:
        # Strip timezone info for simple comparison
        ts = re.sub(r"[TZ]", " ", timestamp_et).strip()
        ts = ts.replace("  ", " ")
        formats = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"]
        for fmt in formats:
            try:
                return datetime.strptime(ts[:16], fmt[:len(fmt)])
            except ValueError:
                continue
    except Exception:
        pass
    return None


def _vwap_posture(price: float, vwap: Optional[float]) -> str:
    if vwap is None:
        return "unknown"
    diff_pct = abs(price - vwap) / vwap * 100
    if diff_pct < 0.05:
        return "at_vwap"
    return "above_vwap" if price > vwap else "below_vwap"


def _value_location(price: float, vah: Optional[float], val: Optional[float]) -> str:
    if vah is None or val is None:
        return "unknown"
    if price > vah:
        return "above_value"
    if price < val:
        return "below_value"
    return "inside_value"


def _nearest_level(price: float, levels: dict[str, Optional[float]]) -> tuple[Optional[str], Optional[float], Optional[float]]:
    """Return (name, value, distance) of nearest non-None level."""
    best_name, best_val, best_dist = None, None, None
    for name, val in levels.items():
        if val is None:
            continue
        dist = abs(price - val)
        if best_dist is None or dist < best_dist:
            best_name, best_val, best_dist = name, val, dist
    return best_name, best_val, best_dist


def _level_proximity_label(nearest_name: Optional[str], nearest_dist: Optional[float], price: float) -> str:
    if nearest_dist is None or price == 0:
        return "unknown"
    pct = nearest_dist / price * 100
    if pct < 0.15:
        mapping = {
            "prior_day_high": "near_pdh",
            "prior_day_low": "near_pdl",
            "previous_session_vah": "near_vah",
            "previous_session_val": "near_val",
            "previous_session_poc": "near_poc",
            "overnight_high": "near_overnight_high",
            "overnight_low": "near_overnight_low",
            "major_htf_resistance": "near_htf_resistance",
            "major_htf_support": "near_htf_support",
        }
        return mapping.get(nearest_name or "", "near_structure")
    return "clear"


def _check_event_risk(packet: MarketPacket, contract: str) -> tuple[str, Optional[str]]:
    """Return (event_risk_level, detail)."""
    lockout_minutes_before = 15
    lockout_minutes_after = 5 if contract != "CL" else 20

    for evt in packet.event_calendar:
        if evt.tier == 1:
            mins = evt.minutes_until
            if mins is not None:
                if -lockout_minutes_after <= mins <= lockout_minutes_before:
                    return "lockout", f"{evt.name} lockout active ({mins:.0f} min)"
                if mins <= 30:
                    return "elevated", f"{evt.name} in {mins:.0f} min"
    return "clear", None


def _macro_state_summary(contract: str, ext: dict) -> Optional[str]:
    """Generate a one-line macro context for contract-specific extensions."""
    if contract == "ZN":
        yield_val = ext.get("cash_10y_yield")
        prior = ext.get("prior_day_10y_yield")
        auction = ext.get("treasury_auction_schedule")
        parts = []
        if yield_val:
            parts.append(f"10Y yield {yield_val:.2f}%")
        if prior and yield_val:
            chg = (yield_val - prior) * 100
            parts.append(f"({chg:+.1f}bps)")
        if auction:
            parts.append(f"Auction: {auction}")
        return " | ".join(parts) if parts else None

    if contract == "6E":
        dxy = ext.get("dxy_current")
        seq = ext.get("session_sequence_complete")
        parts = []
        if dxy:
            parts.append(f"DXY {dxy:.3f}")
        if seq is not None:
            parts.append("Sessions complete" if seq else "Sessions incomplete")
        return " | ".join(parts) if parts else None

    if contract == "MGC":
        dxy = ext.get("dxy_current")
        yld = ext.get("yield_10y_current")
        catalyst = ext.get("macro_fear_catalyst")
        parts = []
        if dxy:
            parts.append(f"DXY {dxy:.3f}")
        if yld:
            parts.append(f"Yield {yld:.2f}%")
        if catalyst:
            parts.append(f"Catalyst: {catalyst[:40]}")
        return " | ".join(parts) if parts else None

    if contract == "CL":
        eia = ext.get("eia_today")
        vol = ext.get("realized_volatility_context")
        parts = []
        if eia:
            parts.append("EIA today")
        if vol:
            parts.append(f"Vol: {vol}")
        return " | ".join(parts) if parts else None

    if contract == "NQ":
        rs = ext.get("relative_strength_vs_es")
        if rs is not None:
            return f"NQ/ES rel strength: {rs:.4f}"

    if contract == "ES":
        breadth = ext.get("breadth_advancing_pct")
        tone = ext.get("index_cash_tone")
        parts = []
        if breadth is not None:
            parts.append(f"Breadth {breadth:.0f}%")
        if tone:
            parts.append(f"Cash tone: {tone}")
        return " | ".join(parts) if parts else None

    return None


def sweep_contract(contract: str, packet: MarketPacket, ext: dict) -> WatchmanState:
    """Run deterministic watchman logic for a single contract."""
    price = packet.current_price
    lvls = packet.levels

    # Staleness
    max_age = CL_MAX_PACKET_AGE_SECONDS if contract == "CL" else MAX_PACKET_AGE_SECONDS
    age = packet.packet_age_seconds
    is_stale = age is not None and age > max_age

    # Session hours
    ts = _parse_et_time(packet.timestamp_et)
    inside_hours = True
    time_remaining = None
    if ts and contract in ALLOWED_HOURS:
        start_str, end_str = ALLOWED_HOURS[contract]
        start_min = _time_str_to_minutes(start_str)
        end_min = _time_str_to_minutes(end_str)
        now_min = ts.hour * 60 + ts.minute
        inside_hours = start_min <= now_min <= end_min
        time_remaining = max(0.0, end_min - now_min)

    # VWAP posture
    vwap_pos = _vwap_posture(price, lvls.vwap)

    # Value location (use prior session VAH/VAL as reference)
    value_loc = _value_location(
        price,
        lvls.previous_session_vah or lvls.current_session_vah,
        lvls.previous_session_val or lvls.current_session_val
    )

    # Nearest level
    level_map = {
        "prior_day_high": lvls.prior_day_high,
        "prior_day_low": lvls.prior_day_low,
        "previous_session_vah": lvls.previous_session_vah,
        "previous_session_val": lvls.previous_session_val,
        "previous_session_poc": lvls.previous_session_poc,
        "overnight_high": lvls.overnight_high,
        "overnight_low": lvls.overnight_low,
        "vwap": lvls.vwap,
        "major_htf_resistance": lvls.major_htf_resistance,
        "major_htf_support": lvls.major_htf_support,
    }
    nearest_name, nearest_val, nearest_dist = _nearest_level(price, level_map)
    prox_label = _level_proximity_label(nearest_name, nearest_dist, price)

    # Delta posture
    delta = packet.cumulative_delta
    delta_trend = packet.delta_trend
    if delta_trend:
        delta_pos = {"positive": "bullish", "negative": "bearish", "neutral": "neutral"}.get(delta_trend, "neutral")
    elif delta is not None:
        delta_pos = "bullish" if delta > 0 else ("bearish" if delta < 0 else "neutral")
    else:
        delta_pos = "unknown"

    # Event risk
    event_risk, event_detail = _check_event_risk(packet, contract)

    # Macro state
    macro = _macro_state_summary(contract, ext)

    # Hard lockout flags
    hard_lockouts = []
    if is_stale:
        hard_lockouts.append(f"STALE_DATA: packet age {age:.0f}s > {max_age}s limit")
    if event_risk == "lockout":
        hard_lockouts.append(f"EVENT_LOCKOUT: {event_detail}")
    if not inside_hours and time_remaining is not None and time_remaining == 0:
        hard_lockouts.append("OUTSIDE_TRADING_HOURS")

    # Awareness flags
    awareness = []
    if event_risk == "elevated":
        awareness.append(f"EVENT_ELEVATED: {event_detail}")
    if vwap_pos == "unknown":
        awareness.append("VWAP_MISSING")
    if value_loc == "unknown":
        awareness.append("VALUE_AREA_MISSING")
    if not inside_hours:
        awareness.append("PRE_OR_POST_MARKET")
    if time_remaining is not None and 0 < time_remaining < 30:
        awareness.append(f"SESSION_WINDING_DOWN: {time_remaining:.0f}min remaining")

    # Missing context
    missing = []
    if lvls.prior_day_high is None:
        missing.append("prior_day_high")
    if lvls.prior_day_low is None:
        missing.append("prior_day_low")
    if lvls.vwap is None:
        missing.append("vwap")
    if packet.cumulative_delta is None:
        missing.append("cumulative_delta")
    if contract == "ZN" and ext.get("cash_10y_yield") is None:
        missing.append("cash_10y_yield")
    if contract == "CL" and ext.get("realized_volatility_context") is None:
        missing.append("realized_volatility_context")
    if contract == "6E" and ext.get("london_high") is None:
        missing.append("london_high/low")

    # Overall status
    if hard_lockouts:
        overall = "blocked"
    elif awareness or missing:
        overall = "caution"
    else:
        overall = "ready"

    return WatchmanState(
        contract=contract,
        packet_age_seconds=age,
        is_stale=is_stale,
        inside_allowed_hours=inside_hours,
        session_time_remaining_minutes=time_remaining,
        vwap_posture=vwap_pos,
        value_location=value_loc,
        level_proximity=prox_label,
        nearest_level_name=nearest_name,
        nearest_level_value=nearest_val,
        nearest_level_distance=nearest_dist,
        delta_posture=delta_pos,
        event_risk=event_risk,
        event_detail=event_detail,
        macro_state=macro,
        hard_lockout_flags=hard_lockouts,
        awareness_flags=awareness,
        missing_context=missing,
        overall_status=overall,
    )


def sweep_all(bundle: PacketBundle) -> dict[str, WatchmanState]:
    """Run watchman sweep across all contracts in the bundle."""
    results = {}
    for contract, packet in bundle.packets.items():
        ext = bundle.extensions.get(contract, {})
        results[contract] = sweep_contract(contract, packet, ext)
    return results
