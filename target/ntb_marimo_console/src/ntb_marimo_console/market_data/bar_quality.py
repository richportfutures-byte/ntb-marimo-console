from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


BarQualityState = Literal["usable", "building", "blocked", "unavailable"]
BarFactStatus = Literal["available", "insufficient", "unavailable"]
LevelComparisonDirection = Literal["at_or_above", "at_or_below"]


@dataclass(frozen=True)
class BarQuality:
    state: BarQualityState
    blocking_reasons: tuple[str, ...] = ()

    @property
    def usable(self) -> bool:
        return self.state == "usable" and not self.blocking_reasons

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state,
            "usable": self.usable,
            "blocking_reasons": list(self.blocking_reasons),
        }


@dataclass(frozen=True)
class BarFactResult:
    status: BarFactStatus
    value: object | None
    blocking_reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "value": self.value,
            "blocking_reasons": list(self.blocking_reasons),
        }


def count_completed_five_minute_closes_at_or_beyond_level(
    bars: tuple[object, ...],
    *,
    level: float | int | None,
    direction: LevelComparisonDirection = "at_or_above",
) -> BarFactResult:
    completed_bars = _completed_bars(bars)
    if level is None:
        return BarFactResult(status="unavailable", value=None, blocking_reasons=("level_unavailable",))
    if not completed_bars:
        return BarFactResult(
            status="unavailable",
            value=None,
            blocking_reasons=("no_completed_five_minute_bars",),
        )
    threshold = float(level)
    if direction == "at_or_below":
        count = sum(1 for bar in completed_bars if float(getattr(bar, "close")) <= threshold)
    else:
        count = sum(1 for bar in completed_bars if float(getattr(bar, "close")) >= threshold)
    return BarFactResult(status="available", value=count)


def latest_completed_close_relative_to_level(
    bars: tuple[object, ...],
    *,
    level: float | int | None,
) -> BarFactResult:
    completed_bars = _completed_bars(bars)
    if level is None:
        return BarFactResult(status="unavailable", value=None, blocking_reasons=("level_unavailable",))
    if not completed_bars:
        return BarFactResult(
            status="unavailable",
            value=None,
            blocking_reasons=("no_completed_five_minute_bars",),
        )
    close = float(completed_bars[-1].close)
    threshold = float(level)
    if close > threshold:
        relation = "above"
    elif close < threshold:
        relation = "below"
    else:
        relation = "at"
    return BarFactResult(
        status="available",
        value={"relation": relation, "close": close, "level": threshold},
    )


def basic_range_state_from_completed_bars(bars: tuple[object, ...]) -> BarFactResult:
    completed_bars = _completed_bars(bars)
    if len(completed_bars) < 2:
        return BarFactResult(
            status="insufficient",
            value=None,
            blocking_reasons=("insufficient_completed_bars_for_range_state",),
        )
    previous_ranges = [float(bar.high) - float(bar.low) for bar in completed_bars[:-1]]
    latest_range = float(completed_bars[-1].high) - float(completed_bars[-1].low)
    average_previous = sum(previous_ranges) / len(previous_ranges)
    if average_previous <= 0:
        return BarFactResult(
            status="unavailable",
            value=None,
            blocking_reasons=("invalid_previous_range_data",),
        )
    if latest_range > average_previous * 1.25:
        state = "expanding"
    elif latest_range < average_previous * 0.75:
        state = "contracting"
    else:
        state = "stable"
    return BarFactResult(status="available", value=state)


def volume_velocity_state_from_completed_bars(bars: tuple[object, ...]) -> BarFactResult:
    completed_bars = _completed_bars(bars)
    if len(completed_bars) < 2:
        return BarFactResult(
            status="insufficient",
            value=None,
            blocking_reasons=("insufficient_completed_bars_for_volume_velocity",),
        )
    if any(getattr(bar, "volume", None) is None for bar in completed_bars):
        return BarFactResult(
            status="unavailable",
            value=None,
            blocking_reasons=("volume_unavailable_for_volume_velocity",),
        )
    previous_volumes = [float(bar.volume) for bar in completed_bars[:-1]]
    latest_volume = float(completed_bars[-1].volume)
    average_previous = sum(previous_volumes) / len(previous_volumes)
    if average_previous <= 0:
        return BarFactResult(
            status="unavailable",
            value=None,
            blocking_reasons=("invalid_previous_volume_data",),
        )
    if latest_volume > average_previous * 1.25:
        state = "accelerating"
    elif latest_volume < average_previous * 0.75:
        state = "decelerating"
    else:
        state = "steady"
    return BarFactResult(status="available", value=state)


def _completed_bars(bars: tuple[object, ...]) -> tuple[object, ...]:
    return tuple(bar for bar in bars if bool(getattr(bar, "completed", False)))
