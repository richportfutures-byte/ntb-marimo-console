from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from ntb_marimo_console.contract_universe import (
    final_target_contracts,
    is_excluded_final_target_contract,
    is_final_target_contract,
    is_never_supported_contract,
)

from .bar_quality import (
    BarQuality,
    basic_range_state_from_completed_bars,
    count_completed_five_minute_closes_at_or_beyond_level,
    latest_completed_close_relative_to_level,
    volume_velocity_state_from_completed_bars,
)
from .chart_bars import (
    BarIngestionResult,
    BarSource,
    BuildingFiveMinuteBar,
    ContractBarState,
    FiveMinuteBar,
    OneMinuteBar,
)


EXPECTED_ONE_MINUTE_BARS_PER_FIVE_MINUTE_BAR = 5


@dataclass
class ChartFuturesBarBuilder:
    expected_symbols: Mapping[str, str] | None = None
    _completed_one_minute_bars: dict[str, list[OneMinuteBar]] = field(default_factory=dict, init=False)
    _building_one_minute_bars: dict[str, list[OneMinuteBar]] = field(default_factory=dict, init=False)
    _blocking_reasons: dict[str, list[str]] = field(default_factory=dict, init=False)
    _last_start_time: dict[str, datetime] = field(default_factory=dict, init=False)

    def ingest(self, message: Mapping[str, object]) -> BarIngestionResult:
        normalized = _normalize_message(message, expected_symbols=self.expected_symbols)
        if isinstance(normalized, _RejectedMessage):
            return BarIngestionResult(
                accepted=False,
                contract=normalized.contract,
                symbol=normalized.symbol,
                blocking_reasons=normalized.blocking_reasons,
                state=self.state(normalized.contract) if normalized.contract in final_target_contracts() else None,
            )

        last_start = self._last_start_time.get(normalized.contract)
        if last_start is not None and normalized.start_time <= last_start:
            reason = f"out_of_order_bar:{normalized.contract}:{_isoformat(normalized.start_time)}"
            self._add_blocking_reason(normalized.contract, reason)
            return BarIngestionResult(
                accepted=False,
                contract=normalized.contract,
                symbol=normalized.symbol,
                blocking_reasons=(reason,),
                state=self.state(normalized.contract),
            )

        bar = _one_minute_bar(normalized)
        self._last_start_time[normalized.contract] = normalized.start_time
        if bar.completed:
            self._completed_one_minute_bars.setdefault(bar.contract, []).append(bar)
        else:
            self._building_one_minute_bars.setdefault(bar.contract, []).append(bar)
        state = self.state(bar.contract)
        return BarIngestionResult(
            accepted=True,
            contract=bar.contract,
            symbol=bar.symbol,
            blocking_reasons=(),
            one_minute_bar=bar,
            state=state,
        )

    def state(
        self,
        contract: str,
        *,
        now: datetime | None = None,
        max_completed_bar_age_seconds: float | None = None,
    ) -> ContractBarState:
        normalized_contract = contract.strip().upper()
        if normalized_contract not in final_target_contracts():
            return ContractBarState(
                contract=normalized_contract,
                blocking_reasons=(f"not_final_target_contract:{normalized_contract}",),
            )
        completed_one_minute = tuple(self._completed_one_minute_bars.get(normalized_contract, ()))
        completed_five_minute, building_five_minute, aggregation_reasons = _aggregate_five_minute(
            normalized_contract,
            completed_one_minute=completed_one_minute,
            building_one_minute=tuple(self._building_one_minute_bars.get(normalized_contract, ())),
        )
        reasons = _dedupe(
            tuple(self._blocking_reasons.get(normalized_contract, ()))
            + aggregation_reasons
            + _staleness_reasons(
                completed_one_minute,
                now=now,
                max_completed_bar_age_seconds=max_completed_bar_age_seconds,
            )
        )
        latest = self._last_start_time.get(normalized_contract)
        return ContractBarState(
            contract=normalized_contract,
            completed_one_minute_bars=completed_one_minute,
            completed_five_minute_bars=completed_five_minute,
            building_five_minute_bar=building_five_minute,
            blocking_reasons=reasons,
            latest_start_time=_isoformat(latest) if latest is not None else None,
            provider=_state_provider(completed_one_minute, building_five_minute),
            source=_state_source(completed_one_minute, building_five_minute),
            profile_id=_state_profile_id(completed_one_minute, building_five_minute),
        )

    def states(self) -> dict[str, ContractBarState]:
        return {contract: self.state(contract) for contract in final_target_contracts()}

    def reset_contract(self, contract: str) -> ContractBarState:
        normalized_contract = contract.strip().upper()
        self._completed_one_minute_bars.pop(normalized_contract, None)
        self._building_one_minute_bars.pop(normalized_contract, None)
        self._blocking_reasons.pop(normalized_contract, None)
        self._last_start_time.pop(normalized_contract, None)
        return self.state(normalized_contract)

    def completed_close_count_at_or_beyond_level(
        self,
        contract: str,
        *,
        level: float | int | None,
        direction: str = "at_or_above",
    ) -> object:
        state = self.state(contract)
        return count_completed_five_minute_closes_at_or_beyond_level(
            state.completed_five_minute_bars,
            level=level,
            direction="at_or_below" if direction == "at_or_below" else "at_or_above",
        )

    def latest_completed_close_relative_to_level(self, contract: str, *, level: float | int | None) -> object:
        return latest_completed_close_relative_to_level(
            self.state(contract).completed_five_minute_bars,
            level=level,
        )

    def basic_range_state(self, contract: str) -> object:
        return basic_range_state_from_completed_bars(self.state(contract).completed_five_minute_bars)

    def volume_velocity_state(self, contract: str) -> object:
        return volume_velocity_state_from_completed_bars(self.state(contract).completed_five_minute_bars)

    def _add_blocking_reason(self, contract: str, reason: str) -> None:
        reasons = self._blocking_reasons.setdefault(contract, [])
        if reason not in reasons:
            reasons.append(reason)


@dataclass(frozen=True)
class _NormalizedMessage:
    contract: str
    symbol: str
    provider: str
    source: BarSource
    profile_id: str | None
    start_time: datetime
    end_time: datetime
    observed_at: datetime
    open: float | int
    high: float | int
    low: float | int
    close: float | int
    volume: float | int | None
    completed: bool


@dataclass(frozen=True)
class _RejectedMessage:
    contract: str | None
    symbol: str | None
    blocking_reasons: tuple[str, ...]


def _normalize_message(
    message: Mapping[str, object],
    *,
    expected_symbols: Mapping[str, str] | None,
) -> _NormalizedMessage | _RejectedMessage:
    contract = _string_value(message, "contract")
    symbol = _string_value(message, "symbol")
    reasons: list[str] = []
    if contract is None:
        reasons.append("contract_required")
    else:
        if is_never_supported_contract(contract):
            reasons.append(f"never_supported_contract:{contract}")
        elif is_excluded_final_target_contract(contract):
            reasons.append(f"excluded_contract:{contract}")
        elif not is_final_target_contract(contract):
            reasons.append(f"not_final_target_contract:{contract}")
    if symbol is None:
        reasons.append("symbol_required")
    if contract is not None and symbol is not None and expected_symbols and contract in expected_symbols:
        expected_symbol = expected_symbols[contract].strip().upper()
        if symbol != expected_symbol:
            reasons.append(f"symbol_mismatch:{contract}:{symbol}")
    service = _string_value(message, "service")
    if service is not None and service != "CHART_FUTURES":
        reasons.append(f"unsupported_service:{service}")
    provider = _string_value(message, "provider") or "SCHWAB"
    source = _source_value(message.get("source"))
    profile_id = _optional_string_value(message, "profile_id")
    start_time = _datetime_value(message, "start_time")
    if start_time is None:
        reasons.append("timezone_aware_start_time_required")
    end_time = _datetime_value(message, "end_time")
    if start_time is not None and end_time is None:
        end_time = start_time + timedelta(minutes=1)
    observed_at = _datetime_value(message, "observed_at") or _datetime_value(message, "received_at")
    if observed_at is None and end_time is not None:
        observed_at = end_time
    if start_time is not None and end_time is not None and end_time != start_time + timedelta(minutes=1):
        reasons.append("one_minute_interval_mismatch")
    completed = message.get("completed")
    if not isinstance(completed, bool):
        reasons.append("completed_flag_required")
    ohlcv = {
        "open": _number_value(message, "open"),
        "high": _number_value(message, "high"),
        "low": _number_value(message, "low"),
        "close": _number_value(message, "close"),
        "volume": _number_value(message, "volume"),
    }
    missing = tuple(key for key, value in ohlcv.items() if key != "volume" and value is None)
    if missing:
        reasons.append("missing_ohlcv_fields:" + ",".join(missing))
    if "volume" in message and ohlcv["volume"] is None:
        reasons.append("invalid_volume")
    if ohlcv["volume"] is not None and float(ohlcv["volume"]) < 0:
        reasons.append("invalid_volume")
    if not missing and not _ohlc_is_coherent(ohlcv["open"], ohlcv["high"], ohlcv["low"], ohlcv["close"]):
        reasons.append("malformed_ohlc")
    if reasons:
        return _RejectedMessage(
            contract=contract,
            symbol=symbol,
            blocking_reasons=tuple(reasons),
        )
    assert contract is not None
    assert symbol is not None
    assert start_time is not None
    assert end_time is not None
    assert observed_at is not None
    assert isinstance(completed, bool)
    return _NormalizedMessage(
        contract=contract,
        symbol=symbol,
        provider=provider.lower(),
        source=source,
        profile_id=profile_id,
        start_time=start_time,
        end_time=end_time,
        observed_at=observed_at,
        open=ohlcv["open"],
        high=ohlcv["high"],
        low=ohlcv["low"],
        close=ohlcv["close"],
        volume=ohlcv["volume"],
        completed=completed,
    )


def _one_minute_bar(message: _NormalizedMessage) -> OneMinuteBar:
    return OneMinuteBar(
        contract=message.contract,
        symbol=message.symbol,
        provider=message.provider,
        source=message.source,
        profile_id=message.profile_id,
        start_time=_isoformat(message.start_time),
        end_time=_isoformat(message.end_time),
        observed_at=_isoformat(message.observed_at),
        open=message.open,
        high=message.high,
        low=message.low,
        close=message.close,
        volume=message.volume,
        completed=message.completed,
        quality=BarQuality(state="usable" if message.completed else "building"),
    )


def _aggregate_five_minute(
    contract: str,
    *,
    completed_one_minute: tuple[OneMinuteBar, ...],
    building_one_minute: tuple[OneMinuteBar, ...],
) -> tuple[tuple[FiveMinuteBar, ...], BuildingFiveMinuteBar | None, tuple[str, ...]]:
    by_bucket: dict[datetime, list[OneMinuteBar]] = {}
    for bar in completed_one_minute:
        bucket_start = _five_minute_bucket(_parse_datetime(bar.start_time))
        by_bucket.setdefault(bucket_start, []).append(bar)

    completed_bars: list[FiveMinuteBar] = []
    blocking_reasons: list[str] = []
    building_bar: BuildingFiveMinuteBar | None = None
    buckets = sorted(by_bucket)
    for index, bucket_start in enumerate(buckets):
        bars = sorted(by_bucket[bucket_start], key=lambda bar: bar.start_time)
        expected_starts = tuple(bucket_start + timedelta(minutes=offset) for offset in range(5))
        actual_starts = {_parse_datetime(bar.start_time) for bar in bars}
        missing_starts = tuple(start for start in expected_starts if start not in actual_starts)
        if len(bars) == EXPECTED_ONE_MINUTE_BARS_PER_FIVE_MINUTE_BAR and not missing_starts:
            completed_bars.append(_completed_five_minute_bar(contract, bars, bucket_start))
            continue
        candidate = _building_five_minute_bar(contract, bars, bucket_start, missing_starts)
        if index == len(buckets) - 1:
            building_bar = candidate
        else:
            blocking_reasons.append(f"gap_in_one_minute_bars:{contract}:{_isoformat(bucket_start)}")

    if building_one_minute:
        latest_building = sorted(building_one_minute, key=lambda bar: bar.start_time)[-1]
        bucket_start = _five_minute_bucket(_parse_datetime(latest_building.start_time))
        bucket_completed = tuple(
            bar
            for bar in completed_one_minute
            if _five_minute_bucket(_parse_datetime(bar.start_time)) == bucket_start
        )
        bucket_bars = tuple(sorted((*bucket_completed, latest_building), key=lambda bar: bar.start_time))
        expected_starts = tuple(bucket_start + timedelta(minutes=offset) for offset in range(5))
        actual_starts = {_parse_datetime(bar.start_time) for bar in bucket_bars}
        missing_starts = tuple(start for start in expected_starts if start not in actual_starts)
        building_bar = _building_five_minute_bar(contract, bucket_bars, bucket_start, missing_starts)

    return tuple(completed_bars), building_bar, _dedupe(tuple(blocking_reasons))


def _completed_five_minute_bar(contract: str, bars: list[OneMinuteBar], bucket_start: datetime) -> FiveMinuteBar:
    return FiveMinuteBar(
        contract=contract,
        symbol=bars[-1].symbol,
        provider=bars[-1].provider,
        source=bars[-1].source,
        profile_id=bars[-1].profile_id,
        start_time=_isoformat(bucket_start),
        end_time=_isoformat(bucket_start + timedelta(minutes=5)),
        observed_at=bars[-1].observed_at,
        open=bars[0].open,
        high=max(bar.high for bar in bars),
        low=min(bar.low for bar in bars),
        close=bars[-1].close,
        volume=_sum_volume(bars),
        quality=BarQuality(state="usable"),
    )


def _building_five_minute_bar(
    contract: str,
    bars: tuple[OneMinuteBar, ...] | list[OneMinuteBar],
    bucket_start: datetime,
    missing_starts: tuple[datetime, ...],
) -> BuildingFiveMinuteBar:
    sorted_bars = tuple(sorted(bars, key=lambda bar: bar.start_time))
    if not sorted_bars:
        return BuildingFiveMinuteBar(
            contract=contract,
            symbol="",
            provider="schwab",
            source="chart_futures_fixture",
            start_time=_isoformat(bucket_start),
            end_time=_isoformat(bucket_start + timedelta(minutes=5)),
            observed_at=None,
            open=None,
            high=None,
            low=None,
            close=None,
            volume=None,
            missing_start_times=tuple(_isoformat(start) for start in missing_starts),
            quality=BarQuality(state="building", blocking_reasons=("building_five_minute_bar",)),
        )
    return BuildingFiveMinuteBar(
        contract=contract,
        symbol=sorted_bars[-1].symbol,
        provider=sorted_bars[-1].provider,
        source=sorted_bars[-1].source,
        profile_id=sorted_bars[-1].profile_id,
        start_time=_isoformat(bucket_start),
        end_time=_isoformat(bucket_start + timedelta(minutes=5)),
        observed_at=sorted_bars[-1].observed_at,
        open=sorted_bars[0].open,
        high=max(bar.high for bar in sorted_bars),
        low=min(bar.low for bar in sorted_bars),
        close=sorted_bars[-1].close,
        volume=_sum_volume(sorted_bars),
        contributing_bar_count=len(sorted_bars),
        missing_start_times=tuple(_isoformat(start) for start in missing_starts),
        quality=BarQuality(state="building", blocking_reasons=("building_five_minute_bar",)),
    )


def _staleness_reasons(
    completed_one_minute: tuple[OneMinuteBar, ...],
    *,
    now: datetime | None,
    max_completed_bar_age_seconds: float | None,
) -> tuple[str, ...]:
    if now is None or max_completed_bar_age_seconds is None or not completed_one_minute:
        return ()
    latest = _parse_datetime(completed_one_minute[-1].end_time)
    age = (now.astimezone(timezone.utc) - latest.astimezone(timezone.utc)).total_seconds()
    if age > max_completed_bar_age_seconds:
        return (f"stale_bar_data:{int(age)}",)
    return ()


def _five_minute_bucket(value: datetime) -> datetime:
    return value.replace(minute=value.minute - (value.minute % 5), second=0, microsecond=0)


def _string_value(message: Mapping[str, object], key: str) -> str | None:
    value = message.get(key)
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip().upper()


def _optional_string_value(message: Mapping[str, object], key: str) -> str | None:
    value = message.get(key)
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _source_value(value: object) -> BarSource:
    if isinstance(value, str) and value.strip().lower() == "chart_futures":
        return "chart_futures"
    return "chart_futures_fixture"


def _number_value(message: Mapping[str, object], key: str) -> float | int | None:
    value = message.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    return None


def _datetime_value(message: Mapping[str, object], key: str) -> datetime | None:
    value = message.get(key)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _ohlc_is_coherent(
    open_price: float | int | None,
    high: float | int | None,
    low: float | int | None,
    close: float | int | None,
) -> bool:
    if open_price is None or high is None or low is None or close is None:
        return False
    return float(high) >= max(float(open_price), float(close), float(low)) and float(low) <= min(
        float(open_price),
        float(close),
        float(high),
    )


def _isoformat(value: datetime) -> str:
    current = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).isoformat()


def _sum_volume(bars: tuple[OneMinuteBar, ...] | list[OneMinuteBar]) -> float | int | None:
    if any(bar.volume is None for bar in bars):
        return None
    return sum(bar.volume for bar in bars if bar.volume is not None)


def _state_provider(
    completed_one_minute: tuple[OneMinuteBar, ...],
    building_five_minute: BuildingFiveMinuteBar | None,
) -> str:
    if completed_one_minute:
        return completed_one_minute[-1].provider
    if building_five_minute is not None:
        return building_five_minute.provider
    return "schwab"


def _state_source(
    completed_one_minute: tuple[OneMinuteBar, ...],
    building_five_minute: BuildingFiveMinuteBar | None,
) -> BarSource:
    if completed_one_minute:
        return completed_one_minute[-1].source
    if building_five_minute is not None:
        return building_five_minute.source
    return "chart_futures_fixture"


def _state_profile_id(
    completed_one_minute: tuple[OneMinuteBar, ...],
    building_five_minute: BuildingFiveMinuteBar | None,
) -> str | None:
    if completed_one_minute:
        return completed_one_minute[-1].profile_id
    if building_five_minute is not None:
        return building_five_minute.profile_id
    return None


def _dedupe(reasons: tuple[str, ...]) -> tuple[str, ...]:
    deduped: list[str] = []
    for reason in reasons:
        if reason not in deduped:
            deduped.append(reason)
    return tuple(deduped)
