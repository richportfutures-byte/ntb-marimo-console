from __future__ import annotations

import math
from datetime import date
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator
from zoneinfo import ZoneInfo

from ..schemas.cl import EiaTiming, RealizedVolatilityContext
from ..schemas.contracts import DxyContext, IndexCashTone, PriceRange, YieldContext
from ..schemas.inputs import (
    AttachedVisuals,
    ChallengeState,
    EventCalendarEntry,
    OpeningType,
)


class CompilerStrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)


class HistoricalBar(CompilerStrictModel):
    timestamp: AwareDatetime
    open: float
    high: float
    low: float
    close: float
    volume: float

    @model_validator(mode="after")
    def validate_ohlcv(self) -> "HistoricalBar":
        if self.high < self.low:
            raise ValueError("Historical bars require high >= low.")
        if not self.low <= self.open <= self.high:
            raise ValueError("Historical bars require open to be inside the high/low range.")
        if not self.low <= self.close <= self.high:
            raise ValueError("Historical bars require close to be inside the high/low range.")
        if self.volume <= 0:
            raise ValueError("Historical bars require volume > 0.")
        return self


class VolumeProfileLevel(CompilerStrictModel):
    price: float
    volume: float

    @model_validator(mode="after")
    def validate_profile_level(self) -> "VolumeProfileLevel":
        if self.volume <= 0:
            raise ValueError("Volume profile levels require volume > 0.")
        return self


class HistoricalSessionRangeInput(CompilerStrictModel):
    session_date: date
    high: float
    low: float

    @model_validator(mode="after")
    def validate_session_range(self) -> "HistoricalSessionRangeInput":
        if self.high <= self.low:
            raise ValueError("Historical session ranges require high > low.")
        return self


class HistoricalObservedVolumeInput(CompilerStrictModel):
    session_date: date
    observed_volume: float

    @model_validator(mode="after")
    def validate_observed_volume(self) -> "HistoricalObservedVolumeInput":
        if self.observed_volume <= 0:
            raise ValueError("Historical observed volumes require observed_volume > 0.")
        return self


class ESHistoricalDataInput(CompilerStrictModel):
    contract: Literal["ES"] = "ES"
    prior_rth_bars: list[HistoricalBar]
    overnight_bars: list[HistoricalBar]
    current_rth_bars: list[HistoricalBar]
    weekly_open_bar: HistoricalBar
    prior_rth_volume_profile: list[VolumeProfileLevel]
    current_rth_volume_profile: list[VolumeProfileLevel]
    prior_20_rth_sessions: list[HistoricalSessionRangeInput]
    prior_20_rth_observed_volumes: list[HistoricalObservedVolumeInput]

    @staticmethod
    def _validate_strictly_ascending(field_name: str, bars: list[HistoricalBar]) -> None:
        if not bars:
            raise ValueError(f"{field_name} must contain at least one bar.")
        timestamps = [bar.timestamp for bar in bars]
        if len(set(timestamps)) != len(timestamps):
            raise ValueError(f"{field_name} must not contain duplicate timestamps.")
        if any(current <= previous for previous, current in zip(timestamps, timestamps[1:])):
            raise ValueError(f"{field_name} must be strictly timestamp-ascending.")

    @staticmethod
    def _validate_volume_profile(field_name: str, levels: list[VolumeProfileLevel]) -> None:
        if len(levels) < 3:
            raise ValueError(f"{field_name} must contain at least three price levels.")
        prices = [level.price for level in levels]
        if len(set(prices)) != len(prices):
            raise ValueError(f"{field_name} must not contain duplicate prices.")
        if prices != sorted(prices):
            raise ValueError(f"{field_name} must be sorted by price ascending.")
        for previous, current in zip(prices, prices[1:]):
            tick_steps = round((current - previous) / 0.25, 6)
            if current <= previous or abs(tick_steps - round(tick_steps)) > 1e-6:
                raise ValueError(
                    f"{field_name} must use a strict 0.25 ES tick ladder with ascending prices."
                )

    @model_validator(mode="after")
    def validate_bar_sets(self) -> "ESHistoricalDataInput":
        for field_name in ("prior_rth_bars", "overnight_bars", "current_rth_bars"):
            self._validate_strictly_ascending(field_name, getattr(self, field_name))
        for field_name in ("prior_rth_volume_profile", "current_rth_volume_profile"):
            self._validate_volume_profile(field_name, getattr(self, field_name))

        current_session_dates = {bar.timestamp.date() for bar in self.current_rth_bars}
        if len(current_session_dates) != 1:
            raise ValueError("current_rth_bars must all fall on one session date.")
        current_session_date = next(iter(current_session_dates))

        prior_session_dates = {bar.timestamp.date() for bar in self.prior_rth_bars}
        if len(prior_session_dates) != 1:
            raise ValueError("prior_rth_bars must all represent one prior session date.")
        prior_session_date = next(iter(prior_session_dates))
        if prior_session_date >= current_session_date:
            raise ValueError("prior_rth_bars must represent a date before current_rth_bars.")

        if len(self.prior_20_rth_sessions) != 20:
            raise ValueError("prior_20_rth_sessions must contain exactly 20 completed sessions.")
        lookback_dates = [session.session_date for session in self.prior_20_rth_sessions]
        if len(set(lookback_dates)) != len(lookback_dates):
            raise ValueError("prior_20_rth_sessions must not contain duplicate session_date values.")
        if any(current <= previous for previous, current in zip(lookback_dates, lookback_dates[1:])):
            raise ValueError("prior_20_rth_sessions must be strictly date-ascending.")
        if lookback_dates[-1] != prior_session_date:
            raise ValueError(
                "prior_20_rth_sessions must end on the same date as prior_rth_bars."
            )
        if lookback_dates[-1] >= current_session_date:
            raise ValueError(
                "prior_20_rth_sessions must contain only completed sessions before current_rth_bars."
            )

        if len(self.prior_20_rth_observed_volumes) != 20:
            raise ValueError(
                "prior_20_rth_observed_volumes must contain exactly 20 completed sessions."
            )
        observed_volume_dates = [session.session_date for session in self.prior_20_rth_observed_volumes]
        if len(set(observed_volume_dates)) != len(observed_volume_dates):
            raise ValueError(
                "prior_20_rth_observed_volumes must not contain duplicate session_date values."
            )
        if any(current <= previous for previous, current in zip(observed_volume_dates, observed_volume_dates[1:])):
            raise ValueError("prior_20_rth_observed_volumes must be strictly date-ascending.")
        if observed_volume_dates != lookback_dates:
            raise ValueError(
                "prior_20_rth_observed_volumes must use the same 20 session dates as prior_20_rth_sessions."
            )

        prior_session_end = self.prior_rth_bars[-1].timestamp
        current_session_start = self.current_rth_bars[0].timestamp
        if self.weekly_open_bar.timestamp > current_session_start:
            raise ValueError("weekly_open_bar timestamp must not be after the first current_rth_bar.")
        if prior_session_end >= current_session_start:
            raise ValueError("prior_rth_bars must end before current_rth_bars begin.")
        if self.overnight_bars[0].timestamp <= prior_session_end:
            raise ValueError("overnight_bars must start after prior_rth_bars end.")
        if self.overnight_bars[-1].timestamp >= current_session_start:
            raise ValueError("overnight_bars must end before current_rth_bars begin.")
        if any(bar.timestamp <= prior_session_end for bar in self.overnight_bars):
            raise ValueError(
                "overnight_bars must fall strictly after prior_rth_bars and before current_rth_bars."
            )
        if any(bar.timestamp >= current_session_start for bar in self.overnight_bars):
            raise ValueError(
                "overnight_bars must fall strictly after prior_rth_bars and before current_rth_bars."
            )

        prior_rth_high = max(bar.high for bar in self.prior_rth_bars)
        prior_rth_low = min(bar.low for bar in self.prior_rth_bars)
        last_lookback_session = self.prior_20_rth_sessions[-1]
        if (
            abs(last_lookback_session.high - prior_rth_high) > 1e-9
            or abs(last_lookback_session.low - prior_rth_low) > 1e-9
        ):
            raise ValueError(
                "The last prior_20_rth_sessions entry must match prior_rth_bars high/low."
            )
        return self


class CLHistoricalDataInput(CompilerStrictModel):
    contract: Literal["CL"] = "CL"
    timestamp: AwareDatetime
    current_price: float
    session_open: float
    prior_day_high: float
    prior_day_low: float
    prior_day_close: float
    overnight_high: float
    overnight_low: float
    current_session_vah: float
    current_session_val: float
    current_session_poc: float
    previous_session_vah: float
    previous_session_val: float
    previous_session_poc: float
    vwap: float
    session_range: float
    avg_20d_session_range: float
    cumulative_delta: float
    current_volume_vs_average: float
    event_calendar_remainder: list[EventCalendarEntry]

    @model_validator(mode="after")
    def validate_cl_market_fields(self) -> "CLHistoricalDataInput":
        if self.prior_day_high < self.prior_day_low:
            raise ValueError("prior_day_high must be >= prior_day_low.")
        if self.overnight_high < self.overnight_low:
            raise ValueError("overnight_high must be >= overnight_low.")
        if not (self.current_session_vah >= self.current_session_poc >= self.current_session_val):
            raise ValueError("current session profile levels must satisfy VAH >= POC >= VAL.")
        if not (self.previous_session_vah >= self.previous_session_poc >= self.previous_session_val):
            raise ValueError("previous session profile levels must satisfy VAH >= POC >= VAL.")
        if self.session_range < 0:
            raise ValueError("session_range must be >= 0.")
        if self.avg_20d_session_range <= 0:
            raise ValueError("avg_20d_session_range must be > 0.")
        if self.current_volume_vs_average <= 0:
            raise ValueError("current_volume_vs_average must be > 0.")
        if not math.isfinite(self.cumulative_delta):
            raise ValueError("cumulative_delta must be finite.")
        return self


class ZNHistoricalDataInput(CompilerStrictModel):
    contract: Literal["ZN"] = "ZN"
    timestamp: AwareDatetime
    current_price: float
    session_open: float
    prior_day_high: float
    prior_day_low: float
    prior_day_close: float
    overnight_high: float
    overnight_low: float
    current_session_vah: float
    current_session_val: float
    current_session_poc: float
    previous_session_vah: float
    previous_session_val: float
    previous_session_poc: float
    vwap: float
    session_range: float
    avg_20d_session_range: float
    cumulative_delta: float
    current_volume_vs_average: float
    event_calendar_remainder: list[EventCalendarEntry]

    @model_validator(mode="after")
    def validate_zn_market_fields(self) -> "ZNHistoricalDataInput":
        if self.prior_day_high < self.prior_day_low:
            raise ValueError("prior_day_high must be >= prior_day_low.")
        if self.overnight_high < self.overnight_low:
            raise ValueError("overnight_high must be >= overnight_low.")
        if not (self.current_session_vah >= self.current_session_poc >= self.current_session_val):
            raise ValueError("current session profile levels must satisfy VAH >= POC >= VAL.")
        if not (self.previous_session_vah >= self.previous_session_poc >= self.previous_session_val):
            raise ValueError("previous session profile levels must satisfy VAH >= POC >= VAL.")
        if self.session_range < 0:
            raise ValueError("session_range must be >= 0.")
        if self.avg_20d_session_range <= 0:
            raise ValueError("avg_20d_session_range must be > 0.")
        if self.current_volume_vs_average <= 0:
            raise ValueError("current_volume_vs_average must be > 0.")
        if not math.isfinite(self.cumulative_delta):
            raise ValueError("cumulative_delta must be finite.")
        return self


class NQHistoricalDataInput(CompilerStrictModel):
    contract: Literal["NQ"] = "NQ"
    timestamp: AwareDatetime
    current_price: float
    session_open: float
    prior_day_high: float
    prior_day_low: float
    prior_day_close: float
    overnight_high: float
    overnight_low: float
    current_session_vah: float
    current_session_val: float
    current_session_poc: float
    previous_session_vah: float
    previous_session_val: float
    previous_session_poc: float
    vwap: float
    session_range: float
    avg_20d_session_range: float
    cumulative_delta: float
    current_volume_vs_average: float
    event_calendar_remainder: list[EventCalendarEntry]

    @model_validator(mode="after")
    def validate_nq_market_fields(self) -> "NQHistoricalDataInput":
        if self.prior_day_high < self.prior_day_low:
            raise ValueError("prior_day_high must be >= prior_day_low.")
        if self.overnight_high < self.overnight_low:
            raise ValueError("overnight_high must be >= overnight_low.")
        if not (self.current_session_vah >= self.current_session_poc >= self.current_session_val):
            raise ValueError("current session profile levels must satisfy VAH >= POC >= VAL.")
        if not (self.previous_session_vah >= self.previous_session_poc >= self.previous_session_val):
            raise ValueError("previous session profile levels must satisfy VAH >= POC >= VAL.")
        if self.session_range < 0:
            raise ValueError("session_range must be >= 0.")
        if self.avg_20d_session_range <= 0:
            raise ValueError("avg_20d_session_range must be > 0.")
        if self.current_volume_vs_average <= 0:
            raise ValueError("current_volume_vs_average must be > 0.")
        if not math.isfinite(self.cumulative_delta):
            raise ValueError("cumulative_delta must be finite.")
        return self


class SixEHistoricalDataInput(CompilerStrictModel):
    contract: Literal["6E"] = "6E"
    timestamp: AwareDatetime
    current_price: float
    session_open: float
    prior_day_high: float
    prior_day_low: float
    prior_day_close: float
    overnight_high: float
    overnight_low: float
    current_session_vah: float
    current_session_val: float
    current_session_poc: float
    previous_session_vah: float
    previous_session_val: float
    previous_session_poc: float
    vwap: float
    session_range: float
    avg_20d_session_range: float
    cumulative_delta: float
    current_volume_vs_average: float
    event_calendar_remainder: list[EventCalendarEntry]
    asia_bars: list[HistoricalBar]
    london_bars: list[HistoricalBar]
    ny_bars: list[HistoricalBar]

    @staticmethod
    def _validate_strictly_ascending(field_name: str, bars: list[HistoricalBar]) -> None:
        if not bars:
            raise ValueError(f"{field_name} must contain at least one bar.")
        timestamps = [bar.timestamp for bar in bars]
        if len(set(timestamps)) != len(timestamps):
            raise ValueError(f"{field_name} must not contain duplicate timestamps.")
        if any(current <= previous for previous, current in zip(timestamps, timestamps[1:])):
            raise ValueError(f"{field_name} must be strictly timestamp-ascending.")

    @model_validator(mode="after")
    def validate_six_e_market_fields(self) -> "SixEHistoricalDataInput":
        if self.prior_day_high < self.prior_day_low:
            raise ValueError("prior_day_high must be >= prior_day_low.")
        if self.overnight_high < self.overnight_low:
            raise ValueError("overnight_high must be >= overnight_low.")
        if not (self.current_session_vah >= self.current_session_poc >= self.current_session_val):
            raise ValueError("current session profile levels must satisfy VAH >= POC >= VAL.")
        if not (self.previous_session_vah >= self.previous_session_poc >= self.previous_session_val):
            raise ValueError("previous session profile levels must satisfy VAH >= POC >= VAL.")
        if self.session_range < 0:
            raise ValueError("session_range must be >= 0.")
        if self.avg_20d_session_range <= 0:
            raise ValueError("avg_20d_session_range must be > 0.")
        if self.current_volume_vs_average <= 0:
            raise ValueError("current_volume_vs_average must be > 0.")
        if not math.isfinite(self.cumulative_delta):
            raise ValueError("cumulative_delta must be finite.")

        for field_name in ("asia_bars", "london_bars", "ny_bars"):
            self._validate_strictly_ascending(field_name, getattr(self, field_name))

        historical_date = self.timestamp.date()
        for field_name in ("asia_bars", "london_bars", "ny_bars"):
            bar_dates = {bar.timestamp.date() for bar in getattr(self, field_name)}
            if bar_dates != {historical_date}:
                raise ValueError(
                    f"{field_name} must fall entirely on the same UTC date as timestamp."
                )

        if self.asia_bars[-1].timestamp >= self.london_bars[0].timestamp:
            raise ValueError("6E session segments must be ordered Asia before London.")
        if self.london_bars[-1].timestamp >= self.ny_bars[0].timestamp:
            raise ValueError("6E session segments must be ordered London before NY.")
        if self.ny_bars[-1].timestamp > self.timestamp:
            raise ValueError("ny_bars must end at or before the historical timestamp.")
        return self


class MGCHistoricalDataInput(CompilerStrictModel):
    contract: Literal["MGC"] = "MGC"
    timestamp: AwareDatetime
    current_price: float
    session_open: float
    prior_day_high: float
    prior_day_low: float
    prior_day_close: float
    overnight_high: float
    overnight_low: float
    current_session_vah: float
    current_session_val: float
    current_session_poc: float
    previous_session_vah: float
    previous_session_val: float
    previous_session_poc: float
    vwap: float
    session_range: float
    avg_20d_session_range: float
    cumulative_delta: float
    current_volume_vs_average: float
    event_calendar_remainder: list[EventCalendarEntry]

    @model_validator(mode="after")
    def validate_mgc_market_fields(self) -> "MGCHistoricalDataInput":
        if self.prior_day_high < self.prior_day_low:
            raise ValueError("prior_day_high must be >= prior_day_low.")
        if self.overnight_high < self.overnight_low:
            raise ValueError("overnight_high must be >= overnight_low.")
        if not (self.current_session_vah >= self.current_session_poc >= self.current_session_val):
            raise ValueError("current session profile levels must satisfy VAH >= POC >= VAL.")
        if not (self.previous_session_vah >= self.previous_session_poc >= self.previous_session_val):
            raise ValueError("previous session profile levels must satisfy VAH >= POC >= VAL.")
        if self.session_range < 0:
            raise ValueError("session_range must be >= 0.")
        if self.avg_20d_session_range <= 0:
            raise ValueError("avg_20d_session_range must be > 0.")
        if self.current_volume_vs_average <= 0:
            raise ValueError("current_volume_vs_average must be > 0.")
        if not math.isfinite(self.cumulative_delta):
            raise ValueError("cumulative_delta must be finite.")
        return self


class NQRelativeStrengthComparisonInput(CompilerStrictModel):
    contract: Literal["NQ"] = "NQ"
    es_timestamp: AwareDatetime
    es_current_price: float
    es_session_open: float

    @model_validator(mode="after")
    def validate_es_comparison_fields(self) -> "NQRelativeStrengthComparisonInput":
        if self.es_current_price <= 0:
            raise ValueError("es_current_price must be > 0.")
        if self.es_session_open <= 0:
            raise ValueError("es_session_open must be > 0.")
        return self


class ESCalendarSourceInput(CompilerStrictModel):
    contract: Literal["ES"] = "ES"
    event_calendar_remainder: list[EventCalendarEntry]


class ESBreadthSourceInput(CompilerStrictModel):
    contract: Literal["ES"] = "ES"
    breadth: str = Field(min_length=1)


class ESIndexCashToneSourceInput(CompilerStrictModel):
    contract: Literal["ES"] = "ES"
    index_cash_tone: IndexCashTone


class ESCumulativeDeltaSourceInput(CompilerStrictModel):
    contract: Literal["ES"] = "ES"
    cumulative_delta: float

    @model_validator(mode="after")
    def validate_cumulative_delta(self) -> "ESCumulativeDeltaSourceInput":
        if not math.isfinite(self.cumulative_delta):
            raise ValueError("cumulative_delta must be finite.")
        return self


class CLContractExtensionInput(CompilerStrictModel):
    contract: Literal["CL"] = "CL"
    eia_timing: EiaTiming
    oil_specific_headlines: str | None = None
    liquidity_sweep_summary: str | None = None
    dom_liquidity_summary: str | None = None
    realized_volatility_context: RealizedVolatilityContext | None = None


class ZNContractExtensionInput(CompilerStrictModel):
    contract: Literal["ZN"] = "ZN"
    cash_10y_yield: float
    treasury_auction_schedule: str = Field(min_length=1)
    macro_release_context: str = Field(min_length=1)
    absorption_summary: str | None = None


class NQContractExtensionInput(CompilerStrictModel):
    contract: Literal["NQ"] = "NQ"
    megacap_leadership_table: dict[str, Any] | None = None


class SixEContractExtensionInput(CompilerStrictModel):
    contract: Literal["6E"] = "6E"
    dxy_context: DxyContext
    europe_initiative_status: str = Field(min_length=1)


class MGCContractExtensionInput(CompilerStrictModel):
    contract: Literal["MGC"] = "MGC"
    dxy_context: DxyContext
    yield_context: YieldContext
    swing_penetration_volume_summary: str | None = None
    macro_fear_catalyst_summary: str = Field(min_length=1)


class ZNCash10YYieldSourceInput(CompilerStrictModel):
    contract: Literal["ZN"] = "ZN"
    cash_10y_yield: float

    @model_validator(mode="after")
    def validate_cash_10y_yield(self) -> "ZNCash10YYieldSourceInput":
        if not math.isfinite(self.cash_10y_yield):
            raise ValueError("cash_10y_yield must be finite.")
        return self


class ZNFredCash10YYieldRequest(CompilerStrictModel):
    contract: Literal["ZN"] = "ZN"
    observation_date: date
    series_id: str = Field(min_length=1)


class CLEiaTimingRequest(CompilerStrictModel):
    contract: Literal["CL"] = "CL"
    current_session_timestamp: AwareDatetime
    scheduled_release_time: AwareDatetime
    release_week_ending: date
    route: str = Field(min_length=1)
    facets: dict[str, list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_same_day_interpretation(self) -> "CLEiaTimingRequest":
        et = ZoneInfo("America/New_York")
        session_date = self.current_session_timestamp.astimezone(et).date()
        release_date = self.scheduled_release_time.astimezone(et).date()
        if session_date != release_date:
            raise ValueError(
                "CLEiaTimingRequest only supports same-day session vs release interpretation."
            )
        for facet_name, facet_values in self.facets.items():
            if not facet_name:
                raise ValueError("CLEiaTimingRequest facets must not use empty facet names.")
            if not facet_values:
                raise ValueError("CLEiaTimingRequest facets must not use empty facet value lists.")
            if any(not str(value).strip() for value in facet_values):
                raise ValueError("CLEiaTimingRequest facets must not contain empty values.")
        return self


class ESDatabentoHistoricalRequest(CompilerStrictModel):
    contract: Literal["ES"] = "ES"
    dataset: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    stype_in: Literal["raw_symbol", "instrument_id", "parent", "continuous"] = "raw_symbol"
    current_session_date: date
    bar_schema: Literal["ohlcv-1m"] = "ohlcv-1m"
    trades_schema: Literal["trades"] = "trades"


class CLDatabentoHistoricalRequest(CompilerStrictModel):
    contract: Literal["CL"] = "CL"
    dataset: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    stype_in: Literal["raw_symbol", "instrument_id", "parent", "continuous"] = "raw_symbol"
    current_session_date: date
    bar_schema: Literal["ohlcv-1m"] = "ohlcv-1m"
    trades_schema: Literal["trades"] = "trades"


class NQDatabentoHistoricalRequest(CompilerStrictModel):
    contract: Literal["NQ"] = "NQ"
    dataset: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    stype_in: Literal["raw_symbol", "instrument_id", "parent", "continuous"] = "raw_symbol"
    current_session_date: date
    bar_schema: Literal["ohlcv-1m"] = "ohlcv-1m"
    trades_schema: Literal["trades"] = "trades"


class SixEDatabentoHistoricalRequest(CompilerStrictModel):
    contract: Literal["6E"] = "6E"
    dataset: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    stype_in: Literal["raw_symbol", "instrument_id", "parent", "continuous"] = "raw_symbol"
    current_session_date: date
    bar_schema: Literal["ohlcv-1m"] = "ohlcv-1m"
    trades_schema: Literal["trades"] = "trades"


class MGCDatabentoHistoricalRequest(CompilerStrictModel):
    contract: Literal["MGC"] = "MGC"
    dataset: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    stype_in: Literal["raw_symbol", "instrument_id", "parent", "continuous"] = "raw_symbol"
    current_session_date: date
    bar_schema: Literal["ohlcv-1m"] = "ohlcv-1m"
    trades_schema: Literal["trades"] = "trades"


class ESDatabentoCumulativeDeltaRequest(CompilerStrictModel):
    contract: Literal["ES"] = "ES"
    dataset: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    stype_in: Literal["raw_symbol", "instrument_id", "parent", "continuous"] = "raw_symbol"
    current_session_date: date
    trades_schema: Literal["trades"] = "trades"


class ESManualOverlayInput(CompilerStrictModel):
    contract: Literal["ES"] = "ES"
    challenge_state: ChallengeState
    attached_visuals: AttachedVisuals = Field(default_factory=AttachedVisuals)
    opening_type: OpeningType
    major_higher_timeframe_levels: list[float] | None = Field(default=None, max_length=5)
    key_hvns: list[float] | None = Field(default=None, max_length=3)
    key_lvns: list[float] | None = Field(default=None, max_length=3)
    singles_excess_poor_high_low_notes: str | None = None
    cross_market_context: dict[str, Any] | None = None
    data_quality_flags: list[str] = Field(default_factory=list)


class CLManualOverlayInput(CompilerStrictModel):
    contract: Literal["CL"] = "CL"
    challenge_state: ChallengeState
    attached_visuals: AttachedVisuals = Field(default_factory=AttachedVisuals)
    opening_type: OpeningType
    major_higher_timeframe_levels: list[float] | None = Field(default=None, max_length=5)
    key_hvns: list[float] | None = Field(default=None, max_length=3)
    key_lvns: list[float] | None = Field(default=None, max_length=3)
    singles_excess_poor_high_low_notes: str | None = None
    cross_market_context: dict[str, Any] | None = None
    data_quality_flags: list[str] = Field(default_factory=list)


class ZNManualOverlayInput(CompilerStrictModel):
    contract: Literal["ZN"] = "ZN"
    challenge_state: ChallengeState
    attached_visuals: AttachedVisuals = Field(default_factory=AttachedVisuals)
    opening_type: OpeningType
    major_higher_timeframe_levels: list[float] | None = Field(default=None, max_length=5)
    key_hvns: list[float] | None = Field(default=None, max_length=3)
    key_lvns: list[float] | None = Field(default=None, max_length=3)
    singles_excess_poor_high_low_notes: str | None = None
    cross_market_context: dict[str, Any] | None = None
    data_quality_flags: list[str] = Field(default_factory=list)


class NQManualOverlayInput(CompilerStrictModel):
    contract: Literal["NQ"] = "NQ"
    challenge_state: ChallengeState
    attached_visuals: AttachedVisuals = Field(default_factory=AttachedVisuals)
    opening_type: OpeningType
    major_higher_timeframe_levels: list[float] | None = Field(default=None, max_length=5)
    key_hvns: list[float] | None = Field(default=None, max_length=3)
    key_lvns: list[float] | None = Field(default=None, max_length=3)
    singles_excess_poor_high_low_notes: str | None = None
    cross_market_context: dict[str, Any] | None = None
    data_quality_flags: list[str] = Field(default_factory=list)


class SixEManualOverlayInput(CompilerStrictModel):
    contract: Literal["6E"] = "6E"
    challenge_state: ChallengeState
    attached_visuals: AttachedVisuals = Field(default_factory=AttachedVisuals)
    opening_type: OpeningType
    major_higher_timeframe_levels: list[float] | None = Field(default=None, max_length=5)
    key_hvns: list[float] | None = Field(default=None, max_length=3)
    key_lvns: list[float] | None = Field(default=None, max_length=3)
    singles_excess_poor_high_low_notes: str | None = None
    cross_market_context: dict[str, Any] | None = None
    data_quality_flags: list[str] = Field(default_factory=list)


class MGCManualOverlayInput(CompilerStrictModel):
    contract: Literal["MGC"] = "MGC"
    challenge_state: ChallengeState
    attached_visuals: AttachedVisuals = Field(default_factory=AttachedVisuals)
    opening_type: OpeningType
    major_higher_timeframe_levels: list[float] | None = Field(default=None, max_length=5)
    key_hvns: list[float] | None = Field(default=None, max_length=3)
    key_lvns: list[float] | None = Field(default=None, max_length=3)
    singles_excess_poor_high_low_notes: str | None = None
    cross_market_context: dict[str, Any] | None = None
    data_quality_flags: list[str] = Field(default_factory=list)
