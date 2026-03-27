from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

ContractSymbol = Literal["ES", "NQ", "CL", "ZN", "6E", "MGC"]
TradeDirection = Literal["LONG", "SHORT"]
SessionType = Literal["RTH", "ETH", "GLOBEX"]
OpeningType = Literal[
    "Open-Drive",
    "Open-Test-Drive",
    "Open-Rejection-Reverse",
    "Open-Auction",
    "NOT_YET_CLASSIFIED",
]
EtTime = Annotated[str, Field(pattern=r"^\d{2}:\d{2}$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)


class PerContractIntMap(StrictModel):
    ES: int
    NQ: int
    CL: int
    ZN: int
    six_e: int = Field(alias="6E")
    MGC: int


class PerContractOptionalDateTimeMap(StrictModel):
    ES: AwareDatetime | None
    NQ: AwareDatetime | None
    CL: AwareDatetime | None
    ZN: AwareDatetime | None
    six_e: AwareDatetime | None = Field(alias="6E")
    MGC: AwareDatetime | None


class PerContractOptionalDirectionMap(StrictModel):
    ES: TradeDirection | None
    NQ: TradeDirection | None
    CL: TradeDirection | None
    ZN: TradeDirection | None
    six_e: TradeDirection | None = Field(alias="6E")
    MGC: TradeDirection | None


class OpenPosition(StrictModel):
    contract: ContractSymbol
    direction: TradeDirection
    size: int
    entry_price: float
    current_risk_dollars: float


class ChallengeState(StrictModel):
    schema_name: Literal["challenge_state_v1"] = Field(default="challenge_state_v1", alias="$schema")
    current_balance: float
    daily_realized_pnl: float
    max_risk_per_trade_dollars: float
    daily_loss_stop_dollars: float
    minimum_reward_to_risk: float
    event_lockout_minutes_before: int
    event_lockout_minutes_after: int
    max_position_size_by_contract: PerContractIntMap
    max_trades_per_day: int
    max_trades_per_contract_per_day: int
    cooldown_after_stopout_minutes: int
    current_open_positions: list[OpenPosition]
    trades_today_all: int
    trades_today_by_contract: PerContractIntMap
    profit_target_dollars: float
    last_stopout_time_by_contract: PerContractOptionalDateTimeMap | None = None
    last_trade_direction_by_contract: PerContractOptionalDirectionMap | None = None


class ContractMetadata(StrictModel):
    schema_name: Literal["contract_metadata_v1"] = Field(default="contract_metadata_v1", alias="$schema")
    contract: ContractSymbol
    tick_size: float
    dollar_per_tick: float
    point_value: float
    max_position_size: int
    slippage_ticks: int
    allowed_hours_start_et: EtTime
    allowed_hours_end_et: EtTime


class EventCalendarEntry(StrictModel):
    name: str
    time: AwareDatetime
    tier: Literal[1, 2]
    event_state: Literal["upcoming", "released"] = "upcoming"
    minutes_until: int | None = None
    minutes_since: int | None = None

    @model_validator(mode="after")
    def validate_event_state_fields(self) -> "EventCalendarEntry":
        if self.event_state == "upcoming":
            if self.minutes_until is None or self.minutes_since is not None:
                raise ValueError(
                    "Upcoming events require minutes_until and must not include minutes_since."
                )
        if self.event_state == "released":
            if self.minutes_since is None or self.minutes_until is not None:
                raise ValueError(
                    "Released events require minutes_since and must not include minutes_until."
                )
        return self


class MarketPacket(StrictModel):
    schema_name: Literal["market_packet_v1"] = Field(default="market_packet_v1", alias="$schema")
    timestamp: AwareDatetime
    contract: ContractSymbol
    session_type: SessionType
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
    opening_type: OpeningType
    major_higher_timeframe_levels: list[float] | None = Field(default=None, max_length=5)
    key_hvns: list[float] | None = Field(default=None, max_length=3)
    key_lvns: list[float] | None = Field(default=None, max_length=3)
    singles_excess_poor_high_low_notes: str | None = None
    event_calendar_remainder: list[EventCalendarEntry]
    cross_market_context: dict[str, Any] | None
    data_quality_flags: list[str] | None


class AttachedVisuals(StrictModel):
    schema_name: Literal["attached_visuals_v1"] = Field(default="attached_visuals_v1", alias="$schema")
    daily_chart_attached: bool = False
    higher_timeframe_chart_attached: bool = False
    tpo_chart_attached: bool = False
    volume_profile_attached: bool = False
    execution_chart_attached: bool = False
    footprint_chart_attached: bool = False
    dom_snapshot_attached: bool = False
