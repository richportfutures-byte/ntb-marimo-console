from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .bar_quality import BarQuality


CHART_FUTURES_BAR_CONTRACT_SCHEMA = "chart_futures_bar_contract_v1"
BarInterval = Literal["1m", "5m"]
BarSource = Literal["chart_futures_fixture", "chart_futures"]
BarReadinessState = Literal["available", "building", "stale", "unavailable", "blocked"]


@dataclass(frozen=True)
class OneMinuteBar:
    contract: str
    symbol: str
    provider: str
    source: BarSource
    start_time: str
    end_time: str
    observed_at: str
    open: float | int
    high: float | int
    low: float | int
    close: float | int
    volume: float | int | None
    completed: bool
    profile_id: str | None = None
    interval: BarInterval = "1m"
    quality: BarQuality = field(default_factory=lambda: BarQuality(state="usable"))
    schema: str = CHART_FUTURES_BAR_CONTRACT_SCHEMA

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "contract": self.contract,
            "profile_id": self.profile_id,
            "provider": self.provider,
            "source": self.source,
            "symbol": self.symbol,
            "interval": self.interval,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "observed_at": self.observed_at,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "completed": self.completed,
            "quality": self.quality.to_dict(),
            "blocking_reasons": list(self.quality.blocking_reasons),
        }


@dataclass(frozen=True)
class FiveMinuteBar:
    contract: str
    symbol: str
    provider: str
    source: BarSource
    start_time: str
    end_time: str
    observed_at: str
    open: float | int
    high: float | int
    low: float | int
    close: float | int
    volume: float | int | None
    completed: bool = True
    profile_id: str | None = None
    interval: BarInterval = "5m"
    contributing_bar_count: int = 5
    quality: BarQuality = field(default_factory=lambda: BarQuality(state="usable"))
    schema: str = CHART_FUTURES_BAR_CONTRACT_SCHEMA

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "contract": self.contract,
            "profile_id": self.profile_id,
            "provider": self.provider,
            "source": self.source,
            "symbol": self.symbol,
            "interval": self.interval,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "observed_at": self.observed_at,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "completed": self.completed,
            "contributing_bar_count": self.contributing_bar_count,
            "quality": self.quality.to_dict(),
            "blocking_reasons": list(self.quality.blocking_reasons),
        }


@dataclass(frozen=True)
class BuildingFiveMinuteBar:
    contract: str
    symbol: str
    provider: str
    source: BarSource
    start_time: str
    end_time: str
    observed_at: str | None
    open: float | int | None
    high: float | int | None
    low: float | int | None
    close: float | int | None
    volume: float | int | None
    completed: bool = False
    profile_id: str | None = None
    interval: BarInterval = "5m"
    contributing_bar_count: int = 0
    expected_bar_count: int = 5
    missing_start_times: tuple[str, ...] = ()
    quality: BarQuality = field(default_factory=lambda: BarQuality(state="building"))
    schema: str = CHART_FUTURES_BAR_CONTRACT_SCHEMA

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "contract": self.contract,
            "profile_id": self.profile_id,
            "provider": self.provider,
            "source": self.source,
            "symbol": self.symbol,
            "interval": self.interval,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "observed_at": self.observed_at,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "completed": self.completed,
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
    provider: str = "schwab"
    source: BarSource = "chart_futures_fixture"
    profile_id: str | None = None
    schema: str = CHART_FUTURES_BAR_CONTRACT_SCHEMA

    @property
    def usable(self) -> bool:
        return bool(self.completed_five_minute_bars) and self.building_five_minute_bar is None and not self.blocking_reasons

    def readiness(self) -> "ContractBarReadiness":
        completed_one_minute_available = bool(self.completed_one_minute_bars)
        completed_five_minute_available = bool(self.completed_five_minute_bars)
        building = self.building_five_minute_bar is not None
        stale = any(reason.startswith("stale_bar_data") for reason in self.blocking_reasons)
        reasons = list(self.blocking_reasons)
        if not completed_one_minute_available:
            reasons.append("completed_one_minute_bars_unavailable")
        if not completed_five_minute_available:
            reasons.append("completed_five_minute_bars_unavailable")
        if building:
            reasons.append("building_five_minute_bar_not_confirmation")
        state: BarReadinessState
        if stale:
            state = "stale"
        elif not completed_one_minute_available or not completed_five_minute_available:
            state = "building" if building else "unavailable"
        elif building:
            state = "building"
        elif reasons:
            state = "blocked"
        else:
            state = "available"
        latest_completed = self.completed_five_minute_bars[-1] if self.completed_five_minute_bars else None
        latest_one_minute = self.completed_one_minute_bars[-1] if self.completed_one_minute_bars else None
        return ContractBarReadiness(
            contract=self.contract,
            state=state,
            available=state == "available",
            completed_one_minute_available=completed_one_minute_available,
            completed_five_minute_available=completed_five_minute_available,
            building=building,
            fresh=not stale,
            provider=self.provider,
            source=self.source,
            profile_id=self.profile_id,
            latest_completed_one_minute_end_time=latest_one_minute.end_time if latest_one_minute is not None else None,
            latest_completed_five_minute_end_time=latest_completed.end_time if latest_completed is not None else None,
            blocking_reasons=_dedupe(tuple(reasons)),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "contract": self.contract,
            "profile_id": self.profile_id,
            "provider": self.provider,
            "source": self.source,
            "usable": self.usable,
            "completed_one_minute_bars": [bar.to_dict() for bar in self.completed_one_minute_bars],
            "completed_five_minute_bars": [bar.to_dict() for bar in self.completed_five_minute_bars],
            "building_five_minute_bar": (
                self.building_five_minute_bar.to_dict() if self.building_five_minute_bar is not None else None
            ),
            "blocking_reasons": list(self.blocking_reasons),
            "latest_start_time": self.latest_start_time,
            "readiness": self.readiness().to_dict(),
        }


@dataclass(frozen=True)
class ContractBarReadiness:
    contract: str
    state: BarReadinessState
    available: bool
    completed_one_minute_available: bool
    completed_five_minute_available: bool
    building: bool
    fresh: bool
    provider: str
    source: BarSource
    profile_id: str | None = None
    latest_completed_one_minute_end_time: str | None = None
    latest_completed_five_minute_end_time: str | None = None
    blocking_reasons: tuple[str, ...] = ()
    schema: str = CHART_FUTURES_BAR_CONTRACT_SCHEMA

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "contract": self.contract,
            "profile_id": self.profile_id,
            "provider": self.provider,
            "source": self.source,
            "state": self.state,
            "available": self.available,
            "completed_one_minute_available": self.completed_one_minute_available,
            "completed_five_minute_available": self.completed_five_minute_available,
            "building": self.building,
            "fresh": self.fresh,
            "latest_completed_one_minute_end_time": self.latest_completed_one_minute_end_time,
            "latest_completed_five_minute_end_time": self.latest_completed_five_minute_end_time,
            "blocking_reasons": list(self.blocking_reasons),
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


def _dedupe(reasons: tuple[str, ...]) -> tuple[str, ...]:
    deduped: list[str] = []
    for reason in reasons:
        normalized = str(reason).strip()
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return tuple(deduped)
