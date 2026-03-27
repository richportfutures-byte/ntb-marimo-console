from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from .inputs import ContractMetadata, MarketPacket, StrictModel

RealizedVolatilityContext = Literal["elevated", "normal", "compressed"]


class EiaTiming(StrictModel):
    status: Literal["not_today", "scheduled", "released"]
    scheduled_time: AwareDatetime | None = None
    minutes_until: int | None = None
    minutes_since: int | None = None

    @model_validator(mode="after")
    def validate_status_fields(self) -> "EiaTiming":
        if self.status == "not_today":
            if any(
                value is not None
                for value in (self.scheduled_time, self.minutes_until, self.minutes_since)
            ):
                raise ValueError("not_today EIA timing cannot include release timing fields.")
        if self.status == "scheduled":
            if self.scheduled_time is None or self.minutes_until is None or self.minutes_since is not None:
                raise ValueError(
                    "scheduled EIA timing requires scheduled_time and minutes_until only."
                )
        if self.status == "released":
            if self.scheduled_time is None or self.minutes_since is None or self.minutes_until is not None:
                raise ValueError(
                    "released EIA timing requires scheduled_time and minutes_since only."
                )
        return self


class CLContractMetadata(ContractMetadata):
    contract: Literal["CL"]


class CLMarketPacket(MarketPacket):
    contract: Literal["CL"]


class CLContractSpecificExtension(StrictModel):
    schema_name: Literal["contract_specific_extension_v1"] = Field(
        default="contract_specific_extension_v1",
        alias="$schema",
    )
    contract: Literal["CL"] = "CL"
    eia_timing: EiaTiming
    oil_specific_headlines: str | None = None
    liquidity_sweep_summary: str | None = None
    dom_liquidity_summary: str | None = None
    realized_volatility_context: RealizedVolatilityContext
