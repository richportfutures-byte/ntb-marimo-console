from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .bar_quality import BarQuality


BarInterval = Literal["1m", "5m"]
BarSource = Literal["chart_futures_fixture", "chart_futures"]


@dataclass(frozen=True)
class OneMinuteBar:
    contract: str
    symbol: str
    start_time: str
    end_time: str
    open: float | int
    high: float | int
    low: float | int
    close: float | int
    volume: float | int
    completed: bool
    source: BarSource = "chart_futures_fixture"
    interval: BarInterval = "1m"
    quality: BarQuality = field(default_factory=lambda: BarQuality(state="usable"))

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "symbol": self.symbol,
            "interval": self.interval,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "completed": self.completed,
            "source": self.source,
            "quality": self.quality.to_dict(),
            "blocking_reasons": list(self.quality.blocking_reasons),
        }


@dataclass(frozen=True)
class FiveMinuteBar:
    contract: str
    symbol: str
    start_time: str
    end_time: str
    open: float | int
    high: float | int
    low: float | int
    close: float | int
    volume: float | int
    completed: bool = True
    source: BarSource = "chart_futures_fixture"
    interval: BarInterval = "5m"
    contributing_bar_count: int = 5
    quality: BarQuality = field(default_factory=lambda: BarQuality(state="usable"))

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "symbol": self.symbol,
            "interval": self.interval,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "completed": self.completed,
            "source": self.source,
            "contributing_bar_count": self.contributing_bar_count,
            "quality": self.quality.to_dict(),
            "blocking_reasons": list(self.quality.blocking_reasons),
        }


@dataclass(frozen=True)
class BuildingFiveMinuteBar:
    contract: str
    symbol: str
    start_time: str
    end_time: str
    open: float | int | None
    high: float | int | None
    low: float | int | None
    close: float | int | None
    volume: float | int | None
    completed: bool = False
    source: BarSource = "chart_futures_fixture"
    interval: BarInterval = "5m"
    contributing_bar_count: int = 0
    expected_bar_count: int = 5
    missing_start_times: tuple[str, ...] = ()
    quality: BarQuality = field(default_factory=lambda: BarQuality(state="building"))

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "symbol": self.symbol,
            "interval": self.interval,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "completed": self.completed,
            "source": self.source,
            "contributing_bar_count": self.contributing_bar_count,
            "expected_bar_count": self.expected_bar_count,
            "missing_start_times": list(self.missing_start_times),
            "quality": self.quality.to_dict(),
            "blocking_reasons": list(self.quality.blocking_reasons),
        }


@dataclass(frozen=True)
class ContractBarState:
    contract: str
    completed_one_minute_bars: tuple[OneMinuteBar, ...] = ()
    completed_five_minute_bars: tuple[FiveMinuteBar, ...] = ()
    building_five_minute_bar: BuildingFiveMinuteBar | None = None
    blocking_reasons: tuple[str, ...] = ()
    latest_start_time: str | None = None

    @property
    def usable(self) -> bool:
        return bool(self.completed_five_minute_bars) and self.building_five_minute_bar is None and not self.blocking_reasons

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "usable": self.usable,
            "completed_one_minute_bars": [bar.to_dict() for bar in self.completed_one_minute_bars],
            "completed_five_minute_bars": [bar.to_dict() for bar in self.completed_five_minute_bars],
            "building_five_minute_bar": (
                self.building_five_minute_bar.to_dict() if self.building_five_minute_bar is not None else None
            ),
            "blocking_reasons": list(self.blocking_reasons),
            "latest_start_time": self.latest_start_time,
        }


@dataclass(frozen=True)
class BarIngestionResult:
    accepted: bool
    contract: str | None
    symbol: str | None
    blocking_reasons: tuple[str, ...]
    one_minute_bar: OneMinuteBar | None = None
    state: ContractBarState | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "accepted": self.accepted,
            "contract": self.contract,
            "symbol": self.symbol,
            "blocking_reasons": list(self.blocking_reasons),
            "one_minute_bar": self.one_minute_bar.to_dict() if self.one_minute_bar is not None else None,
            "state": self.state.to_dict() if self.state is not None else None,
        }
