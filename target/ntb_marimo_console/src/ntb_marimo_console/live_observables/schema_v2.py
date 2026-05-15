from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from .quality import ProviderStatusV2, quality_state_from_reasons


LIVE_OBSERVABLE_SNAPSHOT_V2_SCHEMA = "live_observable_snapshot_v2"
JsonScalar = str | int | float | bool | None
DependencyStatusV2 = Literal["available", "unavailable", "lockout", "derived_with_source", "derived_without_source"]
ChartBarStatusV2 = Literal["available", "building", "stale", "unavailable", "blocked"]


@dataclass(frozen=True)
class QuoteObservableV2:
    bid: float | int | None = None
    ask: float | int | None = None
    last: float | int | None = None
    bid_size: float | int | None = None
    ask_size: float | int | None = None
    last_size: float | int | None = None
    quote_time: str | None = None
    trade_time: str | None = None
    quote_age_seconds: float | None = None
    trade_age_seconds: float | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "bid": self.bid,
            "ask": self.ask,
            "last": self.last,
            "bid_size": self.bid_size,
            "ask_size": self.ask_size,
            "last_size": self.last_size,
            "quote_time": self.quote_time,
            "trade_time": self.trade_time,
            "quote_age_seconds": self.quote_age_seconds,
            "trade_age_seconds": self.trade_age_seconds,
        }


@dataclass(frozen=True)
class SessionObservableV2:
    open: float | int | None = None
    high: float | int | None = None
    low: float | int | None = None
    prior_close: float | int | None = None
    net_change: float | int | None = None
    percent_change: float | int | None = None
    volume: float | int | None = None
    security_status: str | None = None
    tradable: bool | None = None
    active: bool | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "prior_close": self.prior_close,
            "net_change": self.net_change,
            "percent_change": self.percent_change,
            "volume": self.volume,
            "security_status": self.security_status,
            "tradable": self.tradable,
            "active": self.active,
        }


@dataclass(frozen=True)
class DerivedObservableV2:
    spread_ticks: float | None = None
    mid: float | None = None
    distance_to_primary_trigger_ticks: float | None = None
    bar_5m_close: float | None = None
    bar_5m_close_count_at_or_beyond_level: int | None = None
    range_expansion_state: str | None = None
    volume_velocity_state: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "spread_ticks": self.spread_ticks,
            "mid": self.mid,
            "distance_to_primary_trigger_ticks": self.distance_to_primary_trigger_ticks,
            "bar_5m_close": self.bar_5m_close,
            "bar_5m_close_count_at_or_beyond_level": self.bar_5m_close_count_at_or_beyond_level,
            "range_expansion_state": self.range_expansion_state,
            "volume_velocity_state": self.volume_velocity_state,
        }


@dataclass(frozen=True)
class DependencyObservableV2:
    name: str
    status: DependencyStatusV2 = "unavailable"
    required: bool = True
    source: str = "unavailable"
    source_status: str = "unavailable"
    value: JsonScalar = None
    fields: dict[str, JsonScalar] = field(default_factory=dict)
    fresh: bool = False
    blocking_reasons: tuple[str, ...] = ()

    @property
    def available(self) -> bool:
        return self.status in {"available", "derived_with_source"} and self.fresh and not self.blocking_reasons

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "status": self.status,
            "required": self.required,
            "available": self.available,
            "source": self.source,
            "source_status": self.source_status,
            "value": self.value,
            "fields": self.fields,
            "fresh": self.fresh,
            "blocking_reasons": list(self.blocking_reasons),
        }


@dataclass(frozen=True)
class ChartBarObservableV2:
    state: ChartBarStatusV2 = "unavailable"
    available: bool = False
    fresh: bool = False
    source: str = "unavailable"
    source_status: str = "unavailable"
    completed_one_minute_available: bool = False
    completed_five_minute_available: bool = False
    building: bool = False
    completed_one_minute_count: int = 0
    completed_five_minute_count: int = 0
    latest_completed_one_minute_end_time: str | None = None
    latest_completed_five_minute_end_time: str | None = None
    blocking_reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "state": self.state,
            "available": self.available,
            "fresh": self.fresh,
            "source": self.source,
            "source_status": self.source_status,
            "completed_one_minute_available": self.completed_one_minute_available,
            "completed_five_minute_available": self.completed_five_minute_available,
            "building": self.building,
            "completed_one_minute_count": self.completed_one_minute_count,
            "completed_five_minute_count": self.completed_five_minute_count,
            "latest_completed_one_minute_end_time": self.latest_completed_one_minute_end_time,
            "latest_completed_five_minute_end_time": self.latest_completed_five_minute_end_time,
            "blocking_reasons": list(self.blocking_reasons),
        }


@dataclass(frozen=True)
class QualityObservableV2:
    fresh: bool = False
    delayed: bool | None = None
    symbol_match: bool = False
    required_fields_present: bool = False
    core_quote_fields_present: bool = False
    missing_fields: tuple[str, ...] = ()
    chart_bars_ready: bool = False
    dependency_blocking_reasons: tuple[str, ...] = ()
    blocking_reasons: tuple[str, ...] = ()

    @property
    def state(self) -> Literal["ready", "blocked"]:
        return quality_state_from_reasons(self.blocking_reasons)

    def to_dict(self) -> dict[str, object]:
        return {
            "fresh": self.fresh,
            "delayed": self.delayed,
            "symbol_match": self.symbol_match,
            "required_fields_present": self.required_fields_present,
            "core_quote_fields_present": self.core_quote_fields_present,
            "missing_fields": list(self.missing_fields),
            "chart_bars_ready": self.chart_bars_ready,
            "dependency_blocking_reasons": list(self.dependency_blocking_reasons),
            "blocking_reasons": list(self.blocking_reasons),
        }


@dataclass(frozen=True)
class ContractObservableV2:
    contract: str
    symbol: str | None
    quote: QuoteObservableV2 = field(default_factory=QuoteObservableV2)
    session: SessionObservableV2 = field(default_factory=SessionObservableV2)
    derived: DerivedObservableV2 = field(default_factory=DerivedObservableV2)
    chart_bar: ChartBarObservableV2 = field(default_factory=ChartBarObservableV2)
    dependencies: dict[str, DependencyObservableV2] = field(default_factory=dict)
    quality: QualityObservableV2 = field(default_factory=QualityObservableV2)
    label: str | None = None
    sources: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        payload = {
            "contract": self.contract,
            "symbol": self.symbol,
            "label": self.label,
            "quote": self.quote.to_dict(),
            "session": self.session.to_dict(),
            "derived": self.derived.to_dict(),
            "chart_bar": self.chart_bar.to_dict(),
            "dependencies": {name: dependency.to_dict() for name, dependency in self.dependencies.items()},
            "quality": self.quality.to_dict(),
            "sources": self.sources,
        }
        return payload


@dataclass(frozen=True)
class LiveObservableSnapshotV2:
    generated_at: str
    provider: str
    provider_status: ProviderStatusV2
    contracts: dict[str, ContractObservableV2]
    cross_asset: dict[str, object]
    macro_context: dict[str, object]
    session_context: dict[str, object]
    data_quality: dict[str, object]
    schema: str = LIVE_OBSERVABLE_SNAPSHOT_V2_SCHEMA

    @property
    def ready(self) -> bool:
        return bool(self.data_quality.get("ready"))

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": self.schema,
            "generated_at": self.generated_at,
            "provider": self.provider,
            "provider_status": self.provider_status,
            "contracts": {contract: observable.to_dict() for contract, observable in self.contracts.items()},
            "cross_asset": self.cross_asset,
            "macro_context": self.macro_context,
            "session_context": self.session_context,
            "data_quality": self.data_quality,
        }
